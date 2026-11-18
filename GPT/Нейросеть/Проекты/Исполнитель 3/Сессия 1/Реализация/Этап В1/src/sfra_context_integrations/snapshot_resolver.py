"""Exact-version read-only cloud snapshot resolver and workspace materializer.

The resolver binds one catalogue entry per request, fetches only the immutable
object versions named by that reference, verifies the complete outer bundle,
and materializes verified bytes into a caller-owned ephemeral workspace.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from typing import Any, Protocol

from .cloud_snapshot_bundle import (
    ATTESTATION_PATH,
    BUNDLE_FORMAT,
    E1_DATABASE_PATH,
    INVENTORY_PATH,
    SOURCE_ARCHIVE_PREFIX,
    BundleIntegrityError,
    BundleVerificationReport,
    PreparedBundleObject,
    PreparedCloudSnapshotBundle,
    _read_deterministic_zip,
    _validate_relative_posix_path,
    verify_prepared_cloud_snapshot_bundle,
)
from .cloud_snapshot_v2 import (
    CloudSnapshotContractError,
    CloudSnapshotManifestV1,
    CloudSnapshotRefV2,
    ImmutableObjectVersion,
    cloud_snapshot_ref_v2_from_dict,
    serialize_cloud_snapshot_manifest,
    verify_cloud_snapshot_manifest,
)
from .snapshot_catalogue import (
    SnapshotCatalogueEntry,
    SnapshotCatalogueError,
    SnapshotLifecycleState,
    SnapshotNotFoundError,
    SnapshotRetiredError,
)

_SHA256_PREFIX = "sha256:"
_SHA256_HEX_LENGTH = 64
_MAX_INNER_JSON_BYTES = 2 * 1024 * 1024
_EXPECTED_INDEX_MEMBERS = frozenset({ATTESTATION_PATH, INVENTORY_PATH, E1_DATABASE_PATH})
_EXPECTED_ATTESTATION_KEYS = frozenset({
    "attestation_version",
    "format",
    "source_revision",
    "markdown_inventory",
    "indexer_identity",
    "parser_identities",
    "sqlite_schema_identity",
    "database",
    "counts",
})
_EXPECTED_COUNTS_KEYS = frozenset({
    "document_count",
    "active_document_count",
    "node_count",
    "active_node_count",
    "passage_count",
})


class SnapshotResolverError(RuntimeError):
    """Base class for closed, non-content-bearing resolver failures."""

    code = "snapshot_resolution_error"


class InvalidSnapshotRequestError(SnapshotResolverError):
    """The requested snapshot ID is not an exact immutable identity."""

    code = "invalid_snapshot_request"


class SnapshotUnavailableError(SnapshotResolverError):
    """The exact catalogue entry is absent or retired."""

    code = "snapshot_unavailable"


class SnapshotCatalogueReadError(SnapshotResolverError):
    """The catalogue returned an invalid or unavailable lookup outcome."""

    code = "snapshot_catalogue_read_error"


class ExactObjectVersionUnavailableError(SnapshotResolverError):
    """The requested immutable object version is unavailable."""

    code = "exact_object_version_unavailable"


class ObjectStoreReadError(SnapshotResolverError):
    """The read port failed or returned an unsupported response shape."""

    code = "object_store_read_error"


class ObjectVersionIdentityError(SnapshotResolverError):
    """The backend did not return the exact key and immutable version requested."""

    code = "object_version_identity_mismatch"


class ObjectPayloadIntegrityError(SnapshotResolverError):
    """The exact-version payload does not match its committed size and digest."""

    code = "object_payload_integrity_mismatch"


class SnapshotManifestIntegrityError(SnapshotResolverError):
    """The canonical outer manifest does not match the catalogue reference."""

    code = "snapshot_manifest_integrity_error"


class SnapshotBundleIntegrityError(SnapshotResolverError):
    """The downloaded source/index pair is not a valid canonical #119 bundle."""

    code = "snapshot_bundle_integrity_error"


class UnsafeMaterializationWorkspaceError(SnapshotResolverError):
    """The caller workspace or an extracted path is unsafe."""

    code = "unsafe_materialization_workspace"


class MaterializedFileChangedError(SnapshotResolverError):
    """A file changed or was replaced while being materialized."""

    code = "materialized_file_changed"


class ObjectVersionNotFoundError(LookupError):
    """Read-port signal that the requested exact object version does not exist."""


@dataclass(frozen=True, slots=True)
class ObjectVersionRead:
    """Raw response from an exact-version read; version_id must be echoed by the port."""

    key: str
    version_id: str | None
    payload: bytes


class ObjectStoreReadPort(Protocol):
    """Least-privilege read seam. There is deliberately no write/delete/list method."""

    def get_exact(self, *, key: str, version_id: str) -> ObjectVersionRead: ...


class SnapshotCatalogueReadPort(Protocol):
    """Narrow lookup seam used once at the beginning of a request."""

    def get_exact(self, snapshot_id: str) -> SnapshotCatalogueEntry: ...


@dataclass(frozen=True, slots=True)
class MaterializedCloudSnapshotHandle:
    """Request-scoped verified files and exact E1 inner bytes for downstream use.

    The caller owns cleanup of workspace_path. The handle is an immutable record;
    callers must not mutate the materialized files while the request is in flight.
    This is outer bundle consistency, not the separate deep E1 verifier #240.
    """

    snapshot: CloudSnapshotRefV2
    workspace_path: Path
    source_root: Path
    database_path: Path
    attestation_path: Path
    inventory_path: Path
    attestation_bytes: bytes
    markdown_inventory_bytes: bytes
    bundle_report: BundleVerificationReport

    @property
    def snapshot_id(self) -> str:
        return self.snapshot.snapshot_id

    @property
    def source_revision(self):
        return self.snapshot.source_revision

    @property
    def source_object_version(self) -> ImmutableObjectVersion:
        return self.snapshot.source_bundle

    @property
    def index_object_version(self) -> ImmutableObjectVersion:
        return self.snapshot.index_bundle


def _sha256(raw: bytes) -> str:
    return _SHA256_PREFIX + hashlib.sha256(raw).hexdigest()


def _exact_keys(value: dict[str, Any], expected: frozenset[str], name: str) -> None:
    if set(value) != set(expected):
        raise SnapshotBundleIntegrityError(f"{name} fields are incomplete or unsupported")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotBundleIntegrityError("inner JSON contains a duplicate object key")
        result[key] = value
    return result


def _parse_canonical_object(raw: bytes, name: str) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > _MAX_INNER_JSON_BYTES:
        raise SnapshotBundleIntegrityError(f"{name} byte length is invalid")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                SnapshotBundleIntegrityError(f"{name} contains an unsupported JSON constant")
            ),
        )
    except SnapshotBundleIntegrityError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotBundleIntegrityError(f"{name} is not valid UTF-8 JSON") from exc
    if type(value) is not dict:
        raise SnapshotBundleIntegrityError(f"{name} must be a JSON object")
    try:
        canonical = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise SnapshotBundleIntegrityError(f"{name} cannot be canonically encoded") from exc
    if canonical != raw:
        raise SnapshotBundleIntegrityError(f"{name} is not canonical JSON")
    return value


def _non_negative_int(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise SnapshotBundleIntegrityError(f"{name} must be a non-negative integer")
    return value


def _validate_inner_metadata(
    *,
    snapshot: CloudSnapshotRefV2,
    inventory_bytes: bytes,
    attestation_bytes: bytes,
    database_bytes: bytes,
) -> tuple[dict[str, int], str, int]:
    inventory = _parse_canonical_object(inventory_bytes, "Markdown inventory")
    if set(inventory) != {"format", "documents"}:
        raise SnapshotBundleIntegrityError("Markdown inventory fields are incomplete or unsupported")
    if inventory["format"] != "sfra.e1.markdown-inventory.v1":
        raise SnapshotBundleIntegrityError("Markdown inventory format is unsupported")
    documents = inventory["documents"]
    if type(documents) is not list:
        raise SnapshotBundleIntegrityError("Markdown inventory documents must be a list")
    inventory_count = len(documents)
    for row in documents:
        if type(row) is not dict or set(row) != {"path", "byte_size", "sha256"}:
            raise SnapshotBundleIntegrityError("Markdown inventory row is malformed")
        if not isinstance(row["path"], str) or not row["path"]:
            raise SnapshotBundleIntegrityError("Markdown inventory path is invalid")
        _non_negative_int(row["byte_size"], "Markdown inventory byte_size")
        if not isinstance(row["sha256"], str) or len(row["sha256"]) != 71 or not row["sha256"].startswith(_SHA256_PREFIX):
            raise SnapshotBundleIntegrityError("Markdown inventory digest is malformed")

    attestation = _parse_canonical_object(attestation_bytes, "E1 cloud-index attestation")
    _exact_keys(attestation, _EXPECTED_ATTESTATION_KEYS, "E1 cloud-index attestation")
    if attestation["attestation_version"] != 1:
        raise SnapshotBundleIntegrityError("E1 attestation version is unsupported")
    if attestation["format"] != "sfra.e1.cloud-index-attestation.v1":
        raise SnapshotBundleIntegrityError("E1 attestation format is unsupported")
    if attestation["source_revision"] != snapshot.source_revision.to_dict():
        raise SnapshotBundleIntegrityError("E1 attestation source revision differs from outer snapshot")

    inventory_ref = attestation["markdown_inventory"]
    if type(inventory_ref) is not dict or set(inventory_ref) != {"format", "path", "sha256", "document_count"}:
        raise SnapshotBundleIntegrityError("E1 attestation inventory reference is malformed")
    if (
        inventory_ref["format"] != "sfra.e1.markdown-inventory.v1"
        or inventory_ref["path"] != INVENTORY_PATH
        or inventory_ref["sha256"] != _sha256(inventory_bytes)
        or type(inventory_ref["document_count"]) is not int
        or inventory_ref["document_count"] != inventory_count
    ):
        raise SnapshotBundleIntegrityError("E1 attestation does not bind the exact inventory bytes")

    if attestation["indexer_identity"] != snapshot.indexer_identity.to_dict():
        raise SnapshotBundleIntegrityError("E1 attestation indexer identity differs from outer snapshot")
    if attestation["sqlite_schema_identity"] != snapshot.sqlite_schema_identity.to_dict():
        raise SnapshotBundleIntegrityError("E1 attestation SQLite schema identity differs from outer snapshot")

    parser_identities = attestation["parser_identities"]
    if type(parser_identities) is not list:
        raise SnapshotBundleIntegrityError("E1 parser identities must be a list")
    for parser in parser_identities:
        if (
            type(parser) is not dict
            or set(parser) != {"name", "version"}
            or not isinstance(parser["name"], str)
            or not parser["name"]
            or not isinstance(parser["version"], str)
            or not parser["version"]
        ):
            raise SnapshotBundleIntegrityError("E1 parser identity is malformed")

    database = attestation["database"]
    if type(database) is not dict or set(database) != {"path", "sha256", "byte_size"}:
        raise SnapshotBundleIntegrityError("E1 database attestation is malformed")
    if (
        database["path"] != E1_DATABASE_PATH
        or database["sha256"] != _sha256(database_bytes)
        or type(database["byte_size"]) is not int
        or database["byte_size"] != len(database_bytes)
    ):
        raise SnapshotBundleIntegrityError("E1 attestation does not bind the exact SQLite bytes")

    counts = attestation["counts"]
    if type(counts) is not dict or set(counts) != set(_EXPECTED_COUNTS_KEYS):
        raise SnapshotBundleIntegrityError("E1 attestation counts are malformed")
    normalized_counts = {
        key: _non_negative_int(counts[key], f"E1 attestation {key}")
        for key in _EXPECTED_COUNTS_KEYS
    }
    return normalized_counts, inventory_ref["sha256"], inventory_count


def _verify_canonical_snapshot_manifest(snapshot: CloudSnapshotRefV2) -> None:
    try:
        manifest = CloudSnapshotManifestV1(
            source_revision=snapshot.source_revision,
            source_bundle=snapshot.source_bundle,
            index_bundle=snapshot.index_bundle,
            indexer_identity=snapshot.indexer_identity,
            sqlite_schema_identity=snapshot.sqlite_schema_identity,
        )
        raw_manifest = serialize_cloud_snapshot_manifest(manifest)
        verify_cloud_snapshot_manifest(snapshot, raw_manifest)
    except (CloudSnapshotContractError, TypeError, ValueError, AttributeError) as exc:
        raise SnapshotManifestIntegrityError("canonical manifest does not match the immutable snapshot") from exc


def _check_payload(expected: ImmutableObjectVersion, result: ObjectVersionRead) -> bytes:
    if type(result) is not ObjectVersionRead:
        raise ObjectStoreReadError("exact-version port returned an unsupported response type")
    if (
        result.key != expected.key
        or result.version_id != expected.version_id
    ):
        raise ObjectVersionIdentityError("object store did not return the requested exact immutable version")
    if type(result.payload) is not bytes:
        raise ObjectStoreReadError("exact-version port returned a non-byte payload")
    if len(result.payload) != expected.byte_size or _sha256(result.payload) != expected.sha256:
        raise ObjectPayloadIntegrityError("exact-version payload does not match committed digest and size")
    return result.payload


def _read_exact_object(
    port: ObjectStoreReadPort,
    expected: ImmutableObjectVersion,
) -> bytes:
    try:
        result = port.get_exact(key=expected.key, version_id=expected.version_id)
    except ObjectVersionNotFoundError as exc:
        raise ExactObjectVersionUnavailableError("requested immutable object version is unavailable") from exc
    except Exception as exc:
        raise ObjectStoreReadError("exact-version object read failed") from exc
    return _check_payload(expected, result)


def _safe_workspace(workspace: str | Path) -> Path:
    try:
        root = Path(workspace).expanduser()
        if root.is_symlink():
            raise UnsafeMaterializationWorkspaceError("workspace must not be a symlink")
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink() or not root.is_dir():
            raise UnsafeMaterializationWorkspaceError("workspace must be a regular directory")
        return root.resolve(strict=True)
    except SnapshotResolverError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise UnsafeMaterializationWorkspaceError("workspace cannot be prepared safely") from exc


def _mkdir_under(root: Path, directory: Path) -> None:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        root_real = root.resolve(strict=True)
        directory_real = directory.resolve(strict=True)
        if directory.is_symlink() or not directory_real.is_relative_to(root_real):
            raise UnsafeMaterializationWorkspaceError("materialization directory escaped its workspace")
        if not directory.is_dir():
            raise UnsafeMaterializationWorkspaceError("materialization parent is not a directory")
    except SnapshotResolverError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise UnsafeMaterializationWorkspaceError("materialization directory is unsafe") from exc


def _write_exclusive(root: Path, destination: Path, payload: bytes) -> None:
    root_real = root.resolve(strict=True)
    _mkdir_under(root, destination.parent)
    try:
        resolved_parent = destination.parent.resolve(strict=True)
        if not resolved_parent.is_relative_to(root_real):
            raise UnsafeMaterializationWorkspaceError("extracted file escaped the private workspace")
        if destination.exists() or destination.is_symlink():
            raise UnsafeMaterializationWorkspaceError("extracted file already exists")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(destination, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
            opened = os.fstat(stream.fileno())
        observed = destination.lstat()
        if (
            not stat.S_ISREG(observed.st_mode)
            or (observed.st_dev, observed.st_ino) != (opened.st_dev, opened.st_ino)
            or destination.resolve(strict=True).parent != resolved_parent
        ):
            raise MaterializedFileChangedError("materialized file was replaced during write")
        if destination.read_bytes() != payload:
            raise MaterializedFileChangedError("materialized file bytes changed after write")
    except SnapshotResolverError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise UnsafeMaterializationWorkspaceError("extracted file could not be written safely") from exc


def _extract_source_members(source_members: dict[str, bytes], source_root: Path, root: Path) -> None:
    if not source_members:
        raise SnapshotBundleIntegrityError("source archive is empty")
    seen: set[str] = set()
    for member_name, raw in source_members.items():
        if not member_name.startswith(SOURCE_ARCHIVE_PREFIX):
            raise SnapshotBundleIntegrityError("source archive contains a member outside source/")
        relative = member_name[len(SOURCE_ARCHIVE_PREFIX):]
        try:
            _validate_relative_posix_path(relative)
        except Exception as exc:
            raise SnapshotBundleIntegrityError("source archive contains an unsafe path") from exc
        if relative in seen or not isinstance(raw, bytes):
            raise SnapshotBundleIntegrityError("source archive contains duplicate or invalid members")
        seen.add(relative)
        destination = source_root.joinpath(*PurePosixPath(relative).parts)
        _write_exclusive(root, destination, raw)


def _build_prepared_bundle(
    snapshot: CloudSnapshotRefV2,
    source_payload: bytes,
    index_payload: bytes,
    source_members: dict[str, bytes],
    index_members: dict[str, bytes],
) -> PreparedCloudSnapshotBundle:
    if set(index_members) != set(_EXPECTED_INDEX_MEMBERS):
        raise SnapshotBundleIntegrityError("index archive members do not match the accepted bundle layout")
    inventory_bytes = index_members[INVENTORY_PATH]
    attestation_bytes = index_members[ATTESTATION_PATH]
    database_bytes = index_members[E1_DATABASE_PATH]
    counts, inventory_sha256, inventory_count = _validate_inner_metadata(
        snapshot=snapshot,
        inventory_bytes=inventory_bytes,
        attestation_bytes=attestation_bytes,
        database_bytes=database_bytes,
    )
    return PreparedCloudSnapshotBundle(
        bundle_format=BUNDLE_FORMAT,
        source_revision=snapshot.source_revision,
        source_object=PreparedBundleObject(
            key=snapshot.source_bundle.key,
            payload=source_payload,
            sha256=snapshot.source_bundle.sha256,
            byte_size=snapshot.source_bundle.byte_size,
        ),
        index_object=PreparedBundleObject(
            key=snapshot.index_bundle.key,
            payload=index_payload,
            sha256=snapshot.index_bundle.sha256,
            byte_size=snapshot.index_bundle.byte_size,
        ),
        markdown_inventory_bytes=inventory_bytes,
        markdown_inventory_sha256=inventory_sha256,
        markdown_document_count=inventory_count,
        attestation_bytes=attestation_bytes,
        indexer_identity=snapshot.indexer_identity,
        sqlite_schema_identity=snapshot.sqlite_schema_identity,
        source_file_count=len(source_members),
        document_count=counts["document_count"],
        active_document_count=counts["active_document_count"],
        node_count=counts["node_count"],
        active_node_count=counts["active_node_count"],
        passage_count=counts["passage_count"],
        e1_legacy_verifier="resolver_reverification_pending",
    )


class CloudSnapshotResolver:
    """Resolve one exact catalogue entry and materialize its immutable objects."""

    def __init__(
        self,
        catalogue: SnapshotCatalogueReadPort,
        object_store: ObjectStoreReadPort,
    ) -> None:
        self._catalogue = catalogue
        self._object_store = object_store

    def resolve(
        self,
        snapshot_id: str,
        *,
        workspace: str | Path,
    ) -> MaterializedCloudSnapshotHandle:
        """Materialize the exact ref once; the returned workspace belongs to the caller."""
        if (
            not isinstance(snapshot_id, str)
            or len(snapshot_id) != len(_SHA256_PREFIX) + _SHA256_HEX_LENGTH
            or not snapshot_id.startswith(_SHA256_PREFIX)
            or any(char not in "0123456789abcdef" for char in snapshot_id[len(_SHA256_PREFIX):])
        ):
            raise InvalidSnapshotRequestError("snapshot_id must be an exact sha256:<64 lowercase hex> ID")

        # Exactly one catalogue lookup. Never resolve again after object reads begin.
        try:
            entry = self._catalogue.get_exact(snapshot_id)
        except (SnapshotNotFoundError, SnapshotRetiredError) as exc:
            raise SnapshotUnavailableError("exact snapshot is absent or retired") from exc
        except SnapshotCatalogueError as exc:
            raise SnapshotCatalogueReadError("catalogue rejected the exact snapshot lookup") from exc
        except Exception as exc:
            raise SnapshotCatalogueReadError("catalogue exact lookup failed") from exc

        if type(entry) is not SnapshotCatalogueEntry or type(entry.snapshot) is not CloudSnapshotRefV2:
            raise SnapshotCatalogueReadError("catalogue returned an invalid exact snapshot entry")
        state = entry.state
        if state not in (
            SnapshotLifecycleState.STAGED,
            SnapshotLifecycleState.VERIFIED,
            SnapshotLifecycleState.ACTIVE,
        ):
            raise SnapshotCatalogueReadError("catalogue entry has an unsupported lifecycle state")
        # STAGED is intentionally readable for materialization only: the raw E1
        # attestation/database are inputs to the separate deep verifier #240.
        # This method never marks the entry VERIFIED or ACTIVE; downstream query
        # binding remains gated on successful E1 verification.
        try:
            snapshot = cloud_snapshot_ref_v2_from_dict(entry.snapshot.to_dict())
        except (CloudSnapshotContractError, AttributeError, TypeError, ValueError) as exc:
            raise SnapshotCatalogueReadError("catalogue snapshot identity is not canonical") from exc
        if snapshot != entry.snapshot or snapshot.snapshot_id != snapshot_id:
            raise SnapshotCatalogueReadError("catalogue returned a different snapshot identity")

        _verify_canonical_snapshot_manifest(snapshot)
        source_payload = _read_exact_object(self._object_store, snapshot.source_bundle)
        index_payload = _read_exact_object(self._object_store, snapshot.index_bundle)

        try:
            source_members = _read_deterministic_zip(source_payload, "source bundle")
            index_members = _read_deterministic_zip(index_payload, "index bundle")
            if any(not name.startswith(SOURCE_ARCHIVE_PREFIX) for name in source_members):
                raise SnapshotBundleIntegrityError("source archive layout is invalid")
            prepared = _build_prepared_bundle(
                snapshot, source_payload, index_payload, source_members, index_members
            )
            report = verify_prepared_cloud_snapshot_bundle(prepared)
        except SnapshotBundleIntegrityError:
            raise
        except BundleIntegrityError as exc:
            raise SnapshotBundleIntegrityError("downloaded source/index bundle verification failed") from exc
        except Exception as exc:
            raise SnapshotBundleIntegrityError("downloaded source/index bundle could not be verified") from exc

        workspace_root = _safe_workspace(workspace)
        materialized_root: Path | None = None
        try:
            materialized_root = Path(tempfile.mkdtemp(prefix="sfra-snapshot-", dir=workspace_root))
            source_root = materialized_root / "source"
            index_root = materialized_root / "index"
            _mkdir_under(materialized_root, source_root)
            _mkdir_under(materialized_root, index_root)
            _extract_source_members(source_members, source_root, materialized_root)

            inventory_bytes = index_members[INVENTORY_PATH]
            attestation_bytes = index_members[ATTESTATION_PATH]
            database_bytes = index_members[E1_DATABASE_PATH]
            database_path = index_root / E1_DATABASE_PATH
            inventory_path = index_root / INVENTORY_PATH
            attestation_path = index_root / ATTESTATION_PATH
            _write_exclusive(materialized_root, database_path, database_bytes)
            _write_exclusive(materialized_root, inventory_path, inventory_bytes)
            _write_exclusive(materialized_root, attestation_path, attestation_bytes)

            # Recheck materialized bytes after filesystem writes to catch replacement/races.
            if database_path.read_bytes() != database_bytes:
                raise MaterializedFileChangedError("materialized SQLite bytes changed")
            if inventory_path.read_bytes() != inventory_bytes or attestation_path.read_bytes() != attestation_bytes:
                raise MaterializedFileChangedError("materialized E1 inner attestation bytes changed")
            for member_name, raw in source_members.items():
                relative = member_name[len(SOURCE_ARCHIVE_PREFIX):]
                target = source_root.joinpath(*PurePosixPath(relative).parts)
                if target.read_bytes() != raw:
                    raise MaterializedFileChangedError("materialized source file bytes changed")

            return MaterializedCloudSnapshotHandle(
                snapshot=snapshot,
                workspace_path=materialized_root,
                source_root=source_root,
                database_path=database_path,
                attestation_path=attestation_path,
                inventory_path=inventory_path,
                attestation_bytes=attestation_bytes,
                markdown_inventory_bytes=inventory_bytes,
                bundle_report=report,
            )
        except SnapshotResolverError:
            if materialized_root is not None:
                shutil.rmtree(materialized_root, ignore_errors=True)
            raise
        except Exception as exc:
            if materialized_root is not None:
                shutil.rmtree(materialized_root, ignore_errors=True)
            raise UnsafeMaterializationWorkspaceError("snapshot files could not be materialized safely") from exc


__all__ = [
    "CloudSnapshotResolver",
    "ExactObjectVersionUnavailableError",
    "InvalidSnapshotRequestError",
    "MaterializedCloudSnapshotHandle",
    "MaterializedFileChangedError",
    "ObjectPayloadIntegrityError",
    "ObjectStoreReadError",
    "ObjectStoreReadPort",
    "ObjectVersionIdentityError",
    "ObjectVersionNotFoundError",
    "ObjectVersionRead",
    "SnapshotBundleIntegrityError",
    "SnapshotCatalogueReadError",
    "SnapshotManifestIntegrityError",
    "SnapshotResolverError",
    "SnapshotUnavailableError",
    "SnapshotCatalogueReadPort",
    "UnsafeMaterializationWorkspaceError",
]
