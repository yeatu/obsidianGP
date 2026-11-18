from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp.server import MCPServer

import sfra_mcp_server.server as server_module
from sfra_mcp_server.config import ServerConfig
from sfra_mcp_server.server import ServerRuntime, build_runtime, run_stdio


def valid_config(tmp_path: Path) -> ServerConfig:
    sidecar = tmp_path / "sidecar"
    (sidecar / ".git").mkdir(parents=True)
    (sidecar / "state").mkdir()
    (sidecar / "state" / "manifest.json").write_text("{}", encoding="utf-8")
    (sidecar / "state" / "structure.sqlite3").write_bytes(b"fixture-db")
    vault = tmp_path / "vault"
    (vault / ".git").mkdir(parents=True)
    (vault / "ГП").mkdir()
    return ServerConfig.from_env({
        "SFRA_SIDECAR_ROOT": str(sidecar),
        "SFRA_VAULT_GIT_ROOT": str(vault),
        "SFRA_VAULT_SUBDIR": "ГП",
    })


def fake_services():
    return SimpleNamespace(
        pinned_snapshot=object(), source_reader=object(), pipeline=object(),
        search_vault=object(),
    )


def test_build_runtime_composes_services_and_registers_tool_slots(
    tmp_path: Path, monkeypatch
) -> None:
    services = fake_services()
    monkeypatch.setattr(server_module, "build_application_services", lambda config: services)
    runtime = build_runtime(valid_config(tmp_path))
    assert isinstance(runtime, ServerRuntime)
    assert isinstance(runtime.server, MCPServer)
    assert runtime.services is services


def test_build_runtime_rejects_unvalidated_config() -> None:
    with pytest.raises(TypeError, match="ServerConfig"):
        build_runtime(object())  # type: ignore[arg-type]


def test_stdio_runner_selects_only_stdio_transport(
    tmp_path: Path, monkeypatch
) -> None:
    services = fake_services()
    monkeypatch.setattr(server_module, "build_application_services", lambda config: services)
    runtime = build_runtime(valid_config(tmp_path))
    calls: list[str] = []

    class FakeServer:
        def run(self, *, transport: str) -> None:
            calls.append(transport)

    object.__setattr__(runtime, "server", FakeServer())
    run_stdio(runtime)
    assert calls == ["stdio"]


def test_stdio_runner_rejects_arbitrary_runtime() -> None:
    with pytest.raises(TypeError, match="ServerRuntime"):
        run_stdio(object())  # type: ignore[arg-type]
