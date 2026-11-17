from __future__ import annotations

import hashlib
import json
import sqlite3
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
    # A valid-looking ambiguous row must never become searchable or retrievable.
    ambiguous_text = "Уникальный неоднозначный источник для проверки."
    connection.execute(
        """INSERT INTO structural_nodes VALUES
           (5, 1, 'node_ambiguous', 1, 'quote', '[]', 4, 4, 65, 120,
            ?, ?, 'ambiguous', NULL)""",
        (calculate_content_hash(ambiguous_text), ambiguous_text),
    )
    # Status=active alone is not sufficient when E1 marks the row stale by generation.
    stale_generation_text = "Устаревшее поколение источника."
    connection.execute(
        """INSERT INTO structural_nodes VALUES
           (6, 1, 'node_active_stale_generation', 1, 'quote', '[]', 4, 4, 121, 160,
            ?, ?, 'active', 3)""",
        (calculate_content_hash(stale_generation_text), stale_generation_text),
    )
    deleted_text = "Удалённый источник."
    connection.execute(
        """INSERT INTO structural_nodes VALUES
           (7, 1, 'node_deleted', 1, 'quote', '[]', 4, 4, 161, 190,
            ?, ?, 'deleted', NULL)""",
        (calculate_content_hash(deleted_text), deleted_text),
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
           (8, 1, NULL, 1, 'quote', '[]', 4, 4, 66, 67,
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


def _node_hash(database_path: Path, node_id: str) -> str:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT content_hash FROM structural_nodes WHERE node_id=?",
            (node_id,),
        ).fetchone()
    assert row is not None
    return row[0]


def test_ambiguous_node_is_excluded_from_import_search_and_source_lookup(tmp_path, capsys):
    db_path = tmp_path / "structure.sqlite3"
    active_node_id, active_hash, _ = create_executor1_database(db_path)
    ambiguous_hash = _node_hash(db_path, "node_ambiguous")

    nodes, summary = load_current_nodes(db_path)
    indexed_ids = {node["node_id"] for node in nodes}
    assert active_node_id in indexed_ids
    assert "node_ambiguous" not in indexed_ids

    report = search_structural_database(db_path, "неоднозначный источник")
    assert report["search"]["results"] == []
    assert report["search"]["status"] == "not_found_in_retrieval"

    assert get_source_node(db_path, "node_ambiguous", ambiguous_hash) is None
    exit_code = cli_main([
        "get-source", "--source-db", str(db_path),
        "--node-id", "node_ambiguous", "--content-hash", ambiguous_hash,
    ])
    assert exit_code == 2
    assert "not found" in capsys.readouterr().err.lower()

    # The valid active source remains retrievable.
    active = get_source_node(db_path, active_node_id, active_hash)
    assert active is not None
    assert active["node_id"] == active_node_id


def test_ambiguous_node_without_identity_does_not_block_active_import(tmp_path):
    db_path = tmp_path / "structure.sqlite3"
    create_executor1_database(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE structural_nodes SET node_id=NULL, content_hash=NULL "
            "WHERE node_id='node_ambiguous'"
        )

    nodes, summary = load_current_nodes(db_path)
    assert {node["node_id"] for node in nodes} == {
        "node_executor1_root", "node_executor1_0001"
    }
    assert summary.nodes_current == 2
    assert summary.nodes_skipped_without_identity == 0


def test_stale_and_deleted_nodes_are_neither_indexed_nor_retrievable(tmp_path):
    db_path = tmp_path / "structure.sqlite3"
    create_executor1_database(db_path)
    nodes, _ = load_current_nodes(db_path)
    indexed_ids = {node["node_id"] for node in nodes}
    assert indexed_ids == {"node_executor1_root", "node_executor1_0001"}

    for node_id in (
        "node_stale",
        "node_active_stale_generation",
        "node_deleted",
        "node_deleted_doc",
    ):
        assert get_source_node(db_path, node_id, _node_hash(db_path, node_id)) is None


def test_no_active_source_is_reported_as_not_found(tmp_path):
    db_path = tmp_path / "structure.sqlite3"
    create_executor1_database(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE structural_nodes SET status='ambiguous' WHERE status='active'"
        )

    nodes, summary = load_current_nodes(db_path)
    assert nodes == []
    assert summary.nodes_current == 0

    report = search_structural_database(db_path, "остановка кровообращения")
    assert report["search"]["status"] == "not_found_in_retrieval"
    assert report["search"]["results"] == []
    assert get_source_node(
        db_path, "node_executor1_0001", _node_hash(db_path, "node_executor1_0001")
    ) is None


def test_null_document_hash_is_not_replaced_with_node_hash(tmp_path):
    db_path = tmp_path / "structure.sqlite3"
    node_id, content_hash, _ = create_executor1_database(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE documents SET source_sha256=NULL WHERE document_pk=1")

    nodes, _ = load_current_nodes(db_path)
    node = next(item for item in nodes if item["node_id"] == node_id)
    assert node["content_hash"] == content_hash
    assert node["document_hash"] is None

    source = get_source_node(db_path, node_id, content_hash)
    assert source is not None
    assert source["content_hash"] == content_hash
    assert source["document_hash"] is None


def test_integration_check_cli_has_no_duplicate_package_dir_argument():
    import subprocess
    import sys

    script = Path(__file__).resolve().parents[2] / "tools" / "sfra_integration_check.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        text=True, capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    source = script.read_text(encoding="utf-8")
    assert source.count('parser.add_argument("--package-dir"') == 1
