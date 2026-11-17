"""Source-verified, read-only lookup of a current SFRA structural node."""

from __future__ import annotations

import bisect
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


_NODE_ID_RE = re.compile(
    r"node_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z"
)
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SUPPORTED_SCHEMA_VERSION = 2

_EVENT_TYPES = frozenset(
    {
        "document_root",
        "unique_content_hash",
        "unique_heading_key",
        "unique_sibling_heading_key",
        "unique_sibling_slot",
        "new",
        "ambiguous",
        "stale",
        "stale_ambiguous_candidate",
        "document_deleted",
    }
)
_MATCH_EVENT_TYPES = frozenset(
    {
        "document_root",
        "unique_content_hash",
        "unique_heading_key",
        "unique_sibling_heading_key",
        "unique_sibling_slot",
        "new",
    }
)
_REQUIRED_TABLES = frozenset(
    {"schema_info", "documents", "structural_nodes", "node_versions", "node_match_events"}
)


class NodeLookupStatus(str, Enum):
    """Public status returned by get_node_by_id."""

    OK = "ok"
    STALE_SOURCE = "stale_source"
    DELETED = "deleted"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    INVALID_REQUEST = "invalid_request"
    INTEGRITY_ERROR = "integrity_error"


@dataclass(frozen=True, slots=True)
class NodeRecord:
    """A node whose text was sliced from and verified against the source file."""

    node_id: str
    content_hash: str
    source_path: str
    node_type: str
    parent_node_id: str | None
    heading_path: tuple[str, ...]
    raw_text: str
    line_start: int
    line_end: int
    char_start: int
    char_end: int
    byte_start: int
    byte_end: int
    source_sha256: str

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["heading_path"] = list(self.heading_path)
        return result


@dataclass(frozen=True, slots=True)
class NodeLookupResult:
    """A safe lookup result. Error results never contain node text or coordinates."""

    status: NodeLookupStatus
    node: NodeRecord | None = None
    error_code: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.status is NodeLookupStatus.OK and self.node is None:
            raise ValueError("An ok lookup result must include a node")
        if self.status is not NodeLookupStatus.OK and self.node is not None:
            raise ValueError("A failed lookup result must not include a node")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": self.status.value,
            "node": self.node.to_dict() if self.node is not None else None,
        }
        if self.error_code is not None:
            result["error"] = {
                "code": self.error_code,
                "message": self.message or "The requested source node could not be verified.",
            }
        return result


class _LookupFailure(Exception):
    def __init__(self, status: NodeLookupStatus, code: str, message: str):
        super().__init__(code)
        self.status = status
        self.code = code
        self.safe_message = message


def _failure(status: NodeLookupStatus, code: str, message: str) -> NodeLookupResult:
    return NodeLookupResult(status=status, error_code=code, message=message)


def _raise(status: NodeLookupStatus, code: str, message: str) -> None:
    raise _LookupFailure(status, code, message)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _valid_node_id(value: Any) -> bool:
    return isinstance(value, str) and _NODE_ID_RE.fullmatch(value) is not None


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH_RE.fullmatch(value) is not None


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _safe_source_components(source_path: Any) -> tuple[str, ...]:
    """Validate the SQLite path lexically before any filesystem access."""
    if (
        not isinstance(source_path, str)
        or not source_path
        or "\x00" in source_path
        or "\\" in source_path
        or source_path.startswith("/")
        or re.match(r"^[A-Za-z]:", source_path) is not None
    ):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "source_path_unsafe",
            "The stored source path is not a safe relative POSIX path.",
        )

    components = tuple(source_path.split("/"))
    if any(part in {"", ".", ".."} for part in components):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "source_path_unsafe",
            "The stored source path is not a safe relative POSIX path.",
        )
    if PurePosixPath(source_path).is_absolute() or PurePosixPath(source_path).as_posix() != source_path:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "source_path_unsafe",
            "The stored source path is not a canonical relative POSIX path.",
        )
    return components


def _read_only_connection(db_path: str | Path) -> sqlite3.Connection:
    """Open an existing database read-only; never create or migrate it."""
    try:
        path = Path(db_path).expanduser().resolve(strict=True)
    except (OSError, TypeError, ValueError):
        _raise(
            NodeLookupStatus.INVALID_REQUEST,
            "db_path_invalid",
            "The SQLite path must identify an existing database file.",
        )
    if not path.is_file():
        _raise(
            NodeLookupStatus.INVALID_REQUEST,
            "db_path_invalid",
            "The SQLite path must identify an existing database file.",
        )

    try:
        connection = sqlite3.connect(
            path.as_uri() + "?mode=ro",
            uri=True,
            timeout=5,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        return connection
    except (sqlite3.Error, OSError, ValueError):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "sqlite_open_failed",
            "The existing SQLite index could not be opened safely for reading.",
        )


def _verify_database(connection: sqlite3.Connection) -> None:
    try:
        integrity_rows = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        if integrity_rows != ["ok"]:
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "sqlite_integrity_failure",
                "The SQLite index failed its integrity check.",
            )
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "foreign_key_failure",
                "The SQLite index contains foreign-key violations.",
            )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if not _REQUIRED_TABLES.issubset(tables):
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "schema_incomplete",
                "The SQLite index does not contain the required schema v2 tables.",
            )
        schema_rows = connection.execute(
            "SELECT schema_version FROM schema_info WHERE singleton = 1"
        ).fetchall()
        if len(schema_rows) != 1 or schema_rows[0][0] != _SUPPORTED_SCHEMA_VERSION:
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "schema_version_unsupported",
                "The SQLite index schema is not the supported version 2.",
            )
    except sqlite3.Error:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "sqlite_integrity_failure",
            "The SQLite index could not be validated.",
        )


def _decode_json(value: Any, expected_type: type, code: str, message: str) -> Any:
    if not isinstance(value, str):
        _raise(NodeLookupStatus.INTEGRITY_ERROR, code, message)
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        _raise(NodeLookupStatus.INTEGRITY_ERROR, code, message)
    if not isinstance(decoded, expected_type):
        _raise(NodeLookupStatus.INTEGRITY_ERROR, code, message)
    return decoded


def _validate_events(
    connection: sqlite3.Connection,
    document_pk: int,
    document_generation: int,
) -> list[dict[str, Any]]:
    """Validate every event payload for this document before status resolution."""
    try:
        rows = connection.execute(
            """SELECT event_pk, generation, new_local_key, event_type, node_id,
                      candidate_node_ids_json, details_json
               FROM node_match_events
               WHERE document_pk = ?
               ORDER BY event_pk""",
            (document_pk,),
        ).fetchall()
    except sqlite3.Error:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "match_event_read_failed",
            "The node matching history could not be read.",
        )

    events: list[dict[str, Any]] = []
    previous_generation = 0
    for row in rows:
        event_pk = row["event_pk"]
        generation = row["generation"]
        event_type = row["event_type"]
        node_id = row["node_id"]
        if (
            not _is_int(event_pk)
            or event_pk < 1
            or not _is_int(generation)
            or generation < 1
            or generation > document_generation
            or generation < previous_generation
            or event_type not in _EVENT_TYPES
            or not _valid_node_id(node_id)
        ):
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "match_event_type_unknown",
                "The node matching history contains an unknown or inconsistent event.",
            )

        local_key = row["new_local_key"]
        if local_key is not None and (not isinstance(local_key, str) or not local_key):
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "match_event_payload_invalid",
                "The node matching history contains an invalid event payload.",
            )
        if event_type in _MATCH_EVENT_TYPES and local_key is None:
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "match_event_payload_invalid",
                "The node matching history contains an incomplete event payload.",
            )

        candidates = _decode_json(
            row["candidate_node_ids_json"],
            list,
            "match_event_payload_invalid",
            "The node matching history contains an invalid candidate list.",
        )
        details = _decode_json(
            row["details_json"],
            dict,
            "match_event_payload_invalid",
            "The node matching history contains invalid event details.",
        )
        if (
            any(not _valid_node_id(candidate) for candidate in candidates)
            or len(candidates) != len(set(candidates))
            or (event_type == "ambiguous" and not candidates)
            or (event_type != "ambiguous" and candidates)
            or not all(isinstance(key, str) for key in details)
        ):
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "match_event_payload_invalid",
                "The node matching history contains an invalid event payload.",
            )

        events.append(
            {
                "event_pk": event_pk,
                "generation": generation,
                "event_type": event_type,
                "node_id": node_id,
                "candidate_node_ids": candidates,
            }
        )
        previous_generation = generation
    return events


def _validate_json_columns(node: dict[str, Any], version: dict[str, Any]) -> list[str]:
    heading_path = _decode_json(
        node["heading_path_json"],
        list,
        "node_metadata_invalid",
        "The stored node metadata is invalid.",
    )
    version_heading = _decode_json(
        version["heading_path_json"],
        list,
        "version_snapshot_mismatch",
        "The stored node version is invalid.",
    )
    if any(not isinstance(item, str) for item in heading_path + version_heading):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "node_metadata_invalid",
            "The stored node heading path is invalid.",
        )

    for row, code, message in (
        (node, "node_metadata_invalid", "The stored node metadata is invalid."),
        (version, "version_snapshot_mismatch", "The stored node version is invalid."),
    ):
        spans = _decode_json(row["content_spans_json"], list, code, message)
        metadata = _decode_json(row["metadata_json"], dict, code, message)
        warnings = _decode_json(row["warnings_json"], list, code, message)
        if (
            any(not isinstance(span, dict) for span in spans)
            or any(not isinstance(warning, str) for warning in warnings)
            or not all(isinstance(key, str) for key in metadata)
        ):
            _raise(NodeLookupStatus.INTEGRITY_ERROR, code, message)
    return heading_path


def _latest_version(connection: sqlite3.Connection, node_pk: int) -> dict[str, Any]:
    try:
        versions = [
            dict(row)
            for row in connection.execute(
                """SELECT * FROM node_versions
                   WHERE node_pk = ?
                   ORDER BY version_no""",
                (node_pk,),
            ).fetchall()
        ]
    except sqlite3.Error:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "version_history_read_failed",
            "The stored node version history could not be read.",
        )
    if not versions:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "version_snapshot_missing",
            "The stored node has no version snapshot.",
        )
    version_numbers = [row["version_no"] for row in versions]
    generations = [row["generation"] for row in versions]
    if (
        version_numbers != list(range(1, len(versions) + 1))
        or any(not _is_int(value) or value < 1 for value in generations)
        or generations != sorted(generations)
    ):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "version_history_invalid",
            "The stored node version history is inconsistent.",
        )
    return versions[-1]


def _check_db_snapshot(
    connection: sqlite3.Connection,
    node: dict[str, Any],
    document: dict[str, Any],
    events: list[dict[str, Any]],
) -> tuple[list[str], str | None, str | None]:
    """Run the full DB-only integrity preflight without opening the Vault."""
    parent_node_id: str | None = None
    if node["parent_node_pk"] is not None:
        parents = connection.execute(
            "SELECT node_id, document_pk FROM structural_nodes WHERE node_pk = ?",
            (node["parent_node_pk"],),
        ).fetchall()
        if len(parents) != 1 or parents[0]["document_pk"] != node["document_pk"]:
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "parent_reference_invalid",
                "The stored node parent reference is inconsistent.",
            )
        parent_node_id = parents[0]["node_id"]
        if not _valid_node_id(parent_node_id):
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "parent_reference_invalid",
                "The stored node parent identifier is invalid.",
            )

    if not _valid_node_id(node["node_id"]) or not _valid_hash(node["content_hash"]):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "node_identity_invalid",
            "The stored node identity or Content Hash is invalid.",
        )
    if not isinstance(node["raw_text"], str):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "raw_text_invalid",
            "The stored node text is invalid.",
        )
    if _digest_bytes(node["raw_text"].encode("utf-8")) != node["content_hash"]:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "raw_text_hash_mismatch",
            "The stored node text does not match its Content Hash.",
        )

    try:
        all_versions = [
            dict(item)
            for item in connection.execute(
                """SELECT * FROM node_versions
                   WHERE node_pk = ?
                   ORDER BY version_no""",
                (node["node_pk"],),
            ).fetchall()
        ]
    except sqlite3.Error:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "version_history_read_failed",
            "The stored node version history could not be read.",
        )
    if not all_versions:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "version_snapshot_missing",
            "The stored node has no version snapshot.",
        )
    version_numbers = [item["version_no"] for item in all_versions]
    version_generations = [item["generation"] for item in all_versions]
    if (
        version_numbers != list(range(1, len(all_versions) + 1))
        or any(not _is_int(value) or value < 1 for value in version_generations)
        or version_generations != sorted(version_generations)
    ):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "version_history_invalid",
            "The stored node version history is inconsistent.",
        )
    for saved_version in all_versions:
        if (
            not _valid_hash(saved_version["content_hash"])
            or not isinstance(saved_version["raw_text"], str)
            or _digest_bytes(saved_version["raw_text"].encode("utf-8"))
            != saved_version["content_hash"]
        ):
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "version_content_hash_mismatch",
                "A saved node version does not match its Content Hash.",
            )

    latest = all_versions[-1]
    heading_path = _validate_json_columns(node, latest)

    for field in (
        "line_start", "line_end", "char_start", "char_end", "byte_start", "byte_end"
    ):
        if not _is_int(node[field]):
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "source_coordinates_invalid",
                "The stored source coordinates are invalid.",
            )
    if (
        node["char_start"] < 0
        or node["char_end"] < node["char_start"]
        or node["byte_start"] < 0
        or node["byte_end"] < node["byte_start"]
        or node["line_start"] < 1
        or node["line_end"] < 0
        or (
            node["line_end"] < node["line_start"]
            and node["line_end"] != node["line_start"] - 1
        )
    ):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "source_coordinates_invalid",
            "The stored source coordinate ranges are inconsistent.",
        )

    version_parent = latest["parent_node_id"]
    current_fields = {
        "content_hash": node["content_hash"],
        "source_path": document["source_path"],
        "node_type": node["node_type"],
        "parent_node_id": parent_node_id,
        "heading_path_json": node["heading_path_json"],
        "line_start": node["line_start"],
        "line_end": node["line_end"],
        "char_start": node["char_start"],
        "char_end": node["char_end"],
        "byte_start": node["byte_start"],
        "byte_end": node["byte_end"],
        "content_spans_json": node["content_spans_json"],
        "raw_text": node["raw_text"],
        "metadata_json": node["metadata_json"],
        "warnings_json": node["warnings_json"],
    }
    if any(latest[key] != value for key, value in current_fields.items()) or version_parent != parent_node_id:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "version_snapshot_mismatch",
            "The current node record does not match its latest saved version.",
        )

    if (
        not _is_int(node["created_generation"])
        or not _is_int(node["updated_generation"])
        or node["created_generation"] < 1
        or node["updated_generation"] < node["created_generation"]
        or latest["generation"] > node["updated_generation"]
        or node["updated_generation"] > document["generation"]
    ):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "version_generation_mismatch",
            "The current node generation does not match its version history.",
        )

    node_events = [event for event in events if event["node_id"] == node["node_id"]]
    latest_event = node_events[-1]["event_type"] if node_events else None
    candidate_event = any(
        event["event_type"] == "ambiguous"
        and node["node_id"] in event["candidate_node_ids"]
        for event in events
    )
    if candidate_event:
        latest_event = "candidate_of_ambiguous_event"
    return heading_path, parent_node_id, latest_event


def _resolve_db_status(
    node: dict[str, Any],
    document: dict[str, Any],
    latest_event: str | None,
) -> NodeLookupStatus | None:
    doc_status = document["status"]
    node_status = node["status"]
    stale_generation = node["stale_generation"]
    doc_generation = document["generation"]

    if doc_status not in {"active", "deleted"} or node_status not in {
        "active", "ambiguous", "stale"
    }:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "stored_status_invalid",
            "The stored document or node status is invalid.",
        )
    if not _is_int(doc_generation) or doc_generation < 1:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "document_generation_invalid",
            "The stored document generation is invalid.",
        )

    if doc_status == "deleted":
        if (
            node_status != "stale"
            or not _is_int(stale_generation)
            or stale_generation < node["updated_generation"]
            or stale_generation > doc_generation
        ):
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "deleted_document_state_invalid",
                "The deleted document and its node state are inconsistent.",
            )
        return NodeLookupStatus.DELETED

    if node_status in {"active", "ambiguous"}:
        if stale_generation is not None:
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "node_lifecycle_invalid",
                "The stored node lifecycle state is inconsistent.",
            )
        if node_status == "ambiguous":
            if latest_event != "ambiguous":
                _raise(
                    NodeLookupStatus.INTEGRITY_ERROR,
                    "ambiguous_event_missing",
                    "The ambiguous node has no matching ambiguity event.",
                )
            return NodeLookupStatus.AMBIGUOUS
        if latest_event in {
            "stale", "stale_ambiguous_candidate", "document_deleted",
            "ambiguous", "candidate_of_ambiguous_event",
        }:
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "node_event_state_mismatch",
                "The active node status conflicts with its matching history.",
            )
        return None

    if (
        not _is_int(stale_generation)
        or stale_generation < node["updated_generation"]
        or stale_generation > doc_generation
    ):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "stale_generation_invalid",
            "The stale node lifecycle generation is inconsistent.",
        )
    if latest_event in {"stale_ambiguous_candidate", "candidate_of_ambiguous_event"}:
        return NodeLookupStatus.AMBIGUOUS
    if latest_event in {"stale", "document_deleted"}:
        return NodeLookupStatus.DELETED
    _raise(
        NodeLookupStatus.INTEGRITY_ERROR,
        "stale_event_missing",
        "The stale node has no event confirming deletion or ambiguity.",
    )


def _is_linux() -> bool:
    return os.name == "posix" and hasattr(os, "uname") and os.uname().sysname == "Linux"


def _openat2_file(root_fd: int, relative_path: str) -> tuple[int | None, int | None]:
    """Try Linux openat2 with BENEATH and no-symlink resolution."""
    class OpenHow(ctypes.Structure):
        _fields_ = [
            ("flags", ctypes.c_uint64),
            ("mode", ctypes.c_uint64),
            ("resolve", ctypes.c_uint64),
        ]

    libc = ctypes.CDLL(None, use_errno=True)
    syscall = libc.syscall
    syscall.restype = ctypes.c_long
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    # RESOLVE_NO_MAGICLINKS | RESOLVE_NO_SYMLINKS | RESOLVE_BENEATH
    how = OpenHow(flags, 0, 0x02 | 0x04 | 0x08)
    fd = syscall(
        437,  # __NR_openat2 on x86_64 and aarch64 Linux
        root_fd,
        ctypes.c_char_p(os.fsencode(relative_path)),
        ctypes.byref(how),
        ctypes.sizeof(how),
    )
    if fd >= 0:
        return int(fd), None
    return None, ctypes.get_errno()


def _descriptor_walk(root_fd: int, components: tuple[str, ...]) -> int:
    """POSIX fallback with every path component opened relative to a pinned FD."""
    current_fd = os.dup(root_fd)
    directory_flags = (
        os.O_RDONLY
        | os.O_DIRECTORY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        for component in components[:-1]:
            next_fd = os.open(component, directory_flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        return os.open(components[-1], file_flags, dir_fd=current_fd)
    finally:
        os.close(current_fd)


def _open_beneath(root_fd: int, components: tuple[str, ...]) -> int:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "secure_open_unavailable",
            "This platform cannot guarantee safe source-file resolution.",
        )

    relative_path = "/".join(components)
    if _is_linux():
        fd, open_error = _openat2_file(root_fd, relative_path)
        if fd is not None:
            return fd
        if open_error not in {errno.ENOSYS, errno.EINVAL, errno.E2BIG, errno.EPERM}:
            raise OSError(open_error or errno.EIO, os.strerror(open_error or errno.EIO))

    try:
        return _descriptor_walk(root_fd, components)
    except (TypeError, NotImplementedError) as exc:
        raise OSError(errno.ENOSYS, "descriptor-relative open is unavailable") from exc


def _stat_signature(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _check_fd_path(fd: int, canonical_root: Path) -> None:
    """On Linux, ensure the opened descriptor still names a path under the root."""
    proc_root = Path("/proc/self/fd")
    if not proc_root.is_dir():
        return
    proc_fd = proc_root / str(fd)
    try:
        target_text = os.readlink(proc_fd)
        if target_text.endswith(" (deleted)"):
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "file_identity_changed",
                "The source file changed while it was being read.",
            )
        target = Path(target_text).resolve(strict=True)
        target.relative_to(canonical_root)
    except _LookupFailure:
        raise
    except (OSError, ValueError):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "source_target_outside_root",
            "The opened source file could not be confirmed inside the Vault.",
        )


def _open_canonical_root(canonical_root: Path) -> int:
    """Pin the Vault root by walking from / without following any symlink."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise OSError(errno.ENOSYS, "safe root descriptor opening is unavailable")
    directory_flags = (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    current_fd = os.open("/", directory_flags)
    try:
        for component in canonical_root.parts[1:]:
            next_fd = os.open(component, directory_flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        info = os.fstat(current_fd)
        if not stat.S_ISDIR(info.st_mode):
            raise OSError(errno.ENOTDIR, "Vault root is not a directory")
        proc_root = Path("/proc/self/fd")
        if proc_root.is_dir():
            target_text = os.readlink(proc_root / str(current_fd))
            if target_text.endswith(" (deleted)"):
                raise OSError(errno.ESTALE, "Vault root changed during open")
            if Path(target_text).resolve(strict=True) != canonical_root:
                raise OSError(errno.EXDEV, "opened root differs from canonical root")
        return current_fd
    except Exception:
        os.close(current_fd)
        raise


def _read_source_file(canonical_root: Path, components: tuple[str, ...]) -> bytes:
    """Read one regular file through a root directory FD; reject symlink traversal."""
    try:
        root_fd = _open_canonical_root(canonical_root)
    except OSError:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "vault_root_open_failed",
            "The Vault root could not be opened safely.",
        )

    file_fd: int | None = None
    try:
        try:
            file_fd = _open_beneath(root_fd, components)
        except FileNotFoundError:
            _raise(
                NodeLookupStatus.STALE_SOURCE,
                "source_file_missing",
                "The indexed source file is not present in this Vault checkout.",
            )
        except OSError as exc:
            if exc.errno in {errno.ENOENT, errno.ENOTDIR}:
                _raise(
                    NodeLookupStatus.STALE_SOURCE,
                    "source_file_missing",
                    "The indexed source file is not present in this Vault checkout.",
                )
            if exc.errno in {errno.ELOOP, errno.EXDEV}:
                _raise(
                    NodeLookupStatus.INTEGRITY_ERROR,
                    "source_path_unsafe",
                    "The source path resolves through a symbolic link or outside the Vault.",
                )
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "source_open_failed",
                "The source file could not be opened safely.",
            )

        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "source_not_regular_file",
                "The indexed source path does not identify a regular file.",
            )
        _check_fd_path(file_fd, canonical_root)

        chunks: list[bytes] = []
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        source_bytes = b"".join(chunks)

        after = os.fstat(file_fd)
        if _stat_signature(before) != _stat_signature(after) or len(source_bytes) != after.st_size:
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "file_identity_changed",
                "The source file changed while it was being read.",
            )
        _check_fd_path(file_fd, canonical_root)

        # Re-open from the root and compare identity to detect path replacement.
        try:
            verify_fd = _open_beneath(root_fd, components)
        except OSError:
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "file_identity_changed",
                "The source path changed while it was being read.",
            )
        try:
            verified = os.fstat(verify_fd)
            if (verified.st_dev, verified.st_ino) != (after.st_dev, after.st_ino):
                _raise(
                    NodeLookupStatus.INTEGRITY_ERROR,
                    "file_identity_changed",
                    "The source path changed while it was being read.",
                )
        finally:
            os.close(verify_fd)
        return source_bytes
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(root_fd)


def _line_span_for_chars(source: str, char_start: int, char_end: int) -> tuple[int, int]:
    """Mirror parser._Offsets.span_from_chars, including the empty-span convention."""
    line_starts = [0]
    for index, char in enumerate(source):
        if char == "\n":
            line_starts.append(index + 1)
    if line_starts[-1] != len(source):
        line_starts.append(len(source))

    if char_start == char_end:
        line_number = max(1, bisect.bisect_right(line_starts, char_start))
        return line_number, line_number - 1
    line_start = max(1, bisect.bisect_right(line_starts, char_start))
    line_end = max(1, bisect.bisect_right(line_starts, char_end - 1))
    return line_start, line_end


def _read_and_verify_node(
    *,
    node: dict[str, Any],
    document: dict[str, Any],
    parent_node_id: str | None,
    heading_path: list[str],
    canonical_root: Path,
    components: tuple[str, ...],
    expected_hash: str,
) -> NodeRecord:
    if not _valid_hash(document["source_sha256"]):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "source_hash_invalid",
            "The stored source document Hash is invalid.",
        )
    if not _is_int(document["source_size_bytes"]) or document["source_size_bytes"] < 0:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "source_size_invalid",
            "The stored source document size is invalid.",
        )

    source_bytes = _read_source_file(canonical_root, components)
    actual_source_hash = _digest_bytes(source_bytes)
    if actual_source_hash != document["source_sha256"]:
        _raise(
            NodeLookupStatus.STALE_SOURCE,
            "source_hash_mismatch",
            "The Markdown file has changed since this node was indexed.",
        )
    if len(source_bytes) != document["source_size_bytes"]:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "source_size_mismatch",
            "The source file size conflicts with its verified document Hash.",
        )
    try:
        source_text = source_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "source_encoding_invalid",
            "The indexed source file is not valid UTF-8.",
        )

    coordinate_names = (
        "char_start", "char_end", "byte_start", "byte_end", "line_start", "line_end"
    )
    coordinates = [node[name] for name in coordinate_names]
    if any(not _is_int(value) for value in coordinates):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "source_coordinates_invalid",
            "The stored source coordinates are invalid.",
        )
    char_start, char_end, byte_start, byte_end, line_start, line_end = coordinates
    if not (0 <= char_start <= char_end <= len(source_text)):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "char_span_mismatch",
            "The stored character coordinates do not identify a valid source slice.",
        )

    # The return value is taken from this source slice, never from SQLite raw_text.
    source_fragment = source_text[char_start:char_end]
    fragment_bytes = source_fragment.encode("utf-8")
    expected_byte_start = len(source_text[:char_start].encode("utf-8"))
    expected_byte_end = len(source_text[:char_end].encode("utf-8"))
    if (
        byte_start != expected_byte_start
        or byte_end != expected_byte_end
        or not (0 <= byte_start <= byte_end <= len(source_bytes))
        or source_bytes[byte_start:byte_end] != fragment_bytes
    ):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "byte_span_mismatch",
            "The stored UTF-8 byte coordinates do not match the source slice.",
        )

    if (line_start, line_end) != _line_span_for_chars(source_text, char_start, char_end):
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "line_span_mismatch",
            "The stored line coordinates do not match the source slice.",
        )

    actual_node_hash = _digest_bytes(fragment_bytes)
    if actual_node_hash != node["content_hash"]:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "source_fragment_hash_mismatch",
            "The source fragment does not match the stored node Content Hash.",
        )
    if actual_node_hash != expected_hash:
        _raise(
            NodeLookupStatus.STALE_SOURCE,
            "expected_hash_mismatch",
            "The requested node version is no longer current.",
        )

    return NodeRecord(
        node_id=node["node_id"],
        content_hash=actual_node_hash,
        source_path=document["source_path"],
        node_type=node["node_type"],
        parent_node_id=parent_node_id,
        heading_path=tuple(heading_path),
        raw_text=source_fragment,
        line_start=line_start,
        line_end=line_end,
        char_start=char_start,
        char_end=char_end,
        byte_start=byte_start,
        byte_end=byte_end,
        source_sha256=actual_source_hash,
    )


def get_node_by_id(
    db_path: str | Path,
    node_id: str,
    expected_hash: str,
    vault_root: str | Path,
) -> NodeLookupResult:
    """Return an exact current source slice for a Node ID and expected Content Hash.

    db_path is explicit: the caller supplies the SQLite database restored by
    Persistence. The API does not use hidden package configuration or globals.

    vault_root must be the root of the specific Vault checkout whose indexed
    relative source paths are stored in documents.source_path (normally the
    repository's ГП directory, not the repository root).

    Every non-ok result has node=None. The successful raw_text comes from the
    current UTF-8 Markdown file after source, hash and coordinate verification.
    """
    if not _valid_node_id(node_id):
        return _failure(
            NodeLookupStatus.INVALID_REQUEST,
            "node_id_invalid",
            "Node ID must have the canonical node_<UUID4> format.",
        )
    if not _valid_hash(expected_hash):
        return _failure(
            NodeLookupStatus.INVALID_REQUEST,
            "expected_hash_invalid",
            "Expected Hash must have the sha256:<64 lowercase hex> format.",
        )

    try:
        canonical_root = Path(vault_root).expanduser().resolve(strict=True)
    except (OSError, TypeError, ValueError, RuntimeError):
        return _failure(
            NodeLookupStatus.INVALID_REQUEST,
            "vault_root_invalid",
            "Vault root must identify an existing directory.",
        )
    if not canonical_root.is_dir():
        return _failure(
            NodeLookupStatus.INVALID_REQUEST,
            "vault_root_invalid",
            "Vault root must identify an existing directory.",
        )

    connection: sqlite3.Connection | None = None
    try:
        connection = _read_only_connection(db_path)
        _verify_database(connection)
        try:
            matches = connection.execute(
                """SELECT n.*,
                          d.source_path AS document_source_path,
                          d.source_sha256 AS document_source_sha256,
                          d.source_size_bytes AS document_source_size_bytes,
                          d.status AS document_status,
                          d.generation AS document_generation,
                          d.document_pk AS joined_document_pk
                   FROM structural_nodes AS n
                   JOIN documents AS d ON d.document_pk = n.document_pk
                   WHERE n.node_id = ?""",
                (node_id,),
            ).fetchall()
        except sqlite3.Error:
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "node_lookup_failed",
                "The requested node record could not be read from SQLite.",
            )

        if not matches:
            return _failure(
                NodeLookupStatus.NOT_FOUND,
                "node_not_found",
                "No structural node has the requested Node ID.",
            )
        if len(matches) != 1:
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "node_id_not_unique",
                "The requested Node ID does not identify exactly one record.",
            )

        node = dict(matches[0])
        document = {
            "document_pk": node["joined_document_pk"],
            "source_path": node["document_source_path"],
            "source_sha256": node["document_source_sha256"],
            "source_size_bytes": node["document_source_size_bytes"],
            "status": node["document_status"],
            "generation": node["document_generation"],
        }
        if (
            not _is_int(node["node_pk"])
            or not _is_int(node["document_pk"])
            or node["document_pk"] != document["document_pk"]
        ):
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "node_document_reference_invalid",
                "The stored node-to-document reference is inconsistent.",
            )

        # Path syntax is checked before any status is returned. It is DB-only.
        components = _safe_source_components(document["source_path"])
        if (
            not _valid_hash(document["source_sha256"])
            or not _is_int(document["source_size_bytes"])
            or document["source_size_bytes"] < 0
            or not _is_int(document["generation"])
            or document["generation"] < 1
        ):
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "document_record_invalid",
                "The stored document record is inconsistent.",
            )

        events = _validate_events(
            connection,
            int(document["document_pk"]),
            int(document["generation"]),
        )
        heading_path, parent_node_id, latest_event = _check_db_snapshot(
            connection, node, document, events
        )

        # All DB-only checks precede deleted/ambiguous resolution. These paths
        # return without opening the source Markdown file.
        db_status = _resolve_db_status(node, document, latest_event)
        if db_status is not None:
            details = {
                NodeLookupStatus.DELETED: (
                    "node_deleted",
                    "The requested node address has been deleted.",
                ),
                NodeLookupStatus.AMBIGUOUS: (
                    "node_ambiguous",
                    "The requested node address is ambiguous.",
                ),
            }[db_status]
            return _failure(db_status, details[0], details[1])

        record = _read_and_verify_node(
            node=node,
            document=document,
            parent_node_id=parent_node_id,
            heading_path=heading_path,
            canonical_root=canonical_root,
            components=components,
            expected_hash=expected_hash,
        )
        return NodeLookupResult(status=NodeLookupStatus.OK, node=record)

    except _LookupFailure as exc:
        return _failure(exc.status, exc.code, exc.safe_message)
    except Exception:
        # Do not copy internal exception details: they may expose local paths.
        return _failure(
            NodeLookupStatus.INTEGRITY_ERROR,
            "lookup_integrity_failure",
            "The source node could not be verified safely.",
        )
    finally:
        if connection is not None:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
            connection.close()


__all__ = [
    "NodeLookupResult",
    "NodeLookupStatus",
    "NodeRecord",
    "get_node_by_id",
]
