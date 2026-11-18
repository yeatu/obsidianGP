"""Strict wire-contract parsing for the stateless read_source request.

This module only maps caller input to the existing application request type.
It does not construct a ReadSourceService, access E1, read source files, or
register/enable an MCP handler. Runtime integration remains gated by #36/#51.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from sfra_context_builder.models import SnapshotRef
from sfra_context_integrations import ApplicationServiceError, ReadSourceRequest

_SHA40: Final = re.compile(r"^[0-9a-f]{40}$")
_SHA256: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXPECTED_HASH: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_SCOPES: Final = frozenset({"node", "parent", "neighbors", "document"})
_TOP_LEVEL_FIELDS: Final = frozenset({
    "node_id", "expected_hash", "scope", "snapshot", "budget_tokens",
})
_SNAPSHOT_FIELDS: Final = frozenset({
    "vault_commit_sha", "sidecar_commit_sha", "manifest_sha256", "snapshot_id",
})


def _invalid(code: str, message: str) -> ApplicationServiceError:
    """Create a stable, non-reflective validation error."""
    return ApplicationServiceError(code, message)


def parse_read_source_request(value: Mapping[str, object]) -> ReadSourceRequest:
    """Validate the accepted #37 wire shape and build the existing typed request.

    The optional snapshot_id is only an assertion. Identity always comes from
    the three SHA fields and the canonical value is recomputed locally.
    """
    if not isinstance(value, Mapping):
        raise _invalid("invalid_read_request", "read_source request must be an object")
    if any(not isinstance(key, str) for key in value):
        raise _invalid("invalid_read_request", "read_source request has invalid field names")
    if set(value) - _TOP_LEVEL_FIELDS:
        raise _invalid("invalid_read_request", "read_source request has unsupported fields")

    required = {"node_id", "expected_hash", "scope", "snapshot"}
    if not required.issubset(value):
        raise _invalid("invalid_read_request", "read_source request is missing required fields")

    node_id = value["node_id"]
    if not isinstance(node_id, str) or not node_id.strip():
        raise _invalid("invalid_node_id", "node_id must be a non-empty string")

    expected_hash = value["expected_hash"]
    if not isinstance(expected_hash, str) or not _EXPECTED_HASH.fullmatch(expected_hash):
        raise _invalid(
            "invalid_content_hash",
            "expected_hash must be lowercase sha256:<64 hex>",
        )

    scope = value["scope"]
    if not isinstance(scope, str) or scope not in _SCOPES:
        raise _invalid("unsupported_scope", "scope must be node, parent, neighbors, or document")

    budget_tokens = value.get("budget_tokens")
    if budget_tokens is not None and (
        isinstance(budget_tokens, bool)
        or not isinstance(budget_tokens, int)
        or budget_tokens < 1
    ):
        raise _invalid("invalid_budget", "budget_tokens must be a positive integer or null")

    snapshot_value = value["snapshot"]
    if not isinstance(snapshot_value, Mapping):
        raise _invalid("invalid_snapshot", "snapshot must be an object")
    if any(not isinstance(key, str) for key in snapshot_value):
        raise _invalid("invalid_snapshot", "snapshot has invalid field names")
    if set(snapshot_value) - _SNAPSHOT_FIELDS:
        raise _invalid("invalid_snapshot", "snapshot has unsupported fields")

    identity_fields = {
        "vault_commit_sha", "sidecar_commit_sha", "manifest_sha256",
    }
    if not identity_fields.issubset(snapshot_value):
        raise _invalid("invalid_snapshot", "snapshot identity is incomplete")

    vault_sha = snapshot_value["vault_commit_sha"]
    sidecar_sha = snapshot_value["sidecar_commit_sha"]
    manifest_sha = snapshot_value["manifest_sha256"]
    if not isinstance(vault_sha, str) or not _SHA40.fullmatch(vault_sha):
        raise _invalid("invalid_snapshot", "vault_commit_sha must be 40 lowercase hex characters")
    if not isinstance(sidecar_sha, str) or not _SHA40.fullmatch(sidecar_sha):
        raise _invalid("invalid_snapshot", "sidecar_commit_sha must be 40 lowercase hex characters")
    if not isinstance(manifest_sha, str) or not _SHA256.fullmatch(manifest_sha):
        raise _invalid("invalid_snapshot", "manifest_sha256 must be lowercase sha256:<64 hex>")

    snapshot = SnapshotRef(
        vault_commit_sha=vault_sha,
        sidecar_commit_sha=sidecar_sha,
        manifest_sha256=manifest_sha,
    )
    if "snapshot_id" in snapshot_value:
        supplied_snapshot_id = snapshot_value["snapshot_id"]
        if (
            not isinstance(supplied_snapshot_id, str)
            or supplied_snapshot_id != snapshot.snapshot_id
        ):
            raise _invalid(
                "snapshot_mismatch",
                "snapshot_id does not match the supplied snapshot identity",
            )

    return ReadSourceRequest(
        node_id=node_id,
        expected_hash=expected_hash,
        scope=scope,
        snapshot=snapshot,
        budget_tokens=budget_tokens,
    )


__all__ = ["parse_read_source_request"]
