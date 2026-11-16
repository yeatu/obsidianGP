"""Stable structural-node identities and conservative remapping."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .models import ParsedDocument, StructuralNode


def content_hash(raw_text: str) -> str:
    """SHA-256 over the exact UTF-8 source slice."""
    digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _heading_key(node_type: str, metadata: dict[str, Any]) -> tuple | None:
    if node_type != "heading":
        return None
    return ("heading", metadata.get("level"), metadata.get("title"))


def _old_metadata(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("metadata_json")
    if not value:
        return {}
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}


@dataclass(slots=True)
class MatchPlan:
    """Pure matching decision; persistence and UUID assignment happen elsewhere."""

    matches: dict[str, dict[str, Any]] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    ambiguous_candidates: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    new_local_keys: set[str] = field(default_factory=set)
    stale_old_pks: set[int] = field(default_factory=set)


def build_match_plan(old_nodes: list[dict[str, Any]],
                     document: ParsedDocument) -> MatchPlan:
    """Match new parse nodes to previous current nodes without guessing.

    Match order:
      1. the unique document root;
      2. unique (node_type, exact content_hash) pairs within the document;
      3. unique heading (level, exact title) pairs, independent of parent;
      4. a one-old / one-new sibling slot under an already matched parent.

    Remaining many-to-many groups are explicitly ambiguous. They never inherit
    an old node_id. Unmatched new nodes with no previous candidates are new.
    """
    plan = MatchPlan()
    new_nodes = list(document.iter_nodes())
    new_by_key = {node.local_key: node for node in new_nodes}
    old_by_pk = {int(row["node_pk"]): row for row in old_nodes}
    used_old: set[int] = set()

    def match(new_node: StructuralNode, old_row: dict[str, Any], reason: str) -> None:
        local_key = new_node.local_key
        old_pk = int(old_row["node_pk"])
        if local_key in plan.matches or old_pk in used_old:
            return
        plan.matches[local_key] = old_row
        plan.reasons[local_key] = reason
        used_old.add(old_pk)

    # The one document root is structurally fixed even when the file content
    # changes. It has its own Node ID and version stream.
    new_root = document.root
    old_roots = [row for row in old_nodes if row["node_type"] == "document"]
    if len(old_roots) == 1:
        match(new_root, old_roots[0], "document_root")

    # Unique exact content matches can survive a structural move. Repeated
    # identical fragments intentionally do not match here.
    old_hash_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    new_hash_groups: dict[tuple[str, str], list[StructuralNode]] = defaultdict(list)
    for row in old_nodes:
        if row["node_type"] == "document":
            continue
        hash_value = row.get("content_hash") or content_hash(row.get("raw_text") or "")
        old_hash_groups[(row["node_type"], hash_value)].append(row)
    for node in new_nodes:
        if node.node_type == "document":
            continue
        new_hash_groups[(node.node_type, content_hash(node.raw_text))].append(node)

    for key, new_group in new_hash_groups.items():
        old_group = old_hash_groups.get(key, [])
        if len(new_group) == 1 and len(old_group) == 1:
            match(new_group[0], old_group[0], "unique_content_hash")

    # A unique heading title and level form a useful anchor if the body changed
    # or the section moved to a different parent. Duplicate headings are unsafe.
    old_heading_groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    new_heading_groups: dict[tuple, list[StructuralNode]] = defaultdict(list)
    for row in old_nodes:
        key = _heading_key(row["node_type"], _old_metadata(row))
        if key and int(row["node_pk"]) not in used_old:
            old_heading_groups[key].append(row)
    for node in new_nodes:
        key = _heading_key(node.node_type, node.metadata)
        if key and node.local_key not in plan.matches:
            new_heading_groups[key].append(node)

    for key, new_group in new_heading_groups.items():
        old_group = old_heading_groups.get(key, [])
        if len(new_group) == 1 and len(old_group) == 1:
            match(new_group[0], old_group[0], "unique_heading_key")
        elif new_group and old_group:
            for node in new_group:
                plan.ambiguous_candidates[node.local_key] = list(old_group)

    # Walk from every already-matched parent. A unique sibling slot is safe
    # enough for a content edit; a many-to-many remainder is not.
    queue = deque(plan.matches.keys())
    processed_parents: set[str] = set()
    while queue:
        parent_key = queue.popleft()
        if parent_key in processed_parents or parent_key not in plan.matches:
            continue
        processed_parents.add(parent_key)
        old_parent = plan.matches[parent_key]
        old_parent_pk = int(old_parent["node_pk"])

        old_children: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in old_nodes:
            if row.get("parent_node_pk") == old_parent_pk and int(row["node_pk"]) not in used_old:
                old_children[row["node_type"]].append(row)

        new_children: dict[str, list[StructuralNode]] = defaultdict(list)
        for node in new_nodes:
            if node.parent_key == parent_key and node.local_key not in plan.matches:
                new_children[node.node_type].append(node)

        # Match unique same-title headings locally if their global title key
        # was duplicated elsewhere in the document but is unique in this parent.
        for node_type, new_group in list(new_children.items()):
            if node_type != "heading":
                continue
            old_group = old_children.get("heading", [])
            old_by_key: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
            new_by_key: dict[tuple, list[StructuralNode]] = defaultdict(list)
            for row in old_group:
                key = _heading_key("heading", _old_metadata(row))
                if key:
                    old_by_key[key].append(row)
            for child in new_group:
                key = _heading_key("heading", child.metadata)
                if key:
                    new_by_key[key].append(child)
            for key, nodes in new_by_key.items():
                candidates = old_by_key.get(key, [])
                if len(nodes) == 1 and len(candidates) == 1:
                    match(nodes[0], candidates[0], "unique_sibling_heading_key")
                    queue.append(nodes[0].local_key)
                elif nodes and candidates:
                    for child in nodes:
                        plan.ambiguous_candidates[child.local_key] = list(candidates)

        # Remaining non-heading node types: only a strict 1:1 slot match.
        all_types = set(old_children) | set(new_children)
        for node_type in sorted(all_types):
            if node_type == "heading":
                continue
            old_group = [row for row in old_children.get(node_type, [])
                         if int(row["node_pk"]) not in used_old]
            new_group = [node for node in new_children.get(node_type, [])
                         if node.local_key not in plan.matches]
            if len(old_group) == 1 and len(new_group) == 1:
                match(new_group[0], old_group[0], "unique_sibling_slot")
                queue.append(new_group[0].local_key)
            elif old_group and new_group:
                for node in new_group:
                    # If an earlier exact/heading decision already marked this
                    # node ambiguous, merge the candidate set without losing IDs.
                    existing = plan.ambiguous_candidates.get(node.local_key, [])
                    by_pk = {int(row["node_pk"]): row for row in [*existing, *old_group]}
                    plan.ambiguous_candidates[node.local_key] = list(by_pk.values())

        # A matched child that was identified globally may itself be the parent
        # of descendants, so enqueue all mapped direct children as well.
        for child in new_nodes:
            if child.parent_key == parent_key and child.local_key in plan.matches:
                queue.append(child.local_key)

    # Final states. A candidate list is an explicit warning, not permission to
    # reuse any of those previous IDs.
    for node in new_nodes:
        if node.local_key in plan.matches:
            continue
        candidates = plan.ambiguous_candidates.get(node.local_key, [])
        if candidates:
            plan.ambiguous_candidates[node.local_key] = candidates
        else:
            plan.new_local_keys.add(node.local_key)

    all_old_pks = set(old_by_pk)
    plan.stale_old_pks = all_old_pks - used_old
    return plan


__all__ = ["MatchPlan", "build_match_plan", "content_hash"]
