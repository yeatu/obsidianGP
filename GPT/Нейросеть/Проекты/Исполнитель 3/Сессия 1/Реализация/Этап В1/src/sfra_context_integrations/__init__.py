"""Integration boundary modules for the SFRA Context Builder."""

from .search_adapter import E2SearchAdapter, SearchAdapterError, SearchAdapterResult
from .snapshot import PinnedSnapshot, SnapshotBindingError, bind_pinned_snapshot
from .source_protocol import E1PublicSourceAPI, E1NodeReader, SourceReader
from .source_reader import E1SourceReader, SourceReaderContractError
from .dependency_resolver import E1DependencyResolver
from .pipeline import (
    ContextIntegrationPipeline,
    ContextIntegrationResult,
    SourceReadRequest,
)

__all__ = [
    "E1PublicSourceAPI",
    "E1NodeReader",
    "SourceReader",
    "E1SourceReader",
    "SourceReaderContractError",
    "E1DependencyResolver",
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
