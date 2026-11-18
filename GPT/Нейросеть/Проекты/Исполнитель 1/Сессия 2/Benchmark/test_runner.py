from __future__ import annotations

from pathlib import Path
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
            f"tree {'f' * 40}\\n"
            f"parent {current_base}\\n"
            f"parent {pr_head}\\n\\n"
            "Merge PR head into current main\\n"
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
            f"tree {'f' * 40}\\n"
            f"parent {'b' * 40}\\n"
            f"parent {'e' * 40}\\n\\n"
            "Merge ref whose second parent is not the requested PR head\\n"
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

