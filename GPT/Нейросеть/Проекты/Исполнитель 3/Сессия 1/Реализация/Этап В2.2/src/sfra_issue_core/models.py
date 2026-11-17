"""Transport-neutral contracts for the non-production SFRA Issue core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Mapping, Protocol

if TYPE_CHECKING:
    from .status import TransportStatusV2

Operation = Literal["search_vault", "read_source"]


@dataclass(frozen=True, slots=True)
class IssueRecord:
    """Minimal Issue snapshot returned by an injected, non-network port."""

    number: int
    title: str
    repository_full_name: str
    author_login: str
    body: str | bytes | None
    is_pull_request: bool = False


@dataclass(frozen=True, slots=True)
class BodyMaterial:
    """Exact body bytes and digest before UTF-8 or size validation."""

    raw_bytes: bytes
    request_body_sha256: str


@dataclass(frozen=True, slots=True)
class ParsedIssueRequest:
    issue_number: int
    request_id: str
    operation: Operation
    payload: Mapping[str, object]
    request_body_sha256: str


class IssueRequestError(ValueError):
    """Permanent, safe-to-project request validation failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        request_body_sha256: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.request_body_sha256 = request_body_sha256


class IssueWorkerError(RuntimeError):
    """Internal worker invocation or injected-port contract failure."""


class IssueReaderPort(Protocol):
    def read_issue(self, issue_number: int) -> IssueRecord:
        """Return one Issue snapshot; implementations must be injected."""
        ...


class TransportStatusStorePort(Protocol):
    def bind_request_body_sha256(self, issue_number: int, digest: str) -> str:
        """Atomically bind the first body digest and return the immutable baseline."""
        ...

    def put_status(self, status: TransportStatusV2) -> None:
        """Store a typed, source-content-free transport status."""
        ...
