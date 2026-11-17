from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from sfra_search import SFRAIndex, ImportValidationError, calculate_content_hash


def node(node_id: str, path: str, text: str, line: int = 1, heading=None):
    return {
        "node_id": node_id,
        "source_path": path,
        "node_type": "section",
        "parent_node_id": None,
        "heading_path": heading or [],
        "line_start": line,
        "line_end": line + max(0, text.count("\n")),
        "content_hash": calculate_content_hash(text),
        "raw_text": text,
    }


@pytest.fixture
def index(tmp_path):
    return SFRAIndex(tmp_path / "search.sqlite3")


def results(index, query):
    return index.search(query)["results"]


def test_database_and_fts5_creation(index):
    check = index.check()
    assert check["ok"] is True
    assert check["integrity"] == "ok"


def test_exact_russian_word_and_original_text_are_preserved(index):
    original = "Магами пользовались древние ритуалы; маг оставил запись."
    index.import_nodes([node("n1", "персонажи/Маг.md", original)])
    found = results(index, "маг")
    assert found
    assert found[0]["excerpt"] == original
    assert found[0]["node_id"] == "n1"
    assert found[0]["content_hash"] == calculate_content_hash(original)


def test_morphology_finds_case_forms(index):
    index.import_nodes([node("n1", "система магии/маг.md", "Заклинание усилено древними магами и магами-целителями.")])
    assert results(index, "маг")
    assert results(index, "мага")
    assert results(index, "маги")
    assert results(index, "магами")


def test_verb_morphology(index):
    index.import_nodes([node("n1", "персонажи/речь.md", "Они долго разговаривали возле кабинета.")])
    assert results(index, "говорить") or results(index, "говорили") or results(index, "разговаривали")


def test_composite_name_and_filename(index):
    index.import_nodes([node("n1", "персонажи/Генрих Фауст.md", "Генрих-Фауст внимательно слушал собеседника.")])
    assert results(index, "Генрих Фауст")
    assert results(index, "Генрих-Фауст")


def test_heading_search(index):
    index.import_nodes([node("n1", "персонажи/Генрих Фауст.md", "Он говорит спокойно.", heading=["Поведение", "Конфликтное поведение"])])
    assert results(index, "Конфликтное поведение")


@pytest.mark.parametrize("number", ["18 518", "18\u00a0518", "18\u202f518", "18518"])
def test_exact_number_formats(index, number):
    index.import_nodes([
        node("n1", "иное/Демография.md", "Магическое население: 18 518 человек."),
        node("n2", "разобрать/Демография.md", "Расчётное значение: 185180 человек."),
        node("n3", "другое/Население.md", "Суммарное значение: 118518 человек."),
    ])
    found = results(index, number)
    ids = {item["node_id"] for item in found}
    assert "n1" in ids
    assert "n2" not in ids
    assert "n3" not in ids


def test_rejects_content_hash_mismatch(index):
    bad = node("n1", "a.md", "текст")
    bad["content_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ImportValidationError):
        index.import_nodes([bad])
    assert index.check()["active_nodes"] == 0


def test_import_is_idempotent_and_versions_are_retained(index):
    first = node("n1", "персонажи/Генрих Фауст.md", "Первая версия.")
    assert index.import_nodes([first])["versions_created"] == 1
    again = index.import_nodes([first])
    assert again["unchanged"] == 1
    assert again["versions_created"] == 0
    second = node("n1", "персонажи/Генрих Фауст.md", "Вторая версия.")
    assert index.import_nodes([second])["updated"] == 1
    assert index.get_node("n1")["raw_text"] == "Вторая версия."
    assert index.get_node("n1", first["content_hash"])["raw_text"] == "Первая версия."
    assert len(results(index, "Вторая")) == 1
    assert not results(index, "Первая")


def test_delta_does_not_delete_absent_nodes(index):
    a = node("a", "docs/A.md", "alpha")
    b = node("b", "docs/B.md", "beta")
    index.import_nodes([a, b])
    index.import_nodes([a], {"mode": "delta"})
    assert index.get_node("b") is not None


def test_replace_documents_deletes_only_missing_nodes_in_scope(index):
    a = node("a", "docs/A.md", "alpha")
    b = node("b", "docs/A.md", "beta")
    other = node("c", "other/A.md", "gamma")
    index.import_nodes([a, b, other])
    index.import_nodes([a], {"mode": "replace_documents", "replace_source_paths": ["docs/A.md"]})
    assert index.get_node("a") is not None
    assert index.get_node("b") is None
    assert index.get_node("c") is not None


def test_deleted_node_ids(index):
    index.import_nodes([node("a", "docs/A.md", "alpha")])
    index.import_nodes([], {"mode": "delta", "deleted_node_ids": ["a"]})
    assert index.get_node("a") is None
    assert not results(index, "alpha")


def test_parallel_same_basename_documents_remain_distinct(index):
    index.import_nodes([
        node("n1", "иное/Демография.md", "Соотношение магов и магглов."),
        node("n2", "разобрать/Демография.md", "Другая демографическая модель и расчёты."),
    ])
    found = results(index, "Демография")
    paths = {item["source_path"] for item in found}
    assert "иное/Демография.md" in paths
    assert "разобрать/Демография.md" in paths


def test_confirmed_alias_and_mentions(index):
    index.import_nodes([
        node("n1", "персонажи/Дафна.md", "Дафна пришла в зал."),
        node("n2", "сюжет/Сцена.md", "Дафна Гринграсс разговаривала с Генрихом."),
    ])
    index.create_entity("character_daphne", "Дафна Гринграсс", primary_source_path="персонажи/Дафна.md")
    index.add_alias_candidate("character_daphne", "Дафна")
    assert index.search_entity("Дафна")["results"] == []
    index.confirm_alias("character_daphne", "Дафна")
    found = index.search_entity("Дафна")
    assert found["ambiguous"] is False
    assert {r["node_id"] for r in found["results"]} == {"n1", "n2"}
    mentions = index.mentions_for_entity("character_daphne")
    assert {m["node_id"] for m in mentions} == {"n1", "n2"}


def test_ambiguous_alias_is_not_auto_merged(index):
    index.import_nodes([
        node("n1", "персонажи/Александр.md", "Александр Долохов приехал."),
        node("n2", "персонажи/Антонин.md", "Антонин Долохов прибыл позже."),
    ])
    index.create_entity("alexander_dolohov", "Александр Долохов")
    index.create_entity("antonin_dolohov", "Антонин Долохов")
    index.confirm_alias("alexander_dolohov", "Долохов")
    index.confirm_alias("antonin_dolohov", "Долохов")
    found = index.search_entity("Долохов")
    assert found["ambiguous"] is True
    assert set(found["entity_ids"]) == {"alexander_dolohov", "antonin_dolohov"}
    assert len(found["results"]) == 2


def test_rejected_alias_is_not_searchable(index):
    index.import_nodes([node("n1", "персонажи/Рэбекка.md", "Рэбекка Блэк ждала.")])
    index.create_entity("rebecca", "Рэбекка Блэк")
    index.add_alias_candidate("rebecca", "Рэбекка Блэе")
    index.reject_alias("rebecca", "Рэбекка Блэе")
    assert index.search_entity("Рэбекка Блэе")["results"] == []


def test_fts_query_is_escaped_from_user_syntax(index):
    index.import_nodes([node("n1", "docs/A.md", "обычный текст для поиска")])
    response = index.search('обычный OR NEAR(*) " ; DROP TABLE nodes;--')
    assert isinstance(response["results"], list)
    assert index.get_node("n1") is not None


def test_metadata_update_keeps_single_version(index):
    initial = node("n1", "docs/A.md", "same text", line=1)
    index.import_nodes([initial])
    relocated = dict(initial, line_start=20, line_end=20, heading_path=["Новый заголовок"])
    result = index.import_nodes([relocated])
    assert result["versions_created"] == 0
    current = index.get_node("n1")
    assert current["line_start"] == 20
    assert current["heading_path"] == ["Новый заголовок"]


def test_cli_check_entry_point_is_importable():
    from sfra_search.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["--db", ":memory:", "init"])
    assert args.command == "init"


def test_grouped_number_does_not_match_separate_numbers(index):
    index.import_nodes([
        node("n1", "docs/a.md", "В документе указаны отдельные числа 18 и 518, но нет общего значения."),
        node("n2", "docs/b.md", "Точное числовое значение составляет 18 518."),
    ])
    found = results(index, "18 518")
    ids = {item["node_id"] for item in found}
    assert ids == {"n2"}


def test_transaction_rolls_back_entire_batch_on_runtime_failure(index, monkeypatch):
    original = index._insert_fts
    calls = {"n": 0}

    def fail_on_second(conn, version_id, item):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated write failure")
        return original(conn, version_id, item)

    monkeypatch.setattr(index, "_insert_fts", fail_on_second)
    with pytest.raises(RuntimeError, match="simulated"):
        index.import_nodes([
            node("n1", "docs/a.md", "first node"),
            node("n2", "docs/b.md", "second node"),
        ])
    assert index.check()["active_nodes"] == 0
    assert not results(index, "first")


def test_memory_database_uses_shared_connection_lifetime():
    memory = SFRAIndex(":memory:")
    memory.import_nodes([node("n1", "docs/a.md", "memory index")])
    assert results(memory, "memory")


def test_decimal_numbers_are_exact(index):
    index.import_nodes([
        node("n1", "docs/a.md", "Точность 18 518,25."),
        node("n2", "docs/b.md", "Точность 18518,26."),
    ])
    found = results(index, "18 518,25")
    assert {item["node_id"] for item in found} == {"n1"}


def test_import_proposes_entity_candidates_without_confirming_them(index):
    index.import_nodes([node(
        "n1", "персонажи/Дафна Гринграсс.md",
        "Дафна Гринграсс пришла. Дафна Гринграсс улыбнулась.",
        heading=["Персонажи", "Дафна Гринграсс"],
    )])
    candidates = index.list_entity_candidates()
    assert any(c["candidate_text"] == "Дафна Гринграсс" for c in candidates)
    # Candidate harvesting is navigation-only; it must not create an entity or mention.
    assert index.search_entity("Дафна Гринграсс")["results"] == []


def test_confirmed_alias_matches_hyphenated_and_spaced_name(index):
    index.import_nodes([
        node("n1", "персонажи/Генрих.md", "Генрих-Фауст прибыл. Генрих Фауст сел.")
    ])
    index.create_entity("heinrich", "Генрих Фауст")
    found = index.search_entity("Генрих Фауст")
    assert len(found["results"]) == 1
    assert len(index.mentions_for_entity("heinrich")) == 2


def test_normalizer_engine_is_recorded_in_database(index):
    check = index.check()
    assert check["morphology_engine"] == index.morphology.engine


def test_apostrophes_and_em_dash_variants(index):
    index.import_nodes([node("n1", "docs/names.md", "O'Connor встретил Генриха — Фауста.")])
    assert results(index, "O’Connor")
    assert results(index, "Генрих-Фауста") or results(index, "Генрих Фауста")


def test_entity_rank_precedes_title_and_body_matches(index):
    index.import_nodes([
        node("n1", "персонажи/Дафна Гринграсс.md", "Запись персонажа."),
        node("n2", "сюжет/Встреча.md", "Дафна Гринграсс входит в зал."),
    ])
    index.create_entity("daphne", "Дафна Гринграсс", primary_source_path="персонажи/Дафна Гринграсс.md")
    found = index.search("входит в зал", entities=["Дафна Гринграсс"])
    assert found["results"]
    # Entity matches use tier 1, ahead of lexical results.
    assert all(r["relevance"]["tier"] == 1 for r in found["results"])


def test_source_path_rejects_non_posix_or_traversal(index):
    bad = node("n1", "docs\\a.md", "x")
    with pytest.raises(ImportValidationError):
        index.import_nodes([bad])
    bad2 = node("n2", "../outside.md", "x")
    with pytest.raises(ImportValidationError):
        index.import_nodes([bad2])


def test_mixed_text_and_number_query_requires_both_parts(index):
    index.import_nodes([
        node("n1", "docs/one.md", "Население составляет 18 518 магов."),
        node("n2", "docs/two.md", "Население составляет 20 000 магов."),
        node("n3", "docs/three.md", "Население составляет 18 и 518 отдельных объектов."),
    ])
    found = results(index, "Население 18 518")
    assert {item["node_id"] for item in found} == {"n1"}


def test_canonical_alias_stays_confirmed_when_repeated_in_candidates(index):
    index.create_entity("daphne", "Дафна Гринграсс", aliases=["Дафна Гринграсс", "Дафна"])
    statuses = {a["alias_text"]: a["status"] for a in index.list_entity_aliases("daphne")}
    assert statuses["Дафна Гринграсс"] == "confirmed"
    assert statuses["Дафна"] == "candidate"


def test_reject_unknown_alias_records_rejection(index):
    index.create_entity("person", "Персонаж")
    index.reject_alias("person", "неподтверждённое имя")
    aliases = index.list_entity_aliases("person")
    assert any(a["alias_text"] == "неподтверждённое имя" and a["status"] == "rejected" for a in aliases)


def test_exact_numbers_are_indexed_in_document_title_and_heading(index):
    index.import_nodes([
        node("n1", "документы/18 518.md", "В документе нет этого числа в тексте.", heading=["Справка"]),
        node("n2", "документы/другое.md", "Здесь только другое содержание.", heading=["Значение 18 518"]),
    ])
    found = results(index, "18 518")
    assert {item["node_id"] for item in found} == {"n1", "n2"}


def test_exact_and_morphological_channels_are_separated(index):
    index.import_nodes([
        node("n1", "docs/one.md", "Магами пользовались редко."),
        node("n2", "docs/two.md", "Маг явился позже."),
    ])
    found = results(index, "маг")
    by_id = {item["node_id"]: item for item in found}
    assert by_id["n2"]["relevance"]["tier"] == 4
    assert by_id["n1"]["relevance"]["tier"] == 5
    assert by_id["n1"]["match_type"] == "morphological"


def test_stale_candidates_are_replaced_on_node_update(index):
    old = node("n1", "персонажи/Один.md", "Александр Долохов и Александр Долохов.")
    index.import_nodes([old])
    assert any(c["candidate_text"] == "Александр Долохов" for c in index.list_entity_candidates())
    new = node("n1", "персонажи/Один.md", "В документе остался только нейтральный текст.")
    index.import_nodes([new])
    assert not any(c["candidate_text"] == "Александр Долохов" for c in index.list_entity_candidates())


def test_candidate_records_are_removed_when_node_is_deleted(index):
    index.import_nodes([node("n1", "персонажи/Один.md", "Александр Долохов появился дважды: Александр Долохов.")])
    assert index.list_entity_candidates()
    index.import_nodes([], {"mode": "delta", "deleted_node_ids": ["n1"]})
    assert index.list_entity_candidates() == []



def test_get_node_returns_executor3_full_source_contract(index):
    original = "Первоначальный текст\nсо второй строкой."
    item = node("n1", "персонажи/Генрих Фауст.md", original, line=11)
    index.import_nodes([item])

    retrieved = index.get_node("n1", item["content_hash"])
    assert retrieved is not None
    assert retrieved["raw_text"] == original
    assert "excerpt" not in retrieved
    assert retrieved["content_hash"] == item["content_hash"]
    assert retrieved["line_start"] == 11
    assert retrieved["line_end"] == 12
    assert isinstance(retrieved["index_generation"], int)
    assert retrieved["index_generation"] >= 1
    assert retrieved["document_hash"] is None


def test_optional_document_hash_is_preserved_and_not_fabricated(index):
    item = node("n1", "docs/A.md", "node content")
    document_hash = "sha256:" + hashlib.sha256(b"full original markdown file").hexdigest()
    item["document_hash"] = document_hash
    index.import_nodes([item])
    assert index.get_node("n1")["document_hash"] == document_hash

    changed = node("n1", "docs/A.md", "changed node content")
    index.import_nodes([changed])
    # A changed source without a new whole-document hash must not retain stale provenance.
    assert index.get_node("n1")["document_hash"] is None


def test_invalid_optional_document_hash_is_rejected(index):
    item = node("n1", "docs/A.md", "text")
    item["document_hash"] = "not-a-sha256"
    with pytest.raises(ImportValidationError, match="document_hash"):
        index.import_nodes([item])


def test_search_hits_match_executor3_search_schema_basics(index):
    index.import_nodes([node("n1", "docs/A.md", "Точное содержание для проверки.", heading=["Проверка"])])
    response = results(index, "содержание")
    assert response
    hit = response[0]
    required = {"node_id", "source_path", "heading_path", "line_start", "line_end", "content_hash",
                "excerpt", "match_type", "match_reasons", "relevance"}
    assert required.issubset(hit)
    assert 1 <= hit["relevance"]["tier"] <= 6
    assert isinstance(hit["relevance"]["bm25"], (int, float))


def test_v1_database_migrates_to_v2_document_provenance(tmp_path):
    db_path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE documents (
            source_path TEXT PRIMARY KEY,
            state TEXT NOT NULL CHECK(state IN ('active','deleted')) DEFAULT 'active',
            last_generation INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE node_versions (
            version_id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            source_path TEXT NOT NULL,
            node_type TEXT NOT NULL,
            parent_node_id TEXT,
            heading_path_json TEXT NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            raw_text TEXT NOT NULL,
            title_original TEXT NOT NULL,
            path_original TEXT NOT NULL,
            heading_original TEXT NOT NULL,
            title_lemmas TEXT NOT NULL,
            heading_lemmas TEXT NOT NULL,
            raw_lemmas TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(node_id, content_hash)
        );
    """)
    conn.close()

    migrated = SFRAIndex(db_path)
    conn = sqlite3.connect(db_path)
    try:
        document_columns = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
        version_columns = {row[1] for row in conn.execute("PRAGMA table_info(node_versions)")}
        assert "document_hash" in document_columns
        assert {"index_generation", "document_hash"}.issubset(version_columns)
    finally:
        conn.close()
    assert migrated.check()["ok"]


def test_entity_search_returns_explicit_primary_document_first(index):
    index.import_nodes([
        node("n1", "z/Other.md", "Дафна Гринграсс упоминается здесь."),
        node("n2", "a/Primary.md", "Карточка персонажа."),
    ])
    index.create_entity("daphne", "Дафна Гринграсс", primary_source_path="a/Primary.md")
    found = index.search_entity("Дафна Гринграсс")
    assert found["results"]
    assert found["results"][0]["node_id"] == "n2"
    assert found["results"][0]["is_primary_entity_document"] is True
    assert all(r["relevance"]["tier"] == 1 for r in found["results"])


def test_search_excerpt_is_bounded_but_get_node_returns_full_source(index):
    original = ("Начальный абзац без искомого термина. " * 30) + "Уникальный маркер контекста." + (" Хвостовой текст." * 30)
    item = node("n1", "docs/long.md", original)
    index.import_nodes([item])

    hit = results(index, "Уникальный маркер контекста")[0]
    full = index.get_node("n1", item["content_hash"])

    assert len(hit["excerpt"]) <= 422
    assert "Уникальный маркер" in hit["excerpt"]
    assert full["raw_text"] == original
    assert len(full["raw_text"]) > len(hit["excerpt"])
    assert full["content_hash"] == hit["content_hash"]


def test_search_hit_has_executor3_provenance_and_rank_fields(index):
    item = node("n1", "docs/provenance.md", "Проверяемая исходная информация.")
    index.import_nodes([item])
    hit = results(index, "исходная")[0]

    assert hit["node_id"] == item["node_id"]
    assert hit["source_path"] == item["source_path"]
    assert hit["content_hash"] == item["content_hash"]
    assert hit["line_start"] == 1 and hit["line_end"] == 1
    assert hit["heading_path"] == []
    assert isinstance(hit["match_reasons"], list)
    assert 1 <= hit["relevance"]["tier"] <= 6
    assert isinstance(hit["relevance"]["bm25"], (float, int))
    source = index.get_node(hit["node_id"], hit["content_hash"])
    assert source["raw_text"] == item["raw_text"]
    assert source["index_generation"] >= 1
    assert source["document_hash"] is None
