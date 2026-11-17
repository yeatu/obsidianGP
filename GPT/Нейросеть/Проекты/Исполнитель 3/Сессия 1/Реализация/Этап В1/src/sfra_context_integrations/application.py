"""Transport-independent application services for SFRA.

No GitHub, MCP, HTTP, webhook, or persistence code belongs in this module.
It composes accepted E1/E2/E3 ports without duplicating their logic.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
import re
from typing import Literal, Protocol

from sfra_context_builder.models import SearchRequest, SnapshotRef

from .pipeline import ContextIntegrationResult, SourceReadRequest
from .source_protocol import SourceReader


SourceScope = Literal["node", "parent", "neighbors", "document"]
SourceStatus = Literal[
    "ok", "stale", "stale_source", "ambiguous", "deleted", "not_found",
    "invalid_request", "source_unavailable", "integrity_error",
    "budget_exceeded", "snapshot_mismatch",
]
FragmentRole = Literal[
    "target", "parent_context", "previous_neighbor", "next_neighbor", "document",
]
DiagnosticSeverity = Literal["info", "warning", "error"]

_ALLOWED_SCOPES = frozenset({"node", "parent", "neighbors", "document"})
_ALLOWED_STATUSES = frozenset({
    "ok", "stale", "stale_source", "ambiguous", "deleted", "not_found",
    "invalid_request", "source_unavailable", "integrity_error",
    "budget_exceeded", "snapshot_mismatch",
})
_ALLOWED_ROLES = frozenset({
    "target", "parent_context", "previous_neighbor", "next_neighbor", "document",
})
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _immutable_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))


class ApplicationServiceError(ValueError):
    """Typed application-boundary error with a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = _immutable_mapping(details or {})


class ApplicationServiceContractError(ApplicationServiceError):
    """An injected E1/E3 port returned a malformed or unsafe result."""


class ContextIntegrationPipelinePort(Protocol):
    def run(
        self,
        request: SearchRequest,
        *,
        source_reads: Sequence[SourceReadRequest] = (),
    ) -> ContextIntegrationResult:
        ...


class SearchVaultApplication(Protocol):
    def search(
        self,
        request: SearchRequest,
        *,
        source_reads: Sequence[SourceReadRequest] = (),
    ) -> ContextIntegrationResult:
        ...


@dataclass(frozen=True, slots=True)
class ReadSourceRequest:
    """Request to read one exact scope from a snapshot-pinned E1 reader."""

    node_id: str
    expected_hash: str
    scope: SourceScope
    snapshot: SnapshotRef
    budget_tokens: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not self.node_id.strip():
            raise ApplicationServiceError("invalid_node_id", "node_id must be non-empty")
        if not isinstance(self.expected_hash, str) or not _HASH_RE.fullmatch(
            self.expected_hash
        ):
            raise ApplicationServiceError(
                "invalid_content_hash",
                "expected_hash must be sha256:<64 lowercase hex>",
            )
        if not isinstance(self.scope, str) or self.scope not in _ALLOWED_SCOPES:
            raise ApplicationServiceError(
                "unsupported_scope", f"Unsupported source scope: {self.scope!r}"
            )
        if not isinstance(self.snapshot, SnapshotRef):
            raise ApplicationServiceError(
                "invalid_snapshot", "snapshot must be a SnapshotRef"
            )
        if self.budget_tokens is not None and (
            isinstance(self.budget_tokens, bool)
            or not isinstance(self.budget_tokens, int)
            or self.budget_tokens < 1
        ):
            raise ApplicationServiceError(
                "invalid_budget", "budget_tokens must be an integer >= 1 or None"
            )


@dataclass(frozen=True, slots=True)
class SourceFragment:
    """Typed view of a verified source fragment.

    Attributes preserves the full E3 record, including additive provenance fields.
    Raw text is only returned by this application call and is not serialized here.
    """

    role: FragmentRole
    node_id: str
    source_path: str
    content_hash: str
    raw_text: str
    index_generation: int
    document_hash: str | None = None
    attributes: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ServiceDiagnostic:
    code: str
    severity: DiagnosticSeverity
    message: str
    node_ids: tuple[str, ...] = ()
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TokenAccounting:
    budget_owner: Literal["E3"]
    tokens_used: int
    budget_tokens: int | None
    tokenizer: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ServiceError:
    code: str
    message: str
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReadSourceResult:
    """Typed business result; non-ok outcomes never contain partial fragments."""

    request: ReadSourceRequest
    status: SourceStatus
    fragments: tuple[SourceFragment, ...] = ()
    diagnostics: tuple[ServiceDiagnostic, ...] = ()
    token_accounting: TokenAccounting | None = None
    error: ServiceError | None = None

    @property
    def snapshot(self) -> SnapshotRef:
        return self.request.snapshot

    @property
    def snapshot_id(self) -> str:
        return self.request.snapshot.snapshot_id


class ReadSourceApplication(Protocol):
    def read(self, request: ReadSourceRequest) -> ReadSourceResult:
        ...


class SearchVaultService:
    """Thin application facade over the existing ContextIntegrationPipeline.

    Returns the original ContextIntegrationResult unchanged so diagnostics,
    coverage, Included/Deferred nodes, token accounting and budget status survive.
    """

    def __init__(self, pipeline: ContextIntegrationPipelinePort) -> None:
        if not callable(getattr(pipeline, "run", None)):
            raise TypeError("pipeline must implement a run(request, source_reads=...) method")
        self._pipeline = pipeline

    def search(
        self,
        request: SearchRequest,
        *,
        source_reads: Sequence[SourceReadRequest] = (),
    ) -> ContextIntegrationResult:
        if not isinstance(request, SearchRequest):
            raise ApplicationServiceError(
                "invalid_search_request", "request must be an existing B1 SearchRequest"
            )
        if isinstance(source_reads, (str, bytes)) or not isinstance(
            source_reads, Sequence
        ):
            raise ApplicationServiceError(
                "invalid_source_reads",
                "source_reads must be a sequence of E3 SourceReadRequest values",
            )
        typed_reads = tuple(source_reads)
        for index, item in enumerate(typed_reads):
            if not isinstance(item, SourceReadRequest):
                raise ApplicationServiceError(
                    "invalid_source_read",
                    f"source_reads[{index}] must be an E3 SourceReadRequest",
                    details={"index": index},
                )

        result = self._pipeline.run(request, source_reads=typed_reads)
        if not isinstance(result, ContextIntegrationResult):
            raise ApplicationServiceContractError(
                "invalid_pipeline_result",
                "Pipeline must return ContextIntegrationResult",
            )
        if not isinstance(result.snapshot, SnapshotRef):
            raise ApplicationServiceContractError(
                "invalid_pipeline_snapshot",
                "ContextIntegrationResult.snapshot must be a SnapshotRef",
            )
        return result


class ReadSourceService:
    """Typed application facade over one already-pinned E3 SourceReader.

    E3SourceReader retains responsibility for E1 access, provenance validation,
    and token counting. This service does not open SQLite or truncate text.
    """

    def __init__(self, source_reader: SourceReader) -> None:
        if not callable(getattr(source_reader, "read_scope", None)):
            raise TypeError("source_reader must implement read_scope")
        pinned = getattr(source_reader, "pinned_snapshot", None)
        pinned_ref = getattr(pinned, "ref", None)
        if not isinstance(pinned_ref, SnapshotRef):
            raise TypeError("source_reader must expose a PinnedSnapshot with a SnapshotRef")
        self._source_reader = source_reader
        self._pinned_snapshot = pinned_ref

    @property
    def pinned_snapshot(self) -> SnapshotRef:
        return self._pinned_snapshot

    def read(self, request: ReadSourceRequest) -> ReadSourceResult:
        if not isinstance(request, ReadSourceRequest):
            raise ApplicationServiceError(
                "invalid_read_request", "request must be a ReadSourceRequest"
            )
        if request.snapshot != self._pinned_snapshot:
            raise ApplicationServiceError(
                "snapshot_mismatch",
                "Requested SnapshotRef differs from the reader's pinned snapshot",
                details={
                    "requested_snapshot_id": request.snapshot.snapshot_id,
                    "pinned_snapshot_id": self._pinned_snapshot.snapshot_id,
                },
            )

        raw = self._source_reader.read_scope(
            request.node_id,
            request.expected_hash,
            request.scope,
            request.snapshot,
            budget_tokens=request.budget_tokens,
        )
        if not isinstance(raw, Mapping):
            raise ApplicationServiceContractError(
                "invalid_source_result", "SourceReader result must be a mapping"
            )
        if raw.get("snapshot_id") != request.snapshot.snapshot_id:
            raise ApplicationServiceContractError(
                "snapshot_mismatch",
                "SourceReader result does not echo the requested SnapshotRef",
                details={
                    "expected_snapshot_id": request.snapshot.snapshot_id,
                    "actual_snapshot_id": raw.get("snapshot_id"),
                },
            )

        if raw.get("scope") != request.scope:
            raise ApplicationServiceContractError(
                "scope_mismatch",
                "SourceReader result does not match the requested scope",
                details={
                    "expected_scope": request.scope,
                    "actual_scope": raw.get("scope"),
                },
            )

        raw_status = raw.get("status")
        if not isinstance(raw_status, str) or raw_status not in _ALLOWED_STATUSES:
            raise ApplicationServiceContractError(
                "invalid_source_status",
                f"SourceReader returned an unsupported status: {raw_status!r}",
            )
        status: SourceStatus = raw_status
        raw_fragments = raw.get("fragments", [])
        if not isinstance(raw_fragments, (list, tuple)):
            raise ApplicationServiceContractError(
                "invalid_source_fragments", "SourceReader fragments must be an array"
            )

        diagnostics = self._parse_diagnostics(raw.get("diagnostics", ()))
        accounting = self._parse_token_accounting(raw.get("token_accounting"))

        if status != "ok":
            if raw_fragments:
                raise ApplicationServiceContractError(
                    "partial_error_payload",
                    "A non-ok source result must not contain partial fragments",
                )
            return ReadSourceResult(
                request=request,
                status=status,
                diagnostics=diagnostics,
                token_accounting=accounting,
                error=self._parse_error(raw.get("error"), status),
            )

        if not raw_fragments:
            raise ApplicationServiceContractError(
                "empty_success_payload",
                "An ok source result must contain at least one verified fragment",
            )
        fragments = tuple(
            self._parse_fragment(item, index)
            for index, item in enumerate(raw_fragments)
        )
        return ReadSourceResult(
            request=request,
            status="ok",
            fragments=fragments,
            diagnostics=diagnostics,
            token_accounting=accounting,
        )

    @staticmethod
    def _parse_fragment(value: object, index: int) -> SourceFragment:
        if not isinstance(value, Mapping):
            raise ApplicationServiceContractError(
                "invalid_source_fragment", f"fragments[{index}] must be an object"
            )
        role = value.get("role")
        if not isinstance(role, str) or role not in _ALLOWED_ROLES:
            raise ApplicationServiceContractError(
                "invalid_fragment_role", f"fragments[{index}].role is invalid"
            )
        node_id = value.get("node_id")
        source_path = value.get("source_path")
        content_hash = value.get("content_hash")
        raw_text = value.get("raw_text")
        generation = value.get("index_generation")
        document_hash = value.get("document_hash")

        if not isinstance(node_id, str) or not node_id.strip():
            raise ApplicationServiceContractError(
                "invalid_fragment_node_id", f"fragments[{index}].node_id is invalid"
            )
        if not isinstance(source_path, str) or not source_path.strip():
            raise ApplicationServiceContractError(
                "invalid_fragment_source_path", f"fragments[{index}].source_path is invalid"
            )
        if not isinstance(content_hash, str) or not _HASH_RE.fullmatch(content_hash):
            raise ApplicationServiceContractError(
                "invalid_fragment_content_hash",
                f"fragments[{index}].content_hash is malformed",
            )
        if not isinstance(raw_text, str):
            raise ApplicationServiceContractError(
                "invalid_fragment_text", f"fragments[{index}].raw_text must be a string"
            )
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
            raise ApplicationServiceContractError(
                "invalid_fragment_generation",
                f"fragments[{index}].index_generation must be >= 0",
            )
        if document_hash is not None and (
            not isinstance(document_hash, str) or not _HASH_RE.fullmatch(document_hash)
        ):
            raise ApplicationServiceContractError(
                "invalid_fragment_document_hash",
                f"fragments[{index}].document_hash is malformed",
            )

        return SourceFragment(
            role=role,
            node_id=node_id,
            source_path=source_path,
            content_hash=content_hash,
            raw_text=raw_text,
            index_generation=generation,
            document_hash=document_hash,
            attributes=_immutable_mapping(value),
        )

    @staticmethod
    def _parse_diagnostics(value: object) -> tuple[ServiceDiagnostic, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ApplicationServiceContractError(
                "invalid_diagnostics", "SourceReader diagnostics must be an array"
            )
        result: list[ServiceDiagnostic] = []
        for index, item in enumerate(value):
            if not isinstance(item, Mapping):
                raise ApplicationServiceContractError(
                    "invalid_diagnostic", f"diagnostics[{index}] must be an object"
                )
            code, severity, message = (
                item.get("code"), item.get("severity"), item.get("message")
            )
            if not isinstance(code, str) or not code:
                raise ApplicationServiceContractError(
                    "invalid_diagnostic_code", f"diagnostics[{index}].code is invalid"
                )
            if severity not in {"info", "warning", "error"}:
                raise ApplicationServiceContractError(
                    "invalid_diagnostic_severity",
                    f"diagnostics[{index}].severity is invalid",
                )
            if not isinstance(message, str):
                raise ApplicationServiceContractError(
                    "invalid_diagnostic_message",
                    f"diagnostics[{index}].message is invalid",
                )
            node_ids = item.get("node_ids", ())
            details = item.get("details", {})
            if not isinstance(node_ids, (list, tuple)) or any(
                not isinstance(node_id, str) for node_id in node_ids
            ):
                raise ApplicationServiceContractError(
                    "invalid_diagnostic_node_ids",
                    f"diagnostics[{index}].node_ids is invalid",
                )
            if not isinstance(details, Mapping):
                raise ApplicationServiceContractError(
                    "invalid_diagnostic_details",
                    f"diagnostics[{index}].details must be an object",
                )
            result.append(ServiceDiagnostic(
                code=code,
                severity=severity,
                message=message,
                node_ids=tuple(node_ids),
                details=_immutable_mapping(details),
            ))
        return tuple(result)

    @staticmethod
    def _parse_token_accounting(value: object) -> TokenAccounting | None:
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise ApplicationServiceContractError(
                "invalid_token_accounting", "token_accounting must be an object"
            )
        owner = value.get("budget_owner")
        used = value.get("tokens_used")
        budget = value.get("budget_tokens")
        tokenizer = value.get("tokenizer", {})
        if owner != "E3":
            raise ApplicationServiceContractError(
                "invalid_budget_owner", "Token budget must remain owned by E3"
            )
        if isinstance(used, bool) or not isinstance(used, int) or used < 0:
            raise ApplicationServiceContractError(
                "invalid_tokens_used", "tokens_used must be a non-negative integer"
            )
        if budget is not None and (
            isinstance(budget, bool) or not isinstance(budget, int) or budget < 1
        ):
            raise ApplicationServiceContractError(
                "invalid_budget_tokens", "budget_tokens must be >= 1 or None"
            )
        if not isinstance(tokenizer, Mapping):
            raise ApplicationServiceContractError(
                "invalid_tokenizer_metadata", "tokenizer metadata must be an object"
            )
        return TokenAccounting(
            budget_owner="E3",
            tokens_used=used,
            budget_tokens=budget,
            tokenizer=_immutable_mapping(tokenizer),
        )

    @staticmethod
    def _parse_error(value: object, status: SourceStatus) -> ServiceError:
        if isinstance(value, Mapping):
            code = value.get("code")
            message = value.get("message")
            details = value.get("details", {})
            if not isinstance(code, str) or not code:
                code = status
            if not isinstance(message, str) or not message:
                message = status
            if not isinstance(details, Mapping):
                details = {}
            return ServiceError(
                code=code,
                message=message,
                details=_immutable_mapping(details),
            )
        if isinstance(value, str) and value:
            return ServiceError(code=status, message=value)
        return ServiceError(
            code=status,
            message=f"Source read completed with status={status}",
        )
