from __future__ import annotations

from pathlib import Path
import subprocess

from sfra_context_integrations import SearchVaultService
from sfra_indexer import create_state_snapshot, index_vault
from sfra_mcp_server.composition import build_application_services
from sfra_mcp_server.config import ServerConfig


def run_git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def init_checkout(root: Path, branch: str) -> None:
    root.mkdir(parents=True)
    run_git(root, "init", "--initial-branch", branch)
    run_git(root, "config", "user.name", "SFRA fixture")
    run_git(root, "config", "user.email", "sfra-fixture@example.invalid")


def commit_checkout(root: Path, message: str) -> str:
    run_git(root, "add", "-A")
    run_git(root, "commit", "-m", message)
    return run_git(root, "rev-parse", "HEAD")


def test_real_fixture_binds_and_composes_one_verified_search_snapshot(
    tmp_path: Path,
) -> None:
    # This fixture creates disposable repositories and an ephemeral SQLite DB.
    # No user Vault, production sidecar, or source operation is accessed.
    vault_git_root = tmp_path / "vault"
    init_checkout(vault_git_root, "main")
    vault_root = vault_git_root / "ГП"
    vault_root.mkdir()
    (vault_root / "fixture.md").write_text(
        "# Fixture note\n\nSynthetic SFRA integration fixture.\n",
        encoding="utf-8",
    )
    vault_sha = commit_checkout(vault_git_root, "synthetic vault fixture")

    index_dir = tmp_path / "indexer-output"
    indexed = index_vault(vault_root, index_dir)

    sidecar_root = tmp_path / "sidecar"
    init_checkout(sidecar_root, "sfra-state")
    create_state_snapshot(
        indexed.database_path,
        sidecar_root,
        source_repository="yeatu/obsidianGP",
        vault_ref="main",
        vault_commit_sha=vault_sha,
        workflow_run_id="fixture-only",
    )
    commit_checkout(sidecar_root, "synthetic sidecar fixture")

    config = ServerConfig.from_env({
        "SFRA_SIDECAR_ROOT": str(sidecar_root),
        "SFRA_VAULT_GIT_ROOT": str(vault_git_root),
        "SFRA_VAULT_SUBDIR": "ГП",
    })
    services = build_application_services(config)

    assert isinstance(services.search_vault, SearchVaultService)
    assert services.snapshot.vault_commit_sha == vault_sha
    assert services.snapshot.sidecar_commit_sha == run_git(
        sidecar_root, "rev-parse", "HEAD"
    )
    assert services.snapshot.snapshot_id == (
        f"{services.snapshot.vault_commit_sha}:"
        f"{services.snapshot.sidecar_commit_sha}:"
        f"{services.snapshot.manifest_sha256}"
    )
    # Exercise the real verifier, but deliberately do not read source content.
    services.pinned_snapshot.verify_current()
