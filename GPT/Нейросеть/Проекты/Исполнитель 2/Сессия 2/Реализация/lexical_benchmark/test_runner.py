from __future__ import annotations
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lexical_benchmark.runner import evaluate_case, precision_at_k, recall_at_k, reciprocal_rank


def test_recall_at_k_uses_relevant_set():
    assert recall_at_k(["a", "b"], ["x", "a", "b"], 2) == 0.5
    assert recall_at_k(["a", "b"], ["b", "a"], 2) == 1.0


def test_precision_at_k_uses_requested_cutoff():
    assert precision_at_k(["a"], ["a", "b"], 3) == 1 / 3


def test_reciprocal_rank_uses_first_relevant_position():
    assert reciprocal_rank(["a", "b"], ["x", "b", "a"]) == 0.5


def test_empty_relevance_set_has_undefined_metrics():
    assert recall_at_k([], ["x"], 5) is None
    assert precision_at_k([], ["x"], 5) is None
    assert reciprocal_rank([], ["x"]) is None


def test_case_evaluation_detects_order_drift_and_duplicates():
    case = {
        "id": "ordering", "category": "ordering", "query": "дежурство",
        "expected_node_ids": ["a", "b"], "expected_order": ["a", "b"],
        "k": 2, "gate": True,
    }
    result = evaluate_case(case, [
        {"node_ids": ["a", "b"], "hits": [], "exception": None},
        {"node_ids": ["b", "a"], "hits": [], "exception": None},
    ])
    assert result["status"] == "failed"
    assert result["stable_order"] is False
    duplicated = evaluate_case(case, [
        {"node_ids": ["a", "a"], "hits": [], "exception": None},
        {"node_ids": ["a", "a"], "hits": [], "exception": None},
    ])
    assert duplicated["no_duplicates"] is False
    assert duplicated["status"] == "failed"


def test_diagnostic_case_does_not_fail_gate():
    case = {
        "id": "typo", "category": "typo-diagnostic", "query": "кварцолётт",
        "expected_node_ids": ["a"], "k": 3, "gate": False,
    }
    result = evaluate_case(case, [
        {"node_ids": [], "hits": [], "exception": None},
        {"node_ids": [], "hits": [], "exception": None},
    ])
    assert result["status"] == "diagnostic"
    assert result["reciprocal_rank"] == 0.0

def test_case_evaluation_checks_expected_search_status():
    case = {
        "id": "noise",
        "category": "empty-results",
        "query": "!!!",
        "expected_node_ids": [],
        "expected_status": "not_found_in_retrieval",
        "k": 3,
        "gate": True,
    }
    result = evaluate_case(case, [
        {"status": "ok", "node_ids": [], "hits": [], "exception": None},
        {"status": "ok", "node_ids": [], "hits": [], "exception": None},
    ])
    assert result["status"] == "failed"
    assert result["expected_status_match"] is False
