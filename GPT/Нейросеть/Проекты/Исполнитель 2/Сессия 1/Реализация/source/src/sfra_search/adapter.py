"""Input adapter for SFRA structural nodes (Node v1 + batch manifest)."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any, Iterable

HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ImportValidationError(ValueError):
    """Raised when an incoming node or batch manifest violates the contract."""


def calculate_content_hash(raw_text: str) -> str:
    """SHA-256 over the exact UTF-8 bytes of raw_text, without normalization."""
    return "sha256:" + hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def validate_source_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ImportValidationError("source_path must be a non-empty string")
    if "\\" in value:
        raise ImportValidationError("source_path must use POSIX '/' separators")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts) or path.as_posix() != value:
        raise ImportValidationError("source_path must be a normalized relative POSIX path without '.' or '..'")
    return value


def validate_node(node: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(node, dict):
        raise ImportValidationError("Each JSONL row must be an object")
    required = ("node_id", "source_path", "node_type", "heading_path", "line_start", "line_end", "content_hash", "raw_text")
    missing = [key for key in required if key not in node]
    if missing:
        raise ImportValidationError(f"Missing required fields: {', '.join(missing)}")

    node_id = node["node_id"]
    if not isinstance(node_id, str) or not node_id.strip():
        raise ImportValidationError("node_id must be a non-empty string")
    if node_id != node_id.strip():
        raise ImportValidationError("node_id must not contain leading or trailing whitespace")
    source_path = validate_source_path(node["source_path"])
    node_type = node["node_type"]
    if not isinstance(node_type, str) or not node_type.strip():
        raise ImportValidationError("node_type must be a non-empty string")
    parent = node.get("parent_node_id")
    if parent is not None and (not isinstance(parent, str) or not parent.strip()):
        raise ImportValidationError("parent_node_id must be null or a non-empty string")
    heading_path = node["heading_path"]
    if not isinstance(heading_path, list) or any(not isinstance(x, str) for x in heading_path):
        raise ImportValidationError("heading_path must be an array of strings")
    for key in ("line_start", "line_end"):
        if isinstance(node[key], bool) or not isinstance(node[key], int) or node[key] < 1:
            raise ImportValidationError(f"{key} must be a positive 1-based integer")
    if node["line_end"] < node["line_start"]:
        raise ImportValidationError("line_end must be greater than or equal to line_start")
    raw_text = node["raw_text"]
    if not isinstance(raw_text, str):
        raise ImportValidationError("raw_text must be a string")
    content_hash = node["content_hash"]
    if not isinstance(content_hash, str) or not HASH_RE.fullmatch(content_hash):
        raise ImportValidationError("content_hash must use sha256:<64 lowercase hex characters>")
    actual_hash = calculate_content_hash(raw_text)
    if content_hash != actual_hash:
        raise ImportValidationError("content_hash mismatch: expected SHA-256 of exact raw_text UTF-8 bytes")

    document_hash = node.get("document_hash")
    if document_hash is not None and (not isinstance(document_hash, str) or not HASH_RE.fullmatch(document_hash)):
        raise ImportValidationError("document_hash must be null or sha256:<64 lowercase hex characters>")

    # Return a normalized copy, retaining unknown extension fields for forward compatibility.
    clean = dict(node)
    # Keep the producer-issued identifier byte-for-byte; never mint or rewrite IDs.
    clean["node_id"] = node_id
    clean["source_path"] = source_path
    clean["node_type"] = node_type.strip()
    clean["parent_node_id"] = parent
    clean["heading_path"] = list(heading_path)
    return clean


def validate_manifest(manifest: dict[str, Any] | None) -> dict[str, Any]:
    manifest = manifest or {"schema": "sfra-node-batch/v1", "mode": "delta"}
    if not isinstance(manifest, dict):
        raise ImportValidationError("manifest must be an object")
    schema = manifest.get("schema", "sfra-node-batch/v1")
    if schema != "sfra-node-batch/v1":
        raise ImportValidationError(f"Unsupported manifest schema: {schema}")
    mode = manifest.get("mode", "delta")
    if mode not in ("delta", "replace_documents", "full_snapshot"):
        raise ImportValidationError(f"Unsupported import mode: {mode}")
    result = dict(manifest)
    result["schema"] = schema
    result["mode"] = mode
    paths_key = "managed_source_paths" if mode == "full_snapshot" else "replace_source_paths"
    paths = result.get(paths_key, [])
    if not isinstance(paths, list):
        raise ImportValidationError(f"{paths_key} must be an array")
    result[paths_key] = [validate_source_path(p) for p in paths]
    deleted = result.get("deleted_node_ids", [])
    if not isinstance(deleted, list) or any(not isinstance(x, str) or not x.strip() for x in deleted):
        raise ImportValidationError("deleted_node_ids must be an array of non-empty strings")
    result["deleted_node_ids"] = deleted
    return result


def parse_jsonl(text: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ImportValidationError(f"Invalid JSON on JSONL line {line_no}: {exc.msg}") from exc
        nodes.append(validate_node(row))
    return nodes


def load_jsonl(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return parse_jsonl(handle.read())
