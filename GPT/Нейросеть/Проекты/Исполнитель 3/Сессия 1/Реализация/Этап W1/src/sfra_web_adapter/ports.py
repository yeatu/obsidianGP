"""Adapters from GitHub Issue/comment REST to the transport-neutral V2.2 ports."""
from __future__ import annotations
from typing import Mapping
from sfra_issue_core import IssueRecord, TransportStatusV2
from .github_api import GitHubREST
from .ledger import MARKER_AUTHOR, MarkerLedger

class GitHubIssueReader:
    def __init__(self, client: GitHubREST):
        self._client = client

    def read_issue(self, issue_number: int) -> IssueRecord:
        raw = self._client.get_issue(issue_number)
        user = raw.get("user")
        if not isinstance(user, Mapping):
            author = ""
        else:
            author = user.get("login", "")
        return IssueRecord(
            number=raw.get("number"),
            title=raw.get("title"),
            repository_full_name="yeatu/obsidianGP",
            author_login=author,
            body=raw.get("body"),
            is_pull_request="pull_request" in raw,
        )

class GitHubCommentStatusStore:
    """Persist first-seen hash markers only when authored by the Actions bot."""
    def __init__(self, client: GitHubREST):
        self._client = client
        self._statuses: dict[int, TransportStatusV2] = {}

    def bind_request_body_sha256(self, issue_number: int, digest: str) -> str:
        comments = self._client.list_comments(issue_number)
        observed: list[str] = []
        for comment in comments:
            user = comment.get("user")
            if not isinstance(user, Mapping) or user.get("login") != MARKER_AUTHOR:
                continue
            body = comment.get("body")
            if not isinstance(body, str):
                continue
            for line in body.splitlines():
                import re
                match = re.fullmatch(
                    r"<!-- sfra-web-v1 issue=([1-9][0-9]*) body_sha256=([0-9a-f]{64}) state=(STARTED|COMPLETED|REJECTED|FAILED) -->",
                    line.strip(),
                )
                if match and int(match.group(1)) == issue_number:
                    observed.append(match.group(2))
        if not observed:
            marker = MarkerLedger._marker(issue_number, digest, "STARTED")
            self._client.create_comment(issue_number, marker)
            return digest
        if any(item != observed[0] for item in observed):
            return "0" * 64
        return observed[0]

    def put_status(self, status: TransportStatusV2) -> None:
        if not isinstance(status, TransportStatusV2):
            raise TypeError("status store accepts TransportStatusV2 only")
        self._statuses[status.issue_number] = status

    def get_status(self, issue_number: int) -> TransportStatusV2 | None:
        return self._statuses.get(issue_number)
