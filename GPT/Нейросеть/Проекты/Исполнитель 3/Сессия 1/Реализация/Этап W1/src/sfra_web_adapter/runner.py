"""GitHub Actions entrypoint with synthetic-only application ports."""
from __future__ import annotations
import json
import os
from pathlib import Path
from types import SimpleNamespace

from sfra_context_builder.models import SnapshotRef
from sfra_context_integrations import ContextIntegrationResult, ReadSourceRequest, ReadSourceResult, SourceFragment
from sfra_issue_core import IssueWorkerCore
from .github_api import GitHubREST
from .handler import handle_opened_event
from .ports import GitHubCommentStatusStore, GitHubIssueReader

SNAPSHOT = SnapshotRef(
    vault_commit_sha="1" * 40,
    sidecar_commit_sha="2" * 40,
    manifest_sha256="sha256:" + "3" * 64,
)
GOLD_NODE = {
    "node_id": "manual_intro",
    "source_path": "synthetic/operations/manual.md",
    "content_hash": "sha256:04b8c940ba7056617a1fc4d4e45eff787033888862cd291eb9770f3fe6ea0f77",
    "line_start": 1,
    "line_end": 2,
    "raw_text": "Операционный справочник станции «Люмен».\nРуководство относится к тестовому объекту Л-7.\n",
}

class SyntheticSearchApplication:
    """Injected V2.1-shaped port backed by one accepted synthetic gold-corpus node."""
    def __init__(self):
        self.last_projection = None

    def search(self, request):
        self.last_projection = {
            "schema_version": 1,
            "operation": "search_vault",
            "items": [{
                "node_id": GOLD_NODE["node_id"],
                "source_path": GOLD_NODE["source_path"],
                "content_hash": GOLD_NODE["content_hash"],
                "line_start": GOLD_NODE["line_start"],
                "line_end": GOLD_NODE["line_end"],
                "excerpt": GOLD_NODE["raw_text"],
            }],
        }
        pack = {
            "Status": "complete",
            "Included": [{"node_id": GOLD_NODE["node_id"], "raw_text": GOLD_NODE["raw_text"]}],
            "Deferred": [],
            "Coverage": {"covered": 1, "uncovered": 0},
            "Diagnostics": [],
        }
        return ContextIntegrationResult(
            snapshot=SNAPSHOT,
            search=SimpleNamespace(
                batch=SimpleNamespace(inspected_count=1, candidates=(object(),)),
                diagnostics=(),
            ),
            context_pack=pack,
            source_reads=(),
        )

class SyntheticReadSourceApplication:
    """Mock-only source port; never opens a path, database or Vault."""
    def __init__(self):
        self.last_projection = None

    def read(self, request: ReadSourceRequest):
        if request.node_id != GOLD_NODE["node_id"] or request.expected_hash != GOLD_NODE["content_hash"]:
            self.last_projection = None
            return ReadSourceResult(request=request, status="not_found", fragments=())
        fragment = SourceFragment(
            role="target",
            node_id=GOLD_NODE["node_id"],
            source_path=GOLD_NODE["source_path"],
            content_hash=GOLD_NODE["content_hash"],
            raw_text=GOLD_NODE["raw_text"],
            index_generation=1,
        )
        self.last_projection = {
            "schema_version": 1,
            "operation": "read_source",
            "items": [{
                "node_id": fragment.node_id,
                "source_path": fragment.source_path,
                "content_hash": fragment.content_hash,
                "line_start": GOLD_NODE["line_start"],
                "line_end": GOLD_NODE["line_end"],
                "excerpt": fragment.raw_text,
            }],
        }
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
    client = GitHubREST(token=token, repository=repository)
    store = GitHubCommentStatusStore(client)
    search_application = SyntheticSearchApplication()
    read_source_application = SyntheticReadSourceApplication()
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
