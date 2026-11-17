"""Strict parser and validator for the sfra.issue.v1 Issue-body envelope."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any
import uuid

from .models import BodyMaterial, IssueRecord, IssueRequestError, ParsedIssueRequest

MAX_BODY_BYTES = 32 * 1024
EXPECTED_REPOSITORY = "yeatu/obsidianGP"
TITLE_PREFIX = "[SFRA]"
DEFAULT_AUTHOR_ALLOWLIST = ("yeatu",)

_CONTENT_HASH_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_FENCED_JSON_RE = re.compile(
    r"\A\s*\x60{3}json[ \t]*\r?\n(?P<json>.*?)\r?\n\x60{3}[ \t]*\s*\Z",
    re.DOTALL,
)


class _DuplicateJSONKey(ValueError):
    pass


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKey(key)
        result[key] = value
    return result


def _reject_non_json_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def _expect_object(
    value: object,
    *,
    required: set[str],
    allowed: set[str],
    path: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise IssueRequestError("invalid_payload", f"{path} must be an object")
    keys = set(value.keys())
    if any(not isinstance(key, str) for key in keys):
        raise IssueRequestError("invalid_payload", f"{path} keys must be strings")
    if not required.issubset(keys):
        missing = sorted(required - keys)
        raise IssueRequestError("missing_fields", f"{path} is missing required fields: {missing}")
    if not keys.issubset(allowed):
        extra = sorted(str(item) for item in keys - allowed)
        raise IssueRequestError("extra_fields", f"{path} contains unsupported fields: {extra}")
    return value


def _string(value: object, path: str, *, non_empty: bool = True) -> str:
    if not isinstance(value, str) or (non_empty and not value.strip()):
        raise IssueRequestError("invalid_field", f"{path} must be a non-empty string")
    return value


def _string_array(value: object, path: str) -> list[str]:
    if not isinstance(value, list):
        raise IssueRequestError("invalid_field", f"{path} must be an array")
    return [_string(item, f"{path}[{index}]") for index, item in enumerate(value)]


def _positive_int(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise IssueRequestError("invalid_field", f"{path} must be an integer >= 1")
    return value


@dataclass(frozen=True, slots=True)
class IssueRequestParser:
    """Validate Issue metadata, exact UTF-8 body bytes, envelope and payload."""

    allowed_authors: Sequence[str] | None = DEFAULT_AUTHOR_ALLOWLIST

    def __post_init__(self) -> None:
        if isinstance(self.allowed_authors, (str, bytes)):
            raise ValueError("allowed_authors must be a sequence of exact login values, not text")
        values = tuple(self.allowed_authors or ())
        if any(not isinstance(item, str) or not item or item.strip() != item for item in values):
            raise ValueError("allowed_authors must contain exact non-empty login strings")
        object.__setattr__(self, "allowed_authors", values)

    @staticmethod
    def body_material(body: object) -> BodyMaterial:
        if body is None:
            raw = b""
        elif isinstance(body, bytes):
            raw = body
        elif isinstance(body, str):
            try:
                raw = body.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise IssueRequestError(
                    "invalid_utf8", "Issue body cannot be encoded as strict UTF-8"
                ) from exc
        else:
            raise IssueRequestError("invalid_body_type", "Issue body must be text, bytes or null")
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        return BodyMaterial(raw_bytes=raw, request_body_sha256=digest)

    def validate_issue_metadata(self, issue: object) -> IssueRecord:
        if not isinstance(issue, IssueRecord):
            raise IssueRequestError("invalid_issue_record", "Issue reader must return IssueRecord")
        if isinstance(issue.number, bool) or not isinstance(issue.number, int) or issue.number < 1:
            raise IssueRequestError("invalid_issue_number", "Issue number must be a positive integer")
        if issue.is_pull_request is not False:
            raise IssueRequestError("pull_request_not_allowed", "Pull Requests are not SFRA Issues")
        if issue.repository_full_name != EXPECTED_REPOSITORY:
            raise IssueRequestError("wrong_repository", "Issue belongs to an unapproved repository")
        if not isinstance(issue.title, str) or not issue.title.startswith(TITLE_PREFIX):
            raise IssueRequestError("wrong_title_prefix", "Issue title must start with [SFRA]")
        if not isinstance(issue.author_login, str):
            raise IssueRequestError("author_not_allowed", "Issue author is not authorized")
        if not self.allowed_authors or issue.author_login not in self.allowed_authors:
            raise IssueRequestError("author_not_allowed", "Issue author is not on the exact allowlist")
        return issue

    def parse_material(
        self,
        issue: IssueRecord,
        material: BodyMaterial,
    ) -> ParsedIssueRequest:
        digest = material.request_body_sha256
        if not isinstance(material.raw_bytes, bytes):
            raise IssueRequestError(
                "invalid_body_type", "BodyMaterial.raw_bytes must be bytes",
                request_body_sha256=digest,
            )
        expected_digest = "sha256:" + hashlib.sha256(material.raw_bytes).hexdigest()
        if digest != expected_digest:
            raise IssueRequestError(
                "invalid_body_hash", "BodyMaterial digest does not match exact body bytes",
                request_body_sha256=expected_digest,
            )
        if len(material.raw_bytes) > MAX_BODY_BYTES:
            raise IssueRequestError(
                "body_too_large",
                "Issue body exceeds the 32 KiB UTF-8 limit",
                request_body_sha256=digest,
            )
        try:
            body = material.raw_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise IssueRequestError(
                "invalid_utf8", "Issue body is not valid UTF-8", request_body_sha256=digest
            ) from exc

        candidate = body
        if body.lstrip().startswith("\x60\x60\x60"):
            match = _FENCED_JSON_RE.fullmatch(body)
            if match is None:
                raise IssueRequestError(
                    "invalid_json_envelope",
                    "Body must contain exactly one fenced json block and no surrounding text",
                    request_body_sha256=digest,
                )
            candidate = match.group("json")

        try:
            envelope = json.loads(
                candidate,
                object_pairs_hook=_object_without_duplicate_keys,
                parse_constant=_reject_non_json_constant,
            )
        except (_DuplicateJSONKey, json.JSONDecodeError, ValueError) as exc:
            raise IssueRequestError(
                "invalid_json",
                "Issue body does not contain one strict JSON value",
                request_body_sha256=digest,
            ) from exc

        if not isinstance(envelope, dict):
            raise IssueRequestError(
                "invalid_envelope", "JSON envelope must be an object",
                request_body_sha256=digest,
            )

        try:
            checked = _expect_object(
                envelope,
                required={"protocol_version", "request_id", "operation", "payload"},
                allowed={"protocol_version", "request_id", "operation", "payload"},
                path="envelope",
            )
            if checked.get("protocol_version") != "sfra.issue.v1":
                raise IssueRequestError("unsupported_protocol", "Unsupported protocol version")
            request_id = checked.get("request_id")
            if not isinstance(request_id, str) or not _UUID4_RE.fullmatch(request_id):
                raise IssueRequestError("invalid_request_id", "request_id must be a canonical UUID v4")
            try:
                parsed_uuid = uuid.UUID(request_id)
            except ValueError as exc:
                raise IssueRequestError("invalid_request_id", "request_id must be a UUID v4") from exc
            if parsed_uuid.version != 4:
                raise IssueRequestError("invalid_request_id", "request_id must be a UUID v4")
            operation = checked.get("operation")
            if not isinstance(operation, str) or operation not in {"search_vault", "read_source"}:
                raise IssueRequestError("unsupported_operation", "Unsupported SFRA operation")
            payload = self._validate_payload(operation, checked.get("payload"))
        except IssueRequestError as exc:
            raise IssueRequestError(
                exc.code,
                str(exc),
                request_body_sha256=digest,
            ) from exc

        return ParsedIssueRequest(
            issue_number=issue.number,
            request_id=request_id,
            operation=operation,
            payload=MappingProxyType(dict(payload)),
            request_body_sha256=digest,
        )

    def parse(self, issue: IssueRecord) -> ParsedIssueRequest:
        material = self.body_material(issue.body)
        self.validate_issue_metadata(issue)
        return self.parse_material(issue, material)

    @staticmethod
    def _validate_payload(operation: str, value: object) -> Mapping[str, object]:
        if operation == "search_vault":
            payload = _expect_object(
                value,
                required={"query"},
                allowed={
                    "query", "task", "entities", "facets", "budget_tokens",
                    "known", "zones", "focus",
                },
                path="payload",
            )
            normalized: dict[str, object] = {
                "query": _string(payload.get("query"), "payload.query"),
            }
            if "task" in payload:
                normalized["task"] = _string(payload["task"], "payload.task", non_empty=False)
            for field in ("entities", "facets", "zones"):
                if field in payload:
                    normalized[field] = _string_array(payload[field], f"payload.{field}")
            if "budget_tokens" in payload:
                normalized["budget_tokens"] = _positive_int(
                    payload["budget_tokens"], "payload.budget_tokens"
                )
            if "known" in payload:
                known = payload["known"]
                if not isinstance(known, list):
                    raise IssueRequestError("invalid_field", "payload.known must be an array")
                normalized_known: list[dict[str, str]] = []
                for index, item in enumerate(known):
                    entry = _expect_object(
                        item,
                        required={"node_id", "content_hash"},
                        allowed={"node_id", "content_hash"},
                        path=f"payload.known[{index}]",
                    )
                    node_id = _string(entry.get("node_id"), f"payload.known[{index}].node_id")
                    content_hash = entry.get("content_hash")
                    if not isinstance(content_hash, str) or not _CONTENT_HASH_RE.fullmatch(content_hash):
                        raise IssueRequestError(
                            "invalid_field",
                            f"payload.known[{index}].content_hash is malformed",
                        )
                    normalized_known.append({
                        "node_id": node_id,
                        "content_hash": content_hash.lower(),
                    })
                normalized["known"] = normalized_known
            if "focus" in payload:
                focus = payload["focus"]
                if not isinstance(focus, list):
                    raise IssueRequestError("invalid_field", "payload.focus must be an array")
                normalized_focus: list[object] = []
                for index, item in enumerate(focus):
                    if isinstance(item, str):
                        normalized_focus.append(_string(item, f"payload.focus[{index}]"))
                        continue
                    entry = _expect_object(
                        item,
                        required={"id", "label"},
                        allowed={"id", "label", "entities", "facets", "terms", "match_mode"},
                        path=f"payload.focus[{index}]",
                    )
                    item_result: dict[str, object] = {
                        "id": _string(entry.get("id"), f"payload.focus[{index}].id"),
                        "label": _string(entry.get("label"), f"payload.focus[{index}].label"),
                    }
                    for field in ("entities", "facets", "terms"):
                        if field in entry:
                            item_result[field] = _string_array(
                                entry[field], f"payload.focus[{index}].{field}"
                            )
                    if "match_mode" in entry:
                        match_mode = entry["match_mode"]
                        if not isinstance(match_mode, str) or match_mode not in {"any", "all"}:
                            raise IssueRequestError(
                                "invalid_field",
                                f"payload.focus[{index}].match_mode must be any or all",
                            )
                        item_result["match_mode"] = match_mode
                    normalized_focus.append(item_result)
                normalized["focus"] = normalized_focus
            return normalized

        payload = _expect_object(
            value,
            required={"node_id", "expected_hash", "scope"},
            allowed={"node_id", "expected_hash", "scope", "budget_tokens"},
            path="payload",
        )
        node_id = _string(payload.get("node_id"), "payload.node_id")
        expected_hash = payload.get("expected_hash")
        if not isinstance(expected_hash, str) or not _CONTENT_HASH_RE.fullmatch(expected_hash):
            raise IssueRequestError("invalid_field", "payload.expected_hash is malformed")
        scope = payload.get("scope")
        if not isinstance(scope, str) or scope not in {"node", "parent", "neighbors", "document"}:
            raise IssueRequestError("invalid_field", "payload.scope is unsupported")
        normalized_read: dict[str, object] = {
            "node_id": node_id,
            "expected_hash": expected_hash.lower(),
            "scope": scope,
        }
        if "budget_tokens" in payload:
            budget = payload["budget_tokens"]
            if budget is not None:
                budget = _positive_int(budget, "payload.budget_tokens")
            normalized_read["budget_tokens"] = budget
        return normalized_read
