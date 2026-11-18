from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import sfra_mcp_server.composition as composition
from sfra_context_builder import SnapshotRef
from sfra_indexer import verify_state_directory
from sfra_mcp_server.config import ServerConfig
from sfra_mcp_server.composition import (
    ApplicationServices, CompositionError, E1SourceAPIAdapter,
    build_application_services,
)


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


def test_e1_adapter_delegates_to_published_e1_functions(monkeypatch) -> None:
    calls: list[tuple[str, tuple, dict]] = []

    class Result:
        def to_dict(self):
            return {"status": "ok", "snapshot_id": "pinned"}

    def fake_read(*args, **kwargs):
        calls.append(("read", args, kwargs))
        return Result()

    def fake_resolve(*args, **kwargs):
        calls.append(("resolve", args, kwargs))
        return Result()

    fake_e1 = SimpleNamespace(
        read_source_scope=fake_read,
        resolve_current_node=fake_resolve,
    )
    monkeypatch.setattr(composition, "_require_package", lambda name: fake_e1)
    adapter = E1SourceAPIAdapter()
    assert adapter.read_source_scope(
        "/sidecar/state/structure.sqlite3", "/vault/ГП", "node_test",
        "sha256:" + "a" * 64, scope="node", snapshot_id="pinned",
    ) == {"status": "ok", "snapshot_id": "pinned"}
    assert adapter.resolve_current_node(
        "/sidecar/state/structure.sqlite3", "node_test", snapshot_id="pinned",
    ) == {"status": "ok", "snapshot_id": "pinned"}
    assert [entry[0] for entry in calls] == ["read", "resolve"]
    assert calls[0][1][0] == "/sidecar/state/structure.sqlite3"
    assert calls[0][2]["scope"] == "node"
    assert calls[1][2]["snapshot_id"] == "pinned"


def test_application_composition_uses_one_verified_snapshot_and_search_services(
    tmp_path: Path, monkeypatch
) -> None:
    config = valid_config(tmp_path)
    ref = SnapshotRef("a" * 40, "b" * 40, "sha256:" + "c" * 64)
    pinned = SimpleNamespace(ref=ref)
    calls: list[tuple[str, object]] = []
    fake_reader = None

    def fake_bind(**kwargs):
        calls.append(("bind", kwargs))
        return pinned

    class FakeCounter:
        pass

    class FakeReader:
        def __init__(self, api, snapshot, counter):
            calls.append(("reader", (api, snapshot, counter)))
            assert isinstance(api, E1SourceAPIAdapter)
            assert snapshot is pinned
            self.pinned_snapshot = snapshot

    def make_reader(api, snapshot, counter):
        nonlocal fake_reader
        fake_reader = FakeReader(api, snapshot, counter)
        return fake_reader

    class FakeSearchAdapter:
        def __init__(self, snapshot, reader):
            calls.append(("search_adapter", (snapshot, reader)))
            assert snapshot is pinned and reader is fake_reader
            self.source_reader = reader

    class FakeContextBuilder:
        def __init__(self, counter):
            calls.append(("context_builder", counter))

    class FakePipeline:
        def __init__(self, **kwargs):
            calls.append(("pipeline", kwargs))
            assert kwargs["pinned_snapshot"] is pinned
            assert kwargs["search_adapter"].source_reader is fake_reader
            assert kwargs["source_reader"] is fake_reader
            self.kwargs = kwargs

    class FakeSearchService:
        def __init__(self, pipeline_arg):
            assert pipeline_arg.kwargs["pinned_snapshot"] is pinned

    fake_e1 = SimpleNamespace(
        verify_state_directory=verify_state_directory,
        read_source_scope=lambda *args, **kwargs: None,
        resolve_current_node=lambda *args, **kwargs: None,
    )
    fake_b1 = SimpleNamespace(
        TiktokenCounter=FakeCounter,
        ContextBuilder=FakeContextBuilder,
    )
    fake_integration = SimpleNamespace(
        bind_pinned_snapshot=fake_bind,
        E1SourceReader=make_reader,
        E2SearchAdapter=FakeSearchAdapter,
        ContextIntegrationPipeline=FakePipeline,
        SearchVaultService=FakeSearchService,
    )
    modules = {
        "sfra_indexer": fake_e1,
        "sfra_context_builder": fake_b1,
        "sfra_context_integrations": fake_integration,
    }
    monkeypatch.setattr(composition, "_require_package", lambda name: modules[name])

    # Test-local monkeypatches only. Production cannot inject a verifier/snapshot.
    result = build_application_services(config)
    bind_kwargs = dict(calls[0][1])
    assert bind_kwargs["sidecar_root"] == config.sidecar_root
    assert bind_kwargs["vault_git_root"] == config.vault_git_root
    assert bind_kwargs["vault_root"] == config.vault_root
    assert bind_kwargs["state_verifier"] is verify_state_directory
    assert isinstance(result, ApplicationServices)
    assert result.pinned_snapshot is pinned
    assert result.source_reader is fake_reader
    assert result.snapshot == ref
    assert result.search_vault is not None
    assert not hasattr(result, "read_source")


def test_missing_local_dependency_fails_closed(tmp_path: Path, monkeypatch) -> None:
    config = valid_config(tmp_path)

    def missing_package(name: str):
        raise CompositionError(f"Required local package {name!r} is unavailable")

    monkeypatch.setattr(composition, "_require_package", missing_package)
    with pytest.raises(CompositionError, match="Required local package"):
        build_application_services(config)


def test_application_composition_fails_closed_when_binding_fails(
    tmp_path: Path, monkeypatch
) -> None:
    config = valid_config(tmp_path)
    fake_e1 = SimpleNamespace(verify_state_directory=verify_state_directory)
    fake_b1 = SimpleNamespace()
    fake_integration = SimpleNamespace(
        bind_pinned_snapshot=lambda **kwargs: (_ for _ in ()).throw(
            ValueError("fixture snapshot rejected")
        )
    )
    modules = {
        "sfra_indexer": fake_e1,
        "sfra_context_builder": fake_b1,
        "sfra_context_integrations": fake_integration,
    }
    monkeypatch.setattr(composition, "_require_package", lambda name: modules[name])
    with pytest.raises(CompositionError, match="composition failed"):
        build_application_services(config)
