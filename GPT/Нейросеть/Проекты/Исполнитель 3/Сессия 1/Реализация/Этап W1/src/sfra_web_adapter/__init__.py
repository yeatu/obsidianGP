"""Synthetic-only GitHub Issues/Actions transport adapter for SFRA W1."""

from .event_gate import EventGateDecision, inspect_issues_opened_event
from .handler import WebAdapterOutcome, handle_issues_opened
from .status_store import GitHubCommentStatusStore, StartDisposition

__all__ = [
    "EventGateDecision",
    "inspect_issues_opened_event",
    "WebAdapterOutcome",
    "handle_issues_opened",
    "GitHubCommentStatusStore",
    "StartDisposition",
]
