from __future__ import annotations

from pathlib import Path
import re

import pytest

from tests.sfra_indexer.adapter import (
    AdapterNotConfigured,
    NodeView,
    expected_content_hash,
    iter_nodes,
)


FIXTURE_NAMES = (
    "headings_and_duplicates.md",
    "nested_lists.md",
    "block_structures.md",
    "code_links_unicode.md",
    "whitespace.md",
    "crlf_unicode.md",
    "no_headings_mixed.md",
    "empty.md",
)


def read_source(path: Path) -> str:
    # Read bytes first so universal-newline conversion cannot alter the source.
    return path.read_bytes().decode("utf-8")


def get_nodes(result) -> list[NodeView]:
    try:
        return list(iter_nodes(result))
    except AdapterNotConfigured as exc:
        pytest.skip(str(exc))


def assert_source_integrity(source: str, nodes: list[NodeView]) -> None:
    ids = [node.node_id for node in nodes]
    assert len(ids) == len(set(ids)), "node_id должен быть уникальным в документе"
    by_id = {node.node_id: node for node in nodes}
    raw_bytes = source.encode("utf-8")

    for node in nodes:
        assert 0 <= node.char_start <= node.char_end <= len(source), (
            f"Некорректный char-диапазон {node.node_id}"
        )
        assert node.source_text == source[node.char_start:node.char_end], (
            f"Потеря/изменение исходного фрагмента в узле {node.node_id}"
        )

        assert 0 <= node.utf8_byte_start <= node.utf8_byte_end <= len(raw_bytes), (
            f"Некорректный UTF-8 byte-диапазон {node.node_id}"
        )
        expected_byte_start = len(source[:node.char_start].encode("utf-8"))
        expected_byte_end = len(source[:node.char_end].encode("utf-8"))
        assert node.utf8_byte_start == expected_byte_start
        assert node.utf8_byte_end == expected_byte_end
        assert raw_bytes[node.utf8_byte_start:node.utf8_byte_end].decode("utf-8") == node.source_text

        assert node.line_start == source.count("\n", 0, node.char_start) + 1
        if node.char_end > node.char_start:
            expected_line_end = source.count("\n", 0, node.char_end) + 1
            if node.char_end == len(source) and not source.endswith("\n"):
                expected_line_end += 1
            assert node.line_end_exclusive == expected_line_end
        else:
            assert node.line_end_exclusive == node.line_start

        assert node.content_hash == expected_content_hash(node.source_text), (
            f"Content Hash не соответствует исходному фрагменту узла {node.node_id}"
        )
        if node.round_trip_exact is not None:
            assert node.round_trip_exact is True

        if node.parent_id is not None:
            assert node.parent_id in by_id, (
                f"Узел {node.node_id} ссылается на отсутствующего родителя {node.parent_id}"
            )
            parent = by_id[node.parent_id]
            assert parent.char_start <= node.char_start
            assert parent.char_end >= node.char_end, (
                f"Диапазон родителя {parent.node_id} не охватывает потомка {node.node_id}"
            )

        # Parent links must form a tree/forest, never a cycle.
        seen = {node.node_id}
        current = node
        while current.parent_id is not None:
            assert current.parent_id not in seen, f"Цикл в иерархии узла {node.node_id}"
            seen.add(current.parent_id)
            current = by_id[current.parent_id]

    if not source:
        assert all(node.source_text == "" for node in nodes)
        return

    # Every meaningful source character must belong to at least one node.
    # ASCII whitespace between Markdown blocks may be a separator rather than
    # a node. NBSP is treated as content and must remain in an exact source span.
    # Overlapping parent/child spans are expected and harmless.
    intervals = sorted(
        (node.char_start, node.char_end)
        for node in nodes
        if node.char_end > node.char_start
    )
    merged: list[tuple[int, int]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    span_index = 0
    for offset, char in enumerate(source):
        is_content = not char.isspace() or char == "\\u00a0"
        if not is_content:
            continue
        while span_index < len(merged) and merged[span_index][1] <= offset:
            span_index += 1
        assert span_index < len(merged) and merged[span_index][0] <= offset < merged[span_index][1], (
            f"Исходный символ на позиции {offset} не представлен ни одним узлом: {char!r}"
        )


def parse_fixture(indexer_api, fixture_path: Path, fixtures_root: Path) -> list[NodeView]:
    result = indexer_api.parse_document(str(fixture_path), str(fixtures_root))
    return get_nodes(result)


def test_fixture_corpus_is_self_contained(fixtures_root: Path) -> None:
    assert all((fixtures_root / name).is_file() for name in FIXTURE_NAMES)
    assert read_source(fixtures_root / "empty.md") == ""


def test_fixture_corpus_covers_required_markdown_cases(fixtures_root: Path) -> None:
    read = lambda name: read_source(fixtures_root / name)

    headings = read("headings_and_duplicates.md")
    levels = {len(match) for match in re.findall(r"^(#{1,6})\s", headings, re.M)}
    assert levels == {1, 2, 3, 4, 5, 6}
    assert headings.count("## Повторяющийся раздел") == 2

    lists = read("nested_lists.md")
    assert re.search(r"^      - ", lists, re.M)
    assert "КОНЕЦ-ДЛИННОГО-ПУНКТА" in lists
    list_lines = [line for line in lists.splitlines() if re.match(r"^[ \t]*[-*+] ", line)]
    assert len(list_lines) >= 8
    assert not any(line == "" for line in lists.splitlines()[:5])

    blocks = read("block_structures.md")
    assert re.search(r"^\| Колонка \| Значение \|", blocks, re.M)
    assert "> Это первая строка цитаты." in blocks
    assert "> [!NOTE]" in blocks

    code_and_links = read("code_links_unicode.md")
    assert code_and_links.count(chr(96) * 3) == 2
    assert "[официальная документация](https://example.org/reference?q=sfra)" in code_and_links
    assert "Ёжик, чародейство и ГП" in code_and_links

    whitespace = read("whitespace.md")
    assert "\u00a0" in whitespace
    assert "\n\n\n" in whitespace

    crlf_unicode = read("crlf_unicode.md")
    assert "\r\n" in crlf_unicode
    assert "🧙" in crlf_unicode
    assert len("🧙") == 1
    assert len("🧙".encode("utf-8")) == 4

    unheaded = read("no_headings_mixed.md")
    assert not re.search(r"^#{1,6}\s", unheaded, re.M)
    assert "| Параметр | Значение |" in unheaded
    assert "- Первый пункт" in unheaded
    assert "> Цитата без заголовка." in unheaded


@pytest.mark.parametrize("filename", FIXTURE_NAMES)
@pytest.mark.integration
def test_fixture_source_spans_hashes_and_hierarchy(
    indexer_api, fixtures_root: Path, filename: str
) -> None:
    path = fixtures_root / filename
    source = read_source(path)
    nodes = parse_fixture(indexer_api, path, fixtures_root)
    assert_source_integrity(source, nodes)


@pytest.mark.integration
def test_heading_levels_and_duplicate_titles(indexer_api, fixtures_root: Path) -> None:
    path = fixtures_root / "headings_and_duplicates.md"
    nodes = parse_fixture(indexer_api, path, fixtures_root)
    headings = [node for node in nodes if node.kind == "heading"]
    assert {node.level for node in headings} >= {1, 2, 3, 4, 5, 6}
    duplicates = [
        node for node in headings
        if (node.label or "").strip() == "Повторяющийся раздел"
    ]
    assert len(duplicates) == 2
    assert duplicates[0].node_id != duplicates[1].node_id


@pytest.mark.integration
def test_nested_lists_keep_depth_long_text_and_parent_context(
    indexer_api, fixtures_root: Path
) -> None:
    path = fixtures_root / "nested_lists.md"
    nodes = parse_fixture(indexer_api, path, fixtures_root)
    items = [node for node in nodes if node.kind == "list_item"]
    assert items

    depths = []
    for item in items:
        depth = 1
        parent_id = item.parent_id
        seen = {item.node_id}
        while parent_id is not None:
            assert parent_id not in seen
            seen.add(parent_id)
            parent = next((node for node in nodes if node.node_id == parent_id), None)
            if parent is None:
                break
            if parent.kind == "list_item":
                depth += 1
            parent_id = parent.parent_id
        if item.level is not None:
            depth = max(depth, item.level)
        depths.append(depth)
    assert max(depths) >= 4, "Должны сохраниться минимум четыре уровня списка"

    def first_list_line(node: NodeView) -> str:
        first = next((line for line in node.source_text.splitlines() if line.strip()), "")
        return first.lstrip()

    parent = next(
        node for node in items
        if first_list_line(node).startswith("- Родительский пункт")
    )
    child = next(
        node for node in items
        if first_list_line(node).startswith("- Дочернее ограничение")
    )
    assert child.parent_id == parent.node_id
    assert "родительское правило" in parent.source_text.lower()
    assert parent.char_start <= child.char_start < child.char_end <= parent.char_end

    long_item = next(
        node for node in items
        if first_list_line(node).startswith("- Начало длинного пункта")
    )
    assert "КОНЕЦ-ДЛИННОГО-ПУНКТА" in long_item.source_text


@pytest.mark.integration
def test_markdown_blocks_are_not_merged_or_retyped(indexer_api, fixtures_root: Path) -> None:
    path = fixtures_root / "block_structures.md"
    nodes = parse_fixture(indexer_api, path, fixtures_root)
    kinds = {node.kind for node in nodes}
    assert "table" in kinds
    assert "quote" in kinds
    assert "callout" in kinds


@pytest.mark.integration
def test_code_fence_links_and_unicode_survive(indexer_api, fixtures_root: Path) -> None:
    path = fixtures_root / "code_links_unicode.md"
    source = read_source(path)
    nodes = parse_fixture(indexer_api, path, fixtures_root)
    kinds = {node.kind for node in nodes}
    assert "code_block" in kinds
    code_nodes = [node for node in nodes if node.kind == "code_block"]
    assert any("## Это не заголовок" in node.source_text for node in code_nodes)
    assert not any(
        node.kind == "heading" and "Это не заголовок" in (node.label or "")
        for node in nodes
    )
    assert "[официальная документация](https://example.org/reference?q=sfra)" in source
    assert "Ёжик, чародейство и ГП" in source
    assert any("https://example.org/reference?q=sfra" in node.source_text for node in nodes)


@pytest.mark.integration
def test_whitespace_and_nbsp_are_preserved(indexer_api, fixtures_root: Path) -> None:
    path = fixtures_root / "whitespace.md"
    source = read_source(path)
    nodes = parse_fixture(indexer_api, path, fixtures_root)
    assert "\u00a0" in source
    assert any("\u00a0" in node.source_text for node in nodes)
    assert "\n\n\n" in source
    assert any("\n\n\n" in node.source_text for node in nodes)


@pytest.mark.integration
def test_crlf_and_unicode_use_consistent_char_and_byte_coordinates(
    indexer_api, fixtures_root: Path
) -> None:
    path = fixtures_root / "crlf_unicode.md"
    source = read_source(path)
    assert "\r\n" in source
    nodes = parse_fixture(indexer_api, path, fixtures_root)
    assert_source_integrity(source, nodes)
    assert any(
        node.utf8_byte_end - node.utf8_byte_start
        > node.char_end - node.char_start
        for node in nodes
    )


@pytest.mark.integration
def test_documents_without_headings_and_empty_documents_are_valid(
    indexer_api, fixtures_root: Path
) -> None:
    no_heading_path = fixtures_root / "no_headings_mixed.md"
    source = read_source(no_heading_path)
    nodes = parse_fixture(indexer_api, no_heading_path, fixtures_root)
    assert nodes
    assert not any(node.kind == "heading" for node in nodes)
    assert_source_integrity(source, nodes)

    empty_path = fixtures_root / "empty.md"
    empty_nodes = parse_fixture(indexer_api, empty_path, fixtures_root)
    assert_source_integrity("", empty_nodes)
