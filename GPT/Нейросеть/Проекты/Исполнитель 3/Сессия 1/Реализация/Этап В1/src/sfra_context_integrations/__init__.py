"""Integration boundary modules for the SFRA Context Builder."""

from .search_adapter import E2SearchAdapter, SearchAdapterError, SearchAdapterResult
from .snapshot import PinnedSnapshot, SnapshotBindingError, bind_pinned_snapshot
from .source_protocol import (
    E1DependencyReader,
    E1NodeReader,
    E1ScopeAPI,
    SourceReader,
)
from .source_reader import E1SourceReader, SourceReaderContractError
from .pipeline import (
    ContextIntegrationPipeline,
    ContextIntegrationResult,
    SourceReadRequest,
)

__all__ = [
    "E1DependencyReader",
    "E1NodeReader",
    "E1ScopeAPI",
    "SourceReader",
    "E1SourceReader",
    "SourceReaderContractError",
    "E2SearchAdapter",
    "SearchAdapterError",
    "SearchAdapterResult",
    "PinnedSnapshot",
    "SnapshotBindingError",
    "bind_pinned_snapshot",
    "ContextIntegrationPipeline",
    "ContextIntegrationResult",
    "SourceReadRequest",
]
