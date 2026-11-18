"""Provider-neutral, additive cloud SnapshotRef v2 contract.

This module is intentionally separate from snapshot.py and the legacy
sfra_context_builder.models.SnapshotRef contract. It performs no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from typing import Any, TypeAlias


SNAPSHOT_SCHEMA_VERSION = 2
MANIFEST_SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 2 * 1024 * 1024

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_MUTABLE_VERSION_ALIASES = frozenset({"latest", "current", "head", "*"})


class CloudSnapshotContractError(ValueError):
    """Raised when a v2 reference or canonical manifest is invalid."""


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or not value.strip():
        raise CloudSnapshotContractError(f"{name} must be a non-empty string")
    if len(value) > 4096:
        raise CloudSnapshotContractError(f"{name} exceeds the 4096-character limit")
    if value != unicodedata.normalize("NFC", value):
        raise CloudSnapshotContractError(f"{name} must use Unicode NFC normalization")
    if any(unicodedata.category(char) in {"Cc", "Cs"} for char in value):
        raise CloudSnapshotContractError(f"{name} contains a control or surrogate character")
    return value

def _immutable_identifier(value: Any, name: str) -> str:
    """Validate an opaque immutable ID without normalizing the provider value."""
    identifier = _text(value, name)
    if identifier != identifier.strip():
        raise CloudSnapshotContractError(
            f"{name} must not have leading or trailing whitespace"
        )
    if identifier.casefold() in _MUTABLE_VERSION_ALIASES:
        raise CloudSnapshotContractError(f"{name} must be immutable, not a mutable alias")
    return identifier


def _sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise CloudSnapshotContractError(f"{name} must be lowercase sha256:<64 hex>")
    return value


def _git_sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _GIT_SHA_RE.fullmatch(value):
        raise CloudSnapshotContractError(f"{name} must be a lowercase 40-character Git SHA")
    return value


def _positive_int(value: Any, name: str) -> int:
    # bool is an int subclass; exact type checking is intentional.
    if type(value) is not int or value <= 0:
        raise CloudSnapshotContractError(f"{name} must be a positive integer")
    return value


def _exact_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] | None = None,
    name: str,
) -> None:
    optional = optional or set()
    keys = set(value)
    missing = required - keys
    unknown = keys - required - optional
    if missing:
        raise CloudSnapshotContractError(
            f"{name} is missing required field(s): {', '.join(sorted(missing))}"
        )
    if unknown:
        raise CloudSnapshotContractError(
            f"{name} contains unsupported field(s): {', '.join(sorted(unknown))}"
        )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CloudSnapshotContractError(f"{name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise CloudSnapshotContractError(f"{name} keys must be strings")
    return value


@dataclass(frozen=True, slots=True)
class GitCommitSourceRevision:
    """Source revision whose identity is an exact Git commit SHA."""

    commit_sha: str

    def __post_init__(self) -> None:
        _git_sha(self.commit_sha, "source_revision.commit_sha")

    def to_dict(self) -> dict[str, str]:
        return {"kind": "git_commit", "commit_sha": self.commit_sha}


@dataclass(frozen=True, slots=True)
class ImmutableImportSourceRevision:
    """Source revision identified by an immutable import ID, not a Git SHA."""

    import_id: str

    def __post_init__(self) -> None:
        _immutable_identifier(self.import_id, "source_revision.import_id")

    def to_dict(self) -> dict[str, str]:
        return {"kind": "immutable_import", "import_id": self.import_id}


SourceRevision: TypeAlias = GitCommitSourceRevision | ImmutableImportSourceRevision


def _source_revision(value: Any) -> SourceRevision:
    obj = _mapping(value, "source_revision")
    kind = obj.get("kind")
    if kind == "git_commit":
        _exact_keys(obj, required={"kind", "commit_sha"}, name="source_revision")
        return GitCommitSourceRevision(commit_sha=obj["commit_sha"])
    if kind == "immutable_import":
        _exact_keys(obj, required={"kind", "import_id"}, name="source_revision")
        return ImmutableImportSourceRevision(import_id=obj["import_id"])
    raise CloudSnapshotContractError(
        "source_revision.kind must be 'git_commit' or 'immutable_import'"
    )


@dataclass(frozen=True, slots=True)
class ImmutableObjectVersion:
    """Exact immutable object identity; version_id is never a Git SHA."""

    key: str
    version_id: str
    sha256: str
    byte_size: int

    def __post_init__(self) -> None:
        _text(self.key, "object.key")
        _immutable_identifier(self.version_id, "object.version_id")
        _sha256(self.sha256, "object.sha256")
        _positive_int(self.byte_size, "object.byte_size")

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "version_id": self.version_id,
            "sha256": self.sha256,
            "byte_size": self.byte_size,
        }


def _object_version(value: Any, name: str) -> ImmutableObjectVersion:
    obj = _mapping(value, name)
    _exact_keys(
        obj,
        required={"key", "version_id", "sha256", "byte_size"},
        name=name,
    )
    return ImmutableObjectVersion(
        key=obj["key"],
        version_id=obj["version_id"],
        sha256=obj["sha256"],
        byte_size=obj["byte_size"],
    )


@dataclass(frozen=True, slots=True)
class IndexerIdentity:
    """Identity of the index-producing implementation."""

    name: str
    version: str

    def __post_init__(self) -> None:
        _text(self.name, "indexer_identity.name")
        _text(self.version, "indexer_identity.version")

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "version": self.version}


def _indexer_identity(value: Any) -> IndexerIdentity:
    obj = _mapping(value, "indexer_identity")
    _exact_keys(obj, required={"name", "version"}, name="indexer_identity")
    return IndexerIdentity(name=obj["name"], version=obj["version"])


@dataclass(frozen=True, slots=True)
class SqliteSchemaIdentity:
    """SQLite file format/schema identity; independent of object-store version."""

    engine: str
    user_version: int

    def __post_init__(self) -> None:
        if self.engine != "sqlite":
            raise CloudSnapshotContractError("sqlite_schema_identity.engine must be 'sqlite'")
        _positive_int(self.user_version, "sqlite_schema_identity.user_version")

    def to_dict(self) -> dict[str, Any]:
        return {"engine": self.engine, "user_version": self.user_version}


def _sqlite_schema_identity(value: Any) -> SqliteSchemaIdentity:
    obj = _mapping(value, "sqlite_schema_identity")
    _exact_keys(
        obj,
        required={"engine", "user_version"},
        name="sqlite_schema_identity",
    )
    return SqliteSchemaIdentity(engine=obj["engine"], user_version=obj["user_version"])


@dataclass(frozen=True, slots=True)
class CloudSnapshotManifestV1:
    """Canonical manifest payload. Its digest is detached and not self-referential."""

    source_revision: SourceRevision
    source_bundle: ImmutableObjectVersion
    index_bundle: ImmutableObjectVersion
    indexer_identity: IndexerIdentity
    sqlite_schema_identity: SqliteSchemaIdentity
    manifest_schema_version: int = MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.manifest_schema_version) is not int or (
            self.manifest_schema_version != MANIFEST_SCHEMA_VERSION
        ):
            raise CloudSnapshotContractError("unsupported manifest_schema_version")
        if type(self.source_revision) not in (
            GitCommitSourceRevision,
            ImmutableImportSourceRevision,
        ):
            raise CloudSnapshotContractError("source_revision has an unsupported variant")
        if type(self.source_bundle) is not ImmutableObjectVersion:
            raise CloudSnapshotContractError("source_bundle must be ImmutableObjectVersion")
        if type(self.index_bundle) is not ImmutableObjectVersion:
            raise CloudSnapshotContractError("index_bundle must be ImmutableObjectVersion")
        if type(self.indexer_identity) is not IndexerIdentity:
            raise CloudSnapshotContractError("indexer_identity must be IndexerIdentity")
        if type(self.sqlite_schema_identity) is not SqliteSchemaIdentity:
            raise CloudSnapshotContractError(
                "sqlite_schema_identity must be SqliteSchemaIdentity"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_schema_version": self.manifest_schema_version,
            "source_revision": self.source_revision.to_dict(),
            "source_bundle": self.source_bundle.to_dict(),
            "index_bundle": self.index_bundle.to_dict(),
            "indexer_identity": self.indexer_identity.to_dict(),
            "sqlite_schema_identity": self.sqlite_schema_identity.to_dict(),
        }


def cloud_snapshot_manifest_from_dict(value: Any) -> CloudSnapshotManifestV1:
    obj = _mapping(value, "manifest")
    _exact_keys(
        obj,
        required={
            "manifest_schema_version",
            "source_revision",
            "source_bundle",
            "index_bundle",
            "indexer_identity",
            "sqlite_schema_identity",
        },
        name="manifest",
    )
    return CloudSnapshotManifestV1(
        manifest_schema_version=obj["manifest_schema_version"],
        source_revision=_source_revision(obj["source_revision"]),
        source_bundle=_object_version(obj["source_bundle"], "source_bundle"),
        index_bundle=_object_version(obj["index_bundle"], "index_bundle"),
        indexer_identity=_indexer_identity(obj["indexer_identity"]),
        sqlite_schema_identity=_sqlite_schema_identity(obj["sqlite_schema_identity"]),
    )


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise CloudSnapshotContractError("value cannot be canonically encoded as UTF-8 JSON") from exc


def serialize_cloud_snapshot_manifest(manifest: CloudSnapshotManifestV1) -> bytes:
    if type(manifest) is not CloudSnapshotManifestV1:
        raise CloudSnapshotContractError("manifest must be CloudSnapshotManifestV1")
    return _canonical_json_bytes(manifest.to_dict())


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CloudSnapshotContractError("manifest contains a duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise CloudSnapshotContractError(f"manifest contains unsupported JSON constant {value}")


def parse_canonical_cloud_snapshot_manifest(
    raw_bytes: bytes,
    *,
    expected_sha256: str | None = None,
) -> CloudSnapshotManifestV1:
    """Parse canonical UTF-8 bytes, reject duplicate keys, and verify exact bytes."""
    if not isinstance(raw_bytes, bytes):
        raise CloudSnapshotContractError("manifest bytes must be bytes")
    if not raw_bytes or len(raw_bytes) > MAX_MANIFEST_BYTES:
        raise CloudSnapshotContractError("manifest byte length is invalid")
    actual_digest = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
    if expected_sha256 is not None and actual_digest != _sha256(
        expected_sha256, "expected manifest SHA-256"
    ):
        raise CloudSnapshotContractError("manifest SHA-256 does not match exact bytes")

    try:
        text = raw_bytes.decode("utf-8", errors="strict")
        parsed = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except CloudSnapshotContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CloudSnapshotContractError("manifest is not valid UTF-8 JSON") from exc

    manifest = cloud_snapshot_manifest_from_dict(parsed)
    if serialize_cloud_snapshot_manifest(manifest) != raw_bytes:
        raise CloudSnapshotContractError("manifest bytes are valid JSON but not canonical")
    return manifest


def _identity_payload(
    *,
    source_revision: SourceRevision,
    source_bundle: ImmutableObjectVersion,
    index_bundle: ImmutableObjectVersion,
    manifest_sha256: str,
    indexer_identity: IndexerIdentity,
    sqlite_schema_identity: SqliteSchemaIdentity,
) -> dict[str, Any]:
    return {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "source_revision": source_revision.to_dict(),
        "source_bundle": source_bundle.to_dict(),
        "index_bundle": index_bundle.to_dict(),
        "manifest_sha256": manifest_sha256,
        "indexer_identity": indexer_identity.to_dict(),
        "sqlite_schema_identity": sqlite_schema_identity.to_dict(),
    }


def _derive_snapshot_id(payload: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class CloudSnapshotRefV2:
    """Immutable cloud identity, distinct from the Git-checkout SnapshotRef v1."""

    source_revision: SourceRevision
    source_bundle: ImmutableObjectVersion
    index_bundle: ImmutableObjectVersion
    manifest_sha256: str
    indexer_identity: IndexerIdentity
    sqlite_schema_identity: SqliteSchemaIdentity
    snapshot_id: str
    snapshot_schema_version: int = SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.snapshot_schema_version) is not int or (
            self.snapshot_schema_version != SNAPSHOT_SCHEMA_VERSION
        ):
            raise CloudSnapshotContractError("unsupported snapshot_schema_version")
        if type(self.source_revision) not in (
            GitCommitSourceRevision,
            ImmutableImportSourceRevision,
        ):
            raise CloudSnapshotContractError("source_revision has an unsupported variant")
        if type(self.source_bundle) is not ImmutableObjectVersion:
            raise CloudSnapshotContractError("source_bundle must be ImmutableObjectVersion")
        if type(self.index_bundle) is not ImmutableObjectVersion:
            raise CloudSnapshotContractError("index_bundle must be ImmutableObjectVersion")
        if type(self.indexer_identity) is not IndexerIdentity:
            raise CloudSnapshotContractError("indexer_identity must be IndexerIdentity")
        if type(self.sqlite_schema_identity) is not SqliteSchemaIdentity:
            raise CloudSnapshotContractError(
                "sqlite_schema_identity must be SqliteSchemaIdentity"
            )
        _sha256(self.manifest_sha256, "manifest_sha256")
        _sha256(self.snapshot_id, "snapshot_id")
        expected = _derive_snapshot_id(
            _identity_payload(
                source_revision=self.source_revision,
                source_bundle=self.source_bundle,
                index_bundle=self.index_bundle,
                manifest_sha256=self.manifest_sha256,
                indexer_identity=self.indexer_identity,
                sqlite_schema_identity=self.sqlite_schema_identity,
            )
        )
        if self.snapshot_id != expected:
            raise CloudSnapshotContractError("snapshot_id does not match canonical identity tuple")

    def identity_dict(self) -> dict[str, Any]:
        """Return the complete canonical tuple used to derive snapshot_id."""
        return _identity_payload(
            source_revision=self.source_revision,
            source_bundle=self.source_bundle,
            index_bundle=self.index_bundle,
            manifest_sha256=self.manifest_sha256,
            indexer_identity=self.indexer_identity,
            sqlite_schema_identity=self.sqlite_schema_identity,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.identity_dict(),
            "snapshot_id": self.snapshot_id,
        }


@dataclass(frozen=True, slots=True)
class BuiltCloudSnapshotV2:
    """A v2 identity plus the detached canonical manifest bytes it authenticates."""

    ref: CloudSnapshotRefV2
    manifest_bytes: bytes

    def __post_init__(self) -> None:
        if type(self.ref) is not CloudSnapshotRefV2:
            raise CloudSnapshotContractError("ref must be CloudSnapshotRefV2")
        if not isinstance(self.manifest_bytes, bytes):
            raise CloudSnapshotContractError("manifest_bytes must be bytes")
        verify_cloud_snapshot_manifest(self.ref, self.manifest_bytes)


def build_cloud_snapshot_v2(
    manifest: CloudSnapshotManifestV1,
) -> BuiltCloudSnapshotV2:
    """Create canonical manifest bytes, detached digest, and deterministic v2 ID."""
    manifest_bytes = serialize_cloud_snapshot_manifest(manifest)
    manifest_sha256 = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
    payload = _identity_payload(
        source_revision=manifest.source_revision,
        source_bundle=manifest.source_bundle,
        index_bundle=manifest.index_bundle,
        manifest_sha256=manifest_sha256,
        indexer_identity=manifest.indexer_identity,
        sqlite_schema_identity=manifest.sqlite_schema_identity,
    )
    ref = CloudSnapshotRefV2(
        source_revision=manifest.source_revision,
        source_bundle=manifest.source_bundle,
        index_bundle=manifest.index_bundle,
        manifest_sha256=manifest_sha256,
        indexer_identity=manifest.indexer_identity,
        sqlite_schema_identity=manifest.sqlite_schema_identity,
        snapshot_id=_derive_snapshot_id(payload),
    )
    return BuiltCloudSnapshotV2(ref=ref, manifest_bytes=manifest_bytes)


def cloud_snapshot_ref_v2_from_dict(value: Any) -> CloudSnapshotRefV2:
    obj = _mapping(value, "snapshot_ref_v2")
    _exact_keys(
        obj,
        required={
            "snapshot_schema_version",
            "source_revision",
            "source_bundle",
            "index_bundle",
            "manifest_sha256",
            "indexer_identity",
            "sqlite_schema_identity",
            "snapshot_id",
        },
        name="snapshot_ref_v2",
    )
    return CloudSnapshotRefV2(
        snapshot_schema_version=obj["snapshot_schema_version"],
        source_revision=_source_revision(obj["source_revision"]),
        source_bundle=_object_version(obj["source_bundle"], "source_bundle"),
        index_bundle=_object_version(obj["index_bundle"], "index_bundle"),
        manifest_sha256=obj["manifest_sha256"],
        indexer_identity=_indexer_identity(obj["indexer_identity"]),
        sqlite_schema_identity=_sqlite_schema_identity(obj["sqlite_schema_identity"]),
        snapshot_id=obj["snapshot_id"],
    )


def verify_cloud_snapshot_manifest(
    ref: CloudSnapshotRefV2,
    raw_manifest_bytes: bytes,
) -> CloudSnapshotManifestV1:
    """Verify exact manifest digest, canonical encoding, and every bound identity field."""
    if type(ref) is not CloudSnapshotRefV2:
        raise CloudSnapshotContractError("ref must be CloudSnapshotRefV2")
    manifest = parse_canonical_cloud_snapshot_manifest(
        raw_manifest_bytes,
        expected_sha256=ref.manifest_sha256,
    )
    if manifest.to_dict() != {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "source_revision": ref.source_revision.to_dict(),
        "source_bundle": ref.source_bundle.to_dict(),
        "index_bundle": ref.index_bundle.to_dict(),
        "indexer_identity": ref.indexer_identity.to_dict(),
        "sqlite_schema_identity": ref.sqlite_schema_identity.to_dict(),
    }:
        raise CloudSnapshotContractError(
            "manifest identity does not match the immutable v2 snapshot reference"
        )
    return manifest
