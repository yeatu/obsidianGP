"""Allowlist-only projection of V2.1 business results into safe aggregate metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from sfra_context_integrations import ContextIntegrationResult, ReadSourceResult

from .models import Operation

_SAFE_DIAGNOSTIC_CODES = frozenset({
    "retrieval_partial", "budget_limited", "budget_exceeded", "source_checked",
    "invalid_request", "stale_source", "ambiguous", "deleted", "not_found",
    "snapshot_mismatch", "document_hash_mismatch", "snapshot_generation_mismatch",
    "source_unavailable", "integrity_error", "dependency_missing",
    "dependency_unresolved", "search_incomplete", "retrieval_error",
})
_SAFE_BUSINESS_STATUSES = frozenset({
    "ok", "stale", "stale_source", "ambiguous", "deleted", "not_found",
    "invalid_request", "source_unavailable", "integrity_error", "budget_exceeded",
    "snapshot_mismatch", "complete", "partial", "empty", "error",
    "budget_limited", "failed",
})
_SCOPES = frozenset({"node", "parent", "neighbors", "document"})


class SafeProjectionError(ValueError):
    """A V2.1 application result cannot be projected safely."""


@dataclass(frozen=True, slots=True)
class SafeResultProjection:
    operation: str
    business_status: str
    scope: str | None
    counts: Mapping[str, int]
    diagnostic_codes: tuple[str, ...]

    def to_mapping(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "business_status": self.business_status,
            "scope": self.scope,
            "counts": dict(self.counts),
            "diagnostic_codes": list(self.diagnostic_codes),
        }


def _count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _sequence_length(value: object) -> int:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        return 0
    return len(value)


def _safe_status(value: object) -> str:
    return value if isinstance(value, str) and value in _SAFE_BUSINESS_STATUSES else "unknown"


def _safe_codes(*collections: object) -> tuple[str, ...]:
    result: set[str] = set()
    for collection in collections:
        if not isinstance(collection, (list, tuple)):
            continue
        for item in collection:
            code = item.get("code") if isinstance(item, Mapping) else getattr(item, "code", None)
            if isinstance(code, str) and code in _SAFE_DIAGNOSTIC_CODES:
                result.add(code)
    return tuple(sorted(result))


class SafeResultProjector:
    """Project only fixed status/count/scope fields; never serialize source objects."""

    def project(self, operation: Operation, result: object) -> SafeResultProjection:
        if operation == "search_vault":
            return self._project_search(result)
        if operation == "read_source":
            return self._project_read_source(result)
        raise SafeProjectionError("Unsupported operation")

    def _project_search(self, result: object) -> SafeResultProjection:
        if not isinstance(result, ContextIntegrationResult):
            raise SafeProjectionError("search_vault must return ContextIntegrationResult")
        pack = result.context_pack
        if not isinstance(pack, Mapping):
            raise SafeProjectionError("Context Pack must be a mapping")
        search = result.search
        batch = getattr(search, "batch", None)
        if batch is None:
            raise SafeProjectionError("Search result lacks a batch")
        candidates = getattr(batch, "candidates", ())
        included = pack.get("Included", ())
        deferred = pack.get("Deferred", ())
        coverage = pack.get("Coverage", {})
        if not isinstance(coverage, Mapping):
            coverage = {}
        counts = {
            "inspected": _count(getattr(batch, "inspected_count", 0)),
            "candidates": _sequence_length(candidates),
            "included": _sequence_length(included),
            "deferred": _sequence_length(deferred),
            "source_reads": _sequence_length(result.source_reads),
        }
        if "covered" in coverage:
            counts["covered"] = _count(coverage.get("covered"))
        if "uncovered" in coverage:
            counts["uncovered"] = _count(coverage.get("uncovered"))
        codes = _safe_codes(
            getattr(search, "diagnostics", ()),
            pack.get("Diagnostics", ()),
            tuple(
                item.get("diagnostics", ())
                for item in result.source_reads
                if isinstance(item, Mapping)
            ),
        )
        return SafeResultProjection(
            operation="search_vault",
            business_status=_safe_status(pack.get("Status")),
            scope=None,
            counts=MappingProxyType(counts),
            diagnostic_codes=codes,
        )

    def _project_read_source(self, result: object) -> SafeResultProjection:
        if not isinstance(result, ReadSourceResult):
            raise SafeProjectionError("read_source must return ReadSourceResult")
        request = result.request
        scope = getattr(request, "scope", None)
        if scope not in _SCOPES:
            raise SafeProjectionError("ReadSourceResult scope is unsupported")
        fragments = result.fragments
        counts = {"fragments": _sequence_length(fragments)}
        codes = _safe_codes(result.diagnostics)
        return SafeResultProjection(
            operation="read_source",
            business_status=_safe_status(result.status),
            scope=scope,
            counts=MappingProxyType(counts),
            diagnostic_codes=codes,
        )
