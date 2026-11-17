"""Orchestrate E2 retrieval, B1 Context Pack building and E1 source reads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sfra_context_builder import ContextBuilder
from sfra_context_builder.models import DependencyResolver, SearchRequest, SnapshotRef

from .dependency_resolver import E1DependencyResolver
from .search_adapter import E2SearchAdapter, SearchAdapterResult
from .snapshot import PinnedSnapshot
from .source_reader import E1SourceReader, SourceReaderContractError, SCOPES


@dataclass(frozen=True, slots=True)
class SourceReadRequest:
    node_id: str
    expected_hash: str
    scope: str
    budget_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ContextIntegrationResult:
    snapshot: SnapshotRef
    search: SearchAdapterResult
    context_pack: Mapping[str, Any]
    source_reads: tuple[Mapping[str, Any], ...]


class ContextIntegrationPipeline:
    """One immutable snapshot through search, dependency resolution and source reads."""

    def __init__(
        self,
        *,
        pinned_snapshot: PinnedSnapshot,
        search_adapter: E2SearchAdapter,
        context_builder: ContextBuilder,
        source_reader: E1SourceReader,
        dependency_resolver: DependencyResolver | None = None,
    ) -> None:
        if not isinstance(pinned_snapshot, PinnedSnapshot):
            raise TypeError("pinned_snapshot must be a PinnedSnapshot")
        if search_adapter.pinned_snapshot.ref != pinned_snapshot.ref:
            raise ValueError("SearchAdapter and pipeline use different SnapshotRef values")
        if source_reader.pinned_snapshot.ref != pinned_snapshot.ref:
            raise ValueError("SourceReader and pipeline use different SnapshotRef values")
        if search_adapter.source_reader is not source_reader:
            raise ValueError("SearchAdapter and pipeline must share the same SourceReader instance")
        self._pinned = pinned_snapshot
        self._search = search_adapter
        self._builder = context_builder
        self._source_reader = source_reader
        self._dependency_resolver = (
            dependency_resolver
            if dependency_resolver is not None
            else E1DependencyResolver(source_reader)
        )

    def run(
        self,
        request: SearchRequest,
        *,
        source_reads: Sequence[SourceReadRequest] = (),
    ) -> ContextIntegrationResult:
        if not isinstance(request, SearchRequest):
            raise TypeError("request must be a SearchRequest")

        begin_request = getattr(self._dependency_resolver, "begin_request", None)
        if callable(begin_request):
            begin_request()

        search_result = self._search.search(request)
        snapshot = self._pinned.ref
        pack = self._builder.build(
            request,
            search_result.batch,
            self._dependency_resolver,
            snapshot=snapshot,
        )

        dependency_diagnostics = getattr(self._dependency_resolver, "diagnostics", ())
        if dependency_diagnostics:
            pack["Diagnostics"].extend(dict(item) for item in dependency_diagnostics)

        read_results: list[Mapping[str, Any]] = []
        for index, read_request in enumerate(source_reads):
            if not isinstance(read_request, SourceReadRequest):
                raise TypeError(f"source_reads[{index}] must be SourceReadRequest")
            if not read_request.node_id or not read_request.expected_hash:
                raise ValueError(f"source_reads[{index}] requires node_id and expected_hash")
            if read_request.scope not in SCOPES:
                raise ValueError(f"source_reads[{index}] has unsupported scope")
            if (
                read_request.budget_tokens is not None
                and (
                    isinstance(read_request.budget_tokens, bool)
                    or not isinstance(read_request.budget_tokens, int)
                    or read_request.budget_tokens < 1
                )
            ):
                raise ValueError(f"source_reads[{index}].budget_tokens must be >= 1 or None")

            response = self._source_reader.read_scope(
                read_request.node_id,
                read_request.expected_hash,
                read_request.scope,
                snapshot,
                budget_tokens=read_request.budget_tokens,
            )
            if not isinstance(response, Mapping):
                raise SourceReaderContractError(
                    f"SourceReader result {index} must be an object"
                )
            if response.get("snapshot_id") != snapshot.snapshot_id:
                raise SourceReaderContractError(
                    f"SourceReader result {index} belongs to another snapshot",
                    code="snapshot_mismatch",
                )
            if response.get("status") != "ok" and response.get("fragments", []) != []:
                raise SourceReaderContractError(
                    f"SourceReader error result {index} contains partial fragments",
                    code="partial_error_payload",
                )
            read_results.append(response)

        return ContextIntegrationResult(
            snapshot=snapshot,
            search=search_result,
            context_pack=pack,
            source_reads=tuple(read_results),
        )
