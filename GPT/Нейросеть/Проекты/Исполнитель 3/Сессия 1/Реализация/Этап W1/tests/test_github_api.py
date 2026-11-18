from __future__ import annotations
from io import BytesIO
from urllib.error import HTTPError

import pytest

import sfra_web_adapter.github_api as github_api
from sfra_web_adapter import GitHubAPIError, GitHubREST, GitHubCommentStatusStore


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
        self.comments.append({"body": body, "user": {"login": "github-actions[bot]", "type": "Bot"}})


def test_comment_status_store_preserves_first_digest_on_retry_or_changed_body():
    comments = FakeComments()
    store = GitHubCommentStatusStore(comments)
    first = "a" * 64
    changed = "b" * 64
    assert store.bind_request_body_sha256(9, first) == first
    assert len(comments.comments) == 1
    assert store.bind_request_body_sha256(9, first) == first
    assert store.bind_request_body_sha256(9, changed) == first
    assert len(comments.comments) == 1
