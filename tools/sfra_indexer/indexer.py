from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"

_HEADING_RE = re.compile(r"^\ufeff? {0,3}(#{1,6})(?:[ \t]+|$)(.*?)\s*$")
_LIST_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>(?:[-+*]|\d+[.)]))[ \t]+(?P<body>.*)$")
_QUOTE_RE = re.compile(r"^ {0,3}>")
_CALLOUT_RE = re.compile(
    r"^ {0,3}>[ \t]*\[!(?P<kind>[A-Za-z0-9_-]+)\](?P<fold>[+-])?(?:[ \t]+(?P<title>.*))?$",
    re.IGNORECASE,
)
_FENCE_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
_THEMATIC_BREAK_RE = re.compile(r"^ {0,3}(?:-{3,}|_{3,}|\*{3,})[ \t]*$")
_TABLE_DELIMITER_CELL_RE = re.compile(r"^:?-{3,}:?$")


@dataclass
class Diagnostic:
    severity: str
    code: str
    message: str
    path: str | None = None


@dataclass
class Node:
    id: str
    type: str
    parent_id: str | None
    children_ids: list[str]
    start_line: int
    end_line: int
    start_char: int
    end_char: int
    start_byte: int
    end_byte: int
    sha256: str
    source_text: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentRecord:
    path: str
    sha256: str
    byte_count: int
    char_count: int
    line_count: int
    root_node_id: str
    nodes: list[Node]


@dataclass
class IndexResult:
    schema_version: str
    root_path: str
    documents: list[DocumentRecord]
    diagnostics: list[Diagnostic]
    stats: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "root_path": self.root_path,
            "stats": self.stats,
            "documents": [
                {
                    "path": doc.path,
                    "sha256": doc.sha256,
                    "byte_count": doc.byte_count,
                    "char_count": doc.char_count,
                    "line_count": doc.line_count,
                    "root_node_id": doc.root_node_id,
                    "nodes": [asdict(node) for node in doc.nodes],
                }
                for doc in self.documents
            ],
            "diagnostics": [asdict(item) for item in self.diagnostics],
        }


class DocumentReadError(RuntimeError):
    """A Markdown file could not be read or decoded without data loss."""

    def __init__(self, path: Path, message: str, code: str = "read_error") -> None:
        super().__init__(message)
        self.path = path
        self.code = code


def _relative_display_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_relative(path: Path, root: Path) -> str | None:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return None


def scan_vault(
    root_path: str | os.PathLike[str],
    diagnostics: list[Diagnostic] | None = None,
) -> list[Path]:
    """Return sorted Markdown paths under root_path, never following symlinks.

    An optional diagnostics list receives traversal errors. Only the selected root
    directory is walked; sibling repository directories are never inspected.
    """
    root = Path(root_path).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"Vault root is not a directory: {root}")

    found: list[Path] = []

    def onerror(exc: OSError) -> None:
        if diagnostics is not None:
            try:
                shown = Path(exc.filename).relative_to(root).as_posix() if exc.filename else None
            except ValueError:
                shown = None
            diagnostics.append(
                Diagnostic("error", "scan_error", f"Не удалось прочитать каталог: {exc}", shown)
            )

    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False, onerror=onerror):
        current_path = Path(current)
        dirnames[:] = sorted(name for name in dirnames if not (current_path / name).is_symlink())
        for filename in sorted(filenames):
            candidate = current_path / filename
            if candidate.suffix.lower() != ".md" or candidate.is_symlink():
                continue
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                if diagnostics is not None:
                    diagnostics.append(
                        Diagnostic("error", "scan_file_error", str(exc), _safe_relative(candidate, root))
                    )
                continue
            if _is_relative_to(resolved, root) and resolved.is_file():
                found.append(resolved)

    return sorted(found, key=lambda item: _relative_display_path(item, root).casefold())


def _line_records(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    offset = 0
    for raw in text.splitlines(keepends=True):
        records.append({
            "raw": raw,
            "content": raw.rstrip("\r\n"),
            "start": offset,
            "end": offset + len(raw),
        })
        offset += len(raw)
    return records


def _byte_offsets(text: str) -> list[int]:
    offsets = [0]
    total = 0
    for char in text:
        total += len(char.encode("utf-8"))
        offsets.append(total)
    return offsets


def _indent_width(prefix: str) -> int:
    width = 0
    for char in prefix:
        width += 4 - (width % 4) if char == "\t" else 1
    return width


def _line_indent(content: str) -> int:
    return _indent_width(content[: len(content) - len(content.lstrip(" \t"))])


def _has_unescaped_pipe(value: str) -> bool:
    escaped = False
    for char in value:
        if char == "|" and not escaped:
            return True
        if char == "\\" and not escaped:
            escaped = True
        else:
            escaped = False
    return False


def _split_table_cells(content: str) -> list[tuple[str, int, int]]:
    left = len(content) - len(content.lstrip())
    right = len(content.rstrip())
    if left >= right:
        return []
    separators: list[int] = []
    escaped = False
    for pos in range(left, right):
        char = content[pos]
        if char == "|" and not escaped:
            separators.append(pos)
        if char == "\\" and not escaped:
            escaped = True
        else:
            escaped = False
    if not separators:
        return []
    first = left + 1 if separators[0] == left else left
    last = right - 1 if separators[-1] == right - 1 else right
    internal = [pos for pos in separators if first <= pos < last]
    boundaries = [first] + [pos + 1 for pos in internal]
    ends = internal + [last]
    cells: list[tuple[str, int, int]] = []
    for start, end in zip(boundaries, ends):
        raw_start, raw_end = start, end
        while raw_start < raw_end and content[raw_start].isspace():
            raw_start += 1
        while raw_end > raw_start and content[raw_end - 1].isspace():
            raw_end -= 1
        cells.append((content[raw_start:raw_end], raw_start, raw_end))
    return cells


def _table_separator(content: str) -> bool:
    return bool(content.strip()) and _has_unescaped_pipe(content) and all(
        _TABLE_DELIMITER_CELL_RE.fullmatch(cell.strip())
        for cell, _, _ in _split_table_cells(content)
    )


class _DocumentParser:
    def __init__(self, relative_path: str, text: str, raw_bytes: bytes) -> None:
        self.relative_path = relative_path
        self.text = text
        self.raw_bytes = raw_bytes
        self.lines = _line_records(text)
        self.byte_offsets = _byte_offsets(text)
        self.path_key = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:16]
        self.nodes: list[Node] = []
        self.node_by_id: dict[str, Node] = {}
        self.counter = 0
        self.root = self._make_node(
            "document", None, 0, len(text), 1, len(self.lines), {"path": relative_path}
        )

    def _make_node(
        self,
        node_type: str,
        parent_id: str | None,
        start_char: int,
        end_char: int,
        start_line: int,
        end_line: int,
        attributes: dict[str, Any] | None = None,
    ) -> Node:
        self.counter += 1
        node_id = (
            f"doc_{self.path_key}" if node_type == "document"
            else f"node_{self.path_key}_{self.counter:06d}"
        )
        source = self.text[start_char:end_char]
        node = Node(
            node_id, node_type, parent_id, [],
            start_line, end_line, start_char, end_char,
            self.byte_offsets[start_char], self.byte_offsets[end_char],
            hashlib.sha256(source.encode("utf-8")).hexdigest(),
            source, attributes or {},
        )
        self.nodes.append(node)
        self.node_by_id[node_id] = node
        if parent_id is not None:
            self.node_by_id[parent_id].children_ids.append(node_id)
        return node

    def _set_span(self, node: Node, start_char: int, end_char: int, start_line: int, end_line: int) -> None:
        node.start_char, node.end_char = start_char, end_char
        node.start_line, node.end_line = start_line, end_line
        node.start_byte = self.byte_offsets[start_char]
        node.end_byte = self.byte_offsets[end_char]
        node.source_text = self.text[start_char:end_char]
        node.sha256 = hashlib.sha256(node.source_text.encode("utf-8")).hexdigest()

    def _span(self, start_idx: int, end_idx: int) -> tuple[int, int, int, int]:
        if start_idx >= end_idx:
            char = self.lines[start_idx]["start"] if start_idx < len(self.lines) else len(self.text)
            return char, char, start_idx + 1, start_idx
        return (
            self.lines[start_idx]["start"],
            self.lines[end_idx - 1]["end"],
            start_idx + 1,
            end_idx,
        )

    def _make_block(
        self, node_type: str, parent_id: str, start_idx: int, end_idx: int,
        attributes: dict[str, Any] | None = None,
    ) -> Node:
        return self._make_node(
            node_type, parent_id, *self._span(start_idx, end_idx), attributes
        )

    def parse(self) -> DocumentRecord:
        heading_stack: list[tuple[int, Node]] = []
        i = 0
        while i < len(self.lines):
            line = self.lines[i]
            content = line["content"]
            heading_match = _HEADING_RE.match(content)
            if heading_match:
                level = len(heading_match.group(1))
                title = re.sub(r"[ \t]+#+[ \t]*$", "", heading_match.group(2)).strip()
                while heading_stack and heading_stack[-1][0] >= level:
                    _, previous = heading_stack.pop()
                    self._set_span(previous, previous.start_char, line["start"], previous.start_line, i)
                parent_id = heading_stack[-1][1].id if heading_stack else self.root.id
                heading = self._make_node(
                    f"heading_h{level}", parent_id,
                    line["start"], line["end"], i + 1, i + 1,
                    {"level": level, "title": title},
                )
                heading_stack.append((level, heading))
                i += 1
                continue

            parent_id = heading_stack[-1][1].id if heading_stack else self.root.id
            if not content.strip():
                i += 1
                continue

            fence_match = _FENCE_RE.match(content)
            if fence_match:
                i = self._parse_fence(i, parent_id, fence_match)
            elif _LIST_RE.match(content):
                i = self._parse_list(i, parent_id)
            elif _QUOTE_RE.match(content):
                i = self._parse_quote(i, parent_id)
            elif (
                i + 1 < len(self.lines)
                and _has_unescaped_pipe(content)
                and _table_separator(self.lines[i + 1]["content"])
            ):
                i = self._parse_table(i, parent_id)
            elif _THEMATIC_BREAK_RE.match(content):
                self._make_block("thematic_break", parent_id, i, i + 1)
                i += 1
            else:
                i = self._parse_paragraph(i, parent_id)

        while heading_stack:
            _, heading = heading_stack.pop()
            self._set_span(
                heading, heading.start_char, len(self.text),
                heading.start_line, len(self.lines),
            )

        return DocumentRecord(
            self.relative_path,
            hashlib.sha256(self.raw_bytes).hexdigest(),
            len(self.raw_bytes), len(self.text), len(self.lines),
            self.root.id, self.nodes,
        )

    def _parse_fence(self, i: int, parent_id: str, match: re.Match[str]) -> int:
        fence = match.group("fence")
        marker, min_len = fence[0], len(fence)
        close_re = re.compile(rf"^ {{0,3}}{re.escape(marker)}{{{min_len},}}[ \t]*$")
        end, closed = i + 1, False
        while end < len(self.lines):
            if close_re.match(self.lines[end]["content"]):
                end += 1
                closed = True
                break
            end += 1
        info = match.group("info").strip()
        language = info.split(None, 1)[0] if info else None
        self._make_block(
            "code_block", parent_id, i, end,
            {"fence": marker * min_len, "info": info, "language": language, "closed": closed},
        )
        return end

    def _parse_list(self, i: int, parent_id: str) -> int:
        list_node = self._make_block("list", parent_id, i, i + 1)
        stack: list[dict[str, Any]] = []
        records: list[dict[str, Any]] = []
        j = i
        while j < len(self.lines):
            content = self.lines[j]["content"]
            if not content.strip():
                lookahead = j + 1
                while lookahead < len(self.lines) and not self.lines[lookahead]["content"].strip():
                    lookahead += 1
                if lookahead < len(self.lines):
                    next_content = self.lines[lookahead]["content"]
                    next_is_item = _LIST_RE.match(next_content) is not None
                    next_is_continuation = bool(stack) and _line_indent(next_content) > stack[-1]["indent"]
                    if next_is_item or next_is_continuation:
                        for active in stack:
                            active["end_idx"] = lookahead
                        j += 1
                        continue
                break

            item_match = _LIST_RE.match(content)
            if item_match:
                indent = _indent_width(item_match.group("indent"))
                while stack and stack[-1]["indent"] >= indent:
                    stack.pop()
                item_parent = stack[-1]["node"].id if stack else list_node.id
                item = self._make_block(
                    "list_item", item_parent, j, j + 1,
                    {
                        "marker": item_match.group("marker"),
                        "depth": len(stack),
                        "indent": indent,
                        "ordered": item_match.group("marker")[0].isdigit(),
                    },
                )
                record = {"node": item, "indent": indent, "start_idx": j, "end_idx": j + 1}
                records.append(record)
                for active in stack:
                    active["end_idx"] = j + 1
                stack.append(record)
                j += 1
                continue

            if stack and _line_indent(content) > stack[-1]["indent"]:
                for active in stack:
                    active["end_idx"] = j + 1
                j += 1
                continue
            break

        list_end = max(i + 1, j)
        self._set_span(list_node, *self._span(i, list_end))
        for record in records:
            self._set_span(record["node"], *self._span(record["start_idx"], record["end_idx"]))
        return list_end

    def _parse_quote(self, i: int, parent_id: str) -> int:
        j = i
        while j < len(self.lines) and _QUOTE_RE.match(self.lines[j]["content"]):
            j += 1
        callout = _CALLOUT_RE.match(self.lines[i]["content"])
        max_depth = 1
        for k in range(i, j):
            marker_match = re.match(r"^ {0,3}(>+)", self.lines[k]["content"])
            if marker_match:
                max_depth = max(max_depth, len(marker_match.group(1)))
        attrs: dict[str, Any] = {"max_quote_depth": max_depth}
        node_type = "blockquote"
        if callout:
            node_type = "callout"
            attrs.update({
                "callout_type": callout.group("kind").lower(),
                "fold_marker": callout.group("fold"),
                "title": (callout.group("title") or "").strip(),
            })
        self._make_block(node_type, parent_id, i, j, attrs)
        return j

    def _parse_table(self, i: int, parent_id: str) -> int:
        j, rows = i, []
        while j < len(self.lines):
            content = self.lines[j]["content"]
            if not content.strip() or not _has_unescaped_pipe(content):
                break
            rows.append(j)
            j += 1
        table = self._make_block("table", parent_id, i, j, {"row_count": len(rows)})
        for row_index in rows:
            line = self.lines[row_index]
            row = self._make_node(
                "table_row", table.id, line["start"], line["end"],
                row_index + 1, row_index + 1,
                {"row_kind": "separator" if _table_separator(line["content"]) else "data"},
            )
            for cell_text, cell_start, cell_end in _split_table_cells(line["content"]):
                if cell_start != cell_end:
                    self._make_node(
                        "table_cell", row.id,
                        line["start"] + cell_start, line["start"] + cell_end,
                        row_index + 1, row_index + 1, {"value": cell_text},
                    )
        return j

    def _parse_paragraph(self, i: int, parent_id: str) -> int:
        j = i + 1
        while j < len(self.lines):
            content = self.lines[j]["content"]
            if not content.strip():
                break
            if (
                _HEADING_RE.match(content) or _FENCE_RE.match(content)
                or _LIST_RE.match(content) or _QUOTE_RE.match(content)
                or _THEMATIC_BREAK_RE.match(content)
            ):
                break
            if (
                j + 1 < len(self.lines) and _has_unescaped_pipe(content)
                and _table_separator(self.lines[j + 1]["content"])
            ):
                break
            j += 1
        self._make_block("paragraph", parent_id, i, j)
        return j


def parse_document(
    path: str | os.PathLike[str],
    root_path: str | os.PathLike[str],
) -> DocumentRecord:
    """Read and structurally parse one UTF-8 Markdown file under root_path."""
    root = Path(root_path).expanduser().resolve(strict=True)
    requested = Path(path).expanduser()
    if not requested.is_absolute():
        current = requested.absolute()
        if not _is_relative_to(current.resolve(strict=False), root):
            requested = root / requested
    if requested.is_symlink():
        raise DocumentReadError(requested, "Символические ссылки не индексируются", "symlink_skipped")
    try:
        candidate = requested.resolve(strict=True)
    except OSError as exc:
        raise DocumentReadError(requested, f"Не удалось найти файл: {exc}", "read_error") from exc
    if not _is_relative_to(candidate, root):
        raise DocumentReadError(candidate, "Документ находится за пределами индексируемого каталога", "path_outside_root")
    if not candidate.is_file():
        raise DocumentReadError(candidate, "Путь не является обычным Markdown-файлом", "invalid_path")
    if candidate.suffix.lower() != ".md":
        raise DocumentReadError(candidate, "Поддерживаются только файлы .md", "unsupported_extension")

    try:
        raw_bytes = candidate.read_bytes()
    except OSError as exc:
        raise DocumentReadError(candidate, f"Не удалось прочитать файл: {exc}", "read_error") from exc
    try:
        text = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DocumentReadError(
            candidate, f"Файл не является корректным UTF-8 (байтовая позиция {exc.start}): {exc}",
            "invalid_utf8",
        ) from exc
    return _DocumentParser(candidate.relative_to(root).as_posix(), text, raw_bytes).parse()


def build_index(root_path: str | os.PathLike[str]) -> IndexResult:
    """Index every .md file under root_path; report file errors and continue."""
    root = Path(root_path).expanduser().resolve(strict=True)
    diagnostics: list[Diagnostic] = []
    documents: list[DocumentRecord] = []
    try:
        paths = scan_vault(root, diagnostics=diagnostics)
    except OSError as exc:
        diagnostics.append(Diagnostic("error", "scan_root_error", str(exc)))
        paths = []

    for path in paths:
        try:
            documents.append(parse_document(path, root))
        except DocumentReadError as exc:
            diagnostics.append(Diagnostic(
                "error", exc.code, str(exc), _safe_relative(path, root)
            ))
        except Exception as exc:
            diagnostics.append(Diagnostic(
                "error", "parser_error",
                f"Непредвиденная ошибка разбора: {type(exc).__name__}: {exc}",
                _safe_relative(path, root),
            ))

    return IndexResult(
        SCHEMA_VERSION, str(root), documents, diagnostics,
        {
            "documents_discovered": len(paths),
            "documents_indexed": len(documents),
            "documents_failed": len(paths) - len(documents),
            "nodes": sum(len(doc.nodes) for doc in documents),
        },
    )


def export_index(result: IndexResult, output_path: str | os.PathLike[str]) -> Path:
    """Write UTF-8 JSON atomically; reject output located inside the vault."""
    output = Path(output_path).expanduser().absolute()
    root = Path(result.root_path).resolve()
    if _is_relative_to(output.resolve(strict=False), root):
        raise ValueError("Индексный JSON должен находиться вне индексируемого каталога")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=output.parent,
            prefix=f".{output.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary_name = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, output)
    except OSError:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
        raise
    return output
