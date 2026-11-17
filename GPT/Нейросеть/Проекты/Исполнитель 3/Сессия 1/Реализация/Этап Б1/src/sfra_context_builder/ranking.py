"""Stable, deterministic ordering for retrieval candidates."""

from __future__ import annotations

from .models import RetrievalCandidate


def rank_key(candidate: RetrievalCandidate) -> tuple[float | int, ...]:
    """E2 tier/BM25 are authoritative; fallback scores need explicit direction."""
    if candidate.relevance_tier is not None:
        return (
            0,
            candidate.relevance_tier,
            candidate.relevance_bm25 if candidate.relevance_bm25 is not None else float("inf"),
            candidate.original_order,
            candidate.node_id,
        )

    signals = candidate.signals
    signal_tiers = (
        ("entity_exact", 1),
        ("document_name_match", 2),
        ("heading_match", 3),
        ("path_or_heading_name", 3),
        ("exact_terms", 4),
        ("morphology", 5),
        ("facet_match", 6),
    )
    signal_tier = next(
        (tier for name, tier in signal_tiers if signals.get(name) is True),
        7,
    )
    score_key: float = 0.0
    if candidate.score is not None:
        score_key = (
            candidate.score
            if candidate.score_direction == "asc"
            else -candidate.score
        )
    return (1, signal_tier, score_key, candidate.original_order, candidate.node_id)
