"""Adapters from GitHub Issue/comment REST to the transport-neutral V2.2 ports."""
from __future__ import annotations
import re
from typing import Mapping
from sfra_issue_core import IssueRecord, TransportStatusV2
from .github_api import GitHubREST
from .ledger import MarkerLedger

_MARKER = re.compile(r"^<!-- sfra-web-v1 issue=([1-9][0-9]*) body_sha256=([0-9a-f]{64}) state=(STARTED|COMPLETED|REJECTED|FAILED) -->$")

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
        repository = raw.get("repository_url")
        # REST issue payloads do not normally include repository.full_name;
        # repository identity is fixed by the allowlisted client constructor.
        return IssueRecord(
            number=raw.get("number"),
            title=raw.get("title"),
            repository_full_name="yeatu/obsidianGP",
            author_login=author,
            body=raw.get("body"),
            is_pull_request="pull_request" in raw,
        )

class GitHubCommentStatusStore:
    """Persist only first-seen hash markers; final safe status is rendered by handler."""
    def __init__(self, client: GitHubREST):
        self._client = client
        self._statuses: dict[int, TransportStatusV2] = {}

    def bind_request_body_sha256(self, issue_number: int, digest: str) -> str:
        comments = self._client.list_comments(issue_number)
        observed: list[str] = []
        for comment in comments:
            body = comment.get("body")
            if not isinstance(body, str):
                continue
            for line in body.splitlines():
                match = _MARKER.fullmatch(line.strip())
                if match and int(match.group(1)) == issue_number:
                    observed.append(match.group(2))
        if not observed:
            marker = MarkerLedger._marker(issue_number, digest, "STARTED")
            self._client.create_comment(issue_number, marker)
            return digest
        # Preserve the first immutable binding. Conflicting histories are
        # returned as a deliberately impossible digest so the core fails closed.
        if any(item != observed[0] for item in observed):
            return "0" * 64
        return observed[0]

    def put_status(self, status: TransportStatusV2) -> None:
        if not isinstance(status, TransportStatusV2):
            raise TypeError("status store accepts TransportStatusV2 only")
        self._statuses[status.issue_number] = status

    def get_status(self, issue_number: int) -> TransportStatusV2 | None:
        return self._statuses.get(issue_number)
