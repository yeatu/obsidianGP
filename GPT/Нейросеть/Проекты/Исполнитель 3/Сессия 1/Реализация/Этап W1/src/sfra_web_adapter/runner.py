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

class SyntheticSearchApplication:
    """Injected V2.1-shaped port backed only by fixed disposable test data."""
    def search(self, request):
        pack = {
            "Status": "complete",
            "Included": [{"node_id": "synthetic-node-001", "raw_text": "Synthetic fixture excerpt only."}],
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
    def read(self, request: ReadSourceRequest):
        fragment = SourceFragment(
            role="target",
            node_id="synthetic-node-001",
            source_path="synthetic://fixture/source.md",
            content_hash=request.expected_hash,
            raw_text="Synthetic fixture source text only.",
            index_generation=1,
        )
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
    worker = IssueWorkerCore(
        issue_reader=GitHubIssueReader(client),
        status_store=store,
        search_application=SyntheticSearchApplication(),
        read_source_application=SyntheticReadSourceApplication(),
    )
    outcome = handle_opened_event(
        payload,
        event_name=event_name,
        action=action,
        comments=client,
        worker=worker,
        snapshot=SNAPSHOT,
        worker_commit_sha=worker_sha,
    )
    # Aggregate-only output. Never print request payloads, hashes, or results.
    print("SFRA_W1_OUTCOME=" + outcome)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
