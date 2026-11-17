"""Deterministic E1 source-scope fixture. It uses prebuilt records, not Markdown parsing."""

from __future__ import annotations

import hashlib
from typing import Any

from sfra_context_builder.models import SnapshotRef


def sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def snapshot() -> SnapshotRef:
    return SnapshotRef("a" * 40, "b" * 40, "sha256:" + "c" * 64)


class FixtureE1ScopeAPI:
    """Fake public E1 API with explicit precomputed parent/sibling/document records."""

    def __init__(self, expected_snapshot: SnapshotRef | None = None, *, token_counter=None):
        self.expected_snapshot = expected_snapshot or snapshot()
        self.token_counter = token_counter or (lambda text: len(text.split()))
        self.calls = []
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
            "heading_path": list(node["heading_path"]),
            "line_start": node["line_start"],
            "line_end": node["line_end"],
            "content_hash": node["content_hash"],
            "raw_text": node["raw_text"],
            "document_hash": node["document_hash"],
            "index_generation": node["index_generation"],
        }

    def read_scope(self, node_id, expected_hash, scope, budget_tokens, snapshot):
        self.calls.append((node_id, expected_hash, scope, budget_tokens, snapshot))
        target = self.records.get(node_id)
        if snapshot != self.expected_snapshot:
            return {
                "status": "integrity_error",
                "snapshot_id": self.expected_snapshot.snapshot_id,
                "target_source": None,
                "fragments": [],
                "diagnostics": [{"code": "snapshot_mismatch"}],
            }
        override = self.status_overrides.get(node_id)
        if override:
            return {
                "status": override,
                "snapshot_id": snapshot.snapshot_id,
                "target_source": None,
                "fragments": [],
                "diagnostics": [{"code": override}],
            }
        if target is None:
            return {
                "status": "not_found",
                "snapshot_id": snapshot.snapshot_id,
                "target_source": None,
                "fragments": [],
                "diagnostics": [{"code": "node_not_found"}],
            }
        if target["content_hash"] != expected_hash:
            return {
                "status": "stale_source",
                "snapshot_id": snapshot.snapshot_id,
                "target_source": None,
                "fragments": [],
                "diagnostics": [{"code": "expected_hash_mismatch"}],
            }

        target_source = {
            key: value for key, value in target.items()
            if key not in {"raw_text"}
        }
        if scope == "node":
            fragments = [self._fragment(target, "target")]
        elif scope == "parent":
            fragments = [self._fragment(target, "target")]
            parent_id = target["parent_node_id"]
            if parent_id is not None and parent_id in self.records:
                fragments.append(self._fragment(self.records[parent_id], "parent_context"))
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
                "snapshot_id": snapshot.snapshot_id,
                "target_source": None,
                "fragments": [],
                "diagnostics": [{"code": "unsupported_scope"}],
            }

        if scope != "node" and target["document_hash"] is None:
            return {
                "status": "integrity_error",
                "snapshot_id": snapshot.snapshot_id,
                "target_source": target_source,
                "fragments": [],
                "diagnostics": [{"code": "document_hash_unavailable"}],
            }

        tokens_used = sum(self.token_counter(item["raw_text"]) for item in fragments)
        if budget_tokens is not None and tokens_used > budget_tokens:
            return {
                "status": "budget_exceeded",
                "snapshot_id": snapshot.snapshot_id,
                "target_source": None,
                "fragments": [],
                "token_accounting": {
                    "budget_tokens": budget_tokens,
                    "tokens_used": tokens_used,
                },
                "diagnostics": [{"code": "scope_budget_exceeded"}],
            }

        return {
            "status": "ok",
            "snapshot_id": snapshot.snapshot_id,
            "requested": {
                "node_id": node_id,
                "expected_hash": expected_hash,
                "scope": scope,
                "budget_tokens": budget_tokens,
            },
            "target_source": target_source,
            "fragments": fragments,
            "token_accounting": {
                "budget_tokens": budget_tokens,
                "tokens_used": tokens_used,
            },
            "diagnostics": [],
        }
