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
            if mode not in {"any", "all"}:
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

    optional_text = lambda key: (
        None if obj.get(key) is None else _string(obj[key], f"candidate.{key}", allow_empty=True)
    )
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
        has_author_notes=(
            obj.get("has_author_notes")
            if isinstance(obj.get("has_author_notes"), bool) or obj.get("has_author_notes") is None
            else (_ for _ in ()).throw(
                ContractValidationError("candidate.has_author_notes must be boolean or null")
            )
        ),
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
    """Validate the required Context Pack envelope and critical nested invariants."""
    obj = _mapping(value, "ContextPack")
    required = {
        "schema_version", "status", "query", "Included", "Coverage", "Deferred",
        "Parallel Sources", "Known", "Version Changes", "Statistics", "Diagnostics",
    }
    missing = required - set(obj)
    if missing:
        raise ContractValidationError(
            f"ContextPack is missing fields: {', '.join(sorted(missing))}"
        )
    if obj["schema_version"] != "sfra.context_pack.v1":
        raise ContractValidationError("unsupported ContextPack schema_version")
    if obj["status"] not in {
        "complete", "partial", "empty", "budget_limited", "integrity_warning"
    }:
        raise ContractValidationError("invalid ContextPack status")
    for key in ("Included", "Coverage", "Deferred", "Parallel Sources", "Known", "Version Changes", "Diagnostics"):
        if not isinstance(obj[key], list):
            raise ContractValidationError(f"ContextPack.{key} must be an array")
    if not isinstance(obj["Statistics"], Mapping):
        raise ContractValidationError("ContextPack.Statistics must be an object")
    for item in obj["Included"]:
        if item.get("trust_label") != "untrusted_source_data":
            raise ContractValidationError("Included raw_text must be marked untrusted_source_data")
        if "raw_text" not in item or "content_hash" not in item:
            raise ContractValidationError("Included item lacks raw_text or content_hash")
    for item in obj["Deferred"]:
        if item.get("reason") not in {
            "budget_limit", "required_group_budget_limit",
            "lower_priority_budget_limit", "unresolved_required_dependency",
        }:
            raise ContractValidationError("Deferred item has invalid reason")
