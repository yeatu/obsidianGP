from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from sfra_context_integrations.cloud_snapshot_v2 import (
    CloudSnapshotContractError,
    CloudSnapshotManifestV1,
    GitCommitSourceRevision,
    ImmutableImportSourceRevision,
    ImmutableObjectVersion,
    IndexerIdentity,
    SqliteSchemaIdentity,
    build_cloud_snapshot_v2,
    cloud_snapshot_manifest_from_dict,
    cloud_snapshot_ref_v2_from_dict,
    parse_canonical_cloud_snapshot_manifest,
    serialize_cloud_snapshot_manifest,
    verify_cloud_snapshot_manifest,
)


def _object(key: str, version: str, content: bytes) -> ImmutableObjectVersion:
    return ImmutableObjectVersion(
        key=key,
        version_id=version,
        sha256="sha256:" + hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
    )


def _manifest(*, source_revision=None, index_version="idx-v4", schema_info_version=2):
    return CloudSnapshotManifestV1(
        source_revision=source_revision or GitCommitSourceRevision("a" * 40),
        source_bundle=_object("snapshots/source.tar", "src-ver-01", b"synthetic source archive"),
        index_bundle=_object("snapshots/index.sqlite3", "idx-ver-01", b"synthetic sqlite bundle"),
        indexer_identity=IndexerIdentity(name="sfra-indexer", version=index_version),
        sqlite_schema_identity=SqliteSchemaIdentity(
            engine="sqlite", schema_info_version=schema_info_version
        ),
    )


def test_canonical_manifest_bytes_are_stable_and_utf8() -> None:
    manifest = _manifest()
    first = serialize_cloud_snapshot_manifest(manifest)
    second = serialize_cloud_snapshot_manifest(manifest)

    assert first == second
    assert first.startswith(b'{"index_bundle":')
    assert "source_revision".encode() in first
    assert b"\n" not in first
    assert parse_canonical_cloud_snapshot_manifest(first) == manifest


def test_builds_deterministic_snapshot_id_and_round_trips_reference() -> None:
    built_a = build_cloud_snapshot_v2(_manifest())
    built_b = build_cloud_snapshot_v2(_manifest())

    assert built_a.manifest_bytes == built_b.manifest_bytes
    assert built_a.ref == built_b.ref
    assert built_a.ref.snapshot_schema_version == 2
    assert built_a.ref.snapshot_id.startswith("sha256:")
    assert cloud_snapshot_ref_v2_from_dict(built_a.ref.to_dict()) == built_a.ref
    assert verify_cloud_snapshot_manifest(built_a.ref, built_a.manifest_bytes) == _manifest()


@pytest.mark.parametrize(
    "change",
    [
        lambda m: _manifest(source_revision=GitCommitSourceRevision("b" * 40)),
        lambda m: _manifest(
            source_revision=ImmutableImportSourceRevision("vault-import-2026-001")
        ),
        lambda m: replace(
            m,
            source_bundle=replace(m.source_bundle, key="snapshots/source-v2.tar"),
        ),
        lambda m: CloudSnapshotManifestV1(
            source_revision=m.source_revision,
            source_bundle=_object("snapshots/source.tar", "src-ver-02", b"synthetic source archive"),
            index_bundle=m.index_bundle,
            indexer_identity=m.indexer_identity,
            sqlite_schema_identity=m.sqlite_schema_identity,
        ),
        lambda m: CloudSnapshotManifestV1(
            source_revision=m.source_revision,
            source_bundle=_object("snapshots/source.tar", "src-ver-01", b"different source bytes"),
            index_bundle=m.index_bundle,
            indexer_identity=m.indexer_identity,
            sqlite_schema_identity=m.sqlite_schema_identity,
        ),
        lambda m: replace(
            m,
            source_bundle=replace(m.source_bundle, byte_size=m.source_bundle.byte_size + 1),
        ),
        lambda m: replace(
            m,
            index_bundle=replace(m.index_bundle, key="snapshots/index-v2.sqlite3"),
        ),
        lambda m: CloudSnapshotManifestV1(
            source_revision=m.source_revision,
            source_bundle=m.source_bundle,
            index_bundle=_object("snapshots/index.sqlite3", "idx-ver-02", b"synthetic sqlite bundle"),
            indexer_identity=m.indexer_identity,
            sqlite_schema_identity=m.sqlite_schema_identity,
        ),
        lambda m: CloudSnapshotManifestV1(
            source_revision=m.source_revision,
            source_bundle=m.source_bundle,
            index_bundle=_object("snapshots/index.sqlite3", "idx-ver-01", b"different sqlite bytes"),
            indexer_identity=m.indexer_identity,
            sqlite_schema_identity=m.sqlite_schema_identity,
        ),
        lambda m: replace(
            m,
            index_bundle=replace(m.index_bundle, byte_size=m.index_bundle.byte_size + 1),
        ),
        lambda m: CloudSnapshotManifestV1(
            source_revision=m.source_revision,
            source_bundle=m.source_bundle,
            index_bundle=m.index_bundle,
            indexer_identity=IndexerIdentity("sfra-indexer", "idx-v5"),
            sqlite_schema_identity=m.sqlite_schema_identity,
        ),
        lambda m: CloudSnapshotManifestV1(
            source_revision=m.source_revision,
            source_bundle=m.source_bundle,
            index_bundle=m.index_bundle,
            indexer_identity=m.indexer_identity,
            sqlite_schema_identity=SqliteSchemaIdentity("sqlite", 3),
        ),
    ],
)
def test_any_identity_component_change_changes_snapshot_id(change) -> None:
    original = build_cloud_snapshot_v2(_manifest()).ref
    changed = build_cloud_snapshot_v2(change(_manifest())).ref

    assert changed.snapshot_id != original.snapshot_id


def test_manifest_sha256_binds_exact_canonical_bytes() -> None:
    built = build_cloud_snapshot_v2(_manifest())

    with pytest.raises(CloudSnapshotContractError, match="SHA-256"):
        verify_cloud_snapshot_manifest(built.ref, built.manifest_bytes + b" ")


def test_manifest_identity_must_match_reference_even_with_valid_new_digest() -> None:
    built = build_cloud_snapshot_v2(_manifest())
    different = serialize_cloud_snapshot_manifest(_manifest(index_version="idx-v5"))

    # Forge an internally self-consistent v2 identity tuple while retaining the
    # original manifest digest. The ref parser accepts its recomputed ID, but
    # manifest verification must detect the mismatch between tuple and bytes.
    mapping = built.ref.to_dict()
    mapping["indexer_identity"]["version"] = "idx-v5"
    identity_payload = dict(mapping)
    identity_payload.pop("snapshot_id")
    encoded = json.dumps(
        identity_payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    mapping["snapshot_id"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    forged_ref = cloud_snapshot_ref_v2_from_dict(mapping)

    with pytest.raises(CloudSnapshotContractError, match="identity does not match"):
        verify_cloud_snapshot_manifest(forged_ref, built.manifest_bytes)

    with pytest.raises(CloudSnapshotContractError, match="SHA-256"):
        verify_cloud_snapshot_manifest(built.ref, different)


def test_duplicate_json_keys_are_rejected() -> None:
    raw = (
        b'{"manifest_schema_version":1,"manifest_schema_version":1,'
        b'"source_revision":{"kind":"git_commit","commit_sha":"' + b"a" * 40 + b'"},'
        b'"source_bundle":{},"index_bundle":{},"indexer_identity":{},'
        b'"sqlite_schema_identity":{}}'
    )
    with pytest.raises(CloudSnapshotContractError, match="duplicate"):
        parse_canonical_cloud_snapshot_manifest(raw)


def test_non_canonical_json_is_rejected_even_when_semantically_equivalent() -> None:
    canonical = serialize_cloud_snapshot_manifest(_manifest())
    non_canonical = json.dumps(json.loads(canonical), ensure_ascii=False, indent=2).encode()

    with pytest.raises(CloudSnapshotContractError, match="not canonical"):
        parse_canonical_cloud_snapshot_manifest(non_canonical)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda d: d.update(manifest_sha256="sha256:" + "0" * 64), "unsupported field"),
        (lambda d: d.update(snapshot_id="sha256:" + "0" * 64), "unsupported field"),
        (lambda d: d.update(manifest_schema_version=2), "unsupported manifest_schema_version"),
        (lambda d: d.update(extra="x"), "unsupported field"),
        (lambda d: d.pop("source_bundle"), "missing required field"),
    ],
)
def test_manifest_rejects_self_reference_unknown_or_incomplete_fields(mutate, message) -> None:
    data = _manifest().to_dict()
    mutate(data)

    with pytest.raises(CloudSnapshotContractError, match=message):
        cloud_snapshot_manifest_from_dict(data)


@pytest.mark.parametrize(
    "revision",
    [
        {"kind": "git_commit", "commit_sha": "A" * 40},
        {"kind": "git_commit", "commit_sha": "a" * 39},
        {"kind": "immutable_import", "import_id": ""},
        {"kind": "immutable_import", "import_id": "latest"},
        {"kind": "other", "value": "x"},
        {"kind": "git_commit", "commit_sha": "a" * 40, "extra": "x"},
    ],
)
def test_source_revision_variants_are_strict(revision) -> None:
    data = _manifest().to_dict()
    data["source_revision"] = revision

    with pytest.raises(CloudSnapshotContractError):
        cloud_snapshot_manifest_from_dict(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("version_id", "latest"),
        ("version_id", "current"),
        ("version_id", ""),
        ("sha256", "sha256:" + "A" * 64),
        ("sha256", "sha256:" + "a" * 63),
        ("byte_size", 0),
        ("byte_size", True),
        ("key", ""),
    ],
)
def test_immutable_object_identity_rejects_mutable_or_invalid_values(field, value) -> None:
    values = {
        "key": "objects/source.tar",
        "version_id": "version-1",
        "sha256": "sha256:" + "b" * 64,
        "byte_size": 12,
    }
    values[field] = value

    with pytest.raises(CloudSnapshotContractError):
        ImmutableObjectVersion(**values)


def test_indexer_and_sqlite_schema_identity_are_required_and_typed() -> None:
    with pytest.raises(CloudSnapshotContractError, match="indexer_identity.version"):
        IndexerIdentity("sfra-indexer", "")
    with pytest.raises(CloudSnapshotContractError, match="engine"):
        SqliteSchemaIdentity("postgres", 1)
    with pytest.raises(CloudSnapshotContractError, match="positive integer"):
        SqliteSchemaIdentity("sqlite", True)


def test_sqlite_schema_identity_binds_e1_schema_info_version_and_snapshot_id() -> None:
    base = build_cloud_snapshot_v2(_manifest(schema_info_version=2)).ref
    changed = build_cloud_snapshot_v2(_manifest(schema_info_version=3)).ref

    expected = {"engine": "sqlite", "schema_info_version": 2}
    assert base.sqlite_schema_identity.to_dict() == expected
    assert base.identity_dict()["sqlite_schema_identity"] == expected
    assert base.to_dict()["sqlite_schema_identity"] == expected
    assert changed.snapshot_id != base.snapshot_id


def test_legacy_user_version_field_is_rejected_by_manifest_and_ref_parser() -> None:
    manifest_data = _manifest().to_dict()
    manifest_identity = manifest_data["sqlite_schema_identity"]
    manifest_identity["user_version"] = manifest_identity["schema_info_version"]
    with pytest.raises(CloudSnapshotContractError, match="unsupported field"):
        cloud_snapshot_manifest_from_dict(manifest_data)

    ref_data = build_cloud_snapshot_v2(_manifest()).ref.to_dict()
    ref_identity = ref_data["sqlite_schema_identity"]
    ref_identity["user_version"] = ref_identity["schema_info_version"]
    with pytest.raises(CloudSnapshotContractError, match="unsupported field"):
        cloud_snapshot_ref_v2_from_dict(ref_data)


def test_snapshot_reference_rejects_unknown_fields_and_forged_id() -> None:
    built = build_cloud_snapshot_v2(_manifest())
    mapping = built.ref.to_dict()
    mapping["latest"] = True
    with pytest.raises(CloudSnapshotContractError, match="unsupported field"):
        cloud_snapshot_ref_v2_from_dict(mapping)

    mapping = built.ref.to_dict()
    mapping["snapshot_id"] = "sha256:" + "0" * 64
    with pytest.raises(CloudSnapshotContractError, match="snapshot_id"):
        cloud_snapshot_ref_v2_from_dict(mapping)


def test_import_revision_is_a_valid_v2_identity_but_not_a_v1_git_sha() -> None:
    manifest = _manifest(
        source_revision=ImmutableImportSourceRevision("vault-import:2026-11-18:0001")
    )
    built = build_cloud_snapshot_v2(manifest)

    assert built.ref.source_revision == manifest.source_revision
    assert built.ref.to_dict()["source_revision"] == {
        "kind": "immutable_import",
        "import_id": "vault-import:2026-11-18:0001",
    }


def test_manifest_parser_rejects_invalid_utf8_and_json_constants() -> None:
    with pytest.raises(CloudSnapshotContractError, match="UTF-8 JSON"):
        parse_canonical_cloud_snapshot_manifest(b"\xff")
    with pytest.raises(CloudSnapshotContractError, match="unsupported JSON constant"):
        parse_canonical_cloud_snapshot_manifest(b'{"value":NaN}')


def test_manifest_size_bound_is_enforced() -> None:
    with pytest.raises(CloudSnapshotContractError, match="byte length"):
        parse_canonical_cloud_snapshot_manifest(b" " * (2 * 1024 * 1024 + 1))

def test_published_json_schemas_are_versioned_and_closed() -> None:
    schema_dir = Path(__file__).resolve().parents[1] / "schemas"
    manifest_schema = json.loads(
        (schema_dir / "cloud-snapshot-manifest-v1.schema.json").read_text(encoding="utf-8")
    )
    ref_schema = json.loads(
        (schema_dir / "cloud-snapshot-ref-v2.schema.json").read_text(encoding="utf-8")
    )

    assert manifest_schema["$schema"].endswith("/2020-12/schema")
    assert manifest_schema["properties"]["manifest_schema_version"]["const"] == 1
    assert manifest_schema["additionalProperties"] is False
    assert set(manifest_schema["required"]) == {
        "manifest_schema_version", "source_revision", "source_bundle",
        "index_bundle", "indexer_identity", "sqlite_schema_identity",
    }
    assert manifest_schema["properties"]["source_revision"]["oneOf"]
    for name in ("source_bundle", "index_bundle"):
        object_schema = manifest_schema["$defs"]["immutableObjectVersion"]
        assert object_schema["additionalProperties"] is False
        assert set(object_schema["required"]) == {"key", "version_id", "sha256", "byte_size"}
        assert object_schema["properties"]["byte_size"]["minimum"] == 1
    assert manifest_schema["properties"]["sqlite_schema_identity"]["properties"]["engine"]["const"] == "sqlite"
    for schema in (manifest_schema, ref_schema):
        sqlite_identity_schema = schema["properties"]["sqlite_schema_identity"]
        assert sqlite_identity_schema["required"] == ["engine", "schema_info_version"]
        assert sqlite_identity_schema["properties"]["schema_info_version"]["type"] == "integer"
        assert sqlite_identity_schema["properties"]["schema_info_version"]["minimum"] == 1
        assert "user_version" not in sqlite_identity_schema["properties"]

    assert ref_schema["$schema"].endswith("/2020-12/schema")
    assert ref_schema["properties"]["snapshot_schema_version"]["const"] == 2
    assert ref_schema["additionalProperties"] is False
    assert "manifest_sha256" in ref_schema["required"]
    assert ref_schema["properties"]["snapshot_id"]["$ref"] == "#/$defs/sha256"


def test_published_schemas_reject_legacy_user_version_property():
    from copy import deepcopy
    from jsonschema import Draft202012Validator

    schema_dir = Path(__file__).resolve().parents[1] / "schemas"
    manifest_schema = json.loads(
        (schema_dir / "cloud-snapshot-manifest-v1.schema.json").read_text(encoding="utf-8")
    )
    ref_schema = json.loads(
        (schema_dir / "cloud-snapshot-ref-v2.schema.json").read_text(encoding="utf-8")
    )
    manifest_validator = Draft202012Validator(manifest_schema)
    ref_validator = Draft202012Validator(ref_schema)
    git_manifest, _, git_ref, _ = _schema_instances()

    old_manifest = deepcopy(git_manifest)
    identity = old_manifest["sqlite_schema_identity"]
    identity["user_version"] = identity["schema_info_version"]
    assert not manifest_validator.is_valid(old_manifest)

    old_ref = deepcopy(git_ref)
    identity = old_ref["sqlite_schema_identity"]
    identity["user_version"] = identity.pop("schema_info_version")
    assert not ref_validator.is_valid(old_ref)


def _schema_instances():
    """Build structurally valid examples through the public Python contract."""
    from sfra_context_integrations.cloud_snapshot_v2 import build_cloud_snapshot_v2

    git_manifest = _manifest().to_dict()
    import_manifest = _manifest(
        source_revision=ImmutableImportSourceRevision("vault-import:2026-11-18:0001")
    ).to_dict()
    git_ref = build_cloud_snapshot_v2(_manifest()).ref.to_dict()
    import_ref = build_cloud_snapshot_v2(
        _manifest(
            source_revision=ImmutableImportSourceRevision("vault-import:2026-11-18:0001")
        )
    ).ref.to_dict()
    return git_manifest, import_manifest, git_ref, import_ref


def test_published_schemas_pass_draft_2020_12_and_validate_both_revision_variants():
    from jsonschema import Draft202012Validator, FormatChecker

    schema_dir = Path(__file__).resolve().parents[1] / "schemas"
    manifest_schema = json.loads(
        (schema_dir / "cloud-snapshot-manifest-v1.schema.json").read_text(encoding="utf-8")
    )
    ref_schema = json.loads(
        (schema_dir / "cloud-snapshot-ref-v2.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(manifest_schema)
    Draft202012Validator.check_schema(ref_schema)
    manifest_validator = Draft202012Validator(manifest_schema, format_checker=FormatChecker())
    ref_validator = Draft202012Validator(ref_schema, format_checker=FormatChecker())

    git_manifest, import_manifest, git_ref, import_ref = _schema_instances()
    assert manifest_validator.is_valid(git_manifest)
    assert manifest_validator.is_valid(import_manifest)
    assert ref_validator.is_valid(git_ref)
    assert ref_validator.is_valid(import_ref)

    bad_manifest = dict(git_manifest)
    bad_manifest["unexpected"] = True
    assert not manifest_validator.is_valid(bad_manifest)
    bad_ref = dict(git_ref)
    bad_ref["unexpected"] = True
    assert not ref_validator.is_valid(bad_ref)


@pytest.mark.parametrize(
    "identifier",
    [
        "latest", "LATEST", "current", "CURRENT", "head", "HEAD", "*",
        " latest ", "CURRENT ", " Head ", " * ", " ", "\tversion", "version\n",
    ],
)
def test_schemas_reject_mutable_aliases_and_surrounding_whitespace(identifier):
    from copy import deepcopy
    from jsonschema import Draft202012Validator

    schema_dir = Path(__file__).resolve().parents[1] / "schemas"
    manifest_schema = json.loads(
        (schema_dir / "cloud-snapshot-manifest-v1.schema.json").read_text(encoding="utf-8")
    )
    ref_schema = json.loads(
        (schema_dir / "cloud-snapshot-ref-v2.schema.json").read_text(encoding="utf-8")
    )
    manifest_validator = Draft202012Validator(manifest_schema)
    ref_validator = Draft202012Validator(ref_schema)
    git_manifest, _, git_ref, _ = _schema_instances()

    for field in ("source_bundle", "index_bundle"):
        candidate = deepcopy(git_manifest)
        candidate[field]["version_id"] = identifier
        assert not manifest_validator.is_valid(candidate), (field, identifier)
        candidate_ref = deepcopy(git_ref)
        candidate_ref[field]["version_id"] = identifier
        assert not ref_validator.is_valid(candidate_ref), (field, identifier)

    candidate = deepcopy(git_manifest)
    candidate["source_revision"] = {"kind": "immutable_import", "import_id": identifier}
    assert not manifest_validator.is_valid(candidate), identifier
    candidate_ref = deepcopy(git_ref)
    candidate_ref["source_revision"] = {"kind": "immutable_import", "import_id": identifier}
    assert not ref_validator.is_valid(candidate_ref), identifier


@pytest.mark.parametrize(
    "identifier",
    [
        "latest", "LATEST", "current", "CURRENT", "head", "HEAD", "*",
        " latest ", "CURRENT ", " Head ", " * ", "\tversion", "version\n",
        "\u0085version", "version\u0085", "\u00a0version", "version\u3000",
    ],
)
def test_runtime_rejects_mutable_aliases_and_surrounding_whitespace(identifier):
    with pytest.raises(CloudSnapshotContractError):
        ImmutableObjectVersion(
            key="objects/source.tar",
            version_id=identifier,
            sha256="sha256:" + "a" * 64,
            byte_size=1,
        )
    with pytest.raises(CloudSnapshotContractError):
        ImmutableImportSourceRevision(identifier)


def test_opaque_immutable_identifiers_are_preserved_without_trimming():
    version_id = "release 17 / provider-generation:ABC-17"
    import_id = "customer import #17"
    obj = ImmutableObjectVersion(
        key="objects/source.tar",
        version_id=version_id,
        sha256="sha256:" + "a" * 64,
        byte_size=1,
    )
    revision = ImmutableImportSourceRevision(import_id)

    assert obj.version_id == version_id
    assert obj.to_dict()["version_id"] == version_id
    assert revision.import_id == import_id
    assert revision.to_dict()["import_id"] == import_id


@pytest.mark.parametrize("identifier", ["e\u0301", "version\u0001id"])
def test_json_schema_is_structural_preflight_while_runtime_enforces_unicode_rules(identifier):
    from jsonschema import Draft202012Validator

    schema_dir = Path(__file__).resolve().parents[1] / "schemas"
    manifest_schema = json.loads(
        (schema_dir / "cloud-snapshot-manifest-v1.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(manifest_schema)
    manifest = _manifest().to_dict()
    manifest["source_bundle"]["version_id"] = identifier

    # Portable JSON Schema checks structure and immutable identifier boundaries,
    # but Unicode NFC and control/surrogate categories remain Python-runtime rules.
    assert validator.is_valid(manifest)
    with pytest.raises(CloudSnapshotContractError):
        ImmutableObjectVersion(
            key="objects/source.tar",
            version_id=identifier,
            sha256="sha256:" + "a" * 64,
            byte_size=1,
        )
