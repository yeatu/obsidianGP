"""Serialized Issue event orchestration around an injected V2.2 worker."""
from __future__ import annotations
import json
import re
from typing import Callable, Mapping, Protocol
from sfra_issue_core import validate_transport_status_v2
from .event import OpenedIssueRequest, parse_opened_issue_event
from .ledger import MarkerLedger
from .corpus import CORPUS_ID, CORPUS_SHA256, CORPUS_VERSION

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
    value = validate_transport_status_v2(value)
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

def _safe_synthetic_projection(value: object, operation: str) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value.keys()) != {
        "schema_version", "corpus_id", "corpus_version", "corpus_sha256", "case_id", "operation", "evidence"
    }:
        raise ValueError("synthetic response projection has an invalid envelope")
    if (value["schema_version"] != "sfra.web.synthetic-evidence.v1" or
            value["corpus_id"] != CORPUS_ID or value["corpus_version"] != CORPUS_VERSION or
            value["corpus_sha256"] != CORPUS_SHA256 or value["operation"] != operation):
        raise ValueError("synthetic response corpus identity mismatch")
    case_id = value["case_id"]
    if not isinstance(case_id, str) or not re.fullmatch(r"gq-[0-9]{3}-[a-z0-9-]+", case_id):
        raise ValueError("synthetic response case ID is invalid")
    evidence = value["evidence"]
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 8:
        raise ValueError("synthetic response evidence count is invalid")
    safe_items = []
    for item in evidence:
        if not isinstance(item, Mapping) or set(item.keys()) != {
            "node_id", "source_path", "content_hash", "line_start", "line_end", "excerpt"
        }:
            raise ValueError("synthetic response evidence item has an invalid shape")
        if not all(isinstance(item[k], str) for k in (
            "node_id", "source_path", "content_hash", "excerpt"
        )):
            raise ValueError("synthetic response evidence text fields are invalid")
        if (not re.fullmatch(r"[a-z0-9_]{1,80}", item["node_id"]) or
                not item["source_path"].startswith("synthetic/") or
                ".." in item["source_path"].split("/") or len(item["source_path"]) > 240):
            raise ValueError("synthetic response provenance is not synthetic")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", item["content_hash"]):
            raise ValueError("synthetic response content hash is invalid")
        if (isinstance(item["line_start"], bool) or not isinstance(item["line_start"], int)
                or isinstance(item["line_end"], bool) or not isinstance(item["line_end"], int)
                or item["line_start"] < 1 or item["line_end"] < item["line_start"]):
            raise ValueError("synthetic response line span is invalid")
        if len(item["excerpt"].encode("utf-8")) > 1200 or "```" in item["excerpt"]:
            raise ValueError("synthetic response excerpt exceeds bounds")
        safe_items.append({k: item[k] for k in (
            "node_id", "source_path", "content_hash", "line_start", "line_end", "excerpt"
        )})
    return {
        "schema_version": "sfra.web.synthetic-evidence.v1",
        "corpus_id": CORPUS_ID,
        "corpus_version": CORPUS_VERSION,
        "corpus_sha256": CORPUS_SHA256,
        "case_id": case_id,
        "operation": operation,
        "evidence": safe_items,
    }

def _render_status(status: Mapping[str, object], marker: str,
                   projection: Mapping[str, object] | None = None) -> str:
    encoded = json.dumps(status, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    fence = chr(96) * 3
    parts = [marker, "SFRA transport status v2", "", fence + "json", encoded, fence]
    if projection is not None:
        projected = json.dumps(projection, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        parts.extend(["", "SFRA synthetic evidence v1", "", fence + "json", projected, fence])
    return "\n".join(parts)

def handle_opened_event(payload: Mapping[str, object], *, event_name: str, action: str,
                        comments: CommentPort, worker: WorkerPort, snapshot: object,
                        worker_commit_sha: str,
                        response_projection: Callable[[str], object] | None = None) -> str:
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
    projection = None
    if state == "COMPLETED" and response_projection is not None:
        candidate = response_projection(str(mapping["operation"]))
        if candidate is not None:
            projection = _safe_synthetic_projection(candidate, str(mapping["operation"]))
    marker_state = state if state in {"COMPLETED", "REJECTED", "FAILED"} else "FAILED"
    marker = MarkerLedger._marker(request.issue_number, request.body_sha256, marker_state)
    comments.create_comment(request.issue_number, _render_status(mapping, marker, projection))
    return str(state)
