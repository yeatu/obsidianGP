from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path

import pytest

from sfra_context_integrations.cloud_snapshot_v2 import (
    CloudSnapshotManifestV1,
    GitCommitSourceRevision,
    IndexerIdentity,
    SqliteSchemaIdentity,
    build_cloud_snapshot_v2,
)
from sfra_context_integrations.cloud_snapshot_bundle import (
    PreparedCloudSnapshotBundle,
    build_prepared_cloud_snapshot_bundle,
)
from sfra_context_integrations.cloud_snapshot_writer import (
    InMemoryImmutableObjectStore,
    InMemoryWriteFault,
    ObjectStoreAcknowledgementError,
    ObjectStoreConditionalConflictError,
    ObjectStorePartialWriteError,
    ObjectStoreReadBackError,
    ObjectStoreWriteContractError,
    ObjectWriteReceipt,
    PreparedBundleRejectedError,
    UploadedCloudSnapshotBundle,
    write_prepared_cloud_snapshot_bundle,
)


INDEXER = IndexerIdentity(name="sfra-structural-indexer", version="0.2.0")
SQLITE_SCHEMA = SqliteSchemaIdentity(engine="sqlite", schema_info_version=2)


def _prepared_bundle(tmp_path: Path) -> PreparedCloudSnapshotBundle:
    try:
        from sfra_indexer import index_vault
    except ImportError:
        pytest.skip("the E1 indexer fixture package is not installed in this workflow")

    source_root = tmp_path / "synthetic-source"
    source_root.mkdir()
    (source_root / "policy.md").write_bytes(b"# Synthetic policy\r\n\r\nAllowed: fixture-only.\r\n")
    (source_root / "empty.md").write_bytes(b"")
    (source_root / "assets").mkdir()
    (source_root / "assets" / "payload.bin").write_bytes(b"\x00\x01synthetic")

    index_root = tmp_path / "synthetic-index"
    index_vault(source_root, index_root)
    return build_prepared_cloud_snapshot_bundle(
        source_root,
        index_root / "structure.sqlite3",
        source_revision=GitCommitSourceRevision("a" * 40),
        source_object_key="prepared/source-bundle.zip",
        index_object_key="prepared/index-bundle.zip",
        indexer_identity=INDEXER,
        sqlite_schema_identity=SQLITE_SCHEMA,
    )


class RecordingStore:
    def __init__(self, inner=None):
        self.inner = inner or InMemoryImmutableObjectStore()
        self.put_calls = 0
    def put_if_absent(self, key, payload, *, expected_sha256, expected_byte_size):
        self.put_calls += 1
        return self.inner.put_if_absent(
            key, payload, expected_sha256=expected_sha256, expected_byte_size=expected_byte_size
        )
    def read_exact(self, key, version_id):
        return self.inner.read_exact(key, version_id)


def test_writer_verifies_full_bytes_exact_versions_and_binds_cloud_snapshot_ref(tmp_path: Path):
    bundle = _prepared_bundle(tmp_path)
    store = InMemoryImmutableObjectStore()

    uploaded = write_prepared_cloud_snapshot_bundle(bundle, store)

    assert uploaded.prepared_bundle is bundle
    assert uploaded.source_receipt.key == bundle.source_object.key
    assert uploaded.source_receipt.sha256 == bundle.source_object.sha256
    assert uploaded.source_receipt.byte_size == len(bundle.source_object.payload)
    assert uploaded.index_receipt.key == bundle.index_object.key
    assert uploaded.index_receipt.sha256 == bundle.index_object.sha256
    assert uploaded.index_receipt.byte_size == len(bundle.index_object.payload)
    assert store.read_exact(uploaded.source_receipt.key, uploaded.source_receipt.version_id) == bundle.source_object.payload
    assert store.read_exact(uploaded.index_receipt.key, uploaded.index_receipt.version_id) == bundle.index_object.payload
    assert uploaded.snapshot_ref.source_bundle.version_id == uploaded.source_receipt.version_id
    assert uploaded.snapshot_ref.index_bundle.version_id == uploaded.index_receipt.version_id
    assert uploaded.snapshot_ref.source_bundle.sha256 == bundle.source_object.sha256
    assert uploaded.snapshot_ref.index_bundle.sha256 == bundle.index_object.sha256
    assert uploaded.snapshot_ref.source_bundle.byte_size == bundle.source_object.byte_size
    assert uploaded.snapshot_ref.index_bundle.byte_size == bundle.index_object.byte_size
    assert uploaded.snapshot_id == uploaded.snapshot_ref.snapshot_id
    assert uploaded.built_snapshot.manifest_bytes


def test_identical_retries_are_idempotent_and_return_the_same_immutable_snapshot(tmp_path: Path):
    bundle = _prepared_bundle(tmp_path)
    store = InMemoryImmutableObjectStore()

    first = write_prepared_cloud_snapshot_bundle(bundle, store)
    second = write_prepared_cloud_snapshot_bundle(bundle, store)

    assert first.source_receipt == second.source_receipt
    assert first.index_receipt == second.index_receipt
    assert first.snapshot_id == second.snapshot_id
    assert store.stored_object_count() == 2


def test_same_key_with_different_payload_fails_conditional_put_without_overwrite():
    store = InMemoryImmutableObjectStore()
    original = b"original immutable synthetic payload"
    replacement = b"different synthetic payload"
    original_hash = "sha256:" + hashlib.sha256(original).hexdigest()
    replacement_hash = "sha256:" + hashlib.sha256(replacement).hexdigest()
    store.put_if_absent(
        "objects/source.zip", original,
        expected_sha256=original_hash, expected_byte_size=len(original)
    )

    with pytest.raises(ObjectStoreConditionalConflictError):
        store.put_if_absent(
            "objects/source.zip", replacement,
            expected_sha256=replacement_hash, expected_byte_size=len(replacement)
        )
    assert store.read_exact(
        "objects/source.zip", "memory-v1:" + hashlib.sha256((
            "objects/source.zip" + "\\0" + original_hash
        ).encode("utf-8")).hexdigest()
    ) == original


@pytest.mark.parametrize(
    "payload,expected_hash,expected_size",
    [
        (b"payload", "sha256:" + "0" * 64, 7),
        (b"payload", "sha256:" + hashlib.sha256(b"payload").hexdigest(), 8),
        (b"", "sha256:" + hashlib.sha256(b"").hexdigest(), 0),
    ],
)
def test_writer_port_rejects_hash_or_size_mismatch_before_storing(payload, expected_hash, expected_size):
    store = InMemoryImmutableObjectStore()
    with pytest.raises(ObjectStoreWriteContractError):
        store.put_if_absent(
            "objects/test.bin", payload,
            expected_sha256=expected_hash, expected_byte_size=expected_size
        )
    assert store.stored_object_count() == 0


def test_port_is_structurally_write_only_without_list_overwrite_or_delete_methods():
    store = InMemoryImmutableObjectStore()
    assert callable(store.put_if_absent)
    assert callable(store.read_exact)
    assert not hasattr(store, "list_objects")
    assert not hasattr(store, "overwrite")
    assert not hasattr(store, "delete")


def test_invalid_prepared_bundle_fails_before_any_object_is_written(tmp_path: Path):
    bundle = _prepared_bundle(tmp_path)
    forged = replace(bundle, markdown_inventory_sha256="sha256:" + "0" * 64)
    store = RecordingStore()

    with pytest.raises(PreparedBundleRejectedError):
        write_prepared_cloud_snapshot_bundle(forged, store)
    assert store.put_calls == 0


@pytest.mark.parametrize(
    "fault,error_type",
    [
        (InMemoryWriteFault.PARTIAL_WRITE, ObjectStorePartialWriteError),
        (InMemoryWriteFault.MISSING_ACKNOWLEDGEMENT, ObjectStoreAcknowledgementError),
        (InMemoryWriteFault.CORRUPT_READ_BACK, ObjectStoreReadBackError),
    ],
)
def test_faulted_source_write_never_returns_a_verified_bundle_or_snapshot_ref(tmp_path: Path, fault, error_type):
    bundle = _prepared_bundle(tmp_path)
    store = InMemoryImmutableObjectStore(faults={bundle.source_object.key: fault})

    with pytest.raises(error_type):
        write_prepared_cloud_snapshot_bundle(bundle, store)


@pytest.mark.parametrize(
    "fault,error_type",
    [
        (InMemoryWriteFault.PARTIAL_WRITE, ObjectStorePartialWriteError),
        (InMemoryWriteFault.MISSING_ACKNOWLEDGEMENT, ObjectStoreAcknowledgementError),
        (InMemoryWriteFault.CORRUPT_READ_BACK, ObjectStoreReadBackError),
    ],
)
def test_second_object_failure_does_not_return_snapshot_even_when_source_write_is_orphaned(tmp_path: Path, fault, error_type):
    bundle = _prepared_bundle(tmp_path)
    store = InMemoryImmutableObjectStore(faults={bundle.index_object.key: fault})

    with pytest.raises(error_type):
        write_prepared_cloud_snapshot_bundle(bundle, store)

    # Source bytes may remain as an immutable orphan; the port exposes no delete or rollback.
    assert store.read_exact(
        bundle.source_object.key,
        "memory-v1:" + hashlib.sha256((
            bundle.source_object.key + "\\0" + bundle.source_object.sha256
        ).encode("utf-8")).hexdigest(),
    ) == bundle.source_object.payload
    assert store.stored_object_count() == 2


def test_missing_exact_version_readback_is_a_typed_failure(tmp_path: Path):
    bundle = _prepared_bundle(tmp_path)

    class MissingReadBackStore:
        def __init__(self):
            self.inner = InMemoryImmutableObjectStore()
        def put_if_absent(self, key, payload, *, expected_sha256, expected_byte_size):
            return self.inner.put_if_absent(
                key, payload, expected_sha256=expected_sha256, expected_byte_size=expected_byte_size
            )
        def read_exact(self, key, version_id):
            return None

    with pytest.raises(ObjectStoreReadBackError):
        write_prepared_cloud_snapshot_bundle(bundle, MissingReadBackStore())


def test_store_does_not_overwrite_existing_bytes_on_retry_after_partial_write(tmp_path: Path):
    bundle = _prepared_bundle(tmp_path)
    store = InMemoryImmutableObjectStore(faults={
        bundle.source_object.key: InMemoryWriteFault.PARTIAL_WRITE
    })
    with pytest.raises(ObjectStorePartialWriteError):
        write_prepared_cloud_snapshot_bundle(bundle, store)

    with pytest.raises(ObjectStoreConditionalConflictError):
        write_prepared_cloud_snapshot_bundle(bundle, store)


def test_write_receipts_reject_mutable_aliases_but_preserve_opaque_provider_ids():
    from sfra_context_integrations.cloud_snapshot_writer import ObjectWriteReceipt

    for alias in ("latest", "LATEST", "current", "HEAD", "*"):
        with pytest.raises(ObjectStoreWriteContractError):
            ObjectWriteReceipt(
                key="objects/source.zip",
                version_id=alias,
                sha256="sha256:" + "a" * 64,
                byte_size=1,
            )

    receipt = ObjectWriteReceipt(
        key="objects/source.zip",
        version_id="provider-generation/2026-11-18:Opaque-0007",
        sha256="sha256:" + "a" * 64,
        byte_size=1,
    )
    assert receipt.version_id == "provider-generation/2026-11-18:Opaque-0007"


def test_writer_accepts_only_the_exact_prepared_bundle_type():
    store = RecordingStore()
    with pytest.raises(PreparedBundleRejectedError):
        write_prepared_cloud_snapshot_bundle({"source": b"not a descriptor"}, store)
    assert store.put_calls == 0


@pytest.mark.parametrize(
    "version_id",
    [
        "\\x00",
        "control\\x1fcharacter",
        "decomposed-e\\u0301",
        "surrogate-\\ud800",
        "v" * 4097,
        " leading-space",
        "trailing-space ",
    ],
)
def test_write_receipts_reject_version_ids_outside_the_exact_v2_contract(version_id):
    with pytest.raises(ObjectStoreWriteContractError):
        ObjectWriteReceipt(
            key="objects/source.zip",
            version_id=version_id,
            sha256="sha256:" + "a" * 64,
            byte_size=1,
        )


def test_invalid_source_receipt_stops_before_the_index_object_write(tmp_path: Path):
    bundle = _prepared_bundle(tmp_path)

    class InvalidFirstReceiptStore:
        def __init__(self):
            self.put_keys = []

        def put_if_absent(self, key, payload, *, expected_sha256, expected_byte_size):
            self.put_keys.append(key)
            # A conforming store must construct the shared receipt type. Its constructor
            # rejects this non-NFC ID before the writer can attempt the second object.
            return ObjectWriteReceipt(
                key=key,
                version_id="decomposed-e\\u0301",
                sha256=expected_sha256,
                byte_size=expected_byte_size,
            )

        def read_exact(self, key, version_id):
            raise AssertionError("read-back must not run for an invalid receipt")

    store = InvalidFirstReceiptStore()
    with pytest.raises(ObjectStoreWriteContractError):
        write_prepared_cloud_snapshot_bundle(bundle, store)

    assert store.put_keys == [bundle.source_object.key]


def test_uploaded_bundle_rejects_a_different_but_internally_valid_v2_identity(tmp_path: Path):
    bundle = _prepared_bundle(tmp_path)
    uploaded = write_prepared_cloud_snapshot_bundle(bundle, InMemoryImmutableObjectStore())
    original = uploaded.built_snapshot.ref
    forged_manifest = CloudSnapshotManifestV1(
        source_revision=original.source_revision,
        source_bundle=replace(original.source_bundle, key=original.source_bundle.key + ".unrelated"),
        index_bundle=original.index_bundle,
        indexer_identity=original.indexer_identity,
        sqlite_schema_identity=original.sqlite_schema_identity,
    )
    forged_built = build_cloud_snapshot_v2(forged_manifest)

    assert forged_built.ref.source_bundle.version_id == uploaded.source_receipt.version_id
    assert forged_built.ref.index_bundle.version_id == uploaded.index_receipt.version_id
    assert forged_built.ref.snapshot_id != uploaded.snapshot_id
    with pytest.raises(ObjectStoreWriteContractError):
        UploadedCloudSnapshotBundle(
            prepared_bundle=bundle,
            source_receipt=uploaded.source_receipt,
            index_receipt=uploaded.index_receipt,
            built_snapshot=forged_built,
        )
