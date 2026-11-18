from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass

import pytest

from sfra_context_builder.models import SnapshotRef
from sfra_context_integrations import ApplicationServiceError, ReadSourceRequest
from sfra_mcp_server.read_source_contract import parse_read_source_request


def valid_payload() -> dict[str, object]:
    vault = "a" * 40
    sidecar = "b" * 40
    manifest = "sha256:" + "c" * 64
    return {
        "node_id": "node_00000000-0000-4000-8000-000000000001",
        "expected_hash": "sha256:" + "d" * 64,
        "scope": "node",
        "snapshot": {
            "vault_commit_sha": vault,
            "sidecar_commit_sha": sidecar,
            "manifest_sha256": manifest,
        },
    }


def test_parses_minimal_request_and_recomputes_snapshot_identity() -> None:
    request = parse_read_source_request(valid_payload())

    assert isinstance(request, ReadSourceRequest)
    assert request.node_id == "node_00000000-0000-4000-8000-000000000001"
    assert request.scope == "node"
    assert request.budget_tokens is None
    assert isinstance(request.snapshot, SnapshotRef)
    assert request.snapshot.snapshot_id == (
        "a" * 40 + ":" + "b" * 40 + ":sha256:" + "c" * 64
    )


@pytest.mark.parametrize("scope", ["node", "parent", "neighbors", "document"])
def test_accepts_exact_supported_scopes(scope: str) -> None:
    payload = valid_payload()
    payload["scope"] = scope
    assert parse_read_source_request(payload).scope == scope


def test_accepts_exact_derived_snapshot_id_assertion_and_budget() -> None:
    payload = valid_payload()
    snapshot = dict(payload["snapshot"])
    snapshot["snapshot_id"] = (
        "a" * 40 + ":" + "b" * 40 + ":sha256:" + "c" * 64
    )
    payload["snapshot"] = snapshot
    payload["budget_tokens"] = 1200

    request = parse_read_source_request(payload)

    assert request.snapshot.snapshot_id == snapshot["snapshot_id"]
    assert request.budget_tokens == 1200


def test_accepts_explicit_null_budget() -> None:
    payload = valid_payload()
    payload["budget_tokens"] = None
    assert parse_read_source_request(payload).budget_tokens is None


@pytest.mark.parametrize(
    ("field", "bad_value", "error_code"),
    [
        ("node_id", "", "invalid_node_id"),
        ("node_id", None, "invalid_node_id"),
        ("expected_hash", "sha256:" + "A" * 64, "invalid_content_hash"),
        ("expected_hash", "sha256:" + "a" * 63, "invalid_content_hash"),
        ("scope", "all", "unsupported_scope"),
        ("budget_tokens", True, "invalid_budget"),
        ("budget_tokens", 0, "invalid_budget"),
        ("budget_tokens", -1, "invalid_budget"),
        ("budget_tokens", 1.5, "invalid_budget"),
    ],
)
def test_rejects_invalid_fields(field: str, bad_value: object, error_code: str) -> None:
    payload = valid_payload()
    payload[field] = bad_value

    with pytest.raises(ApplicationServiceError) as raised:
        parse_read_source_request(payload)

    assert raised.value.code == error_code


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("vault_commit_sha", "A" * 40),
        ("vault_commit_sha", "a" * 39),
        ("sidecar_commit_sha", "B" * 40),
        ("sidecar_commit_sha", "b" * 41),
        ("manifest_sha256", "sha256:" + "C" * 64),
        ("manifest_sha256", "sha256:" + "c" * 63),
    ],
)
def test_rejects_malformed_snapshot_identity(field: str, bad_value: object) -> None:
    payload = valid_payload()
    snapshot = dict(payload["snapshot"])
    snapshot[field] = bad_value
    payload["snapshot"] = snapshot

    with pytest.raises(ApplicationServiceError) as raised:
        parse_read_source_request(payload)

    assert raised.value.code == "invalid_snapshot"


def test_rejects_missing_or_unknown_top_level_and_snapshot_fields() -> None:
    payload = valid_payload()
    del payload["snapshot"]
    with pytest.raises(ApplicationServiceError) as raised:
        parse_read_source_request(payload)
    assert raised.value.code == "invalid_read_request"

    payload = valid_payload()
    payload["limit"] = 5
    with pytest.raises(ApplicationServiceError) as raised:
        parse_read_source_request(payload)
    assert raised.value.code == "invalid_read_request"

    payload = valid_payload()
    snapshot = dict(payload["snapshot"])
    snapshot["path"] = "not-allowed"
    payload["snapshot"] = snapshot
    with pytest.raises(ApplicationServiceError) as raised:
        parse_read_source_request(payload)
    assert raised.value.code == "invalid_snapshot"


def test_rejects_snapshot_id_that_does_not_match_tuple() -> None:
    payload = valid_payload()
    snapshot = dict(payload["snapshot"])
    snapshot["snapshot_id"] = "not-the-derived-identity"
    payload["snapshot"] = snapshot

    with pytest.raises(ApplicationServiceError) as raised:
        parse_read_source_request(payload)

    assert raised.value.code == "snapshot_mismatch"


def test_non_object_request_and_snapshot_fail_closed() -> None:
    with pytest.raises(ApplicationServiceError) as raised:
        parse_read_source_request(None)  # type: ignore[arg-type]
    assert raised.value.code == "invalid_read_request"

    payload = valid_payload()
    payload["snapshot"] = []
    with pytest.raises(ApplicationServiceError) as raised:
        parse_read_source_request(payload)
    assert raised.value.code == "invalid_snapshot"
