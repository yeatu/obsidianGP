"""Synthetic-only, deterministic regression benchmark for SFRA lexical search."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sqlite3
from pathlib import Path
from sfra_search import SFRAIndex, calculate_content_hash

DEFAULT_CORPUS = Path(__file__).with_name("corpus.json")


def build_nodes(documents):
    nodes = []
    for doc in documents:
        raw = doc["raw_text"]
        nodes.append({
            "node_id": doc["node_id"],
            "source_path": doc["source_path"],
            "node_type": doc.get("node_type", "section"),
            "parent_node_id": None,
            "heading_path": doc.get("heading_path", []),
            "line_start": 1,
            "line_end": max(1, raw.count("\n") + 1),
            "content_hash": calculate_content_hash(raw),
            "raw_text": raw,
        })
    return nodes


def recall_at_k(expected_ids, actual_ids, k):
    expected = set(expected_ids)
    return None if not expected else len(expected.intersection(actual_ids[:k])) / len(expected)


def precision_at_k(expected_ids, actual_ids, k):
    if not expected_ids:
        return None
    return 0.0 if k <= 0 else len(set(expected_ids).intersection(actual_ids[:k])) / k


def reciprocal_rank(expected_ids, actual_ids):
    expected = set(expected_ids)
    if not expected:
        return None
    for rank, node_id in enumerate(actual_ids, start=1):
        if node_id in expected:
            return 1.0 / rank
    return 0.0


def evaluate_case(case, repetitions):
    expected = list(case.get("expected_node_ids", []))
    k = int(case.get("k", 5))
    orders = [item.get("node_ids", []) for item in repetitions]
    first = orders[0] if orders else []
    stable = all(order == first for order in orders)
    duplicate_counts = [len(order) - len(set(order)) for order in orders]
    no_duplicates = all(count == 0 for count in duplicate_counts)
    expected_exception = case.get("expected_exception")
    exceptions = [item.get("exception") for item in repetitions]
    exception_ok = (
        all(name == expected_exception for name in exceptions)
        if expected_exception else all(name is None for name in exceptions)
    )
    expected_order = case.get("expected_order")
    order_ok = expected_order is None or first[:len(expected_order)] == expected_order
    expected_status = case.get("expected_status")
    statuses = [item.get("status") for item in repetitions]
    status_ok = expected_status is None or all(status == expected_status for status in statuses)
    expected_empty = not expected and not expected_exception
    empty_ok = not first if expected_empty else True
    recall1 = recall_at_k(expected, first, 1)
    recallk = recall_at_k(expected, first, k)
    precisionk = precision_at_k(expected, first, k)
    mrr = reciprocal_rank(expected, first)
    gate = bool(case.get("gate", True))
    checks = {
        "stable_order": stable,
        "unique_results": no_duplicates,
        "expected_exception": exception_ok,
        "expected_order": order_ok,
        "expected_status": status_ok,
        "expected_empty": empty_ok,
        "recall_at_k": recallk == 1.0 if expected else True,
    }
    passed = all(checks.values()) if gate else None
    return {
        "id": case["id"], "category": case["category"], "query": case["query"],
        "gate": gate, "status": ("passed" if passed else "failed") if gate else "diagnostic",
        "expected_node_ids": expected, "result_node_ids": first,
        "hits": repetitions[0].get("hits", []) if repetitions else [],
        "k": k, "recall_at_1": recall1, "recall_at_k": recallk,
        "precision_at_k": precisionk, "reciprocal_rank": mrr,
        "stable_order": stable, "no_duplicates": no_duplicates,
        "max_duplicate_count": max(duplicate_counts, default=0),
        "expected_order_match": order_ok, "expected_status_match": status_ok,
        "expected_empty_match": empty_ok,
        "expected_status": expected_status,
        "expected_exception": expected_exception,
        "expected_exception_match": exception_ok,
        "repetitions": len(repetitions), "checks": checks,
        "notes": case.get("notes", ""),
    }


def avg(values):
    values = [value for value in values if value is not None]
    return None if not values else round(sum(values) / len(values), 4)


def render_markdown(report):
    lines = [
        "# SFRA E2 lexical search benchmark", "",
        f"- Status: **{report['status']}**",
        f"- Implementation ref: {report['implementation_ref']}",
        f"- Synthetic documents / queries: {report['synthetic_documents']} / {report['queries_total']}",
        f"- Morphology: {report['morphology_engine']} ({report['pymorphy3_version']})",
        f"- Python / SQLite: {report['python_version']} / {report['sqlite_version']}",
        f"- Corpus SHA-256: {report['corpus_sha256']}", "",
        "## Aggregate baseline", "",
        "| Metric | Result |", "|---|---:|",
        f"| Gated cases | {report['gate_cases_passed']} / {report['gate_cases']} passed |",
        f"| Macro recall@1 | {report['macro_recall_at_1']} |",
        f"| Macro recall@3 | {report['macro_recall_at_3']} |",
        f"| Macro precision@3 | {report['macro_precision_at_3']} |",
        f"| Macro MRR | {report['macro_mrr']} |",
        f"| Stable gated order | {report['stable_gate_cases']} / {report['gate_cases']} |",
        f"| Gated cases with duplicates | {report['duplicate_gate_cases']} |",
        "", "## Per-query results", "",
        "| Case | Category | Query | Expected | Results | Recall@k | Precision@k | Stable | Gate |",
        "|---|---|---|---|---|---:|---:|---:|---|",
    ]
    for item in report["cases"]:
        value = item["recall_at_k"]
        recall = "n/a" if value is None else f"{value:.3f}"
        lines.append(
            f"| {item['id']} | {item['category']} | {item['query']} | "
            f"{', '.join(item['expected_node_ids']) or 'empty'} | "
            f"{', '.join(item['result_node_ids']) or 'empty'} | {recall} | "
            f"{'n/a' if item['precision_at_k'] is None else f'{item["precision_at_k"]:.3f}'} | "
            f"{'yes' if item['stable_order'] else 'no'} | {item['status']} |"
        )
    lines.extend([
        "", "## Interpretation and limitations", "",
        "- Corpus is synthetic; no real Vault excerpts, note names or source paths are included.",
        "- Gated cases verify retrieval contracts, deterministic order, unique results and empty-query behavior.",
        "- Typo tolerance is diagnostic only; fuzzy matching is not part of the current contract.",
        "- Macro recall is averaged over gated cases with non-empty relevance sets. Empty/noise cases are checked separately.",
        "- This is a baseline only. Ranking weights, FTS schema, normalization and public APIs are unchanged.", "",
    ])
    return "\n".join(lines)


def run(corpus_path, repeats, expected_engine):
    raw = corpus_path.read_bytes()
    corpus = json.loads(raw)
    corpus_sha = hashlib.sha256(raw).hexdigest()
    nodes = build_nodes(corpus["documents"])
    index = SFRAIndex(":memory:")
    try:
        imported = index.import_nodes(nodes)
        integrity = index.check()
        engine = index.morphology.engine
        if engine != expected_engine:
            raise RuntimeError(
                f"Expected morphology engine {expected_engine!r}, got {engine!r}; "
                "install the declared morphology dependencies."
            )
        if not integrity.get("ok") or integrity.get("integrity") != "ok":
            raise RuntimeError(f"Synthetic benchmark index integrity failed: {integrity}")
        if imported.get("imported") != len(nodes):
            raise RuntimeError(f"Unexpected synthetic import result: {imported}")
        results = []
        for case in corpus["cases"]:
            repetitions = []
            for _ in range(repeats):
                try:
                    response = index.search(case["query"], limit=int(case.get("limit", 20)))
                    hits = [{
                        "node_id": hit["node_id"],
                        "tier": hit["relevance"]["tier"],
                        "bm25": hit["relevance"]["bm25"],
                        "match_type": hit["match_type"],
                    } for hit in response["results"]]
                    repetitions.append({
                        "status": response["status"],
                        "node_ids": [hit["node_id"] for hit in hits],
                        "hits": hits, "exception": None,
                    })
                except Exception as exc:
                    repetitions.append({
                        "status": "exception", "node_ids": [], "hits": [],
                        "exception": type(exc).__name__,
                    })
            results.append(evaluate_case(case, repetitions))
        gated = [item for item in results if item["gate"]]
        scored = [item for item in gated if item["recall_at_1"] is not None]
        diagnostic = [item for item in results if not item["gate"]]
        passed = sum(item["status"] == "passed" for item in gated)
        return {
            "benchmark_version": corpus["benchmark_version"],
            "status": "passed" if passed == len(gated) else "failed",
            "implementation_ref": os.environ.get("GITHUB_SHA", "local-working-tree"),
            "python_version": platform.python_version(),
            "sqlite_version": sqlite3.sqlite_version,
            "morphology_engine": engine,
            "pymorphy3_version": importlib.metadata.version("pymorphy3") if engine == "pymorphy3" else None,
            "corpus_sha256": corpus_sha,
            "synthetic_documents": len(nodes), "queries_total": len(results),
            "gate_cases": len(gated), "gate_cases_passed": passed,
            "diagnostic_cases": len(diagnostic),
            "macro_recall_at_1": avg([item["recall_at_1"] for item in scored]),
            "macro_recall_at_3": avg([recall_at_k(item["expected_node_ids"], item["result_node_ids"], 3) for item in scored]),
            "macro_precision_at_3": avg([precision_at_k(item["expected_node_ids"], item["result_node_ids"], 3) for item in scored]),
            "macro_mrr": avg([item["reciprocal_rank"] for item in scored]),
            "stable_gate_cases": sum(bool(item["stable_order"]) for item in gated),
            "duplicate_gate_cases": sum(not item["no_duplicates"] for item in gated),
            "index_integrity": integrity["integrity"],
            "index_active_nodes": integrity["active_nodes"],
            "index_imported": imported["imported"],
            "repeat_count": repeats, "cases": results,
            "scope": {
                "runtime_changed": False, "public_api_changed": False,
                "production_workflows_changed": False, "vault_content_used": False,
                "e1_or_e3_changed": False, "fuzzy_matching_promised": False,
            },
        }
    finally:
        index.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--expected-engine", default="pymorphy3")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    args = parser.parse_args(argv)
    if args.repeats < 2:
        parser.error("--repeats must be at least 2 to measure ordering stability")
    report = run(args.corpus, args.repeats, args.expected_engine)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(rendered, encoding="utf-8")
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(render_markdown(report), encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
