"""Validate E1 source-scope responses without reading E1's private SQLite schema."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import re
from typing import Any

from sfra_context_builder.models import SnapshotRef

from .source_protocol import E1ScopeAPI


SCOPES = frozenset({"node", "parent", "neighbors", "document"})
ERROR_STATUSES = frozenset({
    "stale", "stale_source", "ambiguous", "deleted", "not_found",
    "invalid_request", "budget_exceeded", "source_unavailable", "integrity_error",
})
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class SourceReaderContractError(ValueError):
    """E1 returned a malformed or cross-snapshot source response."""

    def __init__(self, message: str, *, code: str = "source_reader_contract_error") -> None:
        super().__init__(message)
        self.code = code


def _is_non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceReaderContractError(f"{name} must be a non-empty string")
    return value


class E1SourceReader:
    """E3 SourceReader adapter over the public E1 scope API.

    The adapter validates the E1 envelope, snapshot echo, exact fragment hashes,
    document identity and document-local generation. It never reconstructs
    neighbors, parses Markdown or queries SQLite directly.
    """

    def __init__(self, scope_api: E1ScopeAPI) -> None:
        if not callable(getattr(scope_api, "read_scope", None)):
            raise TypeError("scope_api must implement read_scope")
        self._scope_api = scope_api

    def read_scope(
        self,
        node_id: str,
        expected_hash: str,
        scope: str,
        snapshot: SnapshotRef,
        *,
        budget_tokens: int | None = None,
    ) -> Mapping[str, Any]:
        _required_text(node_id, "node_id")
        if not isinstance(expected_hash, str) or not _HASH_RE.fullmatch(expected_hash):
            raise ValueError("expected_hash must be sha256:<64 lowercase hex>")
        if scope not in SCOPES:
            raise ValueError(f"unsupported source scope: {scope!r}")
        if not isinstance(snapshot, SnapshotRef):
            raise TypeError("snapshot must be a SnapshotRef")
        if budget_tokens is not None and not _is_non_negative_int(budget_tokens):
            raise ValueError("budget_tokens must be a non-negative integer or None")

        try:
            response = self._scope_api.read_scope(
                node_id,
                expected_hash,
                scope,
                budget_tokens,
                snapshot,
            )
        except Exception as exc:
            raise SourceReaderContractError(
                f"E1 read_scope failed ({type(exc).__name__})",
                code="e1_read_scope_failed",
            ) from exc

        if not isinstance(response, Mapping):
            raise SourceReaderContractError("E1 response must be an object")
        status = response.get("status")
        if not isinstance(status, str):
            raise SourceReaderContractError("E1 response.status must be a string")
        if response.get("snapshot_id") != snapshot.snapshot_id:
            raise SourceReaderContractError(
                "E1 response snapshot_id does not match the pinned SnapshotRef",
                code="snapshot_mismatch",
            )

        fragments = response.get("fragments", [])
        if not isinstance(fragments, list):
            raise SourceReaderContractError("E1 response.fragments must be an array")

        if status != "ok":
            if status not in ERROR_STATUSES:
                raise SourceReaderContractError(f"unsupported E1 source status: {status!r}")
            if fragments:
                raise SourceReaderContractError(
                    "E1 error response must not contain partial source fragments",
                    code="partial_error_payload",
                )
            return dict(response)

        target = response.get("target_source")
        if not isinstance(target, Mapping):
            raise SourceReaderContractError("E1 target_source must be an object")
        target_required = {
            "node_id", "content_hash", "source_path", "document_hash", "index_generation",
        }
        missing_target = target_required - set(target)
        if missing_target:
            raise SourceReaderContractError(
                "E1 target_source is missing: " + ", ".join(sorted(missing_target))
            )
        if target["node_id"] != node_id or target["content_hash"] != expected_hash:
            raise SourceReaderContractError(
                "E1 target_source does not match the requested node address",
                code="source_address_mismatch",
            )
        source_path = _required_text(target["source_path"], "target_source.source_path")
        generation = target["index_generation"]
        if not _is_non_negative_int(generation):
            raise SourceReaderContractError("target_source.index_generation must be non-negative")
        document_hash = target["document_hash"]
        if document_hash is not None and (
            not isinstance(document_hash, str) or not _HASH_RE.fullmatch(document_hash)
        ):
            raise SourceReaderContractError("target_source.document_hash is malformed")
        if scope != "node" and document_hash is None:
            raise SourceReaderContractError(
                f"scope={scope} requires a whole-document hash",
                code="document_hash_unavailable",
            )

        if not isinstance(response.get("diagnostics", []), list):
            raise SourceReaderContractError("E1 diagnostics must be an array")

        seen_roles: set[str] = set()
        has_target_fragment = False
        for index, raw_fragment in enumerate(fragments):
            if not isinstance(raw_fragment, Mapping):
                raise SourceReaderContractError(f"fragments[{index}] must be an object")
            fragment = raw_fragment
            required = {
                "role", "source_path", "content_hash", "raw_text",
                "document_hash", "index_generation",
            }
            missing = required - set(fragment)
            if missing:
                raise SourceReaderContractError(
                    f"fragments[{index}] is missing: " + ", ".join(sorted(missing))
                )
            role = fragment["role"]
            allowed_roles = {
                "target", "parent_context", "previous_neighbor",
                "next_neighbor", "document",
            }
            if role not in allowed_roles:
                raise SourceReaderContractError(f"fragments[{index}].role is unsupported")
            if role in seen_roles:
                raise SourceReaderContractError(f"duplicate source fragment role: {role}")
            seen_roles.add(role)

            fragment_path = _required_text(
                fragment["source_path"], f"fragments[{index}].source_path"
            )
            if fragment_path != source_path:
                raise SourceReaderContractError(
                    "source fragments refer to different source_path values",
                    code="source_path_mismatch",
                )
            raw_text = fragment["raw_text"]
            if not isinstance(raw_text, str):
                raise SourceReaderContractError(f"fragments[{index}].raw_text must be a string")
            content_hash = fragment["content_hash"]
            if not isinstance(content_hash, str) or not _HASH_RE.fullmatch(content_hash):
                raise SourceReaderContractError(
                    f"fragments[{index}].content_hash is malformed"
                )
            fragment_document_hash = fragment["document_hash"]
            if fragment_document_hash != document_hash:
                raise SourceReaderContractError(
                    "source fragments have different document_hash values",
                    code="document_hash_mismatch",
                )
            fragment_generation = fragment["index_generation"]
            if fragment_generation != generation:
                raise SourceReaderContractError(
                    "source fragments have different E1 document generations",
                    code="snapshot_generation_mismatch",
                )

            if role == "document":
                if content_hash != document_hash or _sha256(raw_text) != document_hash:
                    raise SourceReaderContractError(
                        "whole-document fragment does not match document_hash",
                        code="document_hash_mismatch",
                    )
            elif _sha256(raw_text) != content_hash:
                raise SourceReaderContractError(
                    f"fragments[{index}] failed exact UTF-8 SHA-256 validation",
                    code="content_hash_mismatch",
                )

            if role == "target":
                has_target_fragment = True
                if (
                    fragment.get("node_id") != node_id
                    or fragment.get("content_hash") != expected_hash
                ):
                    raise SourceReaderContractError(
                        "target fragment does not match requested node address",
                        code="source_address_mismatch",
                    )

        if scope == "document":
            if len(fragments) != 1 or seen_roles != {"document"}:
                raise SourceReaderContractError(
                    "document scope must return exactly one complete document fragment"
                )
        elif not has_target_fragment:
            raise SourceReaderContractError(
                f"scope={scope} response must contain the exact target fragment"
            )

        if scope == "node" and seen_roles != {"target"}:
            raise SourceReaderContractError("node scope must return only the target fragment")
        if scope == "parent" and target.get("parent_node_id") is not None:
            if "parent_context" not in seen_roles:
                raise SourceReaderContractError(
                    "parent scope omitted an available parent without a diagnostic"
                )
        if scope == "neighbors" and any(
            role not in {"target", "previous_neighbor", "next_neighbor"}
            for role in seen_roles
        ):
            raise SourceReaderContractError("neighbors scope returned an unrelated fragment role")

        return dict(response)

    def read_node(
        self,
        node_id: str,
        expected_hash: str,
        snapshot: SnapshotRef,
    ) -> Mapping[str, Any]:
        """Adapt scope=node to the compact node response consumed by SearchAdapter."""
        response = self.read_scope(
            node_id,
            expected_hash,
            "node",
            snapshot,
            budget_tokens=None,
        )
        if response.get("status") != "ok":
            return {"status": response.get("status"), "node": None}
        target = response["target_source"]
        fragment = next(item for item in response["fragments"] if item["role"] == "target")
        node = dict(target)
        node.update({
            key: value
            for key, value in fragment.items()
            if key not in {"role", "token_count"}
        })
        return {"status": "ok", "node": node}
