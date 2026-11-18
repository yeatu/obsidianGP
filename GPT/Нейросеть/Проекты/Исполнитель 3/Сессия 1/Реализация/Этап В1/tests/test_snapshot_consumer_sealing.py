from __future__ import annotations
import hashlib
import json

import pytest

from sfra_context_builder import ContextBuilder, TiktokenCounter
from sfra_context_builder.models import SnapshotRef
from sfra_context_integrations.pipeline import ContextIntegrationPipeline
from sfra_context_integrations.search_adapter import E2SearchAdapter, SearchAdapterError
from sfra_context_integrations.snapshot import (
    PinnedSnapshot, SnapshotBindingError, bind_pinned_snapshot,
)
from sfra_context_integrations.source_reader import E1SourceReader, SourceReaderContractError
from tests.fixtures.source_reader import FixtureE1ScopeAPI, FixtureTokenCounter, snapshot


class MaliciousSubclass(PinnedSnapshot):
    def verify_current(self):
        # This must never be dispatched by a production consumer.
        raise AssertionError("malicious override must not run")


def _production_snapshot(tmp_path):
    sidecar = tmp_path / "sidecar"
    state = sidecar / "state"
    state.mkdir(parents=True)
    database = state / "structure.sqlite3"
    database.write_bytes(b"realistic temporary sqlite placeholder")
    manifest = {
        "database": "state/structure.sqlite3",
        "database_sha256": "sha256:" + hashlib.sha256(database.read_bytes()).hexdigest(),
        "format_version": 1,
        "indexer_version": "0.2.0",
        "source_branch": "fixture",
        "source_commit": "a" * 40,
        "source_repository": "yeatu/obsidianGP",
        "sqlite_schema_version": 2,
    }
    manifest_path = state / "manifest.json"
    raw = (json.dumps(manifest, indent=2) + "\n").encode()
    manifest_path.write_bytes(raw)
    vault_git = tmp_path / "vault-git"
    vault_root = vault_git / "ГП"
    vault_root.mkdir(parents=True)
    def head_reader(path):
        return "b" * 40 if path == sidecar.resolve() else "a" * 40
    return bind_pinned_snapshot(
        sidecar_root=sidecar,
        vault_git_root=vault_git,
        vault_root=vault_root,
        state_verifier=lambda _: manifest,
        git_head_reader=head_reader,
        git_branch_reader=lambda _: "sfra-state",
        git_status_reader=lambda _: "",
    )


def test_production_consumers_reject_subclass_before_virtual_verifier_or_e1_calls():
    malicious = object.__new__(MaliciousSubclass)
    api = FixtureE1ScopeAPI(snapshot())

    with pytest.raises(TypeError, match="exact factory-created PinnedSnapshot"):
        E1SourceReader(api, malicious, FixtureTokenCounter())
    assert api.scope_calls == []
    assert api.resolve_calls == []

    with pytest.raises(TypeError, match="exact factory-created PinnedSnapshot"):
        E2SearchAdapter(malicious, object())

    with pytest.raises(TypeError, match="exact factory-created PinnedSnapshot"):
        ContextIntegrationPipeline(
            pinned_snapshot=malicious,
            search_adapter=None,
            context_builder=None,
            source_reader=None,
        )


def test_exact_but_unregistered_snapshot_fails_closed_at_all_consumer_boundaries():
    forged = object.__new__(PinnedSnapshot)
    api = FixtureE1ScopeAPI(snapshot())

    with pytest.raises(SourceReaderContractError) as reader_error:
        E1SourceReader(api, forged, FixtureTokenCounter())
    assert reader_error.value.code == "snapshot_changed"
    assert api.scope_calls == []
    assert api.resolve_calls == []

    with pytest.raises(SearchAdapterError) as search_error:
        E2SearchAdapter(forged, object())
    assert search_error.value.code == "snapshot_changed"

    with pytest.raises(SnapshotBindingError, match="no active verifier binding"):
        ContextIntegrationPipeline(
            pinned_snapshot=forged,
            search_adapter=None,
            context_builder=None,
            source_reader=None,
        )


def test_factory_created_exact_type_is_accepted_by_all_production_consumers(tmp_path):
    pinned = _production_snapshot(tmp_path)
    assert type(pinned) is PinnedSnapshot

    api = FixtureE1ScopeAPI(pinned.ref)
    reader = E1SourceReader(api, pinned, FixtureTokenCounter())
    adapter = E2SearchAdapter(
        pinned,
        reader,
        search_call=lambda *args, **kwargs: {
            "search": {"status": "not_found_in_retrieval", "results": []}
        },
    )
    pipeline = ContextIntegrationPipeline(
        pinned_snapshot=pinned,
        search_adapter=adapter,
        context_builder=ContextBuilder(TiktokenCounter("o200k_base")),
        source_reader=reader,
    )

    assert reader.pinned_snapshot is pinned
    assert adapter.pinned_snapshot is pinned
    assert pipeline._pinned is pinned
