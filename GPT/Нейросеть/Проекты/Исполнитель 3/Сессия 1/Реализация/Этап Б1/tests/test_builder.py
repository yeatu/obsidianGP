from __future__ import annotations

import hashlib
import json

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


def test_budget_counts_included_and_provenance_but_not_coverage(builder):
    from sfra_context_builder import ContextBuilder

    class Utf8ByteCounter:
        def count(self, text):
            return len(text.encode("utf-8"))

        def metadata(self):
            return {
                "name": "utf8-byte-test-counter",
                "version": "1",
                "encoding": "utf8-bytes",
                "exact_for_encoding": True,
                "exact_for_client_model": False,
            }

    counter = Utf8ByteCounter()
    local_builder = ContextBuilder(counter)
    focus_ids = [f"aspect_{index:03d}" for index in range(80)]
    candidate = make_candidate(
        "n1", "source material", matched_focus_ids=focus_ids
    )

    focus = [
        {"id": aspect_id, "label": f"Long focus aspect label {index}"}
        for index, aspect_id in enumerate(focus_ids)
    ]
    baseline = local_builder.build(
        make_request(budget_tokens=100_000, focus=focus),
        make_batch(candidate),
    )
    included_wire = json.dumps(
        {"Included": baseline["Included"]},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )
    budget = counter.count(included_wire)
    assert baseline["Statistics"]["tokens_used"] == budget

    pack = local_builder.build(
        make_request(budget_tokens=budget, focus=focus),
        make_batch(candidate),
    )

    assert [item["node_id"] for item in pack["Included"]] == ["n1"]
    assert pack["Statistics"]["tokens_used"] == budget
    assert pack["Statistics"]["response_tokens_estimated"] > budget
    assert len(pack["Coverage"]) == 80
    assert not any(
        item["code"] == "coverage_metadata_exceeds_budget"
        for item in pack["Diagnostics"]
    )


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


def test_known_node_with_unresolved_required_with_dependency_is_partial(builder):
    a = make_candidate("A", "known A", required_with=["M"])
    request = make_request(
        known=[{"node_id": "A", "content_hash": a["content_hash"]}]
    )

    pack = builder.build(request, make_batch(a))

    assert pack["status"] == "partial"
    assert pack["Included"] == []
    assert [item["node_id"] for item in pack["Known"]] == ["A"]
    assert pack["Deferred"] == []
    diagnostic = next(
        item for item in pack["Diagnostics"]
        if item["code"] == "unresolved_required_dependency"
    )
    assert diagnostic["details"]["unresolved_dependency_ids"] == ["M"]


def test_known_node_with_unresolved_parent_context_is_partial(builder):
    a = make_candidate(
        "A", "known A", parent_node_id="M", parent_context_required=True
    )
    request = make_request(
        known=[{"node_id": "A", "content_hash": a["content_hash"]}]
    )

    pack = builder.build(request, make_batch(a))

    assert pack["status"] == "partial"
    assert pack["Included"] == []
    assert [item["node_id"] for item in pack["Known"]] == ["A"]
    assert pack["Deferred"] == []
    diagnostic = next(
        item for item in pack["Diagnostics"]
        if item["code"] == "unresolved_required_dependency"
    )
    assert diagnostic["details"]["unresolved_dependency_ids"] == ["M"]


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


def test_deduplication_preserves_overlap_metadata_from_all_hits(builder):
    first = make_candidate(
        "a", "same source", source_path="one/Shared.md",
        overlap_group_id=None, zone=None, has_author_notes=None,
    )
    second = make_candidate(
        "a", "same source", source_path="one/Shared.md",
        overlap_group_id="shared-model", zone="персонажи", has_author_notes=True,
    )
    parallel = make_candidate(
        "b", "parallel source", source_path="two/Shared.md",
        overlap_group_id="shared-model",
    )
    pack = builder.build(make_request(), make_batch(first, second, parallel))
    assert pack["Statistics"]["included_count"] == 2
    group = next(
        item for item in pack["Parallel Sources"]
        if item["relation"] == "adapter_overlap_group"
    )
    assert {source["node_id"] for source in group["sources"]} == {"a", "b"}
    included_a = next(item for item in pack["Included"] if item["node_id"] == "a")
    assert included_a["zone"] == "персонажи"
    assert included_a["has_author_notes"] is True


def test_terms_are_nfc_casefold_exact_not_morphological(builder):
    exact = make_candidate("n1", "СтИль РЕЧИ персонажа")
    miss = make_candidate("n2", "стилистика речи персонажа")
    request = make_request(focus=[{
        "id": "voice", "label": "Voice", "terms": ["стиль речи"]
    }])
    pack = builder.build(request, make_batch(exact, miss))
    assert pack["Coverage"][0]["included_node_ids"] == ["n1"]
    assert {item["node_id"] for item in pack["Included"]} == {"n1", "n2"}
    assert "n2" not in pack["Coverage"][0]["included_node_ids"]


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


def test_e2_tier_and_bm25_sort_ascending(builder):
    low_priority = make_candidate("tier4", "tier four", relevance={"tier": 4, "bm25": -100})
    stronger = make_candidate("tier2", "tier two", relevance={"tier": 2, "bm25": 10})
    best_bm25 = make_candidate("tier2b", "tier two best", relevance={"tier": 2, "bm25": -2})
    pack = builder.build(make_request(), make_batch(low_priority, stronger, best_bm25))
    assert [item["node_id"] for item in pack["Included"]] == ["tier2b", "tier2", "tier4"]


def test_truncated_flag_prevents_claiming_complete_search(builder):
    request = make_request(focus=[{"id": "missing", "label": "Not found"}])
    pack = builder.build(
        request,
        {"complete": True, "truncated_by_limit": True, "inspected_count": 0, "candidates": []},
    )
    assert pack["search_complete"] is False
    assert pack["status"] == "partial"
    assert "SearchBatch.complete=false" in pack["Coverage"][0]["diagnostic_note"]
