"""SQLite persistence for the stage-B structural representation."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import ParsedDocument, StructuralNode

SCHEMA_VERSION = 1

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_info (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_version INTEGER NOT NULL
);
INSERT OR IGNORE INTO schema_info(singleton, schema_version) VALUES (1, 1);

CREATE TABLE IF NOT EXISTS documents (
    document_pk INTEGER PRIMARY KEY,
    source_path TEXT NOT NULL UNIQUE,
    source_size_bytes INTEGER NOT NULL,
    parser_name TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS structural_nodes (
    node_pk INTEGER PRIMARY KEY,
    document_pk INTEGER NOT NULL REFERENCES documents(document_pk) ON DELETE CASCADE,
    local_key TEXT NOT NULL,
    node_id TEXT,
    parent_node_pk INTEGER REFERENCES structural_nodes(node_pk) ON DELETE CASCADE,
    node_type TEXT NOT NULL,
    heading_path_json TEXT NOT NULL,
    line_start INTEGER NOT NULL,
    line_end INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    byte_start INTEGER NOT NULL,
    byte_end INTEGER NOT NULL,
    content_spans_json TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    UNIQUE(document_pk, local_key)
);
CREATE INDEX IF NOT EXISTS idx_nodes_document ON structural_nodes(document_pk);
CREATE INDEX IF NOT EXISTS idx_nodes_parent ON structural_nodes(parent_node_pk);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON structural_nodes(node_type);

CREATE TABLE IF NOT EXISTS passages (
    passage_pk INTEGER PRIMARY KEY,
    document_pk INTEGER NOT NULL REFERENCES documents(document_pk) ON DELETE CASCADE,
    owner_node_pk INTEGER NOT NULL REFERENCES structural_nodes(node_pk) ON DELETE CASCADE,
    passage_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    line_start INTEGER NOT NULL,
    line_end INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    byte_start INTEGER NOT NULL,
    byte_end INTEGER NOT NULL,
    raw_text TEXT NOT NULL,
    context_text TEXT NOT NULL,
    context_spans_json TEXT NOT NULL,
    estimated_words INTEGER NOT NULL,
    warnings_json TEXT NOT NULL,
    UNIQUE(document_pk, passage_key)
);
CREATE INDEX IF NOT EXISTS idx_passages_owner ON passages(owner_node_pk);
"""


def connect_database(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    return connection


def _span_dict(span) -> dict:
    return {
        "line_start": span.line_start,
        "line_end": span.line_end,
        "char_start": span.char_start,
        "char_end": span.char_end,
        "byte_start": span.byte_start,
        "byte_end": span.byte_end,
    }


def _insert_node(connection: sqlite3.Connection, document_pk: int,
                 node: StructuralNode, parent_pk: int | None,
                 pk_by_key: dict[str, int]) -> None:
    cursor = connection.execute(
        """INSERT INTO structural_nodes(
            document_pk, local_key, node_id, parent_node_pk, node_type,
            heading_path_json, line_start, line_end, char_start, char_end,
            byte_start, byte_end, content_spans_json, raw_text,
            metadata_json, warnings_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            document_pk, node.local_key, node.node_id, parent_pk, node.node_type,
            json.dumps(node.heading_path, ensure_ascii=False),
            node.line_start, node.line_end, node.char_start, node.char_end,
            node.byte_start, node.byte_end,
            json.dumps([_span_dict(span) for span in node.content_spans], ensure_ascii=False),
            node.raw_text,
            json.dumps(node.metadata, ensure_ascii=False),
            json.dumps(node.warnings, ensure_ascii=False),
        ),
    )
    node_pk = int(cursor.lastrowid)
    pk_by_key[node.local_key] = node_pk
    for child in node.children:
        _insert_node(connection, document_pk, child, node_pk, pk_by_key)


def save_parsed_document(connection: sqlite3.Connection, document: ParsedDocument) -> int:
    """Replace one document's current structural representation atomically."""
    source_bytes = document.raw_text.encode("utf-8")
    with connection:
        connection.execute("DELETE FROM documents WHERE source_path = ?", (document.source_path,))
        cursor = connection.execute(
            """INSERT INTO documents(source_path, source_size_bytes, parser_name, parser_version)
               VALUES (?, ?, ?, ?)""",
            (document.source_path, len(source_bytes), document.parser_name, document.parser_version),
        )
        document_pk = int(cursor.lastrowid)
        pk_by_key: dict[str, int] = {}
        _insert_node(connection, document_pk, document.root, None, pk_by_key)
        for ordinal, passage in enumerate(document.passages, start=1):
            owner_pk = pk_by_key[passage.owner_node_key]
            span = passage.span
            connection.execute(
                """INSERT INTO passages(
                    document_pk, owner_node_pk, passage_key, ordinal,
                    line_start, line_end, char_start, char_end, byte_start, byte_end,
                    raw_text, context_text, context_spans_json, estimated_words, warnings_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    document_pk, owner_pk, passage.passage_key, ordinal,
                    span.line_start, span.line_end, span.char_start, span.char_end,
                    span.byte_start, span.byte_end, passage.raw_text,
                    passage.context_text,
                    json.dumps([_span_dict(item) for item in passage.context_spans], ensure_ascii=False),
                    passage.estimated_words, json.dumps(passage.warnings, ensure_ascii=False),
                ),
            )
    return document_pk
