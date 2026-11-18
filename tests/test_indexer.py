from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.sfra_indexer import DocumentReadError, build_index, export_index, parse_document, scan_vault


class IndexerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.vault = self.base / "ГП"
        self.vault.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, relative: str, text: str) -> Path:
        path = self.vault / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path

    def test_unicode_offsets_and_hashes_are_exact(self) -> None:
        original = "# Ёж 🦉\r\nТекст из двух слов.\r\n"
        path = self.write("unicode.md", original)
        document = parse_document(path, self.vault)
        root = document.nodes[0]
        self.assertEqual(root.source_text, original)
        self.assertEqual(root.sha256, hashlib.sha256(original.encode("utf-8")).hexdigest())
        for node in document.nodes:
            self.assertEqual(node.source_text, original[node.start_char:node.end_char])
            self.assertEqual(node.start_byte, len(original[:node.start_char].encode("utf-8")))
            self.assertEqual(node.end_byte, len(original[:node.end_char].encode("utf-8")))

    def test_heading_hierarchy_and_section_boundaries(self) -> None:
        text = "# A\nтекст A\n## B\nтекст B\n# C\nконец\n"
        path = self.write("heads.md", text)
        document = parse_document(path, self.vault)
        headings = [node for node in document.nodes if node.type.startswith("heading_")]
        self.assertEqual([node.attributes["title"] for node in headings], ["A", "B", "C"])
        self.assertEqual(headings[1].parent_id, headings[0].id)
        self.assertEqual(headings[0].source_text, "# A\nтекст A\n## B\nтекст B\n")
        self.assertEqual(headings[1].source_text, "## B\nтекст B\n")

    def test_nested_lists_are_hierarchical(self) -> None:
        text = "- first\n  - child\n    1. grandchild\n- second\n"
        path = self.write("lists.md", text)
        document = parse_document(path, self.vault)
        items = [node for node in document.nodes if node.type == "list_item"]
        self.assertEqual([node.attributes["depth"] for node in items], [0, 1, 2, 0])
        self.assertEqual(items[1].parent_id, items[0].id)
        self.assertEqual(items[2].parent_id, items[1].id)
        self.assertEqual(items[0].source_text, "- first\n  - child\n    1. grandchild\n")

    def test_callout_quote_table_and_fenced_code(self) -> None:
        text = (
            "> [!warning]- Важно\n> Текст\n\n"
            "> обычная цитата\n\n"
            "| имя | значение |\n|:---|---:|\n| ёж | 42 |\n\n"
            "```python\nprint('x')\n```\n"
        )
        path = self.write("blocks.md", text)
        document = parse_document(path, self.vault)
        types = [node.type for node in document.nodes]
        self.assertIn("callout", types)
        self.assertIn("blockquote", types)
        self.assertIn("table", types)
        self.assertEqual(types.count("table_row"), 3)
        self.assertEqual(types.count("table_cell"), 6)
        code = next(node for node in document.nodes if node.type == "code_block")
        self.assertTrue(code.attributes["closed"])
        self.assertEqual(code.attributes["language"], "python")

    def test_empty_document_is_valid(self) -> None:
        path = self.write("empty.md", "")
        document = parse_document(path, self.vault)
        self.assertEqual(document.byte_count, 0)
        self.assertEqual(document.line_count, 0)
        self.assertEqual(len(document.nodes), 1)
        self.assertEqual(document.nodes[0].sha256, hashlib.sha256(b"").hexdigest())

    def test_scan_is_recursive_and_only_markdown(self) -> None:
        self.write("nested/one.md", "x")
        self.write("nested/two.MD", "y")
        self.write("nested/no.txt", "z")
        (self.base / "outside.md").write_text("not in vault", encoding="utf-8")
        paths = scan_vault(self.vault)
        self.assertEqual(
            [path.relative_to(self.vault).as_posix() for path in paths],
            ["nested/one.md", "nested/two.MD"],
        )

    def test_invalid_utf8_is_diagnostic_and_does_not_drop_other_docs(self) -> None:
        (self.vault / "broken.md").write_bytes(b"\xff\xfe")
        self.write("good.md", "# ok\n")
        result = build_index(self.vault)
        self.assertEqual(result.stats["documents_indexed"], 1)
        self.assertEqual(result.stats["documents_failed"], 1)
        self.assertEqual(result.diagnostics[0].code, "invalid_utf8")
        self.assertEqual(result.documents[0].path, "good.md")

    def test_path_escape_is_rejected(self) -> None:
        outside = self.base / "outside.md"
        outside.write_text("x", encoding="utf-8")
        with self.assertRaises(DocumentReadError):
            parse_document(outside, self.vault)

    def test_json_export_and_output_guard(self) -> None:
        self.write("one.md", "# тест\nтекст\n")
        result = build_index(self.vault)
        output = self.base / "sfra_index.json"
        export_index(result, output)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["stats"]["documents_indexed"], 1)
        with self.assertRaises(ValueError):
            export_index(result, self.vault / "index.json")


if __name__ == "__main__":
    unittest.main()
