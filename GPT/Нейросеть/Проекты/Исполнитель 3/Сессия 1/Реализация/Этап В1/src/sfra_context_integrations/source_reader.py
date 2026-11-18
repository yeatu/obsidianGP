"""E3 adapter over the actual public E1 Source Scope API result types."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import re
from typing import Any

from sfra_context_builder.models import SnapshotRef, TokenCounterProtocol

from .snapshot import PinnedSnapshot, SnapshotBindingError
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
    """Validate native E1 dataclass results, then enforce E3-only token budgeting.

    E1's read_source_scope returns SourceScopeResult.to_dict() with anchor,
    parent/previous/next and document records. It does not return the synthetic
    target_source/role fields used by older E3-only fixtures. This adapter maps
    those native records into the E3 SourceReader envelope after verifying their
    source provenance. E1 is never passed a token budget.
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
        # Reject an invalid/stale binding while constructing the reader, before
        # any caller can trigger an E1 address or source read.
        self._verify_pinned_snapshot()

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

    def _verify_pinned_snapshot(self) -> None:
        try:
            self._pinned.verify_current()
        except SnapshotBindingError as exc:
            raise SourceReaderContractError(
                "Pinned snapshot changed after binding; source read rejected",
                code="snapshot_changed",
            ) from exc

    @staticmethod
    def _mapping(value: Any, name: str) -> Mapping[str, Any]:
        if isinstance(value, Mapping):
            return value
        serializer = getattr(value, "to_dict", None)
        if callable(serializer):
            result = serializer()
            if isinstance(result, Mapping):
                return result
        raise SourceReaderContractError(f"{name} must be a mapping or expose to_dict()")

    def resolve_current_node(
        self,
        node_id: str,
        snapshot: SnapshotRef,
    ) -> Mapping[str, Any]:
        """Resolve a current address using E1's CurrentNodeAddress result."""
        _required_text(node_id, "node_id")
        self._check_snapshot(snapshot)
        self._verify_pinned_snapshot()
        try:
            native = self._source_api.resolve_current_node(
                str(self._pinned.database_path),
                node_id,
                snapshot_id=snapshot.snapshot_id,
            )
        except Exception as exc:
            self._verify_pinned_snapshot()
            raise SourceReaderContractError(
                f"E1 resolve_current_node failed ({type(exc).__name__})",
                code="e1_resolve_current_node_failed",
            ) from exc

        self._verify_pinned_snapshot()
        response = self._mapping(native, "E1 resolve_current_node response")
        self._check_echoed_snapshot(response, snapshot)
        status = response.get("status")
        if status != "ok":
            self._check_error_response(response, status, "resolve_current_node")
            return {
                "status": status,
                "snapshot_id": snapshot.snapshot_id,
                "address": None,
                "error": response.get("error"),
            }

        # E1 CurrentNodeAddress.to_dict() is intentionally flat and contains
        # only current address/provenance, never source text.
        address = {
            key: response.get(key)
            for key in (
                "node_id", "content_hash", "source_path",
                "document_hash", "index_generation",
            )
        }
        if any(value is None for value in address.values()):
            raise SourceReaderContractError(
                "E1 current-node success result lacks required address fields"
            )
        self._validate_address(address, requested_node_id=node_id)
        if "raw_text" in response:
            raise SourceReaderContractError(
                "resolve_current_node must return address metadata only, not raw_text",
                code="current_node_returned_source_text",
            )
        return {
            "status": "ok",
            "snapshot_id": snapshot.snapshot_id,
            "address": address,
        }

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
            raise ValueError(f"unsupported scope: {scope!r}")
        self._check_snapshot(snapshot)
        self._verify_pinned_snapshot()
        if budget_tokens is not None and (
            isinstance(budget_tokens, bool)
            or not isinstance(budget_tokens, int)
            or budget_tokens < 1
        ):
            raise ValueError("budget_tokens must be an integer >= 1 or None")

        try:
            native = self._source_api.read_source_scope(
                str(self._pinned.database_path),
                str(self._pinned.vault_root),
                node_id,
                expected_hash,
                scope=scope,
                snapshot_id=snapshot.snapshot_id,
            )
        except Exception as exc:
            self._verify_pinned_snapshot()
            raise SourceReaderContractError(
                f"E1 read_source_scope failed ({type(exc).__name__})",
                code="e1_read_source_scope_failed",
            ) from exc

        self._verify_pinned_snapshot()
        response = self._mapping(native, "E1 read_source_scope response")
        self._check_echoed_snapshot(response, snapshot)
        if response.get("scope") != scope:
            raise SourceReaderContractError(
                "E1 response scope does not match the requested scope",
                code="scope_mismatch",
            )
        status = response.get("status")
        if status != "ok":
            self._check_error_response(response, status, "read_source_scope")
            return {
                "status": status,
                "snapshot_id": snapshot.snapshot_id,
                "target_source": None,
                "fragments": [],
                "diagnostics": [],
                "error": response.get("error"),
            }

        normalized = self._normalize_native_scope(
            response,
            node_id=node_id,
            expected_hash=expected_hash,
            scope=scope,
            snapshot=snapshot,
        )
        self._validate_scope_response(
            normalized,
            node_id=node_id,
            expected_hash=expected_hash,
            scope=scope,
        )

        fragments = normalized["fragments"]
        token_count = sum(
            self._token_counter.count(fragment["raw_text"])
            for fragment in fragments
        )
        accounting = {
            "budget_owner": "E3",
            "tokens_used": token_count,
            "budget_tokens": budget_tokens,
            "tokenizer": dict(self._token_counter.metadata()),
        }
        result = dict(normalized)
        result["token_accounting"] = accounting
        if budget_tokens is not None and token_count > budget_tokens:
            diagnostics = list(result.get("diagnostics", []))
            diagnostics.append({
                "code": "scope_budget_exceeded",
                "severity": "warning",
                "message": (
                    "The complete source scope exceeds the E3 token budget; "
                    "no source text was truncated or returned."
                ),
                "node_ids": [node_id],
                "details": accounting,
            })
            result.update({
                "status": "budget_exceeded",
                "fragments": [],
                "diagnostics": diagnostics,
            })
        return result

    def _normalize_native_scope(
        self,
        response: Mapping[str, Any],
        *,
        node_id: str,
        expected_hash: str,
        scope: str,
        snapshot: SnapshotRef,
    ) -> dict[str, Any]:
        """Map E1 SourceScopeResult.to_dict() into E3's role-labelled envelope."""
        anchor = self._mapping(response.get("anchor"), "E1 scope anchor")
        self._validate_address(
            anchor,
            requested_node_id=node_id,
            requested_hash=expected_hash,
        )
        raw_fragments = response.get("fragments")
        if not isinstance(raw_fragments, list):
            raise SourceReaderContractError("E1 scope fragments must be an array")
        diagnostics: list[Mapping[str, Any]] = []
        normalized_fragments: list[dict[str, Any]] = []

        if scope == "document":
            document = self._mapping(response.get("document"), "E1 document scope result")
            document_hash = document.get("document_hash", document.get("source_sha256"))
            if (
                document.get("source_path") != anchor.get("source_path")
                or document_hash != anchor.get("document_hash")
                or document.get("source_sha256") != anchor.get("document_hash")
                or document.get("index_generation") != anchor.get("index_generation")
                or document.get("anchor_node_id") != node_id
                or document.get("anchor_content_hash") != expected_hash
            ):
                raise SourceReaderContractError(
                    "E1 document record differs from its verified anchor provenance",
                    code="document_hash_mismatch",
                )
            raw_text = document.get("raw_text")
            if not isinstance(raw_text, str):
                raise SourceReaderContractError("E1 document result must contain full raw_text")
            normalized_fragments.append({
                "role": "document",
                "node_id": document.get("anchor_node_id", node_id),
                "source_path": document.get("source_path"),
                "content_hash": document_hash,
                "raw_text": raw_text,
                "document_hash": document_hash,
                "index_generation": document.get(
                    "index_generation", anchor.get("index_generation")
                ),
                "size_bytes": document.get("size_bytes"),
            })
            if raw_fragments:
                raise SourceReaderContractError(
                    "E1 document scope must return the document object, not node fragments"
                )
        else:
            if response.get("document") is not None:
                raise SourceReaderContractError(
                    f"E1 scope={scope} unexpectedly returned a document payload"
                )
            expected_records: list[tuple[str, Mapping[str, Any]]] = [
                ("target", anchor),
            ]
            for native_key, role in (
                ("parent", "parent_context"),
                ("previous", "previous_neighbor"),
                ("next", "next_neighbor"),
            ):
                record = response.get(native_key)
                if record is not None:
                    expected_records.append((
                        role,
                        self._mapping(record, f"E1 scope {native_key} record"),
                    ))

            if scope == "node":
                expected_roles = {"target"}
            elif scope == "parent":
                expected_roles = {"target", "parent_context"}
                if anchor.get("parent_node_id") is None:
                    expected_roles = {"target"}
                    diagnostics.append({
                        "code": "parent_not_present",
                        "severity": "info",
                        "message": "The exact E1 anchor has no parent node.",
                        "node_ids": [node_id],
                        "details": {},
                    })
            elif scope == "neighbors":
                expected_roles = {"target", "previous_neighbor", "next_neighbor"}
            else:
                raise SourceReaderContractError(f"Unsupported normalized scope: {scope}")

            # E1's authoritative named relation fields determine roles. Its
            # fragments tuple must contain exactly the same complete node records.
            expected_records = [
                item for item in expected_records if item[0] in expected_roles
            ]
            expected_by_id = {
                record.get("node_id"): (role, record)
                for role, record in expected_records
            }
            actual_ids: set[str] = set()
            provenance_fields = (
                "node_id", "content_hash", "source_path", "node_type",
                "parent_node_id", "heading_path", "raw_text", "line_start",
                "line_end", "char_start", "char_end", "byte_start", "byte_end",
                "source_sha256", "document_hash", "index_generation", "metadata",
            )
            for raw in raw_fragments:
                item = self._mapping(raw, "E1 scope fragment")
                fragment_id = item.get("node_id")
                if not isinstance(fragment_id, str) or not fragment_id:
                    raise SourceReaderContractError(
                        "E1 node fragment must contain its producer-issued node_id"
                    )
                if fragment_id in actual_ids:
                    raise SourceReaderContractError(
                        "E1 returned a duplicate node fragment"
                    )
                actual_ids.add(fragment_id)
                expected_item = expected_by_id.get(fragment_id)
                if expected_item is None:
                    raise SourceReaderContractError(
                        "E1 returned a node fragment not named by anchor/relationship fields",
                        code="e1_scope_fragment_set_mismatch",
                    )
                role, named_record = expected_item
                mismatches = [
                    field for field in provenance_fields
                    if item.get(field) != named_record.get(field)
                ]
                if mismatches:
                    if {"raw_text", "content_hash"} & set(mismatches):
                        code = "content_hash_mismatch"
                    elif {"document_hash", "source_sha256"} & set(mismatches):
                        code = "document_hash_mismatch"
                    elif "index_generation" in mismatches:
                        code = "snapshot_generation_mismatch"
                    elif "source_path" in mismatches:
                        code = "source_path_mismatch"
                    else:
                        code = "e1_scope_fragment_record_mismatch"
                    raise SourceReaderContractError(
                        "E1 fragment differs from its named anchor/relationship record: "
                        + ", ".join(mismatches),
                        code=code,
                    )
                fragment = dict(item)
                fragment["role"] = role
                normalized_fragments.append(fragment)

            if actual_ids != set(expected_by_id):
                raise SourceReaderContractError(
                    "E1 scope fragments do not contain the complete named record set",
                    code="e1_scope_fragment_set_mismatch",
                )

            if scope == "parent" and anchor.get("parent_node_id") is not None:
                if "parent_context" not in {item["role"] for item in normalized_fragments}:
                    raise SourceReaderContractError(
                        "E1 parent scope omitted an available parent"
                    )
            if scope == "neighbors":
                for role, record in (
                    ("previous_neighbor", response.get("previous")),
                    ("next_neighbor", response.get("next")),
                ):
                    if record is None:
                        continue
                    if role not in {item["role"] for item in normalized_fragments}:
                        raise SourceReaderContractError(
                            f"E1 neighbors scope omitted {role}"
                        )

        return {
            "status": "ok",
            "snapshot_id": snapshot.snapshot_id,
            "scope": scope,
            "requested": {
                "node_id": node_id,
                "expected_hash": expected_hash,
                "scope": scope,
            },
            "target_source": dict(anchor),
            "fragments": normalized_fragments,
            "diagnostics": diagnostics,
        }

    def read_node(
        self,
        node_id: str,
        expected_hash: str,
        snapshot: SnapshotRef,
    ) -> Mapping[str, Any]:
        """Adapt exact scope=node into SearchAdapter's source node envelope."""
        response = self.read_scope(node_id, expected_hash, "node", snapshot)
        if response.get("status") != "ok":
            return {
                "status": response.get("status"),
                "node": None,
                "snapshot_id": response.get("snapshot_id"),
            }
        target = response["target_source"]
        fragment = response["fragments"][0]
        node = dict(target)
        node.update({
            key: value
            for key, value in fragment.items()
            if key not in {"role", "token_count"}
        })
        return {
            "status": "ok",
            "node": node,
            "snapshot_id": response["snapshot_id"],
        }

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
        if operation == "read_source_scope":
            if response.get("fragments", []) != [] or any(
                response.get(key) is not None
                for key in ("anchor", "parent", "previous", "next", "document")
            ):
                raise SourceReaderContractError(
                    "E1 scope error must not contain partial source data",
                    code="partial_error_payload",
                )
        elif operation == "resolve_current_node":
            address_fields = (
                "node_id", "content_hash", "source_path",
                "document_hash", "index_generation",
            )
            if any(response.get(key) is not None for key in address_fields) or "raw_text" in response:
                raise SourceReaderContractError(
                    "E1 current-node error must not contain partial address or source text",
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
            "node_id", "content_hash", "source_path",
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
        generation = address["index_generation"]
        if not _non_negative_int(generation):
            raise SourceReaderContractError("E1 index_generation must be a non-negative integer")
        document_hash = address["document_hash"]
        if document_hash is not None and (
            not isinstance(document_hash, str) or not _HASH_RE.fullmatch(document_hash)
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
        if not isinstance(fragments, list):
            raise SourceReaderContractError("E3 normalized source fragments must be an array")

        roles: set[str] = set()
        fragments_by_role: dict[str, Mapping[str, Any]] = {}
        seen_node_ids: set[str] = set()
        for index, raw in enumerate(fragments):
            fragment = self._mapping(raw, f"E3 source fragments[{index}]")
            required = {
                "role", "source_path", "content_hash", "raw_text",
                "document_hash", "index_generation",
            }
            if fragment.get("role") != "document":
                required.update({
                    "node_id", "node_type", "parent_node_id", "heading_path",
                    "line_start", "line_end", "char_start", "char_end",
                    "byte_start", "byte_end", "source_sha256", "metadata",
                })
            missing = required - set(fragment)
            if missing:
                raise SourceReaderContractError(
                    f"source fragments[{index}] is missing: " + ", ".join(sorted(missing))
                )
            role = fragment["role"]
            if role not in _ROLE_SET or role in roles:
                raise SourceReaderContractError(
                    f"source fragments[{index}] has an unsupported or duplicate role"
                )
            roles.add(role)
            fragments_by_role[role] = fragment
            if fragment["source_path"] != address["source_path"]:
                raise SourceReaderContractError(
                    "Source fragments do not belong to the target source_path",
                    code="source_path_mismatch",
                )
            if fragment["document_hash"] != address["document_hash"]:
                raise SourceReaderContractError(
                    "Source fragments do not share the target document_hash",
                    code="document_hash_mismatch",
                )
            if fragment["index_generation"] != address["index_generation"]:
                raise SourceReaderContractError(
                    "Source fragments do not share the target document generation",
                    code="snapshot_generation_mismatch",
                )
            raw_text = fragment["raw_text"]
            if not isinstance(raw_text, str):
                raise SourceReaderContractError(
                    f"source fragments[{index}].raw_text must be a string"
                )
            content_hash = fragment["content_hash"]
            if not isinstance(content_hash, str) or not _HASH_RE.fullmatch(content_hash):
                raise SourceReaderContractError(
                    f"source fragments[{index}].content_hash is malformed"
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
            else:
                node_id_value = fragment.get("node_id")
                node_type = fragment.get("node_type")
                parent_node_id = fragment.get("parent_node_id")
                heading_path = fragment.get("heading_path")
                line_start, line_end = fragment.get("line_start"), fragment.get("line_end")
                char_start, char_end = fragment.get("char_start"), fragment.get("char_end")
                byte_start, byte_end = fragment.get("byte_start"), fragment.get("byte_end")
                metadata = fragment.get("metadata")
                source_sha = fragment.get("source_sha256")
                if (
                    _sha256(raw_text) != content_hash
                    or not isinstance(node_id_value, str)
                    or not node_id_value.strip()
                    or node_id_value in seen_node_ids
                    or not isinstance(node_type, str)
                    or not node_type.strip()
                    or (parent_node_id is not None and (
                        not isinstance(parent_node_id, str) or not parent_node_id.strip()
                    ))
                    or not isinstance(heading_path, (list, tuple))
                    or any(not isinstance(item, str) for item in heading_path)
                    or isinstance(line_start, bool)
                    or not isinstance(line_start, int)
                    or line_start < 1
                    or isinstance(line_end, bool)
                    or not isinstance(line_end, int)
                    or line_end < line_start - 1
                    or isinstance(char_start, bool)
                    or not isinstance(char_start, int)
                    or char_start < 0
                    or isinstance(char_end, bool)
                    or not isinstance(char_end, int)
                    or char_end < char_start
                    or isinstance(byte_start, bool)
                    or not isinstance(byte_start, int)
                    or byte_start < 0
                    or isinstance(byte_end, bool)
                    or not isinstance(byte_end, int)
                    or byte_end < byte_start
                    or not isinstance(metadata, Mapping)
                    or source_sha != address["document_hash"]
                ):
                    raise SourceReaderContractError(
                        f"Source fragment {role} failed text/hash/locator validation",
                        code="fragment_locator_invalid",
                    )
                seen_node_ids.add(node_id_value)
            if role == "target" and (
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
            expected_parent_id = address.get("parent_node_id")
            parent_fragment = fragments_by_role.get("parent_context")
            if expected_parent_id is not None and parent_fragment is None:
                raise SourceReaderContractError("parent scope omitted an available parent")
            if expected_parent_id is None and parent_fragment is not None:
                raise SourceReaderContractError("root node parent scope returned a parent")
            if parent_fragment is not None and parent_fragment.get("node_id") != expected_parent_id:
                raise SourceReaderContractError(
                    "Parent fragment Node ID does not match target.parent_node_id",
                    code="parent_identity_mismatch",
                )
        if scope == "neighbors":
            if roles - {"target", "previous_neighbor", "next_neighbor"} or "target" not in roles:
                raise SourceReaderContractError("neighbors scope returned invalid fragment roles")
            target_fragment = fragments_by_role["target"]
            target_parent_id = target_fragment.get("parent_node_id")
            target_order = (target_fragment["char_start"], target_fragment["char_end"])
            for role in ("previous_neighbor", "next_neighbor"):
                neighbor = fragments_by_role.get(role)
                if neighbor is None:
                    continue
                if neighbor.get("parent_node_id") != target_parent_id:
                    raise SourceReaderContractError(
                        f"{role} is not an immediate sibling under the target parent",
                        code="neighbor_parent_mismatch",
                    )
                neighbor_order = (neighbor["char_start"], neighbor["char_end"])
                is_ordered = (
                    neighbor_order < target_order
                    if role == "previous_neighbor"
                    else neighbor_order > target_order
                )
                if not is_ordered:
                    raise SourceReaderContractError(
                        f"{role} is not on the expected side of the target in source order",
                        code="neighbor_source_order_mismatch",
                    )
        if scope == "document" and roles != {"document"}:
            raise SourceReaderContractError("document scope must return one complete document fragment")
