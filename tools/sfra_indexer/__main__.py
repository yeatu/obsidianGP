from __future__ import annotations

import argparse
import json

from .indexer import build_index, export_index


def main() -> int:
    parser = argparse.ArgumentParser(description="Структурный индексатор Markdown-файлов SFRA.")
    parser.add_argument("--root", default="ГП", help="Индексируемый каталог (по умолчанию: ГП)")
    parser.add_argument("--output", default="sfra_index.json", help="JSON-индекс вне --root")
    args = parser.parse_args()
    result = build_index(args.root)
    output = export_index(result, args.output)
    print(json.dumps({"output": str(output), "stats": result.stats, "diagnostics": [d.__dict__ for d in result.diagnostics]}, ensure_ascii=False, indent=2))
    return 1 if result.diagnostics else 0


if __name__ == "__main__":
    raise SystemExit(main())
