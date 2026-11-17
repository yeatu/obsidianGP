from __future__ import annotations

from sfra_context_builder import SnapshotRef
from sfra_context_builder.dependencies import build_dependency_groups
from sfra_context_builder.integrity import content_hash
from sfra_context_builder.validation import parse_candidate
from conftest import make_candidate


class FakeResolver:
    def __init__(self, values):
        self.values = values
        self.seen_snapshot = None

    def resolve_node(self, node_id, snapshot):
        self.seen_snapshot = snapshot
        return self.values.get(node_id)


def candidate(raw):
    return parse_candidate(raw, original_order=0)


def test_required_chain_resolves_missing_node_in_pinned_snapshot():
    a = make_candidate("A", "node A", required_with=["B"])
    b = make_candidate("B", "node B", required_with=["C"])
    c = make_candidate("C", "node C")
    resolver = FakeResolver({"C": c})
    snapshot = SnapshotRef("1" * 40, "2" * 40, content_hash("manifest"))
    diagnostics = []
    groups, all_candidates, rejected = build_dependency_groups(
        [candidate(a), candidate(b)],
        resolver=resolver,
        snapshot=snapshot,
        verify_resolved_hash=lambda item: content_hash(item.raw_text) == item.content_hash,
        diagnostics=diagnostics,
    )
    assert len(groups) == 1
    assert {item.node_id for item in groups[0].members} == {"A", "B", "C"}
    assert groups[0].has_unresolved is False
    assert resolver.seen_snapshot == snapshot
    assert rejected == 0


def test_missing_dependency_marks_whole_group_unresolved():
    a = candidate(make_candidate("A", "A", required_with=["M"]))
    diagnostics = []
    groups, _, _ = build_dependency_groups(
        [a],
        resolver=None,
        snapshot=None,
        verify_resolved_hash=lambda item: True,
        diagnostics=diagnostics,
    )
    assert groups[0].unresolved_dependency_ids == ("M",)


def test_dependency_cycle_is_collapsed_once():
    a = candidate(make_candidate("A", "A", required_with=["B"]))
    b = candidate(make_candidate("B", "B", required_with=["A"]))
    diagnostics = []
    groups, _, _ = build_dependency_groups(
        [a, b],
        resolver=None,
        snapshot=None,
        verify_resolved_hash=lambda item: True,
        diagnostics=diagnostics,
    )
    assert len(groups) == 1
    assert groups[0].cycles == (("A", "B"),)
    assert sum(item["code"] == "required_dependency_cycle_collapsed" for item in diagnostics) == 1


def test_document_generation_mismatch_marks_dependency_unresolved():
    a = make_candidate("A", "A", source_path="same.md", required_with=["B"], index_generation=1)
    b = make_candidate("B", "B", source_path="same.md", index_generation=2)
    groups, _, _ = build_dependency_groups(
        [candidate(a), candidate(b)],
        resolver=None,
        snapshot=None,
        verify_resolved_hash=lambda item: True,
        diagnostics=[],
    )
    assert groups[0].has_unresolved
