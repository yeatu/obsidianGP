"""Strict search_vault adapter over the existing SearchVaultService.

This module deliberately does not implement retrieval, source verification,
ranking, coverage, or budget policy. It validates the wire input, delegates once
to SearchVaultService, and projects the already-computed result into the accepted
local MCP envelope.
"""

from collections.abc import Mapping, Sequence
import math
from typing import Any, Callable, Literal

from typing_extensions import NotRequired, TypedDict

from sfra_context_builder.models import SnapshotRef
from sfra_context_builder.validation import (
    ContractValidationError,
    parse_search_request,
)
from sfra_context_integrations.application import ApplicationServiceError
from sfra_context_integrations.pipeline import ContextIntegrationResult


_ALLOWED_FIELDS = frozenset({
    "query",
    "task",
    "entities",
    "facets",
    "zones",
    "budget_tokens",
    "known",
    "focus",
})
_ARRAY_FIELDS = ("entities", "facets", "zones", "known", "focus")
_FOCUS_ARRAY_FIELDS = ("entities", "facets", "terms")


class KnownVersionInput(TypedDict):
    node_id: str
    content_hash: str


class FocusAspectInput(TypedDict):
    id: str
    label: str
    entities: NotRequired[list[str]]
    facets: NotRequired[list[str]]
    terms: NotRequired[list[str]]
    match_mode: NotRequired[Literal["any", "all"]]


class SearchVaultToolError(ValueError):
    """Transport-neutral search_vault failure with a stable public code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _validate_wire_shape(arguments: object) -> Mapping[str, Any]:
    if not isinstance(arguments, Mapping):
        raise SearchVaultToolError(
            "invalid_request",
            "search_vault arguments must be an object",
        )

    unknown = [
        key for key in arguments
        if not isinstance(key, str) or key not in _ALLOWED_FIELDS
    ]
    if unknown:
        raise SearchVaultToolError(
            "invalid_request",
            "search_vault contains unsupported fields",
        )

    for field in _ARRAY_FIELDS:
        if field in arguments and not isinstance(arguments[field], list):
            raise SearchVaultToolError(
                "invalid_request",
                f"{field} must be an array when supplied",
            )

    focus = arguments.get("focus", [])
    if isinstance(focus, list):
        for index, aspect in enumerate(focus):
            if not isinstance(aspect, Mapping):
                raise SearchVaultToolError(
                    "invalid_request",
                    f"focus[{index}] must be an object",
                )
            for field in _FOCUS_ARRAY_FIELDS:
                if field in aspect and not isinstance(aspect[field], list):
                    raise SearchVaultToolError(
                        "invalid_request",
                        f"focus[{index}].{field} must be an array when supplied",
                    )

    return arguments


def _json_value(value: Any, *, location: str) -> Any:
    """Copy diagnostics into JSON primitives without silently dropping fields."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SearchVaultToolError(
                "search_contract_error",
                f"{location} contains a non-finite number",
            )
        return value
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise SearchVaultToolError(
                    "search_contract_error",
                    f"{location} contains a non-string object key",
                )
            output[key] = _json_value(item, location=f"{location}.{key}")
        return output
    if isinstance(value, (list, tuple)):
        return [
            _json_value(item, location=f"{location}[{index}]")
            for index, item in enumerate(value)
        ]
    raise SearchVaultToolError(
        "search_contract_error",
        f"{location} contains a non-JSON value",
    )


def _snapshot_wire(snapshot: SnapshotRef) -> dict[str, str]:
    if not isinstance(snapshot, SnapshotRef):
        raise SearchVaultToolError(
            "search_contract_error",
            "SearchVaultService returned an invalid SnapshotRef",
        )
    return {
        "vault_commit_sha": snapshot.vault_commit_sha,
        "sidecar_commit_sha": snapshot.sidecar_commit_sha,
        "manifest_sha256": snapshot.manifest_sha256,
        "snapshot_id": snapshot.snapshot_id,
    }


def _project_result(
    result: ContextIntegrationResult,
    *,
    expected_snapshot: SnapshotRef,
) -> dict[str, Any]:
    if not isinstance(result, ContextIntegrationResult):
        raise SearchVaultToolError(
            "search_contract_error",
            "SearchVaultService returned an invalid result type",
        )
    if result.snapshot != expected_snapshot:
        raise SearchVaultToolError(
            "snapshot_mismatch",
            "SearchVaultService returned a result from another snapshot",
        )
    if not isinstance(result.context_pack, Mapping):
        raise SearchVaultToolError(
            "search_contract_error",
            "Context Pack must be an object",
        )

    search = result.search
    batch = getattr(search, "batch", None)
    if batch is None:
        raise SearchVaultToolError(
            "search_contract_error",
            "SearchAdapter result has no SearchBatch",
        )

    engine_status = getattr(search, "engine_status", None)
    if engine_status not in {"ok", "not_found_in_retrieval"}:
        raise SearchVaultToolError(
            "search_contract_error",
            "SearchAdapter returned an unsupported engine status",
        )

    engine_count = getattr(search, "engine_result_count", None)
    inspected_count = getattr(batch, "inspected_count", None)
    complete = getattr(batch, "complete", None)
    truncated = getattr(batch, "truncated_by_limit", None)
    cursor = getattr(batch, "cursor", None)

    for name, value in (
        ("engine_result_count", engine_count),
        ("inspected_count", inspected_count),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SearchVaultToolError(
                "search_contract_error",
                f"SearchAdapter returned an invalid {name}",
            )
    if not isinstance(complete, bool) or not isinstance(truncated, bool):
        raise SearchVaultToolError(
            "search_contract_error",
            "SearchBatch completeness flags must be boolean",
        )
    if cursor is not None and not isinstance(cursor, str):
        raise SearchVaultToolError(
            "search_contract_error",
            "SearchBatch cursor must be a string or null",
        )

    diagnostics = getattr(search, "diagnostics", None)
    if not isinstance(diagnostics, Sequence) or isinstance(diagnostics, (str, bytes)):
        raise SearchVaultToolError(
            "search_contract_error",
            "SearchAdapter diagnostics must be an array",
        )

    projected_diagnostics = [
        _json_value(item, location=f"search.diagnostics[{index}]")
        for index, item in enumerate(diagnostics)
    ]

    return {
        "schema_version": "sfra.search_vault.v1",
        "snapshot": _snapshot_wire(result.snapshot),
        "search": {
            "engine_status": engine_status,
            "engine_result_count": engine_count,
            "batch": {
                "complete": complete,
                "inspected_count": inspected_count,
                "truncated_by_limit": truncated,
                "cursor": cursor,
            },
            "diagnostics": projected_diagnostics,
        },
        # Preserve the B1/E3 object, including its own status, completeness,
        # Coverage, Included/Deferred, Statistics, and Diagnostics unchanged.
        "context_pack": result.context_pack,
    }


class SearchVaultTool:
    """Strict adapter over one already-composed SearchVaultService."""

    def __init__(
        self,
        search_service: object,
        snapshot: SnapshotRef,
    ) -> None:
        if not callable(getattr(search_service, "search", None)):
            raise TypeError("search_service must implement search(request)")
        if not isinstance(snapshot, SnapshotRef):
            raise TypeError("snapshot must be a SnapshotRef")
        self._search_service = search_service
        self._snapshot = snapshot

    @property
    def snapshot(self) -> SnapshotRef:
        return self._snapshot

    def handle(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Validate wire input, delegate to SearchVaultService, preserve results."""
        try:
            wire = _validate_wire_shape(arguments)
            request = parse_search_request(wire)
        except SearchVaultToolError:
            raise
        except ContractValidationError as exc:
            raise SearchVaultToolError(
                "invalid_request",
                "search_vault arguments do not match the accepted request contract",
            ) from exc

        try:
            result = self._search_service.search(request)
        except ApplicationServiceError as exc:
            # Do not copy arbitrary details/messages into protocol errors; they
            # can contain filesystem or source-derived values.
            raise SearchVaultToolError(
                exc.code,
                "SearchVaultService rejected the request",
            ) from exc
        except Exception as exc:
            raise SearchVaultToolError(
                "search_failed",
                f"SearchVaultService failed ({type(exc).__name__})",
            ) from exc

        return _project_result(result, expected_snapshot=self._snapshot)


def build_search_vault_handler(
    search_service: object,
    snapshot: SnapshotRef,
) -> Callable[..., dict[str, Any]]:
    """Build the typed callable expected by the MCP SDK tool decorator.

    Keeping this wrapper separate lets the composition/registration layer bind
    the already-created SearchVaultService and its one pinned SnapshotRef without
    duplicating validation or response projection.
    """
    tool = SearchVaultTool(search_service, snapshot)

    def search_vault(
        query: str,
        task: str | None = None,
        entities: list[str] | None = None,
        facets: list[str] | None = None,
        zones: list[str] | None = None,
        budget_tokens: int = 3000,
        known: list[KnownVersionInput] | None = None,
        focus: list[FocusAspectInput] | None = None,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {
            "query": query,
            "budget_tokens": budget_tokens,
        }
        if task is not None:
            arguments["task"] = task
        if entities is not None:
            arguments["entities"] = entities
        if facets is not None:
            arguments["facets"] = facets
        if zones is not None:
            arguments["zones"] = zones
        if known is not None:
            arguments["known"] = known
        if focus is not None:
            arguments["focus"] = focus
        return tool.handle(arguments)

    return search_vault


def handle_search_vault(
    search_service: object,
    snapshot: SnapshotRef,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """Functional adapter for direct composition/tests."""
    return SearchVaultTool(search_service, snapshot).handle(arguments)
