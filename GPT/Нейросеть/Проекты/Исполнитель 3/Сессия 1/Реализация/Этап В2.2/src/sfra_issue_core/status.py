"""Strict transport status schema v2 and in-memory test status store."""

from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Literal, Mapping
import uuid

from .models import TransportStatusStorePort

TransportState = Literal["REJECTED", "COMPLETED", "FAILED"]

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_OPERATIONS = frozenset({"search_vault", "read_source"})
_STATES = frozenset({"REJECTED", "COMPLETED", "FAILED"})
_SCOPES = frozenset({"node", "parent", "neighbors", "document"})
_DIAGNOSTICS = frozenset({
    "retrieval_partial", "budget_limited", "budget_exceeded", "source_checked",
    "invalid_request", "stale_source", "ambiguous", "deleted", "not_found",
    "snapshot_mismatch", "document_hash_mismatch", "snapshot_generation_mismatch",
    "source_unavailable", "integrity_error", "dependency_missing",
    "dependency_unresolved", "search_incomplete", "retrieval_error",
})
_BUSINESS_STATUSES = frozenset({
    "ok", "stale", "stale_source", "ambiguous", "deleted", "not_found",
    "invalid_request", "source_unavailable", "integrity_error", "budget_exceeded",
    "snapshot_mismatch", "complete", "partial", "empty", "error", "unknown",
    "budget_limited", "failed",
})
_ERROR_CODES = frozenset({
    "invalid_issue_record", "invalid_issue_number", "pull_request_not_allowed",
    "wrong_repository", "wrong_title_prefix", "author_not_allowed",
    "invalid_body_type", "invalid_utf8", "body_too_large", "invalid_json_envelope",
    "invalid_json", "invalid_envelope", "missing_fields", "extra_fields",
    "invalid_payload", "unsupported_protocol", "invalid_request_id",
    "unsupported_operation", "invalid_field", "request_body_changed",
    "application_service_failed", "unsafe_result_contract",
})


def _is_int(value: object, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def validate_transport_status_v2(value: object) -> Mapping[str, object]:
    """Validate the exact status-v2 wire shape and reject all extra fields."""

    required = {
        "status_schema_version", "issue_number", "request_id", "operation",
        "transport_status", "request_body_sha256", "worker_commit_sha",
        "error_code", "result",
    }
    if not isinstance(value, Mapping) or set(value.keys()) != required:
        raise ValueError("transport status v2 must contain exactly the required fields")
    version = value["status_schema_version"]
    if not isinstance(version, int) or isinstance(version, bool) or version != 2:
        raise ValueError("status_schema_version must be integer 2")
    if not _is_int(value["issue_number"], 1):
        raise ValueError("issue_number must be a positive integer")
    request_id = value["request_id"]
    if request_id is not None:
        if not isinstance(request_id, str) or not _UUID4_RE.fullmatch(request_id):
            raise ValueError("request_id must be null or a canonical UUID v4")
        if uuid.UUID(request_id).version != 4:
            raise ValueError("request_id must be UUID v4")
    operation = value["operation"]
    if operation is not None and (
        not isinstance(operation, str) or operation not in _OPERATIONS
    ):
        raise ValueError("operation must be null or an allowed operation")
    state = value["transport_status"]
    if not isinstance(state, str) or state not in _STATES:
        raise ValueError("transport_status is unsupported")
    body_hash = value["request_body_sha256"]
    if not isinstance(body_hash, str) or not _SHA256_RE.fullmatch(body_hash):
        raise ValueError("request_body_sha256 is malformed")
    worker_sha = value["worker_commit_sha"]
    if not isinstance(worker_sha, str) or not _GIT_SHA_RE.fullmatch(worker_sha):
        raise ValueError("worker_commit_sha must be a lowercase Git SHA")
    error_code = value["error_code"]
    if error_code is not None and (
        not isinstance(error_code, str) or error_code not in _ERROR_CODES
    ):
        raise ValueError("error_code is not an allowlisted operational code")

    result = value["result"]
    if result is not None:
        result_fields = {
            "operation", "business_status", "scope", "counts", "diagnostic_codes",
        }
        if not isinstance(result, Mapping) or set(result.keys()) != result_fields:
            raise ValueError("safe result must contain exactly the allowlisted fields")
        result_operation = result["operation"]
        if (
            not isinstance(result_operation, str)
            or result_operation not in _OPERATIONS
            or result_operation != operation
        ):
            raise ValueError("safe result operation must match the transport operation")
        business_status = result["business_status"]
        if (
            not isinstance(business_status, str)
            or business_status not in _BUSINESS_STATUSES
        ):
            raise ValueError("business_status is unsupported")
        scope = result["scope"]
        if scope is not None and (
            not isinstance(scope, str) or scope not in _SCOPES
        ):
            raise ValueError("scope is unsupported")
        counts = result["counts"]
        allowed_counts = {
            "inspected", "candidates", "included", "deferred",
            "covered", "uncovered", "source_reads", "fragments",
        }
        if not isinstance(counts, Mapping) or not all(
            isinstance(key, str) and key in allowed_counts for key in counts.keys()
        ):
            raise ValueError("counts contains unsupported fields")
        if any(not _is_int(count) for count in counts.values()):
            raise ValueError("counts values must be non-negative integers")
        codes = result["diagnostic_codes"]
        if not isinstance(codes, (list, tuple)) or any(
            not isinstance(code, str) or code not in _DIAGNOSTICS for code in codes
        ):
            raise ValueError("diagnostic_codes contains an unsupported value")
        if len(set(codes)) != len(codes):
            raise ValueError("diagnostic_codes must be unique")

    if state == "COMPLETED" and (error_code is not None or result is None):
        raise ValueError("COMPLETED status requires a safe result and no error")
    if state in {"REJECTED", "FAILED"} and (error_code is None or result is not None):
        raise ValueError("REJECTED and FAILED statuses require an error and no result")
    return MappingProxyType(dict(value))


@dataclass(frozen=True, slots=True)
class TransportStatusV2:
    status_schema_version: Literal[2]
    issue_number: int
    request_id: str | None
    operation: str | None
    transport_status: TransportState
    request_body_sha256: str
    worker_commit_sha: str
    error_code: str | None = None
    result: Mapping[str, object] | None = None

    def to_mapping(self) -> dict[str, object]:
        result = None
        if self.result is not None:
            result = {
                "operation": self.result["operation"],
                "business_status": self.result["business_status"],
                "scope": self.result["scope"],
                "counts": dict(self.result["counts"]),
                "diagnostic_codes": list(self.result["diagnostic_codes"]),
            }
        value: dict[str, object] = {
            "status_schema_version": self.status_schema_version,
            "issue_number": self.issue_number,
            "request_id": self.request_id,
            "operation": self.operation,
            "transport_status": self.transport_status,
            "request_body_sha256": self.request_body_sha256,
            "worker_commit_sha": self.worker_commit_sha,
            "error_code": self.error_code,
            "result": result,
        }
        validate_transport_status_v2(value)
        return value

    def __post_init__(self) -> None:
        self.to_mapping()


class InMemoryTransportStatusStore:
    """Test-only store; the first observed body hash is immutable for an Issue."""

    def __init__(self) -> None:
        self._body_hashes: dict[int, str] = {}
        self._statuses: dict[int, TransportStatusV2] = {}

    def bind_request_body_sha256(self, issue_number: int, digest: str) -> str:
        current = self._body_hashes.setdefault(issue_number, digest)
        return current

    def put_status(self, status: TransportStatusV2) -> None:
        if not isinstance(status, TransportStatusV2):
            raise TypeError("status store accepts TransportStatusV2 only")
        self._statuses[status.issue_number] = status

    def get_status(self, issue_number: int) -> TransportStatusV2 | None:
        return self._statuses.get(issue_number)

    def get_bound_body_sha256(self, issue_number: int) -> str | None:
        return self._body_hashes.get(issue_number)
