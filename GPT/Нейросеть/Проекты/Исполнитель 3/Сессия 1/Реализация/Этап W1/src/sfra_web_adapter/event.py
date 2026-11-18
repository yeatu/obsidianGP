"""Fail-closed gate for owner-authored issues.opened request events."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
from typing import Mapping

EXPECTED_REPOSITORY = "yeatu/obsidianGP"
EXPECTED_AUTHOR = "yeatu"
TITLE_PREFIX = "[SFRA]"
MAX_BODY_BYTES = 32 * 1024

class EventRejection(ValueError):
    """An event is not an authorized SFRA request."""

@dataclass(frozen=True, slots=True)
class OpenedIssueRequest:
    issue_number: int
    repository: str
    author: str
    title: str
    body: bytes
    body_sha256: str

def parse_opened_issue_event(payload: Mapping[str, object], *, event_name: str,
                              action: str, allowed_author: str = EXPECTED_AUTHOR,
                              expected_repository: str = EXPECTED_REPOSITORY) -> OpenedIssueRequest:
    """Validate event metadata and bind exact UTF-8 body bytes."""
    if event_name != "issues" or action != "opened":
        raise EventRejection("unsupported_event")
    repository, issue, sender = payload.get("repository"), payload.get("issue"), payload.get("sender")
    if not isinstance(repository, Mapping) or not isinstance(issue, Mapping):
        raise EventRejection("invalid_event_shape")
    full_name = repository.get("full_name")
    if full_name != expected_repository:
        raise EventRejection("wrong_repository")
    if "pull_request" in issue:
        raise EventRejection("pull_request_not_allowed")
    number = issue.get("number")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise EventRejection("invalid_issue_number")
    title = issue.get("title")
    if not isinstance(title, str) or not title.startswith(TITLE_PREFIX):
        raise EventRejection("wrong_title_prefix")
    user = issue.get("user")
    if not isinstance(user, Mapping) or user.get("login") != allowed_author:
        raise EventRejection("author_not_allowed")
    if not isinstance(sender, Mapping) or sender.get("login") != allowed_author:
        raise EventRejection("sender_not_allowed")
    raw_body = issue.get("body")
    if raw_body is None:
        body = b""
    elif isinstance(raw_body, str):
        try:
            body = raw_body.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise EventRejection("invalid_utf8") from exc
    else:
        raise EventRejection("invalid_body_type")
    if len(body) > MAX_BODY_BYTES:
        raise EventRejection("body_too_large")
    return OpenedIssueRequest(number, full_name, allowed_author, title, body,
                              hashlib.sha256(body).hexdigest())
