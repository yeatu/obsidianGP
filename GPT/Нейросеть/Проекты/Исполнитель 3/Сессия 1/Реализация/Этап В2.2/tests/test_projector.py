from __future__ import annotations

import json
from types import SimpleNamespace

from sfra_context_builder.models import SnapshotRef
from sfra_context_integrations import (
    ContextIntegrationResult,
    ReadSourceRequest,
    ReadSourceResult,
    ServiceDiagnostic,
    SourceFragment,
)
from sfra_issue_core import SafeResultProjector

SNAPSHOT = SnapshotRef(
    vault_commit_sha="a" * 40,
    sidecar_commit_sha="b" * 40,
    manifest_sha256="sha256:" + "c" * 64,
)
SECRET_TEXT = "SENTINEL_RAW_SOURCE_TEXT"
SECRET_PATH = "SENTINEL_SOURCE_PATH"
SECRET_TITLE = "SENTINEL_DOCUMENT_TITLE"
SECRET_HASH = "sha256:" + "e" * 64


def test_search_projection_keeps_only_allowlisted_status_counts_and_codes() -> None:
    result = ContextIntegrationResult(
        snapshot=SNAPSHOT,
        search=SimpleNamespace(
            batch=SimpleNamespace(
                inspected_count=7,
                candidates=(SimpleNamespace(raw_text=SECRET_TEXT, source_path=SECRET_PATH),),
            ),
            diagnostics=({"code": "retrieval_partial", "message": SECRET_TEXT},),
        ),
        context_pack={
            "Status": "budget_limited",
            "Included": [{"node_id": "secret-id", "title": SECRET_TITLE, "raw_text": SECRET_TEXT}],
            "Deferred": [{"source_path": SECRET_PATH}],
            "Coverage": {"covered": 1, "uncovered": 2},
            "Diagnostics": [{"code": "budget_limited", "message": SECRET_TEXT, "details": {"path": SECRET_PATH}}],
            "RawText": SECRET_TEXT,
            "Title": SECRET_TITLE,
        },
        source_reads=({"raw_text": SECRET_TEXT, "source_path": SECRET_PATH},),
    )

    projected = SafeResultProjector().project("search_vault", result)
    serialized = json.dumps(projected.to_mapping(), sort_keys=True)

    assert projected.business_status == "budget_limited"
    assert projected.counts == {
        "inspected": 7,
        "candidates": 1,
        "included": 1,
        "deferred": 1,
        "source_reads": 1,
        "covered": 1,
        "uncovered": 2,
    }
    for secret in (SECRET_TEXT, SECRET_PATH, SECRET_TITLE, SECRET_HASH, "secret-id"):
        assert secret not in serialized
    assert projected.diagnostic_codes == ("budget_limited", "retrieval_partial")


def test_read_source_projection_never_serializes_fragment_or_diagnostic_details() -> None:
    request = ReadSourceRequest(
        node_id="node_private",
        expected_hash=SECRET_HASH,
        scope="document",
        snapshot=SNAPSHOT,
    )
    fragment = SourceFragment(
        role="document",
        node_id="node_private",
        source_path=SECRET_PATH,
        content_hash=SECRET_HASH,
        raw_text=SECRET_TEXT,
        index_generation=9,
        document_hash=SECRET_HASH,
        attributes={"title": SECRET_TITLE, "raw_text": SECRET_TEXT},
    )
    result = ReadSourceResult(
        request=request,
        status="ok",
        fragments=(fragment,),
        diagnostics=(
            ServiceDiagnostic(
                code="source_checked",
                severity="info",
                message=SECRET_TEXT,
                node_ids=("node_private",),
                details={"path": SECRET_PATH, "title": SECRET_TITLE},
            ),
            ServiceDiagnostic(
                code="arbitrary-untrusted-code",
                severity="info",
                message=SECRET_TEXT,
            ),
        ),
    )

    projected = SafeResultProjector().project("read_source", result)
    serialized = json.dumps(projected.to_mapping(), sort_keys=True)

    assert projected.business_status == "ok"
    assert projected.scope == "document"
    assert projected.counts == {"fragments": 1}
    assert projected.diagnostic_codes == ("source_checked",)
    for secret in (SECRET_TEXT, SECRET_PATH, SECRET_TITLE, SECRET_HASH, "node_private"):
        assert secret not in serialized


def test_unknown_business_status_and_diagnostic_values_fail_closed_to_safe_defaults() -> None:
    result = ContextIntegrationResult(
        snapshot=SNAPSHOT,
        search=SimpleNamespace(
            batch=SimpleNamespace(inspected_count=0, candidates=()),
            diagnostics=({"code": SECRET_TEXT, "message": SECRET_TEXT},),
        ),
        context_pack={"Status": SECRET_TITLE, "Included": [], "Deferred": [], "Diagnostics": []},
        source_reads=(),
    )

    projected = SafeResultProjector().project("search_vault", result)

    assert projected.business_status == "unknown"
    assert projected.diagnostic_codes == ()
    assert SECRET_TEXT not in json.dumps(projected.to_mapping())
    assert SECRET_TITLE not in json.dumps(projected.to_mapping())
