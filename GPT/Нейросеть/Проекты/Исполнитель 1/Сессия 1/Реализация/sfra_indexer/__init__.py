"""Source-preserving structural indexer for SFRA stages B and C."""

from .identity import MatchPlan, build_match_plan, content_hash
from .indexer import IndexResult, get_database_summary, index_vault, read_markdown_file
from .models import ParsedDocument, Passage, SourceSpan, StructuralNode
from .parser import (
    build_passages,
    estimate_words,
    extract_source_slice,
    parse_markdown,
    validate_parsed_document,
)
from .state import (
    StateError,
    create_state_snapshot,
    sha256_file,
    verify_state_directory,
)
from .storage import connect_database, save_parsed_document

__all__ = [
    "IndexResult",
    "MatchPlan",
    "build_match_plan",
    "content_hash",
    "get_database_summary",
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
    "StateError",
    "create_state_snapshot",
    "sha256_file",
    "verify_state_directory",
]
