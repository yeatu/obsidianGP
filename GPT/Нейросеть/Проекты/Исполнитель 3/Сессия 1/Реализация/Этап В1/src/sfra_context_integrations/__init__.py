"""Integration boundary modules for SFRA Context Builder."""

from .search_adapter import E2SearchAdapter, SearchAdapterError, SearchAdapterResult
from .snapshot import PinnedSnapshot, SnapshotBindingError, bind_pinned_snapshot
from .source_protocol import E1NodeReader, E1ScopeReader

__all__ = [
    "E1NodeReader", "E1ScopeReader", "E2SearchAdapter", "SearchAdapterError",
    "SearchAdapterResult", "PinnedSnapshot", "SnapshotBindingError",
    "bind_pinned_snapshot",
]
