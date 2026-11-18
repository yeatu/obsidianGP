from __future__ import annotations
from sfra_web_adapter import handle_opened_event

BOT = {"login": "github-actions[bot]", "id": 41898282, "type": "Bot"}

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
            "request_body_sha256": "sha256:" + self.digest, "worker_commit_sha": "a" * 40,
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

def test_handler_renders_only_allowlisted_canonical_gold_evidence_in_issue_comment():
    from sfra_web_adapter.corpus import SyntheticGoldCorpus
    comments, worker = Comments(), Worker()
    corpus = SyntheticGoldCorpus.load_default()
    case = corpus.case_for_query("обычный лимит шлюза и исключение для учений")
    assert case is not None
    projection = corpus.evidence(case)
    assert projection["case_id"] == "gq-004-exception-pair"
    handle_opened_event(payload(), event_name="issues", action="opened",
        comments=comments, worker=worker, snapshot=object(), worker_commit_sha="a" * 40,
        response_projection=lambda operation: projection)
    rendered = comments.items[-1]["body"]
    assert "SFRA synthetic evidence v1" in rendered
    assert "Обычный предел составляет 12 контейнеров" in rendered
    assert "Исключение для учений разрешает 14 контейнеров" in rendered
    assert "synthetic/policies/limits.md" in rendered
    assert "gq-004-exception-pair" in rendered
    assert "915304e812906f64003d9aacb0dd4b7701f7fbcf4f24fdc3cda21d1108b13068" in rendered

def test_handler_rejects_non_synthetic_projection_provenance():
    from sfra_web_adapter.handler import _safe_synthetic_projection
    from sfra_web_adapter.corpus import SyntheticGoldCorpus
    import pytest
    corpus = SyntheticGoldCorpus.load_default()
    case = corpus.case_for_query("обычный лимит шлюза и исключение для учений")
    bad = corpus.evidence(case)
    bad["evidence"][0]["source_path"] = "/private/vault.md"
    with pytest.raises(ValueError, match="provenance is not synthetic"):
        _safe_synthetic_projection(bad, "search_vault")


def test_handler_rejects_projection_with_unapproved_corpus_digest():
    from sfra_web_adapter.handler import _safe_synthetic_projection
    from sfra_web_adapter.corpus import SyntheticGoldCorpus
    import pytest
    corpus = SyntheticGoldCorpus.load_default()
    case = corpus.case_for_query("обычный лимит шлюза и исключение для учений")
    bad = corpus.evidence(case)
    bad["corpus_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="corpus identity mismatch"):
        _safe_synthetic_projection(bad, "search_vault")

def test_handler_rejects_evidence_bound_to_a_different_operation():
    from sfra_web_adapter.handler import _safe_synthetic_projection
    from sfra_web_adapter.corpus import SyntheticGoldCorpus
    import pytest
    corpus = SyntheticGoldCorpus.load_default()
    case = corpus.case_for_query("обычный лимит шлюза и исключение для учений")
    projection = corpus.evidence(case, operation="search_vault")
    with pytest.raises(ValueError, match="corpus identity mismatch"):
        _safe_synthetic_projection(projection, "read_source")


def test_handler_rejects_unapproved_projection_fields():
    from sfra_web_adapter.handler import _safe_synthetic_projection
    from sfra_web_adapter.corpus import SyntheticGoldCorpus
    import pytest
    corpus = SyntheticGoldCorpus.load_default()
    case = corpus.case_for_query("обычный лимит шлюза и исключение для учений")
    projection = corpus.evidence(case)
    projection["raw_request"] = "must never be rendered"
    with pytest.raises(ValueError, match="invalid envelope"):
        _safe_synthetic_projection(projection, "search_vault")

def test_status_store_ignores_markers_with_missing_or_wrong_bot_id():
    from sfra_web_adapter.ports import GitHubCommentStatusStore
    import pytest

    class Client:
        def __init__(self, user):
            self.comments = [{
                "body": "<!-- sfra-web-v1 issue=21 body_sha256=" + "a" * 64 + " state=COMPLETED -->",
                "user": user,
            }]
            self.created = []
        def list_comments(self, issue_number):
            return self.comments
        def create_comment(self, issue_number, body):
            self.created.append(body)

    identities = [
        {"login": "github-actions[bot]", "type": "Bot"},
        {"login": "github-actions[bot]", "id": 1, "type": "Bot"},
        {"login": "github-actions[bot]", "id": "41898282", "type": "Bot"},
        {"login": "github-actions[bot]", "id": 41898282, "type": "User"},
    ]
    for identity in identities:
        client = Client(identity)
        store = GitHubCommentStatusStore(client)
        digest = "b" * 64

        assert store.bind_request_body_sha256(21, digest) == digest
        assert len(client.created) == 1
        assert "state=STARTED" in client.created[0]
