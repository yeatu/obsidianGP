from __future__ import annotations

import hashlib
import json

import pytest

from sfra_context_integrations.snapshot import SnapshotBindingError, bind_pinned_snapshot


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
