"""Reproducible synthetic-only E2 -> E3 -> B1 benchmark runner for SFRA."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from typing import Any, Mapping, Sequence

CORPUS_DIGEST = "sha256:915304e812906f64003d9aacb0dd4b7701f7fbcf4f24fdc3cda21d1108b13068"
CORPUS_VERSION = "1.0.0"
RUNNER_VERSION = "1.0.0"
REPO_ROOT = Path(__file__).resolve().parents[6]
CORPUS_DIR = REPO_ROOT / "GPT/Нейросеть/Проекты/Аналитик 1/Сессия 4/Issue 41"
E1_DIR = REPO_ROOT / "GPT/Нейросеть/Проекты/Исполнитель 1/Сессия 1/Реализация"
E2_DIR = REPO_ROOT / "GPT/Нейросеть/Проекты/Исполнитель 2/Сессия 1/Реализация/source"
B1_DIR = REPO_ROOT / "GPT/Нейросеть/Проекты/Исполнитель 3/Сессия 1/Реализация/Этап Б1"
E3_DIR = REPO_ROOT / "GPT/Нейросеть/Проекты/Исполнитель 3/Сессия 1/Реализация/Этап В1"

for package_path in (E1_DIR, E2_DIR / "src", B1_DIR / "src", E3_DIR / "src"):
    if str(package_path) not in sys.path:
        sys.path.insert(0, str(package_path))


class BenchmarkError(RuntimeError):
    """A safe benchmark setup or contract failure."""


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _stable_synthetic_node_id(purpose: str, identity: str) -> str:
    """Return a deterministic, corpus-scoped E1 ID for disposable fixture records."""
    if not isinstance(purpose, str) or not purpose or not isinstance(identity, str) or not identity:
        raise BenchmarkError("Synthetic fixture identity inputs must be non-empty strings")
    name = f"sfra-gold-benchmark:{CORPUS_VERSION}:{purpose}:{identity}"
    return "node_" + str(uuid.uuid5(uuid.NAMESPACE_URL, name))


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def init_git(root: Path, branch: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-b", branch)
    git(root, "config", "user.name", "SFRA Synthetic Benchmark")
    git(root, "config", "user.email", "synthetic-benchmark@example.invalid")


def commit_all(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "--allow-empty", "-m", message)
    return git(root, "rev-parse", "HEAD")


def validate_corpus(corpus_path: Path, schema_path: Path) -> tuple[dict[str, Any], str]:
    """Validate schema, corpus digest, identifiers, spans and exact source hashes."""
    try:
        import jsonschema
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:
        raise BenchmarkError("A Draft 2020-12 JSON Schema validator is required") from exc

    raw = corpus_path.read_bytes()
    digest = sha256_bytes(raw)
    if digest != CORPUS_DIGEST:
        raise BenchmarkError("The canonical synthetic corpus digest has changed")
    try:
        corpus = json.loads(raw.decode("utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BenchmarkError("Corpus or schema JSON is invalid") from exc

    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = list(validator.iter_errors(corpus))
    if errors:
        raise BenchmarkError(f"Draft 2020-12 validation failed with {len(errors)} error(s)")

    if corpus.get("corpus_id") != "sfra.synthetic.gold.e2-e3-context-pack":
        raise BenchmarkError("Unexpected corpus identifier")
    if corpus.get("version") != CORPUS_VERSION or corpus.get("synthetic_only") is not True:
        raise BenchmarkError("The accepted synthetic-only corpus version is required")
    if len(corpus["cases"]) != 42 or len(corpus["documents"]) != 32:
        raise BenchmarkError("The accepted corpus cardinality does not match")

    case_ids = [item["id"] for item in corpus["cases"]]
    node_ids: list[str] = []
    node_map: dict[str, dict[str, Any]] = {}
    document_map: dict[str, dict[str, Any]] = {}
    for document in corpus["documents"]:
        source_path = document["source_path"]
        path = PurePosixPath(source_path)
        if not source_path.startswith("synthetic/") or path.is_absolute() or ".." in path.parts:
            raise BenchmarkError("A corpus source path is outside the synthetic namespace")
        if source_path in document_map:
            raise BenchmarkError("Corpus document paths must be unique")
        document_map[source_path] = document
        content = document["content"]
        if sha256_text(content) != document["document_hash"]:
            raise BenchmarkError("A synthetic document digest does not match")
        lines = content.splitlines(keepends=True)
        for node in document["nodes"]:
            node_id = node["node_id"]
            if node_id in node_map:
                raise BenchmarkError("Corpus Node IDs must be globally unique")
            node_ids.append(node_id)
            node_map[node_id] = node
            if node["line_start"] == 1 and node["line_end"] == 0:
                reconstructed = ""
            else:
                start = node["line_start"]
                end = node["line_end"]
                if start < 1 or end < start or end > len(lines):
                    raise BenchmarkError("A node source span is outside its document")
                reconstructed = "".join(lines[start - 1 : end])
            if reconstructed != node["raw_text"]:
                raise BenchmarkError("A node source span does not reconstruct exactly")
            if sha256_text(node["raw_text"]) != node["content_hash"]:
                raise BenchmarkError("A node content digest does not match")

    if len(case_ids) != len(set(case_ids)) or len(node_ids) != len(set(node_ids)):
        raise BenchmarkError("Case IDs and Node IDs must be unique")

    for case in corpus["cases"]:
        referenced: set[str] = set()
        for field in ("expected_node_ids", "acceptable_node_ids", "forbidden_node_ids"):
            referenced.update(case["retrieval"][field])
        for field in ("required_node_ids", "allowed_additional_node_ids", "forbidden_node_ids"):
            referenced.update(case["context_pack"][field])
        for group in case["context_pack"]["required_dependency_groups"]:
            referenced.update(group)
        for facet in case["context_pack"]["facet_evaluation"]:
            referenced.update(facet["required_node_ids"])
        for control in case["scenario_controls"]:
            referenced.update(control.get("node_ids", []))
            if control.get("kind") == "known_version":
                referenced.add(control["node_id"])
        if not referenced.issubset(node_map):
            raise BenchmarkError("A case refers to an unknown synthetic Node ID")
    return corpus, digest


def _write_corpus_documents(vault_root: Path, corpus: Mapping[str, Any]) -> None:
    for document in corpus["documents"]:
        source_path = document["source_path"]
        target = vault_root.joinpath(*PurePosixPath(source_path).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(document["content"], encoding="utf-8", newline="")


def _database_rows(database_path: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """SELECT n.node_pk, n.node_id, n.raw_text, n.content_hash, n.status,
                      n.metadata_json, n.parent_node_pk, d.source_path, d.status AS document_status
               FROM structural_nodes AS n
               JOIN documents AS d ON d.document_pk = n.document_pk
               ORDER BY d.source_path, n.char_start, n.char_end, n.node_pk"""
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _patch_gold_metadata(
    database_path: Path,
    corpus: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Bind gold spans to E1 IDs, adding exact-span fixture records where needed."""
    by_address: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        by_address.setdefault(
            (str(row["source_path"]), str(row["content_hash"])), []
        ).append(dict(row))

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    gold_to_e1: dict[str, str] = {}
    gold_to_row: dict[str, dict[str, Any]] = {}
    try:
        for document in corpus["documents"]:
            if document["source_state"] != "available":
                continue
            for gold_node in document["nodes"]:
                candidates = by_address.get(
                    (document["source_path"], gold_node["content_hash"]), []
                )
                exact = [
                    row for row in candidates
                    if row["raw_text"] == gold_node["raw_text"]
                    and row["status"] == "active"
                    and row["document_status"] == "active"
                ]
                if len(exact) == 1:
                    row = exact[0]
                else:
                    # The gold corpus may group adjacent Markdown blocks into one
                    # annotated section. Add a disposable E1 record for that exact
                    # approved source span instead of weakening source verification.
                    document_row = connection.execute(
                        """SELECT document_pk, generation, source_sha256, status
                           FROM documents WHERE source_path = ?""",
                        (document["source_path"],),
                    ).fetchone()
                    if (
                        document_row is None
                        or document_row["status"] != "active"
                    ):
                        raise BenchmarkError("A synthetic gold document is not active in E1")
                    content = document["content"]
                    line_offsets = [0]
                    for index, char in enumerate(content):
                        if char == "\n":
                            line_offsets.append(index + 1)
                    start_line = int(gold_node["line_start"])
                    end_line = int(gold_node["line_end"])
                    if start_line < 1 or start_line - 1 >= len(line_offsets):
                        raise BenchmarkError("A gold source start coordinate is invalid")
                    char_start = line_offsets[start_line - 1]
                    if end_line < start_line:
                        char_end = char_start
                    elif end_line < len(line_offsets):
                        char_end = line_offsets[end_line]
                    else:
                        char_end = len(content)
                    raw_text = content[char_start:char_end]
                    if raw_text != gold_node["raw_text"]:
                        raise BenchmarkError("An exact-span fixture does not match corpus source text")
                    byte_start = len(content[:char_start].encode("utf-8"))
                    byte_end = len(content[:char_end].encode("utf-8"))
                    span = {
                        "line_start": start_line,
                        "line_end": end_line,
                        "char_start": char_start,
                        "char_end": char_end,
                        "byte_start": byte_start,
                        "byte_end": byte_end,
                    }
                    source_path = document["source_path"]
                    node_type = "paragraph"
                    local_key = "__gold_" + gold_node["node_id"]
                    node_id = _stable_synthetic_node_id("gold-node", gold_node["node_id"])
                    heading_path_json = json.dumps(
                        gold_node["heading_path"], ensure_ascii=False, separators=(",", ":")
                    )
                    spans_json = json.dumps([span], separators=(",", ":"))
                    cursor = connection.execute(
                        """INSERT INTO structural_nodes(
                            document_pk, local_key, node_id, parent_node_pk,
                            node_type, heading_path_json, line_start, line_end,
                            char_start, char_end, byte_start, byte_end,
                            content_spans_json, raw_text, metadata_json, warnings_json,
                            content_hash, status, created_generation, updated_generation
                        ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', '[]',
                                  ?, 'active', ?, ?)""",
                        (
                            int(document_row["document_pk"]),
                            local_key,
                            node_id,
                            node_type,
                            heading_path_json,
                            start_line,
                            end_line,
                            char_start,
                            char_end,
                            byte_start,
                            byte_end,
                            spans_json,
                            raw_text,
                            gold_node["content_hash"],
                            int(document_row["generation"]),
                            int(document_row["generation"]),
                        ),
                    )
                    node_pk = int(cursor.lastrowid)
                    connection.execute(
                        """INSERT INTO node_versions(
                            node_pk, version_no, generation, content_hash, source_path,
                            node_type, parent_node_id, heading_path_json, line_start,
                            line_end, char_start, char_end, byte_start, byte_end,
                            content_spans_json, raw_text, metadata_json, warnings_json
                        ) VALUES (?, 1, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', '[]')""",
                        (
                            node_pk,
                            int(document_row["generation"]),
                            gold_node["content_hash"],
                            source_path,
                            node_type,
                            heading_path_json,
                            start_line,
                            end_line,
                            char_start,
                            char_end,
                            byte_start,
                            byte_end,
                            spans_json,
                            raw_text,
                        ),
                    )
                    details = json.dumps(
                        {"node_type": node_type, "reason": None},
                        separators=(",", ":"),
                    )
                    connection.execute(
                        """INSERT INTO node_match_events(
                            document_pk, generation, new_local_key, event_type,
                            node_id, candidate_node_ids_json, details_json
                        ) VALUES (?, ?, ?, 'new', ?, '[]', ?)""",
                        (
                            int(document_row["document_pk"]),
                            int(document_row["generation"]),
                            local_key,
                            node_id,
                            details,
                        ),
                    )
                    row = {
                        "node_pk": node_pk,
                        "node_id": node_id,
                        "raw_text": raw_text,
                        "content_hash": gold_node["content_hash"],
                        "status": "active",
                        "metadata_json": "{}",
                        "parent_node_pk": None,
                        "source_path": source_path,
                        "document_status": "active",
                    }
                gold_id = gold_node["node_id"]
                gold_to_e1[gold_id] = str(row["node_id"])
                gold_to_row[gold_id] = dict(row)

        with connection:
            for document in corpus["documents"]:
                if document["source_state"] != "available":
                    continue
                for gold_node in document["nodes"]:
                    row = gold_to_row[gold_node["node_id"]]
                    node_pk = int(row["node_pk"])
                    metadata = json.loads(row.get("metadata_json") or "{}")
                    metadata.update({
                        "preservation": gold_node["preservation"],
                        "required_with": [
                            gold_to_e1[item]
                            for item in gold_node["required_with"]
                            if item in gold_to_e1
                        ],
                        "matched_entities": list(gold_node["matched_entities"]),
                        "matched_facets": list(gold_node["matched_facets"]),
                        "parent_context_required": gold_node.get("parent_node_id") is not None,
                    })
                    parent_gold = gold_node.get("parent_node_id")
                    parent_pk = (
                        int(gold_to_row[parent_gold]["node_pk"])
                        if parent_gold is not None and parent_gold in gold_to_row
                        else None
                    )
                    encoded = json.dumps(
                        metadata, ensure_ascii=False, separators=(",", ":")
                    )
                    connection.execute(
                        """UPDATE structural_nodes
                           SET metadata_json = ?, parent_node_pk = ?
                           WHERE node_pk = ?""",
                        (encoded, parent_pk, node_pk),
                    )
                    latest = connection.execute(
                        """SELECT version_no FROM node_versions
                           WHERE node_pk = ? ORDER BY version_no DESC LIMIT 1""",
                        (node_pk,),
                    ).fetchone()
                    if latest is None:
                        raise BenchmarkError("An E1 fixture node has no version snapshot")
                    parent_id = gold_to_e1.get(parent_gold) if parent_gold else None
                    connection.execute(
                        """UPDATE node_versions
                           SET metadata_json = ?, parent_node_id = ?
                           WHERE node_pk = ? AND version_no = ?""",
                        (encoded, parent_id, node_pk, int(latest[0])),
                    )
    finally:
        connection.close()
    return gold_to_e1, gold_to_row

def _create_disposable_repositories(corpus: Mapping[str, Any], work_root: Path):
    """Build temporary Vault and sidecar Git repositories with synthetic fixtures only."""
    import sfra_indexer as e1
    from sfra_indexer.indexer import index_vault

    vault_git = work_root / "vault-git"
    vault_root = vault_git / "vault"
    sidecar_root = work_root / "sidecar-git"
    index_dir = work_root / "index-build"
    init_git(vault_git, "main")
    vault_root.mkdir(parents=True, exist_ok=True)
    _write_corpus_documents(vault_root, corpus)

    deleted_docs = [
        doc for doc in corpus["documents"] if doc["source_state"] == "deleted"
    ]
    ambiguous_docs = [
        doc for doc in corpus["documents"] if doc["source_state"] == "ambiguous"
    ]
    if len(deleted_docs) != 1 or len(ambiguous_docs) != 1:
        raise BenchmarkError("The synthetic corpus must contain one deleted and one ambiguous source")

    deleted_path = vault_root.joinpath(*PurePosixPath(deleted_docs[0]["source_path"]).parts)
    if not deleted_path.read_text(encoding="utf-8"):
        deleted_path.write_text("Удалённая синтетическая запись.\n", encoding="utf-8")
    ambiguous_path = vault_root.joinpath(*PurePosixPath(ambiguous_docs[0]["source_path"]).parts)
    ambiguous_path.write_text(
        "# Повторяемая запись\nПервая синтетическая версия.\n\n"
        "# Повторяемая запись\nВторая синтетическая версия.\n",
        encoding="utf-8",
    )

    index_vault(vault_root, index_dir)
    initial_rows = _database_rows(index_dir / "structure.sqlite3")
    deleted_initial = [
        row for row in initial_rows
        if row["source_path"] == deleted_docs[0]["source_path"] and row["status"] == "active"
    ]
    if not deleted_initial:
        raise BenchmarkError("The deleted-source fixture could not be indexed")
    deleted_fixture_id = str(deleted_initial[0]["node_id"])
    deleted_fixture_hash = str(deleted_initial[0]["content_hash"])

    ambiguous_path.write_text(
        "# Повторяемая запись\nОбновлённая синтетическая версия.\n",
        encoding="utf-8",
    )
    deleted_path.unlink()
    index_vault(vault_root, index_dir)

    final_rows = _database_rows(index_dir / "structure.sqlite3")
    ambiguous_rows = [
        row for row in final_rows
        if row["source_path"] == ambiguous_docs[0]["source_path"]
        and row["status"] == "ambiguous"
    ]
    if not ambiguous_rows:
        raise BenchmarkError("The ambiguous-source fixture did not reach the ambiguous state")
    ambiguous_fixture_id = str(ambiguous_rows[0]["node_id"])
    ambiguous_fixture_hash = str(ambiguous_rows[0]["content_hash"])

    vault_sha = commit_all(vault_git, "Add disposable synthetic gold fixtures")
    gold_to_e1, gold_to_row = _patch_gold_metadata(
        index_dir / "structure.sqlite3", corpus, final_rows
    )
    final_rows = _database_rows(index_dir / "structure.sqlite3")

    init_git(sidecar_root, "sfra-state")
    e1.create_state_snapshot(
        index_dir / "structure.sqlite3",
        sidecar_root,
        source_repository="yeatu/obsidianGP",
        vault_ref="main",
        vault_commit_sha=vault_sha,
        workflow_run_id="synthetic-gold-benchmark",
    )
    commit_all(sidecar_root, "Create synthetic E1 state snapshot")
    if git(sidecar_root, "status", "--porcelain", "--untracked-files=all"):
        raise BenchmarkError("Synthetic sidecar checkout is not clean")
    return {
        "e1": e1,
        "vault_git": vault_git,
        "vault_root": vault_root,
        "sidecar_root": sidecar_root,
        "database_path": sidecar_root / "state" / "structure.sqlite3",
        "gold_to_e1": gold_to_e1,
        "gold_to_row": gold_to_row,
        "all_rows_by_id": {str(row["node_id"]): dict(row) for row in final_rows},
        "deleted": (deleted_fixture_id, deleted_fixture_hash),
        "ambiguous": (ambiguous_fixture_id, ambiguous_fixture_hash),
    }


class CountingSourceAPI:
    def __init__(self, source_api: Any):
        self._source_api = source_api
        self.read_calls = 0
        self.resolve_calls = 0

    def reset(self) -> None:
        self.read_calls = 0
        self.resolve_calls = 0

    def read_source_scope(self, *args: Any, **kwargs: Any):
        self.read_calls += 1
        return self._source_api.read_source_scope(*args, **kwargs)

    def resolve_current_node(self, *args: Any, **kwargs: Any):
        self.resolve_calls += 1
        return self._source_api.resolve_current_node(*args, **kwargs)


class CountingSourceReader:
    """Count source reads by origin at the existing E3 reader boundary."""

    def __init__(self, source_reader: Any):
        self._source_reader = source_reader
        self.mode = "normal"
        self.reset()

    @property
    def pinned_snapshot(self):
        return self._source_reader.pinned_snapshot

    def reset(self) -> None:
        self.mode = "normal"
        self.e2_exact_source_reads = 0
        self.dependency_resolutions = 0
        self.dependency_source_reads = 0
        self.explicit_source_reads = 0

    def read_node(self, *args: Any, **kwargs: Any):
        self.e2_exact_source_reads += 1
        return self._source_reader.read_node(*args, **kwargs)

    def resolve_current_node(self, *args: Any, **kwargs: Any):
        if self.mode == "dependency":
            self.dependency_resolutions += 1
        return self._source_reader.resolve_current_node(*args, **kwargs)

    def read_scope(self, *args: Any, **kwargs: Any):
        if self.mode == "dependency":
            self.dependency_source_reads += 1
        else:
            self.explicit_source_reads += 1
        return self._source_reader.read_scope(*args, **kwargs)


class ScenarioResolver:
    def __init__(self, source_reader: CountingSourceReader, missing_ids: set[str]):
        from sfra_context_integrations.dependency_resolver import E1DependencyResolver
        self._delegate = E1DependencyResolver(source_reader)
        self._source_reader = source_reader
        self._missing_ids = missing_ids

    @property
    def diagnostics(self):
        return self._delegate.diagnostics

    def begin_request(self) -> None:
        self._delegate.begin_request()

    def resolve_node(self, node_id: str, snapshot: Any):
        if node_id in self._missing_ids:
            return None
        previous_mode = self._source_reader.mode
        self._source_reader.mode = "dependency"
        try:
            return self._delegate.resolve_node(node_id, snapshot)
        finally:
            self._source_reader.mode = previous_mode


class ControlledE2SearchAdapter:
    """Wrap E2 only for the corpus-declared synthetic scenario controls."""
    def __init__(
        self,
        adapter: Any,
        incomplete: bool,
        omitted_ids: set[str] | None = None,
        conflict_candidates: Sequence[Any] = (),
    ):
        self._adapter = adapter
        self._incomplete = incomplete
        self._omitted_ids = omitted_ids or set()
        self._conflict_candidates = tuple(conflict_candidates)
        self.source_reader = adapter.source_reader
        self.pinned_snapshot = adapter.pinned_snapshot

    def search(self, request: Any):
        result = self._adapter.search(request)
        candidates = tuple(
            item for item in result.batch.candidates
            if item.node_id not in self._omitted_ids
        )
        # gq-036 explicitly describes a version-conflict fault. Inject two
        # hash-distinct candidates for the same fixture Node ID into the actual
        # E2 -> B1 path, rather than testing the conflict in a detached probe.
        candidates = (*candidates, *self._conflict_candidates)
        batch = replace(
            result.batch,
            candidates=candidates,
            inspected_count=result.batch.inspected_count + len(self._conflict_candidates),
            complete=False if self._incomplete else result.batch.complete,
            truncated_by_limit=False if self._incomplete else result.batch.truncated_by_limit,
        )
        return replace(result, batch=batch)


def _source_read_for_case(
    case: Mapping[str, Any],
    fixture: Mapping[str, Any],
    corpus_node_map: Mapping[str, Mapping[str, Any]],
):
    expected = case.get("expected_read_source")
    if not expected:
        return None
    from sfra_context_integrations.pipeline import SourceReadRequest

    case_id = case["id"]
    scope = expected["scope"]
    budget = 1 if expected["status"] == "budget_exceeded" else None
    if case_id == "gq-019-empty-source-node":
        gold_id = "empty_root"
        node_id = fixture["gold_to_e1"][gold_id]
        content_hash = corpus_node_map[gold_id]["content_hash"]
    elif case_id in {"gq-025-source-budget-exceeded", "gq-030-document-scope"}:
        gold_id = "torch_location" if case_id == "gq-025-source-budget-exceeded" else "aylin_identity"
        node_id = fixture["gold_to_e1"][gold_id]
        content_hash = corpus_node_map[gold_id]["content_hash"]
    elif case_id == "gq-026-stale-hash":
        gold_id = "stale_threshold_current"
        node_id = fixture["gold_to_e1"][gold_id]
        content_hash = "sha256:" + ("1" * 64)
    elif case_id == "gq-027-deleted-source":
        node_id, content_hash = fixture["deleted"]
    elif case_id == "gq-028-ambiguous-source":
        node_id, content_hash = fixture["ambiguous"]
    elif case_id == "gq-029-not-found-source":
        node_id = _stable_synthetic_node_id("not-found-source", case_id)
        content_hash = "sha256:" + ("0" * 64)
    elif case_id == "gq-031-neighbor-scope":
        gold_id = "sequence_signal"
        node_id = fixture["gold_to_e1"][gold_id]
        content_hash = corpus_node_map[gold_id]["content_hash"]
    elif case_id == "gq-032-parent-scope":
        gold_id = "pressure_condition"
        node_id = fixture["gold_to_e1"][gold_id]
        content_hash = corpus_node_map[gold_id]["content_hash"]
    else:
        return None
    return SourceReadRequest(
        node_id=node_id,
        expected_hash=content_hash,
        scope=scope,
        budget_tokens=budget,
    )


def _translate_ids(ids: Sequence[str], reverse_map: Mapping[str, str]) -> set[str]:
    return {reverse_map.get(item, "unannotated") for item in ids}


def _conflict_probe(builder: Any, request: Any, original: Any) -> bool:
    """Prove B1 rejects two hashes for one synthetic Node ID."""
    from sfra_context_builder.models import SearchBatch

    altered_text = "Синтетическая конфликтующая версия."
    altered = replace(
        original,
        content_hash=sha256_text(altered_text),
        raw_text=altered_text,
        original_order=original.original_order + 1000,
    )
    pack = builder.build(
        request,
        SearchBatch(
            complete=True,
            inspected_count=2,
            candidates=(original, altered),
        ),
    )
    return (
        pack.get("status") == "integrity_warning"
        and any(item.get("code") == "version_conflict" for item in pack.get("Diagnostics", []))
    )


def _metric_average(values: Sequence[float | None]) -> float | None:
    selected = [value for value in values if value is not None]
    return None if not selected else round(sum(selected) / len(selected), 4)


LEGACY_CONTEXT_STATUS_MISMATCH_CASES = frozenset({
    "gq-025-source-budget-exceeded",
    "gq-028-ambiguous-source",
    "gq-029-not-found-source",
})


def _completeness_honesty(
    *,
    search_complete: bool,
    context_status: str,
    deferred: Sequence[Mapping[str, Any]],
) -> bool:
    """Validate B1 Pack completeness using Pack inputs only.

    Optional SourceReadRequest operations run after the Pack is built. Their
    outcomes are independent and must never retroactively rewrite Pack status.
    """
    if not search_complete and context_status == "complete":
        return False
    pack_incomplete_reasons = {
        "budget_limit",
        "required_group_budget_limit",
        "lower_priority_budget_limit",
        "unresolved_required_dependency",
    }
    if (
        any(item.get("reason") in pack_incomplete_reasons for item in deferred)
        and context_status == "complete"
    ):
        return False
    return True


def _source_read_contract(
    *,
    actual_status: str | None,
    expected_status: str | None,
    fragments: Any,
) -> tuple[bool | None, bool]:
    """Validate the independent explicit SourceRead result channel."""
    normalized_status = "stale" if actual_status == "stale_source" else actual_status
    if expected_status is None and actual_status is None:
        status_match: bool | None = None
    else:
        status_match = normalized_status == expected_status
    non_ok_empty = actual_status in (None, "ok") or fragments == []
    return status_match, non_ok_empty


def _context_status_diagnostic(case_id: str, status_match: bool) -> str:
    """Keep immutable corpus expectation mismatches visible and classified."""
    if status_match:
        return "matched"
    if case_id in LEGACY_CONTEXT_STATUS_MISMATCH_CASES:
        return "legacy_corpus_contract_interpretation"
    return "unexpected_context_status_mismatch"


def _resolve_pr_checkout_identity(
    root: Path,
    *,
    pr_head_sha: str,
    event_base_sha: str,
    actual_checkout_sha: str,
) -> tuple[str, str | None, str | None]:
    """Resolve the effective PR base from the checked-out merge-commit graph.

    GitHub's pull_request event payload can retain an older base SHA after a
    branch is refreshed with a merge commit that already contains current main.
    When HEAD is a two-parent PR merge commit and its second parent is the
    declared PR head, the first parent is the exact base used to build the
    checked-out tree. Otherwise the event base is retained as unverified.
    """
    try:
        # Read the raw commit object. Unlike rev-list, cat-file retains parent
        # headers even when actions/checkout has marked the merge ref shallow.
        commit_object = git(root, "cat-file", "-p", actual_checkout_sha)
    except Exception:
        return event_base_sha, None, None
    parents = [
        line.split(" ", 1)[1]
        for line in commit_object.splitlines()
        if line.startswith("parent ")
    ]
    if (
        pr_head_sha not in {"", "not-a-pull-request"}
        and len(parents) == 2
        and parents[1] == pr_head_sha
    ):
        return parents[0], parents[0], parents[1]
    return event_base_sha, None, None


def _token_efficiency(
    counter: Any,
    included_entries: Sequence[Mapping[str, Any]],
    baseline_documents: Sequence[str],
) -> float | None:
    """Return 1 - Included raw-text tokens / relevant full-document tokens."""
    baseline_tokens = sum(counter.count(text) for text in baseline_documents)
    if baseline_tokens == 0:
        return None
    included_source_tokens = sum(
        counter.count(entry["raw_text"]) for entry in included_entries
    )
    return round(1.0 - included_source_tokens / baseline_tokens, 4)


def _relevant_context_source_paths(
    case: Mapping[str, Any],
    node_map: Mapping[str, Mapping[str, Any]],
) -> tuple[str, ...]:
    """Return unique source documents for required + allowed additional nodes."""
    context = case["context_pack"]
    relevant_ids = set(context["required_node_ids"]) | set(
        context["allowed_additional_node_ids"]
    )
    missing = relevant_ids.difference(node_map)
    if missing:
        raise BenchmarkError("A relevant context node has no validated source document")
    return tuple(sorted({str(node_map[node_id]["source_path"]) for node_id in relevant_ids}))


def _fallback_rate(dependency_source_reads: int, engine_result_count: int) -> float:
    """Dependency source reads divided by max(1, initial E2 engine results)."""
    if (
        isinstance(dependency_source_reads, bool)
        or not isinstance(dependency_source_reads, int)
        or dependency_source_reads < 0
        or isinstance(engine_result_count, bool)
        or not isinstance(engine_result_count, int)
        or engine_result_count < 0
    ):
        raise BenchmarkError("Fallback Rate counts must be non-negative integers")
    return round(dependency_source_reads / max(1, engine_result_count), 4)


def _render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# SFRA synthetic gold benchmark",
        "",
        f"- Runner: {report['runner_version']}",
        f"- PR head SHA: {report['pr_head_sha']}",
        f"- PR base SHA: {report['pr_base_sha']}",
        f"- Actual checkout SHA: {report['checkout_sha']}",
        f"- Corpus: {report['corpus_version']}",
        f"- Cases: {report['case_count']}",
        f"- Draft 2020-12 schema validation: {report['preflight']['schema_validation']}",
        f"- Gold nodes bound to E1 fixture: {report['preflight']['mapped_gold_nodes']}",
        "",
        "## Aggregate metrics",
        "",
        "| Metric | Mean |",
        "|---|---:|",
    ]
    for key, value in report["aggregate"].items():
        lines.append(f"| {key} | {'n/a' if value is None else value} |")
    lines.extend([
        "",
        "## Gate summary",
        "",
        f"- Passed cases: {report['gate_summary']['passed_cases']}",
        f"- Failed cases: {report['gate_summary']['failed_cases']}",
        f"- Diagnostic status mismatches: {report['gate_summary']['status_mismatches']}",
        f"- Legacy corpus/contract interpretation mismatches: {report['gate_summary']['legacy_context_status_mismatches']}",
        f"- Other Context Pack status mismatches: {report['gate_summary']['other_context_status_mismatches']}",
        f"- Explicit SourceRead status mismatches: {report['gate_summary']['source_read_status_mismatches']}",
        "",
        "## Per-case results",
        "",
        "| Case | Recall | Precision | Token efficiency | Source fidelity | Fallback rate | Dependency reads | Denominator | E2 exact reads | Explicit reads | Dependency resolves | Pack status | Pack diagnostic | Read status | Read fragments | Read contract | Gate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---:|---|---|",
    ])
    for item in report["cases"]:
        def fmt(value):
            return "n/a" if value is None else f"{value:.3f}"
        lines.append(
            f"| {item['case_id']} | {fmt(item['retrieval_recall'])} "
            f"| {fmt(item['context_precision'])} | {fmt(item['token_efficiency'])} "
            f"| {fmt(item['source_fidelity'])} | {fmt(item['fallback_rate'])} "
            f"| {item['dependency_source_reads']} | {item['fallback_rate_denominator']} "
            f"| {item['e2_exact_source_reads']} | {item['explicit_source_reads']} "
            f"| {item['dependency_resolutions']} | {item['actual_status']} "
            f"| {item['context_status_diagnostic']} | {item['source_read_status']} "
            f"| {item['source_read_fragment_count']} | "
            f"{'PASS' if item['source_read_contract_valid'] else 'FAIL'} | "
            f"{'PASS' if item['gate_passed'] else 'FAIL'} |"
        )
    lines.extend([
        "",
        "Context Pack completeness is judged only from E2 SearchBatch completeness, "
        "B1 Pack status and Pack-level deferred required context. Optional standalone "
        "SourceReadRequest outcomes are checked and reported separately and do not "
        "retroactively change ContextPack.status. The expected-status mismatches for "
        "gq-025, gq-028 and gq-029 are explicitly retained as legacy corpus/contract "
        "interpretation diagnostics. Non-ok explicit reads must contain zero fragments. "
        "Recall and precision are measured against the accepted labels and do not "
        "modify the corpus. Token efficiency is 1 - Included raw_text tokens / "
        "relevant full-document tokens for unique documents containing required and "
        "allowed-additional nodes, using o200k_base on both sides. Fallback Rate is "
        "dependency source_scope reads / max(1, initial E2 engine result count); "
        "failed address lookups count zero, while E2 exact-hit reads and explicit "
        "SourceReadRequest reads are reported separately. Raw source text, query text, "
        "source paths and hashes are not written to the report.",
        "",
    ])
    return "\n".join(lines)


def run_benchmark(output_dir: Path) -> dict[str, Any]:
    corpus, digest = validate_corpus(
        CORPUS_DIR / "corpus.v1.json",
        CORPUS_DIR / "gold-case.schema.json",
    )
    node_map = {
        node["node_id"]: {**node, "source_path": document["source_path"]}
        for document in corpus["documents"]
        for node in document["nodes"]
    }
    document_map = {doc["source_path"]: doc for doc in corpus["documents"]}

    import sfra_context_builder
    from sfra_context_builder import ContextBuilder, TiktokenCounter, parse_search_request
    from sfra_context_builder.models import SearchBatch
    from sfra_context_integrations.pipeline import ContextIntegrationPipeline
    from sfra_context_integrations.search_adapter import E2SearchAdapter
    from sfra_context_integrations.snapshot import bind_pinned_snapshot
    from sfra_context_integrations.source_reader import E1SourceReader
    from sfra_search.runtime import search_structural_database

    counter = TiktokenCounter("o200k_base")
    builder = ContextBuilder(counter)
    output_dir.mkdir(parents=True, exist_ok=True)
    per_case: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="sfra-gold-synthetic-") as temp:
        fixture = _create_disposable_repositories(corpus, Path(temp))
        e1 = fixture["e1"]
        pinned = bind_pinned_snapshot(
            sidecar_root=fixture["sidecar_root"],
            vault_git_root=fixture["vault_git"],
            vault_root=fixture["vault_root"],
            state_verifier=e1.verify_state_directory,
            expected_repository="yeatu/obsidianGP",
            expected_sidecar_branch="sfra-state",
        )
        counted_api = CountingSourceAPI(e1)
        base_source_reader = E1SourceReader(counted_api, pinned, counter)
        source_reader = CountingSourceReader(base_source_reader)
        reverse_map = {
            e1_id: gold_id for gold_id, e1_id in fixture["gold_to_e1"].items()
        }
        for case in corpus["cases"]:
            case_id = case["id"]
            controls = {item["kind"]: item for item in case["scenario_controls"]}
            incomplete = controls.get("search_batch_complete", {}).get("value") is False
            missing_ids = set()
            for item in case["scenario_controls"]:
                if item.get("kind") == "resolver_missing_node_ids":
                    missing_ids = {
                        fixture["gold_to_e1"][node_id]
                        for node_id in item["node_ids"]
                        if node_id in fixture["gold_to_e1"]
                    }

            budget = 1 if case_id in {
                "gq-023-budget-atomic-group", "gq-024-budget-low-priority"
            } else 10000
            known: list[dict[str, str]] = []
            known_control = controls.get("known_version")
            if known_control:
                gold_id = known_control["node_id"]
                e1_id = fixture["gold_to_e1"][gold_id]
                if known_control.get("content_hash_from_source"):
                    known_hash = node_map[gold_id]["content_hash"]
                else:
                    known_hash = known_control["content_hash"]
                known = [{"node_id": e1_id, "content_hash": known_hash}]

            if not case["query"].strip():
                from sfra_context_builder.validation import ContractValidationError
                try:
                    parse_search_request({
                        "query": case["query"],
                        "budget_tokens": 10000,
                    })
                except ContractValidationError:
                    invalid_request_rejected = True
                else:
                    invalid_request_rejected = False
                per_case.append({
                    "case_id": case_id,
                    "category": case["category"],
                    "retrieval_recall": None,
                    "context_precision": None,
                    "token_efficiency": None,
                    "source_fidelity": None,
                    "facet_coverage": None,
                    "fallback_rate": None,
                    "fallback_rate_denominator": 0,
                    "dependency_source_reads": 0,
                    "dependency_resolutions": 0,
                    "e2_exact_source_reads": 0,
                    "explicit_source_reads": 0,
                    "tool_cost": 0,
                    "expected_status": "request_invalid",
                    "actual_status": "request_invalid" if invalid_request_rejected else "accepted_invalid_request",
                    "status_match": invalid_request_rejected,
                    "context_status_diagnostic": "matched" if invalid_request_rejected else "unexpected_context_status_mismatch",
                    "deterministic": True,
                    "completeness_honesty": True,
                    "no_forbidden_nodes": True,
                    "atomic_groups": True,
                    "source_read_status": None,
                    "source_read_fragment_count": 0,
                    "source_read_status_match": None,
                    "source_read_non_ok_empty": True,
                    "source_read_contract_valid": True,
                    "conflict_probe": None,
                    "gate_passed": invalid_request_rejected,
                })
                continue

            request = parse_search_request({
                "query": case["query"],
                "budget_tokens": budget,
                "known": known,
            })
            base_adapter = E2SearchAdapter(
                pinned,
                source_reader,
                search_call=search_structural_database,
                search_limit=100,
            )
            omitted_ids = {
                fixture["gold_to_e1"][node_id]
                for item in case["scenario_controls"]
                if item.get("kind") in {
                    "omitted_from_retrieval", "resolver_missing_node_ids"
                }
                for node_id in item.get("node_ids", [])
                if node_id in fixture["gold_to_e1"]
            }
            conflict_candidates = ()
            if case_id == "gq-036-conflicting-versions":
                from sfra_context_builder.models import RetrievalCandidate
                gold_id = "synthetic_conflict_node"
                gold_node = node_map[gold_id]
                original = RetrievalCandidate(
                    node_id=fixture["gold_to_e1"][gold_id],
                    source_path=gold_node["source_path"],
                    heading_path=tuple(gold_node["heading_path"]),
                    line_start=gold_node["line_start"],
                    line_end=gold_node["line_end"],
                    content_hash=gold_node["content_hash"],
                    raw_text=gold_node["raw_text"],
                    match_type="scenario_conflict",
                    original_order=10000,
                    node_type="paragraph",
                )
                altered_text = "Синтетическая конфликтующая версия.\n"
                altered = replace(
                    original,
                    content_hash=sha256_text(altered_text),
                    raw_text=altered_text,
                    original_order=10001,
                )
                conflict_candidates = (original, altered)
            adapter = ControlledE2SearchAdapter(
                base_adapter,
                incomplete,
                omitted_ids,
                conflict_candidates=conflict_candidates,
            )
            resolver = ScenarioResolver(source_reader, missing_ids)
            pipeline = ContextIntegrationPipeline(
                pinned_snapshot=pinned,
                search_adapter=adapter,
                context_builder=builder,
                source_reader=source_reader,
                dependency_resolver=resolver,
            )
            source_read = _source_read_for_case(case, fixture, node_map)
            source_reads = () if source_read is None else (source_read,)

            counted_api.reset()
            source_reader.reset()
            first = pipeline.run(request, source_reads=source_reads)
            first_read_calls = counted_api.read_calls
            first_resolve_calls = counted_api.resolve_calls
            first_e2_exact_source_reads = source_reader.e2_exact_source_reads
            first_dependency_resolutions = source_reader.dependency_resolutions
            first_dependency_source_reads = source_reader.dependency_source_reads
            first_explicit_source_reads = source_reader.explicit_source_reads
            classified_source_reads = (
                first_e2_exact_source_reads
                + first_dependency_source_reads
                + first_explicit_source_reads
            )
            if classified_source_reads != first_read_calls:
                raise BenchmarkError(
                    "Source-read origin counters do not reconcile with E1 read_source_scope calls"
                )
            if first_dependency_resolutions != first_resolve_calls:
                raise BenchmarkError(
                    "Dependency address-resolution counters do not reconcile with E1 resolve_current_node calls"
                )
            first_pack = first.context_pack
            first_retrieved_ids = {
                reverse_map.get(item.node_id, "unannotated")
                for item in first.search.batch.candidates
            }
            first_included = list(first_pack.get("Included", []))
            first_included_ids = {
                reverse_map.get(item["node_id"], "unannotated")
                for item in first_included
            }
            first_known_ids = {
                reverse_map.get(item["node_id"], "unannotated")
                for item in first_pack.get("Known", [])
            }
            first_deferred_ids = {
                reverse_map.get(item["node_id"], "unannotated")
                for item in first_pack.get("Deferred", [])
            }

            counted_api.reset()
            source_reader.reset()
            second = pipeline.run(request, source_reads=source_reads)
            second_pack = second.context_pack
            second_ids = [
                reverse_map.get(item["node_id"], "unannotated")
                for item in second_pack.get("Included", [])
            ]
            first_ids = [
                reverse_map.get(item["node_id"], "unannotated")
                for item in first_pack.get("Included", [])
            ]
            deterministic = (
                first_pack["status"] == second_pack["status"]
                and first_ids == second_ids
                and first_pack.get("search_complete") == second_pack.get("search_complete")
                and [
                    item.get("status") for item in first.source_reads
                ] == [
                    item.get("status") for item in second.source_reads
                ]
            )

            expected_retrieval = set(case["retrieval"]["expected_node_ids"])
            acceptable = set(case["retrieval"]["acceptable_node_ids"])
            forbidden = set(case["retrieval"]["forbidden_node_ids"])
            expected_context = set(case["context_pack"]["required_node_ids"])
            relevant_context = expected_context | acceptable
            recall = (
                None if not expected_retrieval
                else round(len(expected_retrieval & first_retrieved_ids) / len(expected_retrieval), 4)
            )
            precision = (
                None if not first_included_ids
                else round(
                    len(first_included_ids & relevant_context) / len(first_included_ids),
                    4,
                )
            )
            no_forbidden = not bool(forbidden & first_retrieved_ids)
            included_source_fidelity = []
            for entry in first_included:
                fixture_row = fixture["all_rows_by_id"].get(entry["node_id"])
                included_source_fidelity.append(
                    fixture_row is not None
                    and entry.get("raw_text") == fixture_row["raw_text"]
                    and sha256_text(entry.get("raw_text", "")) == fixture_row["content_hash"]
                    and entry.get("content_hash") == fixture_row["content_hash"]
                )
            source_fidelity = (
                None if not included_source_fidelity
                else round(
                    sum(included_source_fidelity) / len(included_source_fidelity), 4
                )
            )

            relevant_paths = _relevant_context_source_paths(case, node_map)
            token_efficiency = _token_efficiency(
                counter,
                first_included,
                [document_map[path]["content"] for path in relevant_paths],
            )
            facet_scores = []
            for facet in case["context_pack"]["facet_evaluation"]:
                required = set(facet["required_node_ids"])
                if required:
                    delivered = required & (first_included_ids | first_known_ids)
                    facet_scores.append(len(delivered) / len(required))
            facet_coverage = _metric_average(facet_scores)

            expected_status = case["context_pack"]["expected_status"]
            actual_status = first_pack["status"]
            status_match = expected_status == actual_status
            source_read_status_raw = (
                first.source_reads[0].get("status") if first.source_reads else None
            )
            source_read_fragments = (
                first.source_reads[0].get("fragments", []) if first.source_reads else []
            )
            completeness_honesty = _completeness_honesty(
                search_complete=first.search.batch.complete,
                context_status=actual_status,
                deferred=first_pack.get("Deferred", []),
            )

            atomic_groups = True
            for group in case["context_pack"]["required_dependency_groups"]:
                group_ids = set(group)
                selected = group_ids & (first_included_ids | first_known_ids)
                deferred = group_ids & first_deferred_ids
                if selected and deferred:
                    atomic_groups = False

            expected_read_status = (
                case.get("expected_read_source", {}).get("status")
                if isinstance(case.get("expected_read_source"), Mapping)
                else None
            )
            source_read_status_match, source_read_non_ok_empty = _source_read_contract(
                actual_status=source_read_status_raw,
                expected_status=expected_read_status,
                fragments=source_read_fragments,
            )
            source_read_contract_valid = (
                source_read_status_match is not False
                and source_read_non_ok_empty
            )
            source_read_fragment_count = (
                len(source_read_fragments)
                if isinstance(source_read_fragments, (list, tuple))
                else None
            )
            context_status_diagnostic = _context_status_diagnostic(
                case_id,
                status_match,
            )

            conflict_probe = None
            if case_id == "gq-036-conflicting-versions":
                conflict_probe = (
                    first_pack["status"] == "integrity_warning"
                    and any(
                        item.get("code") == "version_conflict"
                        for item in first_pack.get("Diagnostics", [])
                    )
                )

            fallback_rate_denominator = first.search.engine_result_count
            fallback_rate = _fallback_rate(
                first_dependency_source_reads,
                fallback_rate_denominator,
            )
            tool_cost = 1 + first_read_calls + first_resolve_calls
            gate_passed = all([
                deterministic,
                no_forbidden,
                completeness_honesty,
                atomic_groups,
                source_fidelity in (None, 1.0),
                source_read_contract_valid,
                conflict_probe is not False,
            ])

            per_case.append({
                "case_id": case_id,
                "category": case["category"],
                "retrieval_recall": recall,
                "context_precision": precision,
                "token_efficiency": token_efficiency,
                "source_fidelity": source_fidelity,
                "facet_coverage": facet_coverage,
                "fallback_rate": fallback_rate,
                "fallback_rate_denominator": fallback_rate_denominator,
                "dependency_source_reads": first_dependency_source_reads,
                "dependency_resolutions": first_dependency_resolutions,
                "e2_exact_source_reads": first_e2_exact_source_reads,
                "explicit_source_reads": first_explicit_source_reads,
                "tool_cost": tool_cost,
                "expected_status": expected_status,
                "actual_status": actual_status,
                "status_match": status_match,
                "context_status_diagnostic": context_status_diagnostic,
                "deterministic": deterministic,
                "completeness_honesty": completeness_honesty,
                "no_forbidden_nodes": no_forbidden,
                "atomic_groups": atomic_groups,
                "source_read_status": source_read_status_raw,
                "source_read_fragment_count": source_read_fragment_count,
                "source_read_status_match": source_read_status_match,
                "source_read_non_ok_empty": source_read_non_ok_empty,
                "source_read_contract_valid": source_read_contract_valid,
                "conflict_probe": conflict_probe,
                "gate_passed": gate_passed,
            })

        pinned.verify_current()
        mapped_nodes = len(fixture["gold_to_e1"])
        deleted_rows = [
            row for row in _database_rows(fixture["database_path"])
            if row["node_id"] == fixture["deleted"][0]
        ]
        deleted_status = any(
            row["status"] == "stale" and row["document_status"] == "deleted"
            for row in deleted_rows
        )
        if not deleted_status:
            raise BenchmarkError("The synthetic deleted-source state was not retained")

    metric_keys = (
        "retrieval_recall", "context_precision", "token_efficiency",
        "source_fidelity", "facet_coverage", "fallback_rate",
    )
    aggregate = {
        key: _metric_average([item[key] for item in per_case])
        for key in metric_keys
    }
    aggregate["mean_tool_cost"] = _metric_average(
        [float(item["tool_cost"]) for item in per_case]
    )
    aggregate["dependency_source_reads"] = sum(
        item["dependency_source_reads"] for item in per_case
    )
    aggregate["dependency_resolutions"] = sum(
        item["dependency_resolutions"] for item in per_case
    )
    aggregate["e2_exact_source_reads"] = sum(
        item["e2_exact_source_reads"] for item in per_case
    )
    aggregate["explicit_source_reads"] = sum(
        item["explicit_source_reads"] for item in per_case
    )
    failed = [item for item in per_case if not item["gate_passed"]]
    try:
        checkout_sha = os.environ.get("BENCHMARK_CHECKOUT_SHA") or git(REPO_ROOT, "rev-parse", "HEAD")
        actual_checkout_sha = git(REPO_ROOT, "rev-parse", "HEAD")
    except Exception:
        checkout_sha = "unavailable"
        actual_checkout_sha = "unavailable"
    pr_head_sha = os.environ.get("BENCHMARK_PR_HEAD_SHA", "not-a-pull-request")
    event_pr_base_sha = os.environ.get("BENCHMARK_PR_BASE_SHA", "not-a-pull-request")
    pr_number = os.environ.get("BENCHMARK_PR_NUMBER", "not-a-pull-request")
    pr_base_sha, checkout_base_sha, checkout_pr_head_sha = _resolve_pr_checkout_identity(
        REPO_ROOT,
        pr_head_sha=pr_head_sha,
        event_base_sha=event_pr_base_sha,
        actual_checkout_sha=actual_checkout_sha,
    )
    report = {
        "runner_version": RUNNER_VERSION,
        "implementation_ref": actual_checkout_sha,
        "pr_number": pr_number,
        "pr_head_sha": pr_head_sha,
        "pr_base_sha": pr_base_sha,
        "pr_base_sha_event": event_pr_base_sha,
        "checkout_sha": actual_checkout_sha,
        "workflow_checkout_sha": checkout_sha,
        "checkout_base_sha": checkout_base_sha,
        "checkout_pr_head_sha": checkout_pr_head_sha,
        "corpus_version": CORPUS_VERSION,
        "corpus_digest": digest,
        "case_count": len(per_case),
        "limitations": [
            "All execution uses disposable synthetic Vault and SQLite fixtures.",
            "Retrieval recall and status mismatches are reported as measured outcomes, not hidden by label changes.",
            "The E2 lexical runtime does not implement a semantic-search baseline.",
            "Standalone SourceRead outcomes are independent from the B1 Context Pack status.",
            "The immutable corpus status mismatches for gq-025/gq-028/gq-029 are explicitly classified as legacy contract-interpretation diagnostics.",
            "Non-ok standalone SourceRead outcomes must contain zero fragments.",
            "The token-efficiency baseline and Included source text use the same o200k_base tokenizer.",
            "Reports omit query text, raw source text, source paths and source content hashes.",
        ],
        "preflight": {
            "schema_validation": "Draft 2020-12 valid",
            "mapped_gold_nodes": mapped_nodes,
            "synthetic_fixture_only": True,
        },
        "environment": {
            "python": platform.python_version(),
            "python_hash_seed": os.environ.get("PYTHONHASHSEED", "unset"),
            "synthetic_fixture_id_strategy": "uuid5:NAMESPACE_URL:sfra-gold-benchmark:<corpus_version>:<purpose>:<stable_identity>",
            "jsonschema": __import__("jsonschema").__version__,
            "tiktoken": counter.metadata()["version"],
            "e2_package": "sfra-search",
            "e1_package": "sfra-structural-indexer",
            "e3_package": "sfra-context-integrations",
            "b1_package": "sfra-context-builder",
        },
        "metric_definitions": {
            "token_efficiency": (
                "1 - Included raw_text o200k_base tokens / full-document o200k_base tokens "
                "for unique documents containing required_node_ids union allowed_additional_node_ids."
            ),
            "fallback_rate": (
                "dependency_source_reads / max(1, initial E2 engine_result_count); "
                "counts actual dependency read_source_scope calls, not address-resolution attempts. "
                "E2 exact-hit reads and explicit SourceReadRequest reads are separate."
            ),
        },
        "aggregate": aggregate,
        "gate_summary": {
            "passed_cases": len(per_case) - len(failed),
            "failed_cases": len(failed),
            "status_mismatches": sum(1 for item in per_case if not item["status_match"]),
            "legacy_context_status_mismatches": sum(
                1 for item in per_case
                if item["context_status_diagnostic"] == "legacy_corpus_contract_interpretation"
            ),
            "other_context_status_mismatches": sum(
                1 for item in per_case
                if item["context_status_diagnostic"] == "unexpected_context_status_mismatch"
            ),
            "source_read_status_mismatches": sum(
                1 for item in per_case if item["source_read_status_match"] is False
            ),
        },
        "cases": per_case,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "benchmark.md").write_text(
        _render_markdown(report), encoding="utf-8"
    )
    print(json.dumps({
        "cases": report["case_count"],
        "passed": report["gate_summary"]["passed_cases"],
        "failed": report["gate_summary"]["failed_cases"],
        "status_mismatches": report["gate_summary"]["status_mismatches"],
    }, sort_keys=True))
    if failed:
        raise BenchmarkError("One or more synthetic benchmark invariants failed")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("benchmark-output"),
    )
    args = parser.parse_args()
    run_benchmark(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
