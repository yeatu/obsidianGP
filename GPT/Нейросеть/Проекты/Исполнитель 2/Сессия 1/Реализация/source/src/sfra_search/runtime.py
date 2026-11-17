"""One-shot runtime for GitHub Actions and other short-lived Python jobs."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .db import SFRAIndex, load_entity_config
from .structural import load_current_nodes


def search_structural_database(
    source_database: str | Path,
    query: str,
    *,
    entities: Iterable[str] | None = None,
    limit: int = 20,
    entity_config: str | Path | None = None,
) -> dict:
    """Build a disposable in-memory FTS index, search once, and return JSON data.

    The Executor 1 database is opened read-only by the adapter. The temporary
    search index lives only in memory and disappears when this function returns.
    Search hits preserve Executor 1's `node_id` and `content_hash` so a later
    component can address the original node in the structural database.
    """
    entities_to_search = list(entities or [])
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if not query.strip() and not entities_to_search:
        raise ValueError("query or at least one entity name must be provided")
    nodes, source_summary = load_current_nodes(source_database)
    index = SFRAIndex(":memory:")
    try:
        managed_paths = sorted({node["source_path"] for node in nodes})
        imported = index.import_nodes(
            nodes,
            manifest={"schema": "sfra-node-batch/v1", "mode": "full_snapshot",
                        "managed_source_paths": managed_paths, "deleted_node_ids": []},
        )
        entities_loaded = 0
        if entity_config is not None:
            entities_loaded = load_entity_config(index, entity_config)

        integrity = index.check()
        if not integrity["ok"]:
            raise RuntimeError(f"Temporary search index failed integrity check: {integrity}")
        search_result = index.search(query, entities=entities_to_search, limit=limit)
        # Include only operational metadata. The search DB itself is never written
        # to disk or returned as an artifact.
        return {
            "runtime": "one-shot-memory",
            "source_index": {
                "documents_active": source_summary.documents_active,
                "documents_total": source_summary.documents_total,
                "nodes_current": source_summary.nodes_current,
            },
            "search_index": imported,
            "entities_loaded": entities_loaded,
            "integrity": integrity,
            "search": search_result,
        }
    finally:
        index.close()
