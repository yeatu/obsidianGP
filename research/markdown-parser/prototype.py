#!/usr/bin/env python3
"""Inspect Markdown block structure while preserving exact source slices.

Coordinates:
- lines: 1-based, end-exclusive
- char offsets: Python Unicode code-point indices, end-exclusive
- byte offsets: UTF-8 byte indices, end-exclusive

The source file is never reconstructed from parser tokens. All excerpts are
sliced from the original string using token.map line boundaries.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt


def make_line_starts(source: str) -> list[int]:
    """Return Python-string offsets for the beginning of each physical line."""
    starts = [0]
    for i, char in enumerate(source):
        if char == "\n":
            starts.append(i + 1)
    return starts


def line_range_to_char_range(
    starts: list[int], source_length: int, start_line0: int, end_line0: int
) -> tuple[int, int]:
    start = starts[start_line0]
    end = starts[end_line0] if end_line0 < len(starts) else source_length
    return start, end


def char_to_utf8_byte_offset(source: str, char_offset: int) -> int:
    return len(source[:char_offset].encode("utf-8"))


def walk_tokens(tokens: list[Any]):
    """Yield opening/block tokens and preserve nesting information."""
    for token in tokens:
        if token.map is not None and token.nesting != -1:
            yield token
        if token.children:
            yield from walk_tokens(token.children)


def extract_blocks(source: str) -> list[dict[str, Any]]:
    # gfm-like2 includes tables, task lists and GitHub-style alerts. Obsidian
    # callouts use the same blockquote shape and are detected from source text.
    md = MarkdownIt("gfm-like2")
    tokens = md.parse(source)
    starts = make_line_starts(source)
    found: list[dict[str, Any]] = []
    heading_counts: dict[str, int] = {}

    for token in walk_tokens(tokens):
        kind = token.type
        if kind not in {
            "heading_open", "list_item_open", "blockquote_open",
            "fence", "code_block", "table_open"
        }:
            continue

        start_line0, end_line0 = token.map
        char_start, char_end = line_range_to_char_range(
            starts, len(source), start_line0, end_line0
        )
        excerpt = source[char_start:char_end]

        # Inline heading content is on the next token, not in heading_open.
        title = None
        if kind == "heading_open":
            title = ""
            # The exact title text is deliberately not reconstructed here.
            # The heading's original source line remains in excerpt.
            heading_counts[excerpt] = heading_counts.get(excerpt, 0) + 1

        is_callout = (
            kind == "blockquote_open"
            and any(line.lstrip().startswith("> [!") for line in excerpt.splitlines())
        )
        if kind == "blockquote_open" and not is_callout:
            label = "blockquote"
        elif is_callout:
            label = "obsidian_callout"
        else:
            label = kind.removesuffix("_open")

        byte_start = char_to_utf8_byte_offset(source, char_start)
        byte_end = char_to_utf8_byte_offset(source, char_end)
        exact = source[char_start:char_end] == excerpt

        item: dict[str, Any] = {
            "type": label,
            "line_start": start_line0 + 1,
            "line_end_exclusive": end_line0 + 1,
            "char_start": char_start,
            "char_end": char_end,
            "utf8_byte_start": byte_start,
            "utf8_byte_end": byte_end,
            "source": excerpt,
            "round_trip_exact": exact,
        }
        if title is not None:
            item["occurrence"] = heading_counts[excerpt]
        found.append(item)

    return found


def inspect_file(path: Path) -> dict[str, Any]:
    # newline="" prevents universal-newline conversion: CRLF remains CRLF.
    with path.open("r", encoding="utf-8", newline="") as stream:
        source = stream.read()
    blocks = extract_blocks(source)
    return {
        "file": str(path),
        "encoding": "utf-8",
        "newline_counts": {
            "LF": source.count("\n"),
            "CRLF": source.count("\r\n"),
            "lone_CR": source.count("\r") - source.count("\r\n"),
        },
        "blocks": blocks,
        "all_round_trip_exact": all(x["round_trip_exact"] for x in blocks),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path, help="Markdown files to inspect")
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    args = parser.parse_args()

    result = [inspect_file(path) for path in args.files]
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
