"""Budget accounting for the atomic Included + Coverage context payload."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from .models import RetrievalCandidate, TokenCounterProtocol


def compact_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False
    )


def provenance(candidate: RetrievalCandidate) -> dict[str, Any]:
    return {
        "node_id": candidate.node_id,
        "source_path": candidate.source_path,
        "heading_path": list(candidate.heading_path),
        "line_start": candidate.line_start,
        "line_end": candidate.line_end,
        "content_hash": candidate.content_hash,
        "zone": candidate.zone,
        "has_author_notes": candidate.has_author_notes,
        "score": candidate.score,
        "match_type": candidate.match_type,
        "signals": dict(candidate.signals),
        "matched_focus_ids": list(candidate.matched_focus_ids),
        "index_generation": candidate.index_generation,
        "document_hash": candidate.document_hash,
    }


def make_included_entry(
    candidate: RetrievalCandidate,
    *,
    token_counter: TokenCounterProtocol,
    inclusion_reason: str,
    is_required_dependency: bool,
) -> dict[str, Any]:
    entry = provenance(candidate)
    entry.update({
        "raw_text": candidate.raw_text,
        "trust_label": "untrusted_source_data",
        "token_count": token_counter.count(candidate.raw_text),
        "inclusion_reason": inclusion_reason,
        "is_required_dependency": is_required_dependency,
    })
    return entry


def context_tokens(
    included: Sequence[Mapping[str, Any]],
    coverage: Sequence[Mapping[str, Any]],
    token_counter: TokenCounterProtocol,
) -> int:
    payload = {"Included": list(included), "Coverage": list(coverage)}
    return token_counter.count(compact_json(payload))


def make_deferred_entry(
    candidate: RetrievalCandidate,
    *,
    estimated_tokens: int,
    reason: str,
    required_group_id: str,
    unresolved_dependency_ids: Sequence[str] = (),
) -> dict[str, Any]:
    entry = provenance(candidate)
    entry.update({
        "estimated_tokens": estimated_tokens,
        "reason": reason,
        "preservation": candidate.preservation,
        "required_with": list(candidate.required_with),
        "unresolved_dependency_ids": list(unresolved_dependency_ids),
        "required_group_id": required_group_id,
    })
    return entry
