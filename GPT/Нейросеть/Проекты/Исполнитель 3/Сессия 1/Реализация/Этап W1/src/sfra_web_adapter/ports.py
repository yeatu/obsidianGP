"""Adapters from GitHub Issue/comment REST to the transport-neutral V2.2 ports."""
from __future__ import annotations
from typing import Mapping
import re
from sfra_issue_core import IssueRecord, TransportStatusV2
from .github_api import GitHubREST
from .ledger import MarkerLedger, authenticated_markers

_V2_BODY_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

class GitHubIssueReader:
    def __init__(self, client: GitHubREST):
        self._client = client

    def read_issue(self, issue_number: int) -> IssueRecord:
        raw = self._client.get_issue(issue_number)
        user = raw.get("user")
        author = user.get("login", "") if isinstance(user, Mapping) else ""
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
        """Bind a V2.2 prefixed digest to the marker ledger's bare-hex format.

        The V2.2 core contract is `sha256:<64 lowercase hex>`; W1's durable
        marker format intentionally remains bare 64-character lowercase hex.
        This is the sole conversion boundary between those representations.
        """
        if not isinstance(digest, str) or not _V2_BODY_SHA256_RE.fullmatch(digest):
            raise ValueError("request body digest must be sha256:<64 lowercase hex>")
        bare_digest = digest.removeprefix("sha256:")
        comments = self._client.list_comments(issue_number)
        observed = authenticated_markers(issue_number, comments)
        if not observed:
            marker = MarkerLedger._marker(issue_number, bare_digest, "STARTED")
            self._client.create_comment(issue_number, marker)
            return digest
        first_digest = observed[0].body_sha256
        if any(item.body_sha256 != first_digest for item in observed):
            # Return a different, still well-formed V2.2 digest so the core's
            # exact comparison fails closed without leaking marker contents.
            sentinel = "1" * 64 if bare_digest == "0" * 64 else "0" * 64
            return "sha256:" + sentinel
        return "sha256:" + first_digest

    def put_status(self, status: TransportStatusV2) -> None:
        if not isinstance(status, TransportStatusV2):
            raise TypeError("status store accepts TransportStatusV2 only")
        self._statuses[status.issue_number] = status

    def get_status(self, issue_number: int) -> TransportStatusV2 | None:
        return self._statuses.get(issue_number)
