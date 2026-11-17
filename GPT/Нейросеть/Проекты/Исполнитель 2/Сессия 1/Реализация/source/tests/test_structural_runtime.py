from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from sfra_search.cli import main as cli_main

from sfra_search import (
    StructuralDatabaseError,
    calculate_content_hash,
    get_source_node,
    load_current_nodes,
    search_structural_database,
)


def create_executor1_database(path: Path) -> tuple[str, str, str]:
    source_text = "Остановка кровообращения произошла в больнице."
    node_id = "node_executor1_0001"
    content_hash = calculate_content_hash(source_text)
    document_hash = "sha256:" + hashlib.sha256(
        ("# Генрих Фауст\n\n" + source_text + "\n").encode("utf-8")
    ).hexdigest()
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE documents (
            document_pk INTEGER PRIMARY KEY,
            source_path TEXT NOT NULL,
            status TEXT NOT NULL,
            source_sha256 TEXT
        );
        CREATE TABLE structural_nodes (
            node_pk INTEGER PRIMARY KEY,
            document_pk INTEGER NOT NULL,
            node_id TEXT,
            parent_node_pk INTEGER,
            node_type TEXT NOT NULL,
            heading_path_json TEXT NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            char_start INTEGER NOT NULL,
            char_end INTEGER NOT NULL,
            content_hash TEXT,
            raw_text TEXT NOT NULL,
            status TEXT NOT NULL,
            stale_generation INTEGER
        );
        """
    )
    connection.execute(
        "INSERT INTO documents VALUES (1, ?, 'active', ?)",
        ("персонажи/Генрих Фауст.md", document_hash),
    )
    connection.execute(
        """INSERT INTO structural_nodes VALUES
           (1, 1, ?, NULL, 'document', '[]', 1, 3, 0, 64, ?, ?, 'active', NULL)""",
        ("node_executor1_root", calculate_content_hash("# Генрих Фауст\n\n" + source_text + "\n"),
         "# Генрих Фауст\n\n" + source_text + "\n"),
    )
    connection.execute(
        """INSERT INTO structural_nodes VALUES
           (2, 1, ?, 1, 'quote', '[\"Предыстория\"]', 3, 3, 17, ?, ?, ?, 'active', NULL)""",
        (node_id, len(("# Генрих Фауст\n\n" + source_text).encode("utf-8")),
         content_hash, source_text),
    )
    # These rows must not enter the current search index.
    connection.execute(
        """INSERT INTO structural_nodes VALUES
           (3, 1, 'node_stale', 1, 'quote', '[]', 4, 4, 65, 70,
            ?, 'устаревший фрагмент', 'stale', 2)""",
        (calculate_content_hash("устаревший фрагмент"),),
    )
    connection.execute(
        "INSERT INTO documents VALUES (2, 'deleted/old.md', 'deleted', NULL)"
    )
    connection.execute(
        """INSERT INTO structural_nodes VALUES
           (4, 2, 'node_deleted_doc', NULL, 'document', '[]', 1, 1, 0, 3,
            ?, 'old', 'active', NULL)""",
        (calculate_content_hash("old"),),
    )
    connection.commit()
    connection.close()
    return node_id, content_hash, document_hash


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_load_current_nodes_preserves_executor1_identity_and_filters_stale(tmp_path):
    db_path = tmp_path / "structure.sqlite3"
    node_id, content_hash, document_hash = create_executor1_database(db_path)
    before = sha256_file(db_path)

    nodes, summary = load_current_nodes(db_path)

    assert [node["node_id"] for node in nodes] == ["node_executor1_root", node_id]
    selected = next(node for node in nodes if node["node_id"] == node_id)
    assert selected["content_hash"] == content_hash
    assert selected["document_hash"] == document_hash
    assert selected["parent_node_id"] == "node_executor1_root"
    assert summary.documents_total == 2
    assert summary.documents_active == 1
    assert summary.nodes_current == 2
    assert sha256_file(db_path) == before


def test_one_shot_search_returns_executor1_node_address_and_original_text(tmp_path):
    db_path = tmp_path / "structure.sqlite3"
    node_id, content_hash, document_hash = create_executor1_database(db_path)
    before = sha256_file(db_path)

    report = search_structural_database(db_path, "остановка кровообращения")

    assert report["runtime"] == "one-shot-memory"
    assert report["source_index"]["nodes_current"] == 2
    hits = report["search"]["results"]
    hit = next(item for item in hits if item["node_id"] == node_id)
    assert hit["content_hash"] == content_hash
    assert hit["document_hash"] == document_hash
    assert hit["relevance"]["tier"] <= 5

    source = get_source_node(db_path, hit["node_id"], hit["content_hash"])
    assert source is not None
    assert source["raw_text"] == "Остановка кровообращения произошла в больнице."
    assert source["content_hash"] == hit["content_hash"]
    assert sha256_file(db_path) == before


def test_source_lookup_requires_both_node_id_and_content_hash(tmp_path):
    db_path = tmp_path / "structure.sqlite3"
    node_id, content_hash, _ = create_executor1_database(db_path)
    assert get_source_node(db_path, node_id, "sha256:" + "0" * 64) is None
    with pytest.raises(ValueError, match="both required"):
        get_source_node(db_path, node_id, "")


def test_missing_executor1_identity_is_rejected_not_regenerated(tmp_path):
    db_path = tmp_path / "structure.sqlite3"
    create_executor1_database(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute(
        """INSERT INTO structural_nodes VALUES
           (5, 1, NULL, 1, 'quote', '[]', 4, 4, 66, 67,
            NULL, 'unidentified', 'active', NULL)"""
    )
    connection.commit()
    connection.close()
    with pytest.raises(StructuralDatabaseError, match="refuses to manufacture identities"):
        load_current_nodes(db_path)


def test_bad_structural_content_hash_is_rejected(tmp_path):
    db_path = tmp_path / "structure.sqlite3"
    create_executor1_database(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute(
        "UPDATE structural_nodes SET content_hash=? WHERE node_id=?",
        ("sha256:" + "0" * 64, "node_executor1_0001"),
    )
    connection.commit()
    connection.close()
    with pytest.raises(StructuralDatabaseError, match="content_hash mismatch"):
        load_current_nodes(db_path)


def test_structural_input_is_opened_read_only(tmp_path):
    db_path = tmp_path / "structure.sqlite3"
    create_executor1_database(db_path)
    connection = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        connection.execute("UPDATE documents SET status='deleted'")
    connection.close()


def test_entity_registry_config_can_be_applied_in_one_shot(tmp_path):
    db_path = tmp_path / "structure.sqlite3"
    node_id, content_hash, _ = create_executor1_database(db_path)
    config_path = tmp_path / "entities.json"
    config_path.write_text(json.dumps({
        "entities": [{
            "entity_id": "entity_genrih",
            "canonical_name": "Генрих Фауст",
            "aliases": [{"text": "Генрих", "status": "confirmed"}],
            "primary_source_path": "персонажи/Генрих Фауст.md",
        }]
    }, ensure_ascii=False), encoding="utf-8")

    report = search_structural_database(
        db_path, "", entities=["Генрих"], entity_config=config_path,
    )
    assert report["entities_loaded"] == 1
    assert report["search"]["status"] == "ok"
    assert any(hit["node_id"] == node_id and hit["content_hash"] == content_hash
               for hit in report["search"]["results"])


def test_run_once_cli_does_not_create_persistent_search_database(tmp_path, capsys):
    source_db = tmp_path / "structure.sqlite3"
    create_executor1_database(source_db)
    persistent_db = tmp_path / "must-not-exist.sqlite3"

    exit_code = cli_main([
        "--db", str(persistent_db), "run-once",
        "--source-db", str(source_db), "--query", "остановка кровообращения",
    ])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["runtime"] == "one-shot-memory"
    assert payload["search"]["status"] == "ok"
    assert not persistent_db.exists()


def test_get_source_cli_resolves_exact_pair(tmp_path, capsys):
    source_db = tmp_path / "structure.sqlite3"
    node_id, content_hash, _ = create_executor1_database(source_db)

    exit_code = cli_main([
        "get-source", "--source-db", str(source_db),
        "--node-id", node_id, "--content-hash", content_hash,
    ])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["node_id"] == node_id
    assert payload["content_hash"] == content_hash
    assert payload["raw_text"] == "Остановка кровообращения произошла в больнице."


def test_empty_source_span_preserves_executor1_zero_end_line(tmp_path):
    db_path = tmp_path / "structure.sqlite3"
    create_executor1_database(db_path)
    empty_hash = calculate_content_hash("")
    connection = sqlite3.connect(db_path)
    connection.execute(
        """UPDATE structural_nodes
           SET line_start=1, line_end=0, raw_text='', content_hash=?
           WHERE node_id='node_executor1_root'""",
        (empty_hash,),
    )
    connection.commit()
    connection.close()
    before = sha256_file(db_path)

    nodes, summary = load_current_nodes(db_path)
    root = next(node for node in nodes if node["node_id"] == "node_executor1_root")
    assert root["line_start"] == 1
    assert root["line_end"] == 0
    assert root["raw_text"] == ""
    assert root["content_hash"] == empty_hash

    source = get_source_node(db_path, "node_executor1_root", empty_hash)
    assert source is not None
    assert source["line_start"] == 1
    assert source["line_end"] == 0
    assert source["raw_text"] == ""
    assert sha256_file(db_path) == before


def _insert_non_active_status_nodes(db_path: Path) -> dict[str, tuple[str, str]]:
    texts = {
        "ambiguous": "неоднозначный маркер sfra",
        "stale_status": "устаревший статус маркер sfra",
        "stale_generation": "устаревшее поколение маркер sfra",
        "deleted": "удалённый статус маркер sfra",
    }
    rows = [
        (5, 1, "node_ambiguous", 1, "quote", "[]", 4, 4, 65, 65 + len(texts["ambiguous"]),
         calculate_content_hash(texts["ambiguous"]), texts["ambiguous"], "ambiguous", None),
        (6, 1, "node_stale_status", 1, "quote", "[]", 5, 5, 120, 120 + len(texts["stale_status"]),
         calculate_content_hash(texts["stale_status"]), texts["stale_status"], "stale", 2),
        (7, 1, "node_stale_generation", 1, "quote", "[]", 6, 6, 180, 180 + len(texts["stale_generation"]),
         calculate_content_hash(texts["stale_generation"]), texts["stale_generation"], "active", 3),
        (8, 1, "node_deleted_status", 1, "quote", "[]", 7, 7, 250, 250 + len(texts["deleted"]),
         calculate_content_hash(texts["deleted"]), texts["deleted"], "deleted", None),
    ]
    connection = sqlite3.connect(db_path)
    connection.executemany(
        """INSERT INTO structural_nodes
           (node_pk,document_pk,node_id,parent_node_pk,node_type,heading_path_json,
            line_start,line_end,char_start,char_end,content_hash,raw_text,status,stale_generation)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    connection.commit()
    connection.close()
    suffixes = {
        "ambiguous": "ambiguous",
        "stale_status": "stale_status",
        "stale_generation": "stale_generation",
        "deleted": "deleted_status",
    }
    return {
        key: (f"node_{suffixes[key]}", calculate_content_hash(value))
        for key, value in texts.items()
    }


def test_active_only_policy_excludes_ambiguous_stale_and_deleted_nodes(tmp_path):
    db_path = tmp_path / "structure.sqlite3"
    active_node_id, active_hash, _ = create_executor1_database(db_path)
    rejected = _insert_non_active_status_nodes(db_path)

    nodes, summary = load_current_nodes(db_path)
    node_ids = {node["node_id"] for node in nodes}
    assert node_ids == {"node_executor1_root", active_node_id}
    assert summary.nodes_current == 2

    active_report = search_structural_database(db_path, "остановка кровообращения")
    active_hits = active_report["search"]["results"]
    assert any(hit["node_id"] == active_node_id for hit in active_hits)
    active_source = get_source_node(db_path, active_node_id, active_hash)
    assert active_source is not None
    assert active_source["content_hash"] == active_hash

    for query in (
        "неоднозначный маркер",
        "устаревший статус маркер",
        "устаревшее поколение маркер",
        "удалённый статус маркер",
        "old",
    ):
        report = search_structural_database(db_path, query)
        assert report["search"]["status"] == "not_found_in_retrieval"
        assert report["search"]["results"] == []

    for node_id, content_hash in rejected.values():
        assert get_source_node(db_path, node_id, content_hash) is None
    assert get_source_node(
        db_path, "node_deleted_doc", calculate_content_hash("old")
    ) is None


def test_snapshot_without_active_source_reports_not_found_in_retrieval(tmp_path):
    db_path = tmp_path / "structure.sqlite3"
    node_id, content_hash, _ = create_executor1_database(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute(
        "UPDATE structural_nodes SET status='ambiguous', stale_generation=NULL WHERE document_pk=1"
    )
    connection.commit()
    connection.close()

    nodes, summary = load_current_nodes(db_path)
    assert nodes == []
    assert summary.nodes_current == 0

    report = search_structural_database(db_path, "остановка кровообращения")
    assert report["search"]["status"] == "not_found_in_retrieval"
    assert report["search"]["results"] == []
    assert get_source_node(db_path, node_id, content_hash) is None


def test_null_document_hash_is_preserved_and_never_replaced_by_node_hash(tmp_path):
    db_path = tmp_path / "structure.sqlite3"
    create_executor1_database(db_path)
    text = "документ без хеша содержит уникальный маркер"
    node_id = "node_no_document_hash"
    node_hash = calculate_content_hash(text)
    connection = sqlite3.connect(db_path)
    connection.execute(
        "INSERT INTO documents VALUES (3, 'hashless/Документ.md', 'active', NULL)"
    )
    connection.execute(
        """INSERT INTO structural_nodes VALUES
           (9, 3, ?, NULL, 'document', '[]', 1, 1, 0, ?, ?, ?, 'active', NULL)""",
        (node_id, len(text), node_hash, text),
    )
    connection.commit()
    connection.close()

    nodes, _ = load_current_nodes(db_path)
    node = next(item for item in nodes if item["node_id"] == node_id)
    assert node["document_hash"] is None
    assert node["content_hash"] == node_hash

    report = search_structural_database(db_path, "уникальный маркер")
    hit = next(item for item in report["search"]["results"] if item["node_id"] == node_id)
    assert hit["document_hash"] is None
    assert hit["content_hash"] == node_hash
    assert hit["document_hash"] != hit["content_hash"]

    source = get_source_node(db_path, node_id, node_hash)
    assert source is not None
    assert source["document_hash"] is None
    assert source["content_hash"] == node_hash


def test_integration_verifier_cli_help_has_one_package_dir_option():
    script = Path(__file__).resolve().parents[2] / "tools" / "sfra_integration_check.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        text=True, capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.count("--package-dir") == 1
