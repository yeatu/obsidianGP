"""Typed data model for the SFRA structural parser (stage B)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Source slice with 1-based inclusive lines and 0-based half-open offsets.

    Character offsets count Python Unicode code points. Byte offsets count UTF-8
    bytes. End offsets are exclusive, matching Python slicing semantics.
    """

    line_start: int
    line_end: int
    char_start: int
    char_end: int
    byte_start: int
    byte_end: int


@dataclass(slots=True)
class StructuralNode:
    """A structural unit in the parsed Markdown tree.

    node_id and content_hash are intentionally unset in stage B; stable identity
    and versioning are the scope of stage C. local_key is parse-local and is not
    a persistent Node ID.
    """

    local_key: str
    source_path: str
    node_type: str
    span: SourceSpan
    heading_path: tuple[str, ...] = ()
    parent_key: str | None = None
    raw_text: str = ""
    content_spans: tuple[SourceSpan, ...] = ()
    children: list[StructuralNode] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    node_id: str | None = None
    content_hash: str | None = None

    @property
    def line_start(self) -> int:
        return self.span.line_start

    @property
    def line_end(self) -> int:
        return self.span.line_end

    @property
    def char_start(self) -> int:
        return self.span.char_start

    @property
    def char_end(self) -> int:
        return self.span.char_end

    @property
    def byte_start(self) -> int:
        return self.span.byte_start

    @property
    def byte_end(self) -> int:
        return self.span.byte_end


@dataclass(frozen=True, slots=True)
class Passage:
    """An exact source passage; its context is deliberately stored separately."""

    passage_key: str
    source_path: str
    owner_node_key: str
    span: SourceSpan
    raw_text: str
    context_text: str = ""
    context_spans: tuple[SourceSpan, ...] = ()
    estimated_words: int = 0
    warnings: tuple[str, ...] = ()


@dataclass(slots=True)
class ParsedDocument:
    source_path: str
    raw_text: str
    root: StructuralNode
    passages: list[Passage] = field(default_factory=list)
    parser_name: str = "markdown-it-py"
    parser_version: str = "unknown"

    def iter_nodes(self):
        """Yield nodes in stable depth-first source order."""
        stack = [self.root]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))

    def get_node(self, local_key: str) -> StructuralNode:
        for node in self.iter_nodes():
            if node.local_key == local_key:
                return node
        raise KeyError(local_key)

    def extract_node(self, local_key: str) -> str:
        node = self.get_node(local_key)
        return self.raw_text[node.char_start : node.char_end]
