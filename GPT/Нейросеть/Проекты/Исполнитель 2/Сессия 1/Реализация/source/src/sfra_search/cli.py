"""Command-line interface for the SFRA local search index."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapter import load_jsonl, validate_manifest
from .db import SFRAIndex, load_entity_config
from .runtime import search_structural_database
from .structural import get_source_node


def _read_manifest(path: str | None) -> dict | None:
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else None


def _print(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sfra", description="Local SQLite/FTS5 search index for SFRA")
    parser.add_argument("--db", default=".ai-index/sfra-search.sqlite3", help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create database schema and verify FTS5")
    imp = sub.add_parser("import-nodes", help="Import Node v1 JSONL")
    imp.add_argument("--jsonl", required=True)
    imp.add_argument("--manifest")
    upd = sub.add_parser("update", help="Apply an incremental batch")
    upd.add_argument("--jsonl", required=True)
    upd.add_argument("--manifest")
    sea = sub.add_parser("search", help="Search text, paths, titles and headings")
    sea.add_argument("query")
    sea.add_argument("--entity", action="append", default=[])
    sea.add_argument("--limit", type=int, default=20)
    ent = sub.add_parser("search-entity", help="Search by confirmed entity or alias")
    ent.add_argument("name")
    ent.add_argument("--limit", type=int, default=20)
    show = sub.add_parser("show", help="Show current or historical node version")
    show.add_argument("node_id")
    show.add_argument("--hash")
    ec = sub.add_parser("load-entities", help="Load entity config JSON")
    ec.add_argument("--config", required=True)
    confirm = sub.add_parser("confirm-alias", help="Confirm an alias for one entity")
    confirm.add_argument("--entity-id", required=True)
    confirm.add_argument("--alias", required=True)
    reject = sub.add_parser("reject-alias", help="Reject an alias for one entity")
    reject.add_argument("--entity-id", required=True)
    reject.add_argument("--alias", required=True)
    aliases = sub.add_parser("list-aliases", help="List aliases and their statuses")
    aliases.add_argument("--entity-id", required=True)
    candidates = sub.add_parser("list-candidates", help="List unconfirmed entity candidates")
    candidates.add_argument("--limit", type=int, default=100)
    sub.add_parser("check", help="Check SQLite, FTS and version integrity")
    once = sub.add_parser("run-once", help="Build an in-memory search index from Executor 1 SQLite and search once")
    once.add_argument("--source-db", required=True, help="Executor 1 structural SQLite database (opened read-only)")
    once.add_argument("--query", required=True, help="Search query")
    once.add_argument("--entity", action="append", default=[], help="Entity name to resolve; may be repeated")
    once.add_argument("--limit", type=int, default=20)
    once.add_argument("--entity-config", help="Optional JSON Entity Registry configuration")
    source = sub.add_parser("get-source", help="Fetch an exact Executor 1 source node by Node ID + Content Hash")
    source.add_argument("--source-db", required=True, help="Executor 1 structural SQLite database (opened read-only)")
    source.add_argument("--node-id", required=True, help="Producer-issued stable Node ID")
    source.add_argument("--content-hash", required=True, help="Exact SHA-256 Content Hash returned by search")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run-once":
            report = search_structural_database(
                args.source_db, args.query, entities=args.entity, limit=args.limit,
                entity_config=args.entity_config,
            )
            _print(report)
            return 0
        if args.command == "get-source":
            source = get_source_node(args.source_db, args.node_id, args.content_hash)
            if source is None:
                print("Node/content-hash pair not found in the current structural index", file=sys.stderr)
                return 2
            _print(source)
            return 0

        index = SFRAIndex(args.db)
        if args.command == "init":
            _print({"database": args.db, "fts5": True, "check": index.check(), "morphology": index.morphology.engine})
        elif args.command in ("import-nodes", "update"):
            nodes = load_jsonl(args.jsonl)
            manifest = _read_manifest(args.manifest)
            _print(index.import_nodes(nodes, manifest))
        elif args.command == "search":
            _print(index.search(args.query, entities=args.entity, limit=args.limit))
        elif args.command == "search-entity":
            _print(index.search_entity(args.name, limit=args.limit))
        elif args.command == "show":
            result = index.get_node(args.node_id, content_hash=args.hash)
            if result is None:
                print("Node/version not found", file=sys.stderr)
                return 2
            _print(result)
        elif args.command == "load-entities":
            _print({"entities_loaded": load_entity_config(index, args.config)})
        elif args.command == "confirm-alias":
            index.confirm_alias(args.entity_id, args.alias)
            _print({"confirmed": True, "entity_id": args.entity_id, "alias": args.alias})
        elif args.command == "reject-alias":
            index.reject_alias(args.entity_id, args.alias)
            _print({"rejected": True, "entity_id": args.entity_id, "alias": args.alias})
        elif args.command == "list-aliases":
            _print(index.list_entity_aliases(args.entity_id))
        elif args.command == "list-candidates":
            _print(index.list_entity_candidates(args.limit))
        elif args.command == "check":
            result = index.check()
            _print(result)
            return 0 if result["ok"] else 1
        return 0
    except Exception as exc:
        print(f"sfra: error: {exc}", file=sys.stderr)
        return 1
