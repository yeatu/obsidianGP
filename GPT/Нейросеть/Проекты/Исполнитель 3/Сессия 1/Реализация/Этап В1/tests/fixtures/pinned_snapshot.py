"""Test-only factory for synthetic PinnedSnapshot subclass fixtures.

Production code must use sfra_context_integrations.snapshot.bind_pinned_snapshot.
The subclass returned here is intentionally rejected by production E1/E2/E3
consumer constructors. Tests may use consumer_seams.py to exercise adapter
methods without making the fixture acceptable to production composition.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from sfra_context_builder.models import SnapshotRef
from sfra_context_integrations.snapshot import PinnedSnapshot, SnapshotBindingError


class _FixturePinnedSnapshot(PinnedSnapshot):
    """Synthetic-only subclass with a test-controlled verifier callback."""

    __slots__ = ("_fixture_verifier",)

    def verify_current(self) -> None:
        try:
            self._fixture_verifier()
        except SnapshotBindingError:
            raise
        except Exception as exc:
            raise SnapshotBindingError("Pinned snapshot verifier failed") from exc


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
    """Build a synthetic snapshot with a test-controlled verifier callback."""
    callback = verifier if verifier is not None else (lambda: None)
    # This constructor bypass is intentionally confined to the test fixture.
    # Production consumers require type(snapshot) is PinnedSnapshot and reject
    # this subclass before invoking any overridable verification method.
    pinned = object.__new__(_FixturePinnedSnapshot)
    object.__setattr__(pinned, "ref", ref)
    object.__setattr__(pinned, "sidecar_root", sidecar_root)
    object.__setattr__(pinned, "database_path", database_path)
    object.__setattr__(pinned, "manifest_path", manifest_path)
    object.__setattr__(pinned, "vault_git_root", vault_git_root)
    object.__setattr__(pinned, "vault_root", vault_root)
    object.__setattr__(pinned, "manifest", manifest)
    object.__setattr__(pinned, "_fixture_verifier", callback)
    return pinned
