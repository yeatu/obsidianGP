"""Production composition of the existing E1/E2/E3 application services."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sfra_indexer import read_source_scope, resolve_current_node, verify_state_directory
from sfra_context_builder import ContextBuilder, SnapshotRef, TiktokenCounter
from sfra_context_integrations import (
    ContextIntegrationPipeline,
    E1SourceReader,
    E2SearchAdapter,
    SearchVaultService,
    bind_pinned_snapshot,
)

from .config import ServerConfig


class CompositionError(RuntimeError):
    """Raised when the trusted local application graph cannot be composed."""


class E1SourceAPIAdapter:
    """Thin adapter over E1's published Python API; never opens SQLite directly."""

    def read_source_scope(
        self, db_path: str, vault_root: str, node_id: str, expected_hash: str,
        *, scope: str, snapshot_id: str,
    ) -> dict[str, Any]:
        result = read_source_scope(
            db_path, vault_root, node_id, expected_hash,
            scope=scope, snapshot_id=snapshot_id,
        )
        return result.to_dict()

    def resolve_current_node(
        self, db_path: str, node_id: str, *, snapshot_id: str,
    ) -> dict[str, Any]:
        result = resolve_current_node(db_path, node_id, snapshot_id=snapshot_id)
        return result.to_dict()


@dataclass(frozen=True, slots=True)
class ApplicationServices:
    """One immutable search composition shared by the MCP tool-handler layer."""

    pinned_snapshot: Any
    source_reader: E1SourceReader
    pipeline: ContextIntegrationPipeline
    search_vault: SearchVaultService

    @property
    def snapshot(self) -> SnapshotRef:
        return self.pinned_snapshot.ref


def build_application_services(config: ServerConfig) -> ApplicationServices:
    """Bind and compose search services, failing closed on any error.

    This is the sole production composition path. Tests replace collaborators
    with monkeypatches local to the test module; no caller-provided verifier or
    snapshot factory is exposed through the CLI or runtime API.

    ReadSourceService is deliberately not constructed here. The coordinator
    prohibited connecting read_source to runtime composition until #36/#51 has
    passed independent review and C acceptance.
    """
    if not isinstance(config, ServerConfig):
        raise TypeError("config must be a validated ServerConfig")

    try:
        pinned = bind_pinned_snapshot(
            sidecar_root=config.sidecar_root,
            vault_git_root=config.vault_git_root,
            vault_root=config.vault_root,
            state_verifier=verify_state_directory,
        )
        token_counter = TiktokenCounter()
        source_reader = E1SourceReader(E1SourceAPIAdapter(), pinned, token_counter)
        search_adapter = E2SearchAdapter(pinned, source_reader)
        context_builder = ContextBuilder(token_counter)
        pipeline = ContextIntegrationPipeline(
            pinned_snapshot=pinned,
            search_adapter=search_adapter,
            context_builder=context_builder,
            source_reader=source_reader,
        )
        return ApplicationServices(
            pinned_snapshot=pinned,
            source_reader=source_reader,
            pipeline=pipeline,
            search_vault=SearchVaultService(pipeline),
        )
    except Exception as exc:
        # Avoid leaking local paths, request material, or source data to stderr.
        raise CompositionError(
            f"Application-service composition failed ({type(exc).__name__})"
        ) from exc
