from __future__ import annotations

from types import SimpleNamespace

from sfra_context_builder.models import SnapshotRef
from sfra_context_integrations import (
    ContextIntegrationResult,
    ReadSourceResult,
    ServiceDiagnostic,
    SourceFragment,
)
from sfra_issue_core import (
    InMemoryTransportStatusStore,
    IssueRecord,
    IssueWorkerCore,
    TransportStatusV2,
)
from conftest import CONTENT_HASH, WORKER_SHA, body_for, issue_record

SNAPSHOT = SnapshotRef(
    vault_commit_sha="a" * 40,
    sidecar_commit_sha="b" * 40,
    manifest_sha256="sha256:" + "c" * 64,
)


class FakeIssueReader:
    def __init__(self, current: IssueRecord) -> None:
        self.current = current
        self.calls: list[int] = []

    def read_issue(self, issue_number: int) -> IssueRecord:
        self.calls.append(issue_number)
        return self.current


class FakeSearchApplication:
    def __init__(self, snapshot: SnapshotRef = SNAPSHOT) -> None:
        self.snapshot = snapshot
        self.calls = []

    def search(self, request):
        self.calls.append(request)
        return ContextIntegrationResult(
            snapshot=self.snapshot,
            search=SimpleNamespace(
                batch=SimpleNamespace(inspected_count=3, candidates=(object(), object())),
                diagnostics=({"code": "retrieval_partial", "message": "source secret"},),
            ),
            context_pack={
                "Status": "budget_limited",
                "Included": [{"raw_text": "MUST_NOT_ESCAPE"}],
                "Deferred": [{"title": "PRIVATE_TITLE"}],
                "Coverage": {"covered": 1, "uncovered": 1},
                "Diagnostics": [{"code": "budget_limited", "message": "MUST_NOT_ESCAPE"}],
            },
            source_reads=(),
        )


class FakeReadSourceApplication:
    def __init__(self) -> None:
        self.calls = []

    def read(self, request):
        self.calls.append(request)
        return ReadSourceResult(
            request=request,
            status="ok",
            fragments=(
                SourceFragment(
                    role="target",
                    node_id=request.node_id,
                    source_path="PRIVATE_PATH",
                    content_hash=request.expected_hash,
                    raw_text="PRIVATE_RAW_TEXT",
                    index_generation=4,
                ),
            ),
            diagnostics=(
                ServiceDiagnostic(
                    code="source_checked",
                    severity="info",
                    message="PRIVATE_RAW_TEXT",
                    details={"path": "PRIVATE_PATH"},
                ),
            ),
        )


def make_worker(issue: IssueRecord):
    reader = FakeIssueReader(issue)
    store = InMemoryTransportStatusStore()
    search = FakeSearchApplication()
    read_source = FakeReadSourceApplication()
    worker = IssueWorkerCore(
        issue_reader=reader,
        status_store=store,
        search_application=search,
        read_source_application=read_source,
    )
    return worker, reader, store, search, read_source


def test_worker_validates_then_calls_search_service_once_and_stores_safe_status() -> None:
    issue = issue_record(body_for(payload={
        "query": "Find a contract",
        "budget_tokens": 700,
        "known": [{"node_id": "node_x", "content_hash": CONTENT_HASH}],
        "focus": [{"id": "voice", "label": "Voice", "terms": ["style"]}],
    }))
    worker, reader, store, search, read_source = make_worker(issue)

    status = worker.run(15, snapshot=SNAPSHOT, worker_commit_sha=WORKER_SHA)
    mapping = status.to_mapping()

    assert status.transport_status == "COMPLETED"
    assert mapping["status_schema_version"] == 2
    assert mapping["result"]["business_status"] == "budget_limited"
    assert search.calls[0].query == "Find a contract"
    assert search.calls[0].budget_tokens == 700
    assert search.calls[0].known[0].content_hash == CONTENT_HASH
    assert search.calls[0].focus[0].aspect_id == "voice"
    assert read_source.calls == []
    assert reader.calls == [15]
    assert store.get_status(15) is status
    assert "MUST_NOT_ESCAPE" not in str(mapping)
    assert "PRIVATE_TITLE" not in str(mapping)


def test_worker_read_source_uses_the_one_passed_snapshot_and_projects_only_counts() -> None:
    issue = issue_record(body_for("read_source", {
        "node_id": "node_example",
        "expected_hash": CONTENT_HASH,
        "scope": "parent",
        "budget_tokens": 90,
    }))
    worker, _, _, search, read_source = make_worker(issue)

    status = worker.run(15, snapshot=SNAPSHOT, worker_commit_sha=WORKER_SHA)

    assert status.transport_status == "COMPLETED"
    assert read_source.calls[0].snapshot is SNAPSHOT
    assert read_source.calls[0].scope == "parent"
    assert search.calls == []
    assert status.result["scope"] == "parent"
    assert status.result["counts"] == {"fragments": 1}
    assert "PRIVATE_RAW_TEXT" not in str(status.to_mapping())
    assert "PRIVATE_PATH" not in str(status.to_mapping())


def test_rejected_input_never_calls_either_application_service() -> None:
    bad_body = body_for(payload={"query": "must not run", "extra": "reject"})
    worker, _, store, search, read_source = make_worker(issue_record(bad_body))

    status = worker.run(15, snapshot=SNAPSHOT, worker_commit_sha=WORKER_SHA)

    assert status.transport_status == "REJECTED"
    assert status.error_code == "extra_fields"
    assert search.calls == []
    assert read_source.calls == []
    assert store.get_bound_body_sha256(15) == status.request_body_sha256


def test_changed_body_hash_is_permanently_rejected_without_second_service_call() -> None:
    reader = FakeIssueReader(issue_record(body_for(payload={"query": "first"})))
    store = InMemoryTransportStatusStore()
    search = FakeSearchApplication()
    read_source = FakeReadSourceApplication()
    worker = IssueWorkerCore(
        issue_reader=reader,
        status_store=store,
        search_application=search,
        read_source_application=read_source,
    )

    first = worker.run(15, snapshot=SNAPSHOT, worker_commit_sha=WORKER_SHA)
    reader.current = issue_record(body_for(payload={"query": "mutated body"}))
    second = worker.run(15, snapshot=SNAPSHOT, worker_commit_sha=WORKER_SHA)

    assert first.transport_status == "COMPLETED"
    assert second.transport_status == "REJECTED"
    assert second.error_code == "request_body_changed"
    assert len(search.calls) == 1
    assert read_source.calls == []
    assert store.get_bound_body_sha256(15) == first.request_body_sha256


def test_worker_sanitizes_application_exception_without_serializing_its_message() -> None:
    class LeakyFailure:
        def search(self, request):
            raise RuntimeError("PRIVATE_RAW_TEXT and PRIVATE_PATH")

    issue = issue_record(body_for())
    reader = FakeIssueReader(issue)
    store = InMemoryTransportStatusStore()
    worker = IssueWorkerCore(
        issue_reader=reader,
        status_store=store,
        search_application=LeakyFailure(),
        read_source_application=FakeReadSourceApplication(),
    )

    status = worker.run(15, snapshot=SNAPSHOT, worker_commit_sha=WORKER_SHA)

    assert status.transport_status == "FAILED"
    assert status.error_code == "application_service_failed"
    assert "PRIVATE_RAW_TEXT" not in str(status.to_mapping())
    assert "PRIVATE_PATH" not in str(status.to_mapping())
