"""SFRA structural Markdown indexer for an Obsidian vault."""

from .indexer import Diagnostic, DocumentReadError, IndexResult, build_index, export_index, parse_document, scan_vault

__all__ = ["Diagnostic", "DocumentReadError", "IndexResult", "build_index", "export_index", "parse_document", "scan_vault"]
