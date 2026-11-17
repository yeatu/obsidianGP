"""Typed, transport-neutral models used by the Context Builder."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class FocusAspect:
    aspect_id: str
    label: str
    entities: tuple[str, ...] = ()
    facets: tuple[str, ...] = ()
    terms: tuple[str, ...] = ()
    match_mode: str = "any"


@dataclass(frozen=True)
class KnownVersion:
    node_id: str
    content_hash: str


@dataclass(frozen=True)
class SearchRequest:
    query: str
    task: str | None
    budget_tokens: int
    entities: tuple[str, ...] = ()
    facets: tuple[str, ...] = ()
    zones: tuple[str, ...] = ()
    known: tuple[KnownVersion, ...] = ()
    focus: tuple[FocusAspect, ...] = ()


@dataclass(frozen=True)
class RetrievalCandidate:
    node_id: str
    source_path: str
    heading_path: tuple[str, ...]
    line_start: int
    line_end: int
    content_hash: str
    raw_text: str
    match_type: str
    original_order: int
    node_type: str | None = None
    parent_node_id: str | None = None
    relevance_tier: int | None = None
    relevance_bm25: float | None = None
    score: float | None = None
    score_direction: str | None = None
    match_reasons: tuple[str, ...] = ()
    unmapped_match_reasons: tuple[str, ...] = ()
    signals: Mapping[str, Any] = field(default_factory=dict)
    matched_focus_ids: tuple[str, ...] = ()
    matched_entities: tuple[str, ...] = ()
    matched_facets: tuple[str, ...] = ()
    matched_terms: tuple[str, ...] = ()
    zone: str | None = None
    has_author_notes: bool | None = None
    preservation: str = "normal"
    required_with: tuple[str, ...] = ()
    parent_context_required: bool = False
    overlap_group_id: str | None = None
    overlap_hint: str | None = None
    index_generation: int | None = None
    document_hash: str | None = None
    entity_metadata: Any = None
    from_retrieval: bool = True

    @property
    def identity(self) -> tuple[str, str]:
        return (self.node_id, self.content_hash)


@dataclass(frozen=True)
class SearchBatch:
    complete: bool
    inspected_count: int
    candidates: tuple[RetrievalCandidate, ...]
    cursor: str | None = None
    truncated_by_limit: bool = False


@dataclass(frozen=True)
class SnapshotRef:
    """Immutable identity of the Vault + sidecar snapshot used by an operation."""

    vault_commit_sha: str
    sidecar_commit_sha: str
    manifest_sha256: str

    def __post_init__(self) -> None:
        for name in ("vault_commit_sha", "sidecar_commit_sha"):
            value = getattr(self, name)
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", value):
                raise ValueError(f"{name} must be a 40-character Git SHA")
            object.__setattr__(self, name, value.lower())
        if not isinstance(self.manifest_sha256, str) or not re.fullmatch(
            r"sha256:[0-9a-fA-F]{64}", self.manifest_sha256
        ):
            raise ValueError("manifest_sha256 must be sha256:<64 hex>")
        object.__setattr__(self, "manifest_sha256", self.manifest_sha256.lower())

    @property
    def snapshot_id(self) -> str:
        return (
            f"{self.vault_commit_sha}:"
            f"{self.sidecar_commit_sha}:"
            f"{self.manifest_sha256}"
        )


class DependencyResolver(Protocol):
    def resolve_node(
        self,
        node_id: str,
        snapshot: SnapshotRef,
    ) -> Mapping[str, Any] | None:
        """Return a complete normalized candidate from the exact pinned snapshot."""
        ...


class TokenCounterProtocol(Protocol):
    def count(self, text: str) -> int:
        ...

    def metadata(self) -> Mapping[str, Any]:
        ...
