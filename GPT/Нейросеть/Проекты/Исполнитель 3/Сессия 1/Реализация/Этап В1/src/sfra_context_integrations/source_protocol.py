"""Public E1 source API ports; no private SQLite implementation lives in E3."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from sfra_context_builder.models import SnapshotRef


class E1NodeReader(Protocol):
    def read_node(
        self, node_id: str, expected_hash: str, snapshot: SnapshotRef
    ) -> Mapping[str, Any]:
        """Return {'status': 'ok', 'node': {...}} or an explicit error status."""
        ...


class E1ScopeReader(E1NodeReader, Protocol):
    """Future E1 capability. Contract only until E1 implements all scopes."""

    def read_scope(
        self,
        node_id: str,
        expected_hash: str,
        scope: str,
        budget_tokens: int | None,
        snapshot: SnapshotRef,
    ) -> Mapping[str, Any]:
        """Read node/parent/neighbors/document from one pinned snapshot."""
        ...
