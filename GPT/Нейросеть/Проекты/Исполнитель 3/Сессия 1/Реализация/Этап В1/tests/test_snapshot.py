from __future__ import annotations

import hashlib
import json

import pytest

from sfra_context_integrations.snapshot import (
    SnapshotBindingError,
    bind_pinned_snapshot,
)


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _fixture(tmp_path, *, source_commit="a" * 40):
    root = tmp_path / "sidecar"
    state = root / "state"
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
    # Deliberately use non-canonical whitespace: SnapshotRef hashes exact bytes.
    raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    manifest_path.write_bytes(raw)
    vault = tmp_path / "vault"
    vault.mkdir()
    return root, vault, manifest, raw, database


def test_binds_snapshot_to_manifest_source_commit_and_exact_manifest_bytes(tmp_path):
    root, vault, manifest, raw, database = _fixture()
    verifier_calls = []

    def verify_state(state_root):
        verifier_calls.append(state_root)
        return manifest

    pinned = bind_pinned_snapshot(
        vault_commit_sha=manifest["source_commit"],
        sidecar_commit_sha="b" * 40,
        sidecar_root=root,
        vault_root=vault,
        state_verifier=verify_state,
    )

    assert pinned.ref.vault_commit_sha == manifest["source_commit"]
    assert pinned.ref.sidecar_commit_sha == "b" * 40
    assert pinned.ref.manifest_sha256 == _sha(raw)
    assert pinned.database_path == database.resolve()
    assert pinned.vault_root == vault.resolve()
    assert verifier_calls == [root.resolve()]


def test_rejects_manifest_source_commit_not_equal_to_pinned_vault(tmp_path):
    root, vault, manifest, _, _ = _fixture()
    with pytest.raises(SnapshotBindingError, match="manifest.source_commit"):
        bind_pinned_snapshot(
            vault_commit_sha="c" * 40,
            sidecar_commit_sha="b" * 40,
            sidecar_root=root,
            vault_root=vault,
            state_verifier=lambda _: manifest,
        )


def test_rejects_database_changed_after_manifest_was_written(tmp_path):
    root, vault, manifest, _, database = _fixture()
    database.write_bytes(b"modified sqlite fixture")
    with pytest.raises(SnapshotBindingError, match="SQLite SHA-256"):
        bind_pinned_snapshot(
            vault_commit_sha=manifest["source_commit"],
            sidecar_commit_sha="b" * 40,
            sidecar_root=root,
            vault_root=vault,
            state_verifier=lambda _: manifest,
        )


def test_rejects_manifest_verifier_disagreement(tmp_path):
    root, vault, manifest, _, _ = _fixture()
    other = dict(manifest, indexer_version="unexpected")
    with pytest.raises(SnapshotBindingError, match="verifier result"):
        bind_pinned_snapshot(
            vault_commit_sha=manifest["source_commit"],
            sidecar_commit_sha="b" * 40,
            sidecar_root=root,
            vault_root=vault,
            state_verifier=lambda _: other,
        )


def test_requires_e1_state_verifier(tmp_path):
    root, vault, manifest, _, _ = _fixture()
    with pytest.raises(SnapshotBindingError, match="state_verifier"):
        bind_pinned_snapshot(
            vault_commit_sha=manifest["source_commit"],
            sidecar_commit_sha="b" * 40,
            sidecar_root=root,
            vault_root=vault,
            state_verifier=None,
        )
