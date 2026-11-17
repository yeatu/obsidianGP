"""Durable, integrity-checked SQLite state snapshots for GitHub Actions."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid
from typing import Any

from .storage import SCHEMA_VERSION

STATE_FORMAT_VERSION = 1
DATABASE_RELATIVE_PATH = "state/structure.sqlite3"
MANIFEST_RELATIVE_PATH = "state/manifest.json"


class StateError(RuntimeError):
    """Raised when a persisted state snapshot is missing or inconsistent."""


def sha256_file(path: str | Path) -> str:
    """Return a prefixed SHA-256 digest for a complete file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _read_only_connection(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise StateError(f"SQLite database does not exist: {path}")
    try:
        return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise StateError(f"Cannot open SQLite database: {exc}") from exc


def _inspect_database(path: Path) -> int:
    """Check SQLite physical integrity, foreign keys and structural schema version."""
    connection = _read_only_connection(path)
    try:
        integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        if integrity != ["ok"]:
            raise StateError("SQLite PRAGMA integrity_check failed: " + "; ".join(integrity))
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise StateError(
                f"SQLite foreign_key_check found {len(foreign_key_errors)} violation(s)"
            )
        row = connection.execute(
            "SELECT schema_version FROM schema_info WHERE singleton = 1"
        ).fetchone()
        if row is None:
            raise StateError("SQLite schema_info row is missing")
        schema_version = int(row[0])
        if schema_version > SCHEMA_VERSION:
            raise StateError(
                f"Database schema {schema_version} is newer than this indexer "
                f"supports ({SCHEMA_VERSION})"
            )
        return schema_version
    except sqlite3.Error as exc:
        raise StateError(f"SQLite integrity/schema inspection failed: {exc}") from exc
    finally:
        connection.close()


def verify_state_directory(state_dir: str | Path) -> dict[str, Any]:
    """Verify the manifest digest and SQLite integrity before state restoration."""
    root = Path(state_dir).expanduser().resolve()
    manifest_path = root / MANIFEST_RELATIVE_PATH
    database_path = root / DATABASE_RELATIVE_PATH
    if not manifest_path.is_file() or not database_path.is_file():
        raise StateError(
            "Persisted state is incomplete: expected state/manifest.json and "
            "state/structure.sqlite3"
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"Cannot read state manifest: {exc}") from exc

    if not isinstance(manifest, dict):
        raise StateError("State manifest must be a JSON object")
    if manifest.get("format_version") != STATE_FORMAT_VERSION:
        raise StateError(
            f"Unsupported state manifest format: {manifest.get('format_version')!r}"
        )
    if manifest.get("database") != DATABASE_RELATIVE_PATH:
        raise StateError("Manifest database path is not the approved state database path")

    # New snapshots write explicit Vault provenance. Older format-v1 manifests
    # remain readable through the legacy source_branch/source_commit aliases.
    vault_ref = manifest.get("vault_ref", manifest.get("source_branch"))
    vault_commit_sha = manifest.get("vault_commit_sha", manifest.get("source_commit"))
    if not isinstance(vault_ref, str) or not vault_ref.strip():
        raise StateError("Manifest vault_ref is missing or malformed")
    if (
        not isinstance(vault_commit_sha, str)
        or len(vault_commit_sha) not in {40, 64}
        or any(char not in "0123456789abcdef" for char in vault_commit_sha.lower())
    ):
        raise StateError("Manifest vault_commit_sha is missing or malformed")
    if (
        "vault_ref" in manifest
        and "source_branch" in manifest
        and manifest["vault_ref"] != manifest["source_branch"]
    ):
        raise StateError("Manifest Vault ref aliases are inconsistent")
    if (
        "vault_commit_sha" in manifest
        and "source_commit" in manifest
        and manifest["vault_commit_sha"] != manifest["source_commit"]
    ):
        raise StateError("Manifest Vault commit aliases are inconsistent")

    expected_digest = manifest.get("database_sha256")
    if (
        not isinstance(expected_digest, str)
        or len(expected_digest) != 71
        or not expected_digest.startswith("sha256:")
    ):
        raise StateError("Manifest database_sha256 is missing or malformed")

    actual_digest = sha256_file(database_path)
    if actual_digest != expected_digest:
        raise StateError(
            "Persisted SQLite SHA-256 mismatch: "
            f"expected {expected_digest}, found {actual_digest}"
        )

    schema_version = _inspect_database(database_path)
    try:
        manifest_schema = int(manifest["sqlite_schema_version"])
    except (KeyError, TypeError, ValueError) as exc:
        raise StateError("Manifest sqlite_schema_version is missing or malformed") from exc
    if schema_version != manifest_schema:
        raise StateError(
            f"SQLite schema version mismatch: manifest={manifest_schema}, "
            f"database={schema_version}"
        )
    return manifest


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def create_state_snapshot(
    db_path: str | Path,
    state_dir: str | Path,
    *,
    source_repository: str,
    vault_ref: str,
    vault_commit_sha: str,
    workflow_run_id: str | int,
) -> dict[str, Any]:
    """Create a consistent SQLite Backup API snapshot and its integrity manifest."""
    if not isinstance(vault_ref, str) or not vault_ref.strip():
        raise StateError("vault_ref must be a non-empty branch, tag, or commit ref")
    if (
        not isinstance(vault_commit_sha, str)
        or len(vault_commit_sha) not in {40, 64}
        or any(char not in "0123456789abcdef" for char in vault_commit_sha.lower())
    ):
        raise StateError("vault_commit_sha must be a 40- or 64-character Git object SHA")

    source_path = Path(db_path).expanduser().resolve()
    if not source_path.is_file():
        raise StateError(f"Source SQLite database does not exist: {source_path}")

    root = Path(state_dir).expanduser().resolve()
    database_path = root / DATABASE_RELATIVE_PATH
    manifest_path = root / MANIFEST_RELATIVE_PATH
    database_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = database_path.with_name(
        f".{database_path.name}.{uuid.uuid4().hex}.tmp"
    )
    source_connection: sqlite3.Connection | None = None
    destination_connection: sqlite3.Connection | None = None
    try:
        source_connection = sqlite3.connect(str(source_path), timeout=30)
        destination_connection = sqlite3.connect(str(temp_path), timeout=30)
        source_connection.backup(destination_connection)
        destination_connection.commit()
        destination_connection.close()
        destination_connection = None
        source_connection.close()
        source_connection = None

        schema_version = _inspect_database(temp_path)
        snapshot_digest = sha256_file(temp_path)
        os.replace(temp_path, database_path)

        final_schema_version = _inspect_database(database_path)
        final_digest = sha256_file(database_path)
        if final_schema_version != schema_version or final_digest != snapshot_digest:
            raise StateError("Final SQLite snapshot changed during publication preparation")

        manifest: dict[str, Any] = {
            "format_version": STATE_FORMAT_VERSION,
            "database": DATABASE_RELATIVE_PATH,
            "database_sha256": final_digest,
            "sqlite_schema_version": final_schema_version,
            "source_repository": source_repository,
            "vault_ref": vault_ref,
            "vault_commit_sha": vault_commit_sha,
            # Backward-compatible aliases for consumers of manifest format v1.
            "source_branch": vault_ref,
            "source_commit": vault_commit_sha,
            "indexer_version": "0.2.0",
            "workflow_run_id": str(workflow_run_id),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_write_json(manifest_path, manifest)
        return verify_state_directory(root)
    except sqlite3.Error as exc:
        raise StateError(f"SQLite Backup API failed: {exc}") from exc
    finally:
        if destination_connection is not None:
            destination_connection.close()
        if source_connection is not None:
            source_connection.close()
        if temp_path.exists():
            temp_path.unlink()
