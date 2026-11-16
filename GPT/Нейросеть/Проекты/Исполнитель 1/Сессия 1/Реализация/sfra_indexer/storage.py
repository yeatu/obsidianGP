"""SQLite schema, migrations, stable node IDs and source-version history."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .identity import build_match_plan, content_hash
from .models import ParsedDocument, StructuralNode

SCHEMA_VERSION = 2

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

CREATE TABLE IF NOT EXISTS node_versions (
    node_version_pk INTEGER PRIMARY KEY,
    node_pk INTEGER NOT NULL REFERENCES structural_nodes(node_pk) ON DELETE CASCADE,
    version_no INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    source_path TEXT NOT NULL,
    node_type TEXT NOT NULL,
    parent_node_id TEXT,
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
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(node_pk, version_no)
);
CREATE INDEX IF NOT EXISTS idx_node_versions_node ON node_versions(node_pk, version_no);

CREATE TABLE IF NOT EXISTS node_match_events (
    event_pk INTEGER PRIMARY KEY,
    document_pk INTEGER NOT NULL REFERENCES documents(document_pk) ON DELETE CASCADE,
    generation INTEGER NOT NULL,
    new_local_key TEXT,
    event_type TEXT NOT NULL,
    node_id TEXT,
    candidate_node_ids_json TEXT NOT NULL DEFAULT '[]',
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_node_match_events_document
    ON node_match_events(document_pk, generation);
"""


_DOCUMENT_COLUMNS = {
    "source_sha256": "TEXT",
    "generation": "INTEGER NOT NULL DEFAULT 0",
    "status": "TEXT NOT NULL DEFAULT 'active'",
}
_NODE_COLUMNS = {
    "content_hash": "TEXT",
    "status": "TEXT NOT NULL DEFAULT 'active'",
    "created_generation": "INTEGER NOT NULL DEFAULT 1",
    "updated_generation": "INTEGER NOT NULL DEFAULT 1",
    "stale_generation": "INTEGER",
}


def _ensure_columns(connection: sqlite3.Connection, table: str,
                    columns: dict[str, str]) -> None:
    existing = {
        row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for name, definition in columns.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _span_dict(span) -> dict:
    return {
        "line_start": span.line_start,
        "line_end": span.line_end,
        "char_start": span.char_start,
        "char_end": span.char_end,
        "byte_start": span.byte_start,
        "byte_end": span.byte_end,
    }


def _node_fields(node: StructuralNode) -> dict[str, Any]:
    return {
        "node_type": node.node_type,
        "heading_path_json": _json(node.heading_path),
        "line_start": node.line_start,
        "line_end": node.line_end,
        "char_start": node.char_start,
        "char_end": node.char_end,
        "byte_start": node.byte_start,
        "byte_end": node.byte_end,
        "content_spans_json": _json([_span_dict(span) for span in node.content_spans]),
        "raw_text": node.raw_text,
        "metadata_json": _json(node.metadata),
        "warnings_json": _json(node.warnings),
        "content_hash": content_hash(node.raw_text),
    }


def _snapshot_signature(fields: dict[str, Any], parent_node_id: str | None) -> tuple:
    return (
        fields["content_hash"], fields["node_type"], parent_node_id,
        fields["heading_path_json"], fields["line_start"], fields["line_end"],
        fields["char_start"], fields["char_end"], fields["byte_start"],
        fields["byte_end"], fields["content_spans_json"], fields["raw_text"],
        fields["metadata_json"], fields["warnings_json"],
    )


def _old_snapshot_signature(row: dict[str, Any],
                            old_by_pk: dict[int, dict[str, Any]]) -> tuple:
    parent = old_by_pk.get(row["parent_node_pk"])
    parent_id = parent["node_id"] if parent else None
    fields = {key: row[key] for key in (
        "content_hash", "node_type", "heading_path_json", "line_start",
        "line_end", "char_start", "char_end", "byte_start", "byte_end",
        "content_spans_json", "raw_text", "metadata_json", "warnings_json",
    )}
    return _snapshot_signature(fields, parent_id)


def _insert_node_version(connection: sqlite3.Connection, node_pk: int,
                          version_no: int, generation: int, source_path: str,
                          fields: dict[str, Any], parent_node_id: str | None) -> None:
    connection.execute(
        """INSERT INTO node_versions(
            node_pk, version_no, generation, content_hash, source_path, node_type,
            parent_node_id, heading_path_json, line_start, line_end, char_start,
            char_end, byte_start, byte_end, content_spans_json, raw_text,
            metadata_json, warnings_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            node_pk, version_no, generation, fields["content_hash"], source_path,
            fields["node_type"], parent_node_id, fields["heading_path_json"],
            fields["line_start"], fields["line_end"], fields["char_start"],
            fields["char_end"], fields["byte_start"], fields["byte_end"],
            fields["content_spans_json"], fields["raw_text"],
            fields["metadata_json"], fields["warnings_json"],
        ),
    )


def _migrate(connection: sqlite3.Connection) -> None:
    """Upgrade Stage-B schema v1 in place and seed identity/version history."""
    _ensure_columns(connection, "documents", _DOCUMENT_COLUMNS)
    _ensure_columns(connection, "structural_nodes", _NODE_COLUMNS)
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_nodes_node_id "
        "ON structural_nodes(node_id) WHERE node_id IS NOT NULL"
    )

    # Backfill Stage-B rows exactly once. The document root stores the original
    # Markdown and therefore provides a trustworthy file hash for future skips.
    docs = connection.execute(
        "SELECT document_pk, source_path FROM documents"
    ).fetchall()
    for document_pk, source_path in docs:
        root = connection.execute(
            """SELECT node_pk, raw_text FROM structural_nodes
               WHERE document_pk = ? AND node_type = 'document'
               ORDER BY node_pk LIMIT 1""",
            (document_pk,),
        ).fetchone()
        if root is not None:
            source_hash = "sha256:" + hashlib.sha256(root[1].encode("utf-8")).hexdigest()
            connection.execute(
                """UPDATE documents SET source_sha256 = COALESCE(source_sha256, ?),
                   generation = CASE WHEN generation = 0 THEN 1 ELSE generation END
                   WHERE document_pk = ?""",
                (source_hash, document_pk),
            )

    rows = connection.execute(
        """SELECT node_pk, node_id, document_pk, local_key, node_type,
                  parent_node_pk, heading_path_json, line_start, line_end,
                  char_start, char_end, byte_start, byte_end, content_spans_json,
                  raw_text, metadata_json, warnings_json, content_hash,
                  created_generation, updated_generation
           FROM structural_nodes ORDER BY node_pk"""
    ).fetchall()
    row_names = [item[1] for item in connection.execute(
        "PRAGMA table_info(structural_nodes)"
    ).fetchall()]
    records = [dict(zip(row_names, row)) for row in rows]
    by_pk = {int(row["node_pk"]): row for row in records}

    for row in records:
        node_pk = int(row["node_pk"])
        node_id = row["node_id"]
        digest = row["content_hash"] or content_hash(row["raw_text"])
        if not node_id:
            node_id = "node_" + str(uuid.uuid4())
            connection.execute(
                "UPDATE structural_nodes SET node_id = ?, content_hash = ? WHERE node_pk = ?",
                (node_id, digest, node_pk),
            )
            row["node_id"] = node_id
            row["content_hash"] = digest
        has_version = connection.execute(
            "SELECT 1 FROM node_versions WHERE node_pk = ? LIMIT 1", (node_pk,)
        ).fetchone()
        if not has_version:
            parent = by_pk.get(row["parent_node_pk"])
            parent_id = parent.get("node_id") if parent else None
            fields = {
                "node_type": row["node_type"],
                "heading_path_json": row["heading_path_json"],
                "line_start": row["line_start"], "line_end": row["line_end"],
                "char_start": row["char_start"], "char_end": row["char_end"],
                "byte_start": row["byte_start"], "byte_end": row["byte_end"],
                "content_spans_json": row["content_spans_json"],
                "raw_text": row["raw_text"], "metadata_json": row["metadata_json"],
                "warnings_json": row["warnings_json"], "content_hash": digest,
            }
            doc_generation = connection.execute(
                "SELECT generation FROM documents WHERE document_pk = ?",
                (row["document_pk"],),
            ).fetchone()[0]
            _insert_node_version(
                connection, node_pk, 1, max(1, int(doc_generation)),
                connection.execute(
                    "SELECT source_path FROM documents WHERE document_pk = ?",
                    (row["document_pk"],),
                ).fetchone()[0],
                fields, parent_id,
            )

    connection.execute(
        "UPDATE schema_info SET schema_version = ? WHERE singleton = 1",
        (SCHEMA_VERSION,),
    )


def connect_database(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    with connection:
        _migrate(connection)
    return connection


def save_parsed_document(connection: sqlite3.Connection,
                         document: ParsedDocument,
                         source_sha256: str | None = None) -> int:
    """Persist a parsed source version while retaining Node IDs and history."""
    source_sha256 = source_sha256 or (
        "sha256:" + hashlib.sha256(document.raw_text.encode("utf-8")).hexdigest()
    )
    source_size_bytes = len(document.raw_text.encode("utf-8"))

    with connection:
        existing_doc = connection.execute(
            """SELECT document_pk, generation FROM documents
               WHERE source_path = ?""",
            (document.source_path,),
        ).fetchone()

        if existing_doc is None:
            cursor = connection.execute(
                """INSERT INTO documents(
                    source_path, source_size_bytes, parser_name, parser_version,
                    source_sha256, generation, status
                ) VALUES (?, ?, ?, ?, ?, 1, 'active')""",
                (document.source_path, source_size_bytes,
                 document.parser_name, document.parser_version, source_sha256),
            )
            document_pk = int(cursor.lastrowid)
            generation = 1
            old_nodes: list[dict[str, Any]] = []
        else:
            document_pk = int(existing_doc["document_pk"])
            generation = int(existing_doc["generation"]) + 1
            old_rows = connection.execute(
                """SELECT * FROM structural_nodes
                   WHERE document_pk = ?
                     AND status IN ('active', 'ambiguous')
                     AND stale_generation IS NULL""",
                (document_pk,),
            ).fetchall()
            old_nodes = [dict(row) for row in old_rows]

        plan = build_match_plan(old_nodes, document)
        old_by_pk = {int(row["node_pk"]): row for row in old_nodes}

        # Free the unique (document_pk, local_key) values before assigning this
        # generation's parse-local keys. Old rows remain addressable by node_id.
        for row in old_nodes:
            node_pk = int(row["node_pk"])
            connection.execute(
                """UPDATE structural_nodes
                   SET local_key = ?, status = 'stale', stale_generation = ?
                   WHERE node_pk = ?""",
                (f"__archived__{node_pk}", generation, node_pk),
            )

        ambiguous_old_pks = {
            int(candidate["node_pk"])
            for candidates in plan.ambiguous_candidates.values()
            for candidate in candidates
        }
        node_pk_by_key: dict[str, int] = {}
        node_id_by_key: dict[str, str] = {}

        for node in document.iter_nodes():
            matched_old = plan.matches.get(node.local_key)
            parent_pk = (
                node_pk_by_key.get(node.parent_key)
                if node.parent_key is not None else None
            )
            parent_id = (
                node_id_by_key.get(node.parent_key)
                if node.parent_key is not None else None
            )
            fields = _node_fields(node)
            if matched_old is not None:
                node_pk = int(matched_old["node_pk"])
                node_id = matched_old["node_id"]
                node_status = "active"
                old_signature = _old_snapshot_signature(matched_old, old_by_pk)
                new_signature = _snapshot_signature(fields, parent_id)
                version_row = connection.execute(
                    "SELECT COALESCE(MAX(version_no), 0) FROM node_versions WHERE node_pk = ?",
                    (node_pk,),
                ).fetchone()
                version_no = int(version_row[0]) + (
                    1 if old_signature != new_signature else 0
                )
                connection.execute(
                    """UPDATE structural_nodes SET
                        local_key = ?, node_id = ?, parent_node_pk = ?,
                        node_type = ?, heading_path_json = ?, line_start = ?,
                        line_end = ?, char_start = ?, char_end = ?, byte_start = ?,
                        byte_end = ?, content_spans_json = ?, raw_text = ?,
                        metadata_json = ?, warnings_json = ?, content_hash = ?,
                        status = ?, updated_generation = ?, stale_generation = NULL
                       WHERE node_pk = ?""",
                    (
                        node.local_key, node_id, parent_pk, fields["node_type"],
                        fields["heading_path_json"], fields["line_start"],
                        fields["line_end"], fields["char_start"], fields["char_end"],
                        fields["byte_start"], fields["byte_end"],
                        fields["content_spans_json"], fields["raw_text"],
                        fields["metadata_json"], fields["warnings_json"],
                        fields["content_hash"], node_status, generation, node_pk,
                    ),
                )
                if version_no > 0 and old_signature != new_signature:
                    _insert_node_version(
                        connection, node_pk, version_no, generation,
                        document.source_path, fields, parent_id,
                    )
                event_type = plan.reasons[node.local_key]
                node.node_id = node_id
                node.content_hash = fields["content_hash"]
            else:
                node_id = "node_" + str(uuid.uuid4())
                node_status = (
                    "ambiguous"
                    if node.local_key in plan.ambiguous_candidates else "active"
                )
                cursor = connection.execute(
                    """INSERT INTO structural_nodes(
                        document_pk, local_key, node_id, parent_node_pk,
                        node_type, heading_path_json, line_start, line_end,
                        char_start, char_end, byte_start, byte_end,
                        content_spans_json, raw_text, metadata_json, warnings_json,
                        content_hash, status, created_generation, updated_generation
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        document_pk, node.local_key, node_id, parent_pk,
                        fields["node_type"], fields["heading_path_json"],
                        fields["line_start"], fields["line_end"],
                        fields["char_start"], fields["char_end"],
                        fields["byte_start"], fields["byte_end"],
                        fields["content_spans_json"], fields["raw_text"],
                        fields["metadata_json"], fields["warnings_json"],
                        fields["content_hash"], node_status, generation, generation,
                    ),
                )
                node_pk = int(cursor.lastrowid)
                _insert_node_version(
                    connection, node_pk, 1, generation,
                    document.source_path, fields, parent_id,
                )
                event_type = "ambiguous" if node_status == "ambiguous" else "new"
                node.node_id = node_id
                node.content_hash = fields["content_hash"]

            node_pk_by_key[node.local_key] = node_pk
            node_id_by_key[node.local_key] = node_id

            candidates = plan.ambiguous_candidates.get(node.local_key, [])
            connection.execute(
                """INSERT INTO node_match_events(
                    document_pk, generation, new_local_key, event_type,
                    node_id, candidate_node_ids_json, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    document_pk, generation, node.local_key, event_type, node_id,
                    _json([row["node_id"] for row in candidates]),
                    _json({"node_type": node.node_type, "reason": plan.reasons.get(node.local_key)}),
                ),
            )

        # Only candidate old nodes are tagged by the ambiguity event; their IDs
        # nevertheless remain stale because no new node inherited them.
        for old_pk in plan.stale_old_pks:
            old_row = old_by_pk[old_pk]
            if old_pk not in ambiguous_old_pks:
                event_type = "stale"
            else:
                event_type = "stale_ambiguous_candidate"
            connection.execute(
                """INSERT INTO node_match_events(
                    document_pk, generation, new_local_key, event_type,
                    node_id, candidate_node_ids_json, details_json
                ) VALUES (?, ?, NULL, ?, ?, '[]', ?)""",
                (document_pk, generation, event_type, old_row["node_id"],
                 _json({"old_local_key": old_row["local_key"]})),
            )

        connection.execute("DELETE FROM passages WHERE document_pk = ?", (document_pk,))
        for ordinal, passage in enumerate(document.passages, start=1):
            owner_pk = node_pk_by_key[passage.owner_node_key]
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
                    _json([_span_dict(item) for item in passage.context_spans]),
                    passage.estimated_words, _json(passage.warnings),
                ),
            )

        connection.execute(
            """UPDATE documents SET source_size_bytes = ?, parser_name = ?,
               parser_version = ?, source_sha256 = ?, generation = ?,
               status = 'active', indexed_at = CURRENT_TIMESTAMP
               WHERE document_pk = ?""",
            (
                source_size_bytes, document.parser_name, document.parser_version,
                source_sha256, generation, document_pk,
            ),
        )

    return document_pk


def mark_document_deleted(connection: sqlite3.Connection,
                          document_pk: int) -> None:
    """Retain the document and node history while marking all current nodes stale."""
    with connection:
        row = connection.execute(
            "SELECT generation FROM documents WHERE document_pk = ?",
            (document_pk,),
        ).fetchone()
        if row is None:
            return
        generation = int(row["generation"]) + 1
        current = connection.execute(
            """SELECT node_pk, node_id, local_key FROM structural_nodes
               WHERE document_pk = ? AND status IN ('active', 'ambiguous')
                 AND stale_generation IS NULL""",
            (document_pk,),
        ).fetchall()
        for item in current:
            node_pk = int(item["node_pk"])
            connection.execute(
                """UPDATE structural_nodes SET local_key = ?, status = 'stale',
                   stale_generation = ? WHERE node_pk = ?""",
                (f"__deleted__{node_pk}", generation, node_pk),
            )
            connection.execute(
                """INSERT INTO node_match_events(
                    document_pk, generation, new_local_key, event_type,
                    node_id, candidate_node_ids_json, details_json
                ) VALUES (?, ?, NULL, 'document_deleted', ?, '[]', ?)""",
                (document_pk, generation, item["node_id"],
                 _json({"old_local_key": item["local_key"]})),
            )
        connection.execute("DELETE FROM passages WHERE document_pk = ?", (document_pk,))
        connection.execute(
            """UPDATE documents SET status = 'deleted', generation = ?,
               indexed_at = CURRENT_TIMESTAMP WHERE document_pk = ?""",
            (generation, document_pk),
        )


def get_database_summary(db_path: str | Path) -> dict[str, int]:
    connection = sqlite3.connect(db_path)
    try:
        documents = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        active_documents = connection.execute(
            "SELECT COUNT(*) FROM documents WHERE status = 'active'"
        ).fetchone()[0]
        nodes = connection.execute("SELECT COUNT(*) FROM structural_nodes").fetchone()[0]
        active_nodes = connection.execute(
            "SELECT COUNT(*) FROM structural_nodes WHERE status IN ('active','ambiguous') "
            "AND stale_generation IS NULL"
        ).fetchone()[0]
        stale_nodes = connection.execute(
            "SELECT COUNT(*) FROM structural_nodes WHERE status = 'stale'"
        ).fetchone()[0]
        ambiguous_nodes = connection.execute(
            "SELECT COUNT(*) FROM structural_nodes WHERE status = 'ambiguous' "
            "AND stale_generation IS NULL"
        ).fetchone()[0]
        passages = connection.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
        empty = connection.execute(
            "SELECT COUNT(*) FROM documents WHERE source_size_bytes = 0"
        ).fetchone()[0]
        return {
            "documents": documents,
            "active_documents": active_documents,
            "nodes": nodes,
            "active_nodes": active_nodes,
            "stale_nodes": stale_nodes,
            "ambiguous_nodes": ambiguous_nodes,
            "passages": passages,
            "empty_documents": empty,
        }
    finally:
        connection.close()
