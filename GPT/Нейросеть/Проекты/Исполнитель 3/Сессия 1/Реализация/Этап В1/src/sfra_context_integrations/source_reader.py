"""E3 adapter over E1's public snapshot-aware Source Scope API."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import re
from typing import Any

from sfra_context_builder.models import SnapshotRef, TokenCounterProtocol

from .snapshot import PinnedSnapshot
from .source_protocol import E1PublicSourceAPI


SCOPES = frozenset({"node", "parent", "neighbors", "document"})
ERROR_STATUSES = frozenset({
    "stale", "stale_source", "ambiguous", "deleted", "not_found",
    "invalid_request", "source_unavailable", "budget_exceeded", "integrity_error",
})
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ROLE_SET = frozenset({
    "target", "parent_context", "previous_neighbor", "next_neighbor", "document",
})


class SourceReaderContractError(ValueError):
    """E1 returned malformed data or data outside the pinned snapshot."""

    def __init__(self, message: str, *, code: str = "source_reader_contract_error") -> None:
        super().__init__(message)
        self.code = code


def _non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceReaderContractError(f"{name} must be a non-empty string")
    return value


class E1SourceReader:
    """Validate E1 responses and enforce E3-only scope budgeting.

    E1 always returns the complete source scope and never receives a token budget.
    E3 counts the complete fragments with the B1 TokenCounterProtocol. If they do
    not fit, E3 returns budget_exceeded with no fragments; raw_text is never cut.
    """

    def __init__(
        self,
        source_api: E1PublicSourceAPI,
        pinned_snapshot: PinnedSnapshot,
        token_counter: TokenCounterProtocol,
    ) -> None:
        if not callable(getattr(source_api, "read_source_scope", None)):
            raise TypeError("source_api must implement read_source_scope")
        if not callable(getattr(source_api, "resolve_current_node", None)):
            raise TypeError("source_api must implement resolve_current_node")
        if not isinstance(pinned_snapshot, PinnedSnapshot):
            raise TypeError("pinned_snapshot must be a PinnedSnapshot")
        if not callable(getattr(token_counter, "count", None)):
            raise TypeError("token_counter must implement TokenCounterProtocol.count")
        self._source_api = source_api
        self._pinned = pinned_snapshot
        self._token_counter = token_counter

    @property
    def pinned_snapshot(self) -> PinnedSnapshot:
        return self._pinned

    def _check_snapshot(self, snapshot: SnapshotRef) -> None:
        if not isinstance(snapshot, SnapshotRef):
            raise TypeError("snapshot must be a SnapshotRef")
        if snapshot != self._pinned.ref:
            raise SourceReaderContractError(
                "Requested SnapshotRef differs from the SourceReader's pinned snapshot",
                code="snapshot_mismatch",
            )

    def resolve_current_node(
        self,
        node_id: str,
        snapshot: SnapshotRef,
    ) -> Mapping[str, Any]:
        """Resolve an exact current node address, using the pinned E1 API only."""
        _required_text(node_id, "node_id")
        self._check_snapshot(snapshot)
        try:
            response = self._source_api.resolve_current_node(
                str(self._pinned.database_path),
                node_id,
                snapshot_id=snapshot.snapshot_id,
            )
        except Exception as exc:
            raise SourceReaderContractError(
                f"E1 resolve_current_node failed ({type(exc).__name__})",
                code="e1_resolve_current_node_failed",
            ) from exc

        response = self._mapping(response, "E1 resolve_current_node response")
        self._check_echoed_snapshot(response, snapshot)
        status = response.get("status")
        if status != "ok":
            self._check_error_response(response, status, "resolve_current_node")
            return dict(response)

        address = response.get("address")
        if not isinstance(address, Mapping):
            raise SourceReaderContractError(
                "E1 current-node success response must contain address"
            )
        self._validate_address(address, requested_node_id=node_id)
        if "raw_text" in address:
            raise SourceReaderContractError(
                "resolve_current_node must return address metadata only, not raw_text",
                code="current_node_returned_source_text",
            )
        return dict(response)

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
        self._check_snapshot(snapshot)
        if budget_tokens is not None and (
            isinstance(budget_tokens, bool)
            or not isinstance(budget_tokens, int)
            or budget_tokens < 1
        ):
            raise ValueError("budget_tokens must be an integer >= 1 or None")

        try:
            response = self._source_api.read_source_scope(
                str(self._pinned.database_path),
                str(self._pinned.vault_root),
                node_id,
                expected_hash,
                scope=scope,
                snapshot_id=snapshot.snapshot_id,
            )
        except Exception as exc:
            raise SourceReaderContractError(
                f"E1 read_source_scope failed ({type(exc).__name__})",
                code="e1_read_source_scope_failed",
            ) from exc

        response = self._mapping(response, "E1 read_source_scope response")
        self._check_echoed_snapshot(response, snapshot)
        status = response.get("status")
        if status != "ok":
            self._check_error_response(response, status, "read_source_scope")
            return dict(response)

        self._validate_scope_response(
            response,
            node_id=node_id,
            expected_hash=expected_hash,
            scope=scope,
        )

        fragments = response["fragments"]
        token_count = sum(self._token_counter.count(fragment["raw_text"]) for fragment in fragments)
        accounting = {
            "budget_owner": "E3",
            "tokens_used": token_count,
            "budget_tokens": budget_tokens,
            "tokenizer": dict(self._token_counter.metadata()),
        }
        result = dict(response)
        result["token_accounting"] = accounting
        if budget_tokens is not None and token_count > budget_tokens:
            diagnostics = list(result.get("diagnostics", []))
            diagnostics.append({
                "code": "scope_budget_exceeded",
                "severity": "warning",
                "message": "The complete source scope exceeds the E3 token budget; no source text was truncated or returned.",
                "node_ids": [node_id],
                "details": accounting,
            })
            result.update({
                "status": "budget_exceeded",
                "fragments": [],
                "diagnostics": diagnostics,
            })
        return result

    def read_node(
        self,
        node_id: str,
        expected_hash: str,
        snapshot: SnapshotRef,
    ) -> Mapping[str, Any]:
        """Adapt exact scope=node into the compact SearchAdapter E1 node envelope."""
        response = self.read_scope(node_id, expected_hash, "node", snapshot)
        if response.get("status") != "ok":
            return {"status": response.get("status"), "node": None}
        target = response["target_source"]
        fragment = response["fragments"][0]
        node = dict(target)
        node.update({
            key: value
            for key, value in fragment.items()
            if key not in {"role", "token_count"}
        })
        return {"status": "ok", "node": node, "snapshot_id": response["snapshot_id"]}

    @staticmethod
    def _mapping(value: Any, name: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise SourceReaderContractError(f"{name} must be an object")
        return value

    @staticmethod
    def _check_echoed_snapshot(response: Mapping[str, Any], snapshot: SnapshotRef) -> None:
        if response.get("snapshot_id") != snapshot.snapshot_id:
            raise SourceReaderContractError(
                "E1 response snapshot_id does not match the pinned SnapshotRef",
                code="snapshot_mismatch",
            )

    @staticmethod
    def _check_error_response(
        response: Mapping[str, Any],
        status: Any,
        operation: str,
    ) -> None:
        if not isinstance(status, str) or status not in ERROR_STATUSES:
            raise SourceReaderContractError(
                f"E1 {operation} returned unsupported status {status!r}"
            )
        if response.get("fragments", []) != [] or (
            operation == "read_source_scope" and response.get("target_source") is not None
        ):
            raise SourceReaderContractError(
                "E1 error response must contain no partial source fragments or target metadata",
                code="partial_error_payload",
            )
        if operation == "resolve_current_node" and response.get("address") is not None:
            raise SourceReaderContractError(
                "E1 current-node error response must not contain an address",
                code="partial_error_payload",
            )

    @staticmethod
    def _validate_address(
        address: Mapping[str, Any],
        *,
        requested_node_id: str,
        requested_hash: str | None = None,
    ) -> None:
        required = {
            "node_id", "content_hash", "source_path", "node_type",
            "parent_node_id", "heading_path", "line_start", "line_end",
            "document_hash", "index_generation",
        }
        missing = required - set(address)
        if missing:
            raise SourceReaderContractError(
                "E1 node address is missing: " + ", ".join(sorted(missing))
            )
        if address["node_id"] != requested_node_id:
            raise SourceReaderContractError(
                "E1 address returned a different Node ID",
                code="source_address_mismatch",
            )
        content_hash = address["content_hash"]
        if not isinstance(content_hash, str) or not _HASH_RE.fullmatch(content_hash):
            raise SourceReaderContractError("E1 address content_hash is malformed")
        if requested_hash is not None and content_hash != requested_hash:
            raise SourceReaderContractError(
                "E1 address content_hash differs from the requested hash",
                code="source_address_mismatch",
            )
        _required_text(address["source_path"], "E1 address source_path")
        _required_text(address["node_type"], "E1 address node_type")
        heading_path = address["heading_path"]
        if not isinstance(heading_path, (list, tuple)) or any(
            not isinstance(item, str) for item in heading_path
        ):
            raise SourceReaderContractError("E1 address heading_path must be an array of strings")
        if (
            isinstance(address["line_start"], bool)
            or not isinstance(address["line_start"], int)
            or address["line_start"] < 1
            or isinstance(address["line_end"], bool)
            or not isinstance(address["line_end"], int)
            or address["line_end"] < address["line_start"] - 1
        ):
            raise SourceReaderContractError("E1 address line coordinates are invalid")
        generation = address["index_generation"]
        if not _non_negative_int(generation):
            raise SourceReaderContractError("E1 index_generation must be a non-negative integer")
        doc_hash = address["document_hash"]
        if doc_hash is not None and (
            not isinstance(doc_hash, str) or not _HASH_RE.fullmatch(doc_hash)
        ):
            raise SourceReaderContractError("E1 document_hash is malformed")

    def _validate_scope_response(
        self,
        response: Mapping[str, Any],
        *,
        node_id: str,
        expected_hash: str,
        scope: str,
    ) -> None:
        address = self._mapping(response.get("target_source"), "E1 target_source")
        self._validate_address(
            address,
            requested_node_id=node_id,
            requested_hash=expected_hash,
        )
        if scope != "node" and address["document_hash"] is None:
            raise SourceReaderContractError(
                f"scope={scope} requires a whole-document hash",
                code="document_hash_unavailable",
            )

        diagnostics = response.get("diagnostics", [])
        if not isinstance(diagnostics, list):
            raise SourceReaderContractError("E1 diagnostics must be an array")
        fragments = response.get("fragments")
        if not isinstance(fragments, list) or not fragments:
            raise SourceReaderContractError("E1 success response must contain source fragments")

        roles: set[str] = set()
        for index, raw in enumerate(fragments):
            fragment = self._mapping(raw, f"E1 fragments[{index}]")
            required = {
                "role", "source_path", "content_hash", "raw_text",
                "document_hash", "index_generation",
            }
            missing = required - set(fragment)
            if missing:
                raise SourceReaderContractError(
                    f"E1 fragments[{index}] is missing: " + ", ".join(sorted(missing))
                )
            role = fragment["role"]
            if role not in _ROLE_SET or role in roles:
                raise SourceReaderContractError(
                    f"E1 fragments[{index}] has an unsupported or duplicate role"
                )
            roles.add(role)
            if fragment["source_path"] != address["source_path"]:
                raise SourceReaderContractError(
                    "E1 fragments do not belong to the target source_path",
                    code="source_path_mismatch",
                )
            if fragment["document_hash"] != address["document_hash"]:
                raise SourceReaderContractError(
                    "E1 fragments do not share the target document_hash",
                    code="document_hash_mismatch",
                )
            if fragment["index_generation"] != address["index_generation"]:
                raise SourceReaderContractError(
                    "E1 fragments do not share the target document generation",
                    code="snapshot_generation_mismatch",
                )
            raw_text = fragment["raw_text"]
            if not isinstance(raw_text, str):
                raise SourceReaderContractError(
                    f"E1 fragments[{index}].raw_text must be a string"
                )
            content_hash = fragment["content_hash"]
            if not isinstance(content_hash, str) or not _HASH_RE.fullmatch(content_hash):
                raise SourceReaderContractError(
                    f"E1 fragments[{index}].content_hash is malformed"
                )
            if role != "document":
                if (
                    not isinstance(fragment.get("node_id"), str)
                    or not fragment["node_id"].strip()
                    or not isinstance(fragment.get("node_type"), str)
                    or not fragment["node_type"].strip()
                    or not isinstance(fragment.get("heading_path"), (list, tuple))
                    or any(not isinstance(item, str) for item in fragment["heading_path"])
                    or isinstance(fragment.get("line_start"), bool)
                    or not isinstance(fragment.get("line_start"), int)
                    or fragment["line_start"] < 1
                    or isinstance(fragment.get("line_end"), bool)
                    or not isinstance(fragment.get("line_end"), int)
                    or fragment["line_end"] < fragment["line_start"] - 1
                ):
                    raise SourceReaderContractError(
                        f"E1 fragment {role} has invalid structural locator metadata",
                        code="fragment_locator_invalid",
                    )
            if role == "document":
                if (
                    content_hash != address["document_hash"]
                    or _sha256(raw_text) != address["document_hash"]
                ):
                    raise SourceReaderContractError(
                        "Complete document text does not match document_hash",
                        code="document_hash_mismatch",
                    )
            elif _sha256(raw_text) != content_hash:
                raise SourceReaderContractError(
                    f"E1 fragment {role} failed exact UTF-8 SHA-256 validation",
                    code="content_hash_mismatch",
                )
            if role == "target":
                if (
                    fragment.get("node_id") != node_id
                    or fragment.get("content_hash") != expected_hash
                ):
                    raise SourceReaderContractError(
                        "Target fragment does not match the requested node address",
                        code="source_address_mismatch",
                    )

        if scope == "node" and roles != {"target"}:
            raise SourceReaderContractError("node scope must return exactly the target fragment")
        if scope == "parent":
            if roles - {"target", "parent_context"} or "target" not in roles:
                raise SourceReaderContractError("parent scope returned invalid fragment roles")
            if address["parent_node_id"] is None:
                if "parent_context" in roles or not any(
                    item.get("code") == "parent_not_present" for item in diagnostics
                ):
                    raise SourceReaderContractError(
                        "root node parent scope must return a parent_not_present diagnostic"
                    )
            elif "parent_context" not in roles:
                raise SourceReaderContractError("parent scope omitted an available parent")
        if scope == "neighbors":
            if roles - {"target", "previous_neighbor", "next_neighbor"} or "target" not in roles:
                raise SourceReaderContractError("neighbors scope returned invalid fragment roles")
        if scope == "document" and roles != {"document"}:
            raise SourceReaderContractError("document scope must return one complete document fragment")
