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

def test_budget_exceeded_cannot_be_represented_as_complete():
    assert not runner._completeness_honesty(
        search_complete=True,
        context_status="complete",
        deferred=[],
        source_read_status="budget_exceeded",
        source_read_fragments=[],
    )
    assert runner._completeness_honesty(
        search_complete=True,
        context_status="partial",
        deferred=[],
        source_read_status="budget_exceeded",
        source_read_fragments=[],
    )


def test_incomplete_search_and_deferred_budget_cannot_be_complete():
    assert not runner._completeness_honesty(
        search_complete=False,
        context_status="complete",
        deferred=[],
        source_read_status=None,
        source_read_fragments=[],
    )
    assert not runner._completeness_honesty(
        search_complete=True,
        context_status="complete",
        deferred=[{"reason": "required_group_budget_limit"}],
        source_read_status=None,
        source_read_fragments=[],
    )


def test_non_ok_source_read_must_not_contain_fragments():
    assert not runner._completeness_honesty(
        search_complete=True,
        context_status="partial",
        deferred=[],
        source_read_status="stale",
        source_read_fragments=[{"raw_text": "unexpected"}],
    )


def test_token_efficiency_uses_same_source_text_tokenizer_on_both_sides():
    class WordCounter:
        def count(self, value: str) -> int:
            return len(value.split())

    included = [{"raw_text": "one two"}]
    baseline_documents = ["one two three four"]
    assert runner._token_efficiency(
        WordCounter(), included, baseline_documents
    ) == 0.5

