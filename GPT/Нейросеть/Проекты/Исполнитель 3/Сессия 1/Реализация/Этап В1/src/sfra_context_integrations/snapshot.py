"""Bind one immutable E1 Vault + sidecar snapshot to B1 SnapshotRef."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from sfra_context_builder.models import SnapshotRef


_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXPECTED_DATABASE = "state/structure.sqlite3"


class SnapshotBindingError(ValueError):
    """Raised when Vault, sidecar and manifest do not describe one snapshot."""


@dataclass(frozen=True, slots=True)
class PinnedSnapshot:
    """Immutable paths and identity for a single checked-out E1 snapshot."""

    ref: SnapshotRef
    sidecar_root: Path
    database_path: Path
    manifest_path: Path
    vault_root: Path
    manifest: Mapping[str, Any]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def bind_pinned_snapshot(
    *,
    vault_commit_sha: str,
    sidecar_commit_sha: str,
    sidecar_root: str | Path,
    vault_root: str | Path,
    state_verifier: Callable[[str | Path], Mapping[str, Any]],
    expected_repository: str = "yeatu/obsidianGP",
) -> PinnedSnapshot:
    """Verify E1 state and bind it to actual immutable checkout SHAs.

    state_verifier must be E1's published verify_state_directory function. It
    performs E1-owned SQLite/schema/FK checks. Both SHAs must come from
    git rev-parse HEAD after the checkouts have been pinned by the caller.
    """
    if not isinstance(vault_commit_sha, str) or not _SHA_RE.fullmatch(vault_commit_sha):
        raise SnapshotBindingError("vault_commit_sha must be a 40-character Git SHA")
    if not isinstance(sidecar_commit_sha, str) or not _SHA_RE.fullmatch(sidecar_commit_sha):
        raise SnapshotBindingError("sidecar_commit_sha must be a 40-character Git SHA")
    if not callable(state_verifier):
        raise SnapshotBindingError("state_verifier must be E1 verify_state_directory")

    root = Path(sidecar_root).expanduser().resolve()
    vault = Path(vault_root).expanduser().resolve()
    manifest_file = root / "state" / "manifest.json"
    database_file = root / _EXPECTED_DATABASE

    if not root.is_dir():
        raise SnapshotBindingError("Pinned sidecar checkout is missing")
    if not vault.is_dir():
        raise SnapshotBindingError("Pinned Vault root does not exist or is not a directory")
    if not manifest_file.is_file() or not database_file.is_file():
        raise SnapshotBindingError("Pinned sidecar checkout lacks manifest or SQLite database")

    try:
        verified_manifest = state_verifier(root)
    except Exception as exc:
        raise SnapshotBindingError(
            f"E1 verify_state_directory failed ({type(exc).__name__})"
        ) from exc
    if not isinstance(verified_manifest, Mapping):
        raise SnapshotBindingError("E1 state verifier must return a manifest mapping")

    try:
        raw_manifest = manifest_file.read_bytes()
        manifest = json.loads(raw_manifest.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotBindingError("E1 manifest is not valid UTF-8 JSON") from exc

    if not isinstance(manifest, dict):
        raise SnapshotBindingError("E1 manifest must be a JSON object")
    if dict(verified_manifest) != manifest:
        raise SnapshotBindingError("E1 verifier result differs from the pinned manifest file")
    if manifest.get("source_repository") != expected_repository:
        raise SnapshotBindingError("E1 manifest source_repository does not match expected repository")
    if manifest.get("database") != _EXPECTED_DATABASE:
        raise SnapshotBindingError("E1 manifest database path is not the approved sidecar path")

    source_commit = manifest.get("source_commit")
    if (
        not isinstance(source_commit, str)
        or not _SHA_RE.fullmatch(source_commit)
        or source_commit.lower() != vault_commit_sha.lower()
    ):
        raise SnapshotBindingError(
            "manifest.source_commit does not match the actual pinned Vault checkout"
        )

    expected_db_hash = manifest.get("database_sha256")
    if not isinstance(expected_db_hash, str) or not _HASH_RE.fullmatch(expected_db_hash):
        raise SnapshotBindingError("manifest.database_sha256 is missing or malformed")
    if _sha256_file(database_file) != expected_db_hash:
        raise SnapshotBindingError("E1 SQLite SHA-256 does not match manifest.database_sha256")

    manifest_digest = "sha256:" + hashlib.sha256(raw_manifest).hexdigest()
    ref = SnapshotRef(
        vault_commit_sha=vault_commit_sha,
        sidecar_commit_sha=sidecar_commit_sha,
        manifest_sha256=manifest_digest,
    )
    return PinnedSnapshot(
        ref=ref,
        sidecar_root=root,
        database_path=database_file.resolve(),
        manifest_path=manifest_file.resolve(),
        vault_root=vault,
        manifest=manifest,
    )
