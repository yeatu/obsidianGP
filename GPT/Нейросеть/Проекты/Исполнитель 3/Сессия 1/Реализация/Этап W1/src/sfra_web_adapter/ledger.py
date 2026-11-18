"""Comment-backed immutable body binding and retry/idempotency decisions."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import re
from typing import Iterable, Mapping

MARKER_AUTHOR = "github-actions[bot]"
_MARKER = re.compile(r"^<!-- sfra-web-v1 issue=(?P<issue>[1-9][0-9]*) body_sha256=(?P<digest>[0-9a-f]{64}) state=(?P<state>STARTED|COMPLETED|REJECTED|FAILED) -->$")
_STATES = frozenset({"STARTED", "COMPLETED", "REJECTED", "FAILED"})

def body_sha256(body: bytes) -> str:
    if not isinstance(body, bytes):
        raise TypeError("body must be exact bytes")
    return hashlib.sha256(body).hexdigest()

@dataclass(frozen=True, slots=True)
class MarkerRecord:
    issue_number: int
    body_sha256: str
    state: str

@dataclass(frozen=True, slots=True)
class LedgerDecision:
    action: str
    body_sha256: str
    marker: str | None
    reason: str

def authenticated_markers(issue_number: int,
                          comments: Iterable[Mapping[str, object]]) -> tuple[MarkerRecord, ...]:
    """Parse only markers authored by the exact GitHub Actions bot identity."""
    records: list[MarkerRecord] = []
    for comment in comments:
        user = comment.get("user")
        if not isinstance(user, Mapping) or user.get("login") != MARKER_AUTHOR:
            continue
        text = comment.get("body")
        if not isinstance(text, str):
            continue
        for line in text.splitlines():
            match = _MARKER.fullmatch(line.strip())
            if match and int(match.group("issue")) == issue_number:
                records.append(MarkerRecord(
                    issue_number=issue_number,
                    body_sha256=match.group("digest"),
                    state=match.group("state"),
                ))
    return tuple(records)

class MarkerLedger:
    """Interpret only bot-authored durable markers; serialize each Issue in caller."""
    def inspect(self, issue_number: int, body: bytes,
                comments: Iterable[Mapping[str, object]]) -> LedgerDecision:
        if isinstance(issue_number, bool) or not isinstance(issue_number, int) or issue_number < 1:
            raise ValueError("issue_number must be a positive integer")
        digest = body_sha256(body)
        observed = authenticated_markers(issue_number, comments)
        if not observed:
            return LedgerDecision("START", digest, self._marker(issue_number, digest, "STARTED"), "first_observation")
        first_digest = observed[0].body_sha256
        if any(item.body_sha256 != first_digest for item in observed):
            return LedgerDecision("REJECT", digest, None, "ledger_conflict")
        if first_digest != digest:
            return LedgerDecision("REJECT", digest, self._marker(issue_number, digest, "REJECTED"), "request_body_changed")
        states = [item.state for item in observed]
        if "COMPLETED" in states:
            return LedgerDecision("SKIP", digest, None, "already_completed")
        if "REJECTED" in states or "FAILED" in states:
            return LedgerDecision("SKIP", digest, None, "terminal_state")
        if "STARTED" in states:
            return LedgerDecision("RETRY", digest, None, "interrupted_or_retried")
        return LedgerDecision("REJECT", digest, None, "unknown_ledger_state")

    @staticmethod
    def _marker(issue_number: int, digest: str, state: str) -> str:
        if state not in _STATES:
            raise ValueError("unsupported ledger state")
        return f"<!-- sfra-web-v1 issue={issue_number} body_sha256={digest} state={state} -->"
