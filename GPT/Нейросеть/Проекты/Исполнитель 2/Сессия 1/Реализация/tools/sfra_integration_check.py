#!/usr/bin/env python3
"""End-to-end SFRA search/source verification against the persisted E1 index."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_json_output(text: str) -> Any:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
        for start in starts:
            try:
                return json.loads(text[start:])
            except json.JSONDecodeError:
                continue
    raise RuntimeError("CLI did not return valid JSON on stdout")


def walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def collect_hits(payload: Any) -> list[dict[str, Any]]:
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for item in walk_dicts(payload):
        node_id = item.get("node_id")
        content_hash = item.get("content_hash")
        if isinstance(node_id, str) and node_id and isinstance(content_hash, str) and content_hash:
            found[(node_id, content_hash)] = item
    return list(found.values())


def find_raw_text(payload: Any) -> str | None:
    for item in walk_dicts(payload):
        for key in ("raw_text", "source_text", "original_text"):
            value = item.get(key)
            if isinstance(value, str):
                return value
    return None


def run_cli(command: list[str], env: dict[str, str]) -> tuple[str, Any]:
    completed = subprocess.run(command, text=True, capture_output=True, env=env)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout:\n{completed.stdout[-4000:]}\nstderr:\n{completed.stderr[-4000:]}"
        )
    return completed.stdout, parse_json_output(completed.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--vault", required=True, type=Path)
    parser.add_argument("--temp-root", required=True, type=Path)
    parser.add_argument("--state-branch-sha", required=True)
    parser.add_argument("--package-dir", type=Path, default=None)
    parser.add_argument("--max-sources", type=int, default=5)
    args = parser.parse_args()

    args.results_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    expected_hash = manifest.get("database_sha256", "")
    actual_hash = "sha256:" + digest(args.source_db)
    if expected_hash != actual_hash:
        raise RuntimeError(f"Structural database SHA mismatch: manifest={expected_hash}, actual={actual_hash}")
    if manifest.get("database") != "state/structure.sqlite3":
        raise RuntimeError("Unexpected database path in state manifest")
    if manifest.get("sqlite_schema_version") != 2:
        raise RuntimeError(f"Unsupported E1 schema version: {manifest.get('sqlite_schema_version')}")
    if manifest.get("source_repository") != os.environ.get("GITHUB_REPOSITORY"):
        raise RuntimeError("Manifest repository does not match the current repository")

    import sqlite3
    uri = f"file:{args.source_db.resolve().as_posix()}?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    try:
        db.execute("PRAGMA query_only = ON")
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: {integrity}")
        schema_version = db.execute(
            "SELECT schema_version FROM schema_info WHERE singleton=1"
        ).fetchone()[0]
        if schema_version != 2:
            raise RuntimeError(f"SQLite schema_info version is {schema_version}, expected 2")
        documents = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        active_documents = db.execute(
            "SELECT COUNT(*) FROM documents WHERE status='active'"
        ).fetchone()[0]
        total_nodes = db.execute("SELECT COUNT(*) FROM structural_nodes").fetchone()[0]
        active_nodes = db.execute(
            """SELECT COUNT(*) FROM structural_nodes n
               JOIN documents d ON d.document_pk=n.document_pk
               WHERE d.status='active' AND n.status='active'
                 AND n.stale_generation IS NULL"""
        ).fetchone()[0]
        missing_ids = db.execute(
            """SELECT COUNT(*) FROM structural_nodes n
               JOIN documents d ON d.document_pk=n.document_pk
               WHERE d.status='active' AND n.status='active'
                 AND n.stale_generation IS NULL
                 AND (n.node_id IS NULL OR n.content_hash IS NULL)"""
        ).fetchone()[0]
        ambiguous_nodes = db.execute(
            """SELECT COUNT(*) FROM structural_nodes n
               JOIN documents d ON d.document_pk=n.document_pk
               WHERE d.status='active' AND n.status='ambiguous'
                 AND n.stale_generation IS NULL"""
        ).fetchone()[0]
        stale_nodes = db.execute(
            """SELECT COUNT(*) FROM structural_nodes n
               JOIN documents d ON d.document_pk=n.document_pk
               WHERE d.status='active'
                 AND (n.status='stale' OR n.stale_generation IS NOT NULL)"""
        ).fetchone()[0]
        deleted_nodes = db.execute(
            """SELECT COUNT(*) FROM structural_nodes n
               JOIN documents d ON d.document_pk=n.document_pk
               WHERE d.status='active' AND n.status='deleted'"""
        ).fetchone()[0]
        nodes_in_deleted_documents = db.execute(
            """SELECT COUNT(*) FROM structural_nodes n
               JOIN documents d ON d.document_pk=n.document_pk
               WHERE d.status!='active'"""
        ).fetchone()[0]
        eligible_source_pairs = {
            (row[0], row[1])
            for row in db.execute(
                """SELECT n.node_id,n.content_hash FROM structural_nodes n
                   JOIN documents d ON d.document_pk=n.document_pk
                   WHERE d.status='active' AND n.status='active'
                     AND n.stale_generation IS NULL
                     AND n.node_id IS NOT NULL AND n.content_hash IS NOT NULL"""
            ).fetchall()
        }
        rejected_source_samples = db.execute(
            """SELECT n.node_id,n.content_hash,n.status,n.stale_generation,d.status
               FROM structural_nodes n JOIN documents d ON d.document_pk=n.document_pk
               WHERE n.node_id IS NOT NULL AND n.content_hash IS NOT NULL
                 AND (d.status!='active' OR n.status!='active' OR n.stale_generation IS NOT NULL)
               ORDER BY n.source_path,n.line_start LIMIT 20"""
        ).fetchall()
        if missing_ids:
            raise RuntimeError(f"{missing_ids} active structural nodes lack node_id/content_hash")
    finally:
        db.close()

    # Require pymorphy3; a fallback is not accepted in this integration run.
    import pymorphy3
    morph = pymorphy3.MorphAnalyzer()
    forms = ["реанимации", "реанимацию"]
    lemmas = {word: morph.parse(word)[0].normal_form for word in forms}
    if len(set(lemmas.values())) != 1:
        raise RuntimeError(f"pymorphy3 did not normalize the test forms to one lemma: {lemmas}")
    if args.package_dir is not None:
        package_root = args.package_dir.resolve()
    else:
        package_spec = importlib.util.find_spec("sfra_search")
        if package_spec is None or not package_spec.submodule_search_locations:
            raise RuntimeError("Installed sfra_search package cannot be located")
        package_root = Path(next(iter(package_spec.submodule_search_locations)))
    if not package_root.is_dir() or not (package_root / "__init__.py").is_file():
        raise RuntimeError(f"sfra_search package directory is invalid: {package_root}")
    python_sources = list(package_root.rglob("*.py"))
    mentions_pymorphy = any(
        "pymorphy3" in p.read_text(encoding="utf-8", errors="ignore").lower()
        or "morphanalyzer" in p.read_text(encoding="utf-8", errors="ignore").lower()
        for p in python_sources
    )
    if not mentions_pymorphy:
        raise RuntimeError("sfra_search source does not reference pymorphy3/MorphAnalyzer")
    from sfra_search.normalize import Morphology
    package_morphology = Morphology()
    if package_morphology.engine != "pymorphy3":
        raise RuntimeError(f"sfra_search selected {package_morphology.engine}, expected pymorphy3")

    cli = shutil.which("sfra")
    if not cli:
        raise RuntimeError("The sfra console command was not installed by the published package")
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["SFRA_REQUIRE_PYMORPHY3"] = "1"

    rejected_source_checks: list[dict[str, Any]] = []
    for row in rejected_source_samples:
        node_id, content_hash, node_status, stale_generation, document_status = row
        completed = subprocess.run(
            [
                cli, "get-source", "--source-db", str(args.source_db),
                "--node-id", node_id, "--content-hash", content_hash,
            ],
            text=True, capture_output=True, env=env,
        )
        if completed.returncode != 2:
            raise RuntimeError(
                "get-source exposed a non-active, stale, or deleted E1 node: "
                f"node_id={node_id}, node_status={node_status}, "
                f"stale_generation={stale_generation}, document_status={document_status}, "
                f"exit_code={completed.returncode}, stdout={completed.stdout[-1000:]}"
            )
        rejected_source_checks.append({
            "node_id": node_id,
            "content_hash": content_hash,
            "node_status": node_status,
            "stale_generation": stale_generation,
            "document_status": document_status,
            "rejected": True,
        })

    queries = ["реанимации", "реанимацию"]
    searches: list[dict[str, Any]] = []
    hit_maps: list[dict[tuple[str, str], dict[str, Any]]] = []
    for query in queries:
        stdout, payload = run_cli(
            [cli, "run-once", "--source-db", str(args.source_db), "--query", query],
            env,
        )
        hits = collect_hits(payload)
        if not hits:
            raise RuntimeError(f"No search hits returned for query: {query}")
        hit_map = {(h["node_id"], h["content_hash"]): h for h in hits}
        disallowed_pairs = sorted(set(hit_map) - eligible_source_pairs)
        if disallowed_pairs:
            raise RuntimeError(
                f"Search returned non-active or stale source addresses for {query!r}: "
                f"{disallowed_pairs[:10]}"
            )
        hit_maps.append(hit_map)
        searches.append({
            "query": query,
            "json": payload,
            "hit_count": len(hits),
            "hits": [
                {k: h.get(k) for k in (
                    "node_id", "content_hash", "source_path", "node_type",
                    "heading_path", "line_start", "line_end", "excerpt",
                    "score", "match_type", "reason"
                ) if k in h}
                for h in hits
            ],
        })

    common = set(hit_maps[0]) & set(hit_maps[1])
    if not common:
        ids1 = sorted({node_id for node_id, _ in hit_maps[0]})
        ids2 = sorted({node_id for node_id, _ in hit_maps[1]})
        raise RuntimeError(
            "The two inflected-form searches have no common node_id+content_hash. "
            f"First IDs={ids1[:10]}, second IDs={ids2[:10]}"
        )

    # Resolve several unique search hits after the temporary FTS index has closed.
    source_pairs: list[tuple[str, str, dict[str, Any]]] = []
    seen = set()
    for hit_map in hit_maps:
        for pair, hit in hit_map.items():
            if pair in seen:
                continue
            seen.add(pair)
            source_pairs.append((pair[0], pair[1], hit))
            if len(source_pairs) >= args.max_sources:
                break
        if len(source_pairs) >= args.max_sources:
            break

    retrieved: list[dict[str, Any]] = []
    for node_id, content_hash, hit in source_pairs:
        stdout, payload = run_cli(
            [
                cli, "get-source",
                "--source-db", str(args.source_db),
                "--node-id", node_id,
                "--content-hash", content_hash,
            ],
            env,
        )
        raw_text = find_raw_text(payload)
        if raw_text is None:
            raise RuntimeError(f"get-source response has no raw_text for {node_id}")
        actual_node_hash = "sha256:" + hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if actual_node_hash != content_hash:
            raise RuntimeError(
                f"get-source hash mismatch for {node_id}: requested={content_hash}, got={actual_node_hash}"
            )

        query_lemmas = set(lemmas.values())
        tokens = re.findall(r"[A-Za-zА-Яа-яЁё]+", raw_text.lower())
        source_lemmas = {morph.parse(token)[0].normal_form for token in tokens}
        if not query_lemmas.issubset(source_lemmas):
            raise RuntimeError(
                f"Retrieved source {node_id} does not contain the normalized query lemma {sorted(query_lemmas)}"
            )

        retrieved.append({
            "node_id": node_id,
            "content_hash": content_hash,
            "source_path": hit.get("source_path"),
            "line_start": hit.get("line_start"),
            "line_end": hit.get("line_end"),
            "raw_text": raw_text,
            "verified_sha256": actual_node_hash,
            "hash_matches": True,
            "normalized_query_lemma_present": True,
        })

    # The search index must not materialize as an additional SQLite file.
    db_files = sorted(
        str(p) for p in args.temp_root.rglob("*")
        if p.is_file() and p.suffix.lower() in {".sqlite", ".sqlite3", ".db"}
        and p.resolve() != args.source_db.resolve()
    )
    if db_files:
        raise RuntimeError("Unexpected persistent search database files: " + ", ".join(db_files))

    # Ensure Vault checkout is pristine and its tracked file bytes are unchanged.
    repo_root = args.vault.resolve().parent
    def git(*command: str) -> str:
        return subprocess.check_output(["git", "-C", str(repo_root), *command], text=True).strip()
    status_before = git("status", "--porcelain", "--", "ГП")
    diff_before = subprocess.run(["git", "-C", str(repo_root), "diff", "--exit-code", "--", "ГП"]).returncode
    tracked = git("ls-files", "-z", "--", "ГП").split("\0")
    tracked = [p for p in tracked if p]
    def vault_digest() -> str:
        h = hashlib.sha256()
        for rel in sorted(tracked):
            path = repo_root / rel
            h.update(rel.encode("utf-8") + b"\0")
            if not path.is_file():
                raise RuntimeError(f"Tracked Vault file is missing: {rel}")
            h.update(hashlib.sha256(path.read_bytes()).digest())
        return h.hexdigest()
    vault_hash_before = vault_digest()
    status_after = git("status", "--porcelain", "--", "ГП")
    diff_after = subprocess.run(["git", "-C", str(repo_root), "diff", "--exit-code", "--", "ГП"]).returncode
    vault_hash_after = vault_digest()
    if status_before or status_after or diff_before or diff_after or vault_hash_before != vault_hash_after:
        raise RuntimeError("Vault changed during read-only search execution")

    summary = {
        "status": "passed",
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "workflow_run_url": (
            f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
            f"{os.environ.get('GITHUB_REPOSITORY')}/actions/runs/{os.environ.get('GITHUB_RUN_ID')}"
        ),
        "implementation_commit": os.environ.get("GITHUB_SHA"),
        "manifest_sha256": "sha256:" + digest(args.manifest),
        "state_branch_sha": args.state_branch_sha,
        "state_manifest": manifest,
        "structural_db": {
            "sha256": actual_hash,
            "integrity_check": integrity,
            "schema_version": schema_version,
            "documents": documents,
            "active_documents": active_documents,
            "total_nodes": total_nodes,
            "active_nodes": active_nodes,
            "nodes_missing_identity": missing_ids,
            "ambiguous_nodes_excluded": ambiguous_nodes,
            "stale_nodes_excluded": stale_nodes,
            "deleted_nodes_excluded": deleted_nodes,
            "nodes_in_deleted_documents_excluded": nodes_in_deleted_documents,
            "eligible_source_pairs": len(eligible_source_pairs),
        },
        "vault": {
            "git_head": git("rev-parse", "HEAD"),
            "tracked_files": len(tracked),
            "digest_before": vault_hash_before,
            "digest_after": vault_hash_after,
            "git_status_clean_before_after": True,
        },
        "morphology": {
            "engine": "pymorphy3",
            "version": importlib.metadata.version("pymorphy3"),
            "test_forms": forms,
            "lemmas": lemmas,
            "same_lemma": True,
            "sfra_search_source_references_pymorphy3": mentions_pymorphy,
        },
        "searches": [
            {k: v for k, v in item.items() if k != "json"} for item in searches
        ],
        "common_node_id_content_hash": [
            {"node_id": node_id, "content_hash": ch} for node_id, ch in sorted(common)
        ],
        "source_retrieval_count": len(retrieved),
        "rejected_source_lookup_checks": rejected_source_checks,
        "persistent_search_db_files": db_files,
        "fts5_storage": "runtime process; no additional SQLite file detected under RUNNER_TEMP",
    }

    (args.results_dir / "search_results.json").write_text(
        json.dumps({"searches": searches}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.results_dir / "source_retrieval.json").write_text(
        json.dumps({"verified_sources": retrieved}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.results_dir / "integration_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
