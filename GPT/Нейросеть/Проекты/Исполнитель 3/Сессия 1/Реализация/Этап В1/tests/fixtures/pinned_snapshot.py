"""Test-only factory for sealed PinnedSnapshot fixtures.

Production code must use sfra_context_integrations.snapshot.bind_pinned_snapshot.
This helper is intentionally kept under tests/fixtures so a no-op verifier cannot
become a production composition path.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from sfra_context_builder.models import SnapshotRef
from sfra_context_integrations.snapshot import (
    PinnedSnapshot,
    _SNAPSHOT_VERIFIER_SEAL,
    _SnapshotVerifier,
)


def make_test_pinned_snapshot(
    *,
    ref: SnapshotRef,
    sidecar_root: Path,
    database_path: Path,
    manifest_path: Path,
    vault_git_root: Path,
    vault_root: Path,
    manifest: Mapping[str, Any],
    verifier: Callable[[], None] | None = None,
) -> PinnedSnapshot:
    """Build an explicitly test-only snapshot with a controllable verifier."""
    callback = verifier if verifier is not None else (lambda: None)
    return PinnedSnapshot(
        ref=ref,
        sidecar_root=sidecar_root,
        database_path=database_path,
        manifest_path=manifest_path,
        vault_git_root=vault_git_root,
        vault_root=vault_root,
        manifest=manifest,
        _verifier=_SnapshotVerifier(callback, _seal=_SNAPSHOT_VERIFIER_SEAL),
    )
