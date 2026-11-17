"""Adapt the E2 search runtime to B1 using E1 as the only raw-text source."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

from sfra_context_builder.models import (
    RetrievalCandidate,
    SearchBatch,
    SearchRequest,
)

from .snapshot import PinnedSnapshot
from .source_protocol import E1NodeReader


class SearchAdapterError(RuntimeError):
    """An E2 request failed or returned an invalid search contract."""

    def __init__(self, message: str, *, code: str = "search_adapter_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SearchAdapterResult:
    batch: SearchBatch
    diagnostics: tuple[Mapping[str, Any], ...]
    engine_status: str
    engine_result_count: int


SearchCallable = Callable[..., Mapping[str, Any]]


def _default_search(
    source_database: str | Path,
    query: str,
    *,
    entities: Sequence[str],
    limit: int,
    entity_config: str | Path | None,
) -> Mapping[str, Any]:
    try:
        from sfra_search.runtime import search_structural_database
    except ImportError as exc:
        raise SearchAdapterError(
            "E2 sfra_search package is not installed in this runtime",
            code="e2_package_unavailable",
        ) from exc
    return search_structural_database(
        source_database,
        query,
        entities=entities,
        limit=limit,
        entity_config=entity_config,
    )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SearchAdapterError(f"{name} must be an object", code="invalid_e2_response")
    return value


def _text(value: Any, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise SearchAdapterError(f"{name} must be a string", code="invalid_e2_response")
    return value


def _positive_int(value: Any, name: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise SearchAdapterError(f"{name} must be an integer >= {minimum}", code="invalid_e2_response")
    return value

def _non_negative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SearchAdapterError(f"{name} must be a non-negative integer", code="invalid_e2_response")
    return value


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise SearchAdapterError(f"{name} must be an array of strings", code="invalid_e2_response")
    return tuple(value)


def _diagnostic(
    code: str,
    severity: str,
    message: str,
    node_ids: Sequence[str] = (),
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "node_ids": list(node_ids),
        "details": dict(details or {}),
    }


class E2SearchAdapter:
    """Call E2, resolve exact text through E1, and construct the B1 SearchBatch.

    E2 excerpts are retained only as hints. Every candidate raw_text is returned
    by the E1 source-reader port for the exact E2 node_id + content_hash address.
    """

    def __init__(
        self,
        pinned_snapshot: PinnedSnapshot,
        source_reader: E1NodeReader,
        *,
        search_call: SearchCallable | None = None,
        search_limit: int = 100,
        entity_config: str | Path | None = None,
    ) -> None:
        if isinstance(search_limit, bool) or not isinstance(search_limit, int) or not 1 <= search_limit <= 500:
            raise ValueError("search_limit must be between 1 and 500")
        if not isinstance(pinned_snapshot, PinnedSnapshot):
            raise TypeError("pinned_snapshot must be a PinnedSnapshot")
        self._snapshot = pinned_snapshot
        self._source_reader = source_reader
        self._search_call = search_call or _default_search
        self._search_limit = search_limit
        self._entity_config = entity_config

    @property
    def pinned_snapshot(self) -> PinnedSnapshot:
        """Expose the immutable snapshot bound to this adapter."""
        return self._snapshot

    @property
    def source_reader(self) -> E1NodeReader:
        """Expose the E1 reader so orchestration can enforce one read boundary."""
        return self._source_reader

    def search(self, request: SearchRequest) -> SearchAdapterResult:
        if not isinstance(request, SearchRequest):
            raise TypeError("request must be a SearchRequest")

        try:
            envelope = self._search_call(
                self._snapshot.database_path,
                request.query,
                entities=request.entities,
                limit=self._search_limit,
                entity_config=self._entity_config,
            )
        except SearchAdapterError:
            raise
        except Exception as exc:
            raise SearchAdapterError(
                f"E2 search failed ({type(exc).__name__})",
                code="e2_search_failed",
            ) from exc

        envelope = _mapping(envelope, "E2 runtime response")
        search = _mapping(envelope.get("search"), "E2 runtime response.search")
        status = search.get("status")
        if status not in {"ok", "not_found_in_retrieval"}:
            raise SearchAdapterError(
                f"Unsupported E2 search status: {status!r}",
                code="invalid_e2_status",
            )

        raw_hits = search.get("results")
        if not isinstance(raw_hits, list):
            raise SearchAdapterError("E2 search.results must be an array", code="invalid_e2_response")
        if status == "not_found_in_retrieval" and raw_hits:
            raise SearchAdapterError(
                "E2 returned hits with not_found_in_retrieval status",
                code="invalid_e2_response",
            )
        if status == "ok" and not raw_hits:
            raise SearchAdapterError(
                "E2 returned an empty list with status=ok",
                code="invalid_e2_response",
            )

        diagnostics: list[Mapping[str, Any]] = []
        if request.facets:
            diagnostics.append(_diagnostic(
                "facet_match_signal_unavailable",
                "info",
                "E2 exposes no facet parameter or explicit facet-match signal; no facet match was inferred.",
                details={"requested_facets": list(request.facets)},
            ))

        candidates: list[RetrievalCandidate] = []
        source_rejections = 0
        zone_filtered = 0
        zone_requested = bool(request.zones)
        allowed_zones = set(request.zones)

        for order, raw_hit in enumerate(raw_hits):
            hit = _mapping(raw_hit, f"E2 search.results[{order}]")
            node_id = _text(hit.get("node_id"), f"results[{order}].node_id")
            expected_hash = _text(hit.get("content_hash"), f"results[{order}].content_hash")
            hit_path = _text(hit.get("source_path"), f"results[{order}].source_path")
            heading_path = _string_tuple(hit.get("heading_path"), f"results[{order}].heading_path")
            line_start = _positive_int(hit.get("line_start"), f"results[{order}].line_start")
            line_end = _non_negative_int(hit.get("line_end"), f"results[{order}].line_end")
            e2_raw_text = hit.get("raw_text")
            if e2_raw_text is not None and not isinstance(e2_raw_text, str):
                raise SearchAdapterError(
                    f"results[{order}].raw_text must be a string when present",
                    code="invalid_e2_response",
                )
            empty_source_span = (
                e2_raw_text == ""
                and line_end == line_start - 1
            )
            if line_end < line_start and not empty_source_span:
                raise SearchAdapterError(
                    f"results[{order}] has invalid source line coordinates",
                    code="invalid_e2_response",
                )
            if e2_raw_text == "" and not empty_source_span:
                raise SearchAdapterError(
                    f"results[{order}] empty raw_text requires line_end == line_start - 1",
                    code="invalid_e2_response",
                )

            relevance = _mapping(hit.get("relevance"), f"results[{order}].relevance")
            tier = _positive_int(relevance.get("tier"), f"results[{order}].relevance.tier")
            if tier > 6:
                raise SearchAdapterError("E2 relevance tier must be between 1 and 6", code="invalid_e2_response")
            bm25 = relevance.get("bm25")
            if isinstance(bm25, bool) or not isinstance(bm25, (int, float)) or not math.isfinite(float(bm25)):
                raise SearchAdapterError("E2 relevance.bm25 must be a finite number", code="invalid_e2_response")

            zone = hit_path.split("/", 1)[0]
            if zone_requested and zone not in allowed_zones:
                zone_filtered += 1
                continue

            try:
                source_response = self._source_reader.read_node(
                    node_id,
                    expected_hash,
                    self._snapshot.ref,
                )
            except Exception as exc:
                source_rejections += 1
                diagnostics.append(_diagnostic(
                    "source_reader_error",
                    "error",
                    f"E1 exact source read failed for {node_id}.",
                    [node_id],
                    {"error_type": type(exc).__name__},
                ))
                continue

            source_response = _mapping(source_response, f"E1 source response for {node_id}")
            source_status = source_response.get("status")
            if source_status != "ok":
                source_rejections += 1
                severity = "error" if source_status == "integrity_error" else "warning"
                diagnostics.append(_diagnostic(
                    f"source_{source_status or 'invalid_status'}",
                    severity,
                    f"E1 did not return the exact current source node for {node_id}.",
                    [node_id],
                    {"status": source_status},
                ))
                continue

            node = _mapping(source_response.get("node"), f"E1 source response for {node_id}.node")
            required_fields = (
                "node_id", "content_hash", "source_path", "heading_path",
                "line_start", "line_end", "node_type", "raw_text",
                "index_generation", "document_hash",
            )
            missing = [field for field in required_fields if field not in node]
            if missing:
                source_rejections += 1
                diagnostics.append(_diagnostic(
                    "source_api_contract_incomplete",
                    "error",
                    f"E1 source response for {node_id} lacks required provenance fields.",
                    [node_id],
                    {"missing_fields": missing},
                ))
                continue

            shared = {
                "node_id": node_id,
                "content_hash": expected_hash,
                "source_path": hit_path,
                "heading_path": list(heading_path),
                "line_start": line_start,
                "line_end": line_end,
            }
            mismatches = [
                key for key, expected in shared.items()
                if node.get(key) != expected
            ]
            for optional_field in ("node_type", "parent_node_id"):
                if optional_field in hit and node.get(optional_field) != hit.get(optional_field):
                    mismatches.append(optional_field)
            hit_document_hash = hit.get("document_hash")
            if hit_document_hash is not None and node.get("document_hash") != hit_document_hash:
                mismatches.append("document_hash")

            if mismatches:
                source_rejections += 1
                diagnostics.append(_diagnostic(
                    "search_source_metadata_mismatch",
                    "error",
                    f"E2 locator and E1 source record disagree for {node_id}.",
                    [node_id],
                    {"mismatched_fields": sorted(set(mismatches))},
                ))
                continue

            raw_text = node.get("raw_text")
            if not isinstance(raw_text, str):
                raise SearchAdapterError(
                    f"E1 source raw_text for {node_id} must be a string",
                    code="invalid_source_response",
                )
            import hashlib
            actual_hash = "sha256:" + hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
            if actual_hash != expected_hash:
                source_rejections += 1
                diagnostics.append(_diagnostic(
                    "source_content_hash_mismatch",
                    "error",
                    f"E1 source text failed exact UTF-8 SHA-256 validation for {node_id}.",
                    [node_id],
                    {"expected_hash": expected_hash, "actual_hash": actual_hash},
                ))
                continue

            generation = node.get("index_generation")
            if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
                raise SearchAdapterError(
                    f"E1 source index_generation for {node_id} must be a non-negative integer",
                    code="invalid_source_response",
                )
            document_hash = node.get("document_hash")
            if document_hash is not None:
                if (
                    not isinstance(document_hash, str)
                    or len(document_hash) != 71
                    or not document_hash.startswith("sha256:")
                    or any(ch not in "0123456789abcdef" for ch in document_hash[7:])
                ):
                    raise SearchAdapterError(
                        f"E1 source document_hash for {node_id} is malformed",
                        code="invalid_source_response",
                    )

            metadata = node.get("metadata") or {}
            if not isinstance(metadata, Mapping):
                raise SearchAdapterError(
                    f"E1 source metadata for {node_id} must be an object or null",
                    code="invalid_source_response",
                )
            preservation = metadata.get("preservation", "normal")
            if preservation not in {"normal", "required"}:
                raise SearchAdapterError(
                    f"E1 source preservation for {node_id} is invalid",
                    code="invalid_source_metadata",
                )
            required_with = metadata.get("required_with", ())
            if not isinstance(required_with, (list, tuple)) or any(
                not isinstance(item, str) or not item for item in required_with
            ):
                raise SearchAdapterError(
                    f"E1 source required_with for {node_id} is invalid",
                    code="invalid_source_metadata",
                )
            parent_required = metadata.get("parent_context_required", False)
            if not isinstance(parent_required, bool):
                raise SearchAdapterError(
                    f"E1 source parent_context_required for {node_id} must be boolean",
                    code="invalid_source_metadata",
                )
            dependency_defaults = {
                key: default
                for key, default in (
                    ("preservation", "normal"),
                    ("required_with", []),
                    ("parent_context_required", False),
                )
                if key not in metadata
            }
            if dependency_defaults:
                diagnostics.append(_diagnostic(
                    "dependency_policy_defaults_applied",
                    "info",
                    f"E3 applied B1 policy defaults for {node_id}; these defaults are not E1 source annotations.",
                    [node_id],
                    {
                        "defaults_applied": dependency_defaults,
                        "metadata_fields_supplied_by_e1": [
                            key for key in (
                                "preservation", "required_with", "parent_context_required"
                            ) if key in metadata
                        ],
                    },
                ))

            reasons = _string_tuple(hit.get("match_reasons", []), f"results[{order}].match_reasons")
            entities = _string_tuple(hit.get("entities", []), f"results[{order}].entities")
            aliases = _string_tuple(hit.get("matched_aliases", []), f"results[{order}].matched_aliases")
            matched_focus = _string_tuple(hit.get("matched_focus_ids", []), f"results[{order}].matched_focus_ids")
            matched_facets = _string_tuple(hit.get("matched_facets", []), f"results[{order}].matched_facets")
            matched_terms = _string_tuple(hit.get("matched_terms", []), f"results[{order}].matched_terms")

            signals: dict[str, Any] = {}
            excerpt = hit.get("excerpt")
            if isinstance(excerpt, str):
                signals["match_excerpt"] = excerpt

            candidates.append(RetrievalCandidate(
                node_id=node_id,
                source_path=hit_path,
                heading_path=heading_path,
                line_start=line_start,
                line_end=line_end,
                content_hash=expected_hash,
                raw_text=raw_text,
                match_type=_text(hit.get("match_type"), f"results[{order}].match_type"),
                original_order=order,
                node_type=str(node["node_type"]),
                parent_node_id=node.get("parent_node_id"),
                relevance_tier=tier,
                relevance_bm25=float(bm25),
                match_reasons=(),
                unmapped_match_reasons=reasons,
                signals=signals,
                matched_focus_ids=matched_focus,
                matched_entities=entities,
                matched_facets=matched_facets,
                matched_terms=matched_terms,
                zone=zone,
                has_author_notes=metadata.get("has_author_notes"),
                preservation=preservation,
                required_with=tuple(required_with),
                parent_context_required=parent_required,
                overlap_group_id=metadata.get("overlap_group_id"),
                overlap_hint=metadata.get("overlap_hint"),
                index_generation=generation,
                document_hash=document_hash,
                entity_metadata={"matched_aliases": list(aliases), "source_metadata": dict(metadata)},
                from_retrieval=True,
            ))

        if zone_requested:
            diagnostics.append(_diagnostic(
                "zone_post_filter_applied",
                "warning",
                "E2 has no zone parameter; exact first-path-segment post-filter was applied and retrieval completeness cannot be guaranteed.",
                details={
                    "requested_zones": list(request.zones),
                    "filtered_hit_count": zone_filtered,
                },
            ))

        truncated = len(raw_hits) >= self._search_limit
        complete = status == "not_found_in_retrieval" or (status == "ok" and not truncated)
        if truncated or zone_requested or source_rejections:
            complete = False

        return SearchAdapterResult(
            batch=SearchBatch(
                complete=complete,
                inspected_count=len(raw_hits),
                candidates=tuple(candidates),
                cursor=None,
                truncated_by_limit=truncated,
            ),
            diagnostics=tuple(diagnostics),
            engine_status=str(status),
            engine_result_count=len(raw_hits),
        )
