"""Fail-closed gate for the single supported GitHub event: issues.opened."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

EXPECTED_REPOSITORY = "yeatu/obsidianGP"
REQUEST_TITLE_MARKER = "[SFRA] [W1] "
DEFAULT_ALLOWED_ACTORS = ("yeatu",)


@dataclass(frozen=True, slots=True)
class EventGateDecision:
    accepted: bool
    reason: str
    issue_number: int | None = None
    title: str | None = None
    author_login: str | None = None
    sender_login: str | None = None
    body: str | None = None


def inspect_issues_opened_event(
    payload: object,
    *,
    repository_full_name: str,
    allowed_actors: tuple[str, ...] = DEFAULT_ALLOWED_ACTORS,
) -> EventGateDecision:
    """Accept only an owner-authored W1 marker issue from the approved repository.

    Non-W1 issues and every event other than issues.opened are ignored. A
    marker-bearing issue with unexpected repository/actor/shape is rejected.
    The Issue body is returned unchanged and is never logged or interpolated
    into an operational error.
    """
    if not isinstance(payload, Mapping):
        return EventGateDecision(False, "invalid_event")
    if payload.get("action") != "opened":
        return EventGateDecision(False, "unsupported_event", )
    repository = payload.get("repository")
    sender = payload.get("sender")
    issue = payload.get("issue")
    if not isinstance(issue, Mapping):
        return EventGateDecision(False, "invalid_event")
    title = issue.get("title")
    if not isinstance(title, str) or not title.startswith(REQUEST_TITLE_MARKER):
        return EventGateDecision(False, "not_w1_request")
    if repository_full_name != EXPECTED_REPOSITORY:
        return EventGateDecision(False, "wrong_runtime_repository")
    if not isinstance(repository, Mapping) or repository.get("full_name") != EXPECTED_REPOSITORY:
        return EventGateDecision(False, "wrong_event_repository")
    if not isinstance(sender, Mapping) or not isinstance(sender.get("login"), str):
        return EventGateDecision(False, "unauthorized_sender")
    user = issue.get("user")
    if not isinstance(user, Mapping) or not isinstance(user.get("login"), str):
        return EventGateDecision(False, "unauthorized_author")
    sender_login = sender["login"]
    author_login = user["login"]
    if not allowed_actors or sender_login not in allowed_actors or author_login not in allowed_actors:
        return EventGateDecision(False, "unauthorized_actor")
    number = issue.get("number")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        return EventGateDecision(False, "invalid_issue_number")
    if "pull_request" in issue:
        return EventGateDecision(False, "pull_request_not_allowed")
    body = issue.get("body")
    if body is not None and not isinstance(body, str):
        return EventGateDecision(False, "invalid_body_type")
    return EventGateDecision(
        True,
        "accepted",
        issue_number=number,
        title=title,
        author_login=author_login,
        sender_login=sender_login,
        body=body,
    )
