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
    """A current structural node fragment verified against its source document."""

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
    document_hash: str
    index_generation: int
    metadata: dict[str, Any]

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
    """Validate every event's exact schema as emitted by storage.py."""
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

    reused_event_types = {
        "document_root",
        "unique_content_hash",
        "unique_heading_key",
        "unique_sibling_heading_key",
        "unique_sibling_slot",
    }
    stale_event_types = {
        "stale",
        "stale_ambiguous_candidate",
        "document_deleted",
    }
    valid_node_types = {
        "document",
        "heading",
        "paragraph",
        "list",
        "list_item",
        "quote",
        "callout",
        "table",
        "code_block",
        "html_block",
        "thematic_break",
    }

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
            or not isinstance(event_type, str)
            or event_type not in _EVENT_TYPES
            or not _valid_node_id(node_id)
        ):
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "match_event_type_unknown",
                "The node matching history contains an unknown or inconsistent event.",
            )

        local_key = row["new_local_key"]
        if local_key is not None and (
            not isinstance(local_key, str) or not local_key.strip()
        ):
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "match_event_payload_invalid",
                "The node matching history contains an invalid local node key.",
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
            or not all(isinstance(key, str) for key in details)
        ):
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "match_event_payload_invalid",
                "The node matching history contains an invalid event payload.",
            )

        if event_type in reused_event_types:
            valid_details = (
                set(details) == {"node_type", "reason"}
                and isinstance(details["node_type"], str)
                and details["node_type"] in valid_node_types
                and details["reason"] == event_type
                and isinstance(local_key, str)
                and bool(local_key.strip())
                and not candidates
            )
        elif event_type in {"new", "ambiguous"}:
            valid_details = (
                set(details) == {"node_type", "reason"}
                and isinstance(details["node_type"], str)
                and details["node_type"] in valid_node_types
                and details["reason"] is None
                and isinstance(local_key, str)
                and bool(local_key.strip())
                and (
                    (event_type == "ambiguous" and bool(candidates))
                    or (event_type == "new" and not candidates)
                )
            )
        elif event_type in stale_event_types:
            valid_details = (
                set(details) == {"old_local_key"}
                and isinstance(details["old_local_key"], str)
                and bool(details["old_local_key"].strip())
                and local_key is None
                and not candidates
            )
        else:
            valid_details = False

        if not valid_details:
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "match_event_payload_invalid",
                "The node matching history contains a payload inconsistent with its event type.",
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


def _verify_document_bytes(document: dict[str, Any], source_bytes: bytes) -> str:
    """Verify one whole Markdown file and return its strict UTF-8 text."""
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
    actual_hash = _digest_bytes(source_bytes)
    if actual_hash != document["source_sha256"]:
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
        return source_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "source_encoding_invalid",
            "The indexed source file is not valid UTF-8.",
        )


def _verify_node_from_source(
    *,
    node: dict[str, Any],
    document: dict[str, Any],
    parent_node_id: str | None,
    heading_path: list[str],
    metadata: dict[str, Any],
    source_bytes: bytes,
    source_text: str,
    expected_hash: str,
) -> NodeRecord:
    """Build one NodeRecord from an already verified shared source-file read."""
    if not _valid_hash(expected_hash):
        _raise(
            NodeLookupStatus.INVALID_REQUEST,
            "expected_hash_invalid",
            "Expected Hash must have the sha256:<64 lowercase hex> format.",
        )
    if expected_hash != node["content_hash"]:
        _raise(
            NodeLookupStatus.STALE_SOURCE,
            "expected_hash_mismatch",
            "The requested node Hash does not identify the current indexed version.",
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

    # Python offsets count Unicode code points; UTF-8 offsets are computed independently.
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
    if (line_start, line_end) != _line_span_for_chars(
        source_text, char_start, char_end
    ):
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

    document_hash = document["source_sha256"]
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
        source_sha256=document_hash,
        document_hash=document_hash,
        index_generation=document["generation"],
        metadata=metadata,
    )


def _load_node_snapshot(
    connection: sqlite3.Connection,
    node_id: str,
    *,
    expected_document_pk: int | None = None,
) -> dict[str, Any]:
    """Load and validate one current node entirely inside the caller's transaction."""
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
        _raise(
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
    if expected_document_pk is not None and document["document_pk"] != expected_document_pk:
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "cross_document_relation",
            "A related node does not belong to the target document.",
        )

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
    db_status = _resolve_db_status(node, document, latest_event)
    if db_status is not None:
        details = {
            NodeLookupStatus.DELETED: (
                "node_deleted",
                "The requested node address is deleted or stale.",
            ),
            NodeLookupStatus.AMBIGUOUS: (
                "node_ambiguous",
                "The requested node address is ambiguous.",
            ),
        }[db_status]
        _raise(db_status, details[0], details[1])

    if document["status"] != "active" or node["status"] != "active":
        _raise(
            NodeLookupStatus.INTEGRITY_ERROR,
            "active_state_mismatch",
            "The node and document do not have an active lifecycle state.",
        )

    metadata = _decode_json(
        node["metadata_json"],
        dict,
        "node_metadata_invalid",
        "The stored node metadata is invalid.",
    )
    return {
        "node": node,
        "document": document,
        "components": components,
        "heading_path": heading_path,
        "parent_node_id": parent_node_id,
        "metadata": metadata,
    }


def _scope_error(
    snapshot_id: str,
    scope: str,
    status: NodeLookupStatus,
    code: str,
    message: str,
) -> "SourceScopeResult":
    return SourceScopeResult(
        snapshot_id=snapshot_id,
        scope=scope,
        status=status,
        fragments=(),
        anchor=None,
        parent=None,
        previous=None,
        next=None,
        document=None,
        error_code=code,
        message=message,
    )


def _current_scope_fragment(
    loaded: dict[str, Any],
    source_bytes: bytes,
    source_text: str,
    expected_hash: str,
) -> NodeRecord:
    return _verify_node_from_source(
        node=loaded["node"],
        document=loaded["document"],
        parent_node_id=loaded["parent_node_id"],
        heading_path=loaded["heading_path"],
        metadata=loaded["metadata"],
        source_bytes=source_bytes,
        source_text=source_text,
        expected_hash=expected_hash,
    )


def read_source_scope(
    db_path: str | Path,
    vault_root: str | Path,
    node_id: str,
    expected_hash: str,
    *,
    scope: str,
    snapshot_id: str,
) -> "SourceScopeResult":
    """Read a source scope through one SQLite read transaction and one source-file read.

    snapshot_id is opaque to E1: it is carried through unchanged and is not a
    claim that E1 verified Git refs, commits, manifests, or snapshot identity.
    """
    if not isinstance(scope, str) or scope not in {"node", "parent", "neighbors", "document"}:
        return _scope_error(
            snapshot_id, str(scope), NodeLookupStatus.INVALID_REQUEST,
            "scope_invalid", "Scope must be one of: node, parent, neighbors, document.",
        )
    if not _valid_node_id(node_id):
        return _scope_error(
            snapshot_id, scope, NodeLookupStatus.INVALID_REQUEST,
            "node_id_invalid", "Node ID must have the canonical node_<UUID4> format.",
        )
    if not _valid_hash(expected_hash):
        return _scope_error(
            snapshot_id, scope, NodeLookupStatus.INVALID_REQUEST,
            "expected_hash_invalid",
            "Expected Hash must have the sha256:<64 lowercase hex> format.",
        )
    try:
        canonical_root = Path(vault_root).expanduser().resolve(strict=True)
    except (OSError, TypeError, ValueError, RuntimeError):
        return _scope_error(
            snapshot_id, scope, NodeLookupStatus.INVALID_REQUEST,
            "vault_root_invalid", "Vault root must identify an existing directory.",
        )
    if not canonical_root.is_dir():
        return _scope_error(
            snapshot_id, scope, NodeLookupStatus.INVALID_REQUEST,
            "vault_root_invalid", "Vault root must identify an existing directory.",
        )

    connection: sqlite3.Connection | None = None
    try:
        # This is the one connection and one read transaction for the entire scope.
        connection = _read_only_connection(db_path)
        if not connection.in_transaction:
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "read_transaction_missing",
                "The source-scope lookup could not establish a read transaction.",
            )
        _verify_database(connection)

        target = _load_node_snapshot(connection, node_id)
        target_document = target["document"]
        target_document_pk = target_document["document_pk"]

        parent_loaded: dict[str, Any] | None = None
        previous_loaded: dict[str, Any] | None = None
        next_loaded: dict[str, Any] | None = None

        if scope == "parent" and target["parent_node_id"] is not None:
            parent_loaded = _load_node_snapshot(
                connection,
                target["parent_node_id"],
                expected_document_pk=target_document_pk,
            )
            if (
                parent_loaded["document"]["generation"] != target_document["generation"]
                or parent_loaded["document"]["source_path"] != target_document["source_path"]
                or parent_loaded["document"]["source_sha256"] != target_document["source_sha256"]
            ):
                _raise(
                    NodeLookupStatus.INTEGRITY_ERROR,
                    "parent_generation_mismatch",
                    "The parent and target do not belong to the same document generation.",
                )

        if scope == "neighbors":
            try:
                sibling_rows = connection.execute(
                    """SELECT node_pk, node_id, parent_node_pk, char_start, char_end,
                              status, stale_generation, document_pk
                       FROM structural_nodes
                       WHERE document_pk = ?
                         AND parent_node_pk IS ?
                         AND stale_generation IS NULL
                       ORDER BY char_start, char_end, node_pk""",
                    (target_document_pk, target["node"]["parent_node_pk"]),
                ).fetchall()
            except sqlite3.Error:
                _raise(
                    NodeLookupStatus.INTEGRITY_ERROR,
                    "sibling_query_failed",
                    "The current sibling sequence could not be read.",
                )

            siblings = [dict(row) for row in sibling_rows]
            target_positions = [
                index for index, row in enumerate(siblings)
                if row["node_id"] == node_id
            ]
            if len(target_positions) != 1:
                _raise(
                    NodeLookupStatus.INTEGRITY_ERROR,
                    "sibling_address_missing",
                    "The active target is not unique in its current sibling sequence.",
                )
            for row in siblings:
                if (
                    row["document_pk"] != target_document_pk
                    or row["parent_node_pk"] != target["node"]["parent_node_pk"]
                    or not _valid_node_id(row["node_id"])
                    or not _is_int(row["char_start"])
                    or not _is_int(row["char_end"])
                ):
                    _raise(
                        NodeLookupStatus.INTEGRITY_ERROR,
                        "sibling_state_invalid",
                        "A current sibling has inconsistent document, parent, or coordinates.",
                    )

            position = target_positions[0]
            previous_row = siblings[position - 1] if position > 0 else None
            following_row = siblings[position + 1] if position + 1 < len(siblings) else None
            if previous_row is not None:
                previous_loaded = _load_node_snapshot(
                    connection, previous_row["node_id"],
                    expected_document_pk=target_document_pk,
                )
            if following_row is not None:
                next_loaded = _load_node_snapshot(
                    connection, following_row["node_id"],
                    expected_document_pk=target_document_pk,
                )
            for related in (previous_loaded, next_loaded):
                if related is not None and (
                    related["document"]["generation"] != target_document["generation"]
                    or related["document"]["source_path"] != target_document["source_path"]
                    or related["document"]["source_sha256"] != target_document["source_sha256"]
                ):
                    _raise(
                        NodeLookupStatus.INTEGRITY_ERROR,
                        "sibling_document_binding_mismatch",
                        "A neighboring node is not bound to the target document snapshot.",
                    )

        # One safe read of the original file is shared by every returned fragment.
        source_bytes = _read_source_file(canonical_root, target["components"])
        source_text = _verify_document_bytes(target_document, source_bytes)

        target_record = _current_scope_fragment(
            target, source_bytes, source_text, expected_hash
        )
        parent_record = (
            _current_scope_fragment(
                parent_loaded, source_bytes, source_text,
                parent_loaded["node"]["content_hash"],
            )
            if parent_loaded is not None else None
        )
        previous_record = (
            _current_scope_fragment(
                previous_loaded, source_bytes, source_text,
                previous_loaded["node"]["content_hash"],
            )
            if previous_loaded is not None else None
        )
        next_record = (
            _current_scope_fragment(
                next_loaded, source_bytes, source_text,
                next_loaded["node"]["content_hash"],
            )
            if next_loaded is not None else None
        )

        document_record = None
        if scope == "node":
            fragments = (target_record,)
        elif scope == "parent":
            fragments = (
                (target_record, parent_record)
                if parent_record is not None else (target_record,)
            )
        elif scope == "neighbors":
            # Keep the fragment sequence in original document order.
            fragments = tuple(
                item for item in (previous_record, target_record, next_record)
                if item is not None
            )
        else:
            fragments = ()
            document_record = DocumentRecord(
                source_path=target_document["source_path"],
                source_sha256=target_document["source_sha256"],
                size_bytes=len(source_bytes),
                raw_text=source_text,
                document_hash=target_document["source_sha256"],
                index_generation=target_document["generation"],
                anchor_node_id=target_record.node_id,
                anchor_content_hash=target_record.content_hash,
            )

        return SourceScopeResult(
            snapshot_id=snapshot_id,
            scope=scope,
            status=NodeLookupStatus.OK,
            fragments=fragments,
            anchor=target_record,
            parent=parent_record,
            previous=previous_record,
            next=next_record,
            document=document_record,
        )
    except _LookupFailure as exc:
        return _scope_error(snapshot_id, scope, exc.status, exc.code, exc.safe_message)
    except Exception:
        return _scope_error(
            snapshot_id, scope, NodeLookupStatus.INTEGRITY_ERROR,
            "source_scope_integrity_failure",
            "The requested source scope could not be verified atomically.",
        )
    finally:
        if connection is not None:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
            connection.close()


@dataclass(frozen=True, slots=True)
class NodeParentResult:
    """Compatibility result for get_parent_by_id."""

    status: NodeLookupStatus
    node: NodeRecord | None = None
    parent: NodeRecord | None = None
    error_code: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": self.status.value,
            "node": self.node.to_dict() if self.node else None,
            "parent": self.parent.to_dict() if self.parent else None,
        }
        if self.error_code:
            result["error"] = {"code": self.error_code, "message": self.message}
        return result


@dataclass(frozen=True, slots=True)
class NodeNeighborsResult:
    """Compatibility result for get_neighbors_by_id."""

    status: NodeLookupStatus
    node: NodeRecord | None = None
    previous: NodeRecord | None = None
    next: NodeRecord | None = None
    error_code: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": self.status.value,
            "node": self.node.to_dict() if self.node else None,
            "previous": self.previous.to_dict() if self.previous else None,
            "next": self.next.to_dict() if self.next else None,
        }
        if self.error_code:
            result["error"] = {"code": self.error_code, "message": self.message}
        return result


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    """A complete original Markdown file read from the verified Vault checkout."""

    source_path: str
    source_sha256: str
    size_bytes: int
    raw_text: str
    document_hash: str
    index_generation: int
    anchor_node_id: str
    anchor_content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DocumentLookupResult:
    """Compatibility result for get_document_by_id."""

    status: NodeLookupStatus
    anchor: NodeRecord | None = None
    document: DocumentRecord | None = None
    error_code: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": self.status.value,
            "anchor": self.anchor.to_dict() if self.anchor else None,
            "document": self.document.to_dict() if self.document else None,
        }
        if self.error_code:
            result["error"] = {"code": self.error_code, "message": self.message}
        return result


@dataclass(frozen=True, slots=True)
class SourceScopeResult:
    """Atomic source-scope result; failures never carry partial source content."""

    snapshot_id: str
    scope: str
    status: NodeLookupStatus
    fragments: tuple[NodeRecord, ...] = ()
    anchor: NodeRecord | None = None
    parent: NodeRecord | None = None
    previous: NodeRecord | None = None
    next: NodeRecord | None = None
    document: DocumentRecord | None = None
    error_code: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.status is not NodeLookupStatus.OK:
            if (
                self.fragments or self.anchor is not None or self.parent is not None
                or self.previous is not None or self.next is not None
                or self.document is not None
            ):
                raise ValueError("Failed source-scope results must not contain partial data")
        elif self.anchor is None:
            raise ValueError("Successful source-scope results must include the verified anchor")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "snapshot_id": self.snapshot_id,
            "scope": self.scope,
            "status": self.status.value,
            "fragments": [item.to_dict() for item in self.fragments],
            "anchor": self.anchor.to_dict() if self.anchor else None,
            "parent": self.parent.to_dict() if self.parent else None,
            "previous": self.previous.to_dict() if self.previous else None,
            "next": self.next.to_dict() if self.next else None,
            "document": self.document.to_dict() if self.document else None,
        }
        if self.error_code:
            result["error"] = {"code": self.error_code, "message": self.message}
        return result


@dataclass(frozen=True, slots=True)
class CurrentNodeAddress:
    """DB-current address for E3; this is not a Git/snapshot attestation."""

    snapshot_id: str
    status: NodeLookupStatus
    node_id: str | None = None
    content_hash: str | None = None
    source_path: str | None = None
    document_hash: str | None = None
    index_generation: int | None = None
    error_code: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.status is NodeLookupStatus.OK:
            if any(value is None for value in (
                self.node_id, self.content_hash, self.source_path,
                self.document_hash, self.index_generation,
            )):
                raise ValueError("A current node address must contain complete metadata")
        elif any(value is not None for value in (
            self.node_id, self.content_hash, self.source_path,
            self.document_hash, self.index_generation,
        )):
            raise ValueError("A failed current-node resolution must not contain an address")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "snapshot_id": self.snapshot_id,
            "status": self.status.value,
            "node_id": self.node_id,
            "content_hash": self.content_hash,
            "source_path": self.source_path,
            "document_hash": self.document_hash,
            "index_generation": self.index_generation,
        }
        if self.error_code:
            result["error"] = {"code": self.error_code, "message": self.message}
        return result


def resolve_current_node(
    db_path: str | Path,
    node_id: str,
    *,
    snapshot_id: str,
) -> CurrentNodeAddress:
    """Resolve an active DB-current node; snapshot_id is opaque and echoed unchanged."""
    if not _valid_node_id(node_id):
        return CurrentNodeAddress(
            snapshot_id=snapshot_id,
            status=NodeLookupStatus.INVALID_REQUEST,
            error_code="node_id_invalid",
            message="Node ID must have the canonical node_<UUID4> format.",
        )

    connection: sqlite3.Connection | None = None
    try:
        connection = _read_only_connection(db_path)
        if not connection.in_transaction:
            _raise(
                NodeLookupStatus.INTEGRITY_ERROR,
                "read_transaction_missing",
                "The current-node lookup could not establish a read transaction.",
            )
        _verify_database(connection)
        loaded = _load_node_snapshot(connection, node_id)
        node = loaded["node"]
        document = loaded["document"]
        return CurrentNodeAddress(
            snapshot_id=snapshot_id,
            status=NodeLookupStatus.OK,
            node_id=node["node_id"],
            content_hash=node["content_hash"],
            source_path=document["source_path"],
            document_hash=document["source_sha256"],
            index_generation=document["generation"],
        )
    except _LookupFailure as exc:
        return CurrentNodeAddress(
            snapshot_id=snapshot_id,
            status=exc.status,
            error_code=exc.code,
            message=exc.safe_message,
        )
    except Exception:
        return CurrentNodeAddress(
            snapshot_id=snapshot_id,
            status=NodeLookupStatus.INTEGRITY_ERROR,
            error_code="current_node_integrity_failure",
            message="The current node address could not be verified safely.",
        )
    finally:
        if connection is not None:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
            connection.close()


def get_node_by_id(
    db_path: str | Path,
    node_id: str,
    expected_hash: str,
    vault_root: str | Path,
) -> NodeLookupResult:
    """Compatibility wrapper over read_source_scope(scope='node')."""
    result = read_source_scope(
        db_path, vault_root, node_id, expected_hash, scope="node", snapshot_id=""
    )
    if result.status is not NodeLookupStatus.OK:
        return _failure(result.status, result.error_code or "lookup_failed", result.message or "")
    return NodeLookupResult(status=NodeLookupStatus.OK, node=result.anchor)


def get_parent_by_id(
    db_path: str | Path,
    node_id: str,
    expected_hash: str,
    vault_root: str | Path,
) -> NodeParentResult:
    """Compatibility wrapper over read_source_scope(scope='parent')."""
    result = read_source_scope(
        db_path, vault_root, node_id, expected_hash, scope="parent", snapshot_id=""
    )
    if result.status is not NodeLookupStatus.OK:
        return NodeParentResult(
            status=result.status, error_code=result.error_code, message=result.message
        )
    return NodeParentResult(
        status=NodeLookupStatus.OK, node=result.anchor, parent=result.parent
    )


def get_neighbors_by_id(
    db_path: str | Path,
    node_id: str,
    expected_hash: str,
    vault_root: str | Path,
) -> NodeNeighborsResult:
    """Compatibility wrapper over read_source_scope(scope='neighbors')."""
    result = read_source_scope(
        db_path, vault_root, node_id, expected_hash, scope="neighbors", snapshot_id=""
    )
    if result.status is not NodeLookupStatus.OK:
        return NodeNeighborsResult(
            status=result.status, error_code=result.error_code, message=result.message
        )
    return NodeNeighborsResult(
        status=NodeLookupStatus.OK,
        node=result.anchor,
        previous=result.previous,
        next=result.next,
    )


def get_document_by_id(
    db_path: str | Path,
    node_id: str,
    expected_hash: str,
    vault_root: str | Path,
) -> DocumentLookupResult:
    """Compatibility wrapper over read_source_scope(scope='document')."""
    result = read_source_scope(
        db_path, vault_root, node_id, expected_hash, scope="document", snapshot_id=""
    )
    if result.status is not NodeLookupStatus.OK:
        return DocumentLookupResult(
            status=result.status, error_code=result.error_code, message=result.message
        )
    return DocumentLookupResult(
        status=NodeLookupStatus.OK,
        anchor=result.anchor,
        document=result.document,
    )


__all__ = [
    "CurrentNodeAddress",
    "DocumentLookupResult",
    "DocumentRecord",
    "NodeLookupResult",
    "NodeLookupStatus",
    "NodeRecord",
    "NodeNeighborsResult",
    "NodeParentResult",
    "SourceScopeResult",
    "get_document_by_id",
    "get_neighbors_by_id",
    "get_node_by_id",
    "get_parent_by_id",
    "read_source_scope",
    "resolve_current_node",
]
