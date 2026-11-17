from __future__ import annotations

from types import SimpleNamespace
from typing import Mapping, Sequence

import pytest

from sfra_context_builder.models import (
    SearchBatch,
    SearchRequest,
    SnapshotRef,
)
from sfra_context_integrations import (
    ApplicationServiceContractError,
    ApplicationServiceError,
    ContextIntegrationResult,
    ReadSourceRequest,
    ReadSourceResult,
    ReadSourceService,
    SearchAdapterResult,
    SearchVaultService,
    SourceReadRequest,
)


SNAPSHOT = SnapshotRef(
    vault_commit_sha="a" * 40,
    sidecar_commit_sha="b" * 40,
    manifest_sha256="sha256:" + "c" * 64,
)
OTHER_SNAPSHOT = SnapshotRef(
    vault_commit_sha="d" * 40,
    sidecar_commit_sha="e" * 40,
    manifest_sha256="sha256:" + "f" * 64,
)
NODE_ID = "node_123"
NODE_HASH = "sha256:" + "1" * 64
DOCUMENT_HASH = "sha256:" + "2" * 64


def make_context_result() -> ContextIntegrationResult:
    search = SearchAdapterResult(
        batch=SearchBatch(complete=False, inspected_count=2, candidates=()),
        diagnostics=({"code": "retrieval_partial", "severity": "warning"},),
        engine_status="ok",
        engine_result_count=2,
    )
    pack = {
        "Status": "budget_limited",
        "Diagnostics": [{"code": "budget_limited"}],
        "Coverage": {"covered": 1, "uncovered": 2},
        "Included": [{"node_id": NODE_ID}],
        "Deferred": [{"node_id": "node_deferred"}],
        "TokenAccounting": {"tokens_used": 900, "budget_tokens": 1000},
    }
    return ContextIntegrationResult(
        snapshot=SNAPSHOT,
        search=search,
        context_pack=pack,
        source_reads=({"status": "ok", "snapshot_id": SNAPSHOT.snapshot_id},),
    )


class FakePipeline:
    def __init__(self, result: ContextIntegrationResult) -> None:
        self.result = result
        self.calls: list[tuple[SearchRequest, tuple[SourceReadRequest, ...]]] = []

    def run(
        self,
        request: SearchRequest,
        *,
        source_reads: Sequence[SourceReadRequest] = (),
    ) -> ContextIntegrationResult:
        self.calls.append((request, tuple(source_reads)))
        return self.result


class FakeSourceReader:
    def __init__(self, response: Mapping[str, object]) -> None:
        self.pinned_snapshot = SimpleNamespace(ref=SNAPSHOT)
        self.response = response
        self.calls: list[tuple[object, ...]] = []

    def read_scope(
        self,
        node_id: str,
        expected_hash: str,
        scope: str,
        snapshot: SnapshotRef,
        *,
        budget_tokens: int | None = None,
    ) -> Mapping[str, object]:
        self.calls.append((node_id, expected_hash, scope, snapshot, budget_tokens))
        return self.response


def search_request() -> SearchRequest:
    return SearchRequest(
        query="проверка контракта",
        task="test application service",
        budget_tokens=1000,
    )


def source_read_request(
    scope: str = "node",
    snapshot: SnapshotRef = SNAPSHOT,
    budget_tokens: int | None = 120,
) -> ReadSourceRequest:
    return ReadSourceRequest(
        node_id=NODE_ID,
        expected_hash=NODE_HASH,
        scope=scope,  # type: ignore[arg-type]
        snapshot=snapshot,
        budget_tokens=budget_tokens,
    )


def fragment(role: str = "target") -> dict[str, object]:
    return {
        "role": role,
        "node_id": NODE_ID,
        "source_path": "characters/hero.md",
        "content_hash": NODE_HASH,
        "document_hash": DOCUMENT_HASH,
        "index_generation": 7,
        "raw_text": "verified original text\n",
        "line_start": 4,
        "line_end": 5,
        "metadata": {"custom": "preserved"},
    }


def source_response(
    *,
    status: str = "ok",
    role: str = "target",
    fragments: list[dict[str, object]] | None = None,
    snapshot_id: str | None = None,
    scope: str = "node",
) -> dict[str, object]:
    return {
        "status": status,
        "snapshot_id": snapshot_id or SNAPSHOT.snapshot_id,
        "scope": scope,
        "fragments": [fragment(role)] if fragments is None and status == "ok" else (fragments or []),
        "diagnostics": [{
            "code": "source_checked",
            "severity": "info",
            "message": "Source provenance was checked by E3.",
            "node_ids": [NODE_ID],
            "details": {"snapshot": SNAPSHOT.snapshot_id},
        }],
        "token_accounting": {
            "budget_owner": "E3",
            "tokens_used": 4,
            "budget_tokens": 120,
            "tokenizer": {"encoding": "test"},
        },
    }


def test_search_vault_service_forwards_typed_request_and_returns_original_result() -> None:
    request = search_request()
    source_reads = (
        SourceReadRequest(
            node_id=NODE_ID,
            expected_hash=NODE_HASH,
            scope="node",
            budget_tokens=100,
        ),
    )
    expected = make_context_result()
    pipeline = FakePipeline(expected)

    result = SearchVaultService(pipeline).search(request, source_reads=source_reads)

    assert result is expected
    assert pipeline.calls == [(request, source_reads)]
    assert result.snapshot == SNAPSHOT
    assert result.search.diagnostics[0]["code"] == "retrieval_partial"
    assert result.context_pack["Status"] == "budget_limited"
    assert result.context_pack["Coverage"] == {"covered": 1, "uncovered": 2}
    assert result.context_pack["Included"] == [{"node_id": NODE_ID}]
    assert result.context_pack["Deferred"] == [{"node_id": "node_deferred"}]


def test_search_vault_service_rejects_untyped_input_before_calling_pipeline() -> None:
    pipeline = FakePipeline(make_context_result())
    service = SearchVaultService(pipeline)

    with pytest.raises(ApplicationServiceError) as bad_request:
        service.search({"query": "not a SearchRequest"})  # type: ignore[arg-type]
    assert bad_request.value.code == "invalid_search_request"

    with pytest.raises(ApplicationServiceError) as bad_reads:
        service.search(search_request(), source_reads=({"node_id": NODE_ID},))  # type: ignore[arg-type]
    assert bad_reads.value.code == "invalid_source_read"
    assert pipeline.calls == []


@pytest.mark.parametrize(
    ("scope", "role"),
    [
        ("node", "target"),
        ("parent", "parent_context"),
        ("neighbors", "next_neighbor"),
        ("document", "document"),
    ],
)
def test_read_source_service_returns_typed_result_for_all_scopes(
    scope: str,
    role: str,
) -> None:
    reader = FakeSourceReader(source_response(role=role, scope=scope))
    service = ReadSourceService(reader)
    request = source_read_request(scope=scope)

    result = service.read(request)

    assert isinstance(result, ReadSourceResult)
    assert result.status == "ok"
    assert result.request is request
    assert result.snapshot == SNAPSHOT
    assert result.snapshot_id == SNAPSHOT.snapshot_id
    assert len(result.fragments) == 1
    assert result.fragments[0].role == role
    assert result.fragments[0].raw_text == "verified original text\n"
    assert result.fragments[0].attributes["metadata"] == {"custom": "preserved"}
    assert result.diagnostics[0].code == "source_checked"
    assert result.token_accounting is not None
    assert result.token_accounting.budget_owner == "E3"
    assert result.token_accounting.tokens_used == 4
    assert reader.calls == [(NODE_ID, NODE_HASH, scope, SNAPSHOT, 120)]


@pytest.mark.parametrize(
    ("status", "error_code"),
    [
        ("stale_source", "stale_source"),
        ("ambiguous", "ambiguous"),
        ("deleted", "deleted"),
        ("not_found", "not_found"),
        ("integrity_error", "integrity_error"),
        ("budget_exceeded", "budget_exceeded"),
    ],
)
def test_read_source_service_preserves_fail_closed_business_statuses(
    status: str,
    error_code: str,
) -> None:
    response = source_response(status=status)
    response["error"] = {"code": error_code, "message": "The source was not returned."}
    reader = FakeSourceReader(response)
    result = ReadSourceService(reader).read(source_read_request())

    assert result.status == status
    assert result.fragments == ()
    assert result.error is not None
    assert result.error.code == error_code
    assert result.diagnostics[0].code == "source_checked"


def test_read_source_service_rejects_partial_fragments_on_non_ok_status() -> None:
    response = source_response(status="stale_source", fragments=[fragment()])
    reader = FakeSourceReader(response)

    with pytest.raises(ApplicationServiceContractError) as error:
        ReadSourceService(reader).read(source_read_request())

    assert error.value.code == "partial_error_payload"


def test_read_source_service_fails_before_call_when_snapshot_is_not_pinned() -> None:
    reader = FakeSourceReader(source_response())
    service = ReadSourceService(reader)

    with pytest.raises(ApplicationServiceError) as error:
        service.read(source_read_request(snapshot=OTHER_SNAPSHOT))

    assert error.value.code == "snapshot_mismatch"
    assert reader.calls == []


def test_read_source_service_rejects_snapshot_echo_mismatch() -> None:
    reader = FakeSourceReader(source_response(snapshot_id=OTHER_SNAPSHOT.snapshot_id))

    with pytest.raises(ApplicationServiceContractError) as error:
        ReadSourceService(reader).read(source_read_request())

    assert error.value.code == "snapshot_mismatch"


def test_read_source_service_rejects_untyped_or_invalid_fragment_data() -> None:
    reader = FakeSourceReader(source_response(fragments=[{"role": "target"}]))

    with pytest.raises(ApplicationServiceContractError) as error:
        ReadSourceService(reader).read(source_read_request())

    assert error.value.code == "invalid_fragment_node_id"


def test_read_source_service_rejects_budget_accounting_not_owned_by_e3() -> None:
    response = source_response()
    response["token_accounting"] = {
        "budget_owner": "E1",
        "tokens_used": 4,
        "budget_tokens": 120,
        "tokenizer": {},
    }
    reader = FakeSourceReader(response)

    with pytest.raises(ApplicationServiceContractError) as error:
        ReadSourceService(reader).read(source_read_request())

    assert error.value.code == "invalid_budget_owner"


def test_read_source_request_validates_scope_hash_snapshot_and_budget() -> None:
    with pytest.raises(ApplicationServiceError) as bad_scope:
        ReadSourceRequest(
            node_id=NODE_ID,
            expected_hash=NODE_HASH,
            scope="whole_vault",  # type: ignore[arg-type]
            snapshot=SNAPSHOT,
        )
    assert bad_scope.value.code == "unsupported_scope"

    with pytest.raises(ApplicationServiceError) as bad_hash:
        ReadSourceRequest(
            node_id=NODE_ID,
            expected_hash="sha256:bad",
            scope="node",
            snapshot=SNAPSHOT,
        )
    assert bad_hash.value.code == "invalid_content_hash"

    with pytest.raises(ApplicationServiceError) as bad_budget:
        ReadSourceRequest(
            node_id=NODE_ID,
            expected_hash=NODE_HASH,
            scope="node",
            snapshot=SNAPSHOT,
            budget_tokens=True,  # type: ignore[arg-type]
        )
    assert bad_budget.value.code == "invalid_budget"


def test_read_source_service_echoes_snapshot_id_on_fail_closed_errors() -> None:
    response = source_response(status="deleted")
    response["error"] = {
        "code": "deleted",
        "message": "The source was not returned.",
    }
    reader = FakeSourceReader(response)

    result = ReadSourceService(reader).read(source_read_request())

    assert result.status == "deleted"
    assert result.snapshot_id == SNAPSHOT.snapshot_id
    assert result.snapshot == SNAPSHOT
    assert result.fragments == ()
    assert result.error is not None
    assert result.error.code == "deleted"
