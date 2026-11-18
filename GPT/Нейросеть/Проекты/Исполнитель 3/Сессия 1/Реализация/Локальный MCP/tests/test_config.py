from __future__ import annotations

from pathlib import Path

import pytest

from sfra_mcp_server.config import ConfigurationError, ServerConfig


def make_checkouts(tmp_path: Path) -> dict[str, str]:
    sidecar = tmp_path / "sidecar"
    (sidecar / ".git").mkdir(parents=True)
    state = sidecar / "state"
    state.mkdir()
    (state / "manifest.json").write_text("{}", encoding="utf-8")
    (state / "structure.sqlite3").write_bytes(b"fixture-db")

    vault_git = tmp_path / "vault"
    (vault_git / ".git").mkdir(parents=True)
    (vault_git / "ГП").mkdir()

    return {
        "SFRA_SIDECAR_ROOT": str(sidecar),
        "SFRA_VAULT_GIT_ROOT": str(vault_git),
        "SFRA_VAULT_SUBDIR": "ГП",
    }


def test_from_env_accepts_independent_fixture_checkouts(tmp_path: Path) -> None:
    config = ServerConfig.from_env(make_checkouts(tmp_path))

    assert config.sidecar_root == (tmp_path / "sidecar").resolve()
    assert config.vault_git_root == (tmp_path / "vault").resolve()
    assert config.vault_root == (tmp_path / "vault" / "ГП").resolve()
    assert config.vault_subdir == Path("ГП")


@pytest.mark.parametrize(
    "missing",
    ["SFRA_SIDECAR_ROOT", "SFRA_VAULT_GIT_ROOT", "SFRA_VAULT_SUBDIR"],
)
def test_missing_required_configuration_fails_closed(
    tmp_path: Path,
    missing: str,
) -> None:
    values = make_checkouts(tmp_path)
    values.pop(missing)

    with pytest.raises(ConfigurationError, match=missing):
        ServerConfig.from_env(values)


def test_relative_checkout_path_is_rejected(tmp_path: Path) -> None:
    values = make_checkouts(tmp_path)
    values["SFRA_SIDECAR_ROOT"] = "sidecar"

    with pytest.raises(ConfigurationError, match="absolute path"):
        ServerConfig.from_env(values)


@pytest.mark.parametrize("subdir", ["", ".", "../outside", "/tmp/outside"])
def test_invalid_vault_subdir_is_rejected(tmp_path: Path, subdir: str) -> None:
    values = make_checkouts(tmp_path)
    values["SFRA_VAULT_SUBDIR"] = subdir

    with pytest.raises(ConfigurationError):
        ServerConfig.from_env(values)


def test_vault_subdir_symlink_escape_is_rejected(tmp_path: Path) -> None:
    values = make_checkouts(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "vault" / "external").symlink_to(outside, target_is_directory=True)
    values["SFRA_VAULT_SUBDIR"] = "external"

    with pytest.raises(ConfigurationError, match="inside"):
        ServerConfig.from_env(values)


def test_sidecar_and_vault_must_be_independent_checkouts(tmp_path: Path) -> None:
    values = make_checkouts(tmp_path)
    (tmp_path / ".git").mkdir()
    values["SFRA_VAULT_GIT_ROOT"] = str(tmp_path)

    with pytest.raises(ConfigurationError, match="independent"):
        ServerConfig.from_env(values)


def test_sidecar_state_directory_symlink_is_rejected(tmp_path: Path) -> None:
    values = make_checkouts(tmp_path)
    state = tmp_path / "sidecar" / "state"
    outside_state = tmp_path / "outside-state"
    outside_state.mkdir()
    (state / "manifest.json").unlink()
    (state / "structure.sqlite3").unlink()
    state.rmdir()
    state.symlink_to(outside_state, target_is_directory=True)

    with pytest.raises(ConfigurationError, match="regular state directory"):
        ServerConfig.from_env(values)


def test_sidecar_requires_manifest_and_database_files(tmp_path: Path) -> None:
    values = make_checkouts(tmp_path)
    (tmp_path / "sidecar" / "state" / "structure.sqlite3").unlink()

    with pytest.raises(ConfigurationError, match="manifest.json and structure.sqlite3"):
        ServerConfig.from_env(values)
