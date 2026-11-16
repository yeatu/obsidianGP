"""Adapter from the not-yet-frozen SFRA result schema to this test suite.

Do not change the public SFRA API to satisfy this module. Map its actual result
objects into NodeView after the implementation/schema is available.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Iterable


class AdapterNotConfigured(NotImplementedError):
    """Raised until the concrete SFRA result shape is mapped."""


@dataclass(frozen=True)
class NodeView:
    """Stable, test-only representation of one source-backed structural node.

    Coordinate convention follows research/markdown-parser/README.md:
    line_start/line_end_exclusive are 1-based; char and UTF-8 byte offsets are
    0-based, end-exclusive. This is a test contract, not an SFRA API schema.
    """

    node_id: str
    parent_id: str | None
    kind: str
    source_text: str
    line_start: int
    line_end_exclusive: int
    char_start: int
    char_end: int
    utf8_byte_start: int
    utf8_byte_end: int
    content_hash: str
    round_trip_exact: bool | None = None
    level: int | None = None
    label: str | None = None


def iter_nodes(result: Any) -> Iterable[NodeView]:
    """Yield normalized nodes from parse_document()'s actual result.

    Implement this function after inspecting the SFRA v1 result schema.
    Map the implementation's source field to source_text, convert its
    coordinates to the three coordinate systems above, and normalize block
    kinds (for example blockquote -> quote, obsidian_callout -> callout,
    fence -> code_block). Do not infer nodes by searching repeated text.
    """
    raise AdapterNotConfigured(
        "Map parse_document() output to NodeView in tests/sfra_indexer/adapter.py"
    )


def iter_document_paths(result: Any, root_path: Path) -> Iterable[str | Path]:
    """Yield every document path from scan_vault()'s actual result.

    Return absolute paths or paths relative to root_path. Do not silently
    discard entries outside root_path: the boundary test must be able to catch
    them.
    """
    raise AdapterNotConfigured(
        "Map scan_vault() output to paths in tests/sfra_indexer/adapter.py"
    )


def expected_content_hash(source_fragment: str) -> str:
    """Return the test oracle for the Content Hash algorithm.

    SHA-256 over exact UTF-8 source is the harness default. Change this function
    only if the SFRA v1 specification explicitly defines another algorithm.
    """
    return hashlib.sha256(source_fragment.encode("utf-8")).hexdigest()
