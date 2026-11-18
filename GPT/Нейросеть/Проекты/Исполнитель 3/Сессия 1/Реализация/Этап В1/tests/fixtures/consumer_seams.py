"""Explicit test-only constructors for exercising consumers with synthetic snapshots.

Production constructors intentionally reject the _FixturePinnedSnapshot subclass.
These helpers bypass only that constructor gate inside the test tree; they are
never imported by production packages and cannot make a fixture acceptable to
production composition.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

from sfra_context_integrations.dependency_resolver import E1DependencyResolver
from sfra_context_integrations.pipeline import ContextIntegrationPipeline
from sfra_context_integrations.search_adapter import E2SearchAdapter
from sfra_context_integrations.source_reader import E1SourceReader


def make_test_source_reader(source_api: object, pinned_snapshot: object, token_counter: object):
    reader = object.__new__(E1SourceReader)
    reader._source_api = source_api
    reader._pinned = pinned_snapshot
    reader._token_counter = token_counter
    reader._verify_pinned_snapshot()
    return reader


def make_test_search_adapter(pinned_snapshot: object, source_reader: object, *,
                             search_call: object = None, search_limit: int = 100,
                             entity_config: str | Path | None = None):
    if isinstance(search_limit, bool) or not isinstance(search_limit, int) or not 1 <= search_limit <= 500:
        raise ValueError("search_limit must be between 1 and 500")
    adapter = object.__new__(E2SearchAdapter)
    adapter._snapshot = pinned_snapshot
    adapter._source_reader = source_reader
    adapter._search_call = search_call or None
    if adapter._search_call is None:
        from sfra_context_integrations.search_adapter import _default_search
        adapter._search_call = _default_search
    adapter._search_limit = search_limit
    adapter._entity_config = entity_config
    adapter._verify_pinned_snapshot()
    return adapter


def make_test_pipeline(*, pinned_snapshot: object, search_adapter: object,
                       context_builder: object, source_reader: object,
                       dependency_resolver: object = None):
    if search_adapter.pinned_snapshot.ref != pinned_snapshot.ref:
        raise ValueError("SearchAdapter and pipeline use different SnapshotRef values")
    if source_reader.pinned_snapshot.ref != pinned_snapshot.ref:
        raise ValueError("SourceReader and pipeline use different SnapshotRef values")
    if search_adapter.source_reader is not source_reader:
        raise ValueError("SearchAdapter and pipeline must share the same SourceReader instance")
    pipeline = object.__new__(ContextIntegrationPipeline)
    pipeline._pinned = pinned_snapshot
    pipeline._search = search_adapter
    pipeline._builder = context_builder
    pipeline._source_reader = source_reader
    pipeline._dependency_resolver = (
        dependency_resolver if dependency_resolver is not None
        else E1DependencyResolver(source_reader)
    )
    return pipeline
