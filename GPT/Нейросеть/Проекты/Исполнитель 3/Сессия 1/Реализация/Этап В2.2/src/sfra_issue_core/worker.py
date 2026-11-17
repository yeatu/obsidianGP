"""Non-production worker core over injected Issue, status and V2.1 service ports."""

from __future__ import annotations

import re
from types import MappingProxyType

from sfra_context_builder.models import FocusAspect, KnownVersion, SearchRequest, SnapshotRef
from sfra_context_integrations import ReadSourceRequest

from .models import (
    IssueReaderPort,
    IssueRecord,
    IssueRequestError,
    IssueWorkerError,
    ParsedIssueRequest,
    TransportStatusStorePort,
)
from .parser import IssueRequestParser
from .projector import SafeProjectionError, SafeResultProjector
from .status import TransportStatusV2

_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class IssueWorkerCore:
    """Validate first, invoke exactly one V2.1 service, and store safe status only."""

    def __init__(
        self,
        *,
        issue_reader: IssueReaderPort,
        status_store: TransportStatusStorePort,
        search_application: object,
        read_source_application: object,
        parser: IssueRequestParser | None = None,
        projector: SafeResultProjector | None = None,
    ) -> None:
        if not callable(getattr(issue_reader, "read_issue", None)):
            raise TypeError("issue_reader must implement read_issue")
        if not callable(getattr(status_store, "bind_request_body_sha256", None)):
            raise TypeError("status_store must implement bind_request_body_sha256")
        if not callable(getattr(status_store, "put_status", None)):
            raise TypeError("status_store must implement put_status")
        if not callable(getattr(search_application, "search", None)):
            raise TypeError("search_application must implement search")
        if not callable(getattr(read_source_application, "read", None)):
            raise TypeError("read_source_application must implement read")
        self._issue_reader = issue_reader
        self._status_store = status_store
        self._search = search_application
        self._read_source = read_source_application
        self._parser = parser or IssueRequestParser()
        self._projector = projector or SafeResultProjector()

    def run(
        self,
        issue_number: int,
        *,
        snapshot: SnapshotRef,
        worker_commit_sha: str,
    ) -> TransportStatusV2:
        if isinstance(issue_number, bool) or not isinstance(issue_number, int) or issue_number < 1:
            raise IssueWorkerError("issue_number must be a positive integer")
        if not isinstance(snapshot, SnapshotRef):
            raise IssueWorkerError("a single pinned SnapshotRef must be supplied")
        if not isinstance(worker_commit_sha, str) or not _GIT_SHA_RE.fullmatch(worker_commit_sha):
            raise IssueWorkerError("worker_commit_sha must be a lowercase 40-character Git SHA")

        issue = self._issue_reader.read_issue(issue_number)
        if not isinstance(issue, IssueRecord) or issue.number != issue_number:
            raise IssueWorkerError("IssueReaderPort returned an invalid or mismatched IssueRecord")

        try:
            material = self._parser.body_material(issue.body)
        except IssueRequestError as exc:
            # No exact byte sequence exists for an invalid body value, so no
            # transport status with a fabricated body digest can be persisted.
            raise IssueWorkerError("Issue body cannot be represented as exact UTF-8 bytes") from exc

        try:
            self._parser.validate_issue_metadata(issue)
        except IssueRequestError as exc:
            return self._store_status(self._rejected(
                issue_number=issue_number,
                body_hash=material.request_body_sha256,
                worker_sha=worker_commit_sha,
                error_code=exc.code,
            ))

        baseline = self._status_store.bind_request_body_sha256(
            issue_number, material.request_body_sha256
        )
        if baseline != material.request_body_sha256:
            return self._store_status(self._rejected(
                issue_number=issue_number,
                body_hash=material.request_body_sha256,
                worker_sha=worker_commit_sha,
                error_code="request_body_changed",
            ))

        try:
            request = self._parser.parse_material(issue, material)
        except IssueRequestError as exc:
            return self._store_status(self._rejected(
                issue_number=issue_number,
                body_hash=material.request_body_sha256,
                worker_sha=worker_commit_sha,
                error_code=exc.code,
            ))

        try:
            business_result = self._invoke(request, snapshot)
            safe_result = self._projector.project(request.operation, business_result)
            status = TransportStatusV2(
                status_schema_version=2,
                issue_number=issue_number,
                request_id=request.request_id,
                operation=request.operation,
                transport_status="COMPLETED",
                request_body_sha256=request.request_body_sha256,
                worker_commit_sha=worker_commit_sha,
                result=MappingProxyType(safe_result.to_mapping()),
            )
        except SafeProjectionError:
            status = self._failed(
                request=request,
                worker_sha=worker_commit_sha,
                error_code="unsafe_result_contract",
            )
        except Exception:
            # Do not copy exception text/details: injected services may include
            # source text or other untrusted values in their messages.
            status = self._failed(
                request=request,
                worker_sha=worker_commit_sha,
                error_code="application_service_failed",
            )
        return self._store_status(status)

    def _invoke(self, request: ParsedIssueRequest, snapshot: SnapshotRef) -> object:
        payload = request.payload
        if request.operation == "search_vault":
            known = tuple(
                KnownVersion(node_id=item["node_id"], content_hash=item["content_hash"])
                for item in payload.get("known", ())
            )
            focus: list[FocusAspect] = []
            for item in payload.get("focus", ()):
                if isinstance(item, str):
                    focus.append(FocusAspect(aspect_id=item, label=item))
                else:
                    focus.append(FocusAspect(
                        aspect_id=item["id"],
                        label=item["label"],
                        entities=tuple(item.get("entities", ())),
                        facets=tuple(item.get("facets", ())),
                        terms=tuple(item.get("terms", ())),
                        match_mode=item.get("match_mode", "any"),
                    ))
            search_request = SearchRequest(
                query=payload["query"],
                task=payload.get("task"),
                budget_tokens=payload.get("budget_tokens", 3000),
                entities=tuple(payload.get("entities", ())),
                facets=tuple(payload.get("facets", ())),
                zones=tuple(payload.get("zones", ())),
                known=known,
                focus=tuple(focus),
            )
            result = self._search.search(search_request)
            if getattr(result, "snapshot", None) != snapshot:
                raise IssueWorkerError("Search application returned a different SnapshotRef")
            return result

        read_request = ReadSourceRequest(
            node_id=payload["node_id"],
            expected_hash=payload["expected_hash"],
            scope=payload["scope"],
            snapshot=snapshot,
            budget_tokens=payload.get("budget_tokens"),
        )
        result = self._read_source.read(read_request)
        if getattr(getattr(result, "request", None), "snapshot", None) != snapshot:
            raise IssueWorkerError("ReadSource application returned a different SnapshotRef")
        return result

    @staticmethod
    def _rejected(
        *,
        issue_number: int,
        body_hash: str,
        worker_sha: str,
        error_code: str,
    ) -> TransportStatusV2:
        return TransportStatusV2(
            status_schema_version=2,
            issue_number=issue_number,
            request_id=None,
            operation=None,
            transport_status="REJECTED",
            request_body_sha256=body_hash,
            worker_commit_sha=worker_sha,
            error_code=error_code,
        )

    @staticmethod
    def _failed(
        *,
        request: ParsedIssueRequest,
        worker_sha: str,
        error_code: str,
    ) -> TransportStatusV2:
        return TransportStatusV2(
            status_schema_version=2,
            issue_number=request.issue_number,
            request_id=request.request_id,
            operation=request.operation,
            transport_status="FAILED",
            request_body_sha256=request.request_body_sha256,
            worker_commit_sha=worker_sha,
            error_code=error_code,
        )

    def _store_status(self, status: TransportStatusV2) -> TransportStatusV2:
        self._status_store.put_status(status)
        return status
