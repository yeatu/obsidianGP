from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

from sfra_context_builder import ContextBuilder, TiktokenCounter, parse_search_request
from sfra_context_integrations.dependency_resolver import E1DependencyResolver
from sfra_context_integrations.pipeline import ContextIntegrationPipeline, SourceReadRequest
from sfra_context_integrations.search_adapter import E2SearchAdapter
from sfra_context_integrations.snapshot import bind_pinned_snapshot
from sfra_context_integrations.source_reader import (
    E1SourceReader,
    SourceReaderContractError,
)


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


def _git_head(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_status(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout




def _expect_contract_rejection(
    source_api,
    pinned,
    token_counter,
    node_id,
    content_hash,
    scope,
    mutation,
    expected_code,
):
    class FaultInjectedE1:
        def read_source_scope(self, db_path, vault_root, requested_node_id, expected_hash, *, scope, snapshot_id):
            native = source_api.read_source_scope(
                db_path,
                vault_root,
                requested_node_id,
                expected_hash,
                scope=scope,
                snapshot_id=snapshot_id,
            )
            payload = native.to_dict()
            if mutation == "snapshot_echo":
                payload["snapshot_id"] = "tampered-snapshot-id"
            elif mutation == "document_hash":
                payload["document"]["document_hash"] = "sha256:" + "0" * 64
                payload["document"]["source_sha256"] = "sha256:" + "0" * 64
            elif mutation == "generation":
                payload["fragments"][0]["index_generation"] += 1
            else:
                raise ValueError(f"unknown fault injection: {mutation}")
            return SimpleNamespace(to_dict=lambda payload=payload: payload)

        def resolve_current_node(self, db_path, requested_node_id, *, snapshot_id):
            native = source_api.resolve_current_node(
                db_path, requested_node_id, snapshot_id=snapshot_id
            )
            return native

    reader = E1SourceReader(FaultInjectedE1(), pinned, token_counter)
    try:
        reader.read_scope(node_id, content_hash, scope, pinned.ref)
    except SourceReaderContractError as exc:
        if exc.code != expected_code:
            raise RuntimeError(
                f"Fault injection {mutation!r} raised {exc.code!r}, expected {expected_code!r}"
            ) from exc
        return exc.code
    raise RuntimeError(f"Fault injection {mutation!r} was not rejected by E3")


def _search_fixture_node(search_structural_database, database_path, query, marker):
    result = search_structural_database(database_path, query, limit=20)
    if result.get("search", {}).get("status") != "ok":
        raise RuntimeError(f"Disposable E1 fixture could not be found by E2: {result}")
    for hit in result["search"].get("results", []):
        if hit.get("node_type") == "paragraph" and marker.casefold() in str(hit.get("excerpt", "")).casefold():
            return hit
    raise RuntimeError(f"E2 did not return the expected disposable fixture node: {marker!r}")


def _run_disposable_e1_lifecycle_cases(source_api, pinned, token_counter, index_vault, search_structural_database):
    """Use E1's public indexer and reader APIs only; never modify E1 SQLite with SQL."""
    reports = {}

    with tempfile.TemporaryDirectory(prefix="sfra-e3-ambiguous-") as temporary:
        root = Path(temporary)
        vault = root / "vault"
        state = root / "state"
        vault.mkdir()
        note = vault / "lifecycle.md"
        note.write_text(
            "# Header\\n\\nFirst paragraph marker.\\n\\nMiddle paragraph marker.\\n\\nLast paragraph marker.\\n",
            encoding="utf-8",
        )
        index_vault(vault, state)
        database = state / "structure.sqlite3"
        anchor = _search_fixture_node(
            search_structural_database, database, "Middle paragraph marker", "Middle paragraph marker"
        )
        note.write_text(
            "# Header\\n\\nFirst paragraph revision A.\\n\\nFirst paragraph revision B.\\n"
            "\\nMiddle paragraph marker.\\n\\nLast paragraph marker.\\n",
            encoding="utf-8",
        )
        index_vault(vault, state)

        fixture_pinned = replace(pinned, database_path=database, vault_root=vault)
        fixture_reader = E1SourceReader(source_api, fixture_pinned, token_counter)
        ambiguous = fixture_reader.read_scope(
            anchor["node_id"], anchor["content_hash"], "neighbors", pinned.ref
        )
        if ambiguous.get("status") != "ambiguous" or ambiguous.get("fragments") != []:
            raise RuntimeError(
                "Disposable E1 ambiguous-sibling fixture did not fail closed: "
                + json.dumps(ambiguous, ensure_ascii=False)
            )
        reports["ambiguous_neighbor_scope"] = {
            "status": ambiguous["status"],
            "fragments_empty": ambiguous["fragments"] == [],
            "created_by": "E1 index_vault public API after one-to-many sibling remap",
            "node_id": anchor["node_id"],
        }

    with tempfile.TemporaryDirectory(prefix="sfra-e3-deleted-") as temporary:
        root = Path(temporary)
        vault = root / "vault"
        state = root / "state"
        vault.mkdir()
        note = vault / "deleted.md"
        note.write_text(
            "# Deleted document\\n\\nUnique deletion lifecycle marker.\\n",
            encoding="utf-8",
        )
        index_vault(vault, state)
        database = state / "structure.sqlite3"
        address = _search_fixture_node(
            search_structural_database, database,
            "Unique deletion lifecycle marker", "Unique deletion lifecycle marker"
        )
        note.unlink()
        index_vault(vault, state)

        fixture_pinned = replace(pinned, database_path=database, vault_root=vault)
        fixture_reader = E1SourceReader(source_api, fixture_pinned, token_counter)
        deleted = fixture_reader.read_scope(
            address["node_id"], address["content_hash"], "node", pinned.ref
        )
        if deleted.get("status") != "deleted" or deleted.get("fragments") != []:
            raise RuntimeError(
                "Disposable E1 deleted-node fixture did not fail closed: "
                + json.dumps(deleted, ensure_ascii=False)
            )
        reports["deleted_node_scope"] = {
            "status": deleted["status"],
            "fragments_empty": deleted["fragments"] == [],
            "created_by": "E1 index_vault public API after source document deletion",
            "node_id": address["node_id"],
        }

    reports["isolation"] = {
        "production_database_used": False,
        "production_vault_modified": False,
        "e1_internal_sql_used_by_e3": False,
    }
    return reports


def main() -> int:
    e1_root = Path(os.environ["SFRA_E1_ROOT"]).resolve()
    sidecar_root = Path(os.environ["SFRA_SIDECAR_ROOT"]).resolve()
    vault_git_root = Path(os.environ["SFRA_VAULT_GIT_ROOT"]).resolve()
    vault_root = (vault_git_root / os.environ.get("SFRA_VAULT_SUBDIR", "ГП")).resolve()
    query = os.environ.get("SFRA_QUERY", "реанимация")

    if str(e1_root) not in sys.path:
        sys.path.insert(0, str(e1_root))

    from sfra_indexer import index_vault, verify_state_directory
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
    sidecar_tree_before = _tracked_tree_digest(sidecar_root)
    vault_before = _tracked_tree_digest(vault_git_root)
    sidecar_head_before = _git_head(sidecar_root)
    vault_head_before = _git_head(vault_git_root)
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
    e1_commit_sha = _git_head(e1_root)
    e3_commit_sha = _git_head(Path.cwd())
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

    pipeline = ContextIntegrationPipeline(
        pinned_snapshot=pinned,
        search_adapter=search_adapter,
        context_builder=ContextBuilder(token_counter),
        source_reader=source_reader,
        dependency_resolver=dependency_resolver,
    )
    pipeline_result = pipeline.run(
        request,
        source_reads=tuple(
            SourceReadRequest(
                node_id=candidate.node_id,
                expected_hash=candidate.content_hash,
                scope=scope,
            )
            for scope in ("node", "parent", "neighbors", "document")
        ),
    )
    pipeline_candidate = pipeline_result.search.batch.candidates[0]
    if (
        pipeline_candidate.node_id != candidate.node_id
        or pipeline_candidate.content_hash != candidate.content_hash
    ):
        raise RuntimeError("Repeated pinned E2 search changed its top candidate")
    scope_results = {
        scope: result
        for scope, result in zip(
            ("node", "parent", "neighbors", "document"),
            pipeline_result.source_reads,
            strict=True,
        )
    }

    parent_relation = next(
        (
            item for item in scope_results["parent"]["fragments"]
            if item["role"] == "parent_context"
        ),
        None,
    )
    dependency_request_id = (
        parent_relation["node_id"] if parent_relation is not None else candidate.node_id
    )
    dependency = dependency_resolver.resolve_node(dependency_request_id, pinned.ref)
    if dependency is None:
        raise RuntimeError(
            "E1 current-node resolver could not produce exact source for the real parent dependency"
        )
    dependency_expected = parent_relation or {
        "node_id": candidate.node_id,
        "content_hash": candidate.content_hash,
        "source_path": candidate.source_path,
        "document_hash": candidate.document_hash,
        "index_generation": candidate.index_generation,
    }
    for key in ("node_id", "content_hash", "source_path", "document_hash", "index_generation"):
        if dependency.get(key) != dependency_expected.get(key):
            raise RuntimeError(
                f"DependencyResolver {key} differs from the exact parent relation address"
            )

    node_fragment = scope_results["node"]["fragments"][0]
    target_source = scope_results["node"]["target_source"]
    expected_identity = {
        "node_id": candidate.node_id,
        "content_hash": candidate.content_hash,
        "source_path": candidate.source_path,
        "document_hash": candidate.document_hash,
        "index_generation": candidate.index_generation,
    }
    for key, expected in expected_identity.items():
        if target_source.get(key) != expected:
            raise RuntimeError(f"E1 target_source {key} differs from the E2-verified candidate")
        if node_fragment.get(key) != expected:
            raise RuntimeError(f"E1 node fragment {key} differs from the E2-verified candidate")
    if node_fragment["raw_text"] != candidate.raw_text:
        raise RuntimeError("SearchAdapter raw_text differs from E1 exact node scope")
    if _sha256_bytes(node_fragment["raw_text"].encode("utf-8")) != candidate.content_hash:
        raise RuntimeError("Exact node source text failed Content Hash verification")

    for scope, result in scope_results.items():
        if result.get("snapshot_id") != pinned.ref.snapshot_id:
            raise RuntimeError(f"E1 scope {scope} does not share the pinned snapshot_id")
        for fragment in result["fragments"]:
            for key in ("source_path", "document_hash", "index_generation"):
                if fragment.get(key) != expected_identity[key]:
                    raise RuntimeError(
                        f"E1 scope {scope} fragment {key} differs from the pinned target document"
                    )

    document_fragment = scope_results["document"]["fragments"][0]
    document_bytes = document_fragment["raw_text"].encode("utf-8")
    if document_fragment["raw_text"] == "":
        raise RuntimeError("E1 document scope returned an empty document unexpectedly")
    if _sha256_bytes(document_bytes) != document_fragment["document_hash"]:
        raise RuntimeError("E1 document text failed whole-document SHA-256")
    if document_fragment["content_hash"] != document_fragment["document_hash"]:
        raise RuntimeError("Document fragment content_hash differs from document_hash")
    if document_fragment.get("size_bytes") != len(document_bytes):
        raise RuntimeError("E1 document size_bytes does not describe the complete raw_text")
    if (
        document_fragment["source_path"] != candidate.source_path
        or document_fragment["document_hash"] != candidate.document_hash
        or document_fragment["index_generation"] != candidate.index_generation
    ):
        raise RuntimeError("E1 full document identity differs from the exact target node")
    # Context Pack must preserve exact E1-backed source identity, not only its text.
    pack = pipeline_result.context_pack
    if not pack.get("Included"):
        raise RuntimeError("Context Builder produced no Included source-backed context")
    included = next(
        (item for item in pack["Included"] if item["node_id"] == candidate.node_id),
        None,
    )
    if included is None:
        raise RuntimeError("E2 top candidate is not present in the Context Pack")
    if included["raw_text"] != candidate.raw_text or included["content_hash"] != candidate.content_hash:
        raise RuntimeError("Context Pack does not preserve the exact E1-backed candidate")
    for key in ("source_path", "document_hash", "index_generation"):
        if included.get(key) != expected_identity[key]:
            raise RuntimeError(f"Context Pack {key} differs from the E1-verified candidate")

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

    snapshot_echo_rejection = _expect_contract_rejection(
        source_api, pinned, token_counter, candidate.node_id, candidate.content_hash,
        "node", "snapshot_echo", "snapshot_mismatch",
    )
    document_hash_rejection = _expect_contract_rejection(
        source_api, pinned, token_counter, candidate.node_id, candidate.content_hash,
        "document", "document_hash", "document_hash_mismatch",
    )
    generation_rejection = _expect_contract_rejection(
        source_api, pinned, token_counter, candidate.node_id, candidate.content_hash,
        "node", "generation", "snapshot_generation_mismatch",
    )

    mismatched_snapshot = replace(
        pinned.ref,
        sidecar_commit_sha="0" * 40,
    )
    try:
        source_reader.read_scope(
            candidate.node_id, candidate.content_hash, "node", mismatched_snapshot
        )
    except SourceReaderContractError as exc:
        if exc.code != "snapshot_mismatch":
            raise
        request_snapshot_rejection = exc.code
    else:
        raise RuntimeError("E3 accepted a SourceReader request with a different SnapshotRef")

    with tempfile.TemporaryDirectory(prefix="sfra-e3-corrupt-source-") as temporary:
        corrupt_root = Path(temporary)
        original_source_path = pinned.vault_root / candidate.source_path
        corrupt_source_path = corrupt_root / candidate.source_path
        corrupt_source_path.parent.mkdir(parents=True, exist_ok=True)
        corrupt_source_path.write_bytes(
            original_source_path.read_bytes() + b"\n<!-- isolated source corruption -->\n"
        )
        corrupt_pinned = replace(pinned, vault_root=corrupt_root)
        corrupt_reader = E1SourceReader(source_api, corrupt_pinned, token_counter)
        corrupt_result = corrupt_reader.read_scope(
            candidate.node_id, candidate.content_hash, "node", pinned.ref
        )
        if corrupt_result.get("status") != "stale_source" or corrupt_result.get("fragments") != []:
            raise RuntimeError(
                "E1 did not reject a corrupted source copy without returning fragments: "
                + json.dumps(corrupt_result, ensure_ascii=False)
            )

    from sfra_search.runtime import search_structural_database as _search_fixture
    disposable_lifecycle = _run_disposable_e1_lifecycle_cases(
        source_api, pinned, token_counter, index_vault, _search_fixture
    )

    not_found_id = "node_00000000-0000-4000-8000-000000000001"
    missing = source_reader.resolve_current_node(not_found_id, pinned.ref)
    if missing.get("status") != "not_found" or missing.get("snapshot_id") != pinned.ref.snapshot_id:
        raise RuntimeError("Unknown Node ID did not return explicit not_found with the pinned snapshot")

    database_after = _sha256_bytes(pinned.database_path.read_bytes())
    manifest_after = _sha256_bytes(pinned.manifest_path.read_bytes())
    sidecar_tree_after = _tracked_tree_digest(sidecar_root)
    vault_after = _tracked_tree_digest(vault_git_root)
    sidecar_head_after = _git_head(sidecar_root)
    vault_head_after = _git_head(vault_git_root)
    sidecar_status_after = _git_status(sidecar_root)
    vault_status_after = _git_status(vault_git_root)

    if database_after != database_before:
        raise RuntimeError("E1 SQLite changed during real integration test")
    if manifest_after != manifest_before:
        raise RuntimeError("E1 manifest changed during real integration test")
    if sidecar_tree_after != sidecar_tree_before:
        raise RuntimeError("A tracked file in the pinned sfra-state checkout changed")
    if vault_after != vault_before:
        raise RuntimeError("Pinned Vault files changed during real integration test")
    if sidecar_head_after != sidecar_head_before or vault_head_after != vault_head_before:
        raise RuntimeError("A pinned Git checkout HEAD moved during the integration test")
    if sidecar_status_after or vault_status_after:
        raise RuntimeError("Real integration test left checkout changes")

    report = {
        "status": "success",
        "implementation": {
            "e1_commit_sha": e1_commit_sha,
            "e3_commit_sha": e3_commit_sha,
            "e1_public_api": [
                "sfra_indexer.read_source_scope",
                "sfra_indexer.resolve_current_node",
                "sfra_indexer.verify_state_directory",
            ],
        },
        "snapshot": {
            "snapshot_id": pinned.ref.snapshot_id,
            "vault_commit_sha": pinned.ref.vault_commit_sha,
            "sidecar_commit_sha": pinned.ref.sidecar_commit_sha,
            "manifest_sha256": pinned.ref.manifest_sha256,
            "database_sha256": database_before,
            "sidecar_tree_sha256": sidecar_tree_before,
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
            "current_target_identity": expected_identity,
            "dependency_resolution": {
                "relationship": "parent_context" if parent_relation is not None else "same-node fallback (no parent in E1 scope)",
                "requested_node_id": dependency_request_id,
                "resolved_identity": {
                    key: dependency[key]
                    for key in ("node_id", "content_hash", "source_path", "document_hash", "index_generation")
                },
            },
            "scopes": {
                scope: {
                    "status": value["status"],
                    "snapshot_id": value["snapshot_id"],
                    "fragment_count": len(value["fragments"]),
                    "roles": [item["role"] for item in value["fragments"]],
                    "fragments": [
                        {
                            "role": item["role"],
                            "node_id": item.get("node_id"),
                            "source_path": item["source_path"],
                            "content_hash": item["content_hash"],
                            "document_hash": item["document_hash"],
                            "index_generation": item["index_generation"],
                            "raw_text_sha256": _sha256_bytes(item["raw_text"].encode("utf-8")),
                            "raw_text_utf8_bytes": len(item["raw_text"].encode("utf-8")),
                            "size_bytes": item.get("size_bytes"),
                        }
                        for item in value["fragments"]
                    ],
                }
                for scope, value in scope_results.items()
            },
            "wrong_hash_returns_no_fragments": stale_result.get("fragments") == [],
            "unknown_node_has_no_address": missing.get("address") is None,
            "wrong_hash_status": stale_result["status"],
            "unknown_node_status": missing["status"],
            "corrupt_source_copy": {
                "status": corrupt_result["status"],
                "fragments_empty": corrupt_result["fragments"] == [],
                "production_vault_modified": False,
            },
            "snapshot_echo_fault_rejected": snapshot_echo_rejection,
            "request_snapshot_mismatch_rejected": request_snapshot_rejection,
            "document_hash_fault_rejected": document_hash_rejection,
            "generation_fault_rejected": generation_rejection,
            "disposable_real_e1_lifecycle": disposable_lifecycle,
        },
        "e3": {
            "orchestrator": "ContextIntegrationPipeline.run",
            "pipeline_snapshot_matches": pipeline_result.snapshot == pinned.ref,
            "context_pack_status": pack["status"],
            "included_count": len(pack["Included"]),
            "deferred_count": len(pack["Deferred"]),
            "included_target_identity": {
                key: included.get(key)
                for key in ("node_id", "content_hash", "source_path", "document_hash", "index_generation")
            },
            "included_target_raw_text_sha256": _sha256_bytes(included["raw_text"].encode("utf-8")),
            "included_target_raw_text_utf8_bytes": len(included["raw_text"].encode("utf-8")),
            "scope_budget_status": budget_result["status"],
            "budget_owner": budget_result["token_accounting"]["budget_owner"],
        },
        "read_only": {
            "sqlite_unchanged": database_before == database_after,
            "manifest_unchanged": manifest_before == manifest_after,
            "sidecar_tree_unchanged": sidecar_tree_before == sidecar_tree_after,
            "vault_unchanged": vault_before == vault_after,
            "sidecar_head_unchanged": sidecar_head_before == sidecar_head_after,
            "vault_head_unchanged": vault_head_before == vault_head_after,
            "sidecar_clean": not sidecar_status_after,
            "vault_checkout_clean": not vault_status_after,
        },
    }
    report_text = json.dumps(report, ensure_ascii=False, indent=2)
    print(report_text)
    report_path = Path("integration-report.json")
    report_path.write_text(report_text + "\n", encoding="utf-8")
    # Read it back so the uploaded artifact is strict standalone JSON.
    json.loads(report_path.read_text(encoding="utf-8"))

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        scope_rows = "\n".join(
            f"| {scope} | {value['status']} | {len(value['fragments'])} | "
            f"{', '.join(item['role'] for item in value['fragments'])} |"
            for scope, value in scope_results.items()
        )
        summary = (
            "# Real E2 → E3 → E1 integration\n\n"
            f"- Snapshot ID: `{pinned.ref.snapshot_id}`\n"
            f"- Vault commit: `{pinned.ref.vault_commit_sha}`\n"
            f"- Sidecar commit: `{pinned.ref.sidecar_commit_sha}`\n"
            f"- Manifest SHA-256: `{pinned.ref.manifest_sha256}`\n"
            f"- E2 hits: {search_result.engine_result_count}; candidates: {len(search_result.batch.candidates)}\n"
            f"- Context Pack: `{pack['status']}`; Included: {len(pack['Included'])}; Deferred: {len(pack['Deferred'])}\n"
            f"- Scope budget (E3): `{budget_result['status']}`\n\n"
            "| Scope | Status | Fragments | Roles |\n"
            "|---|---:|---:|---|\n"
            f"{scope_rows}\n\n"
            "Read-only verification: SQLite, manifest, sidecar tree, Vault tree, "
            "both Git HEADs, and both checkout statuses unchanged.\n"
        )
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
