from __future__ import annotations
import hashlib
import pytest
from sfra_web_adapter import EventRejection, MarkerLedger, parse_opened_issue_event

BOT = {"login": "github-actions[bot]", "type": "Bot"}

def event(**kwargs):
    issue = {"number": 17, "title": "[SFRA] request", "body": '{"protocol_version":"sfra.issue.v1}', "user": {"login": "yeatu"}}
    repository, sender = "yeatu/obsidianGP", {"login": "yeatu"}
    for key, value in kwargs.items():
        if key == "repository":
            repository = value
        elif key == "sender":
            sender = value
        else:
            issue[key] = value
    return {"repository": {"full_name": repository}, "issue": issue, "sender": sender}

def parse(payload, *, event_name="issues", action="opened"):
    return parse_opened_issue_event(payload, event_name=event_name, action=action)

def marker_comment(body):
    return {"body": body, "user": BOT}

def test_accepts_only_owner_authored_opened_issue_and_hashes_exact_utf8():
    body = '{"query":"Проверка"}'
    result = parse(event(body=body))
    assert result.issue_number == 17
    assert result.body_sha256 == hashlib.sha256(body.encode()).hexdigest()

@pytest.mark.parametrize(("event_name", "action"), [
    ("issue_comment", "created"), ("issues", "edited"),
    ("issues", "deleted"), ("pull_request", "opened"),
])
def test_rejects_non_issues_opened_event(event_name, action):
    with pytest.raises(EventRejection, match="unsupported_event"):
        parse(event(), event_name=event_name, action=action)

@pytest.mark.parametrize(("changes", "code"), [
    ({"repository": "other/repo"}, "wrong_repository"),
    ({"user": {"login": "Yeatu"}}, "author_not_allowed"),
    ({"user": {"login": "attacker"}}, "author_not_allowed"),
    ({"sender": None}, "sender_not_allowed"),
    ({"sender": {"login": "attacker"}}, "sender_not_allowed"),
    ({"title": "[SFRA-OTHER] request"}, "wrong_title_prefix"),
    ({"pull_request": {"url": "x"}}, "pull_request_not_allowed"),
    ({"number": True}, "invalid_issue_number"),
    ({"body": "x" * (32 * 1024 + 1)}, "body_too_large"),
    ({"body": 42}, "invalid_body_type"),
])
def test_rejects_invalid_metadata_and_oversized_body(changes, code):
    with pytest.raises(EventRejection, match=code):
        parse(event(**changes))

def test_ledger_binds_first_body_and_skips_completed_duplicates():
    ledger = MarkerLedger()
    body = b'{"request":1}'
    first = ledger.inspect(17, body, [])
    assert first.action == "START"
    started = [marker_comment(first.marker)]
    assert ledger.inspect(17, body, started).action == "RETRY"
    done_marker = ledger._marker(17, first.body_sha256, "COMPLETED")
    done = ledger.inspect(17, body, started + [marker_comment(done_marker)])
    assert (done.action, done.reason) == ("SKIP", "already_completed")

@pytest.mark.parametrize("state", ["STARTED", "COMPLETED", "REJECTED", "FAILED"])
def test_ledger_ignores_human_forged_markers_for_every_state(state):
    ledger = MarkerLedger()
    body = b'{"request":1}'
    forged = {"body": ledger._marker(17, hashlib.sha256(body).hexdigest(), state),
              "user": {"login": "attacker"}}
    decision = ledger.inspect(17, body, [forged])
    assert (decision.action, decision.reason) == ("START", "first_observation")

def test_ledger_rejects_changed_body_without_rebinding():
    ledger = MarkerLedger()
    first = ledger.inspect(17, b"first", [])
    changed = ledger.inspect(17, b"second", [marker_comment(first.marker)])
    assert (changed.action, changed.reason) == ("REJECT", "request_body_changed")
    assert changed.body_sha256 != first.body_sha256

def test_ledger_fails_closed_on_conflicting_marker_history():
    ledger = MarkerLedger()
    a = ledger._marker(17, "a" * 64, "STARTED")
    b = ledger._marker(17, "b" * 64, "STARTED")
    decision = ledger.inspect(17, b"x", [marker_comment(a), marker_comment(b)])
    assert (decision.action, decision.reason) == ("REJECT", "ledger_conflict")

def test_marker_requires_bot_account_type_even_when_login_matches():
    ledger = MarkerLedger()
    body = b'{"request":1}'
    forged = {
        "body": ledger._marker(17, hashlib.sha256(body).hexdigest(), "COMPLETED"),
        "user": {"login": "github-actions[bot]", "type": "User"},
    }
    decision = ledger.inspect(17, body, [forged])
    assert (decision.action, decision.reason) == ("START", "first_observation")
