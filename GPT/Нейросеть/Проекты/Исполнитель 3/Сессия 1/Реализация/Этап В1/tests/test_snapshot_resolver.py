from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib.metadata import version
from pathlib import Path
import shutil

import pytest

from sfra_context_integrations.cloud_snapshot_bundle import (
    build_prepared_cloud_snapshot_bundle,
)
from sfra_context_integrations.cloud_snapshot_v2 import (
    CloudSnapshotManifestV1,
    GitCommitSourceRevision,
    ImmutableImportSourceRevision,
    ImmutableObjectVersion,
    build_cloud_snapshot_v2,
)
from sfra_context_integrations.snapshot_catalogue import (
    InMemorySnapshotCatalogue,
    SnapshotLifecycleState,
)
from sfra_context_integrations.snapshot_resolver import (
    CloudSnapshotResolver,
    ExactObjectVersionUnavailableError,
    MaterializedFileChangedError,
    ObjectPayloadIntegrityError,
    ObjectVersionIdentityError,
    ObjectVersionNotFoundError,
    ObjectVersionRead,
    SnapshotBundleIntegrityError,
    SnapshotNotVerifiedError,
    SnapshotUnavailableError,
)


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _fixture(tmp_path: Path, label: str = "a", *, import_revision: bool = False):
    from sfra_indexer import index_vault

    source_root = tmp_path / f"source-{label}"
    source_root.mkdir()
    (source_root / "nested").mkdir()
    (source_root / "one.md").write_bytes("Первая строка\r\nВторая строка\r\n".encode("utf-8"))
    (source_root / "nested" / "two.MD").write_bytes("Second document\n".encode("utf-8"))
    (source_root / "empty.md").write_bytes(b"")
    (source_root / "asset.bin").write_bytes(b"\x00\x01synthetic asset")

    index_root = tmp_path / f"index-{label}"
    index_vault(source_root, index_root)
    database_path = index_root / "structure.sqlite3"
    assert database_path.is_file()

    revision = (
        ImmutableImportSourceRevision(f"synthetic-import-{label}")
        if import_revision
        else GitCommitSourceRevision(label[0] * 40)
    )
    prepared = build_prepared_cloud_snapshot_bundle(
        source_root,
        database_path,
        source_revision=revision,
        source_object_key=f"objects/{label}/source.zip",
        index_object_key=f"objects/{label}/index.zip",
        indexer_identity=__import__("sfra_context_integrations.cloud_snapshot_v2", fromlist=["IndexerIdentity"]).IndexerIdentity(
            "sfra-structural-indexer", version("sfra-structural-indexer")
        ),
        sqlite_schema_identity=__import__("sfra_context_integrations.cloud_snapshot_v2", fromlist=["SqliteSchemaIdentity"]).SqliteSchemaIdentity(
            "sqlite", 2
        ),
    )
    built = prepared.build_cloud_snapshot_v2(
        source_version_id=f"source-version-{label}",
        index_version_id=f"index-version-{label}",
    )
    return source_root, database_path, revision, prepared, built


class FakeObjectStore:
    def __init__(self):
        self.objects: dict[tuple[str, str], ObjectVersionRead] = {}
        self.read_calls: list[tuple[str, str]] = []

    def add(self, key: str, version_id: str, payload: bytes):
        self.objects[(key, version_id)] = ObjectVersionRead(key, version_id, payload)

    def get_exact(self, *, key: str, version_id: str) -> ObjectVersionRead:
        self.read_calls.append((key, version_id))
        try:
            return self.objects[(key, version_id)]
        except KeyError as exc:
            raise ObjectVersionNotFoundError("synthetic missing immutable version") from exc


def _catalogue_with_snapshot(snapshot):
    catalogue = InMemorySnapshotCatalogue()
    catalogue.stage(snapshot)
    catalogue.mark_verified(snapshot.snapshot_id)
    return catalogue


def _store_for(prepared, snapshot, *, store=None):
    store = store or FakeObjectStore()
    store.add(snapshot.source_bundle.key, snapshot.source_bundle.version_id, prepared.source_object.payload)
    store.add(snapshot.index_bundle.key, snapshot.index_bundle.version_id, prepared.index_object.payload)
    return store


def _resolve(tmp_path: Path, prepared, snapshot, *, catalogue=None, store=None):
    catalogue = catalogue or _catalogue_with_snapshot(snapshot)
    store = _store_for(prepared, snapshot, store=store)
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    handle = CloudSnapshotResolver(catalogue, store).resolve(
        snapshot.snapshot_id,
        workspace=workspace,
    )
    return handle, store, workspace


def test_resolves_exact_versions_and_preserves_raw_e1_inner_bytes(tmp_path: Path):
    source_root, database_path, _revision, prepared, built = _fixture(tmp_path)
    handle, store, workspace = _resolve(tmp_path, prepared, built.ref)

    assert handle.snapshot == built.ref
    assert handle.snapshot_id == built.ref.snapshot_id
    assert handle.source_root.is_dir()
    assert (handle.source_root / "one.md").read_bytes() == (source_root / "one.md").read_bytes()
    assert (handle.source_root / "nested" / "two.MD").read_bytes() == (source_root / "nested" / "two.MD").read_bytes()
    assert handle.database_path.read_bytes() == database_path.read_bytes()
    assert handle.attestation_bytes == prepared.attestation_bytes
    assert handle.markdown_inventory_bytes == prepared.markdown_inventory_bytes
    assert handle.attestation_path.read_bytes() == prepared.attestation_bytes
    assert handle.inventory_path.read_bytes() == prepared.markdown_inventory_bytes
    assert handle.bundle_report.markdown_inventory_sha256 == prepared.markdown_inventory_sha256
    assert store.read_calls == [
        (built.ref.source_bundle.key, built.ref.source_bundle.version_id),
        (built.ref.index_bundle.key, built.ref.index_bundle.version_id),
    ]
    assert handle.workspace_path.parent == workspace
    assert not hasattr(store, "put") and not hasattr(store, "delete") and not hasattr(store, "list_all")
    shutil.rmtree(handle.workspace_path)


def test_immutable_import_revision_is_preserved_without_git_sha_coercion(tmp_path: Path):
    _source, _database, revision, prepared, built = _fixture(
        tmp_path, label="i", import_revision=True
    )
    handle, _store, _workspace = _resolve(tmp_path, prepared, built.ref)

    assert type(handle.source_revision) is ImmutableImportSourceRevision
    assert handle.source_revision == revision
    assert handle.source_revision.to_dict() == {
        "kind": "immutable_import",
        "import_id": "synthetic-import-i",
    }
    shutil.rmtree(handle.workspace_path)


def test_catalogue_entry_is_looked_up_exactly_once_when_active_pointer_changes(tmp_path: Path):
    _source_a, _database_a, _rev_a, prepared_a, built_a = _fixture(tmp_path, label="a")
    _source_b, _database_b, _rev_b, prepared_b, built_b = _fixture(tmp_path, label="b")
    catalogue = InMemorySnapshotCatalogue()
    catalogue.stage(built_a.ref)
    catalogue.mark_verified(built_a.ref.snapshot_id)
    state = catalogue.read_state()
    catalogue.activate(
        built_a.ref.snapshot_id,
        expected_generation=state.generation,
        expected_active_snapshot_id=None,
    )
    catalogue.stage(built_b.ref)
    catalogue.mark_verified(built_b.ref.snapshot_id)

    class CountingCatalogue:
        def __init__(self):
            self.calls = 0

        def get_exact(self, snapshot_id: str):
            self.calls += 1
            return catalogue.get_exact(snapshot_id)

    counting = CountingCatalogue()

    class SwitchingStore(FakeObjectStore):
        def __init__(self):
            super().__init__()
            self.switched = False

        def get_exact(self, *, key: str, version_id: str) -> ObjectVersionRead:
            if not self.switched:
                self.switched = True
                state_now = catalogue.read_state()
                catalogue.activate(
                    built_b.ref.snapshot_id,
                    expected_generation=state_now.generation,
                    expected_active_snapshot_id=built_a.ref.snapshot_id,
                )
            return super().get_exact(key=key, version_id=version_id)

    store = _store_for(prepared_a, built_a.ref, store=SwitchingStore())
    store.add(built_b.ref.source_bundle.key, built_b.ref.source_bundle.version_id, prepared_b.source_object.payload)
    store.add(built_b.ref.index_bundle.key, built_b.ref.index_bundle.version_id, prepared_b.index_object.payload)
    workspace = tmp_path / "switch-workspace"
    workspace.mkdir()

    handle = CloudSnapshotResolver(counting, store).resolve(
        built_a.ref.snapshot_id,
        workspace=workspace,
    )

    assert counting.calls == 1
    assert handle.snapshot == built_a.ref
    assert store.read_calls == [
        (built_a.ref.source_bundle.key, built_a.ref.source_bundle.version_id),
        (built_a.ref.index_bundle.key, built_a.ref.index_bundle.version_id),
    ]
    assert catalogue.read_state().active_snapshot_id == built_b.ref.snapshot_id
    shutil.rmtree(handle.workspace_path)


def test_staged_or_retired_catalogue_entries_fail_closed(tmp_path: Path):
    _source, _database, _revision, _prepared, built = _fixture(tmp_path)
    staged = InMemorySnapshotCatalogue()
    staged.stage(built.ref)
    with pytest.raises(SnapshotNotVerifiedError):
        CloudSnapshotResolver(staged, FakeObjectStore()).resolve(
            built.ref.snapshot_id, workspace=tmp_path / "staged-workspace"
        )

    retired = _catalogue_with_snapshot(built.ref)
    state = retired.read_state()
    retired.retire(
        built.ref.snapshot_id,
        expected_generation=state.generation,
        expected_active_snapshot_id=None,
    )
    with pytest.raises(SnapshotUnavailableError):
        CloudSnapshotResolver(retired, FakeObjectStore()).resolve(
            built.ref.snapshot_id, workspace=tmp_path / "retired-workspace"
        )


def test_missing_exact_object_version_does_not_fallback_to_latest(tmp_path: Path):
    _source, _database, _revision, prepared, built = _fixture(tmp_path)
    catalogue = _catalogue_with_snapshot(built.ref)
    store = FakeObjectStore()
    store.add(
        built.ref.index_bundle.key,
        built.ref.index_bundle.version_id,
        prepared.index_object.payload,
    )
    workspace = tmp_path / "missing-workspace"
    workspace.mkdir()

    with pytest.raises(ExactObjectVersionUnavailableError):
        CloudSnapshotResolver(catalogue, store).resolve(
            built.ref.snapshot_id,
            workspace=workspace,
        )

    assert store.read_calls == [
        (built.ref.source_bundle.key, built.ref.source_bundle.version_id),
    ]


def test_latest_alias_response_is_rejected_even_when_payload_matches(tmp_path: Path):
    _source, _database, _revision, prepared, built = _fixture(tmp_path)
    catalogue = _catalogue_with_snapshot(built.ref)
    store = FakeObjectStore()
    store.objects[(built.ref.source_bundle.key, built.ref.source_bundle.version_id)] = ObjectVersionRead(
        built.ref.source_bundle.key,
        "latest",
        prepared.source_object.payload,
    )

    with pytest.raises(ObjectVersionIdentityError):
        CloudSnapshotResolver(catalogue, store).resolve(
            built.ref.snapshot_id,
            workspace=tmp_path / "latest-workspace",
        )


def test_payload_hash_or_size_mismatch_is_rejected_before_materialization(tmp_path: Path):
    _source, _database, _revision, prepared, built = _fixture(tmp_path)
    catalogue = _catalogue_with_snapshot(built.ref)
    store = _store_for(prepared, built.ref)
    store.objects[(built.ref.source_bundle.key, built.ref.source_bundle.version_id)] = ObjectVersionRead(
        built.ref.source_bundle.key,
        built.ref.source_bundle.version_id,
        prepared.source_object.payload + b"tampered",
    )
    workspace = tmp_path / "tampered-workspace"
    workspace.mkdir()

    with pytest.raises(ObjectPayloadIntegrityError):
        CloudSnapshotResolver(catalogue, store).resolve(
            built.ref.snapshot_id,
            workspace=workspace,
        )
    assert list(workspace.iterdir()) == []


def test_non_bundle_payload_is_rejected_even_when_outer_digest_is_valid(tmp_path: Path):
    _source, _database, revision, prepared, built = _fixture(tmp_path)
    bad_payload = b"not-a-deterministic-zip"
    bad_source = ImmutableObjectVersion(
        key=built.ref.source_bundle.key,
        version_id="source-version-replaced",
        sha256=_sha256(bad_payload),
        byte_size=len(bad_payload),
    )
    manifest = CloudSnapshotManifestV1(
        source_revision=revision,
        source_bundle=bad_source,
        index_bundle=built.ref.index_bundle,
        indexer_identity=built.ref.indexer_identity,
        sqlite_schema_identity=built.ref.sqlite_schema_identity,
    )
    bad_ref = build_cloud_snapshot_v2(manifest).ref
    catalogue = _catalogue_with_snapshot(bad_ref)
    store = FakeObjectStore()
    store.add(bad_source.key, bad_source.version_id, bad_payload)
    store.add(built.ref.index_bundle.key, built.ref.index_bundle.version_id, prepared.index_object.payload)
    workspace = tmp_path / "bad-zip-workspace"
    workspace.mkdir()

    with pytest.raises(SnapshotBundleIntegrityError):
        CloudSnapshotResolver(catalogue, store).resolve(
            bad_ref.snapshot_id,
            workspace=workspace,
        )
    assert list(workspace.iterdir()) == []


def test_bad_snapshot_id_is_rejected_before_catalogue_or_store_access(tmp_path: Path):
    class MustNotBeCalled:
        def get_exact(self, *_args, **_kwargs):
            raise AssertionError("must not access catalogue/store for mutable alias")

    resolver = CloudSnapshotResolver(MustNotBeCalled(), MustNotBeCalled())
    with pytest.raises(Exception) as error:
        resolver.resolve("latest", workspace=tmp_path / "never")
    assert error.value.code == "invalid_snapshot_request"


def test_materialized_workspace_requires_a_non_symlink_directory(tmp_path: Path):
    _source, _database, _revision, prepared, built = _fixture(tmp_path)
    catalogue = _catalogue_with_snapshot(built.ref)
    store = _store_for(prepared, built.ref)
    target = tmp_path / "real-workspace"
    target.mkdir()
    link = tmp_path / "workspace-link"
    link.symlink_to(target, target_is_directory=True)

    with pytest.raises(Exception) as error:
        CloudSnapshotResolver(catalogue, store).resolve(
            built.ref.snapshot_id,
            workspace=link,
        )
    assert error.value.code == "unsafe_materialization_workspace"
