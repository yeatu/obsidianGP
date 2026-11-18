from __future__ import annotations
from io import BytesIO
from urllib.error import HTTPError

import pytest

import sfra_web_adapter.github_api as github_api
from sfra_web_adapter import GitHubAPIError, GitHubREST, GitHubCommentStatusStore
from sfra_web_adapter.ledger import authenticated_markers


def client():
    return GitHubREST(token="synthetic-test-token", repository="yeatu/obsidianGP")


def test_rest_client_rejects_unapproved_repository_endpoint_and_empty_token():
    with pytest.raises(ValueError, match="token"):
        GitHubREST(token="", repository="yeatu/obsidianGP")
    with pytest.raises(ValueError, match="allowlisted"):
        GitHubREST(token="x", repository="other/repo")
    with pytest.raises(ValueError, match="endpoint"):
        GitHubREST(token="x", repository="yeatu/obsidianGP", api_url="https://example.invalid")


def test_http_error_is_sanitized_and_does_not_echo_response_body(monkeypatch):
    def forbidden(request, timeout):
        raise HTTPError(request.full_url, 403, "Forbidden", {}, BytesIO(b"private response body"))
    monkeypatch.setattr(github_api, "urlopen", forbidden)
    with pytest.raises(GitHubAPIError) as error:
        client().get_issue(9)
    assert "private response body" not in str(error.value)
    assert str(error.value) == "GitHub API request failed"


def test_comment_history_uses_bounded_pagination(monkeypatch):
    instance = client()
    calls = []
    def paged(method, path, payload=None):
        calls.append(path)
        if path.endswith("page=1"):
            return [{"body": str(i)} for i in range(100)]
        return [{"body": "last"}]
    monkeypatch.setattr(instance, "_request", paged)
    assert len(instance.list_comments(9)) == 101
    assert len(calls) == 2
    assert "page=1" in calls[0] and "page=2" in calls[1]

def test_comment_history_over_pagination_limit_fails_closed(monkeypatch):
    instance = client()
    monkeypatch.setattr(instance, "_request", lambda *args, **kwargs: [{"body": ""}] * 100)
    with pytest.raises(GitHubAPIError, match="pagination limit"):
        instance.list_comments(9)


def test_comment_body_size_is_bounded_before_network_call(monkeypatch):
    instance = client()
    called = []
    monkeypatch.setattr(instance, "_request", lambda *args, **kwargs: called.append(True))
    with pytest.raises(ValueError, match="45 KiB"):
        instance.create_comment(9, "x" * (45 * 1024 + 1))
    assert called == []


class FakeComments:
    def __init__(self):
        self.comments = []
    def list_comments(self, issue_number):
        return list(self.comments)
    def create_comment(self, issue_number, body):
        self.comments.append({"body": body, "user": {"login": "github-actions[bot]", "id": 41898282, "type": "Bot"}})


def test_comment_status_store_preserves_first_digest_on_retry_or_changed_body():
    comments = FakeComments()
    store = GitHubCommentStatusStore(comments)
    first = "sha256:" + "a" * 64
    changed = "sha256:" + "b" * 64
    assert store.bind_request_body_sha256(9, first) == first
    assert len(comments.comments) == 1
    markers = authenticated_markers(9, comments.comments)
    assert len(markers) == 1
    assert markers[0].body_sha256 == "a" * 64
    assert markers[0].state == "STARTED"
    assert store.bind_request_body_sha256(9, first) == first
    assert store.bind_request_body_sha256(9, changed) == first
    assert len(comments.comments) == 1


@pytest.mark.parametrize(
    "digest",
    [
        "a" * 64,
        "SHA256:" + "a" * 64,
        "sha256:" + "A" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "a" * 64 + "x",
        "sha256:",
        None,
    ],
)
def test_comment_status_store_rejects_malformed_v2_digest_before_reading_or_writing(digest):
    comments = FakeComments()
    store = GitHubCommentStatusStore(comments)
    with pytest.raises(ValueError, match="sha256:<64 lowercase hex>"):
        store.bind_request_body_sha256(9, digest)
    assert comments.comments == []


def test_comment_status_store_fails_closed_on_conflicting_authenticated_markers():
    comments = FakeComments()
    comments.comments.extend([
        {
            "body": MarkerLedger._marker(9, "a" * 64, "STARTED"),
            "user": {"login": "github-actions[bot]", "id": 41898282, "type": "Bot"},
        },
        {
            "body": MarkerLedger._marker(9, "b" * 64, "STARTED"),
            "user": {"login": "github-actions[bot]", "id": 41898282, "type": "Bot"},
        },
    ])
    store = GitHubCommentStatusStore(comments)

    baseline = store.bind_request_body_sha256(9, "sha256:" + "a" * 64)

    assert baseline.startswith("sha256:")
    assert baseline != "sha256:" + "a" * 64
    assert len(authenticated_markers(9, comments.comments)) == 2
