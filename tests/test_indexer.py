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

    def test_unicode_offsets_and_hashes(self) -> None:
        original = "# Ёж 🦉\r\nТекст.\r\n"
        path = self.write("unicode.md", original)
        document = parse_document(path, self.vault)
        self.assertEqual(document.nodes[0].source_text, original)
        self.assertEqual(document.sha256, hashlib.sha256(original.encode()).hexdigest())
        for node in document.nodes:
            self.assertEqual(node.source_text, original[node.start_char:node.end_char])
            self.assertEqual(node.start_byte, len(original[:node.start_char].encode()))
            self.assertEqual(node.end_byte, len(original[:node.end_char].encode()))

    def test_heading_sections_and_nested_lists(self) -> None:
        text = "# A\nтекст A\n## B\nтекст B\n# C\n- first\n  - child\n"
        path = self.write("structure.md", text)
        document = parse_document(path, self.vault)
        headings = [node for node in document.nodes if node.type.startswith("heading_")]
        self.assertEqual([n.attributes["title"] for n in headings], ["A", "B", "C"])
        self.assertEqual(headings[1].parent_id, headings[0].id)
        self.assertEqual(headings[0].source_text, "# A\nтекст A\n## B\nтекст B\n")
        items = [node for node in document.nodes if node.type == "list_item"]
        self.assertEqual([n.attributes["depth"] for n in items], [0, 1])
        self.assertEqual(items[1].parent_id, items[0].id)

    def test_callout_quote_table_and_code(self) -> None:
        text = (
            "> [!warning]- Важно\n> Тело\n\n> Цитата\n\n"
            "| имя | значение |\n|:---|---:|\n| ёж | 42 |\n\n"
            "```python\nprint('x')\n```\n"
        )
        path = self.write("blocks.md", text)
        document = parse_document(path, self.vault)
        types = [node.type for node in document.nodes]
        for expected in ("callout", "blockquote", "table", "code_block", "table_row", "table_cell"):
            self.assertIn(expected, types)
        code = next(node for node in document.nodes if node.type == "code_block")
        self.assertTrue(code.attributes["closed"])
        self.assertEqual(code.attributes["language"], "python")

    def test_empty_file_and_utf8_error_diagnostic(self) -> None:
        self.write("empty.md", "")
        (self.vault / "bad.md").write_bytes(b"\xff\xfe")
        self.write("good.md", "ok\n")
        result = build_index(self.vault)
        self.assertEqual(result.stats["documents_indexed"], 2)
        self.assertEqual(result.stats["documents_failed"], 1)
        self.assertEqual(next(d for d in result.documents if d.path == "empty.md").byte_count, 0)
        self.assertEqual(result.diagnostics[0].code, "invalid_utf8")

    def test_scan_is_recursive_and_export_is_outside_vault(self) -> None:
        self.write("nested/one.md", "x")
        self.write("nested/no.txt", "ignored")
        (self.base / "outside.md").write_text("outside", encoding="utf-8")
        paths = scan_vault(self.vault)
        self.assertEqual([p.relative_to(self.vault).as_posix() for p in paths], ["nested/one.md"])
        result = build_index(self.vault)
        output = self.base / "sfra_index.json"
        export_index(result, output)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["stats"]["documents_indexed"], 1)
        with self.assertRaises(ValueError):
            export_index(result, self.vault / "bad-index.json")

    def test_path_escape_is_rejected(self) -> None:
        outside = self.base / "outside.md"
        outside.write_text("x", encoding="utf-8")
        with self.assertRaises(DocumentReadError):
            parse_document(outside, self.vault)


if __name__ == "__main__":
    unittest.main()
