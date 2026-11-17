from __future__ import annotations

import bisect

import pytest

from sfra_indexer import extract_source_slice, parse_markdown, validate_parsed_document


def nodes_of(parsed, node_type):
    return [node for node in parsed.iter_nodes() if node.node_type == node_type]


def test_nested_headings_h1_through_h6_and_parent_own_spans():
    source = (
        "# H1\nintro\n"
        "## H2\ntext 2\n"
        "### H3\ntext 3\n"
        "#### H4\ntext 4\n"
        "##### H5\ntext 5\n"
        "###### H6\ntext 6\n"
        "## H2 sibling\nlast\n"
    )
    parsed = parse_markdown(source, "headings.md", max_passage_words=0)
    headings = nodes_of(parsed, "heading")
    assert [h.metadata["level"] for h in headings] == [1, 2, 3, 4, 5, 6, 2]
    assert headings[5].heading_path == ("H1", "H2", "H3", "H4", "H5", "H6")

    h1 = headings[0]
    assert h1.raw_text == source
    own_text = [extract_source_slice(source, span) for span in h1.content_spans]
    assert "# H1\n" in own_text
    assert "intro\n" in own_text
    assert "## H2\n" not in own_text


def test_document_without_headings_uses_block_boundaries():
    source = "First paragraph.\n\nSecond paragraph with [link](https://example.org).\n\n> quotation\n"
    parsed = parse_markdown(source, "flat.md", max_passage_words=0)
    assert len(nodes_of(parsed, "heading")) == 0
    assert len(nodes_of(parsed, "paragraph")) == 2
    assert len(nodes_of(parsed, "quote")) == 1
    paragraph = nodes_of(parsed, "paragraph")[1]
    assert paragraph.metadata["link_targets"] == ["https://example.org"]


def test_empty_document_is_valid():
    parsed = parse_markdown("", "empty.md")
    assert parsed.root.raw_text == ""
    assert parsed.root.span.char_start == parsed.root.span.char_end == 0
    assert list(parsed.iter_nodes()) == [parsed.root]


def test_nested_lists_keep_parent_child_relationship_and_own_content():
    source = "- Parent item\n  - Child item\n    - Grandchild\n- Second parent\n"
    parsed = parse_markdown(source, "lists.md", max_passage_words=0)
    lists = nodes_of(parsed, "list")
    items = nodes_of(parsed, "list_item")
    assert len(lists) == 3
    assert len(items) == 4

    parent_item = items[0]
    child_list = next(child for child in parent_item.children if child.node_type == "list")
    assert child_list.parent_key == parent_item.local_key
    assert parent_item.raw_text == "- Parent item\n  - Child item\n    - Grandchild\n"
    own = "".join(extract_source_slice(source, span) for span in parent_item.content_spans)
    assert "Parent item" in own
    assert "Child item" not in own
    assert "Grandchild" not in own


def test_obsidian_callout_is_one_atomic_node():
    source = "> [!WARNING] Осторожно\n> Первая строка\n> - вложенный список\n> - ещё строка\n"
    parsed = parse_markdown(source, "callout.md", max_passage_words=0)
    callouts = nodes_of(parsed, "callout")
    assert len(callouts) == 1
    assert callouts[0].metadata["callout_type"] == "warning"
    assert callouts[0].metadata["callout_title"] == "Осторожно"
    assert callouts[0].raw_text == source
    assert len(callouts[0].children) == 0


def test_table_is_kept_as_single_source_block():
    source = "| Имя | Значение |\n| --- | --- |\n| Ёж | 42 |\n| Тест | \x60код\x60 |\n"
    parsed = parse_markdown(source, "table.md", max_passage_words=0)
    tables = nodes_of(parsed, "table")
    assert len(tables) == 1
    assert tables[0].raw_text == source
    assert tables[0].line_start == 1
    assert tables[0].line_end == 4


def test_quotes_code_blocks_and_markdown_links_are_preserved():
    source = (
        "> Обычная цитата\n> Вторая строка\n\n"
        "~~~python\nprint('Привет 🌍')\n~~~\n\n"
        "Ссылка: [Obsidian](https://obsidian.md) и [локальная](./note.md).\n"
    )
    parsed = parse_markdown(source, "mixed.md", max_passage_words=0)
    assert nodes_of(parsed, "quote")[0].raw_text == "> Обычная цитата\n> Вторая строка\n"
    assert nodes_of(parsed, "code_block")[0].raw_text == "~~~python\nprint('Привет 🌍')\n~~~\n"
    linked = [node for node in nodes_of(parsed, "paragraph") if node.metadata.get("link_targets")]
    assert linked[0].metadata["link_targets"] == ["https://obsidian.md", "./note.md"]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_coordinates_unicode_utf8_and_line_endings(newline):
    source = newline.join([
        "# Кириллица — ёж 🧪",
        "",
        "Абзац: café, Ω, 𐍈, русский текст.",
        "",
        "[ссылка](https://example.test/путь?q=ё)",
        "",
    ]) + newline
    parsed = parse_markdown(source, "unicode.md", max_passage_words=0)
    validate_parsed_document(parsed)
    line_starts = [0]
    for index, char in enumerate(source):
        if char == "\n":
            line_starts.append(index + 1)
    if line_starts[-1] != len(source):
        line_starts.append(len(source))
    for node in parsed.iter_nodes():
        extracted = extract_source_slice(source, node.span)
        assert extracted == node.raw_text
        assert source.encode("utf-8")[node.byte_start:node.byte_end].decode("utf-8") == node.raw_text
        assert node.char_end - node.char_start == len(node.raw_text)
        assert node.byte_end - node.byte_start == len(node.raw_text.encode("utf-8"))
        if node.char_start == node.char_end:
            expected_start = max(1, bisect.bisect_right(line_starts, node.char_start))
            expected_end = expected_start - 1
        else:
            expected_start = max(1, bisect.bisect_right(line_starts, node.char_start))
            expected_end = max(1, bisect.bisect_right(line_starts, node.char_end - 1))
        assert (node.line_start, node.line_end) == (expected_start, expected_end)
    para = nodes_of(parsed, "paragraph")[-1]
    assert "https://example.test/путь?q=ё" in para.raw_text


def test_big_section_passages_keep_exact_raw_slice_and_separate_context():
    chunks = [f"Абзац {i}: " + ("важное слово " * 90) for i in range(1, 14)]
    source = "# Большой раздел\n\n" + "\n\n".join(chunks) + "\n"
    parsed = parse_markdown(source, "large.md", max_passage_words=400)
    heading = nodes_of(parsed, "heading")[0]
    passages = [p for p in parsed.passages if p.owner_node_key == heading.local_key]
    assert len(passages) > 1
    for passage in passages:
        assert passage.raw_text == source[passage.span.char_start:passage.span.char_end]
        assert passage.context_text == "# Большой раздел"
        assert passage.context_text not in passage.raw_text
        assert passage.span.byte_end - passage.span.byte_start == len(passage.raw_text.encode("utf-8"))


def test_atomic_oversized_block_is_not_cut_into_arbitrary_characters():
    source = "> [!NOTE] Цельный блок\n> " + ("слово " * 1500) + "\n"
    parsed = parse_markdown(source, "large-callout.md", max_passage_words=100)
    callout = nodes_of(parsed, "callout")[0]
    assert callout.raw_text == source
    assert any("oversized_unsplittable" in warning for warning in callout.warnings)
    assert not [p for p in parsed.passages if p.owner_node_key == callout.local_key]



def test_passages_from_nested_list_keep_parent_condition_as_separate_context():
    source = "\n".join([
        "- Условие: ученик должен сохранять концентрацию.",
        "  - Первый этап испытания: " + ("внимательно наблюдать " * 18),
        "  - Второй этап испытания: " + ("решить поставленную задачу " * 18),
        "  - Третий этап испытания: " + ("подтвердить полученный результат " * 18),
        "",
    ])
    parsed = parse_markdown(source, "nested-condition.md", max_passage_words=20)
    items = nodes_of(parsed, "list_item")
    parent_item = items[0]
    nested_list = next(child for child in parent_item.children if child.node_type == "list")
    passages = [
        passage for passage in parsed.passages
        if passage.owner_node_key == nested_list.local_key
    ]

    assert len(passages) >= 2
    expected_parent_text = extract_source_slice(source, parent_item.content_spans[0])
    for passage in passages:
        assert "ученик должен сохранять концентрацию" in passage.context_text
        assert passage.raw_text == source[passage.span.char_start:passage.span.char_end]
        assert "ученик должен сохранять концентрацию" not in passage.raw_text
        assert any(
            extract_source_slice(source, context_span) == expected_parent_text
            for context_span in passage.context_spans
        )
        assert passage.span.char_start >= parent_item.content_spans[0].char_end
