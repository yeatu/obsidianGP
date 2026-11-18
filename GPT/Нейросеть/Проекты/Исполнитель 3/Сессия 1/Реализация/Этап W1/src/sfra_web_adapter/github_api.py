"""Small GitHub REST client. Never logs request/response bodies or credentials."""
from __future__ import annotations
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

class GitHubAPIError(RuntimeError):
    """Sanitized GitHub API failure; response bodies are deliberately omitted."""

class GitHubREST:
    def __init__(self, *, token: str, repository: str, api_url: str = "https://api.github.com"):
        if not isinstance(token, str) or not token:
            raise ValueError("GitHub token is required")
        if repository != "yeatu/obsidianGP":
            raise ValueError("repository is not allowlisted")
        if api_url.rstrip("/") != "https://api.github.com":
            raise ValueError("only the approved GitHub API endpoint is supported")
        self._token = token
        self._repository = repository
        self._api = api_url.rstrip("/")

    def _request(self, method: str, path: str, payload: object | None = None) -> Any:
        data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = Request(self._api + path, data=data, method=method, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + self._token,
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        })
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise GitHubAPIError("GitHub API response exceeded the 1 MiB limit")
                return json.loads(raw.decode("utf-8")) if raw else None
        except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubAPIError("GitHub API request failed") from exc

    def get_issue(self, issue_number: int) -> dict[str, object]:
        if isinstance(issue_number, bool) or not isinstance(issue_number, int) or issue_number < 1:
            raise ValueError("issue_number must be positive")
        result = self._request("GET", f"/repos/{self._repository}/issues/{issue_number}")
        if not isinstance(result, dict):
            raise GitHubAPIError("GitHub Issue response has an invalid shape")
        return result

    def list_comments(self, issue_number: int) -> list[dict[str, object]]:
        result = self._request("GET", f"/repos/{self._repository}/issues/{issue_number}/comments?per_page=100")
        if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
            raise GitHubAPIError("GitHub comments response has an invalid shape")
        if len(result) == 100:
            raise GitHubAPIError("Issue comment history exceeds the supported single-page limit")
        return result

    def create_comment(self, issue_number: int, body: str) -> None:
        if not isinstance(body, str) or not body or len(body.encode("utf-8")) > 45 * 1024:
            raise ValueError("comment body is empty or exceeds 45 KiB")
        self._request("POST", f"/repos/{self._repository}/issues/{issue_number}/comments", {"body": body})
