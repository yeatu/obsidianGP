"""Markdown AST parser that preserves exact source coordinates.

The AST decides structure only. All returned text is sliced from the original
source string; this module never serializes AST nodes back into Markdown.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Iterable

from markdown_it import MarkdownIt

from .models import ParsedDocument, Passage, SourceSpan, StructuralNode


CALLOUT_RE = re.compile(r"^\s*>\s*\[!(?P<kind>[A-Za-z0-9_-]+)\](?:\s*(?P<title>.*))?\s*$")
WORD_RE = re.compile(r"\w+", re.UNICODE)
BLOCK_TYPES = {
    "paragraph_open": "paragraph",
    "bullet_list_open": "list",
    "ordered_list_open": "list",
    "list_item_open": "list_item",
    "blockquote_open": "blockquote",
    "table_open": "table",
    "fence": "code_block",
    "code_block": "code_block",
    "html_block": "html_block",
    "hr": "thematic_break",
}


@dataclass(slots=True)
class _AstNode:
    token: object
    children: list[_AstNode] = field(default_factory=list)

    @property
    def token_type(self) -> str:
        return self.token.type  # type: ignore[attr-defined]

    @property
    def source_map(self) -> list[int] | None:
        return self.token.map  # type: ignore[attr-defined]


class _Offsets:
    """Map markdown-it line maps to exact Python-string / UTF-8 offsets."""

    def __init__(self, source: str):
        self.source = source
        self.line_starts = [0]
        for index, char in enumerate(source):
            if char == "\n":
                self.line_starts.append(index + 1)
        if self.line_starts[-1] != len(source):
            self.line_starts.append(len(source))

        self.byte_prefix = [0]
        total = 0
        for char in source:
            total += len(char.encode("utf-8"))
            self.byte_prefix.append(total)

    def span_from_map(self, source_map: list[int] | None) -> SourceSpan:
        if source_map is None:
            raise ValueError("AST token has no source map")
        start_line, end_line = source_map
        return self.span_from_chars(self._line_offset(start_line), self._line_offset(end_line))

    def span_from_chars(self, start: int, end: int) -> SourceSpan:
        if not (0 <= start <= end <= len(self.source)):
            raise ValueError(f"Invalid source range [{start}, {end}) for {len(self.source)} chars")
        if start == end:
            line_number = max(1, bisect.bisect_right(self.line_starts, start))
            return SourceSpan(line_number, line_number - 1, start, end,
                              self.byte_prefix[start], self.byte_prefix[end])
        line_start = max(1, bisect.bisect_right(self.line_starts, start))
        line_end = max(1, bisect.bisect_right(self.line_starts, end - 1))
        return SourceSpan(line_start, line_end, start, end,
                          self.byte_prefix[start], self.byte_prefix[end])

    def _line_offset(self, line_index: int) -> int:
        # markdown-it maps are 0-based with an exclusive end line.
        if line_index < 0:
            raise ValueError(f"Negative line index: {line_index}")
        if line_index < len(self.line_starts):
            return self.line_starts[line_index]
        if line_index == len(self.line_starts):
            return len(self.source)
        raise ValueError(f"AST line index {line_index} exceeds source line map")


class _NodeFactory:
    def __init__(self, source_path: str, source: str):
        self.source_path = source_path
        self.source = source
        self.counter = 0

    def make(self, node_type: str, span: SourceSpan, heading_path: tuple[str, ...],
             parent: StructuralNode, *, metadata: dict | None = None,
             content_spans: Iterable[SourceSpan] | None = None) -> StructuralNode:
        self.counter += 1
        key = f"n{self.counter:06d}"
        node = StructuralNode(
            local_key=key, source_path=self.source_path, node_type=node_type,
            span=span, heading_path=heading_path, parent_key=parent.local_key,
            raw_text=self.source[span.char_start:span.char_end],
            content_spans=tuple(content_spans if content_spans is not None else (span,)),
            metadata=metadata or {},
        )
        parent.children.append(node)
        return node


def _build_ast_tree(markdown: MarkdownIt, source: str) -> list[_AstNode]:
    tokens = markdown.parse(source)
    root = _AstNode(token=None)
    stack = [root]
    for token in tokens:
        if token.nesting == 1:
            current = _AstNode(token=token)
            stack[-1].children.append(current)
            stack.append(current)
        elif token.nesting == -1:
            if len(stack) == 1:
                raise ValueError(f"Unbalanced Markdown AST close token: {token.type}")
            stack.pop()
        else:
            stack[-1].children.append(_AstNode(token=token))
    if len(stack) != 1:
        raise ValueError("Unbalanced Markdown AST open tokens")
    return root.children


def _inline_text(ast_node: _AstNode) -> str:
    for child in ast_node.children:
        if child.token_type == "inline":
            return child.token.content  # type: ignore[attr-defined]
    return ""


def _collect_links(ast_node: _AstNode) -> list[str]:
    links: list[str] = []
    token = ast_node.token
    if token is not None and token.type == "inline" and token.children:  # type: ignore[attr-defined]
        for child in token.children:  # type: ignore[attr-defined]
            if child.type == "link_open":
                href = child.attrGet("href")
                if href is not None:
                    links.append(href)
    for child in ast_node.children:
        links.extend(_collect_links(child))
    return links


def _callout_metadata(raw_text: str) -> dict | None:
    for line in raw_text.splitlines():
        if not line.strip():
            continue
        match = CALLOUT_RE.match(line)
        if match:
            return {"callout_type": match.group("kind").lower(),
                    "callout_title": (match.group("title") or "").strip()}
        return None
    return None


def _ast_range(node: _AstNode, offsets: _Offsets) -> SourceSpan:
    if node.source_map is None:
        raise ValueError(f"Block token {node.token_type} has no source map")
    return offsets.span_from_map(node.source_map)


def _make_block_node(ast_node: _AstNode, parent: StructuralNode,
                     heading_path: tuple[str, ...], factory: _NodeFactory,
                     offsets: _Offsets) -> StructuralNode | None:
    token_type = ast_node.token_type
    node_type = BLOCK_TYPES.get(token_type)
    if node_type is None:
        return None
    span = _ast_range(ast_node, offsets)
    raw = factory.source[span.char_start:span.char_end]
    metadata: dict = {}
    if token_type == "blockquote_open":
        callout = _callout_metadata(raw)
        if callout:
            node_type = "callout"
            metadata.update(callout)
        else:
            node_type = "quote"
    if token_type == "ordered_list_open":
        metadata["ordered"] = True
        metadata["start"] = ast_node.token.attrGet("start") or "1"  # type: ignore[attr-defined]
    elif token_type == "bullet_list_open":
        metadata["ordered"] = False
    if token_type in {"paragraph_open", "list_item_open", "bullet_list_open", "ordered_list_open"}:
        links = _collect_links(ast_node)
        if links:
            metadata["link_targets"] = links

    if node_type == "list":
        own_spans: tuple[SourceSpan, ...] = ()
    elif node_type == "list_item":
        # Own content includes only direct blocks, never nested list descendants.
        own_spans = tuple(
            _ast_range(child, offsets) for child in ast_node.children
            if child.token_type in BLOCK_TYPES
            and BLOCK_TYPES[child.token_type] != "list"
            and child.source_map is not None
        )
    else:
        own_spans = (span,)
    node = factory.make(node_type, span, heading_path, parent,
                        metadata=metadata, content_spans=own_spans)

    # Quotes, Callouts, tables and code blocks stay atomic in stage B.
    # Lists expose items, and nested lists are children of their parent item.
    if node_type == "list":
        for child in ast_node.children:
            if child.token_type == "list_item_open":
                _make_block_node(child, node, heading_path, factory, offsets)
    elif node_type == "list_item":
        for child in ast_node.children:
            if child.token_type in BLOCK_TYPES:
                _make_block_node(child, node, heading_path, factory, offsets)
    return node


def _parse_heading_level(ast_node: _AstNode) -> int:
    token = ast_node.token
    if token is None:
        return 0
    tag = token.tag  # type: ignore[attr-defined]
    return int(tag[1]) if tag and len(tag) == 2 and tag[0] == "h" and tag[1].isdigit() else 0


def parse_markdown(source: str, source_path: str = "<memory>", *,
                   max_passage_words: int = 900) -> ParsedDocument:
    """Parse one Markdown string into a source-addressable structural tree.

    The parser follows CommonMark and enables GFM tables. Obsidian callouts are
    recognized from their original blockquote marker.
    """
    markdown = MarkdownIt("commonmark").enable("table")
    offsets = _Offsets(source)
    factory = _NodeFactory(source_path, source)
    root_span = offsets.span_from_chars(0, len(source))
    root = StructuralNode(
        local_key="root", source_path=source_path, node_type="document",
        span=root_span, raw_text=source,
        content_spans=(root_span,) if source else (),
    )

    ast_nodes = _build_ast_tree(markdown, source) if source else []
    heading_stack: list[tuple[int, StructuralNode]] = []
    for ast_node in ast_nodes:
        if ast_node.token_type == "heading_open":
            level = _parse_heading_level(ast_node)
            title = _inline_text(ast_node).strip()
            heading_span = _ast_range(ast_node, offsets)
            heading_start = heading_span.char_start
            while heading_stack and heading_stack[-1][0] >= level:
                _, closing = heading_stack.pop()
                closing.span = offsets.span_from_chars(closing.char_start, heading_start)
                closing.raw_text = source[closing.char_start:heading_start]

            parent = heading_stack[-1][1] if heading_stack else root
            heading_path = (parent.heading_path if parent.node_type != "document" else ()) + (title,)
            node = factory.make(
                "heading", offsets.span_from_chars(heading_start, len(source)),
                heading_path, parent, metadata={"level": level, "title": title},
                content_spans=(heading_span,),
            )
            heading_stack.append((level, node))
            continue

        parent = heading_stack[-1][1] if heading_stack else root
        _make_block_node(ast_node, parent, parent.heading_path, factory, offsets)

    while heading_stack:
        _, closing = heading_stack.pop()
        closing.span = offsets.span_from_chars(closing.char_start, len(source))
        closing.raw_text = source[closing.char_start:]

    # A heading's total range includes descendants. content_spans contains its
    # heading line and direct blocks only, excluding nested heading sections.
    for node in root.children:
        _refresh_heading_content_spans(node)

    parsed = ParsedDocument(source_path=source_path, raw_text=source, root=root,
                            parser_version=_parser_version())
    if max_passage_words > 0:
        parsed.passages = build_passages(parsed, max_words=max_passage_words)
    validate_parsed_document(parsed)
    return parsed


def _refresh_heading_content_spans(node: StructuralNode) -> None:
    if node.node_type == "heading":
        spans = list(node.content_spans)
        for child in node.children:
            if child.node_type != "heading":
                spans.append(child.span)
        node.content_spans = tuple(spans)
    for child in node.children:
        _refresh_heading_content_spans(child)


def _parser_version() -> str:
    try:
        return version("markdown-it-py")
    except PackageNotFoundError:
        return "unknown"


def estimate_words(text: str) -> int:
    """Approximate word count; not a model-token count."""
    return len(WORD_RE.findall(text))


def _context_for(node: StructuralNode, document: ParsedDocument) -> tuple[str, tuple[SourceSpan, ...]]:
    if not node.heading_path:
        return "", ()
    # Context uses exact heading-line slices but is not part of raw_text/offsets.
    spans: list[SourceSpan] = []
    cursor = node
    while cursor.node_type != "document":
        if cursor.node_type == "heading" and cursor.content_spans:
            spans.append(cursor.content_spans[0])
        if cursor.parent_key is None:
            break
        try:
            cursor = document.get_node(cursor.parent_key)
        except KeyError:
            break
    spans.reverse()
    parts = [document.raw_text[span.char_start:span.char_end].rstrip("\r\n") for span in spans]
    return "\n".join(parts), tuple(spans)


def build_passages(document: ParsedDocument, *, max_words: int = 900) -> list[Passage]:
    """Create soft-sized passages only at existing structural child boundaries.

    Passage raw_text is always a direct source slice. Parent heading context is
    stored separately. Atomic oversized nodes remain whole with a warning.
    """
    if max_words < 1:
        raise ValueError("max_words must be positive")
    passages: list[Passage] = []
    sequence = 0
    for node in document.iter_nodes():
        if node.node_type == "document" or estimate_words(node.raw_text) <= max_words:
            continue
        if not node.children:
            node.warnings.append("oversized_unsplittable: no safe child boundary")
            continue

        candidates = sorted(node.children, key=lambda child: (child.char_start, child.char_end))
        groups: list[list[StructuralNode]] = []
        current: list[StructuralNode] = []
        current_words = 0
        for child in candidates:
            child_words = estimate_words(child.raw_text)
            if current and current_words + child_words > max_words:
                groups.append(current)
                current = []
                current_words = 0
            current.append(child)
            current_words += child_words
            if child_words > max_words:
                child.warnings.append("oversized_child: retained as one structural unit")
        if current:
            groups.append(current)

        context_text, context_spans = _context_for(node, document)
        for group in groups:
            start = min(child.char_start for child in group)
            end = max(child.char_end for child in group)
            span = _Offsets(document.raw_text).span_from_chars(start, end)
            raw = document.raw_text[start:end]
            words = estimate_words(raw)
            warnings = (("oversized_passage: split boundary unavailable without breaking a child",)
                        if words > max_words else ())
            sequence += 1
            passages.append(Passage(
                passage_key=f"p{sequence:06d}", source_path=document.source_path,
                owner_node_key=node.local_key, span=span, raw_text=raw,
                context_text=context_text, context_spans=context_spans,
                estimated_words=words, warnings=warnings,
            ))
    return passages


def extract_source_slice(source: str, span: SourceSpan) -> str:
    """Return the original text range. This is the only extraction primitive."""
    return source[span.char_start:span.char_end]


def validate_parsed_document(document: ParsedDocument) -> None:
    """Raise ValueError when structural or source-coordinate invariants fail."""
    seen_keys: set[str] = set()
    previous_by_parent: dict[str | None, int] = {}
    offsets = _Offsets(document.raw_text)
    for node in document.iter_nodes():
        if node.local_key in seen_keys:
            raise ValueError(f"Duplicate parse-local key: {node.local_key}")
        seen_keys.add(node.local_key)
        if node.source_path != document.source_path:
            raise ValueError(f"Node source path mismatch: {node.local_key}")
        if node.raw_text != extract_source_slice(document.raw_text, node.span):
            raise ValueError(f"Node raw_text is not an exact source slice: {node.local_key}")
        expected_span = offsets.span_from_chars(node.char_start, node.char_end)
        if (node.line_start, node.line_end) != (expected_span.line_start, expected_span.line_end):
            raise ValueError(f"Invalid line coordinates for node {node.local_key}")
        if node.parent_key is not None and node.parent_key not in seen_keys:
            raise ValueError(f"Missing or late parent for node {node.local_key}")
        if node.char_start < previous_by_parent.get(node.parent_key, -1):
            raise ValueError(f"Children are out of source order under parent {node.parent_key}")
        previous_by_parent[node.parent_key] = node.char_start
        for content_span in node.content_spans:
            _check_span(document.raw_text, content_span, node.local_key)

    for passage in document.passages:
        if passage.raw_text != extract_source_slice(document.raw_text, passage.span):
            raise ValueError(f"Passage raw_text is not an exact source slice: {passage.passage_key}")
        expected_span = offsets.span_from_chars(passage.span.char_start, passage.span.char_end)
        if (passage.span.line_start, passage.span.line_end) != (expected_span.line_start, expected_span.line_end):
            raise ValueError(f"Invalid line coordinates for Passage {passage.passage_key}")
        for context_span in passage.context_spans:
            _check_span(document.raw_text, context_span, passage.passage_key)


def _check_span(source: str, span: SourceSpan, label: str) -> None:
    if not (0 <= span.char_start <= span.char_end <= len(source)):
        raise ValueError(f"Invalid character offsets for {label}")
    expected_bytes = (
        len(source[:span.char_start].encode("utf-8")),
        len(source[:span.char_end].encode("utf-8")),
    )
    if (span.byte_start, span.byte_end) != expected_bytes:
        raise ValueError(f"Invalid UTF-8 byte offsets for {label}")
