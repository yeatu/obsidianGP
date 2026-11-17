"""Public ports for E1 source reads and E3 scope reads."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from sfra_context_builder.models import SnapshotRef


class E1NodeReader(Protocol):
    """Exact E1 node lookup used by the E2 SearchAdapter."""

    def read_node(
        self,
        node_id: str,
        expected_hash: str,
        snapshot: SnapshotRef,
    ) -> Mapping[str, Any]:
        """Return an exact node envelope or an explicit non-ok status."""
        ...


class E1ScopeAPI(Protocol):
    """Proposed public E1 operation for all four source scopes.

    Implementations must read from the immutable checkout bound by snapshot.
    The response echoes snapshot.snapshot_id so the caller can detect accidental
    routing to another checkout. No E3 code may query E1 SQLite tables itself.
    """

    def read_scope(
        self,
        node_id: str,
        expected_hash: str,
        scope: str,
        budget_tokens: int | None,
        snapshot: SnapshotRef,
    ) -> Mapping[str, Any]:
        """Return a source-scope response with exact original fragments."""
        ...


class SourceReader(Protocol):
    """Transport-independent E3 reader contract."""

    def read_scope(
        self,
        node_id: str,
        expected_hash: str,
        scope: str,
        snapshot: SnapshotRef,
        *,
        budget_tokens: int | None = None,
    ) -> Mapping[str, Any]:
        """Read one of node/parent/neighbors/document from a pinned snapshot."""
        ...


class E1DependencyReader(Protocol):
    """Future E1 current-node resolver required by B1 dependencies.

    A dependency edge contains only Node ID. E1 must resolve the current exact
    version inside the same pinned snapshot and return its Content Hash. The
    caller then obtains/verifies original text through read_node. This operation
    must not silently select a similar or historical node.
    """

    def resolve_current_node(
        self,
        node_id: str,
        snapshot: SnapshotRef,
    ) -> Mapping[str, Any]:
        """Return current locator metadata including the producer-issued hash."""
        ...
