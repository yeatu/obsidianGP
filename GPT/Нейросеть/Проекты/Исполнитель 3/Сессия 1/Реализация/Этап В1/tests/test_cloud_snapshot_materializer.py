from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import hashlib
from pathlib import Path
import shutil
import zipfile

import pytest

from sfra_context_integrations.cloud_snapshot_v2 import (
    CloudSnapshotManifestV1,
    GitCommitSourceRevision,
    ImmutableImportSourceRevision,
    ImmutableObjectVersion,
    IndexerIdentity,
    SqliteSchemaIdentity,
    build_cloud_snapshot_v2,
)
from sfra_context_integrations.cloud_snapshot_bundle import (
    build_prepared_cloud_snapshot_bundle,
)
from sfra_context_integrations.snapshot_catalogue import (
    InMemorySnapshotCatalogue,
    InvalidSnapshotIdError,
    SnapshotLifecycleState,
    SnapshotRetiredError,
)
from sfra_context_integrations.snapshot_materializer import (
    CloudSnapshotMaterializer,
    InMemoryVersionedObjectStore,
    ObjectStoreReadResult,
    SnapshotMaterializationIntegrityError,
    SnapshotMaterializationStateError,
    VerificationMaterialization,
    MaterializedCloudSnapshot,
    SnapshotObjectIntegrityError,
    SnapshotObjectUnavailableError,
    SnapshotObjectVersionMismatchError,
    SnapshotWorkspaceError,
)


INDEXER = IndexerIdentity(name="sfra-structural-indexer", version="0.2.0")
SQLITE_SCHEMA = SqliteSchemaIdentity(engine="sqlite", schema_info_version=2)


def _fixture(tmp_path: Path, *, immutable_import: bool = False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    indexer = pytest.importorskip(
        "sfra_indexer",
        reason="the full materializer fixture suite runs in the dedicated E1-installed workflow",
    )
    index_vault = indexer.index_vault

    source_root = tmp_path / "synthetic-source"
    source_root.mkdir()
    (source_root / "nested").mkdir()
    (source_root / "README.md").write_bytes(b"# Synthetic snapshot\r\n\r\nExact bytes.\r\n")
    (source_root / "nested" / "unicode.MD").write_bytes("Заметка\n".encode("utf-8"))
    (source_root / "empty.md").write_bytes(b"")
    (source_root / "asset.bin").write_bytes(b"\x00\x01\xfffixture asset")
    index_root = tmp_path / "synthetic-index"
    index_vault(source_root, index_root)
    database_path = index_root / "structure.sqlite3"

    source_revision = (
        ImmutableImportSourceRevision("synthetic-import-2026-120")
        if immutable_import
        else GitCommitSourceRevision("a" * 40)
    )
    prepared = build_prepared_cloud_snapshot_bundle(
        source_root,
        database_path,
        source_revision=source_revision,
        source_object_key="synthetic/source-bundle.zip",
        index_object_key="synthetic/index-bundle.zip",
        indexer_identity=INDEXER,
        sqlite_schema_identity=SQLITE_SCHEMA,
    )
    built = prepared.build_cloud_snapshot_v2(
        source_version_id="source-version-120",
        index_version_id="index-version-120",
    )
    catalogue = InMemorySnapshotCatalogue()
    catalogue.stage(built.ref)
    objects = {
        (built.ref.source_bundle.key, built.ref.source_bundle.version_id): prepared.source_object.payload,
        (built.ref.index_bundle.key, built.ref.index_bundle.version_id): prepared.index_object.payload,
    }
    store = InMemoryVersionedObjectStore(objects)
    return source_root, database_path, prepared, built, catalogue, store


def _activate(catalogue: InMemorySnapshotCatalogue, snapshot_id: str) -> None:
    catalogue.mark_verified(snapshot_id)
    state = catalogue.read_state()
    catalogue.activate(
        snapshot_id,
        expected_generation=state.generation,
        expected_active_snapshot_id=state.active_snapshot_id,
    )


def test_materializes_exact_versions_and_preserves_raw_e1_artifacts(tmp_path: Path):
    source_root, database_path, prepared, built, catalogue, store = _fixture(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = CloudSnapshotMaterializer(catalogue, store).materialize_for_verification(
        built.ref.snapshot_id,
        workspace,
    )

    assert type(result) is VerificationMaterialization
    assert not isinstance(result, MaterializedCloudSnapshot)
    assert result.catalogue_state is SnapshotLifecycleState.STAGED
    assert result.snapshot_ref == built.ref
    assert result.snapshot_id == built.ref.snapshot_id
    assert result.manifest_bytes == built.manifest_bytes
    assert result.bundle_report.source_archive_sha256 == built.ref.source_bundle.sha256
    assert result.bundle_report.index_archive_sha256 == built.ref.index_bundle.sha256
    assert result.source_root.is_dir()
    assert (result.source_root / "README.md").read_bytes() == (source_root / "README.md").read_bytes()
    assert (result.source_root / "nested" / "unicode.MD").read_bytes() == (
        source_root / "nested" / "unicode.MD"
    ).read_bytes()
    assert (result.source_root / "asset.bin").read_bytes() == b"\x00\x01\xfffixture asset"
    assert result.index_database_path.read_bytes() == database_path.read_bytes()

    with zipfile.ZipFile(BytesIO(prepared.index_object.payload), "r") as archive:
        expected_attestation = archive.read("attestation.json")
        expected_inventory = archive.read("markdown-inventory.json")
    assert result.attestation_bytes == expected_attestation
    assert result.markdown_inventory_bytes == expected_inventory
    assert result.attestation_path.read_bytes() == expected_attestation
    assert result.markdown_inventory_path.read_bytes() == expected_inventory
    assert result.index_bundle_sha256 == built.ref.index_bundle.sha256
    assert catalogue.get_exact(built.ref.snapshot_id).state is SnapshotLifecycleState.STAGED
    assert catalogue.read_state().active_snapshot_id is None
    assert result.bundle_report.e1_legacy_verifier == (
        "verified_with_public_e1_v1_git_state_api"
    )
    assert catalogue.get_exact(built.ref.snapshot_id).state is SnapshotLifecycleState.STAGED

    # The object-store interface is read-only, not a write port wearing a fake moustache.
    assert not hasattr(store, "put")
    assert not hasattr(store, "delete")
    assert not hasattr(store, "list")


def test_immutable_import_revision_is_preserved_without_git_coercion(tmp_path: Path):
    _, _, _, built, catalogue, store = _fixture(tmp_path, immutable_import=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = CloudSnapshotMaterializer(catalogue, store).materialize_for_verification(
        built.ref.snapshot_id,
        workspace,
    )

    assert result.snapshot_ref.source_revision == ImmutableImportSourceRevision(
        "synthetic-import-2026-120"
    )
    assert result.bundle_report.e1_legacy_verifier == (
        "skipped_immutable_import_requires_additive_e1_verifier"
    )


def test_missing_exact_object_version_fails_without_creating_materialization(tmp_path: Path):
    _, _, _, built, catalogue, _ = _fixture(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = InMemoryVersionedObjectStore({})

    with pytest.raises(SnapshotObjectUnavailableError):
        CloudSnapshotMaterializer(catalogue, store).materialize_for_verification(
            built.ref.snapshot_id,
            workspace,
        )

    assert list(workspace.iterdir()) == []



def test_wrong_key_echo_is_rejected_even_when_version_and_payload_match(tmp_path: Path):
    _, _, _, built, catalogue, store = _fixture(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    class WrongKeyStore:
        def read_exact(self, key: str, version_id: str) -> ObjectStoreReadResult:
            result = store.read_exact(key, version_id)
            return ObjectStoreReadResult(
                key=result.key + "/unexpected",
                version_id=result.version_id,
                payload=result.payload,
            )

    with pytest.raises(SnapshotObjectVersionMismatchError):
        CloudSnapshotMaterializer(catalogue, WrongKeyStore()).materialize_for_verification(
            built.ref.snapshot_id,
            workspace,
        )

    assert list(workspace.iterdir()) == []

def test_latest_only_or_wrong_version_response_is_rejected(tmp_path: Path):
    _, _, _, built, catalogue, store = _fixture(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    class LatestOnlyStore:
        def read_exact(self, key: str, version_id: str) -> ObjectStoreReadResult:
            exact = store.read_exact(key, version_id)
            return ObjectStoreReadResult(
                key=exact.key,
                version_id="latest",
                payload=exact.payload,
            )

    with pytest.raises(SnapshotObjectVersionMismatchError):
        CloudSnapshotMaterializer(catalogue, LatestOnlyStore()).materialize_for_verification(
            built.ref.snapshot_id,
            workspace,
        )

    assert list(workspace.iterdir()) == []


@pytest.mark.parametrize("corruption", ["changed-bytes", "truncated"])
def test_hash_or_size_mismatch_fails_closed(tmp_path: Path, corruption: str):
    _, _, prepared, built, catalogue, _ = _fixture(tmp_path)
    payload = prepared.source_object.payload
    bad_payload = payload + b"x" if corruption == "changed-bytes" else payload[:-1]
    store = InMemoryVersionedObjectStore(
        {
            (built.ref.source_bundle.key, built.ref.source_bundle.version_id): bad_payload,
            (built.ref.index_bundle.key, built.ref.index_bundle.version_id): prepared.index_object.payload,
        }
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(SnapshotObjectIntegrityError):
        CloudSnapshotMaterializer(catalogue, store).materialize_for_verification(
            built.ref.snapshot_id,
            workspace,
        )

    assert list(workspace.iterdir()) == []


def test_compressed_archive_is_rejected_before_member_read(tmp_path: Path, monkeypatch):
    _, _, prepared, built, catalogue, _ = _fixture(tmp_path)
    source_members: dict[str, bytes] = {}
    with zipfile.ZipFile(BytesIO(prepared.source_object.payload), "r") as archive:
        for name in archive.namelist():
            source_members[name] = archive.read(name)

    stream = BytesIO()
    with zipfile.ZipFile(
        stream,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for name, payload in source_members.items():
            archive.writestr(name, payload, compress_type=zipfile.ZIP_DEFLATED)
    compressed_source = stream.getvalue()
    changed_source_ref = ImmutableObjectVersion(
        key=built.ref.source_bundle.key,
        version_id="compressed-source-version",
        sha256="sha256:" + hashlib.sha256(compressed_source).hexdigest(),
        byte_size=len(compressed_source),
    )
    changed_manifest = CloudSnapshotManifestV1(
        source_revision=built.ref.source_revision,
        source_bundle=changed_source_ref,
        index_bundle=built.ref.index_bundle,
        indexer_identity=built.ref.indexer_identity,
        sqlite_schema_identity=built.ref.sqlite_schema_identity,
    )
    changed_ref = build_cloud_snapshot_v2(changed_manifest).ref
    changed_catalogue = InMemorySnapshotCatalogue()
    changed_catalogue.stage(changed_ref)
    store = InMemoryVersionedObjectStore(
        {
            (changed_ref.source_bundle.key, changed_ref.source_bundle.version_id): compressed_source,
            (changed_ref.index_bundle.key, changed_ref.index_bundle.version_id): prepared.index_object.payload,
        }
    )

    def fail_if_read(*args, **kwargs):
        raise AssertionError("compressed member payload must not be read or decompressed")

    monkeypatch.setattr(zipfile.ZipFile, "read", fail_if_read)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(SnapshotMaterializationIntegrityError):
        CloudSnapshotMaterializer(changed_catalogue, store).materialize_for_verification(
            changed_ref.snapshot_id,
            workspace,
        )

    assert list(workspace.iterdir()) == []


def test_catalogue_a_to_b_switch_keeps_request_on_pinned_a_snapshot(tmp_path: Path):
    _, _, prepared_a, built_a, catalogue, store_a = _fixture(tmp_path / "a")
    (tmp_path / "b").mkdir()
    _, _, prepared_b, built_b, _, _ = _fixture(
        tmp_path / "b",
        immutable_import=True,
    )
    _activate(catalogue, built_a.ref.snapshot_id)
    catalogue.stage(built_b.ref)
    catalogue.mark_verified(built_b.ref.snapshot_id)

    class SwitchingStore:
        def __init__(self):
            self.calls: list[tuple[str, str]] = []

        def read_exact(self, key: str, version_id: str) -> ObjectStoreReadResult:
            self.calls.append((key, version_id))
            result = store_a.read_exact(key, version_id)
            if len(self.calls) == 1:
                state = catalogue.read_state()
                catalogue.activate(
                    built_b.ref.snapshot_id,
                    expected_generation=state.generation,
                    expected_active_snapshot_id=built_a.ref.snapshot_id,
                )
            return result

    switching_store = SwitchingStore()

    class CountingCatalogue:
        def __init__(self):
            self.lookup_count = 0

        def get_exact(self, snapshot_id: str):
            self.lookup_count += 1
            return catalogue.get_exact(snapshot_id)

    counting_catalogue = CountingCatalogue()
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = CloudSnapshotMaterializer(counting_catalogue, switching_store).materialize(
        built_a.ref.snapshot_id,
        workspace,
    )

    # The request stays pinned to A even after the active pointer switches to B.
    # It never resolves or reads B, and it does not mutate the catalogue.
    assert result.snapshot_ref == built_a.ref
    assert result.snapshot_id == built_a.ref.snapshot_id
    assert counting_catalogue.lookup_count == 1
    assert switching_store.calls == [
        (built_a.ref.source_bundle.key, built_a.ref.source_bundle.version_id),
        (built_a.ref.index_bundle.key, built_a.ref.index_bundle.version_id),
    ]
    assert catalogue.read_state().active_snapshot_id == built_b.ref.snapshot_id
    assert catalogue.get_exact(built_b.ref.snapshot_id).snapshot == built_b.ref
    with pytest.raises(SnapshotRetiredError):
        catalogue.get_exact(built_a.ref.snapshot_id)
    assert result.index_database_path.is_file()
    assert result.attestation_bytes == prepared_a.attestation_bytes
    assert result.markdown_inventory_bytes == prepared_a.markdown_inventory_bytes
    shutil.rmtree(result.workspace_root)


def test_retired_snapshot_and_mutable_alias_are_rejected(tmp_path: Path):
    _, _, _, built, catalogue, store = _fixture(tmp_path)
    state = catalogue.read_state()
    catalogue.retire(
        built.ref.snapshot_id,
        expected_generation=state.generation,
        expected_active_snapshot_id=None,
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(SnapshotRetiredError):
        CloudSnapshotMaterializer(catalogue, store).materialize_for_verification(
            built.ref.snapshot_id,
            workspace,
        )
    with pytest.raises(InvalidSnapshotIdError):
        CloudSnapshotMaterializer(catalogue, store).materialize_for_verification("latest", workspace)

    assert list(workspace.iterdir()) == []



def test_staged_snapshot_cannot_use_active_materialization_path(tmp_path: Path):
    _, _, _, built, catalogue, store = _fixture(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    class CountingStore:
        def __init__(self):
            self.calls = 0

        def read_exact(self, key: str, version_id: str) -> ObjectStoreReadResult:
            self.calls += 1
            return store.read_exact(key, version_id)

    counting_store = CountingStore()
    with pytest.raises(SnapshotMaterializationStateError):
        CloudSnapshotMaterializer(catalogue, counting_store).materialize(
            built.ref.snapshot_id,
            workspace,
        )
    assert counting_store.calls == 0
    assert list(workspace.iterdir()) == []
    assert catalogue.get_exact(built.ref.snapshot_id).state is SnapshotLifecycleState.STAGED


def test_verification_materialization_rejects_non_staged_entry(tmp_path: Path):
    _, _, _, built, catalogue, store = _fixture(tmp_path)
    catalogue.mark_verified(built.ref.snapshot_id)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(SnapshotMaterializationStateError):
        CloudSnapshotMaterializer(catalogue, store).materialize_for_verification(
            built.ref.snapshot_id,
            workspace,
        )
    assert list(workspace.iterdir()) == []
    assert catalogue.get_exact(built.ref.snapshot_id).state is SnapshotLifecycleState.VERIFIED


def test_workspace_must_be_an_existing_real_directory(tmp_path: Path):
    _, _, _, built, catalogue, store = _fixture(tmp_path)
    missing_workspace = tmp_path / "missing"

    with pytest.raises(SnapshotWorkspaceError):
        CloudSnapshotMaterializer(catalogue, store).materialize_for_verification(
            built.ref.snapshot_id,
            missing_workspace,
        )
