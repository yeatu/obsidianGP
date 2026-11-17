"""Deterministic focus matching and Coverage construction."""

from __future__ import annotations

import unicodedata
from pathlib import PurePosixPath
from typing import Mapping, Sequence

from .models import FocusAspect, RetrievalCandidate


def normalize_exact(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _contains_exact(needles: Sequence[str], haystacks: Sequence[str]) -> bool:
    normalized_haystacks = [normalize_exact(value) for value in haystacks if value]
    return any(
        normalize_exact(needle) in haystack
        for needle in needles
        if needle
        for haystack in normalized_haystacks
    )


def _entity_values(metadata: object) -> set[str]:
    values: set[str] = set()
    if isinstance(metadata, str):
        values.add(metadata)
    elif isinstance(metadata, Mapping):
        for key in ("name", "canonical_name", "label", "entity_name"):
            value = metadata.get(key)
            if isinstance(value, str):
                values.add(value)
        for key in ("aliases", "names"):
            raw = metadata.get(key)
            if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
                values.update(item for item in raw if isinstance(item, str))
    elif isinstance(metadata, Sequence) and not isinstance(metadata, (str, bytes)):
        for item in metadata:
            values.update(_entity_values(item))
    return values


def focus_matches(
    candidate: RetrievalCandidate,
    focus: Sequence[FocusAspect],
) -> dict[str, str]:
    """Return aspect_id -> basis for exact, auditable matching only."""
    if not candidate.from_retrieval:
        return {}

    matched: dict[str, str] = {}
    candidate_entities = {
        normalize_exact(value)
        for value in (*candidate.matched_entities, *_entity_values(candidate.entity_metadata))
    }
    candidate_facets = {normalize_exact(value) for value in candidate.matched_facets}
    source_and_text = (
        PurePosixPath(candidate.source_path).name,
        candidate.source_path,
        *candidate.heading_path,
        candidate.raw_text,
    )
    explicit_signals = candidate.signals

    for aspect in focus:
        if aspect.aspect_id in candidate.matched_focus_ids:
            matched[aspect.aspect_id] = "adapter_match"
            continue

        category_results: list[bool] = []
        if aspect.entities:
            requested = {normalize_exact(value) for value in aspect.entities}
            category_results.append(bool(requested & candidate_entities))
        if aspect.facets:
            requested = {normalize_exact(value) for value in aspect.facets}
            facet_match = bool(requested & candidate_facets) or explicit_signals.get("facet_match") is True
            category_results.append(facet_match)
        if aspect.terms:
            category_results.append(_contains_exact(aspect.terms, source_and_text))

        if category_results:
            qualifies = (
                all(category_results) if aspect.match_mode == "all"
                else any(category_results)
            )
            if qualifies:
                matched[aspect.aspect_id] = "explicit_entities_facets_terms"
            continue

        if _contains_exact((aspect.label,), source_and_text):
            matched[aspect.aspect_id] = "exact_phrase_fallback"

    return matched


def build_coverage(
    focus: Sequence[FocusAspect],
    matches: Mapping[str, Mapping[str, str]],
    included_ids: set[str],
    known_ids: set[str],
    deferred_ids: set[str],
    search_complete: bool,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for aspect in focus:
        included = sorted(
            node_id for node_id, aspect_matches in matches.items()
            if aspect.aspect_id in aspect_matches and node_id in included_ids
        )
        known = sorted(
            node_id for node_id, aspect_matches in matches.items()
            if aspect.aspect_id in aspect_matches and node_id in known_ids
        )
        deferred = sorted(
            node_id for node_id, aspect_matches in matches.items()
            if aspect.aspect_id in aspect_matches and node_id in deferred_ids
        )
        if included or known:
            status = "found"
        elif deferred:
            status = "deferred"
        else:
            status = "not_found_in_retrieval"
        bases = sorted({
            basis
            for aspect_matches in matches.values()
            if (basis := aspect_matches.get(aspect.aspect_id)) is not None
        })
        note = None
        if status == "not_found_in_retrieval" and not search_complete:
            note = (
                "Аспект не обнаружен среди обработанных результатов; SearchBatch.complete=false, "
                "поэтому это не свидетельствует об отсутствии информации в Vault."
            )
        elif status == "found" and known and not included:
            note = "Источник известен клиенту по той же паре Node ID + Content Hash; raw_text не повторялся."
        result.append({
            "aspect_id": aspect.aspect_id,
            "label": aspect.label,
            "status": status,
            "included_node_ids": included,
            "known_node_ids": known,
            "deferred_node_ids": deferred,
            "basis": bases,
            "diagnostic_note": note,
        })
    return result
