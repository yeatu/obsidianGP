from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import zipfile

import pytest

from sfra_context_integrations.cloud_snapshot_v2 import (
    CloudSnapshotContractError,
    GitCommitSourceRevision,
    ImmutableImportSourceRevision,
    IndexerIdentity,
    SqliteSchemaIdentity,
    verify_cloud_snapshot_manifest,
)
from sfra_context_integrations.cloud_snapshot_bundle import (
    ATTESTATION_PATH,
    BUNDLE_FORMAT,
    E1_CLOUD_INDEX_ATTESTATION_FORMAT,
    E1_DATABASE_PATH,
    INVENTORY_PATH,
    MARKDOWN_INVENTORY_FORMAT,
    BundleIntegrityError,
    CloudSnapshotBundleError,
    PreparedBundleObject,
    UnsafeSourceTreeError,
    build_markdown_inventory,
    build_prepared_cloud_snapshot_bundle,
    verify_prepared_cloud_snapshot_bundle,
    _inventory_from_files,
    _read_deterministic_zip,
)

INDEXER = IndexerIdentity(name="sfra-structural-indexer", version="0.2.0")
SQLITE_SCHEMA = SqliteSchemaIdentity(engine="sqlite", schema_info_version=2)


def _source_tree(root: Path) -> None:
    (root / "nested").mkdir(parents=True)
    (root / "a.md").write_bytes("Line one\r\nLine two\r\n".encode("utf-8"))
    (root / "nested" / "b.MD").write_bytes("Заметка UTF-8\n".encode("utf-8"))
    (root / "empty.md").write_bytes(b"")
    (root / "asset.bin").write_bytes(b"\x00\x01\xffbinary asset")


def _indexed_fixture(tmp_path: Path) -> tuple[Path, Path]:
    try:
        from sfra_indexer import index_vault
    except ImportError:
        pytest.skip("the isolated E1 indexer fixture package is not installed in this workflow")
    source_root = tmp_path / "synthetic-source"
    source_root.mkdir()
    _source_tree(source_root)
    index_root = tmp_path / "synthetic-index"
    index_vault(source_root, index_root)
    database_path = index_root / "structure.sqlite3"
    assert database_path.is_file()
    return source_root, database_path


def _build(
    source_root: Path,
    database_path: Path,
    *,
    source_revision=None,
    source_object_key="prepared/source-bundle.zip",
    index_object_key="prepared/index-bundle.zip",
):
    return build_prepared_cloud_snapshot_bundle(
        source_root,
        database_path,
        source_revision=source_revision or GitCommitSourceRevision("a" * 40),
        source_object_key=source_object_key,
        index_object_key=index_object_key,
        indexer_identity=INDEXER,
        sqlite_schema_identity=SQLITE_SCHEMA,
    )


_INVALID_V2_OBJECT_KEYS = [
    pytest.param(" \\t ", id="whitespace-only"),
    pytest.param("prepared/bad\nkey.zip", id="control-character"),
    pytest.param("prepared/bad\0key.zip", id="nul-control"),
    pytest.param("prepared/cafe\u0301.zip", id="non-nfc"),
    pytest.param("prepared/" + ("x" * 4090), id="over-4096-characters"),
    pytest.param("prepared/\ud800.zip", id="surrogate"),
]


@pytest.mark.parametrize("object_key", _INVALID_V2_OBJECT_KEYS)
@pytest.mark.parametrize("key_field", ["source_object_key", "index_object_key"])
def test_bundle_builder_rejects_object_keys_outside_v2_text_contract(
    tmp_path: Path, object_key: str, key_field: str
):
    source_root, database_path = _indexed_fixture(tmp_path)

    with pytest.raises(CloudSnapshotBundleError):
        _build(source_root, database_path, **{key_field: object_key})


@pytest.mark.parametrize("object_key", _INVALID_V2_OBJECT_KEYS)
@pytest.mark.parametrize("object_name", ["source_object", "index_object"])
def test_prepared_bundle_verifier_rejects_object_keys_outside_v2_text_contract(
    tmp_path: Path, object_key: str, object_name: str
):
    source_root, database_path = _indexed_fixture(tmp_path)
    bundle = _build(source_root, database_path)
    prepared_object = getattr(bundle, object_name)
    tampered_object = replace(prepared_object, key=object_key)
    tampered_bundle = replace(bundle, **{object_name: tampered_object})

    with pytest.raises(BundleIntegrityError, match="invalid CloudSnapshotRef v2 object key"):
        verify_prepared_cloud_snapshot_bundle(tampered_bundle)

    with pytest.raises(BundleIntegrityError, match="invalid CloudSnapshotRef v2 object key"):
        tampered_bundle.build_cloud_snapshot_v2(
            source_version_id="source-v1",
            index_version_id="index-v1",
        )


def test_bundle_builder_accepts_nfc_object_keys_within_v2_text_limit(tmp_path: Path):
    source_root, database_path = _indexed_fixture(tmp_path)
    bundle = _build(
        source_root,
        database_path,
        source_object_key="prepared/café/source.zip",
        index_object_key="prepared/индекс/index.zip",
    )

    assert bundle.source_object.key == "prepared/café/source.zip"
    assert bundle.index_object.key == "prepared/индекс/index.zip"
    boundary_key = "prepared/" + ("k" * 4087)
    assert len(boundary_key) == 4096
    boundary_bundle = _build(
        source_root,
        database_path,
        source_object_key=boundary_key,
        index_object_key="prepared/индекс/index.zip",
    )
    assert len(boundary_bundle.source_object.key) == 4096

    built = bundle.build_cloud_snapshot_v2(
        source_version_id="source-v1",
        index_version_id="index-v1",
    )
    assert built.ref.source_bundle.key == bundle.source_object.key
    assert built.ref.index_bundle.key == bundle.index_object.key


def _zip_members(raw: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(__import__("io").BytesIO(raw), "r") as archive:
        return {item.filename: archive.read(item) for item in archive.infolist()}


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    from sfra_context_integrations.cloud_snapshot_bundle import _deterministic_zip
    return _deterministic_zip(members)


def _prepared_object(key: str, payload: bytes) -> PreparedBundleObject:
    return PreparedBundleObject(
        key=key,
        payload=payload,
        sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
        byte_size=len(payload),
    )


def test_markdown_inventory_is_canonical_and_preserves_exact_bytes(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    _source_tree(source_root)

    inventory = build_markdown_inventory(source_root)
    parsed = json.loads(inventory.canonical_bytes.decode("utf-8"))

    assert parsed["format"] == MARKDOWN_INVENTORY_FORMAT
    assert [item["path"] for item in parsed["documents"]] == [
        "a.md", "empty.md", "nested/b.MD"
    ]
    crlf = next(item for item in parsed["documents"] if item["path"] == "a.md")
    expected = b"Line one\r\nLine two\r\n"
    assert crlf["byte_size"] == len(expected)
    assert crlf["sha256"] == "sha256:" + hashlib.sha256(expected).hexdigest()
    empty = next(item for item in parsed["documents"] if item["path"] == "empty.md")
    assert empty["byte_size"] == 0
    assert inventory.sha256 == "sha256:" + hashlib.sha256(inventory.canonical_bytes).hexdigest()
    assert b"\n" not in inventory.canonical_bytes


@pytest.mark.parametrize(
    "path",
    ["../escape.md", "/absolute.md", "folder/../escape.md", "folder//escape.md", "./escape.md"],
)
def test_inventory_rejects_unsafe_relative_paths(path: str):
    with pytest.raises(UnsafeSourceTreeError):
        _inventory_from_files([(path, b"synthetic")])


def test_inventory_rejects_duplicate_canonical_markdown_paths():
    with pytest.raises(UnsafeSourceTreeError, match="duplicate"):
        _inventory_from_files([("same.md", b"one"), ("same.md", b"two")])

def test_inventory_rejects_symlinks_without_following_them(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    (source_root / "linked.md").symlink_to(outside)

    with pytest.raises(UnsafeSourceTreeError, match="symlink"):
        build_markdown_inventory(source_root)


def test_inventory_rejects_invalid_utf8_markdown_bytes(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "bad.md").write_bytes(b"invalid-\xff-markdown")
    with pytest.raises(UnsafeSourceTreeError, match="UTF-8"):
        build_markdown_inventory(source_root)

def test_inventory_rejects_special_files(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "normal.md").write_text("normal", encoding="utf-8")
    os.mkfifo(source_root / "pipe.md")

    with pytest.raises(UnsafeSourceTreeError, match="special files"):
        build_markdown_inventory(source_root)


def test_inventory_rejects_invalid_utf8_paths(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    descriptor = os.open(
        os.fsencode(source_root) + b"/invalid-\xff.md",
        os.O_CREAT | os.O_WRONLY,
        0o600,
    )
    os.close(descriptor)

    with pytest.raises(UnsafeSourceTreeError, match="UTF-8"):
        build_markdown_inventory(source_root)


def test_bundle_build_is_deterministic_and_verifies_git_backed_fixture(tmp_path: Path):
    source_root, database_path = _indexed_fixture(tmp_path)

    first = _build(source_root, database_path)
    second = _build(source_root, database_path)
    report = verify_prepared_cloud_snapshot_bundle(first)

    assert first.bundle_format == BUNDLE_FORMAT
    assert first.source_object.payload == second.source_object.payload
    assert first.index_object.payload == second.index_object.payload
    assert first.attestation_bytes == second.attestation_bytes
    assert first.markdown_inventory_bytes == second.markdown_inventory_bytes
    assert first.source_object.sha256 == second.source_object.sha256
    assert first.index_object.sha256 == second.index_object.sha256
    assert report.e1_legacy_verifier == "verified_with_public_e1_v1_git_state_api"
    assert report.markdown_document_count == 3
    assert report.active_document_count == 3
    assert report.source_file_count == 4
    assert report.schema_info_version == 2


def test_index_bundle_contains_versioned_attestation_and_canonical_inventory(tmp_path: Path):
    source_root, database_path = _indexed_fixture(tmp_path)
    bundle = _build(source_root, database_path)

    members = _zip_members(bundle.index_object.payload)
    attestation = json.loads(members[ATTESTATION_PATH].decode("utf-8"))
    inventory = json.loads(members[INVENTORY_PATH].decode("utf-8"))

    assert set(members) == {ATTESTATION_PATH, INVENTORY_PATH, E1_DATABASE_PATH}
    assert attestation["format"] == E1_CLOUD_INDEX_ATTESTATION_FORMAT
    assert attestation["source_revision"] == {
        "kind": "git_commit", "commit_sha": "a" * 40
    }
    assert attestation["markdown_inventory"]["format"] == MARKDOWN_INVENTORY_FORMAT
    assert attestation["markdown_inventory"]["sha256"] == bundle.markdown_inventory_sha256
    assert attestation["markdown_inventory"]["document_count"] == 3
    assert attestation["sqlite_schema_identity"] == {
        "engine": "sqlite", "schema_info_version": 2
    }
    assert attestation["database"]["path"] == E1_DATABASE_PATH
    assert attestation["database"]["sha256"].startswith("sha256:")
    assert attestation["parser_identities"]
    assert "snapshot_id" not in str(attestation)
    assert "provider" not in attestation
    assert inventory["format"] == MARKDOWN_INVENTORY_FORMAT


def test_import_revision_is_kept_tagged_and_never_coerced_to_git_sha(tmp_path: Path):
    source_root, database_path = _indexed_fixture(tmp_path)
    revision = ImmutableImportSourceRevision("synthetic-import-2026-11-18")
    bundle = _build(source_root, database_path, source_revision=revision)
    report = verify_prepared_cloud_snapshot_bundle(bundle)
    attestation = json.loads(bundle.attestation_bytes.decode("utf-8"))

    assert attestation["source_revision"] == {
        "kind": "immutable_import",
        "import_id": "synthetic-import-2026-11-18",
    }
    assert report.e1_legacy_verifier == "skipped_immutable_import_requires_additive_e1_verifier"
    built = bundle.build_cloud_snapshot_v2(
        source_version_id="synthetic-source-object-version-1",
        index_version_id="synthetic-index-object-version-1",
    )
    assert built.ref.source_revision == revision
    assert built.ref.source_bundle.version_id == "synthetic-source-object-version-1"
    assert built.ref.index_bundle.version_id == "synthetic-index-object-version-1"


def test_build_cloud_snapshot_v2_reverifies_inventory_and_attestation_before_binding_versions(tmp_path: Path):
    source_root, database_path = _indexed_fixture(tmp_path)
    bundle = _build(source_root, database_path)
    forged = replace(bundle, markdown_inventory_sha256="sha256:" + "0" * 64)
    with pytest.raises(BundleIntegrityError, match="inventory"):
        forged.build_cloud_snapshot_v2(
            source_version_id="immutable-source-v1",
            index_version_id="immutable-index-v1",
        )

def test_final_v2_manifest_is_bound_only_after_exact_upload_versions_are_supplied(tmp_path: Path):
    source_root, database_path = _indexed_fixture(tmp_path)
    bundle = _build(source_root, database_path)
    built = bundle.build_cloud_snapshot_v2(
        source_version_id="immutable-source-generation-7",
        index_version_id="immutable-index-generation-9",
    )

    assert built.ref.source_bundle.sha256 == bundle.source_object.sha256
    assert built.ref.source_bundle.byte_size == bundle.source_object.byte_size
    assert built.ref.index_bundle.sha256 == bundle.index_object.sha256
    assert built.ref.index_bundle.byte_size == bundle.index_object.byte_size
    assert built.ref.source_bundle.version_id == "immutable-source-generation-7"
    assert built.ref.index_bundle.version_id == "immutable-index-generation-9"
    assert verify_cloud_snapshot_manifest(built.ref, built.manifest_bytes)


def test_changed_source_bytes_cannot_be_hidden_by_old_index_database(tmp_path: Path):
    source_root, database_path = _indexed_fixture(tmp_path)
    (source_root / "a.md").write_bytes(b"changed bytes\r\n")

    with pytest.raises(BundleIntegrityError, match="document paths|size/hash"):
        _build(source_root, database_path)


def test_corrupt_or_partial_sqlite_is_rejected_before_a_candidate_is_returned(tmp_path: Path):
    pytest.importorskip("sfra_indexer")
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "one.md").write_text("synthetic source", encoding="utf-8")
    corrupt_database = tmp_path / "corrupt.sqlite3"
    corrupt_database.write_bytes(b"not a sqlite database")

    with pytest.raises(BundleIntegrityError):
        _build(source_root, corrupt_database)


def test_tampered_source_archive_fails_inventory_verification(tmp_path: Path):
    source_root, database_path = _indexed_fixture(tmp_path)
    bundle = _build(source_root, database_path)
    members = _zip_members(bundle.source_object.payload)
    members["source/a.md"] = b"tampered but otherwise valid UTF-8\r\n"
    changed_archive = _zip_bytes(members)
    changed_object = _prepared_object(bundle.source_object.key, changed_archive)
    tampered = replace(bundle, source_object=changed_object)

    with pytest.raises(BundleIntegrityError):
        verify_prepared_cloud_snapshot_bundle(tampered)


def test_missing_index_member_fails_closed(tmp_path: Path):
    source_root, database_path = _indexed_fixture(tmp_path)
    bundle = _build(source_root, database_path)
    members = _zip_members(bundle.index_object.payload)
    members.pop(ATTESTATION_PATH)
    changed_archive = _zip_bytes(members)
    tampered = replace(bundle, index_object=_prepared_object(bundle.index_object.key, changed_archive))

    with pytest.raises(BundleIntegrityError, match="missing or unexpected"):
        verify_prepared_cloud_snapshot_bundle(tampered)


def test_tampered_database_and_attestation_fail_before_verification(tmp_path: Path):
    source_root, database_path = _indexed_fixture(tmp_path)
    bundle = _build(source_root, database_path)
    members = _zip_members(bundle.index_object.payload)
    members[E1_DATABASE_PATH] = b"corrupt sqlite bytes"
    changed_archive = _zip_bytes(members)
    tampered = replace(bundle, index_object=_prepared_object(bundle.index_object.key, changed_archive))

    with pytest.raises(BundleIntegrityError):
        verify_prepared_cloud_snapshot_bundle(tampered)


def test_database_inventory_mismatch_is_rejected_when_document_row_is_missing(tmp_path: Path):
    source_root, database_path = _indexed_fixture(tmp_path)
    import sqlite3

    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM documents WHERE source_path = ?", ("nested/b.MD",))
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(BundleIntegrityError, match="foreign_key_check|document paths"):
        _build(source_root, database_path)


def test_source_bundle_preserves_non_markdown_files_without_putting_them_in_inventory(tmp_path: Path):
    source_root, database_path = _indexed_fixture(tmp_path)
    bundle = _build(source_root, database_path)
    members = _zip_members(bundle.source_object.payload)

    assert members["source/asset.bin"] == b"\x00\x01\xffbinary asset"
    assert bundle.markdown_document_count == 3
    assert bundle.source_file_count == 4


def test_bundle_descriptor_payload_hash_and_size_are_rechecked(tmp_path: Path):
    source_root, database_path = _indexed_fixture(tmp_path)
    bundle = _build(source_root, database_path)
    bad_object = replace(bundle.source_object, payload=b"different bytes")

    with pytest.raises(BundleIntegrityError, match="hash/size"):
        verify_prepared_cloud_snapshot_bundle(replace(bundle, source_object=bad_object))


def test_attestation_parser_identity_and_generation_metadata_are_stable(tmp_path: Path):
    source_root, database_path = _indexed_fixture(tmp_path)
    bundle = _build(source_root, database_path)
    attestation = json.loads(bundle.attestation_bytes.decode("utf-8"))

    assert attestation["indexer_identity"] == {
        "name": "sfra-structural-indexer",
        "version": "0.2.0",
    }
    assert attestation["parser_identities"]
    assert attestation["counts"]["active_document_count"] == 3
    assert attestation["counts"]["active_node_count"] > 0
    assert attestation["database"]["byte_size"] > 0


def test_manifest_bytes_tampering_is_detected_by_the_shared_v2_contract(tmp_path: Path):
    source_root, database_path = _indexed_fixture(tmp_path)
    bundle = _build(source_root, database_path)
    built = bundle.build_cloud_snapshot_v2(
        source_version_id="source-v1",
        index_version_id="index-v1",
    )
    tampered = built.manifest_bytes.replace(b"git_commit", b"git_commiX")

    with pytest.raises(CloudSnapshotContractError):
        verify_cloud_snapshot_manifest(built.ref, tampered)


def test_tampered_source_archive_path_traversal_is_rejected(tmp_path: Path):
    from io import BytesIO
    source_root, database_path = _indexed_fixture(tmp_path)
    bundle = _build(source_root, database_path)
    stream = BytesIO()
    with zipfile.ZipFile(stream, mode="w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("source/../escape.md", b"outside")
    malicious_payload = stream.getvalue()
    tampered = replace(
        bundle,
        source_object=_prepared_object(bundle.source_object.key, malicious_payload),
    )
    with pytest.raises(BundleIntegrityError, match="unsafe archive path"):
        verify_prepared_cloud_snapshot_bundle(tampered)


def test_verifier_rechecks_sqlite_identity_fields_on_prepared_descriptor(tmp_path: Path):
    source_root, database_path = _indexed_fixture(tmp_path)
    bundle = _build(source_root, database_path)
    forged_identity = object.__new__(SqliteSchemaIdentity)
    object.__setattr__(forged_identity, "engine", "not-sqlite")
    object.__setattr__(forged_identity, "schema_info_version", 2)
    forged = replace(bundle, sqlite_schema_identity=forged_identity)
    with pytest.raises(BundleIntegrityError, match="sqlite_schema_identity"):
        verify_prepared_cloud_snapshot_bundle(forged)


@pytest.mark.parametrize(
    "compression",
    [
        pytest.param(zipfile.ZIP_DEFLATED, id="deflated"),
        pytest.param(zipfile.ZIP_BZIP2, id="bzip2"),
        pytest.param(zipfile.ZIP_LZMA, id="lzma"),
    ],
)
def test_deterministic_zip_reader_rejects_compression_before_member_read(
    compression: int,
    monkeypatch: pytest.MonkeyPatch,
):
    from io import BytesIO

    stream = BytesIO()
    with zipfile.ZipFile(stream, mode="w", compression=compression) as archive:
        archive.writestr("source/a.md", b"synthetic payload " * 32)
    payload = stream.getvalue()

    def fail_if_payload_is_read(*args, **kwargs):
        pytest.fail("compressed member payload was read before its compression type was rejected")

    monkeypatch.setattr(zipfile.ZipFile, "read", fail_if_payload_is_read)

    with pytest.raises(BundleIntegrityError, match="unsupported compressed archive member"):
        _read_deterministic_zip(payload, "synthetic source bundle")


def test_deterministic_zip_reader_rejects_stored_size_mismatch_before_member_read(
    monkeypatch: pytest.MonkeyPatch,
):
    from io import BytesIO

    payload = _zip_bytes({"source/a.md": b"synthetic stored payload"})
    original_infolist = zipfile.ZipFile.infolist

    def report_mismatched_stored_size(archive: zipfile.ZipFile):
        infos = original_infolist(archive)
        infos[0].compress_size += 1
        return infos

    def fail_if_payload_is_read(*args, **kwargs):
        pytest.fail("stored member payload was read before its size metadata was rejected")

    monkeypatch.setattr(zipfile.ZipFile, "infolist", report_mismatched_stored_size)
    monkeypatch.setattr(zipfile.ZipFile, "read", fail_if_payload_is_read)

    with pytest.raises(BundleIntegrityError, match="stored member size"):
        _read_deterministic_zip(payload, "synthetic source bundle")


def test_deterministic_zip_reader_accepts_valid_stored_members():
    expected = {"source/a.md": b"synthetic stored payload", "source/empty.md": b""}
    payload = _zip_bytes(expected)

    assert _read_deterministic_zip(payload, "synthetic source bundle") == expected
