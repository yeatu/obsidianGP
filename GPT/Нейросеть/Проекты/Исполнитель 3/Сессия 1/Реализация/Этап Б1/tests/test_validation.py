from __future__ import annotations

import pytest

from sfra_context_builder.validation import ContractValidationError, parse_search_batch, parse_search_request
from conftest import make_batch, make_candidate, make_request


def test_short_focus_ids_are_deterministic():
    request = parse_search_request(make_request(focus=["Voice", "Rules"]))
    assert [item.aspect_id for item in request.focus] == ["focus_001", "focus_002"]


def test_extended_focus_supports_any_and_all():
    request = parse_search_request(make_request(focus=[{
        "id": "x", "label": "X", "entities": ["A"], "terms": ["B"], "match_mode": "all"
    }]))
    assert request.focus[0].match_mode == "all"


def test_duplicate_focus_id_is_rejected():
    with pytest.raises(ContractValidationError, match="duplicate focus id"):
        parse_search_request(make_request(focus=[
            {"id": "x", "label": "one"}, {"id": "x", "label": "two"}
        ]))


@pytest.mark.parametrize("budget", [0, -1, True, "100"])
def test_invalid_budget_is_rejected(budget):
    with pytest.raises(ContractValidationError):
        parse_search_request(make_request(budget_tokens=budget))


def test_unknown_request_field_is_rejected():
    with pytest.raises(ContractValidationError, match="unsupported fields"):
        parse_search_request(make_request(arbitrary=True))


def test_search_batch_requires_complete_inspected_and_candidates():
    with pytest.raises(ContractValidationError):
        parse_search_batch({"complete": True, "candidates": []})


def test_invalid_coordinate_order_is_rejected():
    candidate = make_candidate("n1", "text", line_start=4, line_end=2)
    with pytest.raises(ContractValidationError, match="line_end"):
        parse_search_batch(make_batch(candidate))


def test_score_requires_explicit_direction_without_e2_relevance():
    candidate = make_candidate("n1", "text")
    candidate.pop("relevance")
    candidate["score"] = 0.7
    with pytest.raises(ContractValidationError, match="score_direction"):
        parse_search_batch(make_batch(candidate))
