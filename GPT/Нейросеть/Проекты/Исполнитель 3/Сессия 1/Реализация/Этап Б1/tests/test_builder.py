from __future__ import annotations

import hashlib

from sfra_context_builder.validation import validate_context_pack
from conftest import make_batch, make_candidate, make_request


def test_happy_path_includes_exact_raw_text_and_marks_untrusted(builder):
    text = "Исходный фрагмент без изменений 🪄"
    pack = builder.build(make_request(), make_batch(make_candidate("n1", text)))
    assert pack["status"] == "complete"
    assert pack["Included"][0]["raw_text"] == text
    assert pack["Included"][0]["content_hash"] == "sha256:" + hashlib.sha256(text.encode()).hexdigest()
    assert pack["Included"][0]["trust_label"] == "untrusted_source_data"
    assert pack["Included"][0]["inclusion_reason"] == "retrieval_candidate"
    validate_context_pack(pack)


def test_bad_content_hash_is_rejected_not_deferred(builder):
    bad = make_candidate("bad", "true text", content_hash="sha256:" + "0" * 64)
    pack = builder.build(make_request(), make_batch(bad))
    assert pack["status"] == "integrity_warning"
    assert pack["Included"] == []
    assert pack["Deferred"] == []
    assert pack["Statistics"]["rejected_count"] == 1
    assert pack["Diagnostics"][0]["code"] == "content_hash_mismatch"


def test_identical_node_version_is_deduplicated_and_signals_merged(builder):
    first = make_candidate("n1", "same", match_reasons=["heading_exact"])
    second = make_candidate("n1", "same", match_reasons=["body_morphology"], signals={"heading_match": True})
    pack = builder.build(make_request(), make_batch(first, second))
    assert pack["Statistics"]["retrieved_count"] == 2
    assert pack["Statistics"]["included_count"] == 1
    assert pack["Included"][0]["signals"]["heading_match"] is True


def test_conflicting_versions_for_same_node_are_not_arbitrated(builder):
    first = make_candidate("n1", "version one")
    second = make_candidate("n1", "version two")
    pack = builder.build(make_request(), make_batch(first, second))
    assert pack["status"] == "integrity_warning"
    assert pack["Included"] == []
    assert pack["Deferred"] == []
    assert any(item["code"] == "version_conflict" for item in pack["Diagnostics"])


def test_required_singleton_is_processed_before_normal_candidates(builder):
    normal = make_candidate("normal", "normal", relevance={"tier": 1, "bm25": -10})
    required = make_candidate("required", "mandatory", preservation="required", relevance={"tier": 6, "bm25": 20})
    pack = builder.build(make_request(), make_batch(normal, required))
    assert [item["node_id"] for item in pack["Included"]] == ["required", "normal"]


def test_required_group_is_atomic_under_budget(builder):
    a = make_candidate("A", "one two three four", preservation="required", required_with=["B"])
    b = make_candidate("B", "five six seven eight")
    pack = builder.build(make_request(budget_tokens=1), make_batch(a, b))
    assert pack["Included"] == []
    assert {item["node_id"] for item in pack["Deferred"]} == {"A", "B"}
    assert all(item["reason"] == "required_group_budget_limit" for item in pack["Deferred"])
    assert pack["status"] == "budget_limited"


def test_unresolved_required_dependency_is_partial_not_budget_limited(builder):
    a = make_candidate("A", "A", preservation="required", required_with=["M"])
    pack = builder.build(make_request(), make_batch(a))
    assert pack["status"] == "partial"
    assert pack["Deferred"][0]["reason"] == "unresolved_required_dependency"
    assert pack["Statistics"]["coverage_available_ratio"] is None


def test_focus_known_only_counts_available_but_not_included(builder):
    candidate = make_candidate("n1", "голос героя", matched_focus_ids=["voice"])
    known = [{"node_id": "n1", "content_hash": candidate["content_hash"]}]
    request = make_request(
        known=known,
        focus=[{"id": "voice", "label": "Голос", "match_mode": "any"}],
    )
    pack = builder.build(request, make_batch(candidate))
    assert pack["Coverage"][0]["status"] == "found"
    assert pack["Coverage"][0]["included_node_ids"] == []
    assert pack["Coverage"][0]["known_node_ids"] == ["n1"]
    assert pack["Statistics"]["coverage_available_ratio"] == 1.0
    assert pack["Statistics"]["coverage_included_ratio"] == 0.0


def test_focus_any_and_all_use_exact_categories_only(builder):
    candidate = make_candidate(
        "n1", "модель населения",
        matched_entities=["Магическое население"],
        matched_facets=[],
    )
    any_request = make_request(focus=[{
        "id": "a", "label": "Население", "entities": ["Магическое население"],
        "facets": ["DEMOGRAPHY"], "match_mode": "any"
    }])
    all_request = make_request(focus=[{
        "id": "a", "label": "Население", "entities": ["Магическое население"],
        "facets": ["DEMOGRAPHY"], "match_mode": "all"
    }])
    assert builder.build(any_request, make_batch(candidate))["Coverage"][0]["status"] == "found"
    assert builder.build(all_request, make_batch(candidate))["Coverage"][0]["status"] == "not_found_in_retrieval"


def test_terms_are_nfc_casefold_exact_not_morphological(builder):
    exact = make_candidate("n1", "СтИль РЕЧИ персонажа")
    miss = make_candidate("n2", "стилистика речи персонажа")
    request = make_request(focus=[{
        "id": "voice", "label": "Voice", "terms": ["стиль речи"]
    }])
    pack = builder.build(request, make_batch(exact, miss))
    assert pack["Coverage"][0]["included_node_ids"] == ["n1"]
    assert [item["node_id"] for item in pack["Deferred"]] == ["n2"]


def test_two_same_basename_sources_remain_separate(builder):
    a = make_candidate("a", "демография A", source_path="иное/Демография.md")
    b = make_candidate("b", "демография B", source_path="разобрать/Демография.md")
    pack = builder.build(make_request(), make_batch(a, b))
    assert len(pack["Included"]) == 2
    assert len(pack["Parallel Sources"]) == 1
    assert pack["Parallel Sources"][0]["kept_separate"] is True
    assert {item["source_path"] for item in pack["Parallel Sources"][0]["sources"]} == {
        "иное/Демография.md", "разобрать/Демография.md"
    }


def test_incomplete_search_is_partial_and_not_found_is_scoped(builder):
    request = make_request(focus=[{"id": "x", "label": "Not here"}])
    pack = builder.build(request, make_batch(complete=False),)
    assert pack["status"] == "partial"
    assert pack["Coverage"][0]["status"] == "not_found_in_retrieval"
    assert "SearchBatch.complete=false" in pack["Coverage"][0]["diagnostic_note"]


def test_known_old_version_creates_version_change_and_includes_current(builder):
    current = make_candidate("n1", "current text")
    old_hash = "sha256:" + "f" * 64
    request = make_request(known=[{"node_id": "n1", "content_hash": old_hash}])
    pack = builder.build(request, make_batch(current))
    assert pack["Version Changes"] == [{
        "node_id": "n1",
        "known_hash": old_hash,
        "current_hash": current["content_hash"],
        "action": "deliver_current_version_if_budget_allows",
    }]
    assert pack["Included"][0]["raw_text"] == "current text"


def test_status_budget_limited_precedes_incomplete_search(builder):
    a = make_candidate("n1", "too many words here")
    pack = builder.build(make_request(budget_tokens=1), make_batch(a, complete=False))
    assert pack["status"] == "budget_limited"


def test_parallel_overlap_group_is_neutral(builder):
    a = make_candidate("a", "a", overlap_group_id="g")
    b = make_candidate("b", "b", overlap_group_id="g")
    pack = builder.build(make_request(), make_batch(a, b))
    group = next(item for item in pack["Parallel Sources"] if item["relation"] == "adapter_overlap_group")
    assert "потенциальное пересечение" in group["description"]
    assert group["kept_separate"] is True
