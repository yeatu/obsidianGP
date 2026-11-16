"""Batch Vault parser API for stage B (stable synchronization is stage C)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from .parser import parse_markdown
from .storage import connect_database, save_parsed_document


@dataclass(frozen=True, slots=True)
class IndexResult:
    database_path: str
    documents_seen: int
    nodes_saved: int
    passages_saved: int
    empty_documents: int


def read_markdown_file(path: Path) -> str:
    """Read UTF-8 while preserving LF/CRLF instead of universal-newline conversion."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def index_vault(vault_path: str | Path, index_dir: str | Path) -> IndexResult:
    """Parse all Markdown files in a Vault into an external SQLite sidecar.

    Stage B intentionally performs a batch rebuild. Incremental change detection
    and stable Node ID matching are reserved for stage C.
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
    documents_seen = nodes_saved = passages_saved = empty_documents = 0
    active_paths: set[str] = set()
    try:
        for path in sorted(vault.rglob("*.md"), key=lambda item: item.as_posix().casefold()):
            if not path.is_file():
                continue
            relative_path = path.relative_to(vault).as_posix()
            active_paths.add(relative_path)
            source = read_markdown_file(path)
            parsed = parse_markdown(source, relative_path)
            save_parsed_document(connection, parsed)
            documents_seen += 1
            nodes_saved += sum(1 for _ in parsed.iter_nodes())
            passages_saved += len(parsed.passages)
            if source == "":
                empty_documents += 1

        # Batch snapshot semantics: remove stale rows for files absent from the
        # current filesystem. Only the external sidecar database is modified.
        if active_paths:
            placeholders = ",".join("?" for _ in active_paths)
            connection.execute(
                f"DELETE FROM documents WHERE source_path NOT IN ({placeholders})",
                tuple(sorted(active_paths)),
            )
        else:
            connection.execute("DELETE FROM documents")
        connection.commit()
    finally:
        connection.close()
    return IndexResult(str(db_path), documents_seen, nodes_saved, passages_saved, empty_documents)


def get_database_summary(db_path: str | Path) -> dict[str, int]:
    connection = sqlite3.connect(db_path)
    try:
        documents = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        nodes = connection.execute("SELECT COUNT(*) FROM structural_nodes").fetchone()[0]
        passages = connection.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
        empty = connection.execute(
            "SELECT COUNT(*) FROM documents WHERE source_size_bytes = 0"
        ).fetchone()[0]
        return {"documents": documents, "nodes": nodes, "passages": passages, "empty_documents": empty}
    finally:
        connection.close()
