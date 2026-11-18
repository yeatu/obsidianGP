"""Additive read-only verifier for materialized E1 cloud-index snapshots."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import unicodedata
from typing import Any

from .lookup import (
    NodeLookupStatus, _LookupFailure, _check_db_snapshot, _decode_json,
    _read_only_connection, _read_source_file, _resolve_db_status,
    _safe_source_components, _validate_events, _verify_database,
    _verify_document_bytes, _verify_node_from_source, _valid_hash,
    _valid_node_id,
)

ATTESTATION_FORMAT = "sfra.e1.cloud-index-attestation.v1"
INVENTORY_FORMAT = "sfra.e1.markdown-inventory.v1"
SUPPORTED_SCHEMA_VERSION = 2
DATABASE_PATH = "state/structure.sqlite3"
INVENTORY_PATH = "markdown-inventory.json"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_GIT_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_MUTABLE_IMPORT_ALIASES = frozenset({"latest", "current", "head", "*"})
_REQUIRED_COLUMNS = {
    "schema_info": {"singleton", "schema_version"},
    "documents": {"document_pk", "source_path", "source_size_bytes", "parser_name",
                  "parser_version", "indexed_at", "source_sha256", "generation", "status"},
    "structural_nodes": {"node_pk", "document_pk", "local_key", "node_id", "parent_node_pk",
                         "node_type", "heading_path_json", "line_start", "line_end", "char_start",
                         "char_end", "byte_start", "byte_end", "content_spans_json", "raw_text",
                         "metadata_json", "warnings_json", "content_hash", "status",
                         "created_generation", "updated_generation", "stale_generation"},
    "passages": {"passage_pk", "document_pk", "owner_node_pk", "passage_key", "ordinal",
                 "line_start", "line_end", "char_start", "char_end", "byte_start", "byte_end",
                 "raw_text", "context_text", "context_spans_json", "estimated_words", "warnings_json"},
    "node_versions": {"node_version_pk", "node_pk", "version_no", "generation", "content_hash",
                      "source_path", "node_type", "parent_node_id", "heading_path_json",
                      "line_start", "line_end", "char_start", "char_end", "byte_start",
                      "byte_end", "content_spans_json", "raw_text", "metadata_json",
                      "warnings_json", "created_at"},
    "node_match_events": {"event_pk", "document_pk", "generation", "new_local_key",
                          "event_type", "node_id", "candidate_node_ids_json", "details_json", "created_at"},
}


class CloudIndexVerificationError(ValueError):
    """Stable failure code with a safe, non-sensitive message."""
    _MESSAGES = {
        "attestation_invalid": "The E1 cloud-index attestation is malformed or unsupported.",
        "source_revision_invalid": "The attested source revision is invalid.",
        "inventory_invalid": "The canonical Markdown inventory is malformed or unsupported.",
        "inventory_mismatch": "The materialized Markdown tree does not match its attested inventory.",
        "filesystem_unsafe": "The materialized source tree contains an unsafe or unreadable entry.",
        "filesystem_race": "A source file changed while the materialized snapshot was verified.",
        "database_invalid": "The SQLite database file is missing, unsafe or unreadable.",
        "database_digest_mismatch": "The SQLite database digest does not match the attestation.",
        "database_size_mismatch": "The SQLite database size does not match the attestation.",
        "sqlite_integrity_failure": "The SQLite database failed its physical integrity check.",
        "foreign_key_failure": "The SQLite database contains foreign-key violations.",
        "schema_mismatch": "The SQLite database does not match the supported E1 schema.",
        "document_mismatch": "The active E1 documents do not match the Markdown inventory.",
        "parser_identity_mismatch": "The active document parser identities do not match the attestation.",
        "node_integrity_failure": "The E1 nodes, versions, spans or matching history are inconsistent.",
        "attestation_counts_mismatch": "The SQLite counts do not match the attestation.",
        "indexer_identity_mismatch": "The E1 indexer identity does not match the installed implementation.",
        "verification_failed": "The materialized E1 cloud index could not be verified.",
    }

    def __init__(self, code: str):
        if code not in self._MESSAGES:
            code = "verification_failed"
        self.code = code
        super().__init__(self._MESSAGES[code])


@dataclass(frozen=True, slots=True)
class GitCommitSourceRevision:
    commit_sha: str

    def __post_init__(self) -> None:
        if not isinstance(self.commit_sha, str) or not _GIT_SHA_RE.fullmatch(self.commit_sha):
            raise ValueError("invalid Git commit source revision")

    def to_dict(self) -> dict[str, str]:
        return {"kind": "git_commit", "commit_sha": self.commit_sha}


@dataclass(frozen=True, slots=True)
class ImmutableImportSourceRevision:
    import_id: str

    def __post_init__(self) -> None:
        _validate_import_id(self.import_id)

    def to_dict(self) -> dict[str, str]:
        return {"kind": "immutable_import", "import_id": self.import_id}


SourceRevision = GitCommitSourceRevision | ImmutableImportSourceRevision


@dataclass(frozen=True, slots=True)
class IndexerIdentity:
    name: str
    version: str


@dataclass(frozen=True, slots=True)
class ParserIdentity:
    name: str
    version: str


@dataclass(frozen=True, slots=True)
class CloudIndexAttestation:
    source_revision: SourceRevision
    markdown_inventory_sha256: str
    markdown_document_count: int
    indexer_identity: IndexerIdentity
    parser_identities: tuple[ParserIdentity, ...]
    schema_info_version: int
    database_sha256: str
    database_byte_size: int
    document_count: int
    active_document_count: int
    node_count: int
    active_node_count: int
    passage_count: int


@dataclass(frozen=True, slots=True)
class CloudIndexVerificationReport:
    source_revision: SourceRevision
    database_sha256: str
    database_byte_size: int
    schema_info_version: int
    indexer_identity: IndexerIdentity
    parser_identities: tuple[ParserIdentity, ...]
    markdown_inventory_sha256: str
    markdown_document_count: int
    document_count: int
    active_document_count: int
    node_count: int
    active_node_count: int
    passage_count: int


def _validate_import_id(value: Any) -> str:
    if (
        not isinstance(value, str) or not value or len(value) > 4096
        or value != value.strip() or value != unicodedata.normalize("NFC", value)
        or any(unicodedata.category(ch) in {"Cc", "Cs"} for ch in value)
        or value.casefold() in _MUTABLE_IMPORT_ALIASES
    ):
        raise ValueError("invalid immutable import identifier")
    value.encode("utf-8", errors="strict")
    return value


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _canonical_object(raw: bytes) -> dict[str, Any]:
    if not isinstance(raw, bytes):
        raise ValueError("payload must be bytes")
    value = json.loads(
        raw.decode("utf-8", errors="strict"),
        object_pairs_hook=_reject_duplicate_pairs,
        parse_constant=lambda _v: (_ for _ in ()).throw(ValueError("invalid JSON constant")),
    )
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    canonical = json.dumps(value, ensure_ascii=False, allow_nan=False,
                           sort_keys=True, separators=(",", ":")).encode("utf-8", errors="strict")
    if canonical != raw:
        raise ValueError("JSON is not canonical")
    return value


def _exact(value: Any, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("object fields do not match schema")
    return value


def _text(value: Any, limit: int = 4096) -> str:
    if (
        not isinstance(value, str) or not value or len(value) > limit
        or value != value.strip() or value != unicodedata.normalize("NFC", value)
        or any(unicodedata.category(ch) in {"Cc", "Cs"} for ch in value)
    ):
        raise ValueError("invalid text")
    value.encode("utf-8", errors="strict")
    return value


def _uint(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("expected non-negative integer")
    return value


def _revision(value: Any) -> SourceRevision:
    if not isinstance(value, dict):
        raise ValueError("source revision must be an object")
    if value.get("kind") == "git_commit":
        item = _exact(value, {"kind", "commit_sha"})
        return GitCommitSourceRevision(item["commit_sha"])
    if value.get("kind") == "immutable_import":
        item = _exact(value, {"kind", "import_id"})
        return ImmutableImportSourceRevision(item["import_id"])
    raise ValueError("unknown source revision tag")


def parse_cloud_index_attestation(raw: bytes) -> CloudIndexAttestation:
    """Parse exact canonical attestation bytes into immutable E1-owned types."""
    try:
        obj = _exact(_canonical_object(raw), {
            "attestation_version", "format", "source_revision", "markdown_inventory",
            "indexer_identity", "parser_identities", "sqlite_schema_identity", "database", "counts",
        })
        if type(obj["attestation_version"]) is not int or obj["attestation_version"] != 1:
            raise ValueError("unsupported version")
        if obj["format"] != ATTESTATION_FORMAT:
            raise ValueError("unsupported format")
        try:
            revision = _revision(obj["source_revision"])
        except Exception as exc:
            raise CloudIndexVerificationError("source_revision_invalid") from exc

        inventory = _exact(obj["markdown_inventory"], {"format", "path", "sha256", "document_count"})
        if (inventory["format"] != INVENTORY_FORMAT or inventory["path"] != INVENTORY_PATH
                or not isinstance(inventory["sha256"], str) or not _SHA256_RE.fullmatch(inventory["sha256"])):
            raise ValueError("invalid inventory descriptor")
        inventory_count = _uint(inventory["document_count"])

        indexer = _exact(obj["indexer_identity"], {"name", "version"})
        indexer_identity = IndexerIdentity(_text(indexer["name"], 256), _text(indexer["version"], 128))
        if indexer_identity.name != "sfra-structural-indexer":
            raise ValueError("unknown E1 indexer")

        raw_parsers = obj["parser_identities"]
        if not isinstance(raw_parsers, list):
            raise ValueError("parser identities must be an array")
        parsers = []
        for raw_parser in raw_parsers:
            parser = _exact(raw_parser, {"name", "version"})
            parsers.append(ParserIdentity(_text(parser["name"], 256), _text(parser["version"], 128)))
        parser_keys = [(p.name.encode("utf-8"), p.version.encode("utf-8")) for p in parsers]
        if parser_keys != sorted(parser_keys) or len(set(parser_keys)) != len(parser_keys):
            raise ValueError("parser identities are not canonical")

        schema = _exact(obj["sqlite_schema_identity"], {"engine", "schema_info_version"})
        if schema["engine"] != "sqlite" or type(schema["schema_info_version"]) is not int:
            raise ValueError("invalid schema identity")
        if schema["schema_info_version"] != SUPPORTED_SCHEMA_VERSION:
            raise ValueError("unsupported schema version")

        database = _exact(obj["database"], {"path", "sha256", "byte_size"})
        if (database["path"] != DATABASE_PATH or not isinstance(database["sha256"], str)
                or not _SHA256_RE.fullmatch(database["sha256"])):
            raise ValueError("invalid database descriptor")
        counts = _exact(obj["counts"], {
            "document_count", "active_document_count", "node_count",
            "active_node_count", "passage_count",
        })
        return CloudIndexAttestation(
            source_revision=revision,
            markdown_inventory_sha256=inventory["sha256"],
            markdown_document_count=inventory_count,
            indexer_identity=indexer_identity,
            parser_identities=tuple(parsers),
            schema_info_version=schema["schema_info_version"],
            database_sha256=database["sha256"],
            database_byte_size=_uint(database["byte_size"]),
            document_count=_uint(counts["document_count"]),
            active_document_count=_uint(counts["active_document_count"]),
            node_count=_uint(counts["node_count"]),
            active_node_count=_uint(counts["active_node_count"]),
            passage_count=_uint(counts["passage_count"]),
        )
    except CloudIndexVerificationError:
        raise
    except Exception as exc:
        raise CloudIndexVerificationError("attestation_invalid") from exc


def _safe_path(value: Any) -> str:
    # Match #119's canonical relative-POSIX path contract exactly. Do not add
    # normalization or whitespace restrictions that its producer does not use.
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value or "\x00" in value:
        raise ValueError("unsafe path")
    value.encode("utf-8", errors="strict")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts) or PurePosixPath(value).is_absolute():
        raise ValueError("unsafe path")
    return value


def _read_regular(path: Path) -> bytes:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise CloudIndexVerificationError("filesystem_unsafe")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(fd)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise CloudIndexVerificationError("filesystem_race")
        chunks = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
        signature_before = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
        signature_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        raw = b"".join(chunks)
        if signature_before != signature_after or len(raw) != after.st_size:
            raise CloudIndexVerificationError("filesystem_race")
        return raw
    finally:
        os.close(fd)


def _collect_source_files(source_root: str | Path) -> tuple[tuple[str, bytes], ...]:
    requested = Path(source_root).expanduser()
    if requested.is_symlink():
        raise CloudIndexVerificationError("filesystem_unsafe")
    try:
        root = requested.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise CloudIndexVerificationError("filesystem_unsafe") from exc
    if not root.is_dir():
        raise CloudIndexVerificationError("filesystem_unsafe")
    files: list[tuple[str, bytes]] = []
    seen: set[str] = set()

    def walk(directory: Path, prefix: str) -> None:
        try:
            with os.scandir(directory) as scan:
                entries = list(scan)
            entries.sort(key=lambda item: item.name.encode("utf-8", errors="strict"))
        except (OSError, UnicodeError) as exc:
            raise CloudIndexVerificationError("filesystem_unsafe") from exc
        for entry in entries:
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            try:
                relative = _safe_path(relative)
                if relative in seen or entry.is_symlink():
                    raise CloudIndexVerificationError("filesystem_unsafe")
                seen.add(relative)
                if entry.is_dir(follow_symlinks=False):
                    walk(Path(entry.path), relative)
                elif entry.is_file(follow_symlinks=False):
                    raw = _read_regular(Path(entry.path))
                    if PurePosixPath(relative).suffix.lower() == ".md":
                        raw.decode("utf-8", errors="strict")
                    files.append((relative, raw))
                else:
                    raise CloudIndexVerificationError("filesystem_unsafe")
            except CloudIndexVerificationError:
                raise
            except (OSError, UnicodeError, ValueError) as exc:
                raise CloudIndexVerificationError("filesystem_unsafe") from exc

    walk(root, "")
    files.sort(key=lambda item: item[0].encode("utf-8", errors="strict"))
    return tuple(files)


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8", errors="strict")


def _expected_inventory(files: tuple[tuple[str, bytes], ...]) -> bytes:
    documents = []
    for path, raw in files:
        if PurePosixPath(path).suffix.lower() == ".md":
            raw.decode("utf-8", errors="strict")
            documents.append({
                "path": path,
                "byte_size": len(raw),
                "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
            })
    documents.sort(key=lambda item: item["path"].encode("utf-8", errors="strict"))
    return _canonical_bytes({"format": INVENTORY_FORMAT, "documents": documents})


def _validate_inventory(raw: bytes, expected: bytes, att: CloudIndexAttestation) -> None:
    try:
        obj = _exact(_canonical_object(raw), {"format", "documents"})
        if obj["format"] != INVENTORY_FORMAT or not isinstance(obj["documents"], list):
            raise ValueError("unsupported inventory")
        seen: set[str] = set()
        previous: bytes | None = None
        for row in obj["documents"]:
            item = _exact(row, {"path", "byte_size", "sha256"})
            path = _safe_path(item["path"])
            if PurePosixPath(path).suffix.lower() != ".md" or path in seen:
                raise ValueError("invalid or duplicate inventory path")
            seen.add(path)
            encoded = path.encode("utf-8", errors="strict")
            if previous is not None and encoded <= previous:
                raise ValueError("inventory is not byte-sorted")
            previous = encoded
            _uint(item["byte_size"])
            if not isinstance(item["sha256"], str) or not _SHA256_RE.fullmatch(item["sha256"]):
                raise ValueError("invalid file digest")
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        if digest != att.markdown_inventory_sha256 or len(obj["documents"]) != att.markdown_document_count:
            raise CloudIndexVerificationError("inventory_mismatch")
        if raw != expected:
            raise CloudIndexVerificationError("inventory_mismatch")
    except CloudIndexVerificationError:
        raise
    except Exception as exc:
        raise CloudIndexVerificationError("inventory_invalid") from exc


def _database_bytes(path: str | Path) -> tuple[Path, bytes, tuple[int, int, int, int, int]]:
    requested = Path(path).expanduser()
    try:
        if requested.is_symlink():
            raise CloudIndexVerificationError("database_invalid")
        canonical = requested.resolve(strict=True)
        before = canonical.stat()
        if not stat.S_ISREG(before.st_mode):
            raise CloudIndexVerificationError("database_invalid")
        raw = _read_regular(canonical)
        after = canonical.stat()
        signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if signature(before) != signature(after) or len(raw) != after.st_size:
            raise CloudIndexVerificationError("database_invalid")
        return canonical, raw, signature(after)
    except CloudIndexVerificationError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise CloudIndexVerificationError("database_invalid") from exc


def _required_schema(connection: sqlite3.Connection) -> None:
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables != set(_REQUIRED_COLUMNS):
            raise CloudIndexVerificationError("schema_mismatch")
        for table, required in _REQUIRED_COLUMNS.items():
            actual = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            if actual != required:
                raise CloudIndexVerificationError("schema_mismatch")
        rows = connection.execute("SELECT schema_version FROM schema_info WHERE singleton=1").fetchall()
        if len(rows) != 1 or type(rows[0][0]) is not int or rows[0][0] != SUPPORTED_SCHEMA_VERSION:
            raise CloudIndexVerificationError("schema_mismatch")
    except CloudIndexVerificationError:
        raise
    except sqlite3.Error as exc:
        raise CloudIndexVerificationError("schema_mismatch") from exc


def _verify_database_consistency(
    db_path: Path, source_root: Path
) -> tuple[tuple[int, int, int, int, int], tuple[ParserIdentity, ...]]:
    connection: sqlite3.Connection | None = None
    try:
        connection = _read_only_connection(db_path)
        if (not connection.in_transaction
                or connection.execute("PRAGMA query_only").fetchone()[0] != 1):
            raise CloudIndexVerificationError("sqlite_integrity_failure")
        _verify_database(connection)
        _required_schema(connection)

        documents = [dict(row) for row in connection.execute("SELECT * FROM documents ORDER BY document_pk")]
        nodes = [dict(row) for row in connection.execute("SELECT * FROM structural_nodes ORDER BY node_pk")]
        doc_by_pk = {row["document_pk"]: row for row in documents}
        if len(doc_by_pk) != len(documents) or any(type(key) is not int for key in doc_by_pk):
            raise CloudIndexVerificationError("document_mismatch")

        active_docs: dict[str, dict[str, Any]] = {}
        parser_pairs: set[tuple[str, str]] = set()
        for doc in documents:
            path = _safe_path(doc.get("source_path"))
            if (not _valid_hash(doc.get("source_sha256"))
                    or type(doc.get("source_size_bytes")) is not int or doc["source_size_bytes"] < 0
                    or type(doc.get("generation")) is not int or doc["generation"] < 1
                    or doc.get("status") not in {"active", "deleted"}
                    or not isinstance(doc.get("parser_name"), str) or not doc["parser_name"]
                    or not isinstance(doc.get("parser_version"), str) or not doc["parser_version"]):
                raise CloudIndexVerificationError("document_mismatch")
            if doc["status"] == "active":
                if path in active_docs:
                    raise CloudIndexVerificationError("document_mismatch")
                active_docs[path] = doc
                parser_pairs.add((doc["parser_name"], doc["parser_version"]))

        expected_paths = {
            path for path, _ in _collect_source_files(source_root)
            if PurePosixPath(path).suffix.lower() == ".md"
        }
        if set(active_docs) != expected_paths:
            raise CloudIndexVerificationError("document_mismatch")

        source_bytes: dict[int, bytes] = {}
        source_text: dict[int, str] = {}
        events_by_doc: dict[int, list[dict[str, Any]]] = {}
        for doc_pk, doc in doc_by_pk.items():
            events_by_doc[doc_pk] = _validate_events(connection, doc_pk, doc["generation"])
            if doc["status"] == "active":
                components = _safe_source_components(doc["source_path"])
                raw = _read_source_file(source_root, components)
                source_bytes[doc_pk] = raw
                source_text[doc_pk] = _verify_document_bytes(doc, raw)

        node_ids: set[str] = set()
        node_ids_by_doc: dict[int, set[str]] = {}
        node_pk_to_doc = {node["node_pk"]: node["document_pk"] for node in nodes}
        if len(node_pk_to_doc) != len(nodes):
            raise CloudIndexVerificationError("node_integrity_failure")
        active_node_count = 0
        for node in nodes:
            doc = doc_by_pk.get(node.get("document_pk"))
            if doc is None:
                raise CloudIndexVerificationError("node_integrity_failure")
            node_id = node.get("node_id")
            if not _valid_node_id(node_id) or node_id in node_ids:
                raise CloudIndexVerificationError("node_integrity_failure")
            node_ids.add(node_id)
            node_ids_by_doc.setdefault(doc["document_pk"], set()).add(node_id)
            events = events_by_doc[doc["document_pk"]]
            heading_path, parent_id, latest_event = _check_db_snapshot(connection, node, doc, events)
            status = _resolve_db_status(node, doc, latest_event)
            if node["status"] in {"active", "ambiguous"} and node.get("stale_generation") is None:
                if doc["status"] != "active":
                    raise CloudIndexVerificationError("node_integrity_failure")
                active_node_count += 1
                _verify_node_from_source(
                    node=node,
                    document=doc,
                    parent_node_id=parent_id,
                    heading_path=heading_path,
                    metadata=_decode_json(
                        node["metadata_json"], dict, "node_metadata_invalid",
                        "The stored node metadata is invalid.",
                    ),
                    source_bytes=source_bytes[doc["document_pk"]],
                    source_text=source_text[doc["document_pk"]],
                    expected_hash=node["content_hash"],
                )
            elif status is None:
                raise CloudIndexVerificationError("node_integrity_failure")

        for doc_pk, events in events_by_doc.items():
            document_node_ids = node_ids_by_doc.get(doc_pk, set())
            for event in events:
                if event["node_id"] not in document_node_ids or any(
                    candidate not in document_node_ids for candidate in event["candidate_node_ids"]
                ):
                    raise CloudIndexVerificationError("node_integrity_failure")

        versions = connection.execute(
            "SELECT node_pk, source_path, content_hash, raw_text, heading_path_json, "
            "content_spans_json, metadata_json, warnings_json FROM node_versions"
        ).fetchall()
        for version in versions:
            row = dict(version)
            doc_pk = node_pk_to_doc.get(row["node_pk"])
            if (doc_pk is None or row["source_path"] != doc_by_pk[doc_pk]["source_path"]
                    or not _valid_hash(row["content_hash"]) or not isinstance(row["raw_text"], str)
                    or "sha256:" + hashlib.sha256(row["raw_text"].encode("utf-8", errors="strict")).hexdigest()
                    != row["content_hash"]):
                raise CloudIndexVerificationError("node_integrity_failure")
            _decode_json(row["heading_path_json"], list, "node_integrity_failure", "Invalid version data.")
            _decode_json(row["content_spans_json"], list, "node_integrity_failure", "Invalid version data.")
            _decode_json(row["metadata_json"], dict, "node_integrity_failure", "Invalid version data.")
            _decode_json(row["warnings_json"], list, "node_integrity_failure", "Invalid version data.")

        counts = (
            len(documents),
            len(active_docs),
            len(nodes),
            active_node_count,
            int(connection.execute("SELECT COUNT(*) FROM passages").fetchone()[0]),
        )
        parsers = tuple(
            ParserIdentity(name, version)
            for name, version in sorted(
                parser_pairs, key=lambda pair: (pair[0].encode("utf-8"), pair[1].encode("utf-8"))
            )
        )
        return counts, parsers
    except CloudIndexVerificationError:
        raise
    except _LookupFailure as exc:
        code = {
            "foreign_key_failure": "foreign_key_failure",
            "sqlite_integrity_failure": "sqlite_integrity_failure",
            "schema_incomplete": "schema_mismatch",
            "schema_version_unsupported": "schema_mismatch",
            "db_path_invalid": "database_invalid",
            "sqlite_open_failed": "database_invalid",
        }.get(exc.code, "node_integrity_failure")
        raise CloudIndexVerificationError(code) from exc
    except sqlite3.Error as exc:
        raise CloudIndexVerificationError("sqlite_integrity_failure") from exc
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        raise CloudIndexVerificationError("node_integrity_failure") from exc
    finally:
        if connection is not None:
            connection.close()


def _installed_indexer_version() -> str:
    try:
        return importlib.metadata.version("sfra-structural-indexer")
    except importlib.metadata.PackageNotFoundError as exc:
        raise CloudIndexVerificationError("indexer_identity_mismatch") from exc


def verify_materialized_cloud_index(
    database_path: str | Path,
    source_root: str | Path,
    *,
    attestation: bytes,
    markdown_inventory: bytes,
) -> CloudIndexVerificationReport:
    """Verify an already-materialized source tree and SQLite database read-only.

    The two byte arguments must be the exact attestation and inventory payloads
    from #119. This E1 boundary verifies consistency, not source-origin
    authenticity, provider immutability or the outer CloudSnapshotRef.
    """
    parsed = parse_cloud_index_attestation(attestation)
    try:
        if (parsed.indexer_identity.name != "sfra-structural-indexer"
                or parsed.indexer_identity.version != _installed_indexer_version()):
            raise CloudIndexVerificationError("indexer_identity_mismatch")

        root = Path(source_root).expanduser()
        if root.is_symlink():
            raise CloudIndexVerificationError("filesystem_unsafe")
        root = root.resolve(strict=True)
        files = _collect_source_files(root)
        _validate_inventory(markdown_inventory, _expected_inventory(files), parsed)

        db_path, db_bytes, signature = _database_bytes(database_path)
        actual_digest = "sha256:" + hashlib.sha256(db_bytes).hexdigest()
        if actual_digest != parsed.database_sha256:
            raise CloudIndexVerificationError("database_digest_mismatch")
        if len(db_bytes) != parsed.database_byte_size:
            raise CloudIndexVerificationError("database_size_mismatch")

        counts, parsers = _verify_database_consistency(db_path, root)
        after = db_path.stat()
        after_signature = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if after_signature != signature:
            raise CloudIndexVerificationError("database_invalid")
        if parsed.markdown_document_count != parsed.active_document_count:
            raise CloudIndexVerificationError("document_mismatch")
        if counts != (
            parsed.document_count, parsed.active_document_count, parsed.node_count,
            parsed.active_node_count, parsed.passage_count,
        ):
            raise CloudIndexVerificationError("attestation_counts_mismatch")
        if parsers != parsed.parser_identities:
            raise CloudIndexVerificationError("parser_identity_mismatch")

        return CloudIndexVerificationReport(
            source_revision=parsed.source_revision,
            database_sha256=actual_digest,
            database_byte_size=len(db_bytes),
            schema_info_version=parsed.schema_info_version,
            indexer_identity=parsed.indexer_identity,
            parser_identities=parsers,
            markdown_inventory_sha256=parsed.markdown_inventory_sha256,
            markdown_document_count=parsed.markdown_document_count,
            document_count=counts[0],
            active_document_count=counts[1],
            node_count=counts[2],
            active_node_count=counts[3],
            passage_count=counts[4],
        )
    except CloudIndexVerificationError:
        raise
    except _LookupFailure as exc:
        raise CloudIndexVerificationError("node_integrity_failure") from exc
    except Exception as exc:
        raise CloudIndexVerificationError("verification_failed") from exc


__all__ = [
    "ATTESTATION_FORMAT", "INVENTORY_FORMAT", "CloudIndexAttestation",
    "CloudIndexVerificationError", "CloudIndexVerificationReport",
    "GitCommitSourceRevision", "ImmutableImportSourceRevision", "IndexerIdentity",
    "ParserIdentity", "parse_cloud_index_attestation", "verify_materialized_cloud_index",
]
