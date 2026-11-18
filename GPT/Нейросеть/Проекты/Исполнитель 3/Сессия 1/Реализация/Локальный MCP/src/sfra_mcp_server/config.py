"""Fail-closed configuration for the local SFRA MCP process."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path


class ConfigurationError(ValueError):
    """Raised when local Vault or sidecar configuration is unsafe or incomplete."""


def _required_value(values: Mapping[str, str], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{key} must be set to a non-empty value")
    return value.strip()


def _resolve_checkout(values: Mapping[str, str], key: str) -> Path:
    raw = _required_value(values, key)
    try:
        path = Path(raw).expanduser()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ConfigurationError(f"{key} is not a valid filesystem path") from exc
    if not path.is_absolute():
        raise ConfigurationError(f"{key} must be an absolute path")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ConfigurationError(f"{key} must resolve to an existing directory") from exc
    if not resolved.is_dir():
        raise ConfigurationError(f"{key} must point to a directory")

    git_marker = resolved / ".git"
    if git_marker.is_symlink() or not (git_marker.is_dir() or git_marker.is_file()):
        raise ConfigurationError(f"{key} must point to a Git checkout root")
    return resolved


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """Validated locations for two independent, local, read-only checkouts.

    This validates path shape and presence only. It does not attest a SnapshotRef.
    Snapshot binding and E1 verification remain the responsibility of the accepted
    E3 integration layer and are deliberately not bypassed by this bootstrap.
    """

    sidecar_root: Path
    vault_git_root: Path
    vault_subdir: Path
    vault_root: Path

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "ServerConfig":
        values = os.environ if environ is None else environ
        sidecar_root = _resolve_checkout(values, "SFRA_SIDECAR_ROOT")
        vault_git_root = _resolve_checkout(values, "SFRA_VAULT_GIT_ROOT")

        if _overlaps(sidecar_root, vault_git_root):
            raise ConfigurationError(
                "SFRA_SIDECAR_ROOT and SFRA_VAULT_GIT_ROOT must be independent checkouts"
            )

        raw_subdir = _required_value(values, "SFRA_VAULT_SUBDIR")
        try:
            vault_subdir = Path(raw_subdir)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ConfigurationError("SFRA_VAULT_SUBDIR is not a valid path") from exc
        if (
            vault_subdir.is_absolute()
            or not vault_subdir.parts
            or any(part in {".", ".."} for part in vault_subdir.parts)
        ):
            raise ConfigurationError(
                "SFRA_VAULT_SUBDIR must be a non-empty relative path without dot segments"
            )

        try:
            vault_root = (vault_git_root / vault_subdir).resolve(strict=True)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ConfigurationError(
                "SFRA_VAULT_SUBDIR must resolve to an existing directory"
            ) from exc
        if not vault_root.is_dir():
            raise ConfigurationError("The configured Vault root is not a directory")
        try:
            vault_root.relative_to(vault_git_root)
        except ValueError as exc:
            raise ConfigurationError(
                "The configured Vault root must remain inside SFRA_VAULT_GIT_ROOT"
            ) from exc

        state_root = sidecar_root / "state"
        manifest_path = state_root / "manifest.json"
        database_path = state_root / "structure.sqlite3"
        if state_root.is_symlink() or not state_root.is_dir():
            raise ConfigurationError(
                "The sidecar checkout must contain a regular state directory"
            )
        if (
            manifest_path.is_symlink()
            or database_path.is_symlink()
            or not manifest_path.is_file()
            or not database_path.is_file()
        ):
            raise ConfigurationError(
                "The sidecar state must contain regular manifest.json and structure.sqlite3 files"
            )

        return cls(
            sidecar_root=sidecar_root,
            vault_git_root=vault_git_root,
            vault_subdir=vault_subdir,
            vault_root=vault_root,
        )
