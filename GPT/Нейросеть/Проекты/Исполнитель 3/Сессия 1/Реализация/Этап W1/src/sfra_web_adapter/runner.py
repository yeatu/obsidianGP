"""GitHub Actions entrypoint with synthetic-only application ports."""
from __future__ import annotations
import json
import os
from pathlib import Path
from types import SimpleNamespace

from sfra_context_builder.models import SnapshotRef
from sfra_context_integrations import ContextIntegrationResult, ReadSourceRequest, ReadSourceResult, SourceFragment
from sfra_issue_core import IssueWorkerCore
from .corpus import SyntheticCase, SyntheticGoldCorpus
from .github_api import GitHubREST
from .handler import handle_opened_event
from .ports import GitHubCommentStatusStore, GitHubIssueReader

SNAPSHOT = SnapshotRef(
    vault_commit_sha="1" * 40,
    sidecar_commit_sha="2" * 40,
    manifest_sha256="sha256:" + "3" * 64,
)
CANONICAL_QUERY = "обычный лимит шлюза и исключение для учений"

class SyntheticSearchApplication:
    """V2.1-shaped search port restricted to exact cases in gold corpus v1.0.0."""
    def __init__(self, corpus: SyntheticGoldCorpus | None = None):
        self.corpus = corpus or SyntheticGoldCorpus.load_default()
        self.last_projection = None

    def search(self, request):
        case = self.corpus.case_for_query(request.query)
        nodes = tuple(self.corpus.node(node_id) for node_id in case.node_ids) if case else ()
        nodes = tuple(node for node in nodes if node is not None)
        self.last_projection = self.corpus.evidence(case) if case is not None and nodes else None
        included = [{"node_id": node.node_id, "raw_text": node.raw_text} for node in nodes]
        candidates = tuple(SimpleNamespace(
            node_id=node.node_id,
            source_path=node.source_path,
            content_hash=node.content_hash,
        ) for node in nodes)
        pack = {
            "Status": "complete" if nodes else "not_found",
            "Included": included,
            "Deferred": [],
            "Coverage": {"covered": len(nodes), "uncovered": 0},
            "Diagnostics": [],
        }
        return ContextIntegrationResult(
            snapshot=SNAPSHOT,
            search=SimpleNamespace(
                batch=SimpleNamespace(inspected_count=len(candidates), candidates=candidates),
                diagnostics=(),
            ),
            context_pack=pack,
            source_reads=(),
        )

class SyntheticReadSourceApplication:
    """Mock-only source port backed by the same pinned gold corpus."""
    def __init__(self, corpus: SyntheticGoldCorpus | None = None):
        self.corpus = corpus or SyntheticGoldCorpus.load_default()
        self.last_projection = None

    def read(self, request: ReadSourceRequest):
        node = self.corpus.node(request.node_id)
        case = self.corpus.case_for_node(request.node_id)
        if node is None or case is None or request.expected_hash != node.content_hash:
            self.last_projection = None
            return ReadSourceResult(request=request, status="not_found", fragments=())
        fragment = SourceFragment(
            role="target",
            node_id=node.node_id,
            source_path=node.source_path,
            content_hash=node.content_hash,
            raw_text=node.raw_text,
            index_generation=1,
        )
        self.last_projection = self.corpus.evidence(case, (node.node_id,))
        return ReadSourceResult(request=request, status="ok", fragments=(fragment,))

def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    action = os.environ.get("GITHUB_EVENT_ACTION", "")
    worker_sha = os.environ.get("GITHUB_SHA", "")
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not event_path or not Path(event_path).is_file():
        raise RuntimeError("GitHub event payload is unavailable")
    with open(event_path, "r", encoding="utf-8") as stream:
        payload = json.load(stream)
    corpus = SyntheticGoldCorpus.load_default()
    client = GitHubREST(token=token, repository=repository)
    store = GitHubCommentStatusStore(client)
    search_application = SyntheticSearchApplication(corpus)
    read_source_application = SyntheticReadSourceApplication(corpus)
    worker = IssueWorkerCore(
        issue_reader=GitHubIssueReader(client),
        status_store=store,
        search_application=search_application,
        read_source_application=read_source_application,
    )

    def response_projection(operation: str):
        if operation == "search_vault":
            return search_application.last_projection
        if operation == "read_source":
            return read_source_application.last_projection
        return None

    outcome = handle_opened_event(
        payload,
        event_name=event_name,
        action=action,
        comments=client,
        worker=worker,
        snapshot=SNAPSHOT,
        worker_commit_sha=worker_sha,
        response_projection=response_projection,
    )
    # Aggregate-only output. Synthetic excerpts are emitted only in the intended Issue response comment.
    print("SFRA_W1_OUTCOME=" + outcome)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
