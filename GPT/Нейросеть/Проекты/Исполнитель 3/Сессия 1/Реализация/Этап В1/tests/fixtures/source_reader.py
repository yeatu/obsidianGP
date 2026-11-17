"""Deterministic fake of the agreed public E1 API. No SQL or Markdown parsing."""

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
    """Fake public E1 read_source_scope/resolve_current_node implementation."""

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
                "raw_text": "Target original source fragment.\n",
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
                "raw_text": "Parent source fragment.\n",
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
                "raw_text": "Previous sibling source fragment.\n",
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
                "raw_text": "Next sibling source fragment.\n",
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

    @staticmethod
    def _fragment(node: dict[str, Any], role: str) -> dict[str, Any]:
        return {
            "role": role,
            "node_id": node["node_id"],
            "source_path": node["source_path"],
            "node_type": node["node_type"],
            "parent_node_id": node["parent_node_id"],
            "heading_path": list(node["heading_path"]),
            "line_start": node["line_start"],
            "line_end": node["line_end"],
            "content_hash": node["content_hash"],
            "raw_text": node["raw_text"],
            "document_hash": node["document_hash"],
            "index_generation": node["index_generation"],
        }

    def resolve_current_node(self, db_path, node_id, *, snapshot_id):
        self.resolve_calls.append((db_path, node_id, snapshot_id))
        if snapshot_id != self.expected_snapshot.snapshot_id:
            return {
                "status": "integrity_error",
                "snapshot_id": self.expected_snapshot.snapshot_id,
                "address": None,
                "error": {"code": "snapshot_mismatch"},
            }
        status = self.status_overrides.get(node_id)
        if status:
            return {
                "status": status,
                "snapshot_id": snapshot_id,
                "address": None,
                "error": {"code": status},
            }
        record = self.records.get(node_id)
        if record is None:
            return {
                "status": "not_found",
                "snapshot_id": snapshot_id,
                "address": None,
                "error": {"code": "node_not_found"},
            }
        address = {key: value for key, value in record.items() if key != "raw_text"}
        return {"status": "ok", "snapshot_id": snapshot_id, "address": address}

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
        self.scope_calls.append((db_path, vault_root, node_id, expected_hash, scope, snapshot_id))
        if snapshot_id != self.expected_snapshot.snapshot_id:
            return {
                "status": "integrity_error",
                "snapshot_id": self.expected_snapshot.snapshot_id,
                "target_source": None,
                "fragments": [],
                "diagnostics": [{"code": "snapshot_mismatch"}],
            }
        status = self.status_overrides.get(node_id)
        if status:
            return {
                "status": status,
                "snapshot_id": snapshot_id,
                "target_source": None,
                "fragments": [],
                "diagnostics": [{"code": status}],
            }
        target = self.records.get(node_id)
        if target is None:
            return {
                "status": "not_found",
                "snapshot_id": snapshot_id,
                "target_source": None,
                "fragments": [],
                "diagnostics": [{"code": "node_not_found"}],
            }
        if target["content_hash"] != expected_hash:
            return {
                "status": "stale_source",
                "snapshot_id": snapshot_id,
                "target_source": None,
                "fragments": [],
                "diagnostics": [{"code": "expected_hash_mismatch"}],
            }

        target_source = {key: value for key, value in target.items() if key != "raw_text"}
        if scope == "node":
            fragments = [self._fragment(target, "target")]
        elif scope == "parent":
            fragments = [self._fragment(target, "target")]
            parent_id = target["parent_node_id"]
            if parent_id is not None and parent_id in self.records:
                fragments.append(self._fragment(self.records[parent_id], "parent_context"))
            elif parent_id is None:
                pass
        elif scope == "neighbors":
            fragments = [self._fragment(target, "target")]
            previous_id, next_id = self.sibling_ids.get(node_id, (None, None))
            if previous_id is not None:
                fragments.append(self._fragment(self.records[previous_id], "previous_neighbor"))
            if next_id is not None:
                fragments.append(self._fragment(self.records[next_id], "next_neighbor"))
        elif scope == "document":
            fragments = [{
                "role": "document",
                "node_id": None,
                "source_path": target["source_path"],
                "node_type": "document",
                "parent_node_id": None,
                "heading_path": [],
                "line_start": 1,
                "line_end": self.document_text.count("\n"),
                "content_hash": self.document_hash,
                "raw_text": self.document_text,
                "document_hash": self.document_hash,
                "index_generation": target["index_generation"],
            }]
        else:
            return {
                "status": "invalid_request",
                "snapshot_id": snapshot_id,
                "target_source": None,
                "fragments": [],
                "diagnostics": [{"code": "unsupported_scope"}],
            }

        if scope != "node" and target["document_hash"] is None:
            return {
                "status": "integrity_error",
                "snapshot_id": snapshot_id,
                "target_source": None,
                "fragments": [],
                "diagnostics": [{"code": "document_hash_unavailable"}],
            }
        diagnostics = []
        if scope == "parent" and target["parent_node_id"] is None:
            diagnostics.append({"code": "parent_not_present"})

        return {
            "status": "ok",
            "snapshot_id": snapshot_id,
            "requested": {
                "node_id": node_id,
                "expected_hash": expected_hash,
                "scope": scope,
            },
            "target_source": target_source,
            "fragments": fragments,
            "diagnostics": diagnostics,
        }
