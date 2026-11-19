"""Additive read-only verifier for materialized E1 cloud-index snapshots."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import codecs
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import unicodedata
from typing import Any, Iterator

from .lookup import (
    _LookupFailure, _check_db_snapshot, _decode_json,
    _read_only_connection, _resolve_db_status, _validate_events, _verify_database,
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
# C3 decision #260: operational resource envelope for the E1 verifier.
MAX_ATTESTATION_BYTES = 2 * 1024 * 1024
MAX_INVENTORY_BYTES = 64 * 1024 * 1024
MAX_MARKDOWN_DOCUMENT_ROWS = 100_000
MAX_PARSER_IDENTITIES = 256
MAX_SOURCE_TREE_ENTRIES = 500_000
MAX_MARKDOWN_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_TOTAL_MARKDOWN_BYTES = 2 * 1024 * 1024 * 1024
MAX_SOURCE_PATH_CHARS = 4096
MAX_PATH_COMPONENT_BYTES = 4096
_READ_CHUNK_BYTES = 1024 * 1024
_ALLOWED_NODE_TYPES = frozenset({
    "document", "heading", "paragraph", "list", "list_item", "quote",
    "callout", "table", "code_block", "html_block", "thematic_break",
})

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
        "source_revision_mismatch": "The attested source revision does not match the outer verified revision.",
        "resource_limit_exceeded": "The materialized snapshot exceeds the E1 verifier resource envelope.",
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
        "node_identity_mismatch": "The E1 node identifiers are missing, malformed or duplicated.",
        "node_reference_mismatch": "An E1 node or parent reference is inconsistent.",
        "node_content_mismatch": "An E1 node or historical content hash is inconsistent.",
        "node_span_mismatch": "An E1 source coordinate or span is inconsistent.",
        "node_generation_mismatch": "An E1 node or document generation is inconsistent.",
        "node_history_mismatch": "The E1 node lifecycle or matching event history is inconsistent.",
        "node_version_mismatch": "The E1 node version chain is inconsistent.",
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
    if type(raw) is not bytes:
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


def _canonical_attestation_object(raw: bytes) -> dict[str, Any]:
    """Decode the attestation's parser identity array with an incremental cap."""
    try:
        text = raw.decode("utf-8", errors="strict")
        decoder = json.JSONDecoder(
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda _v: (_ for _ in ()).throw(ValueError("invalid JSON constant")),
        )
        cursor = 0

        def skip_space(position: int) -> int:
            while position < len(text) and text[position] in " \t\r\n":
                position += 1
            return position

        cursor = skip_space(cursor)
        if cursor >= len(text) or text[cursor] != "{":
            raise ValueError("attestation root must be an object")
        cursor += 1
        result: dict[str, Any] = {}
        while True:
            cursor = skip_space(cursor)
            if cursor < len(text) and text[cursor] == "}":
                cursor += 1
                break
            if result:
                if cursor >= len(text) or text[cursor] != ",":
                    raise ValueError("attestation object separator is invalid")
                cursor = skip_space(cursor + 1)
            key, cursor = decoder.raw_decode(text, cursor)
            if not isinstance(key, str) or key in result:
                raise ValueError("attestation contains a duplicate or non-text key")
            cursor = skip_space(cursor)
            if cursor >= len(text) or text[cursor] != ":":
                raise ValueError("attestation object member is malformed")
            cursor = skip_space(cursor + 1)

            if key == "parser_identities":
                if cursor >= len(text) or text[cursor] != "[":
                    raise ValueError("parser identities must be an array")
                cursor += 1
                parser_rows: list[Any] = []
                while True:
                    cursor = skip_space(cursor)
                    if cursor >= len(text):
                        raise ValueError("parser identity array is unterminated")
                    if text[cursor] == "]":
                        cursor += 1
                        break
                    if parser_rows:
                        if text[cursor] != ",":
                            raise ValueError("parser identity separator is invalid")
                        cursor = skip_space(cursor + 1)
                    row, cursor = decoder.raw_decode(text, cursor)
                    if len(parser_rows) >= MAX_PARSER_IDENTITIES:
                        raise CloudIndexVerificationError("resource_limit_exceeded")
                    parser_rows.append(row)
                result[key] = parser_rows
            else:
                value, cursor = decoder.raw_decode(text, cursor)
                result[key] = value

        if skip_space(cursor) != len(text):
            raise ValueError("trailing attestation bytes")
        if _canonical_bytes(result) != raw:
            raise ValueError("attestation bytes are not canonical")
        return result
    except CloudIndexVerificationError:
        raise
    except Exception:
        raise ValueError("attestation is not canonical UTF-8 JSON") from None


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
    if type(raw) is not bytes:
        raise CloudIndexVerificationError("attestation_invalid")
    if len(raw) > MAX_ATTESTATION_BYTES:
        raise CloudIndexVerificationError("resource_limit_exceeded")
    try:
        obj = _exact(_canonical_attestation_object(raw), {
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
            raise CloudIndexVerificationError("source_revision_invalid") from None

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
        if len(raw_parsers) > MAX_PARSER_IDENTITIES:
            raise CloudIndexVerificationError("resource_limit_exceeded")
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
        raise CloudIndexVerificationError("attestation_invalid") from None


def _safe_path(value: Any) -> str:
    # Retain #119's relative POSIX path rules; E1 adds a separate admission cap.
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value or "\x00" in value:
        raise ValueError("unsafe path")
    value.encode("utf-8", errors="strict")
    if len(value) > MAX_SOURCE_PATH_CHARS:
        raise CloudIndexVerificationError("resource_limit_exceeded")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts) or PurePosixPath(value).is_absolute():
        raise ValueError("unsafe path")
    if any(len(part.encode("utf-8", errors="strict")) > MAX_PATH_COMPONENT_BYTES for part in parts):
        raise CloudIndexVerificationError("resource_limit_exceeded")
    return value


@dataclass(frozen=True, slots=True)
class _MarkdownFile:
    path: str
    byte_size: int
    sha256: str


def _identity(st: os.stat_result) -> tuple[int, int]:
    return st.st_dev, st.st_ino


def _signature(st: os.stat_result) -> tuple[int, int, int, int, int]:
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _directory_flags() -> int:
    if (
        os.name != "posix" or not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
    ):
        raise CloudIndexVerificationError("filesystem_unsafe")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _file_flags() -> int:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise CloudIndexVerificationError("filesystem_unsafe")
    return (
        os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )


def _open_absolute_directory(path: Path) -> int:
    """Open each absolute path component without following symlinks."""
    current = os.open(
        "/", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        for component in path.parts[1:]:
            before = os.stat(component, dir_fd=current, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode):
                raise CloudIndexVerificationError("filesystem_unsafe")
            child = os.open(component, _directory_flags(), dir_fd=current)
            opened = os.fstat(child)
            if _identity(before) != _identity(opened) or not stat.S_ISDIR(opened.st_mode):
                os.close(child)
                raise CloudIndexVerificationError("filesystem_race")
            os.close(current)
            current = child
        return current
    except CloudIndexVerificationError:
        os.close(current)
        raise
    except OSError:
        os.close(current)
        raise CloudIndexVerificationError("filesystem_unsafe") from None


@contextmanager
def _pin_source_root(source_root: str | Path) -> Iterator[int]:
    """Pin a real root directory FD for all descendant operations."""
    requested = Path(source_root).expanduser()
    try:
        if requested.is_symlink():
            raise CloudIndexVerificationError("filesystem_unsafe")
        canonical = requested.resolve(strict=True)
        if not canonical.is_dir():
            raise CloudIndexVerificationError("filesystem_unsafe")
        root_fd = _open_absolute_directory(canonical)
    except CloudIndexVerificationError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise CloudIndexVerificationError("filesystem_unsafe") from None
    try:
        if not stat.S_ISDIR(os.fstat(root_fd).st_mode):
            raise CloudIndexVerificationError("filesystem_unsafe")
        yield root_fd
    finally:
        os.close(root_fd)


def _open_directory_relative(
    root_fd: int,
    relative: str,
    *,
    expected_identity: tuple[int, int] | None = None,
) -> int:
    """Open a directory beneath root_fd, rejecting symlinks in every component."""
    current = os.dup(root_fd)
    try:
        if relative:
            for component in relative.split("/"):
                before = os.stat(component, dir_fd=current, follow_symlinks=False)
                if not stat.S_ISDIR(before.st_mode):
                    raise CloudIndexVerificationError("filesystem_race")
                child = os.open(component, _directory_flags(), dir_fd=current)
                opened = os.fstat(child)
                if _identity(before) != _identity(opened) or not stat.S_ISDIR(opened.st_mode):
                    os.close(child)
                    raise CloudIndexVerificationError("filesystem_race")
                os.close(current)
                current = child
        opened = os.fstat(current)
        if not stat.S_ISDIR(opened.st_mode):
            raise CloudIndexVerificationError("filesystem_unsafe")
        if expected_identity is not None and _identity(opened) != expected_identity:
            raise CloudIndexVerificationError("filesystem_race")
        return current
    except CloudIndexVerificationError:
        os.close(current)
        raise
    except OSError:
        os.close(current)
        raise CloudIndexVerificationError("filesystem_race") from None


def _open_regular_at(parent_fd: int, name: str, before: os.stat_result) -> int:
    if not stat.S_ISREG(before.st_mode):
        raise CloudIndexVerificationError("filesystem_unsafe")
    try:
        fd = os.open(name, _file_flags(), dir_fd=parent_fd)
    except OSError:
        raise CloudIndexVerificationError("filesystem_race") from None
    opened = os.fstat(fd)
    if not stat.S_ISREG(opened.st_mode) or _identity(opened) != _identity(before):
        os.close(fd)
        raise CloudIndexVerificationError("filesystem_race")
    return fd


def _hash_markdown_fd(fd: int, expected_size: int, aggregate_before: int) -> tuple[int, str]:
    if (
        expected_size > MAX_MARKDOWN_DOCUMENT_BYTES
        or aggregate_before + expected_size > MAX_TOTAL_MARKDOWN_BYTES
    ):
        raise CloudIndexVerificationError("resource_limit_exceeded")
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
        raise CloudIndexVerificationError("filesystem_race")
    digest = hashlib.sha256()
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    total = 0
    try:
        while True:
            chunk = os.read(fd, _READ_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if (
                total > MAX_MARKDOWN_DOCUMENT_BYTES
                or aggregate_before + total > MAX_TOTAL_MARKDOWN_BYTES
            ):
                raise CloudIndexVerificationError("resource_limit_exceeded")
            digest.update(chunk)
            decoder.decode(chunk, final=False)
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        raise CloudIndexVerificationError("filesystem_unsafe") from None
    after = os.fstat(fd)
    if _signature(before) != _signature(after) or total != expected_size:
        raise CloudIndexVerificationError("filesystem_race")
    return total, "sha256:" + digest.hexdigest()


def _collect_source_files(root_fd: int) -> tuple[_MarkdownFile, ...]:
    """Descriptor-relative walk. Count every entry but read only Markdown bytes."""
    root_st = os.fstat(root_fd)
    if not stat.S_ISDIR(root_st.st_mode):
        raise CloudIndexVerificationError("filesystem_unsafe")
    stack: list[tuple[str, tuple[int, int]]] = [("", _identity(root_st))]
    documents: list[_MarkdownFile] = []
    entry_count = 0
    aggregate_markdown_bytes = 0

    while stack:
        relative_dir, expected_dir_identity = stack.pop()
        directory_fd = _open_directory_relative(
            root_fd, relative_dir, expected_identity=expected_dir_identity
        )
        try:
            directory_before = os.fstat(directory_fd)
            try:
                names = os.listdir(directory_fd)
                names.sort(key=lambda name: name.encode("utf-8", errors="strict"))
            except (OSError, UnicodeError):
                raise CloudIndexVerificationError("filesystem_unsafe") from None

            child_dirs: list[tuple[str, tuple[int, int]]] = []
            for name in names:
                entry_count += 1
                if entry_count > MAX_SOURCE_TREE_ENTRIES:
                    raise CloudIndexVerificationError("resource_limit_exceeded")
                if (
                    not name or name in {".", ".."}
                    or len(name.encode("utf-8", errors="strict")) > MAX_PATH_COMPONENT_BYTES
                ):
                    raise CloudIndexVerificationError("resource_limit_exceeded")
                relative = f"{relative_dir}/{name}" if relative_dir else name
                relative = _safe_path(relative)
                try:
                    before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except OSError:
                    raise CloudIndexVerificationError("filesystem_race") from None
                if stat.S_ISLNK(before.st_mode):
                    raise CloudIndexVerificationError("filesystem_unsafe")
                if stat.S_ISDIR(before.st_mode):
                    child_dirs.append((relative, _identity(before)))
                    continue
                if not stat.S_ISREG(before.st_mode):
                    raise CloudIndexVerificationError("filesystem_unsafe")

                if PurePosixPath(relative).suffix.lower() == ".md":
                    if len(documents) >= MAX_MARKDOWN_DOCUMENT_ROWS:
                        raise CloudIndexVerificationError("resource_limit_exceeded")
                    fd = _open_regular_at(directory_fd, name, before)
                    try:
                        size, digest = _hash_markdown_fd(
                            fd, before.st_size, aggregate_markdown_bytes
                        )
                    finally:
                        os.close(fd)
                    aggregate_markdown_bytes += size
                    try:
                        after_entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    except OSError:
                        raise CloudIndexVerificationError("filesystem_race") from None
                    if _signature(before) != _signature(after_entry):
                        raise CloudIndexVerificationError("filesystem_race")
                    documents.append(_MarkdownFile(relative, size, digest))
                else:
                    # Non-Markdown attachments count toward the entry budget but
                    # their payload bytes are never opened or read.
                    try:
                        after_entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    except OSError:
                        raise CloudIndexVerificationError("filesystem_race") from None
                    if _signature(before) != _signature(after_entry):
                        raise CloudIndexVerificationError("filesystem_race")

            directory_after = os.fstat(directory_fd)
            if _signature(directory_before) != _signature(directory_after):
                raise CloudIndexVerificationError("filesystem_race")
            stack.extend(reversed(child_dirs))
        except CloudIndexVerificationError:
            raise
        except (OSError, UnicodeError, ValueError):
            raise CloudIndexVerificationError("filesystem_unsafe") from None
        finally:
            os.close(directory_fd)

    documents.sort(key=lambda item: item.path.encode("utf-8", errors="strict"))
    return tuple(documents)


def _read_source_document(
    root_fd: int, relative_path: str, expected: _MarkdownFile
) -> tuple[bytes, str]:
    """Read one bounded Markdown file for source-span checks, then release it."""
    parts = relative_path.split("/")
    parent_fd = _open_directory_relative(root_fd, "/".join(parts[:-1]))
    name = parts[-1]
    try:
        try:
            before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError:
            raise CloudIndexVerificationError("filesystem_race") from None
        if not stat.S_ISREG(before.st_mode):
            raise CloudIndexVerificationError("filesystem_unsafe")
        if before.st_size > MAX_MARKDOWN_DOCUMENT_BYTES:
            raise CloudIndexVerificationError("resource_limit_exceeded")
        if before.st_size != expected.byte_size:
            raise CloudIndexVerificationError("inventory_mismatch")
        fd = _open_regular_at(parent_fd, name, before)
        try:
            opened = os.fstat(fd)
            raw_buffer = bytearray()
            digest = hashlib.sha256()
            while True:
                chunk = os.read(fd, _READ_CHUNK_BYTES)
                if not chunk:
                    break
                if len(raw_buffer) + len(chunk) > MAX_MARKDOWN_DOCUMENT_BYTES:
                    raise CloudIndexVerificationError("resource_limit_exceeded")
                raw_buffer.extend(chunk)
                digest.update(chunk)
            after = os.fstat(fd)
            if _signature(opened) != _signature(after) or len(raw_buffer) != after.st_size:
                raise CloudIndexVerificationError("filesystem_race")
        finally:
            os.close(fd)
        after_entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if _signature(before) != _signature(after_entry):
            raise CloudIndexVerificationError("filesystem_race")
        raw = bytes(raw_buffer)
        if "sha256:" + digest.hexdigest() != expected.sha256:
            raise CloudIndexVerificationError("inventory_mismatch")
        try:
            source_text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise CloudIndexVerificationError("filesystem_unsafe") from None
        return raw, source_text
    except CloudIndexVerificationError:
        raise
    except OSError:
        raise CloudIndexVerificationError("filesystem_race") from None
    finally:
        os.close(parent_fd)


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8", errors="strict")


def _expected_inventory(files: tuple[_MarkdownFile, ...]) -> bytes:
    documents = [
        {"path": item.path, "byte_size": item.byte_size, "sha256": item.sha256}
        for item in files
    ]
    documents.sort(key=lambda item: item["path"].encode("utf-8", errors="strict"))
    return _canonical_bytes({"format": INVENTORY_FORMAT, "documents": documents})


def _validate_inventory(raw: bytes, expected: bytes, att: CloudIndexAttestation) -> None:
    """Validate canonical inventory while applying the row cap as rows are decoded."""
    if type(raw) is not bytes:
        raise CloudIndexVerificationError("inventory_invalid")
    if len(raw) > MAX_INVENTORY_BYTES:
        raise CloudIndexVerificationError("resource_limit_exceeded")
    try:
        text = raw.decode("utf-8", errors="strict")
        prefix = '{"documents":['
        if not text.startswith(prefix):
            raise ValueError("inventory root is not canonical")
        decoder = json.JSONDecoder(
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("invalid JSON constant")),
        )
        cursor = len(prefix)
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        previous_path: bytes | None = None

        while True:
            if cursor >= len(text):
                raise ValueError("inventory array is unterminated")
            if text[cursor] == "]":
                cursor += 1
                break
            if rows:
                if text[cursor] != ",":
                    raise ValueError("inventory row separator is invalid")
                cursor += 1
            row, cursor = decoder.raw_decode(text, cursor)
            if len(rows) >= MAX_MARKDOWN_DOCUMENT_ROWS:
                raise CloudIndexVerificationError("resource_limit_exceeded")
            item = _exact(row, {"path", "byte_size", "sha256"})
            item_path = _safe_path(item["path"])
            if PurePosixPath(item_path).suffix.lower() != ".md" or item_path in seen:
                raise ValueError("invalid or duplicate inventory path")
            seen.add(item_path)
            encoded_path = item_path.encode("utf-8", errors="strict")
            if previous_path is not None and encoded_path <= previous_path:
                raise ValueError("inventory rows are not byte-sorted")
            previous_path = encoded_path
            _uint(item["byte_size"])
            if not isinstance(item["sha256"], str) or not _SHA256_RE.fullmatch(item["sha256"]):
                raise ValueError("invalid document digest")
            rows.append(item)

        format_prefix = ',"format":'
        if not text.startswith(format_prefix, cursor):
            raise ValueError("inventory format member is missing")
        cursor += len(format_prefix)
        format_value, cursor = decoder.raw_decode(text, cursor)
        if format_value != INVENTORY_FORMAT or text[cursor:] != "}":
            raise ValueError("inventory format or object terminator is invalid")

        parsed = {"documents": rows, "format": format_value}
        if _canonical_bytes(parsed) != raw:
            raise ValueError("inventory is not canonical JSON")
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        if digest != att.markdown_inventory_sha256 or len(rows) != att.markdown_document_count:
            raise CloudIndexVerificationError("inventory_mismatch")
        if raw != expected:
            raise CloudIndexVerificationError("inventory_mismatch")
    except CloudIndexVerificationError:
        raise
    except Exception:
        raise CloudIndexVerificationError("inventory_invalid") from None


def _database_bytes(path: str | Path) -> tuple[Path, str, int, tuple[int, int, int, int, int]]:
    requested = Path(path).expanduser()
    parent_fd: int | None = None
    try:
        if requested.is_symlink():
            raise CloudIndexVerificationError("database_invalid")
        canonical = requested.resolve(strict=True)
        parent_fd = _open_absolute_directory(canonical.parent)
        name = canonical.name
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise CloudIndexVerificationError("database_invalid")
        fd = _open_regular_at(parent_fd, name, before)
        try:
            opened = os.fstat(fd)
            digest = hashlib.sha256()
            total = 0
            while True:
                chunk = os.read(fd, _READ_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                digest.update(chunk)
            after = os.fstat(fd)
            if _signature(opened) != _signature(after) or total != after.st_size:
                raise CloudIndexVerificationError("database_invalid")
        finally:
            os.close(fd)
        after_entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if _signature(before) != _signature(after_entry):
            raise CloudIndexVerificationError("database_invalid")
        return canonical, "sha256:" + digest.hexdigest(), total, _signature(after_entry)
    except CloudIndexVerificationError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise CloudIndexVerificationError("database_invalid") from None
    finally:
        if parent_fd is not None:
            os.close(parent_fd)


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
        raise CloudIndexVerificationError("schema_mismatch") from None


def _validate_version_coordinates(row: dict[str, Any]) -> None:
    fields = (
        "line_start", "line_end", "char_start", "char_end", "byte_start", "byte_end"
    )
    values = [row.get(field) for field in fields]
    if any(type(value) is not int for value in values):
        raise CloudIndexVerificationError("node_span_mismatch")
    line_start, line_end, char_start, char_end, byte_start, byte_end = values
    raw_text = row.get("raw_text")
    if not isinstance(raw_text, str):
        raise CloudIndexVerificationError("node_version_mismatch")
    try:
        raw_bytes = raw_text.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise CloudIndexVerificationError("node_version_mismatch") from None
    if (
        line_start < 1 or line_end < 0
        or char_start < 0 or char_end < char_start
        or byte_start < 0 or byte_end < byte_start
        or char_end - char_start != len(raw_text)
        or byte_end - byte_start != len(raw_bytes)
    ):
        raise CloudIndexVerificationError("node_span_mismatch")
    if raw_text:
        expected_line_end = line_start + raw_text[:-1].count("\n")
        if line_end != expected_line_end:
            raise CloudIndexVerificationError("node_span_mismatch")
    elif line_end != line_start - 1 or char_end != char_start or byte_end != byte_start:
        raise CloudIndexVerificationError("node_span_mismatch")


def _validate_version_content_spans(row: dict[str, Any]) -> None:
    spans = _decode_json(
        row["content_spans_json"], list, "node_version_mismatch", "Invalid version data."
    )
    previous_char_end: int | None = None
    previous_byte_end: int | None = None
    previous_line_start: int | None = None
    for span in spans:
        if type(span) is not dict or set(span) != {
            "line_start", "line_end", "char_start", "char_end", "byte_start", "byte_end"
        }:
            raise CloudIndexVerificationError("node_span_mismatch")
        if any(type(span.get(field)) is not int for field in (
            "line_start", "line_end", "char_start", "char_end", "byte_start", "byte_end"
        )):
            raise CloudIndexVerificationError("node_span_mismatch")
        if (
            span["line_start"] < row["line_start"]
            or span["line_start"] < 1
            or span["line_end"] < span["line_start"] - 1
            or span["line_end"] > row["line_end"]
            or span["char_start"] < row["char_start"]
            or span["char_end"] < span["char_start"]
            or span["char_end"] > row["char_end"]
            or span["byte_start"] < row["byte_start"]
            or span["byte_end"] < span["byte_start"]
            or span["byte_end"] > row["byte_end"]
            or (
                previous_char_end is not None
                and span["char_start"] < previous_char_end
            )
            or (
                previous_byte_end is not None
                and span["byte_start"] < previous_byte_end
            )
            or (
                previous_line_start is not None
                and span["line_start"] < previous_line_start
            )
            or (
                span["char_start"] == span["char_end"]
                and span["byte_start"] != span["byte_end"]
            )
        ):
            raise CloudIndexVerificationError("node_span_mismatch")
        previous_char_end = span["char_end"]
        previous_byte_end = span["byte_end"]
        previous_line_start = span["line_start"]


def _validate_historical_node_versions(
    connection: sqlite3.Connection,
    documents: dict[int, dict[str, Any]],
    nodes: list[dict[str, Any]],
) -> None:
    node_by_pk = {node["node_pk"]: node for node in nodes}
    if len(node_by_pk) != len(nodes):
        raise CloudIndexVerificationError("node_reference_mismatch")
    node_by_identity: dict[tuple[int, str], dict[str, Any]] = {}
    for node in nodes:
        node_id = node.get("node_id")
        doc_pk = node.get("document_pk")
        if not _valid_node_id(node_id) or doc_pk not in documents:
            raise CloudIndexVerificationError("node_reference_mismatch")
        identity = (doc_pk, node_id)
        if identity in node_by_identity:
            raise CloudIndexVerificationError("node_reference_mismatch")
        node_by_identity[identity] = node

    rows = connection.execute(
        "SELECT node_pk, version_no, generation, content_hash, source_path, node_type, "
        "parent_node_id, heading_path_json, line_start, line_end, char_start, char_end, "
        "byte_start, byte_end, content_spans_json, raw_text, metadata_json, warnings_json "
        "FROM node_versions ORDER BY node_pk, version_no"
    ).fetchall()
    versions_by_node: dict[int, list[dict[str, Any]]] = {}
    for raw in rows:
        version = dict(raw)
        node_pk = version.get("node_pk")
        node = node_by_pk.get(node_pk)
        if node is None:
            raise CloudIndexVerificationError("node_reference_mismatch")
        doc_pk = node["document_pk"]
        doc = documents.get(doc_pk)
        if doc is None or version.get("source_path") != doc["source_path"]:
            raise CloudIndexVerificationError("node_reference_mismatch")
        if version.get("node_type") not in _ALLOWED_NODE_TYPES:
            raise CloudIndexVerificationError("node_version_mismatch")
        if (
            not _valid_hash(version.get("content_hash"))
            or not isinstance(version.get("raw_text"), str)
            or "sha256:" + hashlib.sha256(
                version["raw_text"].encode("utf-8", errors="strict")
            ).hexdigest() != version["content_hash"]
        ):
            raise CloudIndexVerificationError("node_content_mismatch")
        if type(version.get("version_no")) is not int or version["version_no"] < 1:
            raise CloudIndexVerificationError("node_version_mismatch")
        generation = version.get("generation")
        if (
            type(generation) is not int or generation < 1
            or generation > doc["generation"]
            or generation < node["created_generation"]
            or generation > node["updated_generation"]
        ):
            raise CloudIndexVerificationError("node_generation_mismatch")
        parent_id = version.get("parent_node_id")
        if parent_id is not None:
            if not _valid_node_id(parent_id) or parent_id == node["node_id"]:
                raise CloudIndexVerificationError("node_reference_mismatch")
            parent = node_by_identity.get((doc_pk, parent_id))
            if parent is None or parent["created_generation"] > generation:
                raise CloudIndexVerificationError("node_reference_mismatch")

        _validate_version_coordinates(version)
        _validate_version_content_spans(version)
        heading_path = _decode_json(
            version["heading_path_json"], list, "node_version_mismatch", "Invalid version data."
        )
        if any(not isinstance(item, str) for item in heading_path):
            raise CloudIndexVerificationError("node_version_mismatch")
        _decode_json(
            version["metadata_json"], dict, "node_version_mismatch", "Invalid version data."
        )
        warnings = _decode_json(
            version["warnings_json"], list, "node_version_mismatch", "Invalid version data."
        )
        if any(not isinstance(item, str) for item in warnings):
            raise CloudIndexVerificationError("node_version_mismatch")
        versions_by_node.setdefault(node_pk, []).append(version)

    for node_pk, node in node_by_pk.items():
        versions = versions_by_node.get(node_pk, [])
        if not versions:
            raise CloudIndexVerificationError("node_version_mismatch")
        numbers = [version["version_no"] for version in versions]
        generations = [version["generation"] for version in versions]
        if numbers != list(range(1, len(versions) + 1)):
            raise CloudIndexVerificationError("node_version_mismatch")
        if generations != sorted(generations):
            raise CloudIndexVerificationError("node_generation_mismatch")
        if generations[0] < node["created_generation"]:
            raise CloudIndexVerificationError("node_generation_mismatch")
        # A later document generation may legitimately leave this node unchanged;
        # the current/latest equality and upper bound are checked by _check_db_snapshot.


def _verify_database_consistency(
    db_path: Path,
    root_fd: int,
    source_files: tuple[_MarkdownFile, ...],
) -> tuple[tuple[int, int, int, int, int], tuple[ParserIdentity, ...]]:
    connection: sqlite3.Connection | None = None
    try:
        connection = _read_only_connection(db_path)
        if (
            not connection.in_transaction
            or connection.execute("PRAGMA query_only").fetchone()[0] != 1
        ):
            raise CloudIndexVerificationError("sqlite_integrity_failure")
        _verify_database(connection)
        _required_schema(connection)

        documents = [
            dict(row)
            for row in connection.execute("SELECT * FROM documents ORDER BY document_pk")
        ]
        nodes = [
            dict(row)
            for row in connection.execute("SELECT * FROM structural_nodes ORDER BY node_pk")
        ]
        doc_by_pk = {row["document_pk"]: row for row in documents}
        if len(doc_by_pk) != len(documents) or any(type(key) is not int for key in doc_by_pk):
            raise CloudIndexVerificationError("document_mismatch")

        inventory_by_path = {item.path: item for item in source_files}
        active_docs: dict[str, dict[str, Any]] = {}
        seen_document_paths: set[str] = set()
        parser_pairs: set[tuple[str, str]] = set()
        for doc in documents:
            source_path = _safe_path(doc.get("source_path"))
            if source_path in seen_document_paths:
                raise CloudIndexVerificationError("document_mismatch")
            seen_document_paths.add(source_path)
            if (
                not _valid_hash(doc.get("source_sha256"))
                or type(doc.get("source_size_bytes")) is not int
                or doc["source_size_bytes"] < 0
                or type(doc.get("generation")) is not int
                or doc["generation"] < 1
                or doc.get("status") not in {"active", "deleted"}
                or not isinstance(doc.get("parser_name"), str)
                or not doc["parser_name"]
                or not isinstance(doc.get("parser_version"), str)
                or not doc["parser_version"]
            ):
                raise CloudIndexVerificationError("document_mismatch")
            if doc["status"] == "active":
                if source_path in active_docs:
                    raise CloudIndexVerificationError("document_mismatch")
                active_docs[source_path] = doc
                parser_pairs.add((doc["parser_name"], doc["parser_version"]))

        if set(active_docs) != set(inventory_by_path):
            raise CloudIndexVerificationError("document_mismatch")
        for source_path, doc in active_docs.items():
            item = inventory_by_path[source_path]
            if doc["source_size_bytes"] != item.byte_size or doc["source_sha256"] != item.sha256:
                raise CloudIndexVerificationError("document_mismatch")

        nodes_by_doc: dict[int, list[dict[str, Any]]] = {}
        node_ids: set[str] = set()
        node_ids_by_doc: dict[int, set[str]] = {}
        node_pk_to_doc = {node["node_pk"]: node["document_pk"] for node in nodes}
        if len(node_pk_to_doc) != len(nodes):
            raise CloudIndexVerificationError("node_reference_mismatch")
        for node in nodes:
            doc = doc_by_pk.get(node.get("document_pk"))
            if doc is None:
                raise CloudIndexVerificationError("node_reference_mismatch")
            node_id = node.get("node_id")
            if not _valid_node_id(node_id) or node_id in node_ids:
                raise CloudIndexVerificationError("node_identity_mismatch")
            node_ids.add(node_id)
            node_ids_by_doc.setdefault(doc["document_pk"], set()).add(node_id)
            nodes_by_doc.setdefault(doc["document_pk"], []).append(node)

        # Run the complete historical type/link/span/generation preflight before
        # _check_db_snapshot's narrower legacy status checks can coarsen errors.
        _validate_historical_node_versions(connection, doc_by_pk, nodes)

        active_node_count = 0
        for doc_pk, doc in doc_by_pk.items():
            events = _validate_events(connection, doc_pk, doc["generation"])
            document_node_ids = node_ids_by_doc.get(doc_pk, set())
            for event in events:
                if event["node_id"] not in document_node_ids or any(
                    candidate not in document_node_ids for candidate in event["candidate_node_ids"]
                ):
                    raise CloudIndexVerificationError("node_reference_mismatch")

            source_bytes: bytes | None = None
            source_text: str | None = None
            if doc["status"] == "active":
                item = inventory_by_path[doc["source_path"]]
                source_bytes, source_text = _read_source_document(root_fd, doc["source_path"], item)
                verified_text = _verify_document_bytes(doc, source_bytes)
                if verified_text != source_text:
                    raise CloudIndexVerificationError("document_mismatch")

            for node in nodes_by_doc.get(doc_pk, []):
                heading_path, parent_id, latest_event = _check_db_snapshot(
                    connection, node, doc, events
                )
                status = _resolve_db_status(node, doc, latest_event)
                if node["status"] in {"active", "ambiguous"} and node.get("stale_generation") is None:
                    if doc["status"] != "active" or source_bytes is None or source_text is None:
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
                        source_bytes=source_bytes,
                        source_text=source_text,
                        expected_hash=node["content_hash"],
                    )
                elif status is None:
                    raise CloudIndexVerificationError("node_integrity_failure")
            source_bytes = None
            source_text = None

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
                parser_pairs,
                key=lambda pair: (pair[0].encode("utf-8"), pair[1].encode("utf-8")),
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
            "node_id_not_unique": "node_identity_mismatch",
            "node_identity_invalid": "node_identity_mismatch",
            "node_document_reference_invalid": "node_reference_mismatch",
            "cross_document_relation": "node_reference_mismatch",
            "parent_generation_mismatch": "node_reference_mismatch",
            "parent_reference_invalid": "node_reference_mismatch",
            "sibling_document_binding_mismatch": "node_reference_mismatch",
            "raw_text_hash_mismatch": "node_content_mismatch",
            "source_fragment_hash_mismatch": "node_content_mismatch",
            "version_content_hash_mismatch": "node_content_mismatch",
            "source_coordinates_invalid": "node_span_mismatch",
            "char_span_mismatch": "node_span_mismatch",
            "byte_span_mismatch": "node_span_mismatch",
            "line_span_mismatch": "node_span_mismatch",
            "document_generation_invalid": "node_generation_mismatch",
            "node_match_event_generation_mismatch": "node_generation_mismatch",
            "stale_event_generation_mismatch": "node_generation_mismatch",
            "stale_generation_invalid": "node_generation_mismatch",
            "version_generation_mismatch": "node_generation_mismatch",
            "match_event_type_unknown": "node_history_mismatch",
            "match_event_payload_invalid": "node_history_mismatch",
            "match_event_read_failed": "node_history_mismatch",
            "node_match_event_missing": "node_history_mismatch",
            "ambiguous_event_missing": "node_history_mismatch",
            "stale_event_missing": "node_history_mismatch",
            "node_event_state_mismatch": "node_history_mismatch",
            "active_state_mismatch": "node_history_mismatch",
            "deleted_document_state_invalid": "node_history_mismatch",
            "version_history_invalid": "node_version_mismatch",
            "version_history_read_failed": "node_version_mismatch",
            "version_snapshot_mismatch": "node_version_mismatch",
            "version_snapshot_missing": "node_version_mismatch",
            "source_hash_invalid": "document_mismatch",
            "source_size_invalid": "document_mismatch",
            "source_hash_mismatch": "document_mismatch",
            "source_size_mismatch": "document_mismatch",
            "source_encoding_invalid": "document_mismatch",
            "source_file_missing": "inventory_mismatch",
            "source_path_unsafe": "filesystem_unsafe",
            "source_open_failed": "filesystem_unsafe",
            "source_target_outside_root": "filesystem_unsafe",
            "vault_root_open_failed": "filesystem_unsafe",
            "secure_open_unavailable": "filesystem_unsafe",
            "file_identity_changed": "filesystem_race",
            "read_transaction_missing": "sqlite_integrity_failure",
            "node_lookup_failed": "sqlite_integrity_failure",
        }.get(exc.code, "node_integrity_failure")
        raise CloudIndexVerificationError(code) from None
    except sqlite3.Error:
        raise CloudIndexVerificationError("sqlite_integrity_failure") from None
    except (OSError, UnicodeError, ValueError, TypeError, KeyError):
        raise CloudIndexVerificationError("node_integrity_failure") from None
    finally:
        if connection is not None:
            connection.close()


def _installed_indexer_version() -> str:
    try:
        return importlib.metadata.version("sfra-structural-indexer")
    except importlib.metadata.PackageNotFoundError as exc:
        raise CloudIndexVerificationError("indexer_identity_mismatch") from None


def _expected_source_revision(value: Any) -> SourceRevision:
    """Accept only E1-owned tagged types or the exact primitive tagged mapping."""
    try:
        if type(value) in (GitCommitSourceRevision, ImmutableImportSourceRevision):
            canonical = _revision(value.to_dict())
            if type(canonical) is not type(value) or canonical != value:
                raise ValueError("revision does not round-trip exactly")
            return canonical
        if type(value) is dict:
            return _revision(value)
    except Exception:
        raise CloudIndexVerificationError("source_revision_invalid") from None
    raise CloudIndexVerificationError("source_revision_invalid")


def verify_materialized_cloud_index(
    database_path: str | Path,
    source_root: str | Path,
    *,
    attestation: bytes,
    markdown_inventory: bytes,
    expected_source_revision: SourceRevision | dict[str, str],
) -> CloudIndexVerificationReport:
    """Verify materialized source/SQLite bytes against an outer verified revision.

    expected_source_revision is an E1-owned tagged type or strict primitive
    mapping passed from the outer immutable snapshot reference. This verifier
    never imports E3 types or accesses object storage.
    """
    parsed = parse_cloud_index_attestation(attestation)
    expected_revision = _expected_source_revision(expected_source_revision)
    if type(parsed.source_revision) is not type(expected_revision) or parsed.source_revision != expected_revision:
        raise CloudIndexVerificationError("source_revision_mismatch")

    try:
        if (
            parsed.indexer_identity.name != "sfra-structural-indexer"
            or parsed.indexer_identity.version != _installed_indexer_version()
        ):
            raise CloudIndexVerificationError("indexer_identity_mismatch")
        if type(markdown_inventory) is not bytes:
            raise CloudIndexVerificationError("inventory_invalid")
        if len(markdown_inventory) > MAX_INVENTORY_BYTES:
            raise CloudIndexVerificationError("resource_limit_exceeded")

        with _pin_source_root(source_root) as root_fd:
            source_files = _collect_source_files(root_fd)
            _validate_inventory(markdown_inventory, _expected_inventory(source_files), parsed)

            db_path, actual_digest, database_size, database_signature = _database_bytes(database_path)
            if actual_digest != parsed.database_sha256:
                raise CloudIndexVerificationError("database_digest_mismatch")
            if database_size != parsed.database_byte_size:
                raise CloudIndexVerificationError("database_size_mismatch")

            counts, parsers = _verify_database_consistency(db_path, root_fd, source_files)
            after = db_path.stat()
            if _signature(after) != database_signature:
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

            final_source_files = _collect_source_files(root_fd)
            if final_source_files != source_files:
                raise CloudIndexVerificationError("filesystem_race")

            return CloudIndexVerificationReport(
                source_revision=parsed.source_revision,
                database_sha256=actual_digest,
                database_byte_size=database_size,
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
    except _LookupFailure:
        raise CloudIndexVerificationError("node_integrity_failure") from None
    except Exception:
        raise CloudIndexVerificationError("verification_failed") from None


__all__ = [
    "ATTESTATION_FORMAT", "INVENTORY_FORMAT", "CloudIndexAttestation",
    "CloudIndexVerificationError", "CloudIndexVerificationReport",
    "GitCommitSourceRevision", "ImmutableImportSourceRevision", "SourceRevision", "IndexerIdentity",
    "ParserIdentity", "parse_cloud_index_attestation", "verify_materialized_cloud_index",
]
