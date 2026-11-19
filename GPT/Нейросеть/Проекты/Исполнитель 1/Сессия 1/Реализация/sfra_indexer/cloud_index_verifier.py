"""Additive read-only verifier for materialized E1 cloud-index snapshots."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import codecs
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
    _open_beneath, _open_canonical_root, _read_only_connection,
    _resolve_db_status, _safe_source_components, _stat_signature,
    _validate_events, _verify_database, _verify_document_bytes,
    _verify_node_from_source, _valid_hash, _valid_node_id,
)

ATTESTATION_FORMAT = "sfra.e1.cloud-index-attestation.v1"
INVENTORY_FORMAT = "sfra.e1.markdown-inventory.v1"
SUPPORTED_SCHEMA_VERSION = 2
DATABASE_PATH = "state/structure.sqlite3"
INVENTORY_PATH = "markdown-inventory.json"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_GIT_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_MUTABLE_IMPORT_ALIASES = frozenset({"latest", "current", "head", "*"})
MAX_ATTESTATION_BYTES = 2 * 1024 * 1024
MAX_INVENTORY_BYTES = 64 * 1024 * 1024
MAX_MARKDOWN_DOCUMENTS = 100_000
MAX_PARSER_IDENTITIES = 256
MAX_SOURCE_TREE_ENTRIES = 500_000
MAX_MARKDOWN_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_TOTAL_MARKDOWN_BYTES = 2 * 1024 * 1024 * 1024
MAX_SOURCE_PATH_CHARS = 4096
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
        "source_revision_mismatch": "The attested source revision does not match the outer verified source revision.",
        "resource_limit_exceeded": "The materialized snapshot exceeds the approved E1 verifier resource limits.",
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


def _canonical_object(
    raw: bytes,
    *,
    max_bytes: int,
    bounded_arrays: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Parse canonical JSON and stop at the first item beyond bounded arrays.

    The coordinator-approved parser/document counts are enforced while the
    array is decoded, not after json.loads has allocated the complete list.
    Other JSON values continue through the standard duplicate-key-aware
    decoder. Re-serialization is used only for canonical-byte comparison.
    """
    if type(raw) is not bytes:
        raise ValueError("payload must be bytes")
    if len(raw) > max_bytes:
        raise CloudIndexVerificationError("resource_limit_exceeded")

    decoder = json.JSONDecoder(
        object_pairs_hook=_reject_duplicate_pairs,
        parse_constant=lambda _v: (_ for _ in ()).throw(ValueError("invalid JSON constant")),
    )
    text = raw.decode("utf-8", errors="strict")
    array_limits = bounded_arrays or {}
    result: dict[str, Any] = {}
    position = 0
    length = len(text)

    def skip_space(index: int) -> int:
        while index < length and text[index] in " \\t\\r\\n":
            index += 1
        return index

    position = skip_space(position)
    if position >= length or text[position] != "{":
        raise ValueError("JSON root must be an object")
    position += 1
    position = skip_space(position)

    if position < length and text[position] == "}":
        position += 1
    else:
        while True:
            position = skip_space(position)
            key, position = decoder.raw_decode(text, position)
            if not isinstance(key, str) or key in result:
                raise ValueError("invalid or duplicate JSON object key")
            position = skip_space(position)
            if position >= length or text[position] != ":":
                raise ValueError("invalid JSON object separator")
            position = skip_space(position + 1)

            if key in array_limits and position < length and text[position] == "[":
                limit = array_limits[key]
                if type(limit) is not int or limit < 0:
                    raise ValueError("invalid bounded JSON array limit")
                items: list[Any] = []
                position = skip_space(position + 1)
                if position < length and text[position] == "]":
                    position += 1
                else:
                    while True:
                        item, position = decoder.raw_decode(text, position)
                        items.append(item)
                        if len(items) > limit:
                            raise CloudIndexVerificationError("resource_limit_exceeded")
                        position = skip_space(position)
                        if position < length and text[position] == ",":
                            position = skip_space(position + 1)
                            continue
                        if position < length and text[position] == "]":
                            position += 1
                            break
                        raise ValueError("invalid JSON array separator")
                value: Any = items
            else:
                value, position = decoder.raw_decode(text, position)

            result[key] = value
            position = skip_space(position)
            if position < length and text[position] == ",":
                position = skip_space(position + 1)
                continue
            if position < length and text[position] == "}":
                position += 1
                break
            raise ValueError("invalid JSON object separator")

    if skip_space(position) != length:
        raise ValueError("trailing JSON data")
    canonical = json.dumps(
        result, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8", errors="strict")
    if canonical != raw:
        raise ValueError("JSON is not canonical")
    return result


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
        obj = _exact(_canonical_object(raw, max_bytes=MAX_ATTESTATION_BYTES, bounded_arrays={"parser_identities": MAX_PARSER_IDENTITIES}), {
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
        if inventory_count > MAX_MARKDOWN_DOCUMENTS:
            raise CloudIndexVerificationError("resource_limit_exceeded")

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
    # Match #119's canonical relative-POSIX path contract exactly. Do not add
    # normalization or whitespace restrictions that its producer does not use.
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value or "\x00" in value:
        raise ValueError("unsafe path")
    if len(value) > MAX_SOURCE_PATH_CHARS:
        raise CloudIndexVerificationError("resource_limit_exceeded")
    value.encode("utf-8", errors="strict")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts) or PurePosixPath(value).is_absolute():
        raise ValueError("unsafe path")
    return value


def _assert_fd_beneath(fd: int, root: Path) -> None:
    """Fail closed unless the open descriptor still resolves beneath the pinned root."""
    proc_root = Path("/proc/self/fd")
    if not proc_root.is_dir():
        raise CloudIndexVerificationError("filesystem_unsafe")
    try:
        target_text = os.readlink(proc_root / str(fd))
        if target_text.endswith(" (deleted)"):
            raise CloudIndexVerificationError("filesystem_race")
        target = Path(target_text).resolve(strict=True)
        target.relative_to(root)
    except CloudIndexVerificationError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise CloudIndexVerificationError("filesystem_race") from None


def _read_markdown_digest(
    root_fd: int,
    root: Path,
    components: tuple[str, ...],
    expected_stat: os.stat_result,
) -> tuple[int, str]:
    """Hash one Markdown file beneath the pinned root without retaining its payload."""
    try:
        descriptor = _open_beneath(root_fd, components)
    except Exception:
        raise CloudIndexVerificationError("filesystem_race") from None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise CloudIndexVerificationError("filesystem_unsafe")
        if (before.st_dev, before.st_ino) != (expected_stat.st_dev, expected_stat.st_ino):
            raise CloudIndexVerificationError("filesystem_race")
        if before.st_size > MAX_MARKDOWN_DOCUMENT_BYTES:
            raise CloudIndexVerificationError("resource_limit_exceeded")
        _assert_fd_beneath(descriptor, root)
        digest = hashlib.sha256()
        decoder = codecs.getincrementaldecoder("utf-8")("strict")
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_MARKDOWN_DOCUMENT_BYTES:
                raise CloudIndexVerificationError("resource_limit_exceeded")
            try:
                decoder.decode(chunk, final=False)
            except UnicodeDecodeError:
                raise CloudIndexVerificationError("filesystem_unsafe") from None
            digest.update(chunk)
        try:
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            raise CloudIndexVerificationError("filesystem_unsafe") from None
        after = os.fstat(descriptor)
        if _stat_signature(before) != _stat_signature(after) or total != after.st_size:
            raise CloudIndexVerificationError("filesystem_race")
        _assert_fd_beneath(descriptor, root)
        try:
            verify_fd = _open_beneath(root_fd, components)
        except Exception:
            raise CloudIndexVerificationError("filesystem_race") from None
        try:
            verified = os.fstat(verify_fd)
            if (verified.st_dev, verified.st_ino) != (after.st_dev, after.st_ino):
                raise CloudIndexVerificationError("filesystem_race")
            _assert_fd_beneath(verify_fd, root)
        finally:
            os.close(verify_fd)
        return total, "sha256:" + digest.hexdigest()
    except CloudIndexVerificationError:
        raise
    except OSError:
        raise CloudIndexVerificationError("filesystem_race") from None
    finally:
        os.close(descriptor)


def _read_markdown_bytes(
    root_fd: int,
    root: Path,
    components: tuple[str, ...],
    expected_size: int,
    expected_digest: str,
) -> bytes:
    """Read one bounded Markdown file securely for source-coordinate verification."""
    if type(expected_size) is not int or expected_size < 0 or expected_size > MAX_MARKDOWN_DOCUMENT_BYTES:
        raise CloudIndexVerificationError("resource_limit_exceeded")
    try:
        descriptor = _open_beneath(root_fd, components)
    except Exception:
        raise CloudIndexVerificationError("filesystem_race") from None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
            raise CloudIndexVerificationError("filesystem_race")
        _assert_fd_beneath(descriptor, root)
        chunks: list[bytes] = []
        total = 0
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_MARKDOWN_DOCUMENT_BYTES:
                raise CloudIndexVerificationError("resource_limit_exceeded")
            chunks.append(chunk)
            digest.update(chunk)
        after = os.fstat(descriptor)
        if _stat_signature(before) != _stat_signature(after) or total != after.st_size:
            raise CloudIndexVerificationError("filesystem_race")
        if total != expected_size or "sha256:" + digest.hexdigest() != expected_digest:
            raise CloudIndexVerificationError("inventory_mismatch")
        _assert_fd_beneath(descriptor, root)
        try:
            verify_fd = _open_beneath(root_fd, components)
        except Exception:
            raise CloudIndexVerificationError("filesystem_race") from None
        try:
            verified = os.fstat(verify_fd)
            if (verified.st_dev, verified.st_ino) != (after.st_dev, after.st_ino):
                raise CloudIndexVerificationError("filesystem_race")
            _assert_fd_beneath(verify_fd, root)
        finally:
            os.close(verify_fd)
        return b"".join(chunks)
    except CloudIndexVerificationError:
        raise
    except OSError:
        raise CloudIndexVerificationError("filesystem_race") from None
    finally:
        os.close(descriptor)


def _open_directory_at(directory_fd: int, name: str) -> int:
    """Open one child directory relative to a pinned parent without following links."""
    flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    )
    return os.open(name, flags, dir_fd=directory_fd)


def _collect_source_files(source_root: str | Path) -> tuple[tuple[str, int, str], ...]:
    """Enumerate and hash only Markdown files using pinned descriptor-relative access.

    All tree entries count toward the 500,000-entry limit. Non-Markdown entries
    are inspected with metadata only; their payload bytes are never opened/read.
    """
    requested = Path(source_root).expanduser()
    if requested.is_symlink():
        raise CloudIndexVerificationError("filesystem_unsafe")
    try:
        root = requested.resolve(strict=True)
        root_fd = _open_canonical_root(root)
    except Exception:
        raise CloudIndexVerificationError("filesystem_unsafe") from None
    if not root.is_dir():
        os.close(root_fd)
        raise CloudIndexVerificationError("filesystem_unsafe")

    budget = {"entries": 1, "documents": 0, "markdown_bytes": 0}
    documents: list[tuple[str, int, str]] = []

    def walk(directory_fd: int, prefix: str, components: tuple[str, ...]) -> None:
        _assert_fd_beneath(directory_fd, root)
        scan_fd = os.dup(directory_fd)
        names: list[str] = []
        try:
            with os.scandir(scan_fd) as entries:
                for entry in entries:
                    budget["entries"] += 1
                    if budget["entries"] > MAX_SOURCE_TREE_ENTRIES:
                        raise CloudIndexVerificationError("resource_limit_exceeded")
                    name = entry.name
                    try:
                        name.encode("utf-8", errors="strict")
                    except UnicodeEncodeError:
                        raise CloudIndexVerificationError("filesystem_unsafe") from None
                    names.append(name)
        except CloudIndexVerificationError:
            raise
        except (OSError, UnicodeError, ValueError):
            raise CloudIndexVerificationError("filesystem_unsafe") from None
        finally:
            os.close(scan_fd)

        names.sort(key=lambda item: item.encode("utf-8", errors="strict"))
        for name in names:
            relative = f"{prefix}/{name}" if prefix else name
            relative = _safe_path(relative)
            child_components = components + (name,)
            try:
                before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError:
                raise CloudIndexVerificationError("filesystem_race") from None
            mode = before.st_mode
            if stat.S_ISLNK(mode):
                raise CloudIndexVerificationError("filesystem_unsafe")

            if stat.S_ISDIR(mode):
                try:
                    child_fd = _open_directory_at(directory_fd, name)
                except OSError:
                    raise CloudIndexVerificationError("filesystem_race") from None
                try:
                    opened = os.fstat(child_fd)
                    if (
                        not stat.S_ISDIR(opened.st_mode)
                        or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                    ):
                        raise CloudIndexVerificationError("filesystem_race")
                    _assert_fd_beneath(child_fd, root)
                    walk(child_fd, relative, child_components)
                    try:
                        after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    except OSError:
                        raise CloudIndexVerificationError("filesystem_race") from None
                    if (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino):
                        raise CloudIndexVerificationError("filesystem_race")
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(mode):
                if PurePosixPath(relative).suffix.lower() == ".md":
                    budget["documents"] += 1
                    if budget["documents"] > MAX_MARKDOWN_DOCUMENTS:
                        raise CloudIndexVerificationError("resource_limit_exceeded")
                    if before.st_size > MAX_MARKDOWN_DOCUMENT_BYTES:
                        raise CloudIndexVerificationError("resource_limit_exceeded")
                    size, digest = _read_markdown_digest(root_fd, root, child_components, before)
                    if size != before.st_size:
                        raise CloudIndexVerificationError("filesystem_race")
                    budget["markdown_bytes"] += size
                    if budget["markdown_bytes"] > MAX_TOTAL_MARKDOWN_BYTES:
                        raise CloudIndexVerificationError("resource_limit_exceeded")
                    documents.append((relative, size, digest))
                else:
                    # Metadata-only: never open or retain arbitrary attachment bytes.
                    try:
                        after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    except OSError:
                        raise CloudIndexVerificationError("filesystem_race") from None
                    if _stat_signature(before) != _stat_signature(after):
                        raise CloudIndexVerificationError("filesystem_race")
            else:
                raise CloudIndexVerificationError("filesystem_unsafe")
        _assert_fd_beneath(directory_fd, root)

    try:
        walk(root_fd, "", ())
        documents.sort(key=lambda item: item[0].encode("utf-8", errors="strict"))
        return tuple(documents)
    except CloudIndexVerificationError:
        raise
    except (OSError, RuntimeError, UnicodeError, ValueError, TypeError):
        raise CloudIndexVerificationError("filesystem_unsafe") from None
    finally:
        os.close(root_fd)


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8", errors="strict")


def _expected_inventory(files: tuple[tuple[str, int, str], ...]) -> bytes:
    documents: list[dict[str, Any]] = []
    empty = _canonical_bytes({"format": INVENTORY_FORMAT, "documents": []})
    projected_size = len(empty) - 2
    for path, size, digest in files:
        row = {"path": path, "byte_size": size, "sha256": digest}
        projected_size += len(_canonical_bytes(row)) + (1 if documents else 0)
        if projected_size > MAX_INVENTORY_BYTES:
            raise CloudIndexVerificationError("resource_limit_exceeded")
        documents.append(row)
    result = _canonical_bytes({"format": INVENTORY_FORMAT, "documents": documents})
    if len(result) > MAX_INVENTORY_BYTES:
        raise CloudIndexVerificationError("resource_limit_exceeded")
    return result


def _validate_inventory(raw: bytes, expected: bytes, att: CloudIndexAttestation) -> None:
    if type(raw) is not bytes or len(raw) > MAX_INVENTORY_BYTES:
        raise CloudIndexVerificationError("resource_limit_exceeded")
    try:
        obj = _exact(_canonical_object(raw, max_bytes=MAX_INVENTORY_BYTES, bounded_arrays={"documents": MAX_MARKDOWN_DOCUMENTS}), {"format", "documents"})
        if obj["format"] != INVENTORY_FORMAT or not isinstance(obj["documents"], list):
            raise ValueError("unsupported inventory")
        if len(obj["documents"]) > MAX_MARKDOWN_DOCUMENTS:
            raise CloudIndexVerificationError("resource_limit_exceeded")
        seen: set[str] = set()
        previous: bytes | None = None
        total_bytes = 0
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
            total_bytes += byte_size
            if total_bytes > MAX_TOTAL_MARKDOWN_BYTES:
                raise CloudIndexVerificationError("resource_limit_exceeded")
            if not isinstance(item["sha256"], str) or not _SHA256_RE.fullmatch(item["sha256"]):
                raise ValueError("invalid file digest")
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        if digest != att.markdown_inventory_sha256 or len(obj["documents"]) != att.markdown_document_count:
            raise CloudIndexVerificationError("inventory_mismatch")
        if raw != expected:
            raise CloudIndexVerificationError("inventory_mismatch")
    except CloudIndexVerificationError:
        raise
    except Exception:
        raise CloudIndexVerificationError("inventory_invalid") from None


def _read_regular(path: Path) -> bytes:
    """Read the explicitly supplied SQLite file without following a final symlink."""
    try:
        before = path.lstat()
    except OSError:
        raise CloudIndexVerificationError("database_invalid") from None
    if not stat.S_ISREG(before.st_mode):
        raise CloudIndexVerificationError("database_invalid")
    flags = (
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise CloudIndexVerificationError("database_invalid") from None
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise CloudIndexVerificationError("database_invalid")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if _stat_signature(opened) != _stat_signature(after):
            raise CloudIndexVerificationError("database_invalid")
        raw = b"".join(chunks)
        if len(raw) != after.st_size:
            raise CloudIndexVerificationError("database_invalid")
        try:
            path_after = path.lstat()
        except OSError:
            raise CloudIndexVerificationError("database_invalid") from None
        if (path_after.st_dev, path_after.st_ino) != (after.st_dev, after.st_ino):
            raise CloudIndexVerificationError("database_invalid")
        return raw
    finally:
        os.close(descriptor)


def _database_bytes(path: str | Path) -> tuple[Path, str, int, tuple[int, int, int, int, int]]:
    """Hash the SQLite file incrementally without retaining its contents."""
    requested = Path(path).expanduser()
    try:
        if requested.is_symlink():
            raise CloudIndexVerificationError("database_invalid")
        canonical = requested.resolve(strict=True)
        before = canonical.stat()
        if not stat.S_ISREG(before.st_mode):
            raise CloudIndexVerificationError("database_invalid")
        flags = (
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        descriptor = os.open(canonical, flags)
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            ):
                raise CloudIndexVerificationError("database_invalid")
            digest = hashlib.sha256()
            total = 0
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                digest.update(chunk)
            after_fd = os.fstat(descriptor)
            try:
                after_path = canonical.stat()
            except OSError:
                raise CloudIndexVerificationError("database_invalid") from None
            if (
                _stat_signature(opened) != _stat_signature(after_fd)
                or (after_fd.st_dev, after_fd.st_ino) != (after_path.st_dev, after_path.st_ino)
                or total != after_fd.st_size
            ):
                raise CloudIndexVerificationError("database_invalid")
            signature = _stat_signature(after_fd)
            return canonical, "sha256:" + digest.hexdigest(), total, signature
        finally:
            os.close(descriptor)
    except CloudIndexVerificationError:
        raise
    except (OSError, RuntimeError, ValueError, TypeError):
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
    db_path: Path,
    source_root: Path,
    source_files: tuple[tuple[str, int, str], ...],
) -> tuple[tuple[int, int, int, int, int], tuple[ParserIdentity, ...]]:
    connection: sqlite3.Connection | None = None
    root_fd: int | None = None
    try:
        source_by_path = {path: (size, digest) for path, size, digest in source_files}
        if len(source_by_path) != len(source_files):
            raise CloudIndexVerificationError("inventory_mismatch")

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

        if set(active_docs) != set(source_by_path):
            raise CloudIndexVerificationError("document_mismatch")
        for path, doc in active_docs.items():
            expected_size, expected_digest = source_by_path[path]
            if doc["source_size_bytes"] != expected_size or doc["source_sha256"] != expected_digest:
                raise CloudIndexVerificationError("document_mismatch")

        events_by_doc: dict[int, list[dict[str, Any]]] = {}
        for doc_pk, doc in doc_by_pk.items():
            events_by_doc[doc_pk] = _validate_events(connection, doc_pk, doc["generation"])

        node_ids: set[str] = set()
        node_ids_by_doc: dict[int, set[str]] = {}
        node_pk_to_doc = {node["node_pk"]: node["document_pk"] for node in nodes}
        node_id_by_pk = {node["node_pk"]: node["node_id"] for node in nodes}
        if len(node_pk_to_doc) != len(nodes) or len(node_id_by_pk) != len(nodes):
            raise CloudIndexVerificationError("node_integrity_failure")
        nodes_by_doc: dict[int, list[tuple[dict[str, Any], str | None, list[str]]]] = {}
        active_node_count = 0

        for node in nodes:
            doc = doc_by_pk.get(node.get("document_pk"))
            if doc is None:
                raise CloudIndexVerificationError("node_integrity_failure")
            node_id = node.get("node_id")
            if not _valid_node_id(node_id) or node_id in node_ids:
                raise CloudIndexVerificationError("node_identity_mismatch")
            node_ids.add(node_id)
            node_ids_by_doc.setdefault(doc["document_pk"], set()).add(node_id)
            events = events_by_doc[doc["document_pk"]]
            heading_path, parent_id, latest_event = _check_db_snapshot(connection, node, doc, events)
            status = _resolve_db_status(node, doc, latest_event)
            if node["status"] in {"active", "ambiguous"} and node.get("stale_generation") is None:
                if doc["status"] != "active":
                    raise CloudIndexVerificationError("node_integrity_failure")
                active_node_count += 1
                nodes_by_doc.setdefault(doc["document_pk"], []).append(
                    (node, parent_id, heading_path)
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

        root_fd = _open_canonical_root(source_root)
        for path, doc in active_docs.items():
            expected_size, expected_digest = source_by_path[path]
            raw = _read_markdown_bytes(
                root_fd, source_root, _safe_source_components(path),
                expected_size, expected_digest,
            )
            source_text = _verify_document_bytes(doc, raw)
            for node, parent_id, heading_path in nodes_by_doc.get(doc["document_pk"], []):
                _verify_node_from_source(
                    node=node,
                    document=doc,
                    parent_node_id=parent_id,
                    heading_path=heading_path,
                    metadata=_decode_json(
                        node["metadata_json"], dict, "node_metadata_invalid",
                        "The stored node metadata is invalid.",
                    ),
                    source_bytes=raw,
                    source_text=source_text,
                    expected_hash=node["content_hash"],
                )
            del source_text
            del raw

        versions = connection.execute(
            "SELECT node_pk, version_no, generation, content_hash, source_path, node_type, "
            "parent_node_id, heading_path_json, line_start, line_end, char_start, char_end, "
            "byte_start, byte_end, content_spans_json, raw_text, metadata_json, warnings_json "
            "FROM node_versions ORDER BY node_pk, version_no"
        ).fetchall()
        versions_by_node: dict[int, list[dict[str, Any]]] = {}
        coordinate_fields = (
            "line_start", "line_end", "char_start", "char_end", "byte_start", "byte_end"
        )
        for version_row in versions:
            row = dict(version_row)
            node_pk = row.get("node_pk")
            doc_pk = node_pk_to_doc.get(node_pk)
            if doc_pk is None or row["source_path"] != doc_by_pk[doc_pk]["source_path"]:
                raise CloudIndexVerificationError("node_reference_mismatch")
            if row["node_type"] not in _ALLOWED_NODE_TYPES:
                raise CloudIndexVerificationError("node_reference_mismatch")
            parent_id = row["parent_node_id"]
            if parent_id is not None and (
                not _valid_node_id(parent_id)
                or parent_id not in node_ids_by_doc.get(doc_pk, set())
                or parent_id == node_id_by_pk.get(node_pk)
            ):
                raise CloudIndexVerificationError("node_reference_mismatch")

            if any(type(row[field]) is not int for field in coordinate_fields):
                raise CloudIndexVerificationError("node_span_mismatch")
            if (
                row["line_start"] < 1
                or row["line_end"] < 0
                or row["line_end"] < row["line_start"] - 1
                or (row["line_end"] == row["line_start"] - 1 and row["char_start"] != row["char_end"])
                or row["char_start"] < 0
                or row["char_end"] < row["char_start"]
                or row["byte_start"] < 0
                or row["byte_end"] < row["byte_start"]
            ):
                raise CloudIndexVerificationError("node_span_mismatch")

            if (
                type(row["version_no"]) is not int or row["version_no"] < 1
                or type(row["generation"]) is not int or row["generation"] < 1
                or not _valid_hash(row["content_hash"])
                or not isinstance(row["raw_text"], str)
            ):
                raise CloudIndexVerificationError("node_version_mismatch")
            try:
                raw_version = row["raw_text"].encode("utf-8", errors="strict")
            except UnicodeEncodeError:
                raise CloudIndexVerificationError("node_version_mismatch") from None
            if "sha256:" + hashlib.sha256(raw_version).hexdigest() != row["content_hash"]:
                raise CloudIndexVerificationError("node_content_mismatch")

            heading_path = _decode_json(
                row["heading_path_json"], list, "node_version_mismatch", "Invalid version data."
            )
            if any(not isinstance(item, str) for item in heading_path):
                raise CloudIndexVerificationError("node_version_mismatch")
            spans = _decode_json(
                row["content_spans_json"], list, "node_version_mismatch", "Invalid version data."
            )
            for span in spans:
                if type(span) is not dict or set(span) != {
                    "line_start", "line_end", "char_start", "char_end", "byte_start", "byte_end"
                }:
                    raise CloudIndexVerificationError("node_span_mismatch")
                if any(type(span[field]) is not int for field in coordinate_fields):
                    raise CloudIndexVerificationError("node_span_mismatch")
                if (
                    span["line_start"] < 1
                    or span["line_end"] < 0
                    or span["line_end"] < span["line_start"] - 1
                    or (span["line_end"] == span["line_start"] - 1 and span["char_start"] != span["char_end"])
                    or span["char_start"] < 0
                    or span["char_end"] < span["char_start"]
                    or span["byte_start"] < 0
                    or span["byte_end"] < span["byte_start"]
                ):
                    raise CloudIndexVerificationError("node_span_mismatch")
            _decode_json(row["metadata_json"], dict, "node_version_mismatch", "Invalid version data.")
            warnings = _decode_json(row["warnings_json"], list, "node_version_mismatch", "Invalid version data.")
            if any(not isinstance(item, str) for item in warnings):
                raise CloudIndexVerificationError("node_version_mismatch")
            versions_by_node.setdefault(node_pk, []).append(row)

        nodes_by_pk = {node["node_pk"]: node for node in nodes}
        for node_pk, node_versions in versions_by_node.items():
            numbers = [row["version_no"] for row in node_versions]
            generations = [row["generation"] for row in node_versions]
            node = nodes_by_pk[node_pk]
            doc = doc_by_pk[node["document_pk"]]
            if (
                numbers != list(range(1, len(node_versions) + 1))
                or generations != sorted(generations)
                or generations[0] < node["created_generation"]
                or generations[-1] != node["updated_generation"]
                or generations[-1] > doc["generation"]
            ):
                raise CloudIndexVerificationError("node_generation_mismatch")
            latest = node_versions[-1]
            parent_id = (
                node_id_by_pk.get(node["parent_node_pk"])
                if node["parent_node_pk"] is not None else None
            )
            if (
                latest["parent_node_id"] != parent_id
                or latest["node_type"] != node["node_type"]
                or latest["source_path"] != doc["source_path"]
                or latest["line_start"] != node["line_start"]
                or latest["line_end"] != node["line_end"]
                or latest["char_start"] != node["char_start"]
                or latest["char_end"] != node["char_end"]
                or latest["byte_start"] != node["byte_start"]
                or latest["byte_end"] != node["byte_end"]
            ):
                raise CloudIndexVerificationError("node_version_mismatch")
        if set(versions_by_node) != set(nodes_by_pk):
            raise CloudIndexVerificationError("node_version_mismatch")

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
    except sqlite3.Error:
        raise CloudIndexVerificationError("sqlite_integrity_failure") from None
    except (OSError, UnicodeError, ValueError, TypeError, KeyError):
        raise CloudIndexVerificationError("node_integrity_failure") from None
    finally:
        if root_fd is not None:
            os.close(root_fd)
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
    expected_source_revision: SourceRevision,
    attestation: bytes,
    markdown_inventory: bytes,
) -> CloudIndexVerificationReport:
    """Verify one already-materialized E1 cloud index against its outer revision.

    The expected_source_revision must be an exact E1-owned Git/import tagged value
    supplied by the caller from the independently verified outer snapshot handle.
    Attestation and inventory are the exact raw #119 bytes. This E1 boundary
    verifies materialized consistency; it does not authenticate source origin,
    provider immutability or the outer CloudSnapshotRef itself.
    """
    parsed = parse_cloud_index_attestation(attestation)
    try:
        if type(expected_source_revision) not in (
            GitCommitSourceRevision, ImmutableImportSourceRevision
        ):
            raise CloudIndexVerificationError("source_revision_invalid")
        try:
            expected_revision = _revision(expected_source_revision.to_dict())
        except Exception:
            raise CloudIndexVerificationError("source_revision_invalid") from None
        if (
            type(parsed.source_revision) is not type(expected_revision)
            or parsed.source_revision != expected_revision
        ):
            raise CloudIndexVerificationError("source_revision_mismatch")

        if (
            parsed.indexer_identity.name != "sfra-structural-indexer"
            or parsed.indexer_identity.version != _installed_indexer_version()
        ):
            raise CloudIndexVerificationError("indexer_identity_mismatch")
        if not isinstance(markdown_inventory, bytes) or len(markdown_inventory) > MAX_INVENTORY_BYTES:
            raise CloudIndexVerificationError("resource_limit_exceeded")

        requested_root = Path(source_root).expanduser()
        if requested_root.is_symlink():
            raise CloudIndexVerificationError("filesystem_unsafe")
        try:
            root = requested_root.resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            raise CloudIndexVerificationError("filesystem_unsafe") from None
        if not root.is_dir():
            raise CloudIndexVerificationError("filesystem_unsafe")

        source_files = _collect_source_files(root)
        expected_inventory = _expected_inventory(source_files)
        _validate_inventory(markdown_inventory, expected_inventory, parsed)

        db_path, actual_digest, database_size, signature = _database_bytes(database_path)
        if actual_digest != parsed.database_sha256:
            raise CloudIndexVerificationError("database_digest_mismatch")
        if database_size != parsed.database_byte_size:
            raise CloudIndexVerificationError("database_size_mismatch")

        counts, parsers = _verify_database_consistency(db_path, root, source_files)

        # Re-scan using the same descriptor-rooted admission rules. This catches
        # tree replacement or inventory drift during the SQLite verification.
        source_files_after = _collect_source_files(root)
        if source_files_after != source_files:
            raise CloudIndexVerificationError("filesystem_race")

        try:
            after = db_path.stat()
        except OSError:
            raise CloudIndexVerificationError("database_invalid") from None
        if _stat_signature(after) != signature:
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
            source_revision=expected_revision,
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
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, sqlite3.Error):
        raise CloudIndexVerificationError("verification_failed") from None



__all__ = [
    "ATTESTATION_FORMAT", "INVENTORY_FORMAT", "CloudIndexAttestation",
    "CloudIndexVerificationError", "CloudIndexVerificationReport",
    "GitCommitSourceRevision", "ImmutableImportSourceRevision", "SourceRevision", "IndexerIdentity",
    "ParserIdentity", "parse_cloud_index_attestation", "verify_materialized_cloud_index",
]
