"""Serialized Issue event orchestration around an injected V2.2 worker."""
from __future__ import annotations
import hashlib
import json
import re
from typing import Callable, Mapping, Protocol
from sfra_issue_core import validate_transport_status_v2
from .event import OpenedIssueRequest, parse_opened_issue_event
from .ledger import MarkerLedger
from .corpus import CORPUS_ID, CORPUS_SHA256, CORPUS_VERSION

CANONICAL_CASE_ID = "gq-004-exception-pair"
CANONICAL_QUERY = "обычный лимит шлюза и исключение для учений"
CANONICAL_SEARCH_NODE_IDS = ("gate_rule", "gate_exception")
APPROVED_EVIDENCE_BY_NODE = {
    "gate_rule": {
        "source_path": "synthetic/policies/limits.md",
        "content_hash": "sha256:3083f2441d11dcec16760ea8bf667cec23f2bf161829ae59a257e4b13edd700c",
        "line_start": 2,
        "line_end": 2,
    },
    "gate_exception": {
        "source_path": "synthetic/policies/limits.md",
        "content_hash": "sha256:91677acb7f96a2becf66a12572459e4cac2a966b6a08e399fa831f1c19d4bbf5",
        "line_start": 3,
        "line_end": 3,
    },
}

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
    """Validate and copy only the single approved W1 evidence projection."""
    if not isinstance(value, Mapping) or set(value.keys()) != {
        "schema_version", "corpus_id", "corpus_version", "corpus_sha256", "case_id", "operation", "evidence"
    }:
        raise ValueError("synthetic response projection has an invalid envelope")
    if (value["schema_version"] != "sfra.web.synthetic-evidence.v1" or
            value["corpus_id"] != CORPUS_ID or value["corpus_version"] != CORPUS_VERSION or
            value["corpus_sha256"] != CORPUS_SHA256 or value["operation"] != operation):
        raise ValueError("synthetic response corpus identity mismatch")
    if value["case_id"] != CANONICAL_CASE_ID:
        raise ValueError("synthetic response case is not approved")

    evidence = value["evidence"]
    if not isinstance(evidence, list):
        raise ValueError("synthetic response evidence is invalid")
    if operation == "search_vault":
        expected_node_ids = CANONICAL_SEARCH_NODE_IDS
        if tuple(item.get("node_id") if isinstance(item, Mapping) else None for item in evidence) != expected_node_ids:
            raise ValueError("synthetic search evidence is not the canonical node set")
    elif operation == "read_source":
        if len(evidence) != 1 or not isinstance(evidence[0], Mapping):
            raise ValueError("synthetic read evidence must contain exactly one approved node")
        if evidence[0].get("node_id") not in APPROVED_EVIDENCE_BY_NODE:
            raise ValueError("synthetic read node is not approved")
    else:
        raise ValueError("synthetic response operation is not approved")

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
        expected = APPROVED_EVIDENCE_BY_NODE.get(item["node_id"])
        if expected is None:
            raise ValueError("synthetic response node is not approved")
        if any(item[field] != expected[field] for field in (
            "source_path", "content_hash", "line_start", "line_end"
        )):
            raise ValueError("synthetic response provenance does not match the approved node")
        if (not re.fullmatch(r"sha256:[0-9a-f]{64}", item["content_hash"]) or
                hashlib.sha256(item["excerpt"].encode("utf-8", errors="strict")).hexdigest()
                != item["content_hash"].removeprefix("sha256:")):
            raise ValueError("synthetic response excerpt does not match the approved content hash")
        if (isinstance(item["line_start"], bool) or type(item["line_start"]) is not int
                or isinstance(item["line_end"], bool) or type(item["line_end"]) is not int
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
        "case_id": CANONICAL_CASE_ID,
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
