from __future__ import annotations

from pathlib import Path
import json
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner


def test_canonical_corpus_passes_draft_2020_12_preflight():
    corpus, digest = runner.validate_corpus(
        runner.CORPUS_DIR / "corpus.v1.json",
        runner.CORPUS_DIR / "gold-case.schema.json",
    )
    assert digest == runner.CORPUS_DIGEST
    assert corpus["version"] == "1.0.0"
    assert len(corpus["cases"]) == 42
    assert sum(len(document["nodes"]) for document in corpus["documents"]) == 69


def test_sha256_uses_exact_utf8_bytes():
    assert runner.sha256_text("строка\n") == runner.sha256_bytes("строка\n".encode("utf-8"))
    assert runner.sha256_text("строка") != runner.sha256_text("строка\n")


def test_synthetic_fixture_node_ids_are_stable_and_purpose_scoped():
    first = runner._stable_synthetic_node_id("gold-node", "torch_location")
    repeated = runner._stable_synthetic_node_id("gold-node", "torch_location")

    assert first == repeated
    assert first.startswith("node_")
    assert first != runner._stable_synthetic_node_id("gold-node", "gate_rule")
    assert first != runner._stable_synthetic_node_id("not-found-source", "torch_location")


def test_synthetic_database_node_ids_and_references_are_canonicalized(tmp_path):
    database_path = tmp_path / "fixture.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE documents(
            document_pk INTEGER PRIMARY KEY, source_path TEXT NOT NULL,
            status TEXT NOT NULL
        );
        CREATE TABLE structural_nodes(
            node_pk INTEGER PRIMARY KEY, document_pk INTEGER NOT NULL,
            local_key TEXT NOT NULL, node_id TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            metadata_json TEXT NOT NULL, warnings_json TEXT NOT NULL,
            status TEXT NOT NULL
        );
        CREATE TABLE node_versions(
            node_version_pk INTEGER PRIMARY KEY, parent_node_id TEXT,
            metadata_json TEXT NOT NULL, warnings_json TEXT NOT NULL
        );
        CREATE TABLE node_match_events(
            event_pk INTEGER PRIMARY KEY, node_id TEXT,
            candidate_node_ids_json TEXT NOT NULL, details_json TEXT NOT NULL
        );
        INSERT INTO documents VALUES (1, 'synthetic/a.md', 'active');
        INSERT INTO documents VALUES (2, 'synthetic/b.md', 'active');
        INSERT INTO structural_nodes VALUES
            (1, 1, 'root', 'node_00000000-0000-4000-8000-000000000001',
             'sha256:1111111111111111111111111111111111111111111111111111111111111111',
             '{"required_with":["node_00000000-0000-4000-8000-000000000002"]}', '[]', 'active');
        INSERT INTO structural_nodes VALUES
            (2, 2, 'child', 'node_00000000-0000-4000-8000-000000000002',
             'sha256:2222222222222222222222222222222222222222222222222222222222222222',
             '{}', '[]', 'active');
        INSERT INTO node_versions VALUES
            (1, 'node_00000000-0000-4000-8000-000000000002',
             '{"parent":"node_00000000-0000-4000-8000-000000000001"}', '[]');
        INSERT INTO node_match_events VALUES
            (1, 'node_00000000-0000-4000-8000-000000000001',
             '["node_00000000-0000-4000-8000-000000000002"]', '{}');
        """
    )
    connection.commit()
    connection.close()

    mapping = runner._canonicalize_synthetic_node_ids(database_path)
    connection = sqlite3.connect(database_path)
    try:
        canonical_before_archive = {
            int(pk): node_id for pk, node_id in connection.execute(
                "SELECT node_pk, node_id FROM structural_nodes ORDER BY node_pk"
            )
        }
        assert set(canonical_before_archive) == {1, 2}
        # Model E1's second-pass tombstone archival: the parser local_key is
        # replaced after the source document disappears, but the existing
        # canonical Node ID and source-state markers must remain stable.
        connection.execute(
            "UPDATE structural_nodes SET local_key = ?, status = ? WHERE node_pk = 1",
            ("__deleted__1", "stale"),
        )
        connection.execute(
            "UPDATE documents SET status = ? WHERE document_pk = 1",
            ("deleted",),
        )
        # E1 uses a distinct tombstone key when a document is re-indexed and
        # an individual old node is archived rather than the whole document.
        connection.execute(
            "UPDATE structural_nodes SET local_key = ?, status = ? WHERE node_pk = 2",
            ("__archived__2", "stale"),
        )
        connection.commit()
    finally:
        connection.close()

    second_mapping = runner._canonicalize_synthetic_node_ids(database_path)
    third_mapping = runner._canonicalize_synthetic_node_ids(database_path)
    connection = sqlite3.connect(database_path)
    try:
        rows = connection.execute(
            """SELECT n.node_pk, n.node_id, n.local_key, n.status, d.status
               FROM structural_nodes AS n
               JOIN documents AS d ON d.document_pk = n.document_pk
               ORDER BY n.node_pk"""
        ).fetchall()
        ids = [row[1] for row in rows]
        assert ids == [
            canonical_before_archive[1],
            runner._stable_synthetic_node_id(
                "indexed-node",
                "synthetic/b.md\\nchild\\nsha256:2222222222222222222222222222222222222222222222222222222222222222",
            ),
        ]
        assert rows[0][2:] == ("__deleted__1", "stale", "deleted")
        assert rows[1][2:4] == ("__archived__2", "stale")
        assert second_mapping[canonical_before_archive[1]] == canonical_before_archive[1]
        assert third_mapping[canonical_before_archive[1]] == canonical_before_archive[1]
        assert second_mapping[canonical_before_archive[2]] == canonical_before_archive[2]
        assert third_mapping[canonical_before_archive[2]] == canonical_before_archive[2]
        assert list(second_mapping.values()) == list(third_mapping.values())
        parent = connection.execute(
            "SELECT parent_node_id, metadata_json FROM node_versions WHERE node_version_pk = 1"
        ).fetchone()
        assert parent[0] == ids[1]
        assert json.loads(parent[1]) == {"parent": ids[0]}
        metadata = connection.execute(
            "SELECT metadata_json FROM structural_nodes WHERE node_pk = 1"
        ).fetchone()[0]
        assert json.loads(metadata) == {"required_with": [ids[1]]}
        event = connection.execute(
            "SELECT node_id, candidate_node_ids_json FROM node_match_events WHERE event_pk = 1"
        ).fetchone()
        assert event[0] == ids[0]
        assert json.loads(event[1]) == [ids[1]]
    finally:
        connection.close()



def test_synthetic_node_identity_separates_reused_parser_key_by_content_hash():
    old_version = runner._stable_synthetic_node_id(
        "indexed-node", "synthetic/states/ambiguous-source.md\\nn000001\\nsha256:old"
    )
    new_version = runner._stable_synthetic_node_id(
        "indexed-node", "synthetic/states/ambiguous-source.md\\nn000001\\nsha256:new"
    )

    assert old_version != new_version

def test_metric_average_ignores_undefined_cases():
    assert runner._metric_average([0.5, None, 1.0]) == 0.75
    assert runner._metric_average([None, None]) is None

def test_standalone_source_read_failures_do_not_change_pack_completeness():
    for status in ("budget_exceeded", "ambiguous", "not_found"):
        assert runner._completeness_honesty(
            search_complete=True,
            context_status="complete",
            deferred=[],
        )
        status_match, non_ok_empty = runner._source_read_contract(
            actual_status=status,
            expected_status=status,
            fragments=[],
        )
        assert status_match is True
        assert non_ok_empty is True


def test_incomplete_search_and_deferred_budget_cannot_be_complete():
    assert not runner._completeness_honesty(
        search_complete=False,
        context_status="complete",
        deferred=[],
    )
    assert not runner._completeness_honesty(
        search_complete=True,
        context_status="complete",
        deferred=[{"reason": "required_group_budget_limit"}],
    )


def test_unresolved_required_dependency_cannot_be_reported_as_complete():
    assert not runner._completeness_honesty(
        search_complete=True,
        context_status="complete",
        deferred=[{"reason": "unresolved_required_dependency"}],
    )
    assert runner._completeness_honesty(
        search_complete=True,
        context_status="partial",
        deferred=[{"reason": "unresolved_required_dependency"}],
    )


def test_non_ok_source_read_must_not_contain_fragments():
    status_match, non_ok_empty = runner._source_read_contract(
        actual_status="stale",
        expected_status="stale",
        fragments=[{"raw_text": "unexpected"}],
    )
    assert status_match is True
    assert non_ok_empty is False


def test_explicit_source_read_status_is_checked_independently():
    status_match, non_ok_empty = runner._source_read_contract(
        actual_status="not_found",
        expected_status="ambiguous",
        fragments=[],
    )
    assert status_match is False
    assert non_ok_empty is True

    missing_match, missing_empty = runner._source_read_contract(
        actual_status=None,
        expected_status="ambiguous",
        fragments=[],
    )
    assert missing_match is False
    assert missing_empty is True


def test_legacy_context_status_mismatches_remain_classified_and_visible():
    for case_id in (
        "gq-025-source-budget-exceeded",
        "gq-028-ambiguous-source",
        "gq-029-not-found-source",
    ):
        assert runner._context_status_diagnostic(case_id, False) == (
            "legacy_corpus_contract_interpretation"
        )
    assert runner._context_status_diagnostic("gq-010-number-plus-condition", False) == (
        "unexpected_context_status_mismatch"
    )
    assert runner._context_status_diagnostic("gq-025-source-budget-exceeded", True) == "matched"


def test_pr_report_uses_verified_checkout_base_when_event_base_is_stale(monkeypatch, tmp_path):
    checkout = "d" * 40
    current_base = "b" * 40
    pr_head = "c" * 40
    stale_event_base = "a" * 40

    def fake_git(root, *args):
        assert args == ("cat-file", "-p", checkout)
        # Raw commit headers remain readable in a depth-one/shallow checkout.
        return (
            f"tree {'f' * 40}\n"
            f"parent {current_base}\n"
            f"parent {pr_head}\n\n"
            "Merge PR head into current main\n"
        )

    monkeypatch.setattr(runner, "git", fake_git)
    effective_base, checkout_base, checkout_head = runner._resolve_pr_checkout_identity(
        tmp_path,
        pr_head_sha=pr_head,
        event_base_sha=stale_event_base,
        actual_checkout_sha=checkout,
    )

    assert effective_base == current_base
    assert checkout_base == current_base
    assert checkout_head == pr_head


def test_pr_report_keeps_event_base_when_merge_ref_parent_does_not_match_pr_head(monkeypatch, tmp_path):
    checkout = "d" * 40
    event_base = "a" * 40
    declared_pr_head = "c" * 40

    monkeypatch.setattr(
        runner,
        "git",
        lambda root, *args: (
            f"tree {'f' * 40}\n"
            f"parent {'b' * 40}\n"
            f"parent {'e' * 40}\n\n"
            "Merge ref whose second parent is not the requested PR head\n"
        ),
    )
    effective_base, checkout_base, checkout_head = runner._resolve_pr_checkout_identity(
        tmp_path,
        pr_head_sha=declared_pr_head,
        event_base_sha=event_base,
        actual_checkout_sha=checkout,
    )

    assert effective_base == event_base
    assert checkout_base is None
    assert checkout_head is None


def test_token_efficiency_uses_same_source_text_tokenizer_on_both_sides():
    class WordCounter:
        def count(self, value: str) -> int:
            return len(value.split())

    included = [{"raw_text": "one two"}]
    baseline_documents = ["one two three four"]
    assert runner._token_efficiency(
        WordCounter(), included, baseline_documents
    ) == 0.5


def _corpus_node_map(corpus):
    return {
        node["node_id"]: {**node, "source_path": document["source_path"]}
        for document in corpus["documents"]
        for node in document["nodes"]
    }


def test_gq_007_and_gq_008_token_baselines_include_allowed_additional_documents():
    corpus, _ = runner.validate_corpus(
        runner.CORPUS_DIR / "corpus.v1.json",
        runner.CORPUS_DIR / "gold-case.schema.json",
    )
    node_map = _corpus_node_map(corpus)
    cases = {case["id"]: case for case in corpus["cases"]}

    assert runner._relevant_context_source_paths(
        cases["gq-007-entity-alias-russian"], node_map
    ) == (
        "synthetic/entities/alias-register.md",
        "synthetic/entities/aylin-profile.md",
    )
    assert runner._relevant_context_source_paths(
        cases["gq-008-short-code-ambiguity"], node_map
    ) == (
        "synthetic/entities/alias-register.md",
        "synthetic/entities/aylin-profile.md",
    )


def test_relevant_context_baseline_deduplicates_documents():
    case = {
        "context_pack": {
            "required_node_ids": ["node_a", "node_b"],
            "allowed_additional_node_ids": ["node_c"],
        }
    }
    node_map = {
        "node_a": {"source_path": "synthetic/one.md"},
        "node_b": {"source_path": "synthetic/one.md"},
        "node_c": {"source_path": "synthetic/two.md"},
    }
    assert runner._relevant_context_source_paths(case, node_map) == (
        "synthetic/one.md",
        "synthetic/two.md",
    )


class _FakeDependencySourceReader:
    def __init__(self, resolve_status="ok"):
        self.pinned_snapshot = object()
        self.resolve_status = resolve_status
        self.scope_calls = 0
        self.hash_value = "sha256:" + "a" * 64
        self.target = {
            "content_hash": self.hash_value,
            "source_path": "synthetic/dependency.md",
            "node_type": "paragraph",
            "parent_node_id": None,
            "heading_path": [],
            "line_start": 1,
            "line_end": 1,
            "index_generation": 1,
            "document_hash": "sha256:" + "b" * 64,
            "metadata": {},
        }

    def resolve_current_node(self, node_id, snapshot):
        if self.resolve_status != "ok":
            return {"status": self.resolve_status, "snapshot_id": snapshot.snapshot_id}
        return {
            "status": "ok",
            "snapshot_id": snapshot.snapshot_id,
            "address": {"content_hash": self.hash_value},
        }

    def read_scope(self, node_id, expected_hash, scope, snapshot):
        self.scope_calls += 1
        return {
            "status": "ok",
            "snapshot_id": snapshot.snapshot_id,
            "target_source": dict(self.target),
            "fragments": [{"raw_text": "synthetic dependency"}],
        }

    def read_node(self, *args, **kwargs):
        return {"status": "ok", "node": {}}


def test_dependency_fallback_rate_counts_actual_scope_reads_only_after_successful_resolve():
    from sfra_context_builder.models import SnapshotRef

    snapshot = SnapshotRef("a" * 40, "b" * 40, "sha256:" + "c" * 64)
    fake = _FakeDependencySourceReader()
    reader = runner.CountingSourceReader(fake)
    resolver = runner.ScenarioResolver(reader, set())

    resolved = resolver.resolve_node("node_dependency", snapshot)

    assert resolved is not None
    assert reader.dependency_resolutions == 1
    assert reader.dependency_source_reads == 1
    assert fake.scope_calls == 1
    assert runner._fallback_rate(reader.dependency_source_reads, 2) == 0.5


def test_failed_dependency_address_resolution_counts_zero_fallback_reads():
    from sfra_context_builder.models import SnapshotRef

    snapshot = SnapshotRef("a" * 40, "b" * 40, "sha256:" + "c" * 64)
    fake = _FakeDependencySourceReader(resolve_status="not_found")
    reader = runner.CountingSourceReader(fake)
    resolver = runner.ScenarioResolver(reader, set())

    assert resolver.resolve_node("node_missing", snapshot) is None
    assert reader.dependency_resolutions == 1
    assert reader.dependency_source_reads == 0
    assert fake.scope_calls == 0
    assert runner._fallback_rate(reader.dependency_source_reads, 2) == 0.0


def test_e2_hit_and_explicit_scope_reads_do_not_inflate_fallback_rate():
    from sfra_context_builder.models import SnapshotRef

    snapshot = SnapshotRef("a" * 40, "b" * 40, "sha256:" + "c" * 64)
    fake = _FakeDependencySourceReader()
    reader = runner.CountingSourceReader(fake)

    reader.read_node("node_hit", "hash", snapshot)
    reader.read_scope("node_explicit", fake.hash_value, "document", snapshot)

    assert reader.e2_exact_source_reads == 1
    assert reader.explicit_source_reads == 1
    assert reader.dependency_source_reads == 0
    assert runner._fallback_rate(reader.dependency_source_reads, 2) == 0.0

