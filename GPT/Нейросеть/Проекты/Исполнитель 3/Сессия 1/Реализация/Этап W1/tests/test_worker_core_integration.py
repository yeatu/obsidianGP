from __future__ import annotations
import json

from sfra_issue_core import InMemoryTransportStatusStore, IssueRecord, IssueWorkerCore
from sfra_web_adapter.runner import (
    GOLD_NODE, SNAPSHOT, SyntheticReadSourceApplication, SyntheticSearchApplication,
)

WORKER_SHA = "a" * 40
REQUEST_ID = "6f2f5b1e-6ab7-4a9e-9c2b-c0c9846c7d14"

class Reader:
    def __init__(self, body):
        self.body = body
    def read_issue(self, issue_number):
        return IssueRecord(issue_number, "[SFRA] synthetic", "yeatu/obsidianGP",
                           "yeatu", self.body, False)

def request_body(operation="search_vault", payload=None):
    if payload is None:
        payload = {"query": "synthetic fixture query"}
    return json.dumps({
        "protocol_version": "sfra.issue.v1",
        "request_id": REQUEST_ID,
        "operation": operation,
        "payload": payload,
    })

def make_worker(body):
    return IssueWorkerCore(
        issue_reader=Reader(body),
        status_store=InMemoryTransportStatusStore(),
        search_application=SyntheticSearchApplication(),
        read_source_application=SyntheticReadSourceApplication(),
    )

def test_v2_2_core_runs_search_through_injected_synthetic_application_port():
    status = make_worker(request_body()).run(
        29, snapshot=SNAPSHOT, worker_commit_sha=WORKER_SHA
    )
    result = status.to_mapping()
    assert result["transport_status"] == "COMPLETED"
    assert result["result"]["operation"] == "search_vault"
    assert result["result"]["counts"]["included"] == 1
    assert "Synthetic fixture excerpt only." not in str(result)

def test_v2_2_core_keeps_read_source_on_synthetic_injected_port():
    body = request_body("read_source", {
        "node_id": "manual_intro",
        "expected_hash": "sha256:04b8c940ba7056617a1fc4d4e45eff787033888862cd291eb9770f3fe6ea0f77",
        "scope": "node",
    })
    status = make_worker(body).run(29, snapshot=SNAPSHOT, worker_commit_sha=WORKER_SHA)
    result = status.to_mapping()
    assert result["transport_status"] == "COMPLETED"
    assert result["result"]["operation"] == "read_source"
    assert result["result"]["counts"]["fragments"] == 1
    assert "synthetic://fixture" not in str(result)

def test_synthetic_applications_expose_bounded_gold_corpus_projection():
    search = SyntheticSearchApplication()
    search.search({"query": "synthetic"})
    projected = search.last_projection
    assert projected["schema_version"] == 1
    assert projected["operation"] == "search_vault"
    assert projected["items"][0]["node_id"] == "manual_intro"
    assert projected["items"][0]["source_path"] == "synthetic/operations/manual.md"
    assert projected["items"][0]["content_hash"] == GOLD_NODE["content_hash"]
    assert projected["items"][0]["excerpt"] == GOLD_NODE["raw_text"]

    read = SyntheticReadSourceApplication()
    request = type("Request", (), {
        "node_id": "manual_intro",
        "expected_hash": GOLD_NODE["content_hash"],
    })()
    result = read.read(request)
    assert result.status == "ok"
    assert read.last_projection["operation"] == "read_source"
    assert read.last_projection["items"][0]["excerpt"] == GOLD_NODE["raw_text"]
