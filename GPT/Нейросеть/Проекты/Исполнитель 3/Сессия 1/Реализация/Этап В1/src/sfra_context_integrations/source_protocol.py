"""Exact public E1 API contracts consumed by E3.

These signatures deliberately mirror the agreed E1 boundary. E3 never opens
E1 SQLite tables or derives structural relationships from Markdown.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from sfra_context_builder.models import SnapshotRef


class E1PublicSourceAPI(Protocol):
    def read_source_scope(
        self,
        db_path: str,
        vault_root: str,
        node_id: str,
        expected_hash: str,
        *,
        scope: str,
        snapshot_id: str,
    ) -> Mapping[str, Any]:
        """Read one verified node/parent/neighbors/document scope."""
        ...

    def resolve_current_node(
        self,
        db_path: str,
        node_id: str,
        *,
        snapshot_id: str,
    ) -> Mapping[str, Any]:
        """Resolve the current exact node address, without returning source text."""
        ...


class E1NodeReader(Protocol):
    """Node-reader shape consumed by SearchAdapter."""

    def read_node(
        self,
        node_id: str,
        expected_hash: str,
        snapshot: SnapshotRef,
    ) -> Mapping[str, Any]:
        ...


class SourceReader(Protocol):
    """Transport-independent E3 source reader."""

    @property
    def pinned_snapshot(self):
        ...

    def read_scope(
        self,
        node_id: str,
        expected_hash: str,
        scope: str,
        snapshot: SnapshotRef,
        *,
        budget_tokens: int | None = None,
    ) -> Mapping[str, Any]:
        ...

    def read_node(
        self,
        node_id: str,
        expected_hash: str,
        snapshot: SnapshotRef,
    ) -> Mapping[str, Any]:
        ...


class DependencyResolver(Protocol):
    def resolve_node(
        self,
        node_id: str,
        snapshot: SnapshotRef,
    ) -> Mapping[str, Any] | None:
        ...
