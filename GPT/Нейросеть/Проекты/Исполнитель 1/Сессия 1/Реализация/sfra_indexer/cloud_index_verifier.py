"""Additive read-only verifier for materialized E1 cloud-index snapshots."""
from __future__ import annotations

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
from typing import Any

from .lookup import (
    _LookupFailure, _check_db_snapshot, _decode_json,
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
MAX_ATTESTATION_BYTES = 2 * 1024 * 1024
MAX_INVENTORY_BYTES = 64 * 1024 * 1024
MAX_MARKDOWN_DOCUMENTS = 100_000
MAX_PARSER_IDENTITIES = 256
MAX_SOURCE_TREE_ENTRIES = 500_000
MAX_MARKDOWN_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_AGGREGATE_MARKDOWN_BYTES = 2 * 1024 * 1024 * 1024
MAX_RELATIVE_PATH_CHARS = 4096
_READ_CHUNK_BYTES = 1024 * 1024
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
        "resource_limit_exceeded": "The materialized snapshot exceeds the E1 verifier resource envelope.",
        "source_revision_mismatch": "The E1 attestation source revision differs from the expected outer revision.",
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


class _ResourceLimitExceeded(ValueError):
    """Internal signal for one of the coordinator-approved resource ceilings."""


def _limited_top_level_object(
    text: str,
    *,
    limited_arrays: dict[str, int],
) -> dict[str, Any]:
    """Decode one canonical object, stopping top-level bounded arrays at limit + 1."""
    decoder = json.JSONDecoder(
        object_pairs_hook=_reject_duplicate_pairs,
        parse_constant=lambda _v: (_ for _ in ()).throw(ValueError("invalid JSON constant")),
    )
    index = 0
    length = len(text)

    def skip_space(position: int) -> int:
        while position < length and text[position] in " \t\r\n":
            position += 1
        return position

    index = skip_space(index)
    if index >= length or text[index] != "{":
        raise ValueError("JSON root must be an object")
    index += 1
    result: dict[str, Any] = {}
    index = skip_space(index)
    if index < length and text[index] == "}":
        index += 1
    else:
        while True:
            index = skip_space(index)
            key, index = decoder.raw_decode(text, index)
            if not isinstance(key, str) or key in result:
                raise ValueError("invalid or duplicate JSON key")
            index = skip_space(index)
            if index >= length or text[index] != ":":
                raise ValueError("missing JSON object separator")
            index = skip_space(index + 1)
            if key in limited_arrays and index < length and text[index] == "[":
                value: list[Any] = []
                index += 1
                index = skip_space(index)
                if index < length and text[index] == "]":
                    index += 1
                else:
                    while True:
                        item, index = decoder.raw_decode(text, index)
                        value.append(item)
                        if len(value) > limited_arrays[key]:
                            raise _ResourceLimitExceeded()
                        index = skip_space(index)
                        if index < length and text[index] == ",":
                            index = skip_space(index + 1)
                            continue
                        if index < length and text[index] == "]":
                            index += 1
                            break
                        raise ValueError("invalid JSON array separator")
            else:
                value, index = decoder.raw_decode(text, index)
            result[key] = value
            index = skip_space(index)
            if index < length and text[index] == ",":
                index += 1
                continue
            if index < length and text[index] == "}":
                index += 1
                break
            raise ValueError("invalid JSON object separator")
    if skip_space(index) != length:
        raise ValueError("trailing JSON data")
    return result


def _canonical_object(
    raw: bytes,
    *,
    max_bytes: int,
    limited_arrays: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Parse bounded canonical UTF-8 JSON without materializing oversized arrays."""
    if not isinstance(raw, bytes):
        raise ValueError("payload must be bytes")
    if len(raw) > max_bytes:
        raise _ResourceLimitExceeded()
    text = raw.decode("utf-8", errors="strict")
    value = _limited_top_level_object(text, limited_arrays=limited_arrays or {})
    canonical = json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8", errors="strict")
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
        obj = _exact(_canonical_object(
            raw,
            max_bytes=MAX_ATTESTATION_BYTES,
            limited_arrays={"parser_identities": MAX_PARSER_IDENTITIES},
        ), {
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
    except _ResourceLimitExceeded:
        raise CloudIndexVerificationError("resource_limit_exceeded") from None
    except Exception as exc:
        raise CloudIndexVerificationError("attestation_invalid") from None


def _safe_path(value: Any) -> str:
    # Match #119's canonical relative-POSIX path contract exactly. Do not add
    # normalization or whitespace restrictions that its producer does not use.
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value or "\x00" in value:
        raise ValueError("unsafe path")
    value.encode("utf-8", errors="strict")
    if len(value) > MAX_RELATIVE_PATH_CHARS:
        raise _ResourceLimitExceeded()
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts) or PurePosixPath(value).is_absolute():
        raise ValueError("unsafe path")
    return value


def _stat_signature(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev, value.st_ino, value.st_mode, value.st_size,
        value.st_mtime_ns, value.st_ctime_ns,
    )


def _open_source_root(source_root: str | Path) -> tuple[Path, int]:
    requested = Path(source_root).expanduser()
    try:
        requested_stat = requested.lstat()
        if stat.S_ISLNK(requested_stat.st_mode) or not stat.S_ISDIR(requested_stat.st_mode):
            raise CloudIndexVerificationError("filesystem_unsafe")
        root = requested.resolve(strict=True)
        before = root.lstat()
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(root, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            os.close(descriptor)
            raise CloudIndexVerificationError("filesystem_race")
        return root, descriptor
    except CloudIndexVerificationError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise CloudIndexVerificationError("filesystem_unsafe") from None


def _open_child_directory(
    parent_fd: int,
    name: str,
    before: os.stat_result,
) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError:
        # The entry was observed as a directory but could not be pinned without
        # following a link or accepting a replaced directory component.
        raise CloudIndexVerificationError("filesystem_race") from None
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        os.close(descriptor)
        raise CloudIndexVerificationError("filesystem_race")
    return descriptor


def _read_markdown_at(
    parent_fd: int,
    name: str,
    before: os.stat_result,
    *,
    retain_bytes: bool,
) -> tuple[int, str, bytes | None]:
    if not stat.S_ISREG(before.st_mode):
        raise CloudIndexVerificationError("filesystem_unsafe")
    if before.st_size > MAX_MARKDOWN_DOCUMENT_BYTES:
        raise CloudIndexVerificationError("resource_limit_exceeded")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError:
        raise CloudIndexVerificationError("filesystem_race") from None
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            or _stat_signature(before) != _stat_signature(opened)
        ):
            raise CloudIndexVerificationError("filesystem_race")

        digest = hashlib.sha256()
        decoder = codecs.getincrementaldecoder("utf-8")("strict")
        chunks: list[bytes] | None = [] if retain_bytes else None
        total = 0
        while True:
            chunk = os.read(descriptor, _READ_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_MARKDOWN_DOCUMENT_BYTES:
                raise CloudIndexVerificationError("resource_limit_exceeded")
            decoder.decode(chunk, final=False)
            digest.update(chunk)
            if chunks is not None:
                chunks.append(chunk)
        decoder.decode(b"", final=True)
        after = os.fstat(descriptor)
        try:
            path_after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError:
            raise CloudIndexVerificationError("filesystem_race") from None
        if (
            _stat_signature(opened) != _stat_signature(after)
            or _stat_signature(after) != _stat_signature(path_after)
            or total != after.st_size
        ):
            raise CloudIndexVerificationError("filesystem_race")
        raw = b"".join(chunks) if chunks is not None else None
        return total, "sha256:" + digest.hexdigest(), raw
    except UnicodeDecodeError:
        raise CloudIndexVerificationError("filesystem_unsafe") from None
    finally:
        os.close(descriptor)


def _scan_source_inventory(root_fd: int) -> tuple[list[dict[str, Any]], int]:
    """Descriptor-relative tree walk; non-Markdown payload bytes are never read."""
    documents: list[dict[str, Any]] = []
    total_entries = 0
    aggregate_markdown_bytes = 0

    def walk(directory_fd: int, prefix: str) -> None:
        nonlocal total_entries, aggregate_markdown_bytes
        try:
            names = os.listdir(directory_fd)
            names.sort(key=lambda item: item.encode("utf-8", errors="strict"))
        except (OSError, UnicodeError):
            raise CloudIndexVerificationError("filesystem_unsafe") from None

        for name in names:
            try:
                relative = f"{prefix}/{name}" if prefix else name
                relative = _safe_path(relative)
                total_entries += 1
                if total_entries > MAX_SOURCE_TREE_ENTRIES:
                    raise CloudIndexVerificationError("resource_limit_exceeded")
                before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if stat.S_ISLNK(before.st_mode):
                    raise CloudIndexVerificationError("filesystem_unsafe")
                if stat.S_ISDIR(before.st_mode):
                    child_fd = _open_child_directory(directory_fd, name, before)
                    try:
                        walk(child_fd, relative)
                    finally:
                        os.close(child_fd)
                elif stat.S_ISREG(before.st_mode):
                    if PurePosixPath(relative).suffix.lower() != ".md":
                        # Count and type-check attachments, but deliberately do
                        # not open, hash, decode, or retain their payload bytes.
                        continue
                    if len(documents) >= MAX_MARKDOWN_DOCUMENTS:
                        raise CloudIndexVerificationError("resource_limit_exceeded")
                    if before.st_size > MAX_MARKDOWN_DOCUMENT_BYTES:
                        raise CloudIndexVerificationError("resource_limit_exceeded")
                    aggregate_markdown_bytes += before.st_size
                    if aggregate_markdown_bytes > MAX_AGGREGATE_MARKDOWN_BYTES:
                        raise CloudIndexVerificationError("resource_limit_exceeded")
                    size, digest, _ = _read_markdown_at(
                        directory_fd, name, before, retain_bytes=False
                    )
                    if size != before.st_size:
                        raise CloudIndexVerificationError("filesystem_race")
                    documents.append({
                        "path": relative,
                        "byte_size": size,
                        "sha256": digest,
                    })
                else:
                    raise CloudIndexVerificationError("filesystem_unsafe")
            except CloudIndexVerificationError:
                raise
            except _ResourceLimitExceeded:
                raise CloudIndexVerificationError("resource_limit_exceeded") from None
            except (OSError, UnicodeError, ValueError, TypeError):
                raise CloudIndexVerificationError("filesystem_unsafe") from None

    walk(root_fd, "")
    documents.sort(key=lambda item: item["path"].encode("utf-8", errors="strict"))
    return documents, total_entries


def _read_markdown_beneath(root_fd: int, relative_path: str) -> bytes:
    """Open one Markdown file below the pinned root without following components."""
    components = _safe_path(relative_path).split("/")
    current_fd = os.dup(root_fd)
    try:
        for component in components[:-1]:
            try:
                before = os.stat(component, dir_fd=current_fd, follow_symlinks=False)
            except OSError:
                raise CloudIndexVerificationError("filesystem_race") from None
            if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
                raise CloudIndexVerificationError("filesystem_unsafe")
            child_fd = _open_child_directory(current_fd, component, before)
            os.close(current_fd)
            current_fd = child_fd
        try:
            before = os.stat(components[-1], dir_fd=current_fd, follow_symlinks=False)
        except OSError:
            raise CloudIndexVerificationError("filesystem_race") from None
        size, _digest, raw = _read_markdown_at(
            current_fd, components[-1], before, retain_bytes=True
        )
        if raw is None or len(raw) != size:
            raise CloudIndexVerificationError("filesystem_race")
        return raw
    except CloudIndexVerificationError:
        raise
    except _ResourceLimitExceeded:
        raise CloudIndexVerificationError("resource_limit_exceeded") from None
    except (OSError, UnicodeError, ValueError, TypeError):
        raise CloudIndexVerificationError("filesystem_unsafe") from None
    finally:
        os.close(current_fd)


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8", errors="strict")


def _expected_inventory(documents: list[dict[str, Any]]) -> bytes:
    return _canonical_bytes({"format": INVENTORY_FORMAT, "documents": documents})


def _validate_inventory(
    raw: bytes,
    expected_documents: list[dict[str, Any]],
    att: CloudIndexAttestation,
) -> None:
    try:
        obj = _exact(_canonical_object(
            raw,
            max_bytes=MAX_INVENTORY_BYTES,
            limited_arrays={"documents": MAX_MARKDOWN_DOCUMENTS},
        ), {"format", "documents"})
        if obj["format"] != INVENTORY_FORMAT or not isinstance(obj["documents"], list):
            raise ValueError("unsupported inventory")
        seen: set[str] = set()
        previous: bytes | None = None
        aggregate_bytes = 0
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
            byte_size = _uint(item["byte_size"])
            if byte_size > MAX_MARKDOWN_DOCUMENT_BYTES:
                raise CloudIndexVerificationError("resource_limit_exceeded")
            aggregate_bytes += byte_size
            if aggregate_bytes > MAX_AGGREGATE_MARKDOWN_BYTES:
                raise CloudIndexVerificationError("resource_limit_exceeded")
            if not isinstance(item["sha256"], str) or not _SHA256_RE.fullmatch(item["sha256"]):
                raise ValueError("invalid file digest")
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        if digest != att.markdown_inventory_sha256 or len(obj["documents"]) != att.markdown_document_count:
            raise CloudIndexVerificationError("inventory_mismatch")
        if obj["documents"] != expected_documents:
            raise CloudIndexVerificationError("inventory_mismatch")
    except CloudIndexVerificationError:
        raise
    except _ResourceLimitExceeded:
        raise CloudIndexVerificationError("resource_limit_exceeded") from None
    except Exception as exc:
        raise CloudIndexVerificationError("inventory_invalid") from None


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
        raise CloudIndexVerificationError("database_invalid") from None


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
        seen_document_paths: set[str] = set()
        parser_pairs: set[tuple[str, str]] = set()
        for doc in documents:
            path = _safe_path(doc.get("source_path"))
            if path in seen_document_paths:
                raise CloudIndexVerificationError("document_mismatch")
            seen_document_paths.add(path)
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
            if doc_pk is None or row["source_path"] != doc_by_pk[doc_pk]["source_path"]:
                raise CloudIndexVerificationError("node_reference_mismatch")
            if (not _valid_hash(row["content_hash"]) or not isinstance(row["raw_text"], str)
                    or "sha256:" + hashlib.sha256(row["raw_text"].encode("utf-8", errors="strict")).hexdigest()
                    != row["content_hash"]):
                raise CloudIndexVerificationError("node_version_mismatch")
            _decode_json(row["heading_path_json"], list, "node_version_mismatch", "Invalid version data.")
            _decode_json(row["content_spans_json"], list, "node_version_mismatch", "Invalid version data.")
            _decode_json(row["metadata_json"], dict, "node_version_mismatch", "Invalid version data.")
            _decode_json(row["warnings_json"], list, "node_version_mismatch", "Invalid version data.")

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
    except sqlite3.Error as exc:
        raise CloudIndexVerificationError("sqlite_integrity_failure") from None
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        raise CloudIndexVerificationError("node_integrity_failure") from None
    finally:
        if connection is not None:
            connection.close()


def _installed_indexer_version() -> str:
    try:
        return importlib.metadata.version("sfra-structural-indexer")
    except importlib.metadata.PackageNotFoundError as exc:
        raise CloudIndexVerificationError("indexer_identity_mismatch") from None


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
        try:
            root = root.resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            raise CloudIndexVerificationError("filesystem_unsafe") from None
        if not root.is_dir():
            raise CloudIndexVerificationError("filesystem_unsafe")
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
        raise CloudIndexVerificationError("node_integrity_failure") from None
    except Exception as exc:
        raise CloudIndexVerificationError("verification_failed") from None


__all__ = [
    "ATTESTATION_FORMAT", "INVENTORY_FORMAT", "CloudIndexAttestation",
    "CloudIndexVerificationError", "CloudIndexVerificationReport",
    "GitCommitSourceRevision", "ImmutableImportSourceRevision", "SourceRevision", "IndexerIdentity",
    "ParserIdentity", "parse_cloud_index_attestation", "verify_materialized_cloud_index",
]
