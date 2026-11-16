"""Integration smoke test for the six project documents named in the SFRA task."""
from pathlib import Path
import hashlib
import unittest

from tools.sfra_indexer import parse_document

ROOT = Path(__file__).resolve().parents[1] / "ГП"
SAMPLES = [
    "персонажи/ученики/Молодая кровь/Генрих Фауст.md",
    "персонажи/ученики/Аристократия/Дафна и Грейс и Рон/Дафна Гринграсс.md",
    "фракции/Рэддл.md",
    "персонажи/ученики/Иное/Перси Уизли.md",
    "персонажи/преподаватели/Преподаватели.md",
    "иное/Демография.md",
]


class ProjectSampleTests(unittest.TestCase):
    @unittest.skipUnless(ROOT.is_dir(), "Run inside the obsidianGP repository")
    def test_six_requested_documents(self) -> None:
        for relative in SAMPLES:
            with self.subTest(path=relative):
                path = ROOT / relative
                raw = path.read_bytes()
                text = raw.decode("utf-8")
                document = parse_document(path, ROOT)
                self.assertEqual(document.sha256, hashlib.sha256(raw).hexdigest())
                self.assertGreaterEqual(len(document.nodes), 1)
                for node in document.nodes:
                    self.assertEqual(node.source_text, text[node.start_char:node.end_char])
                    self.assertLessEqual(node.end_byte, len(raw))


if __name__ == "__main__":
    unittest.main()
