from __future__ import annotations

import json

from sfra_issue_core import IssueRecord

SNAPSHOT_VALUES = {
    "vault_commit_sha": "a" * 40,
    "sidecar_commit_sha": "b" * 40,
    "manifest_sha256": "sha256:" + "c" * 64,
}
REQUEST_ID = "6f2f5b1e-6ab7-4a9e-9c2b-c0c9846c7d14"
WORKER_SHA = "d" * 40
CONTENT_HASH = "sha256:" + "1" * 64


def envelope(operation: str = "search_vault", payload: dict | None = None) -> dict:
    if payload is None:
        payload = {"query": "contract test"}
    return {
        "protocol_version": "sfra.issue.v1",
        "request_id": REQUEST_ID,
        "operation": operation,
        "payload": payload,
    }


def body_for(operation: str = "search_vault", payload: dict | None = None) -> str:
    return json.dumps(envelope(operation, payload), ensure_ascii=False, separators=(",", ":"))


def issue_record(
    body: str | bytes | None = None,
    *,
    number: int = 15,
    title: str = "[SFRA] test request",
    repository: str = "yeatu/obsidianGP",
    author: str = "yeatu",
    is_pull_request: bool = False,
) -> IssueRecord:
    if body is None:
        body = body_for()
    return IssueRecord(
        number=number,
        title=title,
        repository_full_name=repository,
        author_login=author,
        body=body,
        is_pull_request=is_pull_request,
    )
