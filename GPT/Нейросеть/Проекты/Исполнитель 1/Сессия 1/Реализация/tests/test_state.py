from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from sfra_indexer import (
    StateError,
    connect_database,
    create_state_snapshot,
    index_vault,
    verify_state_directory,
)


def _indexed_database(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text(
        "# Profile\n\nStable paragraph.\n",
        encoding="utf-8",
    )
    result = index_vault(vault, tmp_path / "working-index")
    return result.database_path


def test_snapshot_manifest_and_database_are_verified(tmp_path):
    source_db = _indexed_database(tmp_path)
    state_dir = tmp_path / "state-repository"

    manifest = create_state_snapshot(
        source_db,
        state_dir,
        source_repository="yeatu/obsidianGP",
        source_branch="executor-1/sfra-indexer-session-1",
        source_commit="abc123",
        workflow_run_id=42,
    )

    assert manifest["format_version"] == 1
    assert manifest["database"] == "state/structure.sqlite3"
    assert manifest["database_sha256"].startswith("sha256:")
    assert manifest["sqlite_schema_version"] == 2
    assert manifest["workflow_run_id"] == "42"
    assert verify_state_directory(state_dir) == manifest

    snapshot = sqlite3.connect(state_dir / "state/structure.sqlite3")
    try:
        assert snapshot.execute("SELECT COUNT(*) FROM structural_nodes").fetchone()[0] > 0
    finally:
        snapshot.close()


def test_manifest_hash_mismatch_is_rejected_before_restore(tmp_path):
    source_db = _indexed_database(tmp_path)
    state_dir = tmp_path / "state-repository"
    create_state_snapshot(
        source_db,
        state_dir,
        source_repository="yeatu/obsidianGP",
        source_branch="executor-1/sfra-indexer-session-1",
        source_commit="abc123",
        workflow_run_id="test",
    )

    manifest_path = state_dir / "state/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database_sha256"] = "sha256:" + ("0" * 64)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(StateError, match="SHA-256 mismatch"):
        verify_state_directory(state_dir)


def test_sqlite_corruption_is_rejected_even_when_manifest_hash_matches(tmp_path):
    source_db = _indexed_database(tmp_path)
    state_dir = tmp_path / "state-repository"
    create_state_snapshot(
        source_db,
        state_dir,
        source_repository="yeatu/obsidianGP",
        source_branch="executor-1/sfra-indexer-session-1",
        source_commit="abc123",
        workflow_run_id="test",
    )

    database_path = state_dir / "state/structure.sqlite3"
    database_path.write_bytes(b"not a SQLite database")
    manifest_path = state_dir / "state/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database_sha256"] = "sha256:" + hashlib.sha256(
        database_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(StateError, match="integrity/schema inspection failed"):
        verify_state_directory(state_dir)


def test_backup_api_captures_committed_wal_data(tmp_path):
    source_db = _indexed_database(tmp_path)
    connection = connect_database(source_db)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE backup_probe (value TEXT NOT NULL)")
        connection.execute("INSERT INTO backup_probe(value) VALUES ('committed in WAL')")
        connection.commit()

        state_dir = tmp_path / "state-repository"
        create_state_snapshot(
            source_db,
            state_dir,
            source_repository="yeatu/obsidianGP",
            source_branch="executor-1/sfra-indexer-session-1",
            source_commit="abc123",
            workflow_run_id="wal-test",
        )

        snapshot = sqlite3.connect(state_dir / "state/structure.sqlite3")
        try:
            value = snapshot.execute("SELECT value FROM backup_probe").fetchone()[0]
        finally:
            snapshot.close()
        assert value == "committed in WAL"
    finally:
        connection.close()


def test_missing_state_is_not_treated_as_an_empty_database(tmp_path):
    with pytest.raises(StateError, match="incomplete"):
        verify_state_directory(tmp_path / "missing-state")
