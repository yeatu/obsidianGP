from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from sfra_context_builder import ContextBuilder, TiktokenCounter, parse_search_request
from sfra_context_integrations.dependency_resolver import E1DependencyResolver
from sfra_context_integrations.search_adapter import E2SearchAdapter
from sfra_context_integrations.snapshot import bind_pinned_snapshot
from sfra_context_integrations.source_reader import E1SourceReader


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _tracked_tree_digest(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    digest = hashlib.sha256()
    for raw_name in sorted(item for item in completed.stdout.split(b"\0") if item):
        path = repo_root / os.fsdecode(raw_name)
        digest.update(raw_name)
        if path.is_symlink():
            digest.update(b"SYMLINK\0")
            digest.update(os.fsencode(os.readlink(path)))
        elif path.is_file():
            digest.update(path.read_bytes())
        else:
            digest.update(b"MISSING\0")
    return "sha256:" + digest.hexdigest()


def _git_status(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def main() -> int:
    e1_root = Path(os.environ["SFRA_E1_ROOT"]).resolve()
    sidecar_root = Path(os.environ["SFRA_SIDECAR_ROOT"]).resolve()
    vault_git_root = Path(os.environ["SFRA_VAULT_GIT_ROOT"]).resolve()
    vault_root = (vault_git_root / os.environ.get("SFRA_VAULT_SUBDIR", "ГП")).resolve()
    query = os.environ.get("SFRA_QUERY", "реанимация")

    if str(e1_root) not in sys.path:
        sys.path.insert(0, str(e1_root))

    from sfra_indexer import verify_state_directory
    from sfra_indexer import read_source_scope, resolve_current_node

    source_api = SimpleNamespace(
        read_source_scope=read_source_scope,
        resolve_current_node=resolve_current_node,
    )
    pinned = bind_pinned_snapshot(
        sidecar_root=sidecar_root,
        vault_git_root=vault_git_root,
        vault_root=vault_root,
        state_verifier=verify_state_directory,
    )

    database_before = _sha256_bytes(pinned.database_path.read_bytes())
    manifest_before = _sha256_bytes(pinned.manifest_path.read_bytes())
    vault_before = _tracked_tree_digest(vault_git_root)
    sidecar_status_before = _git_status(sidecar_root)
    vault_status_before = _git_status(vault_git_root)
    if sidecar_status_before or vault_status_before:
        raise RuntimeError("Real integration checkout must start clean")

    from sfra_search.runtime import search_structural_database

    token_counter = TiktokenCounter("o200k_base")
    source_reader = E1SourceReader(source_api, pinned, token_counter)
    search_adapter = E2SearchAdapter(
        pinned,
        source_reader,
        search_call=search_structural_database,
        search_limit=30,
    )
    dependency_resolver = E1DependencyResolver(source_reader)
    request = parse_search_request({
        "query": query,
        "task": "E3 real E1/E2 snapshot integration verification",
        "budget_tokens": 6000,
    })

    search_result = search_adapter.search(request)
    if not search_result.batch.candidates:
        raise RuntimeError(
            f"E2 returned no source-verifiable candidates: {search_result.engine_status}"
        )
    candidate = search_result.batch.candidates[0]

    current = source_reader.resolve_current_node(candidate.node_id, pinned.ref)
    if current.get("status") != "ok":
        raise RuntimeError(f"E1 resolve_current_node failed: {current.get('status')}")
    if current["address"]["content_hash"] != candidate.content_hash:
        raise RuntimeError("E1 current address hash differs from E2 candidate hash")

    dependency = dependency_resolver.resolve_node(candidate.node_id, pinned.ref)
    if dependency is None:
        raise RuntimeError("E1 current-node resolver could not produce an exact dependency candidate")
    if dependency["content_hash"] != candidate.content_hash:
        raise RuntimeError("Dependency resolver returned a different current Content Hash")

    scope_results = {}
    for scope in ("node", "parent", "neighbors", "document"):
        result = source_reader.read_scope(
            candidate.node_id,
            candidate.content_hash,
            scope,
            pinned.ref,
        )
        if result.get("status") != "ok":
            raise RuntimeError(f"E1 scope {scope} failed: {result.get('status')}")
        if result.get("snapshot_id") != pinned.ref.snapshot_id:
            raise RuntimeError(f"E1 scope {scope} returned another snapshot_id")
        scope_results[scope] = result

    node_fragment = scope_results["node"]["fragments"][0]
    if node_fragment["raw_text"] != candidate.raw_text:
        raise RuntimeError("SearchAdapter raw_text differs from E1 exact node scope")
    if _sha256_bytes(node_fragment["raw_text"].encode("utf-8")) != candidate.content_hash:
        raise RuntimeError("Exact node source text failed Content Hash verification")

    document_fragment = scope_results["document"]["fragments"][0]
    if document_fragment["raw_text"] == "":
        raise RuntimeError("E1 document scope returned an empty document unexpectedly")
    if _sha256_bytes(document_fragment["raw_text"].encode("utf-8")) != document_fragment["document_hash"]:
        raise RuntimeError("E1 document text failed whole-document SHA-256")
    if document_fragment["content_hash"] != document_fragment["document_hash"]:
        raise RuntimeError("Document fragment content_hash differs from document_hash")

    budget_result = source_reader.read_scope(
        candidate.node_id,
        candidate.content_hash,
        "document",
        pinned.ref,
        budget_tokens=1,
    )
    if budget_result.get("status") != "budget_exceeded" or budget_result.get("fragments") != []:
        raise RuntimeError("E3 did not reject the complete document scope atomically over budget")

    stale_result = source_reader.read_scope(
        candidate.node_id,
        "sha256:" + "0" * 64,
        "node",
        pinned.ref,
    )
    if stale_result.get("status") != "stale_source" or stale_result.get("fragments") != []:
        raise RuntimeError("Wrong Content Hash did not fail closed as stale_source")

    not_found_id = "node_00000000-0000-4000-8000-000000000001"
    missing = source_reader.resolve_current_node(not_found_id, pinned.ref)
    if missing.get("status") != "not_found" or missing.get("snapshot_id") != pinned.ref.snapshot_id:
        raise RuntimeError("Unknown Node ID did not return explicit not_found with the pinned snapshot")

    builder = ContextBuilder(token_counter)
    pack = builder.build(
        request,
        search_result.batch,
        dependency_resolver,
        snapshot=pinned.ref,
    )
    if not pack.get("Included"):
        raise RuntimeError("Context Builder produced no Included source-backed context")
    included = next((item for item in pack["Included"] if item["node_id"] == candidate.node_id), None)
    if included is None:
        raise RuntimeError("E2 top candidate is not present in the Context Pack")
    if included["raw_text"] != candidate.raw_text or included["content_hash"] != candidate.content_hash:
        raise RuntimeError("Context Pack does not preserve the exact E1-backed candidate")

    database_after = _sha256_bytes(pinned.database_path.read_bytes())
    manifest_after = _sha256_bytes(pinned.manifest_path.read_bytes())
    vault_after = _tracked_tree_digest(vault_git_root)
    sidecar_status_after = _git_status(sidecar_root)
    vault_status_after = _git_status(vault_git_root)

    if database_after != database_before:
        raise RuntimeError("E1 SQLite changed during real integration test")
    if manifest_after != manifest_before:
        raise RuntimeError("E1 manifest changed during real integration test")
    if vault_after != vault_before:
        raise RuntimeError("Pinned Vault files changed during real integration test")
    if sidecar_status_after or vault_status_after:
        raise RuntimeError("Real integration test left checkout changes")

    report = {
        "status": "success",
        "snapshot": {
            "snapshot_id": pinned.ref.snapshot_id,
            "vault_commit_sha": pinned.ref.vault_commit_sha,
            "sidecar_commit_sha": pinned.ref.sidecar_commit_sha,
            "manifest_sha256": pinned.ref.manifest_sha256,
            "database_sha256": database_before,
            "vault_tree_sha256": vault_before,
        },
        "e2": {
            "status": search_result.engine_status,
            "hits": search_result.engine_result_count,
            "candidate_count": len(search_result.batch.candidates),
            "top_node_id": candidate.node_id,
            "top_content_hash": candidate.content_hash,
            "tier": candidate.relevance_tier,
            "bm25": candidate.relevance_bm25,
        },
        "e1": {
            "current_node_status": current["status"],
            "dependency_resolved": True,
            "scopes": {
                scope: {
                    "status": value["status"],
                    "fragment_count": len(value["fragments"]),
                    "roles": [item["role"] for item in value["fragments"]],
                }
                for scope, value in scope_results.items()
            },
            "wrong_hash_status": stale_result["status"],
            "unknown_node_status": missing["status"],
        },
        "e3": {
            "context_pack_status": pack["status"],
            "included_count": len(pack["Included"]),
            "deferred_count": len(pack["Deferred"]),
            "scope_budget_status": budget_result["status"],
            "budget_owner": budget_result["token_accounting"]["budget_owner"],
        },
        "read_only": {
            "sqlite_unchanged": database_before == database_after,
            "manifest_unchanged": manifest_before == manifest_after,
            "vault_unchanged": vault_before == vault_after,
            "sidecar_clean": not sidecar_status_after,
            "vault_checkout_clean": not vault_status_after,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
