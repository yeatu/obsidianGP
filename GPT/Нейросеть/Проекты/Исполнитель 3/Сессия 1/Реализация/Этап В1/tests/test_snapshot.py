from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
import json

import pytest

import sfra_context_integrations.snapshot as snapshot_module

from sfra_context_integrations.snapshot import (
    PinnedSnapshot,
    SnapshotBindingError,
    bind_pinned_snapshot,
)
from sfra_context_integrations.search_adapter import E2SearchAdapter, SearchAdapterError
from sfra_context_integrations.source_reader import E1SourceReader, SourceReaderContractError
from sfra_context_builder.models import SearchRequest, SnapshotRef


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _fixture(tmp_path, *, source_commit="a" * 40):
    sidecar = tmp_path / "sidecar"
    state = sidecar / "state"
    state.mkdir(parents=True)
    database = state / "structure.sqlite3"
    database.write_bytes(b"immutable sqlite fixture")
    manifest = {
        "database": "state/structure.sqlite3",
        "database_sha256": _sha(database.read_bytes()),
        "format_version": 1,
        "indexer_version": "0.2.0",
        "source_branch": "executor-1/sfra-indexer-session-1",
        "source_commit": source_commit,
        "source_repository": "yeatu/obsidianGP",
        "sqlite_schema_version": 2,
    }
    manifest_path = state / "manifest.json"
    raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    manifest_path.write_bytes(raw)
    vault_git = tmp_path / "vault-git"
    vault_root = vault_git / "ГП"
    vault_root.mkdir(parents=True)
    return sidecar, vault_git, vault_root, manifest, raw, database


def _binder(
    sidecar, vault_git, vault_root, manifest, *,
    sidecar_sha="b" * 40, vault_sha="a" * 40, dirty="",
    branch="sfra-state",
):
    def head_reader(path):
        return sidecar_sha if path == sidecar.resolve() else vault_sha

    return bind_pinned_snapshot(
        sidecar_root=sidecar,
        vault_git_root=vault_git,
        vault_root=vault_root,
        state_verifier=lambda _: manifest,
        git_head_reader=head_reader,
        git_branch_reader=lambda _: branch,
        git_status_reader=lambda _: dirty,
    )


def test_binds_snapshot_to_actual_git_heads_and_exact_manifest_bytes(tmp_path):
    sidecar, vault_git, vault_root, manifest, raw, database = _fixture(tmp_path)

    pinned = _binder(sidecar, vault_git, vault_root, manifest)

    assert pinned.ref.vault_commit_sha == manifest["source_commit"]
    assert pinned.ref.sidecar_commit_sha == "b" * 40
    assert pinned.ref.manifest_sha256 == _sha(raw)
    assert pinned.database_path == database.resolve()
    assert pinned.vault_git_root == vault_git.resolve()
    assert pinned.vault_root == vault_root.resolve()


def test_rejects_manifest_source_commit_not_equal_to_actual_vault_head(tmp_path):
    sidecar, vault_git, vault_root, manifest, _, _ = _fixture(tmp_path)
    with pytest.raises(SnapshotBindingError, match="manifest.source_commit"):
        _binder(sidecar, vault_git, vault_root, manifest, vault_sha="c" * 40)


def test_rejects_dirty_sidecar_or_vault_checkout(tmp_path):
    sidecar, vault_git, vault_root, manifest, _, _ = _fixture(tmp_path)
    with pytest.raises(SnapshotBindingError, match="dirty"):
        _binder(sidecar, vault_git, vault_root, manifest, dirty=" M state/manifest.json\n")


def test_rejects_database_changed_after_manifest_was_written(tmp_path):
    sidecar, vault_git, vault_root, manifest, _, database = _fixture(tmp_path)
    database.write_bytes(b"modified sqlite fixture")
    with pytest.raises(SnapshotBindingError, match="SQLite SHA-256"):
        _binder(sidecar, vault_git, vault_root, manifest)


def test_rejects_manifest_verifier_disagreement(tmp_path):
    sidecar, vault_git, vault_root, manifest, _, _ = _fixture(tmp_path)

    with pytest.raises(SnapshotBindingError, match="verifier result"):
        bind_pinned_snapshot(
            sidecar_root=sidecar,
            vault_git_root=vault_git,
            vault_root=vault_root,
            state_verifier=lambda _: dict(manifest, indexer_version="unexpected"),
            git_head_reader=lambda path: (
                "b" * 40 if path == sidecar.resolve() else "a" * 40
            ),
            git_branch_reader=lambda _: "sfra-state",
            git_status_reader=lambda _: "",
        )


def test_requires_e1_state_verifier(tmp_path):
    sidecar, vault_git, vault_root, manifest, _, _ = _fixture(tmp_path)
    with pytest.raises(SnapshotBindingError, match="verify_state_directory"):
        bind_pinned_snapshot(
            sidecar_root=sidecar,
            vault_git_root=vault_git,
            vault_root=vault_root,
            state_verifier=None,
        )


def test_pinned_snapshot_rejects_public_direct_construction_with_noop(tmp_path):
    root = tmp_path.resolve()
    with pytest.raises(SnapshotBindingError, match="bind_pinned_snapshot"):
        PinnedSnapshot(
            ref=SnapshotRef("a" * 40, "b" * 40, "sha256:" + "c" * 64),
            sidecar_root=root,
            database_path=root / "state" / "structure.sqlite3",
            manifest_path=root / "state" / "manifest.json",
            vault_git_root=root,
            vault_root=root / "ГП",
            manifest={"source_commit": "a" * 40},
            _verifier_callback=lambda: None,
        )


def test_bound_verifier_callback_cannot_be_replaced(tmp_path):
    sidecar, vault_git, vault_root, manifest, _, database = _fixture(tmp_path)
    pinned = _binder(sidecar, vault_git, vault_root, manifest)

    # The original factory-created verifier is active before any attempted bypass.
    pinned.verify_current()

    with pytest.raises(FrozenInstanceError):
        pinned._verifier_callback = lambda: None

    with pytest.raises(FrozenInstanceError):
        del pinned._verifier_callback

    database.write_bytes(b"replacement after attempted verifier replacement")
    with pytest.raises(SnapshotBindingError, match="SQLite database digest changed"):
        pinned.verify_current()


def test_snapshot_module_exposes_no_verifier_minting_symbols():
    assert not hasattr(snapshot_module, "_SnapshotVerifier")
    assert not hasattr(snapshot_module, "_SNAPSHOT_VERIFIER_SEAL")


def test_rejects_vault_root_outside_pinned_git_checkout(tmp_path):
    sidecar, vault_git, _, manifest, _, _ = _fixture(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(SnapshotBindingError, match="inside"):
        _binder(sidecar, vault_git, outside, manifest)



def test_rejects_sidecar_checkout_not_on_sfra_state_branch(tmp_path):
    sidecar, vault_git, vault_root, manifest, _, _ = _fixture(tmp_path)
    with pytest.raises(SnapshotBindingError, match="sfra-state"):
        _binder(sidecar, vault_git, vault_root, manifest, branch="main")


class _Counter:
    def count(self, text):
        return len(text)

    def metadata(self):
        return {"name": "fixture-counter", "version": "1"}


class _ReadApi:
    def __init__(self, *, mutate=None):
        self.calls = []
        self.mutate = mutate

    def resolve_current_node(self, db_path, node_id, *, snapshot_id):
        self.calls.append(("resolve", db_path, node_id, snapshot_id))
        if self.mutate is not None:
            self.mutate()
        return {"status": "not_found", "snapshot_id": snapshot_id}

    def read_source_scope(self, db_path, vault_root, node_id, expected_hash, *, scope, snapshot_id):
        self.calls.append(("read", db_path, vault_root, node_id, expected_hash, scope, snapshot_id))
        if self.mutate is not None:
            self.mutate()
        return {"status": "not_found", "snapshot_id": snapshot_id, "scope": scope}


def test_source_reader_rejects_sidecar_replacement_before_e1_read(tmp_path):
    sidecar, vault_git, vault_root, manifest, _, database = _fixture(tmp_path)
    pinned = _binder(sidecar, vault_git, vault_root, manifest)
    api = _ReadApi()
    reader = E1SourceReader(api, pinned, _Counter())

    database.write_bytes(b"replacement sidecar database")

    with pytest.raises(SourceReaderContractError) as error:
        reader.resolve_current_node("node_fixture", pinned.ref)

    assert error.value.code == "snapshot_changed"
    assert api.calls == []


def test_source_reader_discards_e1_result_if_sidecar_changes_during_read(tmp_path):
    sidecar, vault_git, vault_root, manifest, _, database = _fixture(tmp_path)
    pinned = _binder(sidecar, vault_git, vault_root, manifest)

    def replace_sidecar():
        database.write_bytes(b"replacement during E1 read")

    api = _ReadApi(mutate=replace_sidecar)
    reader = E1SourceReader(api, pinned, _Counter())

    with pytest.raises(SourceReaderContractError) as error:
        reader.resolve_current_node("node_fixture", pinned.ref)

    assert error.value.code == "snapshot_changed"
    assert len(api.calls) == 1


def test_search_adapter_discards_e2_result_if_sidecar_changes_during_search(tmp_path):
    sidecar, vault_git, vault_root, manifest, _, database = _fixture(tmp_path)
    pinned = _binder(sidecar, vault_git, vault_root, manifest)

    class _NodeReader:
        def __init__(self):
            self.calls = []

        def read_node(self, node_id, expected_hash, snapshot):
            self.calls.append(node_id)
            return {"status": "not_found", "node": None}

    reader = _NodeReader()

    def search_call(*args, **kwargs):
        database.write_bytes(b"replacement during E2 search")
        return {"search": {"status": "not_found_in_retrieval", "results": []}}

    request = SearchRequest(
        query="fixture",
        task=None,
        budget_tokens=100,
    )
    adapter = E2SearchAdapter(pinned, reader, search_call=search_call)

    with pytest.raises(SearchAdapterError) as error:
        adapter.search(request)

    assert error.value.code == "snapshot_changed"
    assert reader.calls == []
