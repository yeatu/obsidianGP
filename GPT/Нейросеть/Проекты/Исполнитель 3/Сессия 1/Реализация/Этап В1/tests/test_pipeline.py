from __future__ import annotations

from pathlib import Path

import pytest

from sfra_context_builder import ContextBuilder, TiktokenCounter, parse_search_request
from sfra_context_integrations.pipeline import (
    ContextIntegrationPipeline,
    SourceReadRequest,
)
from sfra_context_integrations.dependency_resolver import E1DependencyResolver
from sfra_context_integrations.search_adapter import E2SearchAdapter
from sfra_context_integrations.snapshot import PinnedSnapshot
from sfra_context_integrations.source_reader import E1SourceReader
from tests.fixtures.source_reader import FixtureE1ScopeAPI, sha, snapshot


def _pinned(tmp_path, ref):
    sidecar = tmp_path / "sidecar"
    vault = tmp_path / "vault"
    sidecar.mkdir(parents=True)
    vault.mkdir(parents=True)
    database = sidecar / "structure.sqlite3"
    database.write_bytes(b"pinned fixture sidecar bytes")
    manifest = sidecar / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    return PinnedSnapshot(
        ref=ref,
        sidecar_root=sidecar,
        database_path=database,
        manifest_path=manifest,
        vault_git_root=tmp_path,
        vault_root=vault,
        manifest={"source_commit": ref.vault_commit_sha},
    )


def _request(budget=2000):
    return parse_search_request({
        "query": "original source fragment",
        "task": "C1 integration fixture",
        "budget_tokens": budget,
    })


def _engine_hit(api):
    node = api.records["node_target"]
    return {
        "node_id": node["node_id"],
        "source_path": node["source_path"],
        "node_type": node["node_type"],
        "parent_node_id": node["parent_node_id"],
        "heading_path": node["heading_path"],
        "line_start": node["line_start"],
        "line_end": node["line_end"],
        "content_hash": node["content_hash"],
        "excerpt": "search hint only",
        "match_type": "exact_heading",
        "match_reasons": ["heading_terms", "unmapped_engine_reason"],
        "relevance": {"tier": 3, "bm25": -4.75},
        "entities": [],
        "matched_aliases": [],
        # The adapter must not use this E2-derived generation.
        "index_generation": 999,
        "document_hash": node["document_hash"],
    }


class RecordingDependencyResolver:
    def __init__(self, expected_snapshot, document_hash, *, generation=7):
        self.expected_snapshot = expected_snapshot
        self.document_hash = document_hash
        self.generation = generation
        self.calls = []

    def resolve_node(self, node_id, snapshot):
        self.calls.append((node_id, snapshot))
        assert snapshot == self.expected_snapshot
        assert node_id == "node_required"
        raw_text = "Required dependency source text.\n"
        return {
            "node_id": node_id,
            "source_path": "fixtures/test-document.md",
            "heading_path": ["Test document"],
            "line_start": 6,
            "line_end": 6,
            "content_hash": sha(raw_text),
            "raw_text": raw_text,
            "match_type": "required_dependency",
            "index_generation": self.generation,
            "document_hash": self.document_hash,
        }


def _pipeline(tmp_path, *, metadata=None, dependency_resolver=None):
    ref = snapshot()
    pinned = _pinned(tmp_path, ref)
    api = FixtureE1ScopeAPI(ref)
    if metadata is not None:
        api.records["node_target"]["metadata"] = metadata
    source_reader = E1SourceReader(api, pinned, TiktokenCounter("o200k_base"))
    hit = _engine_hit(api)

    def search_call(database, query, *, entities, limit, entity_config):
        assert database == pinned.database_path
        assert query == "original source fragment"
        assert tuple(entities) == ()
        return {
            "runtime": "one-shot-memory",
            "search": {"status": "ok", "results": [hit]},
        }

    adapter = E2SearchAdapter(
        pinned,
        source_reader,
        search_call=search_call,
        search_limit=20,
    )
    pipeline = ContextIntegrationPipeline(
        pinned_snapshot=pinned,
        search_adapter=adapter,
        context_builder=ContextBuilder(TiktokenCounter("o200k_base")),
        source_reader=source_reader,
        dependency_resolver=dependency_resolver,
    )
    return pipeline, api, pinned, source_reader


def test_end_to_end_search_context_pack_and_all_scope_reads_share_one_snapshot(tmp_path):
    pipeline, api, pinned, reader = _pipeline(tmp_path)
    scopes = ("node", "parent", "neighbors", "document")

    result = pipeline.run(
        _request(),
        source_reads=tuple(
            SourceReadRequest(
                node_id="node_target",
                expected_hash=api.records["node_target"]["content_hash"],
                scope=scope,
            )
            for scope in scopes
        ),
    )

    assert result.snapshot == pinned.ref
    assert result.context_pack["schema_version"] == "sfra.context_pack.v1"
    assert result.context_pack["status"] == "complete"
    assert result.context_pack["Included"][0]["node_id"] == "node_target"
    assert result.context_pack["Included"][0]["raw_text"] == api.records["node_target"]["raw_text"]
    assert result.context_pack["Included"][0]["content_hash"] == api.records["node_target"]["content_hash"]
    assert result.search.batch.candidates[0].relevance_tier == 3
    assert result.search.batch.candidates[0].relevance_bm25 == -4.75
    assert result.search.batch.candidates[0].raw_text == api.records["node_target"]["raw_text"]
    assert result.search.batch.candidates[0].signals["match_excerpt"] == "search hint only"
    assert len(result.source_reads) == 4
    assert [item["status"] for item in result.source_reads] == ["ok"] * 4
    assert [item["requested"]["scope"] for item in result.source_reads] == list(scopes)
    assert all(call[-1] == pinned.ref.snapshot_id for call in api.scope_calls)
    assert all(item["snapshot_id"] == pinned.ref.snapshot_id for item in result.source_reads)
    assert reader is pipeline._source_reader


def test_dependency_resolution_receives_same_snapshot_and_group_is_atomic(tmp_path):
    ref = snapshot()
    temporary = tmp_path / "temp"
    temporary.mkdir()
    api = FixtureE1ScopeAPI(ref)
    api.records["node_target"]["metadata"] = {
        "preservation": "required",
        "required_with": ["node_required"],
        "parent_context_required": False,
    }
    dependency_resolver = RecordingDependencyResolver(ref, api.document_hash)
    pipeline, api, pinned, _ = _pipeline(
        tmp_path,
        metadata=api.records["node_target"]["metadata"],
        dependency_resolver=dependency_resolver,
    )

    result = pipeline.run(_request())

    included_ids = {entry["node_id"] for entry in result.context_pack["Included"]}
    assert included_ids == {"node_target", "node_required"}
    assert dependency_resolver.calls == [("node_required", pinned.ref)]


def test_dependency_from_another_document_generation_is_rejected(tmp_path):
    ref = snapshot()
    api = FixtureE1ScopeAPI(ref)
    api.records["node_target"]["metadata"] = {
        "preservation": "required",
        "required_with": ["node_required"],
        "parent_context_required": False,
    }
    resolver = RecordingDependencyResolver(ref, api.document_hash, generation=8)
    pipeline, _, _, _ = _pipeline(
        tmp_path,
        metadata=api.records["node_target"]["metadata"],
        dependency_resolver=resolver,
    )

    result = pipeline.run(_request())

    assert any(
        diagnostic["code"] == "snapshot_generation_mismatch"
        for diagnostic in result.context_pack["Diagnostics"]
    )
    assert result.context_pack["status"] == "integrity_warning"


def test_context_builder_budget_remains_atomic_through_pipeline(tmp_path):
    pipeline, _, _, _ = _pipeline(tmp_path)

    result = pipeline.run(_request(budget=1))

    assert result.context_pack["Included"] == []
    assert result.context_pack["Deferred"][0]["node_id"] == "node_target"
    assert result.context_pack["status"] == "budget_limited"


def test_pipeline_rejects_adapter_bound_to_different_snapshot(tmp_path):
    ref = snapshot()
    pinned = _pinned(tmp_path, ref)
    other_api = FixtureE1ScopeAPI(ref)
    other_reader = E1SourceReader(other_api, pinned, TiktokenCounter("o200k_base"))
    other_ref = type(ref)("d" * 40, "e" * 40, "sha256:" + "f" * 64)
    other_pinned = _pinned(tmp_path / "other", other_ref)
    adapter = E2SearchAdapter(other_pinned, other_reader, search_call=lambda *a, **k: {})
    with pytest.raises(ValueError, match="different SnapshotRef"):
        ContextIntegrationPipeline(
            pinned_snapshot=pinned,
            search_adapter=adapter,
            context_builder=ContextBuilder(TiktokenCounter("o200k_base")),
            source_reader=other_reader,
        )


def test_pipeline_does_not_read_after_e2_runtime_error(tmp_path):
    ref = snapshot()
    pinned = _pinned(tmp_path, ref)
    api = FixtureE1ScopeAPI(ref)
    reader = E1SourceReader(api, pinned, TiktokenCounter("o200k_base"))

    def fail(*args, **kwargs):
        raise OSError("fixture failure")

    adapter = E2SearchAdapter(pinned, reader, search_call=fail)
    pipeline = ContextIntegrationPipeline(
        pinned_snapshot=pinned,
        search_adapter=adapter,
        context_builder=ContextBuilder(TiktokenCounter("o200k_base")),
        source_reader=reader,
    )

    with pytest.raises(Exception, match="E2 search failed"):
        pipeline.run(
            _request(),
            source_reads=(SourceReadRequest("node_target", api.records["node_target"]["content_hash"], "node"),),
        )
    assert api.scope_calls == []


def test_default_e1_dependency_resolver_uses_current_address_then_exact_node_read(tmp_path):
    pipeline, api, pinned, _ = _pipeline(
        tmp_path,
        metadata={
            "preservation": "required",
            "required_with": ["node_parent"],
            "parent_context_required": False,
        },
    )

    result = pipeline.run(_request())

    included_ids = {entry["node_id"] for entry in result.context_pack["Included"]}
    assert included_ids == {"node_target", "node_parent"}
    assert api.resolve_calls == [(
        str(pinned.database_path),
        "node_parent",
        pinned.ref.snapshot_id,
    )]
    assert any(
        call[2:5] == ("node_parent", api.records["node_parent"]["content_hash"], "node")
        for call in api.scope_calls
    )
    assert all(call[-1] == pinned.ref.snapshot_id for call in api.scope_calls)


def test_ambiguous_dependency_is_not_replaced_and_is_diagnosed(tmp_path):
    pipeline, api, pinned, _ = _pipeline(
        tmp_path,
        metadata={
            "preservation": "required",
            "required_with": ["node_parent"],
            "parent_context_required": False,
        },
    )
    api.status_overrides["node_parent"] = "ambiguous"

    result = pipeline.run(_request())

    included_ids = {entry["node_id"] for entry in result.context_pack["Included"]}
    # Required groups are atomic: an ambiguous dependency defers the entire group.
    assert included_ids == set()
    assert any(
        item["code"] == "dependency_current_node_unavailable"
        and item["details"]["e1_status"] == "ambiguous"
        for item in result.context_pack["Diagnostics"]
    )
    assert all(call[2] != "node_parent" for call in api.scope_calls)
    assert "node_target" in {
        item["node_id"] for item in result.context_pack["Deferred"]
    }


def test_e1_dependency_diagnostics_are_scoped_to_each_pipeline_run(tmp_path):
    pipeline, api, pinned, _ = _pipeline(
        tmp_path,
        metadata={
            "preservation": "required",
            "required_with": ["node_parent"],
            "parent_context_required": False,
        },
    )
    resolver = pipeline._dependency_resolver
    api.status_overrides["node_parent"] = "ambiguous"

    first = pipeline.run(_request())
    assert any(
        item["code"] == "dependency_current_node_unavailable"
        for item in first.context_pack["Diagnostics"]
    )

    api.status_overrides.pop("node_parent")
    second = pipeline.run(_request())

    assert not any(
        item["code"] == "dependency_current_node_unavailable"
        for item in second.context_pack["Diagnostics"]
    )
    defaults = [
        item for item in second.context_pack["Diagnostics"]
        if item["code"] == "dependency_policy_defaults_applied"
    ]
    assert len(defaults) == 1
    assert defaults[0]["node_ids"] == ["node_parent"]
    assert resolver.diagnostics == [
        item for item in resolver.diagnostics
        if item["code"] == "dependency_policy_defaults_applied"
    ]
