from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from sfra_context_builder.models import SearchRequest, SnapshotRef
from sfra_context_integrations.search_adapter import E2SearchAdapter, SearchAdapterError
from sfra_context_integrations.snapshot import PinnedSnapshot


_DEFAULT_RAW = "Текст исходного узла.\r\nВторая строка."


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _request(**overrides):
    values = {
        "query": "реанимация", "task": None, "budget_tokens": 1500,
        "entities": (), "facets": (), "zones": (), "known": (), "focus": (),
    }
    values.update(overrides)
    return SearchRequest(**values)


def _snapshot():
    return SnapshotRef("a" * 40, "b" * 40, "sha256:" + "c" * 64)


def _pinned(tmp_path=None):
    root = Path(tmp_path or ".").resolve()
    return PinnedSnapshot(
        ref=_snapshot(),
        sidecar_root=root,
        database_path=root / "state" / "structure.sqlite3",
        manifest_path=root / "state" / "manifest.json",
        vault_root=root / "ГП",
        manifest={"source_commit": "a" * 40},
    )


def _hit(raw_text: str = _DEFAULT_RAW) -> dict:
    return {
        "node_id": "node_123",
        "source_path": "правила/реанимация.md",
        "node_type": "paragraph",
        "parent_node_id": "node_parent",
        "heading_path": ["Правила"],
        "line_start": 10,
        "line_end": 11,
        "content_hash": _hash(raw_text),
        "excerpt": "короткая поисковая подсказка",
        "match_type": "exact_heading",
        "match_reasons": ["heading_terms", "e2_reason_not_mapped"],
        "relevance": {"tier": 3, "bm25": -4.25},
        "entities": ["entity_01"],
        "matched_aliases": ["Реанимация"],
        "index_generation": 999,
        "document_hash": "sha256:" + "d" * 64,
    }


def _source(hit: dict, raw_text: str | None = None, *, status="ok", metadata=None):
    if status != "ok":
        return {"status": status, "node": None}
    exact_text = _DEFAULT_RAW if raw_text is None else raw_text
    return {
        "status": "ok",
        "node": {
            "node_id": hit["node_id"],
            "content_hash": hit["content_hash"],
            "source_path": hit["source_path"],
            "node_type": hit["node_type"],
            "parent_node_id": hit["parent_node_id"],
            "heading_path": hit["heading_path"],
            "line_start": hit["line_start"],
            "line_end": hit["line_end"],
            "raw_text": exact_text,
            "index_generation": 7,
            "document_hash": hit["document_hash"],
            "metadata": metadata if metadata is not None else {
                "preservation": "required",
                "required_with": ["node_sibling"],
                "parent_context_required": True,
                "has_author_notes": False,
            },
        },
    }


class FakeSourceReader:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def read_node(self, node_id, expected_hash, snapshot):
        self.calls.append((node_id, expected_hash, snapshot))
        if callable(self.responses):
            return self.responses(node_id, expected_hash, snapshot)
        return self.responses


def _engine(hits, *, status="ok"):
    def call(source_database, query, *, entities, limit, entity_config):
        assert query == "реанимация"
        assert entities == []
        assert entity_config is None
        return {
            "runtime": "one-shot-memory",
            "search": {
                "status": status,
                "results": [] if status == "not_found_in_retrieval" else hits,
            },
        }
    return call


def test_adapter_uses_e1_exact_text_and_preserves_e2_rank_and_metadata():
    original = "Точный исходный узел.\r\nБез нормализации."
    hit = _hit(original)
    reader = FakeSourceReader(_source(hit, original))
    adapter = E2SearchAdapter(_pinned(), reader, search_call=_engine([hit]), search_limit=10)

    result = adapter.search(_request())

    assert result.engine_status == "ok"
    assert result.batch.complete is True
    assert len(result.batch.candidates) == 1
    candidate = result.batch.candidates[0]
    assert candidate.raw_text == original
    assert candidate.signals["match_excerpt"] == hit["excerpt"]
    assert candidate.raw_text != candidate.signals["match_excerpt"]
    assert candidate.relevance_tier == 3
    assert candidate.relevance_bm25 == -4.25
    assert candidate.score is None
    assert candidate.score_direction is None
    assert candidate.match_type == "exact_heading"
    assert candidate.unmapped_match_reasons == ("heading_terms", "e2_reason_not_mapped")
    assert candidate.match_reasons == ()
    assert candidate.index_generation == 7
    assert candidate.index_generation != hit["index_generation"]
    assert candidate.preservation == "required"
    assert candidate.required_with == ("node_sibling",)
    assert candidate.parent_context_required is True
    assert reader.calls == [("node_123", hit["content_hash"], _snapshot())]


def test_adapter_maps_empty_retrieval_to_empty_complete_batch():
    reader = FakeSourceReader({"status": "not_found_in_retrieval", "node": None})
    adapter = E2SearchAdapter(
        _pinned(), reader,
        search_call=_engine([], status="not_found_in_retrieval"),
        search_limit=10,
    )
    result = adapter.search(_request())
    assert result.batch.complete is True
    assert result.batch.inspected_count == 0
    assert result.batch.candidates == ()
    assert result.diagnostics == ()


def test_adapter_does_not_turn_engine_error_into_empty_search():
    def fail(*args, **kwargs):
        raise OSError("sidecar unavailable")
    adapter = E2SearchAdapter(_pinned(), FakeSourceReader({}), search_call=fail)
    with pytest.raises(SearchAdapterError) as error:
        adapter.search(_request())
    assert error.value.code == "e2_search_failed"


def test_adapter_marks_limit_sized_result_as_truncated():
    hit = _hit()
    reader = FakeSourceReader(_source(hit))
    adapter = E2SearchAdapter(_pinned(), reader, search_call=_engine([hit, hit]), search_limit=2)
    result = adapter.search(_request())
    assert result.batch.complete is False
    assert result.batch.truncated_by_limit is True
    assert result.batch.inspected_count == 2


@pytest.mark.parametrize("status", ["stale_source", "ambiguous", "deleted", "not_found"])
def test_adapter_excludes_non_ok_source_status_and_marks_batch_incomplete(status):
    hit = _hit()
    reader = FakeSourceReader(_source(hit, status=status))
    adapter = E2SearchAdapter(_pinned(), reader, search_call=_engine([hit]))
    result = adapter.search(_request())
    assert result.batch.candidates == ()
    assert result.batch.complete is False
    assert result.diagnostics[0]["code"] == f"source_{status}"


def test_adapter_treats_source_integrity_error_as_error_diagnostic():
    hit = _hit()
    reader = FakeSourceReader(_source(hit, status="integrity_error"))
    adapter = E2SearchAdapter(_pinned(), reader, search_call=_engine([hit]))
    result = adapter.search(_request())
    assert result.batch.complete is False
    assert result.diagnostics[0]["severity"] == "error"


def test_adapter_rejects_locator_metadata_mismatch():
    hit = _hit()
    source = _source(hit)
    source["node"]["source_path"] = "другой/документ.md"
    adapter = E2SearchAdapter(_pinned(), FakeSourceReader(source), search_call=_engine([hit]))
    result = adapter.search(_request())
    assert result.batch.candidates == ()
    assert result.batch.complete is False
    assert result.diagnostics[0]["code"] == "search_source_metadata_mismatch"


def test_adapter_rejects_source_text_with_wrong_hash():
    hit = _hit("expected text")
    source = _source(hit, "different text")
    adapter = E2SearchAdapter(_pinned(), FakeSourceReader(source), search_call=_engine([hit]))
    result = adapter.search(_request())
    assert result.batch.candidates == ()
    assert result.diagnostics[0]["code"] == "source_content_hash_mismatch"
    assert result.diagnostics[0]["severity"] == "error"


def test_adapter_does_not_infer_facet_match_and_reports_missing_dependency_metadata():
    hit = _hit()
    source = _source(hit, metadata={})
    adapter = E2SearchAdapter(_pinned(), FakeSourceReader(source), search_call=_engine([hit]))
    result = adapter.search(_request(facets=("VOICE",)))
    assert result.batch.candidates[0].matched_facets == ()
    assert result.batch.candidates[0].preservation == "normal"
    assert result.diagnostics[0]["code"] == "facet_match_signal_unavailable"
    assert any(d["code"] == "dependency_metadata_unavailable" for d in result.diagnostics)


def test_zone_post_filter_is_exact_and_marks_result_incomplete():
    rules_hit = _hit()
    other_hit = dict(rules_hit)
    other_hit["node_id"] = "node_456"
    other_hit["source_path"] = "персонажи/реанимация.md"
    other_hit["content_hash"] = _hash("Другой текст")
    reader = FakeSourceReader(_source(rules_hit))
    adapter = E2SearchAdapter(_pinned(), reader, search_call=_engine([rules_hit, other_hit]))
    result = adapter.search(_request(zones=("правила",)))
    assert len(result.batch.candidates) == 1
    assert result.batch.candidates[0].zone == "правила"
    assert result.batch.complete is False
    assert any(d["code"] == "zone_post_filter_applied" for d in result.diagnostics)
    assert len(reader.calls) == 1
