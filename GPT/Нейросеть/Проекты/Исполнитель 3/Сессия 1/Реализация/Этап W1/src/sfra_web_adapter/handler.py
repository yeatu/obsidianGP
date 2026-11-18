"""Serialized Issue event orchestration around an injected V2.2 worker."""
from __future__ import annotations
import json
from typing import Mapping, Protocol
from .event import OpenedIssueRequest, parse_opened_issue_event
from .ledger import MarkerLedger

class CommentPort(Protocol):
    def list_comments(self, issue_number: int) -> list[dict[str, object]]: ...
    def create_comment(self, issue_number: int, body: str) -> None: ...

class WorkerPort(Protocol):
    def run(self, issue_number: int, *, snapshot: object, worker_commit_sha: str) -> object: ...

def _safe_status_mapping(status: object) -> dict[str, object]:
    method = getattr(status, "to_mapping", None)
    if not callable(method):
        raise TypeError("worker must return a typed transport status")
    value = method()
    if not isinstance(value, Mapping):
        raise TypeError("transport status must be a mapping")
    keys = {
        "status_schema_version", "issue_number", "request_id", "operation",
        "transport_status", "request_body_sha256", "worker_commit_sha",
        "error_code", "result",
    }
    if set(value.keys()) != keys:
        raise ValueError("worker returned an unexpected status shape")
    return {
        "status_schema_version": value["status_schema_version"],
        "issue_number": value["issue_number"],
        "request_id": value["request_id"],
        "operation": value["operation"],
        "transport_status": value["transport_status"],
        "request_body_sha256": value["request_body_sha256"],
        "worker_commit_sha": value["worker_commit_sha"],
        "error_code": value["error_code"],
        "result": value["result"],
    }

def _render_status(status: Mapping[str, object], marker: str) -> str:
    encoded = json.dumps(status, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    fence = chr(96) * 3
    return "\n".join((marker, "SFRA transport status v2", "", fence + "json", encoded, fence))

def handle_opened_event(payload: Mapping[str, object], *, event_name: str, action: str,
                        comments: CommentPort, worker: WorkerPort, snapshot: object,
                        worker_commit_sha: str) -> str:
    request: OpenedIssueRequest = parse_opened_issue_event(
        payload, event_name=event_name, action=action
    )
    decision = MarkerLedger().inspect(
        request.issue_number, request.body, comments.list_comments(request.issue_number)
    )
    if decision.action == "SKIP":
        return decision.reason
    if decision.action == "REJECT":
        if decision.reason == "request_body_changed":
            comments.create_comment(request.issue_number, "SFRA request rejected: request_body_changed")
        return decision.reason
    if decision.action == "START":
        assert decision.marker is not None
        comments.create_comment(request.issue_number, decision.marker)
    status = worker.run(
        request.issue_number, snapshot=snapshot, worker_commit_sha=worker_commit_sha
    )
    mapping = _safe_status_mapping(status)
    state = mapping["transport_status"]
    marker_state = state if state in {"COMPLETED", "REJECTED", "FAILED"} else "FAILED"
    marker = MarkerLedger._marker(request.issue_number, request.body_sha256, marker_state)
    comments.create_comment(request.issue_number, _render_status(mapping, marker))
    return str(state)
