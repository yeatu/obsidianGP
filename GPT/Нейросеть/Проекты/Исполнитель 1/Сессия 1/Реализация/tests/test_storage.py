from __future__ import annotations

import hashlib
import sqlite3

import pytest

from sfra_indexer import connect_database, index_vault, parse_markdown, save_parsed_document


def test_sqlite_schema_stores_document_tree_and_passages(tmp_path):
    source = "# Раздел\n\n" + "текст " * 1200 + "\n\n## Дочерний\nСодержимое.\n"
    parsed = parse_markdown(source, "note.md", max_passage_words=300)
    db = tmp_path / "sidecar" / "structure.sqlite3"
    connection = connect_database(db)
    try:
        document_pk = save_parsed_document(connection, parsed)
        assert document_pk > 0
        docs = [tuple(row) for row in connection.execute(
            "SELECT source_path, source_size_bytes FROM documents"
        ).fetchall()]
        assert docs == [("note.md", len(source.encode("utf-8")))]
        nodes = connection.execute(
            "SELECT node_type, parent_node_pk, raw_text FROM structural_nodes ORDER BY node_pk"
        ).fetchall()
        assert any(row[0] == "heading" for row in nodes)
        assert any(row[0] == "paragraph" for row in nodes)
        assert connection.execute("SELECT COUNT(*) FROM passages").fetchone()[0] > 1
        assert connection.execute(
            "SELECT node_id FROM structural_nodes WHERE node_type='heading'"
        ).fetchone()[0].startswith("node_")
        assert connection.execute(
            "SELECT COUNT(*) FROM node_versions"
        ).fetchone()[0] == len(nodes)
        assert connection.execute(
            "SELECT COUNT(*) FROM node_match_events"
        ).fetchone()[0] == len(nodes)
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "fts" not in " ".join(names).lower()
    finally:
        connection.close()


def test_index_vault_indexes_empty_files_and_never_modifies_sources(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    nested = vault / "nested"
    nested.mkdir()
    (vault / "empty.md").write_bytes(b"")
    (nested / "unicode.md").write_bytes("# Привет\r\n\r\nтекст 🧪\r\n".encode("utf-8"))
    before = {
        path.relative_to(vault).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in vault.rglob("*.md")
    }

    result = index_vault(vault, tmp_path / "sidecar")
    after = {
        path.relative_to(vault).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in vault.rglob("*.md")
    }
    assert result.documents_seen == 2
    assert result.empty_documents == 1
    assert before == after

    connection = sqlite3.connect(result.database_path)
    try:
        rows = [tuple(row) for row in connection.execute(
            "SELECT source_path, source_size_bytes FROM documents ORDER BY source_path"
        ).fetchall()]
        assert rows[0] == ("empty.md", 0)
        assert rows[1][0] == "nested/unicode.md"
        raw = connection.execute(
            "SELECT raw_text FROM structural_nodes WHERE node_type='paragraph'"
        ).fetchone()[0]
        assert "\r\n" in raw
    finally:
        connection.close()


def test_index_directory_inside_vault_is_rejected(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with pytest.raises(ValueError, match="outside"):
        index_vault(vault, vault / ".ai-index")
