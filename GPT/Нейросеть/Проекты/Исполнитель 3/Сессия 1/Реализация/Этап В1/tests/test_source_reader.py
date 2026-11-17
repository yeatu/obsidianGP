from __future__ import annotations

import pytest

from sfra_context_integrations.source_reader import (
    E1SourceReader,
    SourceReaderContractError,
)
from tests.fixtures.source_reader import FixtureE1ScopeAPI, snapshot


def _target_hash(api):
    return api.records["node_target"]["content_hash"]


@pytest.mark.parametrize(
    ("scope", "roles"),
    [
        ("node", {"target"}),
        ("parent", {"target", "parent_context"}),
        ("neighbors", {"target", "previous_neighbor", "next_neighbor"}),
        ("document", {"document"}),
    ],
)
def test_source_reader_supports_all_four_scopes(scope, roles):
    pinned = snapshot()
    api = FixtureE1ScopeAPI(pinned)
    reader = E1SourceReader(api)

    result = reader.read_scope(
        "node_target",
        _target_hash(api),
        scope,
        pinned,
    )

    assert result["status"] == "ok"
    assert result["snapshot_id"] == pinned.snapshot_id
    assert {fragment["role"] for fragment in result["fragments"]} == roles
    assert all(fragment["source_path"] == "fixtures/test-document.md" for fragment in result["fragments"])
    assert {fragment["index_generation"] for fragment in result["fragments"]} == {7}
    assert {fragment["document_hash"] for fragment in result["fragments"]} == {api.document_hash}


def test_read_node_adapts_exact_node_fragment_for_search_adapter():
    pinned = snapshot()
    api = FixtureE1ScopeAPI(pinned)
    reader = E1SourceReader(api)

    result = reader.read_node("node_target", _target_hash(api), pinned)

    assert result["status"] == "ok"
    assert result["node"]["node_id"] == "node_target"
    assert result["node"]["content_hash"] == _target_hash(api)
    assert result["node"]["raw_text"] == "Target original source fragment.\n"
    assert result["node"]["document_hash"] == api.document_hash
    assert result["node"]["index_generation"] == 7


@pytest.mark.parametrize("status", ["stale_source", "ambiguous", "deleted", "not_found", "integrity_error"])
def test_source_reader_preserves_explicit_non_ok_status_without_fragments(status):
    pinned = snapshot()
    api = FixtureE1ScopeAPI(pinned)
    api.status_overrides["node_target"] = status
    reader = E1SourceReader(api)

    result = reader.read_scope(
        "node_target",
        _target_hash(api),
        "node",
        pinned,
    )

    assert result["status"] == status
    assert result["fragments"] == []


def test_source_reader_rejects_cross_snapshot_response():
    pinned = snapshot()
    api = FixtureE1ScopeAPI(pinned)
    reader = E1SourceReader(api)
    other = type(pinned)("d" * 40, "e" * 40, "sha256:" + "f" * 64)

    with pytest.raises(SourceReaderContractError) as error:
        reader.read_scope("node_target", _target_hash(api), "node", other)

    assert error.value.code == "snapshot_mismatch"


def test_source_reader_rejects_mixed_document_generation():
    pinned = snapshot()
    api = FixtureE1ScopeAPI(pinned)
    original = api.read_scope

    def mixed(*args):
        response = original(*args)
        if response["status"] == "ok":
            response["fragments"][1]["index_generation"] = 8
        return response

    api.read_scope = mixed
    reader = E1SourceReader(api)

    with pytest.raises(SourceReaderContractError) as error:
        reader.read_scope("node_target", _target_hash(api), "neighbors", pinned)

    assert error.value.code == "snapshot_generation_mismatch"


def test_source_reader_rejects_mixed_document_hash():
    pinned = snapshot()
    api = FixtureE1ScopeAPI(pinned)
    original = api.read_scope

    def mixed(*args):
        response = original(*args)
        if response["status"] == "ok":
            response["fragments"][1]["document_hash"] = "sha256:" + "0" * 64
        return response

    api.read_scope = mixed
    reader = E1SourceReader(api)

    with pytest.raises(SourceReaderContractError) as error:
        reader.read_scope("node_target", _target_hash(api), "neighbors", pinned)

    assert error.value.code == "document_hash_mismatch"


def test_source_reader_rejects_modified_fragment_text():
    pinned = snapshot()
    api = FixtureE1ScopeAPI(pinned)
    original = api.read_scope

    def corrupted(*args):
        response = original(*args)
        if response["status"] == "ok":
            response["fragments"][0]["raw_text"] += "tampered"
        return response

    api.read_scope = corrupted
    reader = E1SourceReader(api)

    with pytest.raises(SourceReaderContractError) as error:
        reader.read_scope("node_target", _target_hash(api), "node", pinned)

    assert error.value.code == "content_hash_mismatch"


def test_source_reader_refuses_partial_fragments_on_budget_exceeded():
    pinned = snapshot()
    api = FixtureE1ScopeAPI(pinned)
    reader = E1SourceReader(api)

    result = reader.read_scope(
        "node_target",
        _target_hash(api),
        "document",
        pinned,
        budget_tokens=1,
    )

    assert result["status"] == "budget_exceeded"
    assert result["fragments"] == []
    assert result["token_accounting"]["tokens_used"] > result["token_accounting"]["budget_tokens"]


def test_source_reader_rejects_error_response_that_contains_partial_text():
    pinned = snapshot()
    api = FixtureE1ScopeAPI(pinned)
    original = api.read_scope

    def partial_error(*args):
        response = original(*args)
        response["status"] = "integrity_error"
        return response

    api.read_scope = partial_error
    reader = E1SourceReader(api)

    with pytest.raises(SourceReaderContractError) as error:
        reader.read_scope("node_target", _target_hash(api), "node", pinned)

    assert error.value.code == "partial_error_payload"


def test_source_reader_rejects_null_document_hash_for_non_node_scopes():
    pinned = snapshot()
    api = FixtureE1ScopeAPI(pinned)
    api.records["node_target"]["document_hash"] = None
    reader = E1SourceReader(api)

    result = reader.read_scope(
        "node_target",
        _target_hash(api),
        "parent",
        pinned,
    )

    assert result["status"] == "integrity_error"
    assert result["fragments"] == []
