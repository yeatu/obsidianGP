from __future__ import annotations

import hashlib
import json
import sqlite3

from sfra_indexer import index_vault


def open_db(index_result):
    connection = sqlite3.connect(index_result.database_path)
    connection.row_factory = sqlite3.Row
    return connection


def test_repeat_index_skips_unchanged_document_and_preserves_ids(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("# Section\n\nOriginal paragraph.\n", encoding="utf-8")

    first = index_vault(vault, tmp_path / "sidecar")
    with open_db(first) as connection:
        before = [
            tuple(row) for row in connection.execute(
                "SELECT local_key, node_id, content_hash, status FROM structural_nodes ORDER BY node_pk"
            )
        ]
        versions_before = connection.execute("SELECT COUNT(*) FROM node_versions").fetchone()[0]
        generation_before = connection.execute(
            "SELECT generation FROM documents WHERE source_path='note.md'"
        ).fetchone()[0]

    second = index_vault(vault, tmp_path / "sidecar")
    with open_db(second) as connection:
        after = [
            tuple(row) for row in connection.execute(
                "SELECT local_key, node_id, content_hash, status FROM structural_nodes ORDER BY node_pk"
            )
        ]
        versions_after = connection.execute("SELECT COUNT(*) FROM node_versions").fetchone()[0]
        generation_after = connection.execute(
            "SELECT generation FROM documents WHERE source_path='note.md'"
        ).fetchone()[0]

    assert first.documents_indexed == 1
    assert second.documents_indexed == 0
    assert second.documents_skipped == 1
    assert before == after
    assert versions_before == versions_after
    assert generation_before == generation_after == 1


def test_content_edit_keeps_node_id_and_creates_new_sha256_version(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    file = vault / "note.md"
    file.write_text("# Section\n\nOriginal paragraph.\n", encoding="utf-8")
    first = index_vault(vault, tmp_path / "sidecar")

    with open_db(first) as connection:
        previous = connection.execute(
            "SELECT node_pk, node_id, content_hash FROM structural_nodes WHERE node_type='paragraph'"
        ).fetchone()

    file.write_text("# Section\n\nEdited paragraph.\n", encoding="utf-8")
    second = index_vault(vault, tmp_path / "sidecar")
    with open_db(second) as connection:
        current = connection.execute(
            "SELECT node_pk, node_id, content_hash, status FROM structural_nodes "
            "WHERE node_type='paragraph' AND stale_generation IS NULL"
        ).fetchone()
        versions = connection.execute(
            "SELECT version_no, content_hash, raw_text FROM node_versions "
            "WHERE node_pk=? ORDER BY version_no",
            (previous["node_pk"],),
        ).fetchall()

    expected_hash = "sha256:" + hashlib.sha256(b"Edited paragraph.\n").hexdigest()
    assert current["node_id"] == previous["node_id"]
    assert current["content_hash"] == expected_hash
    assert current["content_hash"] != previous["content_hash"]
    assert current["status"] == "active"
    assert [row["version_no"] for row in versions] == [1, 2]
    assert versions[0]["content_hash"] == previous["content_hash"]
    assert versions[1]["content_hash"] == expected_hash
    assert versions[1]["raw_text"] == "Edited paragraph.\n"


def test_unique_heading_key_preserves_id_when_section_moves(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    file = vault / "note.md"
    file.write_text(
        "# Alpha\n\n## Moved\n\nBody text.\n\n# Beta\n\nOther text.\n",
        encoding="utf-8",
    )
    first = index_vault(vault, tmp_path / "sidecar")
    with open_db(first) as connection:
        moved_before = connection.execute(
            "SELECT node_pk, node_id FROM structural_nodes "
            "WHERE node_type='heading' AND heading_path_json LIKE '%Moved%' "
            "AND stale_generation IS NULL"
        ).fetchone()

    file.write_text(
        "# Alpha\n\n# Beta\n\nOther text.\n\n## Moved\n\nBody text.\n",
        encoding="utf-8",
    )
    second = index_vault(vault, tmp_path / "sidecar")
    with open_db(second) as connection:
        moved_after = connection.execute(
            """SELECT n.node_pk, n.node_id, p.node_type AS parent_type,
                      p.metadata_json AS parent_metadata
               FROM structural_nodes n
               LEFT JOIN structural_nodes p ON p.node_pk=n.parent_node_pk
               WHERE n.node_type='heading'
                 AND n.heading_path_json LIKE '%Moved%'
                 AND n.stale_generation IS NULL"""
        ).fetchone()
    assert moved_after["node_id"] == moved_before["node_id"]
    assert moved_after["parent_type"] == "heading"
    assert '"title":"Beta"' in moved_after["parent_metadata"]


def test_ambiguous_many_to_many_match_never_reuses_old_ids(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    file = vault / "note.md"
    file.write_text("# Section\n\nOld alpha.\n\nOld beta.\n", encoding="utf-8")
    first = index_vault(vault, tmp_path / "sidecar")
    with open_db(first) as connection:
        old_ids = {
            row["node_id"] for row in connection.execute(
                "SELECT node_id FROM structural_nodes WHERE node_type='paragraph' "
                "AND stale_generation IS NULL"
            )
        }

    file.write_text("# Section\n\nNew gamma.\n\nNew delta.\n", encoding="utf-8")
    second = index_vault(vault, tmp_path / "sidecar")
    with open_db(second) as connection:
        new_rows = connection.execute(
            "SELECT node_id, status FROM structural_nodes WHERE node_type='paragraph' "
            "AND stale_generation IS NULL"
        ).fetchall()
        old_rows = connection.execute(
            "SELECT node_id, status FROM structural_nodes WHERE node_type='paragraph' "
            "AND stale_generation IS NOT NULL"
        ).fetchall()
        ambiguous_events = connection.execute(
            "SELECT candidate_node_ids_json FROM node_match_events WHERE event_type='ambiguous'"
        ).fetchall()

    new_ids = {row["node_id"] for row in new_rows}
    assert len(new_ids) == 2
    assert new_ids.isdisjoint(old_ids)
    assert {row["status"] for row in new_rows} == {"ambiguous"}
    assert old_ids == {row["node_id"] for row in old_rows}
    assert {row["status"] for row in old_rows} == {"stale"}
    assert len(ambiguous_events) == 2
    for event in ambiguous_events:
        assert set(json.loads(event["candidate_node_ids_json"])) == old_ids


def test_deleted_node_is_stale_and_its_version_is_retained(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    file = vault / "note.md"
    file.write_text("# Section\n\nKeep this.\n\nRemove this.\n", encoding="utf-8")
    first = index_vault(vault, tmp_path / "sidecar")
    with open_db(first) as connection:
        deleted = connection.execute(
            "SELECT node_pk, node_id FROM structural_nodes WHERE node_type='paragraph' "
            "AND raw_text LIKE '%Remove this%'"
        ).fetchone()

    file.write_text("# Section\n\nKeep this.\n", encoding="utf-8")
    second = index_vault(vault, tmp_path / "sidecar")
    with open_db(second) as connection:
        old_node = connection.execute(
            "SELECT status, stale_generation FROM structural_nodes WHERE node_pk=?",
            (deleted["node_pk"],),
        ).fetchone()
        old_versions = connection.execute(
            "SELECT COUNT(*) FROM node_versions WHERE node_pk=?",
            (deleted["node_pk"],),
        ).fetchone()[0]
    assert old_node["status"] == "stale"
    assert old_node["stale_generation"] == 2
    assert old_versions == 1


def test_only_changed_file_is_reindexed_and_removed_file_is_retained_as_deleted(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    one = vault / "one.md"
    two = vault / "two.md"
    one.write_text("first file\n", encoding="utf-8")
    two.write_text("second file\n", encoding="utf-8")

    first = index_vault(vault, tmp_path / "sidecar")
    with open_db(first) as connection:
        stable_two = connection.execute(
            "SELECT node_id FROM structural_nodes WHERE document_pk=("
            "SELECT document_pk FROM documents WHERE source_path='two.md') "
            "AND node_type='paragraph'"
        ).fetchone()[0]

    one.write_text("edited first file\n", encoding="utf-8")
    second = index_vault(vault, tmp_path / "sidecar")
    assert second.documents_seen == 2
    assert second.documents_indexed == 1
    assert second.documents_skipped == 1

    with open_db(second) as connection:
        stable_two_after = connection.execute(
            "SELECT node_id FROM structural_nodes WHERE document_pk=("
            "SELECT document_pk FROM documents WHERE source_path='two.md') "
            "AND node_type='paragraph' AND stale_generation IS NULL"
        ).fetchone()[0]
    assert stable_two == stable_two_after

    two.unlink()
    third = index_vault(vault, tmp_path / "sidecar")
    with open_db(third) as connection:
        deleted_doc = connection.execute(
            "SELECT status FROM documents WHERE source_path='two.md'"
        ).fetchone()[0]
        stale_count = connection.execute(
            "SELECT COUNT(*) FROM structural_nodes WHERE document_pk=("
            "SELECT document_pk FROM documents WHERE source_path='two.md') "
            "AND status='stale'"
        ).fetchone()[0]
    assert deleted_doc == "deleted"
    assert stale_count > 0


def test_stage_b_database_migrates_and_seeds_ids_hashes_and_version_one(tmp_path):
    db = tmp_path / "legacy.sqlite3"
    source = "# Legacy\n\nLegacy body.\n"
    spans = json.dumps([{
        "line_start": 1, "line_end": 3, "char_start": 0,
        "char_end": len(source), "byte_start": 0,
        "byte_end": len(source.encode("utf-8"))
    }])
    connection = sqlite3.connect(db)
    connection.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE schema_info(singleton INTEGER PRIMARY KEY, schema_version INTEGER NOT NULL);
        INSERT INTO schema_info VALUES (1, 1);
        CREATE TABLE documents(
            document_pk INTEGER PRIMARY KEY, source_path TEXT NOT NULL UNIQUE,
            source_size_bytes INTEGER NOT NULL, parser_name TEXT NOT NULL,
            parser_version TEXT NOT NULL, indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE structural_nodes(
            node_pk INTEGER PRIMARY KEY,
            document_pk INTEGER NOT NULL REFERENCES documents(document_pk) ON DELETE CASCADE,
            local_key TEXT NOT NULL, node_id TEXT,
            parent_node_pk INTEGER REFERENCES structural_nodes(node_pk) ON DELETE CASCADE,
            node_type TEXT NOT NULL, heading_path_json TEXT NOT NULL,
            line_start INTEGER NOT NULL, line_end INTEGER NOT NULL,
            char_start INTEGER NOT NULL, char_end INTEGER NOT NULL,
            byte_start INTEGER NOT NULL, byte_end INTEGER NOT NULL,
            content_spans_json TEXT NOT NULL, raw_text TEXT NOT NULL,
            metadata_json TEXT NOT NULL, warnings_json TEXT NOT NULL,
            UNIQUE(document_pk, local_key)
        );
        CREATE TABLE passages(
            passage_pk INTEGER PRIMARY KEY,
            document_pk INTEGER NOT NULL REFERENCES documents(document_pk) ON DELETE CASCADE,
            owner_node_pk INTEGER NOT NULL REFERENCES structural_nodes(node_pk) ON DELETE CASCADE,
            passage_key TEXT NOT NULL, ordinal INTEGER NOT NULL,
            line_start INTEGER NOT NULL, line_end INTEGER NOT NULL,
            char_start INTEGER NOT NULL, char_end INTEGER NOT NULL,
            byte_start INTEGER NOT NULL, byte_end INTEGER NOT NULL,
            raw_text TEXT NOT NULL, context_text TEXT NOT NULL,
            context_spans_json TEXT NOT NULL, estimated_words INTEGER NOT NULL,
            warnings_json TEXT NOT NULL, UNIQUE(document_pk, passage_key)
        );
    """)
    connection.execute(
        "INSERT INTO documents(document_pk, source_path, source_size_bytes, parser_name, parser_version) "
        "VALUES (1, 'legacy.md', ?, 'markdown-it-py', '4.2.0')",
        (len(source.encode("utf-8")),),
    )
    connection.execute(
        """INSERT INTO structural_nodes(
            node_pk, document_pk, local_key, node_id, parent_node_pk, node_type,
            heading_path_json, line_start, line_end, char_start, char_end,
            byte_start, byte_end, content_spans_json, raw_text, metadata_json,
            warnings_json
        ) VALUES (1, 1, 'root', NULL, NULL, 'document', '[]', 1, 3, 0, ?, 0, ?, ?, ?, '{}', '[]')""",
        (len(source), len(source.encode("utf-8")), spans, source),
    )
    connection.execute(
        """INSERT INTO structural_nodes(
            node_pk, document_pk, local_key, node_id, parent_node_pk, node_type,
            heading_path_json, line_start, line_end, char_start, char_end,
            byte_start, byte_end, content_spans_json, raw_text, metadata_json,
            warnings_json
        ) VALUES (2, 1, 'n000001', NULL, 1, 'paragraph', '[]', 3, 3, 10, ?, 10, ?, ?, 'Legacy body.\n', '{}', '[]')""",
        (len(source), len(source.encode("utf-8")), spans),
    )
    connection.commit()
    connection.close()

    migrated = sqlite3.connect(db)
    migrated.row_factory = sqlite3.Row
    migrated = __import__("sfra_indexer").connect_database(db)
    try:
        rows = migrated.execute(
            "SELECT node_id, content_hash FROM structural_nodes ORDER BY node_pk"
        ).fetchall()
        assert all(row["node_id"].startswith("node_") for row in rows)
        assert rows[1]["content_hash"] == "sha256:" + hashlib.sha256(
            b"Legacy body.\n"
        ).hexdigest()
        assert migrated.execute(
            "SELECT COUNT(*) FROM node_versions"
        ).fetchone()[0] == 2
        assert migrated.execute(
            "SELECT source_sha256 FROM documents WHERE source_path='legacy.md'"
        ).fetchone()[0] == "sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()
        assert migrated.execute(
            "SELECT schema_version FROM schema_info WHERE singleton=1"
        ).fetchone()[0] == 2
    finally:
        migrated.close()
