"""Deterministic fake matching E1's actual public dataclass to_dict() shape."""

from __future__ import annotations

import hashlib
from typing import Any

from sfra_context_builder.models import SnapshotRef


def sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def snapshot() -> SnapshotRef:
    return SnapshotRef("a" * 40, "b" * 40, "sha256:" + "c" * 64)


class FixtureTokenCounter:
    def count(self, text: str) -> int:
        return len(text.split())

    def metadata(self):
        return {
            "name": "fixture-whitespace",
            "version": "1",
            "encoding": "words",
            "exact_for_encoding": True,
            "exact_for_client_model": False,
        }


class FixtureE1ScopeAPI:
    """Fake E1 API. It returns native SourceScopeResult/CurrentNodeAddress dictionaries."""

    def __init__(self, expected_snapshot: SnapshotRef | None = None):
        self.expected_snapshot = expected_snapshot or snapshot()
        self.scope_calls = []
        self.resolve_calls = []
        self.document_text = (
            "# Test document\n"
            "Parent source fragment.\n"
            "Previous sibling source fragment.\n"
            "Target original source fragment.\n"
            "Next sibling source fragment.\n"
        )
        self.document_hash = sha(self.document_text)
        self.records: dict[str, dict[str, Any]] = {
            "node_target": {
                "node_id": "node_target",
                "content_hash": sha("Target original source fragment.\n"),
                "source_path": "fixtures/test-document.md",
                "node_type": "paragraph",
                "parent_node_id": "node_parent",
                "heading_path": ["Test document"],
                "line_start": 4,
                "line_end": 4,
                "char_start": 90,
                "char_end": 123,
                "byte_start": 90,
                "byte_end": 123,
                "raw_text": "Target original source fragment.\n",
                "source_sha256": self.document_hash,
                "document_hash": self.document_hash,
                "index_generation": 7,
                "metadata": {},
            },
            "node_parent": {
                "node_id": "node_parent",
                "content_hash": sha("Parent source fragment.\n"),
                "source_path": "fixtures/test-document.md",
                "node_type": "heading",
                "parent_node_id": None,
                "heading_path": ["Test document"],
                "line_start": 2,
                "line_end": 2,
                "char_start": 16,
                "char_end": 40,
                "byte_start": 16,
                "byte_end": 40,
                "raw_text": "Parent source fragment.\n",
                "source_sha256": self.document_hash,
                "document_hash": self.document_hash,
                "index_generation": 7,
                "metadata": {},
            },
            "node_previous": {
                "node_id": "node_previous",
                "content_hash": sha("Previous sibling source fragment.\n"),
                "source_path": "fixtures/test-document.md",
                "node_type": "paragraph",
                "parent_node_id": "node_parent",
                "heading_path": ["Test document"],
                "line_start": 3,
                "line_end": 3,
                "char_start": 40,
                "char_end": 77,
                "byte_start": 40,
                "byte_end": 77,
                "raw_text": "Previous sibling source fragment.\n",
                "source_sha256": self.document_hash,
                "document_hash": self.document_hash,
                "index_generation": 7,
                "metadata": {},
            },
            "node_next": {
                "node_id": "node_next",
                "content_hash": sha("Next sibling source fragment.\n"),
                "source_path": "fixtures/test-document.md",
                "node_type": "paragraph",
                "parent_node_id": "node_parent",
                "heading_path": ["Test document"],
                "line_start": 5,
                "line_end": 5,
                "char_start": 123,
                "char_end": 157,
                "byte_start": 123,
                "byte_end": 157,
                "raw_text": "Next sibling source fragment.\n",
                "source_sha256": self.document_hash,
                "document_hash": self.document_hash,
                "index_generation": 7,
                "metadata": {},
            },
        }
        self.sibling_ids = {
            "node_target": ("node_previous", "node_next"),
            "node_previous": (None, "node_target"),
            "node_next": ("node_target", None),
        }
        self.status_overrides: dict[str, str] = {}

    def _error_scope(self, node_id: str, scope: str, snapshot_id: str, status: str):
        return {
            "snapshot_id": snapshot_id,
            "scope": scope,
            "status": status,
            "fragments": [],
            "anchor": None,
            "parent": None,
            "previous": None,
            "next": None,
            "document": None,
            "error": {"code": status, "message": status},
        }

    def resolve_current_node(self, db_path, node_id, *, snapshot_id):
        self.resolve_calls.append((db_path, node_id, snapshot_id))
        if snapshot_id != self.expected_snapshot.snapshot_id:
            return {
                "snapshot_id": self.expected_snapshot.snapshot_id,
                "status": "integrity_error",
                "node_id": None,
                "content_hash": None,
                "source_path": None,
                "document_hash": None,
                "index_generation": None,
                "error": {"code": "snapshot_mismatch"},
            }
        status = self.status_overrides.get(node_id)
        if status:
            return {
                "snapshot_id": snapshot_id,
                "status": status,
                "node_id": None,
                "content_hash": None,
                "source_path": None,
                "document_hash": None,
                "index_generation": None,
                "error": {"code": status},
            }
        record = self.records.get(node_id)
        if record is None:
            return {
                "snapshot_id": snapshot_id,
                "status": "not_found",
                "node_id": None,
                "content_hash": None,
                "source_path": None,
                "document_hash": None,
                "index_generation": None,
                "error": {"code": "node_not_found"},
            }
        return {
            "snapshot_id": snapshot_id,
            "status": "ok",
            "node_id": record["node_id"],
            "content_hash": record["content_hash"],
            "source_path": record["source_path"],
            "document_hash": record["document_hash"],
            "index_generation": record["index_generation"],
        }

    def read_source_scope(
        self,
        db_path,
        vault_root,
        node_id,
        expected_hash,
        *,
        scope,
        snapshot_id,
    ):
        self.scope_calls.append((
            db_path, vault_root, node_id, expected_hash, scope, snapshot_id
        ))
        if snapshot_id != self.expected_snapshot.snapshot_id:
            return self._error_scope(node_id, scope, self.expected_snapshot.snapshot_id, "integrity_error")
        status = self.status_overrides.get(node_id)
        if status:
            return self._error_scope(node_id, scope, snapshot_id, status)
        target = self.records.get(node_id)
        if target is None:
            return self._error_scope(node_id, scope, snapshot_id, "not_found")
        if target["content_hash"] != expected_hash:
            return self._error_scope(node_id, scope, snapshot_id, "stale_source")
        if scope != "node" and target["document_hash"] is None:
            return self._error_scope(node_id, scope, snapshot_id, "integrity_error")

        parent = None
        previous = None
        following = None
        document = None
        if scope == "parent":
            parent_id = target["parent_node_id"]
            parent = self.records.get(parent_id) if parent_id is not None else None
        elif scope == "neighbors":
            previous_id, next_id = self.sibling_ids.get(node_id, (None, None))
            previous = self.records.get(previous_id) if previous_id else None
            following = self.records.get(next_id) if next_id else None
        elif scope == "document":
            document = {
                "source_path": target["source_path"],
                "source_sha256": self.document_hash,
                "size_bytes": len(self.document_text.encode("utf-8")),
                "raw_text": self.document_text,
                "document_hash": self.document_hash,
                "index_generation": target["index_generation"],
                "anchor_node_id": target["node_id"],
                "anchor_content_hash": target["content_hash"],
            }
        elif scope != "node":
            return self._error_scope(node_id, scope, snapshot_id, "invalid_request")

        if scope == "node":
            fragments = [dict(target)]
        elif scope == "parent":
            fragments = [dict(target)] + ([dict(parent)] if parent is not None else [])
        elif scope == "neighbors":
            fragments = (
                [dict(target)]
                + ([dict(previous)] if previous is not None else [])
                + ([dict(following)] if following is not None else [])
            )
        else:
            fragments = []

        return {
            "snapshot_id": snapshot_id,
            "scope": scope,
            "status": "ok",
            "fragments": fragments,
            "anchor": dict(target),
            "parent": dict(parent) if parent is not None else None,
            "previous": dict(previous) if previous is not None else None,
            "next": dict(following) if following is not None else None,
            "document": document,
        }
