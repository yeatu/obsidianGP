"""Stage-B structural parser for Source-First Retrieval Architecture."""

from .indexer import IndexResult, index_vault, read_markdown_file
from .models import ParsedDocument, Passage, SourceSpan, StructuralNode
from .parser import (
    build_passages,
    estimate_words,
    extract_source_slice,
    parse_markdown,
    validate_parsed_document,
)
from .storage import connect_database, save_parsed_document

__all__ = [
    "IndexResult",
    "ParsedDocument",
    "Passage",
    "SourceSpan",
    "StructuralNode",
    "build_passages",
    "connect_database",
    "estimate_words",
    "extract_source_slice",
    "index_vault",
    "parse_markdown",
    "read_markdown_file",
    "save_parsed_document",
    "validate_parsed_document",
]
