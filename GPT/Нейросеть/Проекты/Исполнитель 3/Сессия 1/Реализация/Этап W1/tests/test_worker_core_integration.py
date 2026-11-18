from __future__ import annotations
import json
from types import SimpleNamespace

from sfra_issue_core import InMemoryTransportStatusStore, IssueRecord, IssueWorkerCore
from sfra_web_adapter import MarkerLedger, handle_opened_event
from sfra_web_adapter.ports import GitHubCommentStatusStore
from sfra_web_adapter.corpus import SyntheticGoldCorpus
from sfra_web_adapter.runner import (
    CANONICAL_QUERY, SNAPSHOT, SyntheticReadSourceApplication, SyntheticSearchApplication,
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
    assert "Обычный предел составляет 12 контейнеров" not in str(result)

def test_v2_2_core_keeps_read_source_on_synthetic_injected_port():
    corpus = SyntheticGoldCorpus.load_default()
    node = corpus.node("gate_rule")
    assert node is not None
    body = request_body("read_source", {
        "node_id": node.node_id,
        "expected_hash": node.content_hash,
        "scope": "node",
    })
    status = make_worker(body).run(29, snapshot=SNAPSHOT, worker_commit_sha=WORKER_SHA)
    result = status.to_mapping()
    assert result["transport_status"] == "COMPLETED"
    assert result["result"]["operation"] == "read_source"
    assert result["result"]["counts"]["fragments"] == 1
    assert node.raw_text not in str(result)

def test_synthetic_applications_expose_bounded_gold_corpus_projection():
    corpus = SyntheticGoldCorpus.load_default()
    search = SyntheticSearchApplication(corpus)
    search.search(SimpleNamespace(query=CANONICAL_QUERY))
    projected = search.last_projection
    assert projected["schema_version"] == "sfra.web.synthetic-evidence.v1"
    assert projected["case_id"] == "gq-004-exception-pair"
    assert projected["corpus_sha256"] == "sha256:915304e812906f64003d9aacb0dd4b7701f7fbcf4f24fdc3cda21d1108b13068"
    assert projected["evidence"][0]["node_id"] == "gate_rule"
    assert projected["evidence"][0]["source_path"] == "synthetic/policies/limits.md"

    node = corpus.node("manual_intro")
    assert node is not None
    read = SyntheticReadSourceApplication(corpus)
    request = SimpleNamespace(node_id=node.node_id, expected_hash=node.content_hash)
    result = read.read(request)
    assert result.status == "ok"
    assert read.last_projection["case_id"] == "gq-004-exception-pair"
    assert read.last_projection["evidence"][0]["excerpt"] == node.raw_text

class BotComments:
    def __init__(self):
        self.items = []
    def list_comments(self, issue_number):
        return list(self.items)
    def create_comment(self, issue_number, body):
        self.items.append({"body": body, "user": {"login": "github-actions[bot]"}})

def test_event_body_digest_is_rechecked_against_api_reread_before_any_service_call():
    event_body = request_body()
    changed_body = request_body(payload={"query": "edited after webhook delivery"})
    comments = BotComments()
    started = MarkerLedger().inspect(29, event_body.encode("utf-8"), [])
    comments.create_comment(29, started.marker)

    class CurrentIssueReader:
        def read_issue(self, issue_number):
            return IssueRecord(29, "[SFRA] synthetic", "yeatu/obsidianGP",
                               "yeatu", changed_body, False)

    search_app = SyntheticSearchApplication()
    read_app = SyntheticReadSourceApplication()
    worker = IssueWorkerCore(
        issue_reader=CurrentIssueReader(),
        status_store=GitHubCommentStatusStore(comments),
        search_application=search_app,
        read_source_application=read_app,
    )
    event = {
        "repository": {"full_name": "yeatu/obsidianGP"},
        "sender": {"login": "yeatu"},
        "issue": {"number": 29, "title": "[SFRA] synthetic", "body": event_body,
                  "user": {"login": "yeatu"}},
    }
    outcome = handle_opened_event(
        event, event_name="issues", action="opened", comments=comments,
        worker=worker, snapshot=SNAPSHOT, worker_commit_sha=WORKER_SHA,
    )
    assert outcome == "REJECTED"
    assert search_app.calls == 0
    assert read_app.calls == 0
    assert "request_body_changed" in comments.items[-1]["body"]
