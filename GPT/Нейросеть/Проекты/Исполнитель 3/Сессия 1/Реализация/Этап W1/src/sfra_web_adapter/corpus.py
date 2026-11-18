"""Pinned, synthetic-only gold corpus reader and response projection."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Mapping

CORPUS_ID = "sfra.synthetic.gold.e2-e3-context-pack"
CORPUS_VERSION = "1.0.0"
CORPUS_SHA256 = "sha256:915304e812906f64003d9aacb0dd4b7701f7fbcf4f24fdc3cda21d1108b13068"
CORPUS_RELATIVE_PATH = Path(
    "GPT/Нейросеть/Проекты/Аналитик 1/Сессия 4/Issue 41/corpus.v1.json"
)

@dataclass(frozen=True, slots=True)
class SyntheticNode:
    node_id: str
    source_path: str
    content_hash: str
    line_start: int
    line_end: int
    raw_text: str

@dataclass(frozen=True, slots=True)
class SyntheticCase:
    case_id: str
    query: str
    node_ids: tuple[str, ...]

class SyntheticGoldCorpus:
    """Load only the pinned gold corpus; never consult Vault or production index."""
    def __init__(self, raw: bytes):
        actual = "sha256:" + hashlib.sha256(raw).hexdigest()
        if actual != CORPUS_SHA256:
            raise ValueError("synthetic gold corpus digest mismatch")
        data = json.loads(raw.decode("utf-8"))
        if (data.get("corpus_id") != CORPUS_ID or
                data.get("version") != CORPUS_VERSION or
                data.get("synthetic_only") is not True):
            raise ValueError("synthetic gold corpus identity mismatch")
        nodes: dict[str, SyntheticNode] = {}
        for document in data.get("documents", []):
            source_path = document.get("source_path")
            if not isinstance(source_path, str) or not source_path.startswith("synthetic/"):
                raise ValueError("gold corpus contains a non-synthetic source path")
            for raw_node in document.get("nodes", []):
                node_id = raw_node.get("node_id")
                raw_text = raw_node.get("raw_text")
                content_hash = raw_node.get("content_hash")
                line_start, line_end = raw_node.get("line_start"), raw_node.get("line_end")
                if (not all(isinstance(x, str) for x in (node_id, raw_text, content_hash)) or
                        isinstance(line_start, bool) or not isinstance(line_start, int) or
                        isinstance(line_end, bool) or not isinstance(line_end, int) or
                        line_start < 1 or line_end < line_start):
                    raise ValueError("gold corpus node is malformed")
                actual_node_hash = "sha256:" + hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
                if actual_node_hash != content_hash:
                    raise ValueError("gold corpus node content hash mismatch")
                if node_id in nodes:
                    raise ValueError("gold corpus node IDs must be unique")
                nodes[node_id] = SyntheticNode(
                    node_id, source_path, content_hash, line_start, line_end, raw_text
                )
        cases: dict[str, SyntheticCase] = {}
        for raw_case in data.get("cases", []):
            case_id = raw_case.get("id")
            query = raw_case.get("query")
            retrieval = raw_case.get("retrieval")
            node_ids = retrieval.get("expected_node_ids") if isinstance(retrieval, Mapping) else None
            if (not isinstance(case_id, str) or not isinstance(query, str) or
                    not isinstance(node_ids, list) or not all(x in nodes for x in node_ids)):
                raise ValueError("gold corpus case is malformed")
            cases[case_id] = SyntheticCase(case_id, query, tuple(node_ids))
        self._nodes = nodes
        self._cases = cases
        self._cases_by_query = {case.query: case for case in cases.values()}

    @classmethod
    def load_default(cls) -> "SyntheticGoldCorpus":
        root = next((p for p in Path(__file__).resolve().parents if (p / ".github").is_dir()), None)
        if root is None:
            raise RuntimeError("repository root is unavailable for synthetic corpus")
        path = root / CORPUS_RELATIVE_PATH
        return cls(path.read_bytes())

    def case_for_query(self, query: str) -> SyntheticCase | None:
        return self._cases_by_query.get(query)

    def node(self, node_id: str) -> SyntheticNode | None:
        return self._nodes.get(node_id)

    def case_for_node(self, node_id: str) -> SyntheticCase | None:
        return next((case for case in self._cases.values() if node_id in case.node_ids), None)

    def evidence(self, case: SyntheticCase, node_ids: tuple[str, ...] | None = None,
                 *, operation: str = "search_vault") -> dict[str, object]:
        if operation not in {"search_vault", "read_source"}:
            raise ValueError("unsupported synthetic evidence operation")
        selected = case.node_ids if node_ids is None else node_ids
        if not selected or len(selected) > 8:
            raise ValueError("synthetic response evidence must contain 1..8 nodes")
        items = []
        for node_id in selected:
            node = self._nodes.get(node_id)
            if node is None:
                raise ValueError("synthetic response references an unknown node")
            if len(node.raw_text.encode("utf-8")) > 1200:
                raise ValueError("synthetic excerpt exceeds response bound")
            items.append({
                "node_id": node.node_id,
                "source_path": node.source_path,
                "content_hash": node.content_hash,
                "line_start": node.line_start,
                "line_end": node.line_end,
                "excerpt": node.raw_text,
            })
        return {
            "schema_version": "sfra.web.synthetic-evidence.v1",
            "corpus_id": CORPUS_ID,
            "corpus_version": CORPUS_VERSION,
            "corpus_sha256": CORPUS_SHA256,
            "case_id": case.case_id,
            "operation": operation,
            "evidence": items,
        }
