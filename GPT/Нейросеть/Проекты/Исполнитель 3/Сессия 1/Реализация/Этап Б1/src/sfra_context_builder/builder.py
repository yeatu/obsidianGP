"""Pure Context Pack assembly orchestration."""

from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from .budget import (
    compact_json,
    included_tokens,
    make_deferred_entry,
    make_included_entry,
)
from .coverage import build_coverage, focus_matches
from .dependencies import DependencyGroup, build_dependency_groups
from .integrity import content_hash
from .models import DependencyResolver, RetrievalCandidate, SearchBatch, SearchRequest, SnapshotRef, TokenCounterProtocol
from .ranking import rank_key
from .validation import ContractValidationError, parse_candidate, parse_search_batch, parse_search_request, validate_context_pack


class ContextBuilder:
    """Build Context Packs without transport or storage dependencies."""

    def __init__(self, token_counter: TokenCounterProtocol) -> None:
        self._token_counter = token_counter

    def build(
        self,
        request: Mapping[str, Any] | SearchRequest,
        batch: Mapping[str, Any] | SearchBatch,
        dependency_resolver: DependencyResolver | None = None,
        *,
        snapshot: SnapshotRef | None = None,
    ) -> dict[str, Any]:
        normalized_request = (
            request if isinstance(request, SearchRequest) else parse_search_request(request)
        )
        normalized_batch = (
            batch if isinstance(batch, SearchBatch) else parse_search_batch(batch)
        )
        if dependency_resolver is not None and snapshot is None:
            raise ContractValidationError(
                "snapshot is required when a DependencyResolver is supplied"
            )

        search_complete = normalized_batch.complete and not normalized_batch.truncated_by_limit
        diagnostics: list[dict[str, Any]] = []
        rejected_count = 0
        retrieved_count = len(normalized_batch.candidates)

        verified: list[RetrievalCandidate] = []
        for candidate in normalized_batch.candidates:
            actual = content_hash(candidate.raw_text)
            if actual != candidate.content_hash:
                rejected_count += 1
                diagnostics.append({
                    "code": "content_hash_mismatch",
                    "severity": "error",
                    "message": "Кандидат исключён: SHA-256(raw_text UTF-8) не совпадает с content_hash.",
                    "node_ids": [candidate.node_id],
                    "details": {
                        "expected_hash": candidate.content_hash,
                        "actual_hash": actual,
                        "included": False,
                        "deferred": False,
                    },
                })
                continue
            verified.append(candidate)

        candidates, conflicts = self._deduplicate(verified)
        if conflicts:
            rejected_count += sum(len(hashes) for hashes in conflicts.values())
            for node_id, hashes in sorted(conflicts.items()):
                diagnostics.append({
                    "code": "version_conflict",
                    "severity": "error",
                    "message": f"В одном SearchBatch обнаружены конфликтующие версии Node ID {node_id}.",
                    "node_ids": [node_id],
                    "details": {"content_hashes": sorted(hashes), "included": False},
                })
            candidates = [candidate for candidate in candidates if candidate.node_id not in conflicts]

        matches: dict[str, dict[str, str]] = {
            candidate.node_id: focus_matches(candidate, normalized_request.focus)
            for candidate in candidates
            if candidate.from_retrieval
        }
        # Preserve adapter matches and exact fallback matches as normalized metadata.
        candidates = [
            self._with_focus_matches(candidate, matches.get(candidate.node_id, {}))
            for candidate in candidates
        ]

        groups, candidates, resolver_rejected = build_dependency_groups(
            candidates,
            resolver=dependency_resolver,
            snapshot=snapshot,
            verify_resolved_hash=lambda item: content_hash(item.raw_text) == item.content_hash,
            diagnostics=diagnostics,
        )
        rejected_count += resolver_rejected
        by_id = {candidate.node_id: candidate for candidate in candidates}

        # Resolver-only nodes must not become focus hits.
        matches = {
            candidate.node_id: focus_matches(candidate, normalized_request.focus)
            for candidate in candidates
            if candidate.from_retrieval
        }

        known_pairs = {(item.node_id, item.content_hash) for item in normalized_request.known}
        known_versions: dict[str, set[str]] = defaultdict(set)
        for item in normalized_request.known:
            known_versions[item.node_id].add(item.content_hash)

        known_ids = {
            node_id
            for node_id, version_hash in by_id.items()
            if (node_id, version_hash.content_hash) in known_pairs
        }
        known_entries = [
            {
                "node_id": node_id,
                "content_hash": by_id[node_id].content_hash,
                "delivery": "already_known_not_repeated",
            }
            for node_id in sorted(known_ids)
        ]
        version_changes = []
        for node_id, candidate in sorted(by_id.items()):
            previous = sorted(known_versions.get(node_id, set()) - {candidate.content_hash})
            if previous:
                version_changes.append({
                    "node_id": node_id,
                    "known_hash": previous[0],
                    "current_hash": candidate.content_hash,
                    "action": "deliver_current_version_if_budget_allows",
                })

        # Unselected candidates start in Deferred for coverage accounting. A successful
        # atomic inclusion moves the entire dependency group from Deferred to Included.
        deferred_reason: dict[str, str] = {
            node_id: "lower_priority_budget_limit"
            for node_id in by_id
            if node_id not in known_ids
        }
        deferred_unresolved: dict[str, tuple[str, ...]] = {}
        included_entries: list[dict[str, Any]] = []
        included_ids: set[str] = set()
        processed_groups: set[str] = set()
        unresolved_required_groups = False
        def coverage_for(
            proposed_included: set[str],
            proposed_deferred: set[str],
        ) -> list[dict[str, Any]]:
            return build_coverage(
                normalized_request.focus,
                matches,
                proposed_included,
                known_ids,
                proposed_deferred,
                search_complete,
            )

        def try_group(group: DependencyGroup) -> None:
            nonlocal included_entries, included_ids, unresolved_required_groups
            processed_groups.add(group.group_id)
            new_members = [
                member for member in group.members
                if member.node_id not in known_ids
            ]
            if group.has_unresolved:
                unresolved_required_groups = True
                for member in new_members:
                    deferred_reason[member.node_id] = "unresolved_required_dependency"
                    deferred_unresolved[member.node_id] = group.unresolved_dependency_ids
                diagnostics.append({
                    "code": "unresolved_required_dependency",
                    "severity": "warning",
                    "message": "Неделимая группа отложена: обязательная зависимость не разрешена в закреплённом snapshot.",
                    "node_ids": [member.node_id for member in group.members],
                    "details": {
                        "group_node_ids": [member.node_id for member in group.members],
                        "unresolved_dependency_ids": list(group.unresolved_dependency_ids),
                        "required_group_id": group.group_id,
                    },
                })
                return

            ordered_members = self._order_group_members(group)
            new_members = [m for m in ordered_members if m.node_id not in known_ids]
            proposed_entries = list(included_entries)
            for member in new_members:
                proposed_entries.append(make_included_entry(
                    member,
                    token_counter=self._token_counter,
                    inclusion_reason=self._inclusion_reason(member, group),
                    is_required_dependency=member.node_id in group.referenced_ids,
                ))
            proposed_ids = included_ids | {member.node_id for member in new_members}
            cost = included_tokens(proposed_entries, self._token_counter)
            if cost <= normalized_request.budget_tokens:
                included_entries = proposed_entries
                included_ids = proposed_ids
                for member in new_members:
                    deferred_reason.pop(member.node_id, None)
                    deferred_unresolved.pop(member.node_id, None)
                return

            if group.required:
                reason = "required_group_budget_limit"
            elif len(new_members) > 1:
                reason = "lower_priority_budget_limit"
            else:
                reason = "budget_limit"
            for member in new_members:
                deferred_reason[member.node_id] = reason
            diagnostics.append({
                "code": reason,
                "severity": "warning",
                "message": "Неделимая группа целиком отложена: она не помещается в budget_tokens.",
                "node_ids": [member.node_id for member in group.members],
                "details": {
                    "group_node_ids": [member.node_id for member in group.members],
                    "estimated_tokens": cost,
                    "budget_tokens": normalized_request.budget_tokens,
                    "required_group_id": group.group_id,
                },
            })

        # Required groups are always considered before focus and ordinary ranking.
        required_groups = [group for group in groups if group.required]
        for group in required_groups:
            try_group(group)

        # Then select the best not-yet-considered group for each focus aspect, in request order.
        for aspect in normalized_request.focus:
            eligible = [
                group for group in groups
                if group.group_id not in processed_groups
                and any(
                    aspect.aspect_id in matches.get(member.node_id, {})
                    for member in group.members
                )
            ]
            if eligible:
                eligible.sort(key=lambda group: min(rank_key(member) for member in group.members))
                try_group(eligible[0])

        # Finally process the remaining groups in deterministic rank order.
        for group in sorted(groups, key=lambda g: min(rank_key(member) for member in g.members)):
            if group.group_id not in processed_groups:
                try_group(group)

        deferred_entries: list[dict[str, Any]] = []
        for group in groups:
            for member in self._order_group_members(group):
                if member.node_id in included_ids or member.node_id in known_ids:
                    continue
                reason = deferred_reason.get(member.node_id, "lower_priority_budget_limit")
                estimated = self._token_counter.count(member.raw_text)
                deferred_entries.append(make_deferred_entry(
                    member,
                    estimated_tokens=estimated,
                    reason=reason,
                    required_group_id=group.group_id,
                    unresolved_dependency_ids=deferred_unresolved.get(member.node_id, ()),
                ))
        # Preserve selection order: required groups first, then focus, then rank.
        deferred_entries.sort(
            key=lambda item: (
                rank_key(by_id[item["node_id"]]),
                item["node_id"],
            )
        )
        final_deferred_ids = {item["node_id"] for item in deferred_entries}
        coverage = coverage_for(included_ids, final_deferred_ids)

        parallel_sources = self._parallel_sources(
            [candidate for candidate in candidates if candidate.from_retrieval]
        )
        if parallel_sources:
            diagnostics.append({
                "code": "parallel_sources_preserved",
                "severity": "info",
                "message": "Потенциально пересекающиеся источники сохранены отдельно; автоматическая арбитрация не выполнялась.",
                "node_ids": sorted({
                    source["node_id"]
                    for group in parallel_sources
                    for source in group["sources"]
                }),
                "details": {"relationship_is_not_a_conflict_judgement": True},
            })

        if not search_complete:
            diagnostics.append({
                "code": "search_result_truncated",
                "severity": "warning",
                "message": "SearchAdapter не подтвердил полноту поисковой выдачи.",
                "node_ids": [],
                "details": {
                    "complete": normalized_batch.complete,
                    "truncated_by_limit": normalized_batch.truncated_by_limit,
                    "cursor_available": normalized_batch.cursor is not None,
                },
            })

        for candidate in candidates:
            if candidate.unmapped_match_reasons:
                diagnostics.append({
                    "code": "unmapped_match_reasons",
                    "severity": "info",
                    "message": "Неизвестные match_reasons сохранены без интерпретации и веса.",
                    "node_ids": [candidate.node_id],
                    "details": {"values": list(candidate.unmapped_match_reasons)},
                })

        not_found_count = sum(1 for aspect in coverage if aspect["status"] == "not_found_in_retrieval")
        available_count = sum(1 for aspect in coverage if aspect["status"] in {"found", "deferred"})
        included_aspect_count = sum(1 for aspect in coverage if aspect["included_node_ids"])
        focus_count = len(coverage)
        available_ratio = None if focus_count == 0 else available_count / focus_count
        included_ratio = None if focus_count == 0 else included_aspect_count / focus_count

        tokens_used = included_tokens(included_entries, self._token_counter)

        if any(item["severity"] == "error" for item in diagnostics):
            status = "integrity_warning"
        elif not candidates and search_complete:
            status = "empty"
        elif unresolved_required_groups:
            status = "partial"
        elif any(item["reason"] in {
            "budget_limit", "required_group_budget_limit", "lower_priority_budget_limit"
        } for item in deferred_entries):
            status = "budget_limited"
        elif (
            not search_complete
            or any(item["reason"] == "unresolved_required_dependency" for item in deferred_entries)
            or any(aspect["status"] in {"deferred", "not_found_in_retrieval"} for aspect in coverage)
        ):
            status = "partial"
        else:
            status = "complete"

        pack: dict[str, Any] = {
            "schema_version": "sfra.context_pack.v1",
            "status": status,
            "query": normalized_request.query,
            "task": normalized_request.task,
            "search_complete": search_complete,
            "Included": included_entries,
            "Coverage": coverage,
            "Deferred": deferred_entries,
            "Parallel Sources": parallel_sources,
            "Known": known_entries,
            "Version Changes": version_changes,
            "Statistics": {
                "retrieved_count": retrieved_count,
                "included_count": len(included_entries),
                "deferred_count": len(deferred_entries),
                "known_count": len(known_entries),
                "not_found_aspect_count": not_found_count,
                "focus_count": focus_count,
                "coverage_available_ratio": available_ratio,
                "coverage_included_ratio": included_ratio,
                "budget_tokens": normalized_request.budget_tokens,
                "tokens_used": tokens_used,
                "response_tokens_estimated": 0,
                "token_counter": dict(self._token_counter.metadata()),
                "example_counts_are_illustrative": False,
                "rejected_count": rejected_count,
            },
            "Diagnostics": diagnostics,
        }
        estimate = 0
        for _ in range(8):
            pack["Statistics"]["response_tokens_estimated"] = estimate
            updated_estimate = self._token_counter.count(compact_json(pack))
            if updated_estimate == estimate:
                break
            estimate = updated_estimate
        pack["Statistics"]["response_tokens_estimated"] = estimate
        validate_context_pack(pack)
        return pack

    @staticmethod
    def _with_focus_matches(
        candidate: RetrievalCandidate,
        matches: Mapping[str, str],
    ) -> RetrievalCandidate:
        if not matches:
            return candidate
        from dataclasses import replace
        ids = tuple(dict.fromkeys((*candidate.matched_focus_ids, *matches.keys())))
        return replace(candidate, matched_focus_ids=ids)

    @staticmethod
    def _deduplicate(
        candidates: Sequence[RetrievalCandidate],
    ) -> tuple[list[RetrievalCandidate], dict[str, set[str]]]:
        from dataclasses import replace
        by_pair: dict[tuple[str, str], RetrievalCandidate] = {}
        hashes_by_id: dict[str, set[str]] = defaultdict(set)
        for candidate in candidates:
            hashes_by_id[candidate.node_id].add(candidate.content_hash)
            previous = by_pair.get(candidate.identity)
            if previous is None:
                by_pair[candidate.identity] = candidate
                continue
            merged_signals = dict(previous.signals)
            for key, value in candidate.signals.items():
                if isinstance(value, bool) and isinstance(merged_signals.get(key), bool):
                    merged_signals[key] = merged_signals[key] or value
                elif key not in merged_signals:
                    merged_signals[key] = value
            if previous.entity_metadata is None:
                merged_entity_metadata = candidate.entity_metadata
            elif candidate.entity_metadata is None or candidate.entity_metadata == previous.entity_metadata:
                merged_entity_metadata = previous.entity_metadata
            elif isinstance(previous.entity_metadata, (list, tuple)):
                merged_entity_metadata = list(previous.entity_metadata)
                if candidate.entity_metadata not in merged_entity_metadata:
                    merged_entity_metadata.append(candidate.entity_metadata)
            else:
                merged_entity_metadata = [previous.entity_metadata, candidate.entity_metadata]

            if previous.has_author_notes is True or candidate.has_author_notes is True:
                merged_has_author_notes = True
            elif previous.has_author_notes is None or candidate.has_author_notes is None:
                merged_has_author_notes = None
            else:
                merged_has_author_notes = False

            by_pair[candidate.identity] = replace(
                previous,
                original_order=min(previous.original_order, candidate.original_order),
                node_type=previous.node_type or candidate.node_type,
                parent_node_id=previous.parent_node_id or candidate.parent_node_id,
                zone=previous.zone or candidate.zone,
                has_author_notes=merged_has_author_notes,
                entity_metadata=merged_entity_metadata,
                match_reasons=tuple(dict.fromkeys((*previous.match_reasons, *candidate.match_reasons))),
                unmapped_match_reasons=tuple(dict.fromkeys((*previous.unmapped_match_reasons, *candidate.unmapped_match_reasons))),
                matched_focus_ids=tuple(dict.fromkeys((*previous.matched_focus_ids, *candidate.matched_focus_ids))),
                matched_entities=tuple(dict.fromkeys((*previous.matched_entities, *candidate.matched_entities))),
                matched_facets=tuple(dict.fromkeys((*previous.matched_facets, *candidate.matched_facets))),
                matched_terms=tuple(dict.fromkeys((*previous.matched_terms, *candidate.matched_terms))),
                required_with=tuple(dict.fromkeys((*previous.required_with, *candidate.required_with))),
                parent_context_required=previous.parent_context_required or candidate.parent_context_required,
                overlap_group_id=previous.overlap_group_id or candidate.overlap_group_id,
                overlap_hint=previous.overlap_hint or candidate.overlap_hint,
                preservation=(
                    "required"
                    if "required" in {previous.preservation, candidate.preservation}
                    else "normal"
                ),
                signals=merged_signals,
            )
        conflicts = {
            node_id: hashes for node_id, hashes in hashes_by_id.items() if len(hashes) > 1
        }
        return list(by_pair.values()), conflicts

    @staticmethod
    def _order_group_members(group: DependencyGroup) -> list[RetrievalCandidate]:
        dependency_ids = set(group.referenced_ids)
        roots = sorted(
            (item for item in group.members if item.node_id not in dependency_ids),
            key=rank_key,
        )
        dependencies = sorted(
            (item for item in group.members if item.node_id in dependency_ids),
            key=lambda item: item.node_id,
        )
        if not roots:
            return sorted(group.members, key=rank_key)
        return [*roots, *dependencies]

    @staticmethod
    def _inclusion_reason(candidate: RetrievalCandidate, group: DependencyGroup) -> str:
        if candidate.node_id in group.parent_context_ids:
            return "required_parent_context"
        if candidate.node_id in group.referenced_ids:
            return "required_dependency"
        return "retrieval_candidate"

    @staticmethod
    def _parallel_sources(candidates: Sequence[RetrievalCandidate]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], dict[str, Any]] = {}

        def add(key: tuple[str, str], relation: str, description: str, candidate: RetrievalCandidate, signal: str) -> None:
            entry = grouped.setdefault(key, {
                "group_id": key[1],
                "relation": relation,
                "description": description,
                "kept_separate": True,
                "sources": [],
            })
            if not any(source["node_id"] == candidate.node_id for source in entry["sources"]):
                entry["sources"].append({
                    "node_id": candidate.node_id,
                    "source_path": candidate.source_path,
                    "content_hash": candidate.content_hash,
                    "signal": signal,
                })

        by_basename: dict[str, list[RetrievalCandidate]] = defaultdict(list)
        by_overlap: dict[str, list[RetrievalCandidate]] = defaultdict(list)
        by_hint: dict[str, list[RetrievalCandidate]] = defaultdict(list)
        for candidate in candidates:
            basename = PurePosixPath(candidate.source_path).name.casefold()
            by_basename[basename].append(candidate)
            if candidate.overlap_group_id:
                by_overlap[candidate.overlap_group_id].append(candidate)
            if candidate.overlap_hint:
                by_hint[candidate.overlap_hint].append(candidate)

        for basename, members in by_basename.items():
            paths = {item.source_path for item in members}
            if len(members) >= 2 and len(paths) >= 2:
                key_id = f"basename:{basename}"
                for member in members:
                    add(
                        ("same_basename_different_path", key_id),
                        "same_basename_different_path",
                        "Совпадает имя файла, пути различаются; источники сохранены отдельно.",
                        member,
                        "same_basename_different_path",
                    )
        for overlap_id, members in by_overlap.items():
            if len(members) >= 2:
                key_id = f"overlap:{overlap_id}"
                for member in members:
                    add(
                        ("adapter_overlap_group", key_id),
                        "adapter_overlap_group",
                        "Поисковый адаптер отметил потенциальное пересечение; источники сохранены отдельно.",
                        member,
                        "adapter_overlap_group",
                    )
        for hint, members in by_hint.items():
            if len(members) >= 2:
                key_id = f"hint:{hint}"
                for member in members:
                    add(
                        ("adapter_overlap_hint", key_id),
                        "adapter_overlap_hint",
                        "Поисковый движок передал подсказку о возможном пересечении; источники сохранены отдельно.",
                        member,
                        "adapter_overlap_hint",
                    )
        result = list(grouped.values())
        for item in result:
            item["sources"].sort(key=lambda source: (source["source_path"], source["node_id"]))
        return sorted(result, key=lambda item: (item["relation"], item["group_id"]))
