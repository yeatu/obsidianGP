from __future__ import annotations

import pytest

from sfra_context_integrations.snapshot import SnapshotBindingError
from sfra_context_integrations.source_reader import SourceReaderContractError
from tests.fixtures.consumer_seams import make_test_source_reader
from tests.fixtures.pinned_snapshot import make_test_pinned_snapshot
from tests.fixtures.source_reader import FixtureE1ScopeAPI, FixtureTokenCounter, snapshot


def _pinned(tmp_path, ref, *, verifier=None):
    sidecar = tmp_path / "sidecar"
    vault_git = tmp_path / "vault-git"
    vault = vault_git / "ГП"
    state = sidecar / "state"
    state.mkdir(parents=True)
    vault.mkdir(parents=True)
    database = state / "structure.sqlite3"
    manifest = state / "manifest.json"
    database.write_bytes(b"fixture sidecar")
    manifest.write_bytes(b"{}")
    return make_test_pinned_snapshot(
        ref=ref,
        sidecar_root=sidecar,
        database_path=database,
        manifest_path=manifest,
        vault_git_root=vault_git,
        vault_root=vault,
        manifest={"source_commit": ref.vault_commit_sha},
        verifier=verifier,
    )


def _reader(tmp_path):
    ref = snapshot()
    pinned = _pinned(tmp_path, ref)
    api = FixtureE1ScopeAPI(ref)
    return make_test_source_reader(api, pinned, FixtureTokenCounter()), api, pinned


def test_reader_runs_verifier_and_fails_before_any_e1_call(tmp_path):
    ref = snapshot()
    checks = []

    def reject_snapshot():
        checks.append("checked")
        raise SnapshotBindingError("fixture verifier rejected the snapshot")

    pinned = _pinned(tmp_path, ref, verifier=reject_snapshot)
    api = FixtureE1ScopeAPI(ref)

    with pytest.raises(SourceReaderContractError) as error:
        make_test_source_reader(api, pinned, FixtureTokenCounter())

    assert error.value.code == "snapshot_changed"
    assert checks == ["checked"]
    assert api.resolve_calls == []
    assert api.scope_calls == []


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
def test_source_reader_supports_all_four_scopes_through_exact_public_api(tmp_path, scope, roles):
    reader, api, pinned = _reader(tmp_path)

    result = reader.read_scope(
        "node_target",
        _target_hash(api),
        scope,
        pinned.ref,
    )

    assert result["status"] == "ok"
    assert result["snapshot_id"] == pinned.ref.snapshot_id
    assert {fragment["role"] for fragment in result["fragments"]} == roles
    assert all(fragment["source_path"] == "fixtures/test-document.md" for fragment in result["fragments"])
    assert {fragment["index_generation"] for fragment in result["fragments"]} == {7}
    assert {fragment["document_hash"] for fragment in result["fragments"]} == {api.document_hash}
    assert api.scope_calls == [(
        str(pinned.database_path),
        str(pinned.vault_root),
        "node_target",
        _target_hash(api),
        scope,
        pinned.ref.snapshot_id,
    )]


def test_read_node_adapts_exact_node_fragment_for_search_adapter(tmp_path):
    reader, api, pinned = _reader(tmp_path)

    result = reader.read_node("node_target", _target_hash(api), pinned.ref)

    assert result["status"] == "ok"
    assert result["snapshot_id"] == pinned.ref.snapshot_id
    assert result["node"]["node_id"] == "node_target"
    assert result["node"]["content_hash"] == _target_hash(api)
    assert result["node"]["raw_text"] == "Target original source fragment.\n"
    assert result["node"]["document_hash"] == api.document_hash
    assert result["node"]["index_generation"] == 7


def test_resolve_current_node_passes_snapshot_id_and_returns_address_only(tmp_path):
    reader, api, pinned = _reader(tmp_path)

    result = reader.resolve_current_node("node_target", pinned.ref)

    assert result["status"] == "ok"
    assert result["snapshot_id"] == pinned.ref.snapshot_id
    assert result["address"]["node_id"] == "node_target"
    assert result["address"]["content_hash"] == _target_hash(api)
    assert "raw_text" not in result["address"]
    assert api.resolve_calls == [(
        str(pinned.database_path),
        "node_target",
        pinned.ref.snapshot_id,
    )]


@pytest.mark.parametrize("status", ["stale_source", "ambiguous", "deleted", "not_found", "integrity_error"])
def test_source_reader_preserves_explicit_non_ok_status_without_fragments(tmp_path, status):
    reader, api, pinned = _reader(tmp_path)
    api.status_overrides["node_target"] = status

    result = reader.read_scope(
        "node_target",
        _target_hash(api),
        "node",
        pinned.ref,
    )

    assert result["status"] == status
    assert result["fragments"] == []


def test_source_reader_rejects_cross_snapshot_before_calling_e1(tmp_path):
    reader, api, pinned = _reader(tmp_path)
    other = type(pinned.ref)("d" * 40, "e" * 40, "sha256:" + "f" * 64)

    with pytest.raises(SourceReaderContractError) as error:
        reader.read_scope("node_target", _target_hash(api), "node", other)

    assert error.value.code == "snapshot_mismatch"
    assert api.scope_calls == []


def test_source_reader_rejects_e1_response_with_wrong_snapshot_id(tmp_path):
    reader, api, pinned = _reader(tmp_path)
    api.expected_snapshot = type(pinned.ref)("d" * 40, "e" * 40, "sha256:" + "f" * 64)

    with pytest.raises(SourceReaderContractError) as error:
        reader.read_scope("node_target", _target_hash(api), "node", pinned.ref)

    assert error.value.code == "snapshot_mismatch"


def test_source_reader_rejects_mixed_document_generation(tmp_path):
    reader, api, pinned = _reader(tmp_path)
    original = api.read_source_scope

    def mixed(*args, **kwargs):
        response = original(*args, **kwargs)
        if response["status"] == "ok":
            response["fragments"][1]["index_generation"] = 8
        return response

    api.read_source_scope = mixed

    with pytest.raises(SourceReaderContractError) as error:
        reader.read_scope("node_target", _target_hash(api), "neighbors", pinned.ref)

    assert error.value.code == "snapshot_generation_mismatch"


def test_source_reader_rejects_mixed_document_hash(tmp_path):
    reader, api, pinned = _reader(tmp_path)
    original = api.read_source_scope

    def mixed(*args, **kwargs):
        response = original(*args, **kwargs)
        if response["status"] == "ok":
            response["fragments"][1]["document_hash"] = "sha256:" + "0" * 64
        return response

    api.read_source_scope = mixed

    with pytest.raises(SourceReaderContractError) as error:
        reader.read_scope("node_target", _target_hash(api), "neighbors", pinned.ref)

    assert error.value.code == "document_hash_mismatch"


def test_source_reader_rejects_modified_fragment_text(tmp_path):
    reader, api, pinned = _reader(tmp_path)
    original = api.read_source_scope

    def corrupted(*args, **kwargs):
        response = original(*args, **kwargs)
        if response["status"] == "ok":
            response["fragments"][0]["raw_text"] += "tampered"
        return response

    api.read_source_scope = corrupted

    with pytest.raises(SourceReaderContractError) as error:
        reader.read_scope("node_target", _target_hash(api), "node", pinned.ref)

    assert error.value.code == "content_hash_mismatch"


def test_source_reader_budget_is_calculated_by_e3_and_never_sent_to_e1(tmp_path):
    reader, api, pinned = _reader(tmp_path)
    original = api.read_source_scope
    long_text = "Target original source fragment. " + ("verified text. " * 40) + "\n"
    api.records["node_target"]["raw_text"] = long_text
    api.records["node_target"]["content_hash"] = (
        "sha256:" + __import__("hashlib").sha256(long_text.encode("utf-8")).hexdigest()
    )
    api.document_text = api.document_text.replace("Target original source fragment.\n", long_text)
    api.document_hash = (
        "sha256:" + __import__("hashlib").sha256(api.document_text.encode("utf-8")).hexdigest()
    )
    for record in api.records.values():
        record["document_hash"] = api.document_hash

    result = reader.read_scope(
        "node_target",
        api.records["node_target"]["content_hash"],
        "document",
        pinned.ref,
        budget_tokens=2,
    )

    assert result["status"] == "budget_exceeded"
    assert result["fragments"] == []
    assert result["token_accounting"]["budget_owner"] == "E3"
    assert result["token_accounting"]["tokens_used"] > 2
    assert api.scope_calls[-1][-1] == pinned.ref.snapshot_id
    assert len(api.scope_calls[-1]) == 6  # E1 receives no token budget argument.


def test_source_reader_rejects_error_response_that_contains_partial_text(tmp_path):
    reader, api, pinned = _reader(tmp_path)
    original = api.read_source_scope

    def partial_error(*args, **kwargs):
        response = original(*args, **kwargs)
        response["status"] = "integrity_error"
        return response

    api.read_source_scope = partial_error

    with pytest.raises(SourceReaderContractError) as error:
        reader.read_scope("node_target", _target_hash(api), "node", pinned.ref)

    assert error.value.code == "partial_error_payload"


def test_source_reader_requires_whole_document_hash_for_non_node_scopes(tmp_path):
    reader, api, pinned = _reader(tmp_path)
    api.records["node_target"]["document_hash"] = None
    api.records["node_target"]["source_sha256"] = None

    result = reader.read_scope(
        "node_target",
        _target_hash(api),
        "parent",
        pinned.ref,
    )

    assert result["status"] == "integrity_error"
    assert result["fragments"] == []


class _E1DataclassResult:
    """Small stand-in for E1's frozen result dataclasses."""

    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return self._payload


class _DataclassReturningE1API:
    def __init__(self, delegate):
        self.delegate = delegate

    def read_source_scope(self, *args, **kwargs):
        return _E1DataclassResult(
            self.delegate.read_source_scope(*args, **kwargs)
        )

    def resolve_current_node(self, *args, **kwargs):
        return _E1DataclassResult(
            self.delegate.resolve_current_node(*args, **kwargs)
        )


def test_source_reader_accepts_e1_public_result_dataclasses(tmp_path):
    ref = snapshot()
    pinned = _pinned(tmp_path, ref)
    fake = FixtureE1ScopeAPI(ref)
    reader = make_test_source_reader(
        _DataclassReturningE1API(fake),
        pinned,
        FixtureTokenCounter(),
    )

    current = reader.resolve_current_node("node_target", pinned.ref)
    scope = reader.read_scope(
        "node_target",
        _target_hash(fake),
        "document",
        pinned.ref,
    )

    assert current["status"] == "ok"
    assert current["address"]["content_hash"] == _target_hash(fake)
    assert scope["status"] == "ok"
    assert scope["fragments"][0]["role"] == "document"
    assert scope["fragments"][0]["raw_text"] == fake.document_text


def test_parent_scope_rejects_parent_id_not_equal_to_target_parent_node_id(tmp_path):
    reader, api, pinned = _reader(tmp_path)
    original = api.read_source_scope

    def wrong_parent(*args, **kwargs):
        response = original(*args, **kwargs)
        if response["status"] == "ok":
            response["parent"] = dict(api.records["node_next"])
            response["fragments"] = [
                dict(response["anchor"]),
                dict(response["parent"]),
            ]
        return response

    api.read_source_scope = wrong_parent
    with pytest.raises(SourceReaderContractError) as error:
        reader.read_scope("node_target", _target_hash(api), "parent", pinned.ref)
    assert error.value.code == "parent_identity_mismatch"


def test_neighbors_scope_rejects_sibling_under_another_parent(tmp_path):
    reader, api, pinned = _reader(tmp_path)
    original = api.read_source_scope

    def wrong_parent(*args, **kwargs):
        response = original(*args, **kwargs)
        if response["status"] == "ok":
            response["previous"]["parent_node_id"] = "node_other_parent"
            for fragment in response["fragments"]:
                if fragment["node_id"] == "node_previous":
                    fragment["parent_node_id"] = "node_other_parent"
        return response

    api.read_source_scope = wrong_parent
    with pytest.raises(SourceReaderContractError) as error:
        reader.read_scope("node_target", _target_hash(api), "neighbors", pinned.ref)
    assert error.value.code == "neighbor_parent_mismatch"


def test_neighbors_scope_rejects_reversed_source_order(tmp_path):
    reader, api, pinned = _reader(tmp_path)
    original = api.read_source_scope

    def reversed_previous(*args, **kwargs):
        response = original(*args, **kwargs)
        if response["status"] == "ok":
            response["previous"]["char_start"] = 200
            response["previous"]["char_end"] = 210
            for fragment in response["fragments"]:
                if fragment["node_id"] == "node_previous":
                    fragment["char_start"] = 200
                    fragment["char_end"] = 210
        return response

    api.read_source_scope = reversed_previous
    with pytest.raises(SourceReaderContractError) as error:
        reader.read_scope("node_target", _target_hash(api), "neighbors", pinned.ref)
    assert error.value.code == "neighbor_source_order_mismatch"


def test_neighbors_scope_rejects_duplicate_node_id_across_roles(tmp_path):
    reader, api, pinned = _reader(tmp_path)
    original = api.read_source_scope

    def duplicate_next(*args, **kwargs):
        response = original(*args, **kwargs)
        if response["status"] == "ok":
            response["next"] = dict(response["anchor"])
            response["fragments"] = [
                dict(response["anchor"]),
                dict(response["previous"]),
                dict(response["next"]),
            ]
        return response

    api.read_source_scope = duplicate_next
    with pytest.raises(SourceReaderContractError):
        reader.read_scope("node_target", _target_hash(api), "neighbors", pinned.ref)


def test_source_reader_rejects_wrong_echoed_scope(tmp_path):
    reader, api, pinned = _reader(tmp_path)
    original = api.read_source_scope

    def wrong_scope(*args, **kwargs):
        response = original(*args, **kwargs)
        response["scope"] = "document"
        return response

    api.read_source_scope = wrong_scope
    with pytest.raises(SourceReaderContractError) as error:
        reader.read_scope("node_target", _target_hash(api), "node", pinned.ref)
    assert error.value.code == "scope_mismatch"
