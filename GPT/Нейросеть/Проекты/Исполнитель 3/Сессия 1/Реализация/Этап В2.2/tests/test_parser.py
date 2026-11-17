from __future__ import annotations

import hashlib
import json

import pytest

from sfra_issue_core import (
    MAX_BODY_BYTES,
    BodyMaterial,
    IssueRequestError,
    IssueRequestParser,
)
from conftest import body_for, envelope, issue_record


def test_parser_accepts_clean_json_and_hashes_exact_original_utf8_bytes() -> None:
    body = " \n" + body_for(payload={"query": "Проверка контракта"}) + "\n "
    parsed = IssueRequestParser().parse(issue_record(body))

    assert parsed.request_id == "6f2f5b1e-6ab7-4a9e-9c2b-c0c9846c7d14"
    assert parsed.operation == "search_vault"
    assert parsed.payload["query"] == "Проверка контракта"
    assert parsed.request_body_sha256 == "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def test_parser_accepts_exactly_one_fenced_json_block() -> None:
    fence = chr(96) * 3
    body = "\n" + fence + "json\n" + body_for() + "\n" + fence + "\n"

    parsed = IssueRequestParser().parse(issue_record(body))

    assert parsed.operation == "search_vault"


@pytest.mark.parametrize(
    "body",
    [
        "Please run this:\n" + body_for(),
        body_for() + "\nextra text",
        body_for() + "\n" + chr(96) * 3 + "json\n{}\n" + chr(96) * 3,
        chr(96) * 3 + "python\n{}\n" + chr(96) * 3,
        chr(96) * 3 + "json\n{}\n" + chr(96) * 3 + "\nmore",
        "{not-json",
        '{"protocol_version":"sfra.issue.v1","protocol_version":"sfra.issue.v1"}',
    ],
)
def test_parser_rejects_surrounding_text_multiple_blocks_and_malformed_json(body: str) -> None:
    with pytest.raises(IssueRequestError):
        IssueRequestParser().parse(issue_record(body))


def test_parser_rejects_invalid_utf8_and_oversized_body_with_exact_hash() -> None:
    invalid = b"\xff\xfe"
    with pytest.raises(IssueRequestError) as utf8_error:
        IssueRequestParser().parse(issue_record(invalid))
    assert utf8_error.value.code == "invalid_utf8"
    assert utf8_error.value.request_body_sha256 == (
        "sha256:" + hashlib.sha256(invalid).hexdigest()
    )

    oversized = b" " * (MAX_BODY_BYTES + 1)
    with pytest.raises(IssueRequestError) as size_error:
        IssueRequestParser().parse(issue_record(oversized))
    assert size_error.value.code == "body_too_large"
    assert size_error.value.request_body_sha256 == (
        "sha256:" + hashlib.sha256(oversized).hexdigest()
    )


def test_parser_rejects_body_material_when_digest_does_not_match_exact_bytes() -> None:
    raw = b'{"protocol_version":"sfra.issue.v1"}'
    wrong = "sha256:" + "0" * 64
    with pytest.raises(IssueRequestError) as error:
        IssueRequestParser().parse_material(
            issue_record(raw),
            BodyMaterial(raw_bytes=raw, request_body_sha256=wrong),
        )
    assert error.value.code == "invalid_body_hash"


def test_parser_rejects_empty_or_absent_allowlist_fail_closed() -> None:
    for allowlist in (None, (), []):
        with pytest.raises(IssueRequestError) as error:
            IssueRequestParser(allowed_authors=allowlist).parse(issue_record())
        assert error.value.code == "author_not_allowed"


def test_parser_rejects_text_as_allowlist_instead_of_treating_each_character_as_a_login() -> None:
    with pytest.raises(ValueError):
        IssueRequestParser(allowed_authors="yeatu")


@pytest.mark.parametrize(
    ("changes", "expected_code"),
    [
        ({"is_pull_request": True}, "pull_request_not_allowed"),
        ({"repository": "other/repo"}, "wrong_repository"),
        ({"title": "SFRA request"}, "wrong_title_prefix"),
        ({"author": "Yeatu"}, "author_not_allowed"),
        ({"author": "other"}, "author_not_allowed"),
    ],
)
def test_parser_enforces_issue_metadata_exactly(changes: dict, expected_code: str) -> None:
    issue = issue_record(
        is_pull_request=changes.get("is_pull_request", False),
        repository=changes.get("repository", "yeatu/obsidianGP"),
        title=changes.get("title", "[SFRA] test"),
        author=changes.get("author", "yeatu"),
    )
    with pytest.raises(IssueRequestError) as error:
        IssueRequestParser().parse(issue)
    assert error.value.code == expected_code


@pytest.mark.parametrize(
    ("envelope_data", "expected_code"),
    [
        ({**envelope(), "extra": True}, "extra_fields"),
        ({**envelope(), "protocol_version": "sfra.issue.v2"}, "unsupported_protocol"),
        ({**envelope(), "request_id": "not-a-uuid"}, "invalid_request_id"),
        ({**envelope(), "operation": "delete"}, "unsupported_operation"),
        ({**envelope(), "payload": {"query": "x", "unexpected": "field"}}, "extra_fields"),
        ({**envelope(), "payload": {}}, "missing_fields"),
        ({**envelope(), "payload": {"query": "x", "budget_tokens": True}}, "invalid_field"),
        ({**envelope(), "operation": []}, "unsupported_operation"),
    ],
)
def test_parser_rejects_invalid_envelope_and_search_payload(envelope_data: dict, expected_code: str) -> None:
    with pytest.raises(IssueRequestError) as error:
        IssueRequestParser().parse(issue_record(json.dumps(envelope_data)))
    assert error.value.code == expected_code


@pytest.mark.parametrize(
    "payload",
    [
        {"node_id": "node_x", "expected_hash": "sha256:" + "a" * 64, "scope": "document", "other": 1},
        {"node_id": "node_x", "expected_hash": "sha256:bad", "scope": "node"},
        {"node_id": "node_x", "expected_hash": "sha256:" + "a" * 64, "scope": "vault"},
        {"node_id": "node_x", "expected_hash": "sha256:" + "a" * 64, "scope": "node", "budget_tokens": False},
        {"node_id": "node_x", "expected_hash": "sha256:" + "a" * 64, "scope": []},
    ],
)
def test_parser_applies_strict_read_source_payload_schema(payload: dict) -> None:
    with pytest.raises(IssueRequestError):
        IssueRequestParser().parse(issue_record(body_for("read_source", payload)))


def test_parser_rejects_extra_nested_focus_and_known_fields() -> None:
    payload = {
        "query": "find",
        "focus": [{"id": "topic", "label": "Topic", "unexpected": "no"}],
    }
    with pytest.raises(IssueRequestError) as focus_error:
        IssueRequestParser().parse(issue_record(body_for(payload=payload)))
    assert focus_error.value.code == "extra_fields"

    payload = {
        "query": "find",
        "known": [{"node_id": "node_x", "content_hash": "sha256:" + "a" * 64, "text": "no"}],
    }
    with pytest.raises(IssueRequestError) as known_error:
        IssueRequestParser().parse(issue_record(body_for(payload=payload)))
    assert known_error.value.code == "extra_fields"
