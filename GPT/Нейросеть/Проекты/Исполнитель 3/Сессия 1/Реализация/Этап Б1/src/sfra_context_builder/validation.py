"""Strict contract validation and normalization for core operation inputs."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .models import (
    FocusAspect,
    KnownVersion,
    RetrievalCandidate,
    SearchBatch,
    SearchRequest,
)

HASH_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
NODE_HASH_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")


class ContractValidationError(ValueError):
    """Raised when an operation payload violates its published contract."""


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{name} must be an object")
    return value


def _string(value: Any, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ContractValidationError(f"{name} must be a string")
    if not allow_empty and not value.strip():
        raise ContractValidationError(f"{name} must not be empty")
    return value


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ContractValidationError(f"{name} must be an array of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_string(item, f"{name}[{index}]"))
    return tuple(result)


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractValidationError(f"{name} must be an integer >= {minimum}")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractValidationError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ContractValidationError(f"{name} must be finite")
    return result


def _hash(value: Any, name: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise ContractValidationError(f"{name} must be sha256:<64 hex> or null")
    return value.lower()


def parse_search_request(value: Mapping[str, Any]) -> SearchRequest:
    obj = _mapping(value, "SearchRequest")
    allowed = {
        "query", "task", "entities", "facets", "budget_tokens",
        "known", "zones", "focus",
    }
    extra = set(obj) - allowed
    if extra:
        raise ContractValidationError(
            f"SearchRequest has unsupported fields: {', '.join(sorted(extra))}"
        )

    query = _string(obj.get("query"), "query")
    task_raw = obj.get("task")
    task = None if task_raw is None else _string(task_raw, "task", allow_empty=True)
    budget = _integer(obj.get("budget_tokens", 3000), "budget_tokens", minimum=1)

    known_items = obj.get("known", ())
    if not isinstance(known_items, Sequence) or isinstance(known_items, (str, bytes)):
        raise ContractValidationError("known must be an array")
    known: list[KnownVersion] = []
    seen_known: set[tuple[str, str]] = set()
    for index, raw in enumerate(known_items):
        item = _mapping(raw, f"known[{index}]")
        if set(item) - {"node_id", "content_hash"}:
            raise ContractValidationError(f"known[{index}] contains unsupported fields")
        node_id = _string(item.get("node_id"), f"known[{index}].node_id")
        content_hash = _hash(item.get("content_hash"), f"known[{index}].content_hash")
        pair = (node_id, str(content_hash))
        if pair not in seen_known:
            known.append(KnownVersion(node_id, str(content_hash)))
            seen_known.add(pair)

    focus_items = obj.get("focus", ())
    if not isinstance(focus_items, Sequence) or isinstance(focus_items, (str, bytes)):
        raise ContractValidationError("focus must be an array")
    focus: list[FocusAspect] = []
    focus_ids: set[str] = set()
    for index, raw in enumerate(focus_items):
        if isinstance(raw, str):
            label = _string(raw, f"focus[{index}]")
            aspect_id = f"focus_{index + 1:03d}"
            aspect = FocusAspect(aspect_id=aspect_id, label=label)
        else:
            item = _mapping(raw, f"focus[{index}]")
            allowed_focus = {"id", "label", "entities", "facets", "terms", "match_mode"}
            extra_focus = set(item) - allowed_focus
            if extra_focus:
                raise ContractValidationError(
                    f"focus[{index}] has unsupported fields: {', '.join(sorted(extra_focus))}"
                )
            aspect_id = _string(item.get("id"), f"focus[{index}].id")
            label = _string(item.get("label"), f"focus[{index}].label")
            mode = item.get("match_mode", "any")
            if not isinstance(mode, str) or mode not in {"any", "all"}:
                raise ContractValidationError(f"focus[{index}].match_mode must be any or all")
            aspect = FocusAspect(
                aspect_id=aspect_id,
                label=label,
                entities=_string_tuple(item.get("entities", ()), f"focus[{index}].entities"),
                facets=_string_tuple(item.get("facets", ()), f"focus[{index}].facets"),
                terms=_string_tuple(item.get("terms", ()), f"focus[{index}].terms"),
                match_mode=mode,
            )
        if aspect.aspect_id in focus_ids:
            raise ContractValidationError(f"duplicate focus id: {aspect.aspect_id}")
        focus_ids.add(aspect.aspect_id)
        focus.append(aspect)

    return SearchRequest(
        query=query,
        task=task,
        budget_tokens=budget,
        entities=_string_tuple(obj.get("entities", ()), "entities"),
        facets=_string_tuple(obj.get("facets", ()), "facets"),
        zones=_string_tuple(obj.get("zones", ()), "zones"),
        known=tuple(known),
        focus=tuple(focus),
    )


def parse_candidate(
    value: Mapping[str, Any],
    *,
    original_order: int,
    dependency: bool = False,
) -> RetrievalCandidate:
    obj = _mapping(value, "candidate")
    required = {
        "node_id", "source_path", "heading_path", "line_start",
        "line_end", "content_hash", "raw_text",
    }
    missing = required - set(obj)
    if missing:
        raise ContractValidationError(
            f"candidate is missing required fields: {', '.join(sorted(missing))}"
        )

    node_id = _string(obj["node_id"], "candidate.node_id")
    source_path = _string(obj["source_path"], "candidate.source_path")
    heading_path = _string_tuple(obj.get("heading_path"), "candidate.heading_path")
    line_start = _integer(obj["line_start"], "candidate.line_start", minimum=1)
    line_end = _integer(obj["line_end"], "candidate.line_end", minimum=1)
    if line_end < line_start:
        raise ContractValidationError("candidate.line_end must be >= line_start")
    content_hash = _hash(obj["content_hash"], "candidate.content_hash")
    raw_text = _string(obj["raw_text"], "candidate.raw_text", allow_empty=True)

    match_type_raw = obj.get("match_type", "required_dependency" if dependency else None)
    match_type = _string(match_type_raw, "candidate.match_type")

    relevance = obj.get("relevance")
    tier: int | None = None
    bm25: float | None = None
    if relevance is not None:
        rel = _mapping(relevance, "candidate.relevance")
        if "tier" not in rel or "bm25" not in rel:
            raise ContractValidationError("candidate.relevance requires tier and bm25")
        tier = _integer(rel["tier"], "candidate.relevance.tier", minimum=1)
        if tier > 6:
            raise ContractValidationError("candidate.relevance.tier must be between 1 and 6")
        bm25 = _number(rel["bm25"], "candidate.relevance.bm25")

    score_raw = obj.get("score")
    score = None if score_raw is None else _number(score_raw, "candidate.score")
    score_direction = obj.get("score_direction")
    if score_direction is not None and score_direction not in {"asc", "desc"}:
        raise ContractValidationError("candidate.score_direction must be asc or desc")
    if tier is None and score is not None and score_direction is None:
        raise ContractValidationError(
            "score_direction is required when score is supplied without relevance.tier"
        )

    preservation = obj.get("preservation", "normal")
    if preservation not in {"required", "normal"}:
        raise ContractValidationError("candidate.preservation must be required or normal")
    parent_required = obj.get("parent_context_required", False)
    if not isinstance(parent_required, bool):
        raise ContractValidationError("candidate.parent_context_required must be boolean")
    generation_raw = obj.get("index_generation")
    generation = (
        None if generation_raw is None
        else _integer(generation_raw, "candidate.index_generation", minimum=0)
    )
    document_hash = _hash(
        obj.get("document_hash"), "candidate.document_hash", nullable=True
    )

    signals = obj.get("signals", {})
    signals = _mapping(signals, "candidate.signals")
    for key, item in signals.items():
        if not isinstance(item, (bool, str, int, float)) and item is not None:
            raise ContractValidationError(f"candidate.signals.{key} has unsupported value")
        if isinstance(item, float) and not math.isfinite(item):
            raise ContractValidationError(f"candidate.signals.{key} must be finite")

    optional_text = lambda key: (
        None if obj.get(key) is None else _string(obj[key], f"candidate.{key}", allow_empty=True)
    )
    has_author_notes = obj.get("has_author_notes")
    if has_author_notes is not None and not isinstance(has_author_notes, bool):
        raise ContractValidationError("candidate.has_author_notes must be boolean or null")

    return RetrievalCandidate(
        node_id=node_id,
        source_path=source_path,
        heading_path=heading_path,
        line_start=line_start,
        line_end=line_end,
        content_hash=str(content_hash),
        raw_text=raw_text,
        match_type=match_type,
        original_order=original_order,
        node_type=optional_text("node_type"),
        parent_node_id=optional_text("parent_node_id"),
        relevance_tier=tier,
        relevance_bm25=bm25,
        score=score,
        score_direction=score_direction,
        match_reasons=_string_tuple(obj.get("match_reasons", ()), "candidate.match_reasons"),
        unmapped_match_reasons=_string_tuple(
            obj.get("unmapped_match_reasons", ()), "candidate.unmapped_match_reasons"
        ),
        signals=dict(signals),
        matched_focus_ids=_string_tuple(
            obj.get("matched_focus_ids", ()), "candidate.matched_focus_ids"
        ),
        matched_entities=_string_tuple(
            obj.get("matched_entities", ()), "candidate.matched_entities"
        ),
        matched_facets=_string_tuple(
            obj.get("matched_facets", ()), "candidate.matched_facets"
        ),
        matched_terms=_string_tuple(
            obj.get("matched_terms", ()), "candidate.matched_terms"
        ),
        zone=optional_text("zone"),
        has_author_notes=has_author_notes,
        preservation=preservation,
        required_with=_string_tuple(obj.get("required_with", ()), "candidate.required_with"),
        parent_context_required=parent_required,
        overlap_group_id=optional_text("overlap_group_id"),
        overlap_hint=optional_text("overlap_hint"),
        index_generation=generation,
        document_hash=document_hash,
        entity_metadata=obj.get("entity"),
        from_retrieval=not dependency,
    )


def parse_search_batch(value: Mapping[str, Any]) -> SearchBatch:
    obj = _mapping(value, "SearchBatch")
    allowed = {"complete", "cursor", "inspected_count", "truncated_by_limit", "candidates"}
    extra = set(obj) - allowed
    if extra:
        raise ContractValidationError(
            f"SearchBatch has unsupported fields: {', '.join(sorted(extra))}"
        )
    if not isinstance(obj.get("complete"), bool):
        raise ContractValidationError("SearchBatch.complete must be boolean")
    inspected = _integer(obj.get("inspected_count"), "SearchBatch.inspected_count", minimum=0)
    cursor = obj.get("cursor")
    if cursor is not None:
        cursor = _string(cursor, "SearchBatch.cursor", allow_empty=True)
    truncated = obj.get("truncated_by_limit", False)
    if not isinstance(truncated, bool):
        raise ContractValidationError("SearchBatch.truncated_by_limit must be boolean")
    raw_candidates = obj.get("candidates")
    if not isinstance(raw_candidates, Sequence) or isinstance(raw_candidates, (str, bytes)):
        raise ContractValidationError("SearchBatch.candidates must be an array")
    candidates = tuple(
        parse_candidate(item, original_order=index)
        for index, item in enumerate(raw_candidates)
    )
    return SearchBatch(
        complete=obj["complete"],
        inspected_count=inspected,
        candidates=candidates,
        cursor=cursor,
        truncated_by_limit=truncated,
    )


def validate_context_pack(value: Mapping[str, Any]) -> None:
    """Validate the Context Pack envelope and all schema-critical nested records."""
    obj = _mapping(value, "ContextPack")
    required = {
        "schema_version", "status", "query", "Included", "Coverage", "Deferred",
        "Parallel Sources", "Known", "Version Changes", "Statistics", "Diagnostics",
    }
    allowed = required | {"task", "search_complete"}
    missing = required - set(obj)
    extra = set(obj) - allowed
    if missing:
        raise ContractValidationError(
            f"ContextPack is missing fields: {', '.join(sorted(missing))}"
        )
    if extra:
        raise ContractValidationError(
            f"ContextPack has unsupported fields: {', '.join(sorted(extra))}"
        )
    if obj["schema_version"] != "sfra.context_pack.v1":
        raise ContractValidationError("unsupported ContextPack schema_version")
    if obj["status"] not in {
        "complete", "partial", "empty", "budget_limited", "integrity_warning"
    }:
        raise ContractValidationError("invalid ContextPack status")
    _string(obj["query"], "ContextPack.query", allow_empty=True)
    if "task" in obj and obj["task"] is not None and not isinstance(obj["task"], str):
        raise ContractValidationError("ContextPack.task must be string or null")
    if "search_complete" in obj and not isinstance(obj["search_complete"], bool):
        raise ContractValidationError("ContextPack.search_complete must be boolean")

    array_fields = (
        "Included", "Coverage", "Deferred", "Parallel Sources",
        "Known", "Version Changes", "Diagnostics",
    )
    for key in array_fields:
        if not isinstance(obj[key], list):
            raise ContractValidationError(f"ContextPack.{key} must be an array")

    provenance_required = {
        "node_id", "source_path", "heading_path", "line_start", "line_end", "content_hash"
    }

    def validate_provenance(item: Mapping[str, Any], name: str) -> None:
        missing_fields = provenance_required - set(item)
        if missing_fields:
            raise ContractValidationError(
                f"{name} is missing provenance fields: {', '.join(sorted(missing_fields))}"
            )
        _string(item["node_id"], f"{name}.node_id")
        _string(item["source_path"], f"{name}.source_path")
        _string_tuple(item["heading_path"], f"{name}.heading_path")
        _integer(item["line_start"], f"{name}.line_start", minimum=1)
        line_end = _integer(item["line_end"], f"{name}.line_end", minimum=1)
        if line_end < item["line_start"]:
            raise ContractValidationError(f"{name}.line_end must be >= line_start")
        _hash(item["content_hash"], f"{name}.content_hash")
        if "signals" in item:
            _mapping(item["signals"], f"{name}.signals")
        if "matched_focus_ids" in item:
            _string_tuple(item["matched_focus_ids"], f"{name}.matched_focus_ids")
        if "document_hash" in item:
            _hash(item["document_hash"], f"{name}.document_hash", nullable=True)
        if "index_generation" in item and item["index_generation"] is not None:
            _integer(item["index_generation"], f"{name}.index_generation", minimum=0)

    included_required = {"raw_text", "trust_label", "inclusion_reason"}
    inclusion_reasons = {
        "retrieval_candidate", "required_dependency", "required_parent_context"
    }
    for index, raw in enumerate(obj["Included"]):
        item = _mapping(raw, f"Included[{index}]")
        validate_provenance(item, f"Included[{index}]")
        if not included_required.issubset(item):
            raise ContractValidationError(f"Included[{index}] lacks raw_text/trust_label/inclusion_reason")
        _string(item["raw_text"], f"Included[{index}].raw_text", allow_empty=True)
        if item["trust_label"] != "untrusted_source_data":
            raise ContractValidationError("Included raw_text must be marked untrusted_source_data")
        if item["inclusion_reason"] not in inclusion_reasons:
            raise ContractValidationError(f"Included[{index}] has invalid inclusion_reason")
        if "token_count" in item:
            _integer(item["token_count"], f"Included[{index}].token_count", minimum=0)
        if "is_required_dependency" in item and not isinstance(item["is_required_dependency"], bool):
            raise ContractValidationError(f"Included[{index}].is_required_dependency must be boolean")

    coverage_statuses = {"found", "deferred", "not_found_in_retrieval"}
    coverage_bases = {"adapter_match", "explicit_entities_facets_terms", "exact_phrase_fallback"}
    coverage_required = {
        "aspect_id", "label", "status", "included_node_ids",
        "known_node_ids", "deferred_node_ids", "basis",
    }
    for index, raw in enumerate(obj["Coverage"]):
        item = _mapping(raw, f"Coverage[{index}]")
        if not coverage_required.issubset(item):
            raise ContractValidationError(f"Coverage[{index}] is missing required fields")
        _string(item["aspect_id"], f"Coverage[{index}].aspect_id")
        _string(item["label"], f"Coverage[{index}].label")
        if item["status"] not in coverage_statuses:
            raise ContractValidationError(f"Coverage[{index}] has invalid status")
        for field_name in ("included_node_ids", "known_node_ids", "deferred_node_ids"):
            _string_tuple(item[field_name], f"Coverage[{index}].{field_name}")
        bases = _string_tuple(item["basis"], f"Coverage[{index}].basis")
        if any(basis not in coverage_bases for basis in bases):
            raise ContractValidationError(f"Coverage[{index}].basis has unsupported value")
        if "diagnostic_note" in item and item["diagnostic_note"] is not None and not isinstance(item["diagnostic_note"], str):
            raise ContractValidationError(f"Coverage[{index}].diagnostic_note must be string or null")

    deferred_reasons = {
        "budget_limit", "required_group_budget_limit",
        "lower_priority_budget_limit", "unresolved_required_dependency",
    }
    for index, raw in enumerate(obj["Deferred"]):
        item = _mapping(raw, f"Deferred[{index}]")
        validate_provenance(item, f"Deferred[{index}]")
        if "estimated_tokens" not in item or "reason" not in item:
            raise ContractValidationError(f"Deferred[{index}] lacks estimated_tokens/reason")
        _integer(item["estimated_tokens"], f"Deferred[{index}].estimated_tokens", minimum=0)
        if item["reason"] not in deferred_reasons:
            raise ContractValidationError("Deferred item has invalid reason")
        if "required_with" in item:
            _string_tuple(item["required_with"], f"Deferred[{index}].required_with")
        if "unresolved_dependency_ids" in item:
            _string_tuple(item["unresolved_dependency_ids"], f"Deferred[{index}].unresolved_dependency_ids")

    for index, raw in enumerate(obj["Parallel Sources"]):
        item = _mapping(raw, f"Parallel Sources[{index}]")
        if item.get("relation") not in {
            "same_basename_different_path", "adapter_overlap_group", "adapter_overlap_hint"
        } or item.get("kept_separate") is not True:
            raise ContractValidationError(f"Parallel Sources[{index}] has invalid relation/kept_separate")
        sources = item.get("sources")
        if not isinstance(sources, list) or len(sources) < 2:
            raise ContractValidationError(f"Parallel Sources[{index}].sources must contain at least two items")
        for source_index, source_raw in enumerate(sources):
            source = _mapping(source_raw, f"Parallel Sources[{index}].sources[{source_index}]")
            for field_name in ("node_id", "source_path", "content_hash"):
                _string(source.get(field_name), f"Parallel Sources[{index}].sources[{source_index}].{field_name}")
            _hash(source["content_hash"], f"Parallel Sources[{index}].sources[{source_index}].content_hash")

    for index, raw in enumerate(obj["Known"]):
        item = _mapping(raw, f"Known[{index}]")
        _string(item.get("node_id"), f"Known[{index}].node_id")
        _hash(item.get("content_hash"), f"Known[{index}].content_hash")
        if item.get("delivery") != "already_known_not_repeated":
            raise ContractValidationError(f"Known[{index}] has invalid delivery")

    for index, raw in enumerate(obj["Version Changes"]):
        item = _mapping(raw, f"Version Changes[{index}]")
        _string(item.get("node_id"), f"Version Changes[{index}].node_id")
        _hash(item.get("known_hash"), f"Version Changes[{index}].known_hash")
        _hash(item.get("current_hash"), f"Version Changes[{index}].current_hash")
        if item.get("action") != "deliver_current_version_if_budget_allows":
            raise ContractValidationError(f"Version Changes[{index}] has invalid action")

    stats = _mapping(obj["Statistics"], "Statistics")
    stats_required = {
        "retrieved_count", "included_count", "deferred_count", "known_count",
        "not_found_aspect_count", "focus_count", "coverage_available_ratio",
        "coverage_included_ratio", "budget_tokens", "tokens_used",
        "response_tokens_estimated", "token_counter", "rejected_count",
    }
    if not stats_required.issubset(stats):
        raise ContractValidationError("Statistics is missing required fields")
    for key in (
        "retrieved_count", "included_count", "deferred_count", "known_count",
        "not_found_aspect_count", "focus_count", "budget_tokens", "tokens_used",
        "response_tokens_estimated", "rejected_count",
    ):
        _integer(stats[key], f"Statistics.{key}", minimum=1 if key == "budget_tokens" else 0)
    for key in ("coverage_available_ratio", "coverage_included_ratio"):
        ratio = stats[key]
        if ratio is not None and (
            isinstance(ratio, bool) or not isinstance(ratio, (int, float))
            or not math.isfinite(float(ratio)) or not 0 <= ratio <= 1
        ):
            raise ContractValidationError(f"Statistics.{key} must be between 0 and 1 or null")
    token_counter = _mapping(stats["token_counter"], "Statistics.token_counter")
    for key in ("name", "version", "encoding"):
        _string(token_counter.get(key), f"Statistics.token_counter.{key}", allow_empty=True)
    for key in ("exact_for_encoding", "exact_for_client_model"):
        if not isinstance(token_counter.get(key), bool):
            raise ContractValidationError(f"Statistics.token_counter.{key} must be boolean")

    for index, raw in enumerate(obj["Diagnostics"]):
        item = _mapping(raw, f"Diagnostics[{index}]")
        for key in ("code", "message"):
            _string(item.get(key), f"Diagnostics[{index}].{key}", allow_empty=True)
        if item.get("severity") not in {"info", "warning", "error"}:
            raise ContractValidationError(f"Diagnostics[{index}] has invalid severity")
        if "node_ids" in item:
            _string_tuple(item["node_ids"], f"Diagnostics[{index}].node_ids")
        if "details" in item:
            _mapping(item["details"], f"Diagnostics[{index}].details")
