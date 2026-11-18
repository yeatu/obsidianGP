from __future__ import annotations
import json

from sfra_issue_core import InMemoryTransportStatusStore, IssueRecord, IssueWorkerCore
from types import SimpleNamespace
from sfra_web_adapter.runner import (
    CANONICAL_QUERY, SNAPSHOT, SyntheticReadSourceApplication, SyntheticSearchApplication,
)
from sfra_web_adapter.corpus import SyntheticGoldCorpus

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
        payload = {"query": CANONICAL_QUERY}
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
    assert result["result"]["counts"]["included"] == 2
    assert "Synthetic fixture excerpt only." not in str(result)

def test_v2_2_core_keeps_read_source_on_synthetic_injected_port():
    body = request_body("read_source", {
        "node_id": "gate_rule",
        "expected_hash": "sha256:3083f2441d11dcec16760ea8bf667cec23f2bf161829ae59a257e4b13edd700c",
        "scope": "node",
    })
    status = make_worker(body).run(29, snapshot=SNAPSHOT, worker_commit_sha=WORKER_SHA)
    result = status.to_mapping()
    assert result["transport_status"] == "COMPLETED"
    assert result["result"]["operation"] == "read_source"
    assert result["result"]["counts"]["fragments"] == 1
    assert "synthetic/policies/limits.md" not in str(result)

def test_synthetic_applications_expose_bounded_canonical_gold_case_projection():
    corpus = SyntheticGoldCorpus.load_default()
    search = SyntheticSearchApplication(corpus)
    search.search(SimpleNamespace(query=CANONICAL_QUERY))
    projected = search.last_projection
    assert projected["schema_version"] == "sfra.web.synthetic-evidence.v1"
    assert projected["corpus_id"] == "sfra.synthetic.gold.e2-e3-context-pack"
    assert projected["corpus_version"] == "1.0.0"
    assert projected["corpus_sha256"] == "sha256:915304e812906f64003d9aacb0dd4b7701f7fbcf4f24fdc3cda21d1108b13068"
    assert projected["case_id"] == "gq-004-exception-pair"
    assert [x["node_id"] for x in projected["evidence"]] == ["gate_rule", "gate_exception"]
    assert projected["evidence"][0]["source_path"] == "synthetic/policies/limits.md"
    assert "12 контейнеров" in projected["evidence"][0]["excerpt"]
    assert "14 контейнеров" in projected["evidence"][1]["excerpt"]

    read = SyntheticReadSourceApplication(corpus)
    request = SimpleNamespace(
        node_id="gate_rule",
        expected_hash="sha256:3083f2441d11dcec16760ea8bf667cec23f2bf161829ae59a257e4b13edd700c",
    )
    result = read.read(request)
    assert result.status == "ok"
    assert read.last_projection["case_id"] == "gq-004-exception-pair"
    assert read.last_projection["evidence"][0]["node_id"] == "gate_rule"
