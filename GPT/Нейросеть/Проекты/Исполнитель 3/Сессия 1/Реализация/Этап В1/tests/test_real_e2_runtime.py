from __future__ import annotations

import hashlib
import json
import sqlite3

from sfra_context_builder import TiktokenCounter, parse_search_request
from tests.fixtures.pinned_snapshot import make_test_pinned_snapshot
from tests.fixtures.consumer_seams import make_test_source_reader, make_test_search_adapter
from tests.fixtures.source_reader import FixtureE1ScopeAPI, FixtureTokenCounter, sha, snapshot


def _create_structural_fixture(path, api):
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE documents (
                document_pk INTEGER PRIMARY KEY,
                source_path TEXT NOT NULL,
                source_sha256 TEXT,
                status TEXT NOT NULL,
                generation INTEGER NOT NULL
            );
            CREATE TABLE structural_nodes (
                node_pk INTEGER PRIMARY KEY,
                document_pk INTEGER NOT NULL,
                local_key TEXT NOT NULL,
                node_id TEXT,
                parent_node_pk INTEGER,
                node_type TEXT NOT NULL,
                heading_path_json TEXT NOT NULL,
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                char_start INTEGER NOT NULL,
                char_end INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                status TEXT NOT NULL,
                stale_generation INTEGER
            );
            """
        )
        connection.execute(
            """
            INSERT INTO documents(
                document_pk, source_path, source_sha256, status, generation
            ) VALUES (1, ?, ?, 'active', 7)
            """,
            ("fixtures/test-document.md", api.document_hash),
        )
        node_pk_by_id = {
            node_id: index
            for index, node_id in enumerate(api.records, start=1)
        }
        for node_id, node in api.records.items():
            connection.execute(
                """
                INSERT INTO structural_nodes(
                    node_pk, document_pk, local_key, node_id, parent_node_pk,
                    node_type, heading_path_json, line_start, line_end,
                    char_start, char_end, content_hash, raw_text, status,
                    stale_generation
                ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', NULL)
                """,
                (
                    node_pk_by_id[node_id],
                    node_id,
                    node_id,
                    (
                        node_pk_by_id[node["parent_node_id"]]
                        if node["parent_node_id"] is not None
                        else None
                    ),
                    node["node_type"],
                    json.dumps(node["heading_path"], ensure_ascii=False),
                    node["line_start"],
                    node["line_end"],
                    node["line_start"] * 100,
                    node["line_start"] * 100 + len(node["raw_text"]),
                    node["content_hash"],
                    node["raw_text"],
                ),
            )
        connection.commit()
    finally:
        connection.close()


def test_default_adapter_invokes_real_e2_runtime_and_uses_e1_exact_text(tmp_path):
    ref = snapshot()
    api = FixtureE1ScopeAPI(ref)
    long_text = "Target original source fragment. " + ("additional verified source text. " * 24) + "\n"
    api.records["node_target"]["raw_text"] = long_text
    api.records["node_target"]["content_hash"] = sha(long_text)
    api.document_text = api.document_text.replace(
        "Target original source fragment.\n", long_text
    )
    api.document_hash = sha(api.document_text)
    for item in api.records.values():
        item["document_hash"] = api.document_hash
        item["source_sha256"] = api.document_hash
    database = tmp_path / "structure.sqlite3"
    _create_structural_fixture(database, api)
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    sidecar = tmp_path / "sidecar"
    vault_git = tmp_path / "vault-git"
    vault = vault_git / "ГП"
    sidecar.mkdir()
    vault.mkdir(parents=True)
    (sidecar / "state").mkdir()
    pinned = make_test_pinned_snapshot(
        ref=ref,
        sidecar_root=sidecar,
        database_path=database,
        manifest_path=sidecar / "state" / "manifest.json",
        vault_git_root=vault_git,
        vault_root=vault,
        manifest={"source_commit": ref.vault_commit_sha},
    )
    reader = make_test_source_reader(api, pinned, TiktokenCounter("o200k_base"))
    adapter = make_test_search_adapter(
        pinned,
        reader,
        search_limit=20,
    )

    from sfra_search.runtime import search_structural_database

    assert callable(search_structural_database)
    result = adapter.search(
        parse_search_request({
            "query": "Target original source fragment",
            "task": None,
            "budget_tokens": 1500,
        })
    )

    assert result.engine_status == "ok"
    assert result.batch.complete is True
    assert result.batch.truncated_by_limit is False
    assert len(result.batch.candidates) == 1
    candidate = result.batch.candidates[0]
    source = api.records["node_target"]

    assert candidate.node_id == source["node_id"]
    assert candidate.content_hash == source["content_hash"]
    assert candidate.raw_text == source["raw_text"]
    assert candidate.raw_text != candidate.signals["match_excerpt"]
    assert candidate.index_generation == 7
    assert candidate.document_hash == api.document_hash
    assert candidate.relevance_tier in range(1, 7)
    assert isinstance(candidate.relevance_bm25, float)
    assert candidate.match_type
    assert api.scope_calls == [
        (
            str(pinned.database_path),
            str(pinned.vault_root),
            "node_target",
            source["content_hash"],
            "node",
            ref.snapshot_id,
        )
    ]
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
