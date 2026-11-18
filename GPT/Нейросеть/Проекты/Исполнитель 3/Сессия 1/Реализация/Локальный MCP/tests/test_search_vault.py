from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from sfra_context_builder.models import SearchBatch, SnapshotRef
from sfra_context_integrations.application import ApplicationServiceError
from sfra_context_integrations.pipeline import ContextIntegrationResult
from sfra_context_integrations.search_adapter import SearchAdapterResult
from sfra_mcp_server.search_vault import SearchVaultTool, SearchVaultToolError


def _snapshot() -> SnapshotRef:
    return SnapshotRef(
        "a" * 40,
        "b" * 40,
        "sha256:" + "c" * 64,
    )


def _pack(
    *,
    status: str = "complete",
    search_complete: bool = True,
    budget_tokens: int = 3000,
) -> dict[str, Any]:
    return {
        "schema_version": "sfra.context_pack.v1",
        "status": status,
        "search_complete": search_complete,
        "Included": [],
        "Coverage": [],
        "Deferred": [],
        "Parallel Sources": [],
        "Known": [],
        "Version Changes": [],
        "Statistics": {
            "retrieved_count": 0,
            "included_count": 0,
            "deferred_count": 0,
            "budget_tokens": budget_tokens,
            "tokens_used": 0,
        },
        "Diagnostics": [],
    }


@dataclass
class FakeSearchService:
    result: ContextIntegrationResult
    calls: list[Any]

    def search(self, request):
        self.calls.append(request)
        return self.result


def _result(
    snapshot: SnapshotRef | None = None,
    *,
    complete: bool = True,
    engine_status: str = "ok",
    diagnostics: tuple[dict[str, Any], ...] = (),
    context_pack: dict[str, Any] | None = None,
    truncated_by_limit: bool = False,
) -> ContextIntegrationResult:
    ref = snapshot or _snapshot()
    search = SearchAdapterResult(
        batch=SearchBatch(
            complete=complete,
            inspected_count=4,
            candidates=(),
            cursor=None,
            truncated_by_limit=truncated_by_limit,
        ),
        diagnostics=diagnostics,
        engine_status=engine_status,
        engine_result_count=4,
    )
    return ContextIntegrationResult(
        snapshot=ref,
        search=search,
        context_pack=context_pack or _pack(),
        source_reads=(),
    )


def _service(result: ContextIntegrationResult | None = None) -> FakeSearchService:
    return FakeSearchService(result or _result(), [])


def test_search_vault_uses_existing_service_and_returns_full_snapshot_and_pack():
    pack = _pack(
        status="budget_limited",
        search_complete=True,
        budget_tokens=1200,
    )
    service = _service(_result(context_pack=pack))
    tool = SearchVaultTool(service, _snapshot())

    response = tool.handle({
        "query": "fixture query",
        "task": "fixture task",
        "entities": ["Entity A"],
        "budget_tokens": 1200,
        "known": [{
            "node_id": "node_fixture",
            "content_hash": "sha256:" + "d" * 64,
        }],
        "focus": [{
            "id": "focus_1",
            "label": "critical rule",
            "terms": ["must"],
            "match_mode": "all",
        }],
    })

    assert len(service.calls) == 1
    request = service.calls[0]
    assert request.query == "fixture query"
    assert request.task == "fixture task"
    assert request.entities == ("Entity A",)
    assert request.budget_tokens == 1200
    assert request.known[0].node_id == "node_fixture"
    assert request.focus[0].aspect_id == "focus_1"

    assert response["schema_version"] == "sfra.search_vault.v1"
    assert response["snapshot"] == {
        "vault_commit_sha": "a" * 40,
        "sidecar_commit_sha": "b" * 40,
        "manifest_sha256": "sha256:" + "c" * 64,
        "snapshot_id": _snapshot().snapshot_id,
    }
    assert response["context_pack"] is pack
    assert response["context_pack"]["status"] == "budget_limited"
    assert response["context_pack"]["Statistics"]["budget_tokens"] == 1200


def test_search_vault_preserves_incomplete_batch_and_adapter_diagnostics():
    diagnostic = {
        "code": "facet_match_signal_unavailable",
        "severity": "warning",
        "message": "Requested facets were not evaluated by E2",
        "node_ids": [],
        "details": {"evaluation": "not_evaluated"},
    }
    pack = _pack(status="partial", search_complete=False)
    service = _service(_result(
        complete=False,
        diagnostics=(diagnostic,),
        context_pack=pack,
        truncated_by_limit=False,
    ))

    response = SearchVaultTool(service, _snapshot()).handle({
        "query": "synthetic query",
        "facets": ["facet_unavailable"],
        "zones": ["zone-a"],
    })

    assert response["search"]["batch"]["complete"] is False
    assert response["search"]["batch"]["truncated_by_limit"] is False
    assert response["search"]["diagnostics"] == [diagnostic]
    assert response["context_pack"] is pack
    assert response["context_pack"]["search_complete"] is False
    assert response["context_pack"]["status"] == "partial"
    assert service.calls[0].facets == ("facet_unavailable",)
    assert service.calls[0].zones == ("zone-a",)


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"query": "   "},
        {"query": "x", "unknown": True},
        {"query": "x", "budget_tokens": True},
        {"query": "x", "budget_tokens": 0},
        {"query": "x", "entities": None},
        {"query": "x", "entities": ["ok", ""]},
        {"query": "x", "known": [{"node_id": "n"}]},
        {"query": "x", "known": [{"node_id": "n", "content_hash": "sha256:" + "a" * 64, "extra": 1}]},
        {"query": "x", "focus": ["legacy string form"]},
        {"query": "x", "focus": [{"id": "f", "label": "label", "unexpected": "x"}]},
        {"query": "x", "focus": [{"id": "f", "label": "label", "terms": None}]},
    ],
)
def test_invalid_wire_input_fails_before_service_call(arguments):
    service = _service()

    with pytest.raises(SearchVaultToolError) as error:
        SearchVaultTool(service, _snapshot()).handle(arguments)

    assert error.value.code == "invalid_request"
    assert service.calls == []


def test_search_vault_sdk_types_keep_known_and_focus_fields_closed():
    from sfra_mcp_server.search_vault import FocusAspectInput, KnownVersionInput

    assert KnownVersionInput.__required_keys__ == {"node_id", "content_hash"}
    assert KnownVersionInput.__optional_keys__ == set()
    assert FocusAspectInput.__required_keys__ == {"id", "label"}
    assert FocusAspectInput.__optional_keys__ == {
        "entities", "facets", "terms", "match_mode",
    }


def test_build_search_vault_handler_exposes_the_contract_signature():
    from inspect import signature

    from sfra_mcp_server.search_vault import build_search_vault_handler

    service = _service()
    handler = build_search_vault_handler(service, _snapshot())

    assert list(signature(handler).parameters) == [
        "query",
        "task",
        "entities",
        "facets",
        "zones",
        "budget_tokens",
        "known",
        "focus",
    ]
    response = handler("wrapper query", budget_tokens=250)
    assert response["context_pack"] is service.result.context_pack
    assert service.calls[0].query == "wrapper query"
    assert service.calls[0].budget_tokens == 250


def test_search_vault_rejects_result_from_another_snapshot():
    service = _service(_result(SnapshotRef(
        "d" * 40, "e" * 40, "sha256:" + "f" * 64
    )))

    with pytest.raises(SearchVaultToolError) as error:
        SearchVaultTool(service, _snapshot()).handle({"query": "valid query"})

    assert error.value.code == "snapshot_mismatch"
    assert len(service.calls) == 1


def test_application_error_is_mapped_without_exposing_error_details():
    class SecretFailingService:
        def search(self, request):
            raise ApplicationServiceError(
                "pipeline_failed",
                "private /vault/path with source-derived metadata",
                details={"path": "/private/source"},
            )

    with pytest.raises(SearchVaultToolError) as error:
        SearchVaultTool(SecretFailingService(), _snapshot()).handle({
            "query": "valid query",
        })

    assert error.value.code == "pipeline_failed"
    assert "/vault/path" not in str(error.value)
    assert "/private/source" not in str(error.value)


def test_diagnostic_projection_rejects_non_json_values():
    diagnostic = {
        "code": "diagnostic",
        "severity": "warning",
        "message": "safe",
        "details": {"opaque": object()},
    }
    service = _service(_result(diagnostics=(diagnostic,)))

    with pytest.raises(SearchVaultToolError) as error:
        SearchVaultTool(service, _snapshot()).handle({"query": "valid query"})

    assert error.value.code == "search_contract_error"


def test_invalid_service_failure_does_not_echo_arbitrary_exception_message():
    class SecretFailingService:
        def search(self, request):
            raise RuntimeError("source=/private/vault/path/raw-content")

    with pytest.raises(SearchVaultToolError) as error:
        SearchVaultTool(SecretFailingService(), _snapshot()).handle({
            "query": "valid query",
        })

    assert error.value.code == "search_failed"
    assert "/private/vault/path" not in str(error.value)
    assert "raw-content" not in str(error.value)
