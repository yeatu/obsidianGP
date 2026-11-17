"""Resolve B1 dependency Node IDs through E1 current-address and exact-source APIs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sfra_context_builder.models import SnapshotRef

from .source_reader import E1SourceReader, SourceReaderContractError


class E1DependencyResolver:
    """B1 DependencyResolver backed by E1 current-node resolution.

    Missing/stale/ambiguous/deleted addresses return None to B1, leaving the
    dependency unresolved and therefore excluded from any required atomic group.
    Detailed E1 status is retained for Context Pack diagnostics.
    """

    def __init__(self, source_reader: E1SourceReader) -> None:
        if not callable(getattr(source_reader, "resolve_current_node", None)) or not callable(
            getattr(source_reader, "read_scope", None)
        ):
            raise TypeError("source_reader must implement resolve_current_node and read_scope")
        self._reader = source_reader
        self.diagnostics: list[Mapping[str, Any]] = []

    def resolve_node(
        self,
        node_id: str,
        snapshot: SnapshotRef,
    ) -> Mapping[str, Any] | None:
        try:
            response = self._reader.resolve_current_node(node_id, snapshot)
            status = response.get("status")
            if status != "ok":
                self.diagnostics.append({
                    "code": "dependency_current_node_unavailable",
                    "severity": "warning",
                    "message": f"E1 could not confirm current dependency node {node_id}.",
                    "node_ids": [node_id],
                    "details": {"e1_status": status},
                })
                return None

            address = response["address"]
            expected_hash = address["content_hash"]
            source = self._reader.read_scope(
                node_id,
                expected_hash,
                "node",
                snapshot,
            )
            if source.get("status") != "ok":
                self.diagnostics.append({
                    "code": "dependency_source_unavailable",
                    "severity": "warning",
                    "message": f"E1 could not verify source text for dependency node {node_id}.",
                    "node_ids": [node_id],
                    "details": {"e1_status": source.get("status")},
                })
                return None

            target = source["target_source"]
            fragment = source["fragments"][0]
            if target["content_hash"] != expected_hash:
                raise SourceReaderContractError(
                    "Dependency current address changed between resolve and exact read",
                    code="dependency_address_changed",
                )
            if response.get("snapshot_id") != snapshot.snapshot_id:
                raise SourceReaderContractError(
                    "Dependency current address belongs to another snapshot",
                    code="snapshot_mismatch",
                )

            metadata = target.get("metadata")
            metadata = metadata if isinstance(metadata, Mapping) else {}
            # These are B1 policy defaults when E1 has no explicit metadata.
            # They are not described as source annotations.
            preservation = metadata.get("preservation", "normal")
            required_with = metadata.get("required_with", ())
            parent_required = metadata.get("parent_context_required", False)
            defaults_applied = {
                key: default
                for key, default in (
                    ("preservation", "normal"),
                    ("required_with", ()),
                    ("parent_context_required", False),
                )
                if key not in metadata
            }
            if defaults_applied:
                self.diagnostics.append({
                    "code": "dependency_policy_defaults_applied",
                    "severity": "info",
                    "message": (
                        f"E3 applied B1 policy defaults for dependency {node_id}; "
                        "these values are not E1 source annotations."
                    ),
                    "node_ids": [node_id],
                    "details": {"defaults_applied": defaults_applied},
                })
            if preservation not in {"normal", "required"}:
                raise SourceReaderContractError(
                    "E1 dependency metadata preservation is invalid",
                    code="dependency_metadata_invalid",
                )
            if not isinstance(required_with, (list, tuple)) or any(
                not isinstance(item, str) or not item for item in required_with
            ):
                raise SourceReaderContractError(
                    "E1 dependency metadata required_with is invalid",
                    code="dependency_metadata_invalid",
                )
            if not isinstance(parent_required, bool):
                raise SourceReaderContractError(
                    "E1 dependency metadata parent_context_required is invalid",
                    code="dependency_metadata_invalid",
                )

            return {
                "node_id": node_id,
                "source_path": target["source_path"],
                "node_type": target["node_type"],
                "parent_node_id": target.get("parent_node_id"),
                "heading_path": target["heading_path"],
                "line_start": target["line_start"],
                "line_end": target["line_end"],
                "content_hash": target["content_hash"],
                "raw_text": fragment["raw_text"],
                "match_type": "required_dependency",
                "index_generation": target["index_generation"],
                "document_hash": target["document_hash"],
                "preservation": preservation,
                "required_with": tuple(required_with),
                "parent_context_required": parent_required,
                "entity_metadata": (
                    {"e1_metadata": dict(metadata)} if metadata else None
                ),
            }
        except SourceReaderContractError as exc:
            self.diagnostics.append({
                "code": exc.code,
                "severity": "error",
                "message": f"Dependency source verification failed for {node_id}.",
                "node_ids": [node_id],
                "details": {"error_type": type(exc).__name__},
            })
            return None
