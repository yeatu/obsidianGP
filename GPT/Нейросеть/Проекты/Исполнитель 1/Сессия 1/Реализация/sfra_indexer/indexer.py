"""Incremental Vault API for the SFRA structural index."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import sqlite3

from .parser import parse_markdown
from .storage import connect_database, mark_document_deleted, save_parsed_document


@dataclass(frozen=True, slots=True)
class IndexResult:
    database_path: str
    documents_seen: int
    documents_indexed: int
    documents_skipped: int
    nodes_saved: int
    passages_saved: int
    empty_documents: int


def read_markdown_file(path: Path) -> str:
    """Read UTF-8 while preserving LF/CRLF instead of universal-newline conversion."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _file_hash(source: str) -> str:
    return "sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()


def index_vault(vault_path: str | Path, index_dir: str | Path) -> IndexResult:
    """Incrementally index Markdown files into an external SQLite sidecar.

    Only files with a changed whole-file SHA-256 are parsed. Each changed
    document is committed atomically, including node matching, new versions,
    stale/ambiguous states, match events and Passage replacement.
    """
    vault = Path(vault_path).expanduser().resolve()
    destination = Path(index_dir).expanduser().resolve()
    if not vault.is_dir():
        raise NotADirectoryError(f"Vault directory does not exist: {vault}")
    if destination == vault or vault in destination.parents:
        raise ValueError("index_dir must be outside the source Vault")

    destination.mkdir(parents=True, exist_ok=True)
    db_path = destination / "structure.sqlite3"
    connection = connect_database(db_path)
    documents_seen = documents_indexed = documents_skipped = 0
    nodes_saved = passages_saved = empty_documents = 0
    active_paths: set[str] = set()
    try:
        existing_documents = {
            row["source_path"]: row
            for row in connection.execute(
                "SELECT document_pk, source_path, source_sha256, status FROM documents"
            ).fetchall()
        }
        markdown_files = sorted(
            (item for item in vault.rglob("*") if item.is_file() and item.suffix.lower() == ".md"),
            key=lambda item: item.as_posix().casefold(),
        )

        for path in markdown_files:
            relative_path = path.relative_to(vault).as_posix()
            active_paths.add(relative_path)
            source = read_markdown_file(path)
            source_hash = _file_hash(source)
            documents_seen += 1

            previous = existing_documents.get(relative_path)
            if (
                previous is not None
                and previous["status"] == "active"
                and previous["source_sha256"] == source_hash
            ):
                documents_skipped += 1
                continue

            parsed = parse_markdown(source, relative_path)
            save_parsed_document(connection, parsed, source_hash)
            documents_indexed += 1
            nodes_saved += sum(1 for _ in parsed.iter_nodes())
            passages_saved += len(parsed.passages)
            if source == "":
                empty_documents += 1

        # Preserve deleted document and node history rather than cascading rows.
        for row in connection.execute(
            "SELECT document_pk, source_path FROM documents WHERE status = 'active'"
        ).fetchall():
            if row["source_path"] not in active_paths:
                mark_document_deleted(connection, int(row["document_pk"]))

        connection.commit()
    finally:
        connection.close()

    return IndexResult(
        database_path=str(db_path),
        documents_seen=documents_seen,
        documents_indexed=documents_indexed,
        documents_skipped=documents_skipped,
        nodes_saved=nodes_saved,
        passages_saved=passages_saved,
        empty_documents=empty_documents,
    )


def get_database_summary(db_path: str | Path) -> dict[str, int]:
    """Read-only database counters for diagnostics and CLI display."""
    connection = sqlite3.connect(db_path)
    try:
        document_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        active_documents = connection.execute(
            "SELECT COUNT(*) FROM documents WHERE status = 'active'"
        ).fetchone()[0]
        node_count = connection.execute("SELECT COUNT(*) FROM structural_nodes").fetchone()[0]
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
        version_count = connection.execute("SELECT COUNT(*) FROM node_versions").fetchone()[0]
        event_count = connection.execute("SELECT COUNT(*) FROM node_match_events").fetchone()[0]
        passage_count = connection.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
        empty_count = connection.execute(
            "SELECT COUNT(*) FROM documents WHERE source_size_bytes = 0 AND status = 'active'"
        ).fetchone()[0]
        return {
            "documents": document_count,
            "active_documents": active_documents,
            "nodes": node_count,
            "active_nodes": active_nodes,
            "stale_nodes": stale_nodes,
            "ambiguous_nodes": ambiguous_nodes,
            "node_versions": version_count,
            "match_events": event_count,
            "passages": passage_count,
            "empty_documents": empty_count,
        }
    finally:
        connection.close()
