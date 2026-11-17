"""Read-only adapter for Executor 1's structural SQLite index.

The structural database is the source of truth for stable Node IDs and content
hashes. SFRA's lexical index is a disposable derivative and never writes to the
input database.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .adapter import ImportValidationError, validate_node


class StructuralDatabaseError(ValueError):
    """Raised when an input database does not match Executor 1's published schema."""


@dataclass(frozen=True, slots=True)
class StructuralDatabaseSummary:
    documents_active: int
    documents_total: int
    nodes_current: int
    nodes_skipped_without_identity: int = 0


def _connect_read_only(path: str | Path) -> sqlite3.Connection:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Structural database does not exist: {source}")
    # mode=ro is enforced by SQLite itself; query_only is an extra guard against
    # accidental writes in this process.
    uri = source.as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _validate_schema(connection: sqlite3.Connection) -> tuple[set[str], set[str]]:
    tables = {
        str(row["name"])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing_tables = {"documents", "structural_nodes"} - tables
    if missing_tables:
        raise StructuralDatabaseError(
            "Missing Executor 1 tables: " + ", ".join(sorted(missing_tables))
        )
    document_columns = _columns(connection, "documents")
    node_columns = _columns(connection, "structural_nodes")
    required_documents = {"document_pk", "source_path", "status"}
    required_nodes = {
        "node_pk", "document_pk", "node_id", "parent_node_pk", "node_type",
        "heading_path_json", "line_start", "line_end", "content_hash",
        "raw_text", "status", "stale_generation", "char_start", "char_end",
    }
    missing_documents = required_documents - document_columns
    missing_nodes = required_nodes - node_columns
    if missing_documents or missing_nodes:
        details = []
        if missing_documents:
            details.append("documents: " + ", ".join(sorted(missing_documents)))
        if missing_nodes:
            details.append("structural_nodes: " + ", ".join(sorted(missing_nodes)))
        raise StructuralDatabaseError("Unsupported Executor 1 schema; missing " + "; ".join(details))
    return document_columns, node_columns


def load_current_nodes(database_path: str | Path) -> tuple[list[dict[str, Any]], StructuralDatabaseSummary]:
    """Load and validate one consistent read-only snapshot of current nodes."""
    connection = _connect_read_only(database_path)
    try:
        document_columns, _ = _validate_schema(connection)
        documents_total = int(connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
        documents_active = int(
            connection.execute("SELECT COUNT(*) FROM documents WHERE status='active'").fetchone()[0]
        )
        nodes_skipped = int(connection.execute(
            """SELECT COUNT(*) FROM structural_nodes n
               JOIN documents d ON d.document_pk=n.document_pk
               WHERE d.status='active' AND n.status IN ('active','ambiguous')
                 AND n.stale_generation IS NULL
                 AND (n.node_id IS NULL OR n.content_hash IS NULL)"""
        ).fetchone()[0])
        if nodes_skipped:
            raise StructuralDatabaseError(
                f"{nodes_skipped} current structural nodes lack node_id or content_hash; "
                "the importer refuses to manufacture identities"
            )

        document_hash_select = (
            "d.source_sha256 AS document_hash"
            if "source_sha256" in document_columns
            else "NULL AS document_hash"
        )
        cursor = connection.execute(
            f"""SELECT d.source_path, {document_hash_select},
                       n.node_id, n.node_type, n.heading_path_json,
                       n.line_start, n.line_end, n.content_hash, n.raw_text,
                       parent.node_id AS parent_node_id
                FROM structural_nodes AS n
                JOIN documents AS d ON d.document_pk = n.document_pk
                LEFT JOIN structural_nodes AS parent ON parent.node_pk = n.parent_node_pk
                WHERE d.status = 'active'
                  AND n.status IN ('active', 'ambiguous')
                  AND n.stale_generation IS NULL
                ORDER BY d.source_path, n.char_start, n.char_end, n.node_id"""
        )
        nodes: list[dict[str, Any]] = []
        for row in cursor:
            try:
                heading_path = json.loads(row["heading_path_json"] or "[]")
                node = validate_node({
                    "node_id": row["node_id"],
                    "source_path": row["source_path"],
                    "node_type": row["node_type"],
                    "parent_node_id": row["parent_node_id"],
                    "heading_path": heading_path,
                    "line_start": row["line_start"],
                    "line_end": row["line_end"],
                    "content_hash": row["content_hash"],
                    "raw_text": row["raw_text"],
                    "document_hash": row["document_hash"],
                })
            except (json.JSONDecodeError, ImportValidationError) as exc:
                raise StructuralDatabaseError(
                    f"Invalid structural node {row['node_id']}: {exc}"
                ) from exc
            nodes.append(node)
        return nodes, StructuralDatabaseSummary(
            documents_active=documents_active,
            documents_total=documents_total,
            nodes_current=len(nodes),
            nodes_skipped_without_identity=nodes_skipped,
        )
    finally:
        connection.close()


def get_source_node(database_path: str | Path, node_id: str, content_hash: str) -> dict[str, Any] | None:
    """Fetch an exact current source node from Executor 1 by its stable address.

    Both `node_id` and `content_hash` are required. The source DB is opened
    read-only and the returned `raw_text` is the original structural slice.
    """
    if not isinstance(node_id, str) or not node_id or not isinstance(content_hash, str) or not content_hash:
        raise ValueError("node_id and content_hash are both required")
    connection = _connect_read_only(database_path)
    try:
        document_columns, _ = _validate_schema(connection)
        document_hash_select = (
            "d.source_sha256 AS document_hash"
            if "source_sha256" in document_columns
            else "NULL AS document_hash"
        )
        row = connection.execute(
            f"""SELECT n.node_id, d.source_path, n.node_type, n.content_hash,
                       n.heading_path_json, n.line_start, n.line_end, n.raw_text,
                       parent.node_id AS parent_node_id, {document_hash_select}
                FROM structural_nodes n
                JOIN documents d ON d.document_pk=n.document_pk
                LEFT JOIN structural_nodes parent ON parent.node_pk=n.parent_node_pk
                WHERE n.node_id=? AND n.content_hash=?
                  AND d.status='active'
                  AND n.status IN ('active','ambiguous')
                  AND n.stale_generation IS NULL
                LIMIT 1""",
            (node_id, content_hash),
        ).fetchone()
        if row is None:
            return None
        try:
            return validate_node({
                "node_id": row["node_id"],
                "source_path": row["source_path"],
                "node_type": row["node_type"],
                "parent_node_id": row["parent_node_id"],
                "heading_path": json.loads(row["heading_path_json"] or "[]"),
                "line_start": row["line_start"],
                "line_end": row["line_end"],
                "content_hash": row["content_hash"],
                "raw_text": row["raw_text"],
                "document_hash": row["document_hash"],
            })
        except (json.JSONDecodeError, ImportValidationError) as exc:
            raise StructuralDatabaseError(
                f"Invalid source node for {node_id!r} + {content_hash!r}: {exc}"
            ) from exc
    finally:
        connection.close()
