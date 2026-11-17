"""Command line interface for parsing and indexing Markdown Vaults."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .indexer import get_database_summary, index_vault, read_markdown_file
from .parser import parse_markdown
from .state import create_state_snapshot, verify_state_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sfra-index",
        description="Build a structural-only SFRA Markdown index",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_cmd = subparsers.add_parser("parse", help="Parse one Markdown file and print its structural tree")
    parse_cmd.add_argument("file", type=Path)
    parse_cmd.add_argument("--source-path", default=None)

    index_cmd = subparsers.add_parser("index", help="Batch-index every Markdown file in a Vault")
    index_cmd.add_argument("--vault", required=True, type=Path)
    index_cmd.add_argument("--index-dir", required=True, type=Path)

    info_cmd = subparsers.add_parser("info", help="Show counts in an existing sidecar database")
    info_cmd.add_argument("--db", required=True, type=Path)

    state_verify_cmd = subparsers.add_parser(
        "state-verify", help="Verify a persisted state manifest and SQLite snapshot"
    )
    state_verify_cmd.add_argument("--state-dir", required=True, type=Path)

    state_snapshot_cmd = subparsers.add_parser(
        "state-snapshot", help="Create a verified SQLite Backup API snapshot and manifest"
    )
    state_snapshot_cmd.add_argument("--db", required=True, type=Path)
    state_snapshot_cmd.add_argument("--state-dir", required=True, type=Path)
    state_snapshot_cmd.add_argument("--source-repository", required=True)
    state_snapshot_cmd.add_argument(
        "--vault-ref", "--source-branch", dest="vault_ref", required=True,
        help="Exact Vault branch, tag, or commit ref that was checked out",
    )
    state_snapshot_cmd.add_argument(
        "--vault-commit-sha", "--source-commit", dest="vault_commit_sha", required=True,
        help="Actual checked-out Vault Git commit SHA",
    )
    state_snapshot_cmd.add_argument("--workflow-run-id", required=True)

    return parser


def _node_dict(node) -> dict:
    return {
        "local_key": node.local_key,
        "node_id": node.node_id,
        "content_hash": node.content_hash,
        "node_type": node.node_type,
        "heading_path": list(node.heading_path),
        "parent_key": node.parent_key,
        "line_start": node.line_start,
        "line_end": node.line_end,
        "char_start": node.char_start,
        "char_end": node.char_end,
        "byte_start": node.byte_start,
        "byte_end": node.byte_end,
        "raw_text": node.raw_text,
        "content_spans": [
            {
                "line_start": span.line_start,
                "line_end": span.line_end,
                "char_start": span.char_start,
                "char_end": span.char_end,
                "byte_start": span.byte_start,
                "byte_end": span.byte_end,
            }
            for span in node.content_spans
        ],
        "metadata": node.metadata,
        "warnings": node.warnings,
        "children": [_node_dict(child) for child in node.children],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "parse":
        source = read_markdown_file(args.file)
        source_path = args.source_path or args.file.name
        parsed = parse_markdown(source, source_path)
        print(json.dumps(_node_dict(parsed.root), ensure_ascii=False, indent=2))
        return 0
    if args.command == "index":
        result = index_vault(args.vault, args.index_dir)
        print(json.dumps(
            {
                "database_path": result.database_path,
                "documents_seen": result.documents_seen,
                "documents_indexed": result.documents_indexed,
                "documents_skipped": result.documents_skipped,
                "nodes_saved": result.nodes_saved,
                "passages_saved": result.passages_saved,
                "empty_documents": result.empty_documents,
            },
            ensure_ascii=False,
            indent=2,
        ))
        return 0
    if args.command == "info":
        print(json.dumps(get_database_summary(args.db), ensure_ascii=False, indent=2))
        return 0
    if args.command == "state-verify":
        manifest = verify_state_directory(args.state_dir)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    if args.command == "state-snapshot":
        manifest = create_state_snapshot(
            args.db,
            args.state_dir,
            source_repository=args.source_repository,
            vault_ref=args.vault_ref,
            vault_commit_sha=args.vault_commit_sha,
            workflow_run_id=args.workflow_run_id,
        )
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
