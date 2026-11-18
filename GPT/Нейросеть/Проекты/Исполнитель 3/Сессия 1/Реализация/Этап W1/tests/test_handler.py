from __future__ import annotations
from sfra_web_adapter import handle_opened_event

BOT = {"login": "github-actions[bot]"}

def payload(body='{"protocol_version":"sfra.issue.v1"}'):
    return {"repository": {"full_name": "yeatu/obsidianGP"},
            "sender": {"login": "yeatu"},
            "issue": {"number": 21, "title": "[SFRA] synthetic", "body": body,
                      "user": {"login": "yeatu"}}}

class Comments:
    def __init__(self):
        self.items = []
    def list_comments(self, issue_number):
        return list(self.items)
    def create_comment(self, issue_number, body):
        self.items.append({"body": body, "user": BOT})

class Status:
    def __init__(self, digest, state="COMPLETED"):
        self.digest = digest
        self.state = state
    def to_mapping(self):
        return {
            "status_schema_version": 2, "issue_number": 21,
            "request_id": "6f2f5b1e-6ab7-4a9e-9c2b-c0c9846c7d14",
            "operation": "search_vault", "transport_status": self.state,
            "request_body_sha256": self.digest, "worker_commit_sha": "a" * 40,
            "error_code": None if self.state == "COMPLETED" else "application_service_failed",
            "result": {"operation": "search_vault", "business_status": "complete",
                       "scope": None, "counts": {"candidates": 1}, "diagnostic_codes": []}
                     if self.state == "COMPLETED" else None,
        }

class Worker:
    def __init__(self):
        self.calls = 0
    def run(self, issue_number, *, snapshot, worker_commit_sha):
        self.calls += 1
        import hashlib
        digest = hashlib.sha256(payload()["issue"]["body"].encode()).hexdigest()
        return Status(digest)

def test_handler_runs_once_persists_allowlisted_result_and_skips_duplicate():
    comments, worker = Comments(), Worker()
    result = handle_opened_event(payload(), event_name="issues", action="opened",
        comments=comments, worker=worker, snapshot=object(), worker_commit_sha="a" * 40)
    assert result == "COMPLETED"
    assert worker.calls == 1
    rendered = comments.items[-1]["body"]
    assert "SFRA transport status v2" in rendered
    assert '"candidates":1' in rendered
    assert handle_opened_event(payload(), event_name="issues", action="opened",
        comments=comments, worker=worker, snapshot=object(), worker_commit_sha="a" * 40) == "already_completed"
    assert worker.calls == 1

def test_handler_rejects_changed_body_before_worker():
    comments, worker = Comments(), Worker()
    handle_opened_event(payload(), event_name="issues", action="opened",
        comments=comments, worker=worker, snapshot=object(), worker_commit_sha="a" * 40)
    changed = payload('{"protocol_version":"sfra.issue.v1","changed":true}')
    assert handle_opened_event(changed, event_name="issues", action="opened",
        comments=comments, worker=worker, snapshot=object(), worker_commit_sha="a" * 40) == "request_body_changed"
    assert worker.calls == 1

def test_handler_ignores_human_forged_completed_marker():
    comments, worker = Comments(), Worker()
    import hashlib
    body = payload()["issue"]["body"].encode()
    digest = hashlib.sha256(body).hexdigest()
    forged = f"<!-- sfra-web-v1 issue=21 body_sha256={digest} state=COMPLETED -->"
    comments.items.append({"body": forged, "user": {"login": "attacker"}})
    assert handle_opened_event(payload(), event_name="issues", action="opened",
        comments=comments, worker=worker, snapshot=object(), worker_commit_sha="a" * 40) == "COMPLETED"
    assert worker.calls == 1

def test_status_store_ignores_human_forged_first_seen_marker():
    from sfra_web_adapter.ports import GitHubCommentStatusStore
    class Client:
        def __init__(self):
            self.comments = [{"body": "<!-- sfra-web-v1 issue=21 body_sha256=" + "a" * 64 + " state=COMPLETED -->",
                              "user": {"login": "attacker"}}]
            self.created = []
        def list_comments(self, issue_number):
            return self.comments
        def create_comment(self, issue_number, body):
            self.created.append(body)
    client = Client()
    store = GitHubCommentStatusStore(client)
    digest = "b" * 64
    assert store.bind_request_body_sha256(21, digest) == digest
    assert len(client.created) == 1
    assert "state=STARTED" in client.created[0]

def test_handler_renders_only_allowlisted_synthetic_evidence_in_issue_comment():
    comments, worker = Comments(), Worker()
    projection = {
        "schema_version": 1,
        "operation": "search_vault",
        "items": [{
            "node_id": "manual_intro",
            "source_path": "synthetic/operations/manual.md",
            "content_hash": "sha256:" + "a" * 64,
            "line_start": 1,
            "line_end": 2,
            "excerpt": "Synthetic corpus excerpt.",
        }],
    }
    handle_opened_event(payload(), event_name="issues", action="opened",
        comments=comments, worker=worker, snapshot=object(), worker_commit_sha="a" * 40,
        response_projection=lambda operation: projection)
    rendered = comments.items[-1]["body"]
    assert "SFRA synthetic evidence v1" in rendered
    assert "Synthetic corpus excerpt." in rendered
    assert "synthetic/operations/manual.md" in rendered

def test_handler_rejects_non_synthetic_projection_provenance():
    from sfra_web_adapter.handler import _safe_synthetic_projection
    bad = {
        "schema_version": 1, "operation": "search_vault",
        "items": [{
            "node_id": "node", "source_path": "/private/vault.md",
            "content_hash": "sha256:" + "a" * 64,
            "line_start": 1, "line_end": 1, "excerpt": "not allowed",
        }],
    }
    import pytest
    with pytest.raises(ValueError, match="not synthetic"):
        _safe_synthetic_projection(bad, "search_vault")
