from __future__ import annotations

import pytest

from sfra_issue_core import (
    InMemoryTransportStatusStore,
    TransportStatusV2,
    validate_transport_status_v2,
)
from conftest import REQUEST_ID, WORKER_SHA


def rejected_status() -> TransportStatusV2:
    return TransportStatusV2(
        status_schema_version=2,
        issue_number=15,
        request_id=None,
        operation=None,
        transport_status="REJECTED",
        request_body_sha256="sha256:" + "a" * 64,
        worker_commit_sha=WORKER_SHA,
        error_code="invalid_json",
    )


def test_status_v2_has_required_typed_fields_and_separates_business_status() -> None:
    completed = TransportStatusV2(
        status_schema_version=2,
        issue_number=15,
        request_id=REQUEST_ID,
        operation="search_vault",
        transport_status="COMPLETED",
        request_body_sha256="sha256:" + "b" * 64,
        worker_commit_sha=WORKER_SHA,
        result={
            "operation": "search_vault",
            "business_status": "budget_limited",
            "scope": None,
            "counts": {"included": 1, "deferred": 2},
            "diagnostic_codes": ["budget_limited"],
        },
    )
    data = completed.to_mapping()

    assert data["status_schema_version"] == 2
    assert data["transport_status"] == "COMPLETED"
    assert data["result"]["business_status"] == "budget_limited"
    assert validate_transport_status_v2(data)["request_body_sha256"] == data["request_body_sha256"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.pop("worker_commit_sha"),
        lambda data: data.update({"unexpected": "field"}),
        lambda data: data.update({"status_schema_version": True}),
        lambda data: data.update({"status_schema_version": 2.0}),
        lambda data: data.update({"issue_number": True}),
        lambda data: data.update({"request_body_sha256": "sha256:BAD"}),
        lambda data: data.update({"worker_commit_sha": "not-a-git-sha"}),
        lambda data: data.update({"transport_status": "budget_limited"}),
        lambda data: data.update({"error_code": "raw source text"}),
    ],
)
def test_status_v2_rejects_missing_extra_and_invalid_fields(mutation) -> None:
    data = rejected_status().to_mapping()
    mutation(data)
    with pytest.raises(ValueError):
        validate_transport_status_v2(data)


def test_status_v2_rejects_source_material_in_safe_result() -> None:
    data = {
        "status_schema_version": 2,
        "issue_number": 15,
        "request_id": REQUEST_ID,
        "operation": "read_source",
        "transport_status": "COMPLETED",
        "request_body_sha256": "sha256:" + "b" * 64,
        "worker_commit_sha": WORKER_SHA,
        "error_code": None,
        "result": {
            "operation": "read_source",
            "business_status": "ok",
            "scope": "document",
            "counts": {"fragments": 1},
            "diagnostic_codes": [],
            "raw_text": "DO_NOT_PUBLISH",
        },
    }
    with pytest.raises(ValueError):
        validate_transport_status_v2(data)


def test_in_memory_status_store_keeps_first_body_hash_immutable() -> None:
    store = InMemoryTransportStatusStore()
    first = "sha256:" + "1" * 64
    changed = "sha256:" + "2" * 64

    assert store.bind_request_body_sha256(15, first) == first
    assert store.bind_request_body_sha256(15, changed) == first
    assert store.get_bound_body_sha256(15) == first

    status = rejected_status()
    store.put_status(status)
    assert store.get_status(15) is status
