"""Create a SnapshotRef from two clean immutable Git checkouts and E1 manifest."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import weakref
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from sfra_context_builder.models import SnapshotRef


_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXPECTED_DATABASE = "state/structure.sqlite3"


class SnapshotBindingError(ValueError):
    """Raised when Vault, sidecar and manifest do not describe one snapshot."""


@dataclass(frozen=True, slots=True, init=False, weakref_slot=True)
class PinnedSnapshot:
    """Snapshot identity bound to a verifier created by the trusted factory.

    Direct construction is deliberately disabled. Production instances are
    created only inside bind_pinned_snapshot(), after checkout, manifest and
    E1 state verification. The active verifier is kept in a private weak
    registry, not in an instance attribute: consumers cannot obtain or mutate
    the callback function object through a PinnedSnapshot reference.
    """

    ref: SnapshotRef
    sidecar_root: Path
    database_path: Path
    manifest_path: Path
    vault_git_root: Path
    vault_root: Path
    manifest: Mapping[str, Any]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise SnapshotBindingError(
            "PinnedSnapshot must be created by bind_pinned_snapshot()"
        )

    def verify_current(self) -> None:
        """Fail closed if any bound checkout, manifest or database changed."""
        _run_registered_verifier(self)


def _build_verifier_registry():
    """Create a one-shot verifier registry without exposing callback state on snapshots."""
    entries: dict[
        int,
        tuple[weakref.ReferenceType[PinnedSnapshot], Callable[[], None]],
    ] = {}

    def register(snapshot: PinnedSnapshot, callback: Callable[[], None]) -> None:
        if not callable(callback):
            raise SnapshotBindingError("Pinned snapshot verifier must be callable")
        key = id(snapshot)
        existing = entries.get(key)
        if existing is not None and existing[0]() is snapshot:
            raise SnapshotBindingError(
                "Pinned snapshot already has an active verifier"
            )

        def discard(reference: weakref.ReferenceType[PinnedSnapshot]) -> None:
            current = entries.get(key)
            if current is not None and current[0] is reference:
                entries.pop(key, None)

        reference = weakref.ref(snapshot, discard)
        entries[key] = (reference, callback)

    def verify(snapshot: PinnedSnapshot) -> None:
        entry = entries.get(id(snapshot))
        if entry is None or entry[0]() is not snapshot:
            raise SnapshotBindingError(
                "Pinned snapshot has no active verifier binding"
            )
        callback = entry[1]
        try:
            callback()
        except SnapshotBindingError:
            raise
        except Exception as exc:
            raise SnapshotBindingError("Pinned snapshot verifier failed") from exc

    return register, verify


_register_snapshot_verifier, _run_registered_verifier = _build_verifier_registry()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _git_head(root: str | Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "HEAD^{commit}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _git_branch(root: str | Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "symbolic-ref", "--quiet", "--short", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _git_status(root: str | Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def bind_pinned_snapshot(
    *,
    sidecar_root: str | Path,
    vault_git_root: str | Path,
    vault_root: str | Path,
    state_verifier: Callable[[str | Path], Mapping[str, Any]],
    git_head_reader: Callable[[str | Path], str] = _git_head,
    git_branch_reader: Callable[[str | Path], str] = _git_branch,
    git_status_reader: Callable[[str | Path], str] = _git_status,
    expected_repository: str = "yeatu/obsidianGP",
    expected_sidecar_branch: str = "sfra-state",
) -> PinnedSnapshot:
    """Verify clean Git checkouts, exact E1 manifest bytes and SQLite digest.

    The actual Git HEAD values are always read by this layer. The only injectable
    readers are for isolated tests; production callers use subprocess git.
    state_verifier must be E1's public verify_state_directory function. It owns
    SQLite schema/integrity checks; E3 owns checkout and manifest binding.
    """
    if not callable(state_verifier):
        raise SnapshotBindingError("state_verifier must be E1 verify_state_directory")

    sidecar = Path(sidecar_root).expanduser().resolve()
    vault_git = Path(vault_git_root).expanduser().resolve()
    vault = Path(vault_root).expanduser().resolve()
    manifest_file = sidecar / "state" / "manifest.json"
    database_file = sidecar / _EXPECTED_DATABASE

    if not sidecar.is_dir():
        raise SnapshotBindingError("Pinned sidecar checkout is missing")
    if not vault_git.is_dir() or not vault.is_dir():
        raise SnapshotBindingError("Pinned Vault checkout or Vault root is missing")
    try:
        vault.relative_to(vault_git)
    except ValueError as exc:
        raise SnapshotBindingError("vault_root must be inside the pinned Vault Git checkout") from exc
    if not manifest_file.is_file() or not database_file.is_file():
        raise SnapshotBindingError("Pinned sidecar checkout lacks manifest or SQLite database")

    try:
        sidecar_commit_sha = git_head_reader(sidecar).strip()
        vault_commit_sha = git_head_reader(vault_git).strip()
    except Exception as exc:
        raise SnapshotBindingError(f"Could not read pinned Git HEAD ({type(exc).__name__})") from exc
    if not _SHA_RE.fullmatch(sidecar_commit_sha):
        raise SnapshotBindingError("sidecar checkout HEAD is not a 40-character Git SHA")
    if not _SHA_RE.fullmatch(vault_commit_sha):
        raise SnapshotBindingError("Vault checkout HEAD is not a 40-character Git SHA")

    try:
        actual_sidecar_branch = git_branch_reader(sidecar).strip()
    except Exception as exc:
        raise SnapshotBindingError(
            "Could not verify that the sidecar checkout is on the sfra-state branch"
        ) from exc
    if actual_sidecar_branch != expected_sidecar_branch:
        raise SnapshotBindingError(
            f"Sidecar checkout branch must be {expected_sidecar_branch!r}, "
            f"found {actual_sidecar_branch!r}"
        )

    for name, root in (("sidecar", sidecar), ("Vault", vault_git)):
        try:
            dirty = git_status_reader(root)
        except Exception as exc:
            raise SnapshotBindingError(f"Could not verify {name} checkout status") from exc
        if dirty:
            raise SnapshotBindingError(f"{name} checkout is dirty; snapshot binding requires clean checkouts")

    try:
        verified_manifest = state_verifier(sidecar)
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

    source_commit = manifest.get("vault_commit_sha", manifest.get("source_commit"))
    if (
        not isinstance(source_commit, str)
        or not _SHA_RE.fullmatch(source_commit)
        or source_commit.lower() != vault_commit_sha.lower()
    ):
        raise SnapshotBindingError(
            "manifest.source_commit/vault_commit_sha does not match actual pinned Vault checkout HEAD"
        )
    if (
        "vault_commit_sha" in manifest
        and "source_commit" in manifest
        and manifest["vault_commit_sha"] != manifest["source_commit"]
    ):
        raise SnapshotBindingError("manifest Vault commit aliases are inconsistent")

    expected_db_hash = manifest.get("database_sha256")
    if not isinstance(expected_db_hash, str) or not _HASH_RE.fullmatch(expected_db_hash):
        raise SnapshotBindingError("manifest.database_sha256 is missing or malformed")
    actual_db_hash = _sha256_file(database_file)
    if actual_db_hash != expected_db_hash:
        raise SnapshotBindingError("E1 SQLite SHA-256 does not match manifest.database_sha256")

    manifest_digest = "sha256:" + hashlib.sha256(raw_manifest).hexdigest()
    ref = SnapshotRef(
        vault_commit_sha=vault_commit_sha,
        sidecar_commit_sha=sidecar_commit_sha,
        manifest_sha256=manifest_digest,
    )

    def verify_current() -> None:
        """Revalidate identities immediately around each E1/E2 read boundary."""
        # Detect path/symlink substitution rather than following a new target
        # under the previously issued SnapshotRef.
        try:
            resolved_paths = (
                sidecar.resolve(),
                database_file.resolve(),
                manifest_file.resolve(),
                vault_git.resolve(),
                vault.resolve(),
            )
        except OSError as exc:
            raise SnapshotBindingError("A pinned snapshot path is no longer available") from exc
        if resolved_paths != (sidecar, database_file, manifest_file, vault_git, vault):
            raise SnapshotBindingError("A pinned snapshot path was replaced or redirected")

        try:
            current_sidecar_head = git_head_reader(sidecar).strip()
            current_vault_head = git_head_reader(vault_git).strip()
            current_branch = git_branch_reader(sidecar).strip()
        except Exception as exc:
            raise SnapshotBindingError(
                f"Could not revalidate pinned Git identity ({type(exc).__name__})"
            ) from exc
        if current_sidecar_head.lower() != ref.sidecar_commit_sha:
            raise SnapshotBindingError("Pinned sidecar Git HEAD changed after binding")
        if current_vault_head.lower() != ref.vault_commit_sha:
            raise SnapshotBindingError("Pinned Vault Git HEAD changed after binding")
        if current_branch != expected_sidecar_branch:
            raise SnapshotBindingError("Pinned sidecar branch changed after binding")

        for name, root in (("sidecar", sidecar), ("Vault", vault_git)):
            try:
                dirty = git_status_reader(root)
            except Exception as exc:
                raise SnapshotBindingError(
                    f"Could not revalidate {name} checkout status"
                ) from exc
            if dirty:
                raise SnapshotBindingError(
                    f"Pinned {name} checkout became dirty after binding"
                )

        try:
            current_manifest_bytes = manifest_file.read_bytes()
            current_manifest = json.loads(current_manifest_bytes.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SnapshotBindingError(
                "Pinned E1 manifest changed or became unreadable after binding"
            ) from exc
        current_manifest_digest = (
            "sha256:" + hashlib.sha256(current_manifest_bytes).hexdigest()
        )
        if current_manifest_digest != ref.manifest_sha256:
            raise SnapshotBindingError("Pinned E1 manifest digest changed after binding")
        if not isinstance(current_manifest, dict) or current_manifest != manifest:
            raise SnapshotBindingError("Pinned E1 manifest content changed after binding")

        # Initial binding already ran E1's full state verifier. Rechecking
        # the exact manifest digest and full SQLite SHA-256 here proves that the
        # same E1-verified database bytes remain in place without repeating the
        # comparatively expensive SQLite integrity scan for every candidate.
        expected_current_db_hash = current_manifest.get("database_sha256")
        if (
            not isinstance(expected_current_db_hash, str)
            or not _HASH_RE.fullmatch(expected_current_db_hash)
            or _sha256_file(database_file) != expected_current_db_hash
        ):
            raise SnapshotBindingError(
                "Pinned SQLite database digest changed after snapshot binding"
            )

        # Close the verification window as much as possible: re-read the exact
        # manifest and database digests after E1's verifier has inspected them.
        try:
            final_manifest_bytes = manifest_file.read_bytes()
        except OSError as exc:
            raise SnapshotBindingError("Pinned E1 manifest disappeared during verification") from exc
        if (
            "sha256:" + hashlib.sha256(final_manifest_bytes).hexdigest()
            != ref.manifest_sha256
            or _sha256_file(database_file) != expected_current_db_hash
        ):
            raise SnapshotBindingError("Pinned sidecar changed during verification")

        try:
            if git_head_reader(sidecar).strip().lower() != ref.sidecar_commit_sha:
                raise SnapshotBindingError("Pinned sidecar Git HEAD changed during verification")
            if git_head_reader(vault_git).strip().lower() != ref.vault_commit_sha:
                raise SnapshotBindingError("Pinned Vault Git HEAD changed during verification")
            if git_status_reader(sidecar) or git_status_reader(vault_git):
                raise SnapshotBindingError("Pinned checkout became dirty during verification")
        except SnapshotBindingError:
            raise
        except Exception as exc:
            raise SnapshotBindingError("Could not complete pinned checkout verification") from exc

    # Construct only after all snapshot identities and the active verifier
    # closure have been established. Public direct construction is disabled.
    pinned = object.__new__(PinnedSnapshot)
    object.__setattr__(pinned, "ref", ref)
    object.__setattr__(pinned, "sidecar_root", sidecar)
    object.__setattr__(pinned, "database_path", database_file.resolve())
    object.__setattr__(pinned, "manifest_path", manifest_file.resolve())
    object.__setattr__(pinned, "vault_git_root", vault_git)
    object.__setattr__(pinned, "vault_root", vault)
    object.__setattr__(pinned, "manifest", manifest)
    _register_snapshot_verifier(pinned, verify_current)
    return pinned
