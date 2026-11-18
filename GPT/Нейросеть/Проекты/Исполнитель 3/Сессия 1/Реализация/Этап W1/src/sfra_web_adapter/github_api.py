"""Small GitHub REST port for the W1 transport boundary.

The adapter deliberately returns bounded error codes and never includes
request/response bodies, headers, tokens or exception strings in diagnostics.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import os
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from sfra_issue_core.models import IssueRecord


class GitHubApiError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class GitHubApiPort(Protocol):
    def get_issue(self, issue_number: int) -> Mapping[str, object]: ...
    def list_issue_comments(self, issue_number: int) -> Sequence[Mapping[str, object]]: ...
    def create_issue_comment(self, issue_number: int, body: str) -> Mapping[str, object]: ...
    def update_issue_comment(self, comment_id: int, body: str) -> Mapping[str, object]: ...


class GitHubApiClient:
    """Minimal token-authenticated REST client; no arbitrary URLs are accepted."""

    def __init__(
        self,
        *,
        token: str,
        repository_full_name: str,
        api_url: str = "https://api.github.com",
        timeout_seconds: float = 15.0,
    ) -> None:
        if not token or "\n" in token or "\r" in token:
            raise ValueError("GitHub token is required")
        if repository_full_name != "yeatu/obsidianGP":
            raise ValueError("repository is not allowlisted")
        self._token = token
        self._repository = repository_full_name
        self._api_url = api_url.rstrip("/")
        self._timeout = timeout_seconds

    @classmethod
    def from_environment(cls) -> "GitHubApiClient":
        token = os.environ.get("GITHUB_TOKEN", "")
        repository = os.environ.get("GITHUB_REPOSITORY", "")
        api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        return cls(token=token, repository_full_name=repository, api_url=api_url)

    def _request(self, method: str, path: str, payload: object | None = None) -> object:
        url = f"{self._api_url}{path}"
        data = None if payload is None else json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "sfra-web-adapter-w1",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self._timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            code = "github_rate_limited" if exc.code == 403 else "github_http_error"
            raise GitHubApiError(code) from None
        except (URLError, TimeoutError, OSError):
            raise GitHubApiError("github_transport_error") from None
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GitHubApiError("github_invalid_response") from None

    def _repo_path(self) -> str:
        return "/repos/" + quote(self._repository, safe="/")

    def get_issue(self, issue_number: int) -> Mapping[str, object]:
        value = self._request("GET", f"{self._repo_path()}/issues/{issue_number}")
        if not isinstance(value, Mapping):
            raise GitHubApiError("github_invalid_issue")
        return value

    def list_issue_comments(self, issue_number: int) -> Sequence[Mapping[str, object]]:
        items: list[Mapping[str, object]] = []
        for page in range(1, 11):
            value = self._request(
                "GET",
                f"{self._repo_path()}/issues/{issue_number}/comments?per_page=100&page={page}",
            )
            if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
                raise GitHubApiError("github_invalid_comments")
            items.extend(value)
            if len(value) < 100:
                return tuple(items)
        raise GitHubApiError("github_comment_page_limit")

    def create_issue_comment(self, issue_number: int, body: str) -> Mapping[str, object]:
        value = self._request(
            "POST",
            f"{self._repo_path()}/issues/{issue_number}/comments",
            {"body": body},
        )
        if not isinstance(value, Mapping) or not isinstance(value.get("id"), int):
            raise GitHubApiError("github_invalid_comment_response")
        return value

    def update_issue_comment(self, comment_id: int, body: str) -> Mapping[str, object]:
        value = self._request(
            "PATCH",
            f"{self._repo_path()}/issues/comments/{comment_id}",
            {"body": body},
        )
        if not isinstance(value, Mapping) or value.get("id") != comment_id:
            raise GitHubApiError("github_invalid_comment_response")
        return value


class GitHubIssueReaderPort:
    """Adapt the existing V2.2 IssueReaderPort to the GitHub REST client."""

    def __init__(self, api: GitHubApiPort, repository_full_name: str) -> None:
        if repository_full_name != "yeatu/obsidianGP":
            raise ValueError("repository is not allowlisted")
        self._api = api
        self._repository = repository_full_name

    def read_issue(self, issue_number: int) -> IssueRecord:
        value = self._api.get_issue(issue_number)
        user = value.get("user")
        if not isinstance(user, Mapping):
            raise GitHubApiError("github_invalid_issue")
        author = user.get("login")
        title = value.get("title")
        body = value.get("body")
        number = value.get("number")
        pull_request = "pull_request" in value
        if (
            isinstance(number, bool)
            or not isinstance(number, int)
            or not isinstance(title, str)
            or not isinstance(author, str)
            or (body is not None and not isinstance(body, str))
        ):
            raise GitHubApiError("github_invalid_issue")
        return IssueRecord(
            number=number,
            title=title,
            repository_full_name=self._repository,
            author_login=author,
            body=body,
            is_pull_request=pull_request,
        )
