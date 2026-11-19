"""SQLite/FTS5 SFRA search index implementation."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import Counter
import time
from pathlib import Path
from typing import Any, Iterable

from .adapter import ImportValidationError, validate_manifest, validate_node
from .normalize import Morphology, alias_key, build_fts_query, build_morph_fts_query, extract_numbers, tokenize, _non_numeric_query_tokens

SCHEMA_VERSION = 2

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS index_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    source_path TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK(state IN ('active','deleted')) DEFAULT 'active',
    last_generation INTEGER NOT NULL DEFAULT 0,
    document_hash TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    current_version_id INTEGER,
    state TEXT NOT NULL CHECK(state IN ('active','deleted')) DEFAULT 'active',
    FOREIGN KEY(current_version_id) REFERENCES node_versions(version_id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE IF NOT EXISTS node_versions (
    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    source_path TEXT NOT NULL,
    node_type TEXT NOT NULL,
    parent_node_id TEXT,
    heading_path_json TEXT NOT NULL,
    line_start INTEGER NOT NULL,
    line_end INTEGER NOT NULL,
    raw_text TEXT NOT NULL,
    title_original TEXT NOT NULL,
    path_original TEXT NOT NULL,
    heading_original TEXT NOT NULL,
    title_lemmas TEXT NOT NULL,
    heading_lemmas TEXT NOT NULL,
    raw_lemmas TEXT NOT NULL,
    index_generation INTEGER NOT NULL DEFAULT 0,
    document_hash TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(node_id, content_hash),
    FOREIGN KEY(node_id) REFERENCES nodes(node_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_node_versions_source_path ON node_versions(source_path);
CREATE INDEX IF NOT EXISTS idx_node_versions_node ON node_versions(node_id, version_id);
CREATE TABLE IF NOT EXISTS node_numbers (
    number_id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    field_name TEXT NOT NULL CHECK(field_name IN ('raw_text','title_original','path_original','heading_original')),
    value_key TEXT NOT NULL,
    surface TEXT NOT NULL,
    start_char INTEGER NOT NULL,
    end_char INTEGER NOT NULL,
    FOREIGN KEY(version_id) REFERENCES node_versions(version_id) ON DELETE CASCADE,
    UNIQUE(version_id, field_name, value_key, start_char, end_char)
);
CREATE INDEX IF NOT EXISTS idx_node_numbers_key ON node_numbers(value_key);
CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS entity_aliases (
    alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    alias_text TEXT NOT NULL,
    alias_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('candidate','confirmed','rejected')),
    origin TEXT NOT NULL DEFAULT 'manual',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE,
    UNIQUE(entity_id, alias_key)
);
CREATE INDEX IF NOT EXISTS idx_alias_key_status ON entity_aliases(alias_key, status);
CREATE TABLE IF NOT EXISTS entity_sources (
    entity_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('primary_document','related_document')),
    PRIMARY KEY(entity_id, source_path, role),
    FOREIGN KEY(entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS entity_candidates (
    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_text TEXT NOT NULL,
    candidate_key TEXT NOT NULL,
    source_path TEXT,
    node_id TEXT,
    source_kind TEXT NOT NULL,
    occurrences INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL CHECK(status IN ('pending','accepted','rejected')) DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS mentions (
    mention_id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    node_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    alias_id INTEGER NOT NULL,
    matched_text TEXT NOT NULL,
    start_char INTEGER NOT NULL,
    end_char INTEGER NOT NULL,
    matching_method TEXT NOT NULL,
    FOREIGN KEY(version_id) REFERENCES node_versions(version_id) ON DELETE CASCADE,
    FOREIGN KEY(node_id) REFERENCES nodes(node_id) ON DELETE CASCADE,
    FOREIGN KEY(entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY(alias_id) REFERENCES entity_aliases(alias_id) ON DELETE CASCADE,
    UNIQUE(version_id, alias_id, start_char, end_char)
);
CREATE INDEX IF NOT EXISTS idx_mentions_entity ON mentions(entity_id, version_id);
CREATE INDEX IF NOT EXISTS idx_mentions_node ON mentions(node_id, version_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_candidate_origin
    ON entity_candidates(candidate_key, source_path, node_id, source_kind);
"""


class SFRAIndex:
    """Local lexical and entity index. Search results always contain original text."""

    def __init__(self, db_path: str | os.PathLike[str]):
        self.db_path = str(db_path)
        self._uri = False
        self._memory_anchor = None
        if self.db_path == ":memory:":
            import uuid
            self.db_path = f"file:sfra-{uuid.uuid4().hex}?mode=memory&cache=shared"
            self._uri = True
            self._memory_anchor = sqlite3.connect(self.db_path, uri=True, timeout=10, isolation_level=None)
        else:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.morphology = Morphology()
        self._initialize()

    def close(self) -> None:
        """Close the anchor connection that keeps a shared in-memory DB alive."""
        if self._memory_anchor is not None:
            self._memory_anchor.close()
            self._memory_anchor = None

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None, uri=self._uri)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        if not self._uri:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _initialize(self) -> None:
        conn = self._connect()
        try:
            try:
                conn.execute("CREATE VIRTUAL TABLE temp.__sfra_fts5_probe USING fts5(value)")
                conn.execute("DROP TABLE temp.__sfra_fts5_probe")
            except sqlite3.OperationalError as exc:
                raise RuntimeError("SQLite FTS5 is unavailable in this Python build") from exc
            conn.executescript(SCHEMA_SQL)
            # Schema v2 adds document-level provenance fields. Apply idempotent
            # ALTER migrations for databases created by the v1 prototype.
            document_columns = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
            if "document_hash" not in document_columns:
                conn.execute("ALTER TABLE documents ADD COLUMN document_hash TEXT")
            version_columns = {row[1] for row in conn.execute("PRAGMA table_info(node_versions)")}
            if "index_generation" not in version_columns:
                conn.execute("ALTER TABLE node_versions ADD COLUMN index_generation INTEGER NOT NULL DEFAULT 0")
            if "document_hash" not in version_columns:
                conn.execute("ALTER TABLE node_versions ADD COLUMN document_hash TEXT")
            conn.execute(
                """CREATE VIRTUAL TABLE IF NOT EXISTS node_fts USING fts5(
                    title_original, path_original, heading_original, raw_text,
                    title_lemmas, heading_lemmas, raw_lemmas,
                    tokenize='unicode61 remove_diacritics 0'
                )"""
            )
            conn.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (1)")
            conn.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)", (SCHEMA_VERSION,))
            conn.execute("INSERT OR IGNORE INTO index_meta(key,value) VALUES('index_generation','0')")
            conn.execute("INSERT INTO index_meta(key,value) VALUES('schema_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(SCHEMA_VERSION),))
            conn.execute("INSERT OR IGNORE INTO index_meta(key,value) VALUES('morphology_engine',?)", (self.morphology.engine,))
            stored_engine = conn.execute("SELECT value FROM index_meta WHERE key='morphology_engine'").fetchone()[0]
            if stored_engine != self.morphology.engine:
                raise RuntimeError(
                    f"Index morphology engine is {stored_engine!r}, current engine is {self.morphology.engine!r}; rebuild the derived index to avoid mixed normalization"
                )
        finally:
            conn.close()

    @staticmethod
    def _title(source_path: str) -> str:
        name = source_path.rsplit("/", 1)[-1]
        return name[:-3] if name.casefold().endswith(".md") else name

    def _prepare_node(self, node: dict[str, Any]) -> dict[str, Any]:
        clean = validate_node(node)
        title = clean.get("document_title") or self._title(clean["source_path"])
        if not isinstance(title, str):
            raise ImportValidationError("document_title must be a string when supplied")
        heading = " / ".join(clean["heading_path"])
        clean.update({
            "title_original": title,
            "path_original": clean["source_path"],
            "heading_original": heading,
            "title_lemmas": self.morphology.normalize_text(title),
            "heading_lemmas": self.morphology.normalize_text(heading),
            "raw_lemmas": self.morphology.normalize_text(clean["raw_text"]),
        })
        return clean

    def _next_generation(self, conn: sqlite3.Connection) -> int:
        current = int(conn.execute("SELECT value FROM index_meta WHERE key='index_generation'").fetchone()[0])
        generation = current + 1
        conn.execute("UPDATE index_meta SET value=? WHERE key='index_generation'", (str(generation),))
        return generation

    @staticmethod
    def _insert_fts(conn: sqlite3.Connection, version_id: int, node: dict[str, Any]) -> None:
        conn.execute("DELETE FROM node_fts WHERE rowid=?", (version_id,))
        conn.execute(
            """INSERT INTO node_fts(rowid,title_original,path_original,heading_original,raw_text,
                    title_lemmas,heading_lemmas,raw_lemmas)
               VALUES(?,?,?,?,?,?,?,?)""",
            (version_id, node["title_original"], node["path_original"], node["heading_original"],
             node["raw_text"], node["title_lemmas"], node["heading_lemmas"], node["raw_lemmas"]),
        )

    @staticmethod
    def _replace_numbers(conn: sqlite3.Connection, version_id: int, node: dict[str, Any]) -> None:
        conn.execute("DELETE FROM node_numbers WHERE version_id=?", (version_id,))
        records = []
        for field_name in ("raw_text", "title_original", "path_original", "heading_original"):
            for key, surface, start, end in extract_numbers(node[field_name]):
                records.append((version_id, field_name, key, surface, start, end))
        conn.executemany(
            "INSERT INTO node_numbers(version_id,field_name,value_key,surface,start_char,end_char) VALUES(?,?,?,?,?,?)",
            records,
        )

    @staticmethod
    def _find_alias_spans(text: str, alias: str) -> list[tuple[str, int, int]]:
        parts = tokenize(alias)
        if not parts:
            return []
        # Flexible whitespace between alias tokens, strict Unicode word boundaries.
        separator = r"[\s\-‐‑‒–—'’ʼ]+"
        pattern = r"(?<!\w)" + separator.join(re.escape(p) for p in parts) + r"(?!\w)"
        flags = re.IGNORECASE | re.UNICODE
        # Preserve the stored alias surface but compare a case-insensitive form.
        return [(m.group(0), m.start(), m.end()) for m in re.finditer(pattern, text, flags)]

    def _rebuild_mentions_for_version(self, conn: sqlite3.Connection, version_id: int, node_id: str, raw_text: str) -> int:
        conn.execute("DELETE FROM mentions WHERE version_id=?", (version_id,))
        aliases = conn.execute(
            "SELECT alias_id,entity_id,alias_text FROM entity_aliases WHERE status='confirmed' ORDER BY alias_id"
        ).fetchall()
        count = 0
        for alias in aliases:
            for matched, start, end in self._find_alias_spans(raw_text, alias["alias_text"]):
                conn.execute(
                    """INSERT OR IGNORE INTO mentions
                       (version_id,node_id,entity_id,alias_id,matched_text,start_char,end_char,matching_method)
                       VALUES(?,?,?,?,?,?,?,'confirmed_alias_exact')""",
                    (version_id, node_id, alias["entity_id"], alias["alias_id"], matched, start, end),
                )
                count += 1
        return count

    def _record_entity_candidates(self, conn: sqlite3.Connection, node: dict[str, Any]) -> None:
        """Store unconfirmed navigation candidates from titles, headings and repeated names."""
        candidates: list[tuple[str, str, int]] = []
        candidates.append((node["title_original"], "document_title", 1))
        candidates.extend((heading, "heading", 1) for heading in node["heading_path"] if heading.strip())
        capitalized = re.findall(
            r"(?<!\w)([А-ЯЁA-Z][А-ЯЁа-яёA-Za-z0-9’'\-]+(?:\s+[А-ЯЁA-Z][А-ЯЁа-яёA-Za-z0-9’'\-]+){1,2})(?!\w)",
            node["raw_text"], flags=re.UNICODE,
        )
        counts = Counter(capitalized)
        candidates.extend((phrase, "repeated_name", occurrences) for phrase, occurrences in counts.items() if occurrences >= 2)
        for text, source_kind, occurrences in candidates:
            key = alias_key(text)
            if not key:
                continue
            existing = conn.execute(
                "SELECT candidate_id FROM entity_candidates WHERE candidate_key=? AND source_path=? AND node_id=? AND source_kind=?",
                (key, node["source_path"], node["node_id"], source_kind),
            ).fetchone()
            alias_status = conn.execute(
                "SELECT status FROM entity_aliases WHERE alias_key=? ORDER BY CASE status WHEN 'confirmed' THEN 0 WHEN 'rejected' THEN 1 ELSE 2 END LIMIT 1",
                (key,),
            ).fetchone()
            candidate_status = "accepted" if alias_status and alias_status["status"] == "confirmed" else (
                "rejected" if alias_status and alias_status["status"] == "rejected" else "pending"
            )
            if existing:
                conn.execute("UPDATE entity_candidates SET candidate_text=?,occurrences=?,status=? WHERE candidate_id=?",
                             (text, occurrences, candidate_status, existing["candidate_id"]))
            else:
                conn.execute(
                    "INSERT INTO entity_candidates(candidate_text,candidate_key,source_path,node_id,source_kind,occurrences,status) VALUES(?,?,?,?,?,?,?)",
                    (text, key, node["source_path"], node["node_id"], source_kind, occurrences, candidate_status),
                )

    def list_entity_candidates(self, limit: int = 100) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT candidate_id,candidate_text,source_path,node_id,source_kind,occurrences,status "
                "FROM entity_candidates WHERE status='pending' ORDER BY occurrences DESC,source_path,candidate_text LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def import_nodes(self, nodes: Iterable[dict[str, Any]], manifest: dict[str, Any] | None = None) -> dict[str, int]:
        batch = [self._prepare_node(node) for node in nodes]
        manifest = validate_manifest(manifest)
        mode = manifest["mode"]
        replacement_paths = set(manifest.get("managed_source_paths", []) if mode == "full_snapshot" else manifest.get("replace_source_paths", []))
        deleted_ids = set(manifest["deleted_node_ids"])
        if mode in ("replace_documents", "full_snapshot"):
            bad_paths = sorted({n["source_path"] for n in batch} - replacement_paths)
            if bad_paths:
                raise ImportValidationError(f"Batch contains paths outside replacement scope: {bad_paths}")
        node_ids = [n["node_id"] for n in batch]
        if len(node_ids) != len(set(node_ids)):
            raise ImportValidationError("Duplicate node_id in one import batch")
        if deleted_ids.intersection(node_ids):
            raise ImportValidationError("A node cannot be imported and deleted in the same batch")

        document_hashes: dict[str, str] = {}
        for node in batch:
            value = node.get("document_hash")
            if value is None:
                continue
            previous = document_hashes.setdefault(node["source_path"], value)
            if previous != value:
                raise ImportValidationError(f"Conflicting document_hash values for {node['source_path']}")

        imported = updated = unchanged = deleted = versions_created = mentions_written = 0
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            generation = self._next_generation(conn)
            all_paths = {n["source_path"] for n in batch} | replacement_paths
            for source_path in all_paths:
                conn.execute(
                    """INSERT INTO documents(source_path,state,last_generation,document_hash,updated_at)
                       VALUES(?,'active',?,?,CURRENT_TIMESTAMP)
                       ON CONFLICT(source_path) DO UPDATE SET state='active',last_generation=excluded.last_generation,
                         document_hash=excluded.document_hash,updated_at=CURRENT_TIMESTAMP""",
                    (source_path, generation, document_hashes.get(source_path)),
                )
            resolved_document_hashes = {
                row["source_path"]: row["document_hash"]
                for row in conn.execute(
                    "SELECT source_path,document_hash FROM documents WHERE source_path IN (%s)" %
                    ",".join("?" for _ in all_paths), tuple(all_paths)
                ).fetchall()
            } if all_paths else {}
            for node in batch:
                node["document_hash"] = resolved_document_hashes.get(node["source_path"])

            imported_ids = set(node_ids)
            if mode in ("replace_documents", "full_snapshot"):
                placeholders = ",".join("?" for _ in replacement_paths)
                if replacement_paths:
                    old_ids = conn.execute(
                        f"""SELECT n.node_id FROM nodes n JOIN node_versions v
                             ON v.version_id=n.current_version_id
                             WHERE n.state='active' AND v.source_path IN ({placeholders})""",
                        tuple(replacement_paths),
                    ).fetchall()
                    for row in old_ids:
                        if row["node_id"] not in imported_ids:
                            conn.execute("UPDATE nodes SET state='deleted',current_version_id=NULL WHERE node_id=?", (row["node_id"],))
                            conn.execute("DELETE FROM entity_candidates WHERE node_id=?", (row["node_id"],))
                            deleted += 1

            for node in batch:
                existing = conn.execute("SELECT current_version_id,state FROM nodes WHERE node_id=?", (node["node_id"],)).fetchone()
                if existing is None:
                    conn.execute("INSERT INTO nodes(node_id,state) VALUES(?,'active')", (node["node_id"],))
                current = conn.execute(
                    "SELECT version_id,content_hash,source_path,node_type,parent_node_id,heading_path_json,line_start,line_end,raw_text,index_generation,document_hash "
                    "FROM node_versions WHERE node_id=? AND content_hash=?",
                    (node["node_id"], node["content_hash"]),
                ).fetchone()
                if current is not None:
                    version_id = int(current["version_id"])
                    metadata_changed = any([
                        current["source_path"] != node["source_path"],
                        current["node_type"] != node["node_type"],
                        current["parent_node_id"] != node["parent_node_id"],
                        current["heading_path_json"] != json.dumps(node["heading_path"], ensure_ascii=False),
                        current["line_start"] != node["line_start"],
                        current["line_end"] != node["line_end"],
                        current["document_hash"] != node["document_hash"],
                    ])
                    if metadata_changed:
                        conn.execute(
                            """UPDATE node_versions SET source_path=?,node_type=?,parent_node_id=?,heading_path_json=?,
                               line_start=?,line_end=?,title_original=?,path_original=?,heading_original=?,
                               title_lemmas=?,heading_lemmas=?,raw_lemmas=?,index_generation=?,document_hash=? WHERE version_id=?""",
                            (node["source_path"], node["node_type"], node["parent_node_id"],
                             json.dumps(node["heading_path"], ensure_ascii=False), node["line_start"], node["line_end"],
                             node["title_original"], node["path_original"], node["heading_original"],
                             node["title_lemmas"], node["heading_lemmas"], node["raw_lemmas"], generation,
                             node["document_hash"], version_id),
                        )
                        self._insert_fts(conn, version_id, node)
                        self._replace_numbers(conn, version_id, node)
                        conn.execute("DELETE FROM entity_candidates WHERE node_id=?", (node["node_id"],))
                        self._record_entity_candidates(conn, node)
                    else:
                        unchanged += 1
                else:
                    cursor = conn.execute(
                        """INSERT INTO node_versions
                           (node_id,content_hash,source_path,node_type,parent_node_id,heading_path_json,line_start,line_end,
                            raw_text,title_original,path_original,heading_original,title_lemmas,heading_lemmas,raw_lemmas,
                            index_generation,document_hash)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (node["node_id"], node["content_hash"], node["source_path"], node["node_type"],
                         node["parent_node_id"], json.dumps(node["heading_path"], ensure_ascii=False),
                         node["line_start"], node["line_end"], node["raw_text"], node["title_original"],
                         node["path_original"], node["heading_original"], node["title_lemmas"],
                         node["heading_lemmas"], node["raw_lemmas"], generation, node["document_hash"]),
                    )
                    version_id = int(cursor.lastrowid)
                    self._insert_fts(conn, version_id, node)
                    self._replace_numbers(conn, version_id, node)
                    mentions_written += self._rebuild_mentions_for_version(conn, version_id, node["node_id"], node["raw_text"])
                    conn.execute("DELETE FROM entity_candidates WHERE node_id=?", (node["node_id"],))
                    self._record_entity_candidates(conn, node)
                    versions_created += 1
                    if existing is None:
                        imported += 1
                    else:
                        updated += 1
                conn.execute("UPDATE nodes SET current_version_id=?,state='active' WHERE node_id=?", (version_id, node["node_id"]))

            for node_id in deleted_ids:
                cur = conn.execute("UPDATE nodes SET state='deleted',current_version_id=NULL WHERE node_id=? AND state='active'", (node_id,))
                conn.execute("DELETE FROM entity_candidates WHERE node_id=?", (node_id,))
                deleted += cur.rowcount

            # A full snapshot can explicitly mark managed documents active even if they contain zero nodes.
            if mode == "full_snapshot":
                for source_path in replacement_paths:
                    conn.execute("UPDATE documents SET state='active',last_generation=? WHERE source_path=?", (generation, source_path))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return {"generation": generation, "imported": imported, "updated": updated, "unchanged": unchanged,
                "deleted": deleted, "versions_created": versions_created, "mentions_written": mentions_written}

    def update_index(self, nodes: Iterable[dict[str, Any]], manifest: dict[str, Any] | None = None) -> dict[str, int]:
        return self.import_nodes(nodes, manifest)

    def create_entity(self, entity_id: str, canonical_name: str, aliases: Iterable[str] = (),
                      primary_source_path: str | None = None) -> None:
        if not entity_id or not canonical_name:
            raise ValueError("entity_id and canonical_name are required")
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO entities(entity_id,canonical_name) VALUES(?,?) ON CONFLICT(entity_id) DO UPDATE SET canonical_name=excluded.canonical_name",
                         (entity_id, canonical_name))
            canonical_key = alias_key(canonical_name)
            self._upsert_alias(conn, entity_id, canonical_name, "confirmed", "canonical")
            for alias in aliases:
                if isinstance(alias, str) and alias.strip() and alias_key(alias) != canonical_key:
                    self._upsert_alias(conn, entity_id, alias.strip(), "candidate", "config_candidate")
            if primary_source_path:
                from .adapter import validate_source_path
                primary_source_path = validate_source_path(primary_source_path)
                conn.execute("DELETE FROM entity_sources WHERE entity_id=? AND role='primary_document'", (entity_id,))
                conn.execute("INSERT OR IGNORE INTO entity_sources(entity_id,source_path,role) VALUES(?,?,'primary_document')",
                             (entity_id, primary_source_path))
            self._rebuild_all_current_mentions(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _upsert_alias(conn: sqlite3.Connection, entity_id: str, alias: str, status: str, origin: str) -> int:
        key = alias_key(alias)
        if not key:
            raise ValueError("Alias must contain searchable letters or digits")
        row = conn.execute("SELECT alias_id FROM entity_aliases WHERE entity_id=? AND alias_key=?", (entity_id, key)).fetchone()
        if row:
            conn.execute("UPDATE entity_aliases SET alias_text=?,status=?,origin=?,updated_at=CURRENT_TIMESTAMP WHERE alias_id=?",
                         (alias, status, origin, row["alias_id"]))
            return int(row["alias_id"])
        cur = conn.execute("INSERT INTO entity_aliases(entity_id,alias_text,alias_key,status,origin) VALUES(?,?,?,?,?)",
                           (entity_id, alias, key, status, origin))
        return int(cur.lastrowid)

    def add_alias_candidate(self, entity_id: str, alias: str) -> int:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            alias_id = self._upsert_alias(conn, entity_id, alias, "candidate", "manual_candidate")
            conn.commit()
            return alias_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def confirm_alias(self, entity_id: str, alias: str) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            alias_id = self._upsert_alias(conn, entity_id, alias, "confirmed", "manual_confirmed")
            conn.execute("UPDATE entity_candidates SET status='accepted' WHERE candidate_key=?", (alias_key(alias),))
            self._rebuild_all_current_mentions(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def reject_alias(self, entity_id: str, alias: str) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            key = alias_key(alias)
            cur = conn.execute("""UPDATE entity_aliases SET status='rejected',origin='manual_rejected',updated_at=CURRENT_TIMESTAMP
                                 WHERE entity_id=? AND alias_key=?""", (entity_id, key))
            if cur.rowcount == 0:
                self._upsert_alias(conn, entity_id, alias, "rejected", "manual_rejected")
            conn.execute("UPDATE entity_candidates SET status='rejected' WHERE candidate_key=?", (key,))
            self._rebuild_all_current_mentions(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _rebuild_all_current_mentions(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            "SELECT v.version_id,v.node_id,v.raw_text FROM node_versions v JOIN nodes n "
            "ON n.current_version_id=v.version_id WHERE n.state='active'"
        ).fetchall()
        conn.execute("DELETE FROM mentions WHERE version_id IN (SELECT current_version_id FROM nodes WHERE current_version_id IS NOT NULL)")
        for row in rows:
            self._rebuild_mentions_for_version(conn, row["version_id"], row["node_id"], row["raw_text"])

    def list_entity_aliases(self, entity_id: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT alias_id,entity_id,alias_text,status,origin FROM entity_aliases WHERE entity_id=? ORDER BY alias_id", (entity_id,)).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_node(self, node_id: str, content_hash: str | None = None) -> dict[str, Any] | None:
        """Return the complete original Node v1 payload and provenance metadata.

        Unlike search hits, this method never renames raw_text to excerpt. A missing
        document_hash is returned as null rather than fabricated from a single node.
        """
        conn = self._connect()
        try:
            if content_hash:
                row = conn.execute(
                    """SELECT v.* FROM node_versions v WHERE v.node_id=? AND v.content_hash=?""",
                    (node_id, content_hash),
                ).fetchone()
            else:
                row = conn.execute(
                    """SELECT v.* FROM nodes n JOIN node_versions v ON v.version_id=n.current_version_id
                       WHERE n.node_id=? AND n.state='active'""",
                    (node_id,),
                ).fetchone()
            return self._row_to_node(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "node_id": row["node_id"],
            "source_path": row["source_path"],
            "node_type": row["node_type"],
            "parent_node_id": row["parent_node_id"],
            "heading_path": json.loads(row["heading_path_json"]),
            "line_start": row["line_start"],
            "line_end": row["line_end"],
            "content_hash": row["content_hash"],
            "raw_text": row["raw_text"],
            "index_generation": row["index_generation"],
            "document_hash": row["document_hash"],
        }

    @staticmethod
    def _make_excerpt(raw_text: str, query: str | None = None, max_chars: int = 420) -> str:
        """Build a bounded search hint; the complete source is available via get_node()."""
        if len(raw_text) <= max_chars:
            return raw_text
        start = 0
        if query:
            # Prefer a literal query token as the excerpt anchor. Morphological-only
            # matches simply fall back to the beginning, without modifying source text.
            for token in tokenize(query):
                match = re.search(re.escape(token), raw_text, flags=re.IGNORECASE)
                if match:
                    start = max(0, match.start() - max_chars // 4)
                    break
        end = min(len(raw_text), start + max_chars)
        excerpt = raw_text[start:end]
        if start:
            excerpt = "…" + excerpt
        if end < len(raw_text):
            excerpt += "…"
        return excerpt

    @staticmethod
    def _row_to_result(row: sqlite3.Row, reason: str | None, query: str | None = None) -> dict[str, Any]:
        data = dict(row)
        data["heading_path"] = json.loads(data.pop("heading_path_json"))
        original = data.pop("raw_text")
        data["excerpt"] = SFRAIndex._make_excerpt(original, query=query)
        data.pop("created_at", None)
        data["match_type"] = reason or "direct_lookup"
        return data

    def _resolve_entity_names(self, names: Iterable[str], conn: sqlite3.Connection) -> tuple[set[str], dict[str, list[str]]]:
        ids: set[str] = set()
        matches: dict[str, list[str]] = {}
        for name in names:
            key = alias_key(name)
            rows = conn.execute(
                "SELECT DISTINCT e.entity_id FROM entity_aliases a JOIN entities e ON e.entity_id=a.entity_id "
                "WHERE a.alias_key=? AND a.status='confirmed' ORDER BY e.entity_id", (key,)
            ).fetchall()
            found = [r["entity_id"] for r in rows]
            matches[name] = found
            ids.update(found)
        return ids, matches

    def search_entity(self, name: str, limit: int = 20) -> dict[str, Any]:
        conn = self._connect()
        try:
            entity_ids, resolutions = self._resolve_entity_names([name], conn)
            if not entity_ids:
                return {"query_entity": name, "entity_ids": [], "ambiguous": False, "status": "not_found_in_retrieval", "results": []}
            placeholders = ",".join("?" for _ in entity_ids)
            candidates: dict[int, dict[str, Any]] = {}
            rows = conn.execute(
                f"""SELECT DISTINCT v.*,m.entity_id,m.matched_text,a.alias_text
                    FROM mentions m JOIN nodes n ON n.node_id=m.node_id AND n.current_version_id=m.version_id AND n.state='active'
                    JOIN node_versions v ON v.version_id=m.version_id
                    JOIN entity_aliases a ON a.alias_id=m.alias_id
                    WHERE m.entity_id IN ({placeholders})""", tuple(entity_ids)
            ).fetchall()
            for row in rows:
                version_id = row["version_id"]
                item = candidates.setdefault(version_id, {"row": row, "reasons": set(), "aliases": set(), "is_primary": False})
                item["reasons"].add(f"entity_mention:{row['entity_id']}")
                item["aliases"].add(row["alias_text"])

            primary_rows = conn.execute(
                f"""SELECT DISTINCT v.*,s.entity_id FROM entity_sources s
                    JOIN node_versions v ON v.source_path=s.source_path
                    JOIN nodes n ON n.node_id=v.node_id AND n.current_version_id=v.version_id AND n.state='active'
                    WHERE s.role='primary_document' AND s.entity_id IN ({placeholders})""", tuple(entity_ids)
            ).fetchall()
            for row in primary_rows:
                version_id = row["version_id"]
                item = candidates.setdefault(version_id, {"row": row, "reasons": set(), "aliases": set(), "is_primary": False})
                item["reasons"].add(f"entity_primary_document:{row['entity_id']}")
                item["is_primary"] = True

            results = []
            for version_id, item in candidates.items():
                row = item["row"]
                results.append(self._row_to_result(row, "exact_entity"))
                results[-1]["match_reasons"] = sorted(item["reasons"])
                results[-1]["matched_aliases"] = sorted(item["aliases"])
                results[-1]["entities"] = sorted(entity_ids)
                results[-1]["is_primary_entity_document"] = item["is_primary"]
                results[-1]["relevance"] = {"tier": 1, "bm25": 0.0}
            # The explicitly configured primary document is first; other confirmed
            # mentions remain separate results and are ordered deterministically.
            results.sort(key=lambda r: (not r["is_primary_entity_document"],
                                        r["source_path"], r["line_start"], r["node_id"]))
            results = results[:max(1, limit)]
            return {"query_entity": name, "entity_ids": sorted(entity_ids), "ambiguous": len(entity_ids) > 1,
                    "status": "ok", "results": results}
        finally:
            conn.close()

    def search(self, query: str, entities: Iterable[str] | None = None, limit: int = 20) -> dict[str, Any]:
        entities = list(entities or [])
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        if not query.strip() and not entities:
            raise ValueError("query or entities must be provided")
        limit = max(1, min(int(limit), 500))
        conn = self._connect()
        try:
            candidates: dict[int, dict[str, Any]] = {}

            fts_sql = """SELECT v.*, bm25(node_fts,8.0,2.0,6.0,1.0,6.0,4.0,1.0) AS bm25_rank
                         FROM node_fts JOIN node_versions v ON v.version_id=node_fts.rowid
                         JOIN nodes n ON n.node_id=v.node_id AND n.current_version_id=v.version_id AND n.state='active'
                         WHERE node_fts MATCH ?"""
            term_fts_sql = """SELECT v.version_id,v.node_id,v.source_path,v.parent_node_id
                              FROM node_fts JOIN node_versions v ON v.version_id=node_fts.rowid
                              JOIN nodes n ON n.node_id=v.node_id AND n.current_version_id=v.version_id AND n.state='active'
                              WHERE node_fts MATCH ?"""

            def fetch_fts_rows(match_query: str) -> list[sqlite3.Row]:
                if not match_query:
                    return []
                return conn.execute(fts_sql, (match_query,)).fetchall()

            def fetch_term_rows(match_query: str) -> list[sqlite3.Row]:
                if not match_query:
                    return []
                return conn.execute(term_fts_sql, (match_query,)).fetchall()

            def collect_fts(
                match_query: str,
                reason: str,
                tier: int,
                *,
                rows: list[sqlite3.Row] | None = None,
                allowed_version_ids: set[int] | None = None,
            ) -> int:
                if not match_query:
                    return 0
                matched_rows = fetch_fts_rows(match_query) if rows is None else rows
                if allowed_version_ids is not None:
                    matched_rows = [row for row in matched_rows if row["version_id"] in allowed_version_ids]
                for row in matched_rows:
                    vid = row["version_id"]
                    item = candidates.setdefault(vid, {"row": row, "reasons": set(), "tiers": [], "bm25": row["bm25_rank"], "entities": set(), "aliases": set()})
                    item["reasons"].add(reason)
                    item["tiers"].append(tier)
                    if item["bm25"] is None or row["bm25_rank"] < item["bm25"]:
                        item["bm25"] = row["bm25_rank"]
                return len(matched_rows)

            def qualifying_partial_versions(
                fallback_rows: list[sqlite3.Row],
                channel: str,
            ) -> set[int]:
                """Keep tier-6 candidates only when a local structural group carries query evidence.

                A multi-token fallback requires at least two distinct informative query
                terms in one source-document group, plus an anchor term found in no more
                than 2% of active documents (with a one-document floor). A candidate
                must itself match a contributing term. Groups are limited to the same
                source document and an explicit parent/child or sibling relationship.
                """
                raw_terms = _non_numeric_query_tokens(query)
                if channel == "morphology":
                    terms = [self.morphology.normalize_word(term) for term in raw_terms]
                else:
                    terms = raw_terms
                terms = list(dict.fromkeys(term for term in terms if term and len(term) >= 3))
                if len(terms) < 2 or not fallback_rows:
                    return set()

                term_hits: dict[str, list[sqlite3.Row]] = {}
                term_document_frequency: dict[str, int] = {}
                for term in terms:
                    term_query = (
                        build_morph_fts_query(term, self.morphology)
                        if channel == "morphology"
                        else build_fts_query(term)
                    )
                    hits = fetch_term_rows(term_query)
                    if hits:
                        term_hits[term] = hits
                        term_document_frequency[term] = len({hit["source_path"] for hit in hits})

                if len(term_hits) < 2:
                    return set()

                active_document_count = int(
                    conn.execute("SELECT COUNT(*) FROM documents WHERE state='active'").fetchone()[0]
                )
                anchor_document_limit = max(1, int(active_document_count * 0.02))

                def same_explicit_group(left: sqlite3.Row, right: sqlite3.Row) -> bool:
                    if left["source_path"] != right["source_path"]:
                        return False
                    if left["version_id"] == right["version_id"]:
                        return True
                    if left["node_id"] == right["parent_node_id"]:
                        return True
                    if right["node_id"] == left["parent_node_id"]:
                        return True
                    return (
                        left["parent_node_id"] is not None
                        and left["parent_node_id"] == right["parent_node_id"]
                    )

                allowed: set[int] = set()
                for candidate in fallback_rows:
                    candidate_id = int(candidate["version_id"])
                    own_terms = {
                        term
                        for term, hits in term_hits.items()
                        if any(hit["version_id"] == candidate_id for hit in hits)
                    }
                    if not own_terms:
                        continue

                    group_terms = {
                        term
                        for term, hits in term_hits.items()
                        if any(same_explicit_group(candidate, hit) for hit in hits)
                    }
                    if len(group_terms) == 1:
                        # Preserve the documented exact partial-search control only for a rare
                        # original-form anchor. A lone morphology lemma is not sufficient.
                        if channel != "exact":
                            continue
                        only_term = next(iter(group_terms))
                        if term_document_frequency[only_term] > anchor_document_limit:
                            continue
                    elif len(group_terms) < 2:
                        continue
                    elif not any(term_document_frequency[term] <= anchor_document_limit for term in group_terms):
                        continue
                    allowed.add(candidate_id)
                return allowed

            def with_or_fallback(match_query: str, reason: str, tier: int, channel: str) -> None:
                if not match_query:
                    return
                try:
                    count = collect_fts(match_query, reason, tier)
                    if count == 0 and " AND " in match_query:
                        fallback_query = match_query.replace(" AND ", " OR ")
                        fallback_rows = fetch_fts_rows(fallback_query)
                        allowed_versions = qualifying_partial_versions(fallback_rows, channel)
                        collect_fts(
                            fallback_query,
                            reason + "_or_fallback",
                            6,
                            rows=fallback_rows,
                            allowed_version_ids=allowed_versions,
                        )
                except sqlite3.OperationalError:
                    # Query text is quoted and tokenized before reaching FTS5; this is a last-resort guard.
                    return

            exact_q = build_fts_query(query)
            morph_q = build_morph_fts_query(query, self.morphology)
            with_or_fallback(exact_q, "fts_exact_tokens", 4, "exact")
            if morph_q and morph_q != exact_q:
                with_or_fallback(morph_q, "fts_morphology", 5, "morphology")

            # Numeric lookup uses exact canonical equality, not FTS token or substring matching.
            for number_key, surface, _, _ in extract_numbers(query):
                number_rows = conn.execute(
                    """SELECT DISTINCT v.* FROM node_numbers x JOIN node_versions v ON v.version_id=x.version_id
                       JOIN nodes n ON n.node_id=v.node_id AND n.current_version_id=v.version_id AND n.state='active'
                       WHERE x.value_key=?""", (number_key,)
                ).fetchall()
                for row in number_rows:
                    vid = row["version_id"]
                    item = candidates.setdefault(vid, {"row": row, "reasons": set(), "tiers": [], "bm25": None, "entities": set(), "aliases": set()})
                    item["reasons"].add(f"exact_number:{number_key}")
                    item["tiers"].append(4)

            entity_ids, resolutions = self._resolve_entity_names(entities, conn) if entities else (set(), {})
            if entity_ids:
                placeholders = ",".join("?" for _ in entity_ids)
                rows = conn.execute(
                    f"""SELECT DISTINCT v.*,m.entity_id,m.matched_text,a.alias_text
                        FROM mentions m JOIN nodes n ON n.node_id=m.node_id AND n.current_version_id=m.version_id AND n.state='active'
                        JOIN node_versions v ON v.version_id=m.version_id JOIN entity_aliases a ON a.alias_id=m.alias_id
                        WHERE m.entity_id IN ({placeholders})""", tuple(entity_ids)
                ).fetchall()
                for row in rows:
                    vid = row["version_id"]
                    item = candidates.setdefault(vid, {"row": row, "reasons": set(), "tiers": [], "bm25": None, "entities": set(), "aliases": set()})
                    item["reasons"].add(f"entity_mention:{row['entity_id']}")
                    item["entities"].add(row["entity_id"])
                    item["aliases"].add(row["alias_text"])
                    item["tiers"].append(1)
                primary_rows = conn.execute(
                    f"""SELECT DISTINCT v.*,s.entity_id FROM entity_sources s JOIN node_versions v ON v.source_path=s.source_path
                        JOIN nodes n ON n.node_id=v.node_id AND n.current_version_id=v.version_id AND n.state='active'
                        WHERE s.role='primary_document' AND s.entity_id IN ({placeholders})""", tuple(entity_ids)
                ).fetchall()
                for row in primary_rows:
                    vid = row["version_id"]
                    item = candidates.setdefault(vid, {"row": row, "reasons": set(), "tiers": [], "bm25": None, "entities": set(), "aliases": set()})
                    item["reasons"].add(f"entity_primary_document:{row['entity_id']}")
                    item["entities"].add(row["entity_id"])
                    item["tiers"].append(1)

            # A mixed query containing numbers requires every exact numeric value.
            # Numeric hits alone must also not satisfy a non-numeric part of the query.
            required_number_keys = [key for key, _, _, _ in extract_numbers(query)]
            lexical_query_tokens = _non_numeric_query_tokens(query)
            if required_number_keys:
                for version_id in list(candidates):
                    present_numbers = {r["value_key"] for r in conn.execute(
                        "SELECT value_key FROM node_numbers WHERE version_id=?", (version_id,)
                    ).fetchall()}
                    if not set(required_number_keys).issubset(present_numbers):
                        del candidates[version_id]
                        continue
                    if lexical_query_tokens:
                        row = candidates[version_id]["row"]
                        searchable_exact = set(tokenize(" ".join([
                            row["title_original"], row["path_original"], row["heading_original"], row["raw_text"]
                        ])))
                        searchable_morph = set(tokenize(" ".join([
                            row["title_lemmas"], row["heading_lemmas"], row["raw_lemmas"]
                        ])))
                        query_lemmas = set(self.morphology.normalize_text(" ".join(lexical_query_tokens)).split())
                        if not (set(lexical_query_tokens) & searchable_exact or query_lemmas & searchable_morph):
                            del candidates[version_id]

            # Add human-readable tier evidence, while keeping zones/notes neutral.
            query_tokens = tokenize(query)
            query_fold = " ".join(query_tokens)
            for item in candidates.values():
                row = item["row"]
                title = " ".join(tokenize(row["title_original"]))
                heading = " ".join(tokenize(row["heading_original"]))
                body_tokens = tokenize(row["raw_text"])
                if query_fold and all(t in title.split() for t in query_tokens):
                    item["reasons"].add("document_title_terms")
                    item["tiers"].append(2)
                if query_fold and all(t in heading.split() for t in query_tokens):
                    item["reasons"].add("heading_terms")
                    item["tiers"].append(3)
                if query_tokens and any(body_tokens[i:i + len(query_tokens)] == query_tokens
                                         for i in range(max(0, len(body_tokens) - len(query_tokens) + 1))):
                    item["reasons"].add("exact_body_phrase")
                    item["tiers"].append(4)

            results = []
            for item in candidates.values():
                row = item["row"]
                tier = min(item["tiers"] or [6])
                result = self._row_to_result(row, "ranked_search", query=query)
                result["match_reasons"] = sorted(item["reasons"])
                result["match_type"] = {1: "exact_entity", 2: "document_title", 3: "exact_heading",
                                         4: "exact_word_or_number", 5: "morphological", 6: "partial_lexical"}.get(tier, "lexical")
                # Executor 3's hit schema requires a numeric BM25 field. Non-FTS
                # matches use 0.0 and are still ordered by their higher-level tier.
                result["relevance"] = {"tier": tier, "bm25": float(item["bm25"]) if item["bm25"] is not None else 0.0}
                result["entities"] = sorted(item["entities"])
                result["matched_aliases"] = sorted(item["aliases"])
                results.append(result)
            results.sort(key=lambda r: (r["relevance"]["tier"],
                                        r["relevance"]["bm25"],
                                        r["source_path"], r["line_start"], r["node_id"]))
            results = results[:limit]
            return {"query": query, "entity_resolution": resolutions, "status": "ok" if results else "not_found_in_retrieval",
                    "results": results, "morphology_engine": self.morphology.engine}
        finally:
            conn.close()

    def mentions_for_entity(self, entity_id: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT m.node_id,v.source_path,v.content_hash,v.line_start,v.line_end,m.matched_text,
                          m.start_char,m.end_char,m.matching_method
                   FROM mentions m JOIN nodes n ON n.node_id=m.node_id AND n.current_version_id=m.version_id AND n.state='active'
                   JOIN node_versions v ON v.version_id=m.version_id
                   WHERE m.entity_id=? ORDER BY v.source_path,v.line_start,m.start_char""", (entity_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def check(self) -> dict[str, Any]:
        conn = self._connect()
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            active = conn.execute("SELECT COUNT(*) FROM nodes WHERE state='active' AND current_version_id IS NOT NULL").fetchone()[0]
            current_without_fts = conn.execute(
                """SELECT COUNT(*) FROM nodes n LEFT JOIN node_fts f ON f.rowid=n.current_version_id
                   WHERE n.state='active' AND n.current_version_id IS NOT NULL AND f.rowid IS NULL"""
            ).fetchone()[0]
            dangling_current = conn.execute(
                """SELECT COUNT(*) FROM nodes n LEFT JOIN node_versions v ON v.version_id=n.current_version_id
                   WHERE n.current_version_id IS NOT NULL AND v.version_id IS NULL"""
            ).fetchone()[0]
            generation = int(conn.execute("SELECT value FROM index_meta WHERE key='index_generation'").fetchone()[0])
            morphology_engine = conn.execute("SELECT value FROM index_meta WHERE key='morphology_engine'").fetchone()[0]
            return {"integrity": integrity, "active_nodes": active, "current_nodes_missing_fts": current_without_fts,
                    "dangling_current_versions": dangling_current, "index_generation": generation,
                    "morphology_engine": morphology_engine,
                    "ok": integrity == "ok" and current_without_fts == 0 and dangling_current == 0}
        finally:
            conn.close()


def load_entity_config(index: SFRAIndex, path: str | os.PathLike[str]) -> int:
    """Load explicit entity configuration; aliases default to candidate unless status is explicit."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    entities = data.get("entities") if isinstance(data, dict) else None
    if not isinstance(entities, list):
        raise ValueError("Entity config must contain an 'entities' array")
    count = 0
    for item in entities:
        raw_aliases = item.get("aliases", [])
        candidate_strings = [a for a in raw_aliases if isinstance(a, str)]
        index.create_entity(item["entity_id"], item["canonical_name"], candidate_strings, item.get("primary_source_path"))
        for alias in raw_aliases:
            if isinstance(alias, dict) and isinstance(alias.get("text"), str):
                status = alias.get("status", "candidate")
                if status == "confirmed":
                    index.confirm_alias(item["entity_id"], alias["text"])
                elif status == "rejected":
                    index.reject_alias(item["entity_id"], alias["text"])
                else:
                    index.add_alias_candidate(item["entity_id"], alias["text"])
        count += 1
    return count
