"""Read-only exact-version cloud snapshot materialization.

This boundary resolves one immutable snapshot identity, reads only the two exact
object versions bound by that identity, verifies the accepted outer manifest
and #119 bundle, then writes the verified bytes into a disposable workspace.
It intentionally has no provider, network, write-port or catalogue mutation API.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Mapping, Protocol

from .cloud_snapshot_v2 import (
    CloudSnapshotContractError,
    CloudSnapshotManifestV1,
    CloudSnapshotRefV2,
    ImmutableObjectVersion,
    IndexerIdentity,
    SqliteSchemaIdentity,
    serialize_cloud_snapshot_manifest,
    verify_cloud_snapshot_manifest,
)
from .cloud_snapshot_bundle import (
    ATTESTATION_PATH,
    BUNDLE_FORMAT,
    E1_CLOUD_INDEX_ATTESTATION_FORMAT,
    E1_DATABASE_PATH,
    INVENTORY_PATH,
    MARKDOWN_INVENTORY_FORMAT,
    SOURCE_ARCHIVE_PREFIX,
    BundleIntegrityError,
    BundleVerificationReport,
    PreparedBundleObject,
    PreparedCloudSnapshotBundle,
    _read_deterministic_zip,
    verify_prepared_cloud_snapshot_bundle,
)
from .snapshot_catalogue import (
    SnapshotCatalogueEntry,
    SnapshotCatalogueError,
    SnapshotCataloguePort,
    SnapshotLifecycleState,
    SnapshotRetiredError,
)


class SnapshotMaterializationError(RuntimeError):
    """Base class for fail-closed resolver/materializer failures."""


class SnapshotObjectUnavailableError(SnapshotMaterializationError):
    """An exact immutable object version is absent from the read port."""


class SnapshotObjectVersionMismatchError(SnapshotMaterializationError):
    """The read port returned a different key or immutable version ID."""


class SnapshotObjectIntegrityError(SnapshotMaterializationError):
    """The exact object payload does not match its v2 hash/size identity."""


class SnapshotMaterializationIntegrityError(SnapshotMaterializationError):
    """The manifest or either deterministic bundle fails verification."""


class SnapshotBindingChangedError(SnapshotMaterializationError):
    """The exact catalogue identity changed or became unavailable in flight."""


class SnapshotWorkspaceError(SnapshotMaterializationError):
    """The caller workspace cannot safely receive a new disposable materialization."""


class ObjectStoreObjectNotFoundError(LookupError):
    """The requested exact key/version pair is not present in the read port."""


@dataclass(frozen=True, slots=True)
class ObjectStoreReadResult:
    """One exact immutable object payload returned by a read-only port."""

    key: str
    version_id: str
    payload: bytes


class ObjectStoreReadPort(Protocol):
    """Least-privilege exact-version read interface; no list/write/delete methods."""

    def read_exact(self, key: str, version_id: str) -> ObjectStoreReadResult: ...


class InMemoryVersionedObjectStore:
    """Disposable immutable-version fixture adapter.

    The complete fixture mapping is supplied at construction. The adapter
    deliberately exposes only read_exact; it has no upload, overwrite, list or
    delete operation.
    """

    def __init__(self, objects: Mapping[tuple[str, str], bytes]) -> None:
        if not isinstance(objects, Mapping):
            raise TypeError("objects must be a mapping of (key, version_id) to bytes")
        copied: dict[tuple[str, str], bytes] = {}
        for identity, payload in objects.items():
            if (
                type(identity) is not tuple
                or len(identity) != 2
                or not all(isinstance(part, str) and part for part in identity)
            ):
                raise ValueError("each object identity must be a non-empty (key, version_id) tuple")
            if not isinstance(payload, bytes):
                raise TypeError("object payloads must be bytes")
            copied[identity] = payload
        self._objects = copied

    def read_exact(self, key: str, version_id: str) -> ObjectStoreReadResult:
        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")
        if not isinstance(version_id, str) or not version_id:
            raise ValueError("version_id must be a non-empty string")
        identity = (key, version_id)
        try:
            payload = self._objects[identity]
        except KeyError as exc:
            raise ObjectStoreObjectNotFoundError(
                "the requested exact immutable object version does not exist"
            ) from exc
        return ObjectStoreReadResult(key=key, version_id=version_id, payload=payload)


@dataclass(frozen=True, slots=True)
class MaterializedCloudSnapshot:
    """Request-scoped verified snapshot and the exact artifacts consumed by E1.

    The raw attestation and inventory bytes are preserved exactly as extracted
    from the verified index archive. They are not parsed and re-serialized for
    the downstream E1 cloud verifier.
    """

    snapshot_ref: CloudSnapshotRefV2
    workspace_root: Path
    source_root: Path
    index_root: Path
    index_database_path: Path
    attestation_path: Path
    markdown_inventory_path: Path
    attestation_bytes: bytes
    markdown_inventory_bytes: bytes
    manifest_bytes: bytes
    bundle_report: BundleVerificationReport

    @property
    def snapshot_id(self) -> str:
        return self.snapshot_ref.snapshot_id

    @property
    def index_bundle_sha256(self) -> str:
        return self.snapshot_ref.index_bundle.sha256


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"unsupported JSON constant: {value}")


def _parse_canonical_json(payload: bytes, name: str) -> dict[str, object]:
    if not isinstance(payload, bytes):
        raise SnapshotMaterializationIntegrityError(f"{name} must be exact bytes")
    try:
        parsed = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
        if type(parsed) is not dict:
            raise ValueError("root must be a JSON object")
        canonical = json.dumps(
            parsed,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (UnicodeDecodeError, UnicodeEncodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SnapshotMaterializationIntegrityError(
            f"{name} is not valid canonical UTF-8 JSON"
        ) from exc
    if canonical != payload:
        raise SnapshotMaterializationIntegrityError(
            f"{name} bytes are not in canonical JSON form"
        )
    return parsed


def _require_object(value: object, *, name: str, keys: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise SnapshotMaterializationIntegrityError(
            f"{name} must contain exactly the accepted fields"
        )
    return value


def _require_nonnegative_int(value: object, *, name: str) -> int:
    if type(value) is not int or value < 0:
        raise SnapshotMaterializationIntegrityError(
            f"{name} must be a non-negative integer"
        )
    return value


def _extract_attestation_metadata(
    index_members: Mapping[str, bytes],
    ref: CloudSnapshotRefV2,
    *,
    source_payload: bytes,
    index_payload: bytes,
    source_file_count: int,
) -> PreparedCloudSnapshotBundle:
    required_members = {ATTESTATION_PATH, INVENTORY_PATH, E1_DATABASE_PATH}
    if set(index_members) != required_members:
        raise SnapshotMaterializationIntegrityError(
            "index bundle must contain exactly the accepted E1 attestation, inventory and SQLite files"
        )

    attestation_bytes = index_members[ATTESTATION_PATH]
    inventory_bytes = index_members[INVENTORY_PATH]
    database_bytes = index_members[E1_DATABASE_PATH]
    attestation = _parse_canonical_json(attestation_bytes, "E1 cloud-index attestation")
    attestation = _require_object(
        attestation,
        name="E1 cloud-index attestation",
        keys={
            "attestation_version",
            "format",
            "source_revision",
            "markdown_inventory",
            "indexer_identity",
            "parser_identities",
            "sqlite_schema_identity",
            "database",
            "counts",
        },
    )
    if type(attestation["attestation_version"]) is not int or attestation["attestation_version"] != 1:
        raise SnapshotMaterializationIntegrityError("unsupported E1 attestation version")
    if attestation["format"] != E1_CLOUD_INDEX_ATTESTATION_FORMAT:
        raise SnapshotMaterializationIntegrityError("unsupported E1 cloud-index attestation format")
    if attestation["source_revision"] != ref.source_revision.to_dict():
        raise SnapshotMaterializationIntegrityError(
            "E1 attestation source revision does not match the outer snapshot identity"
        )

    inventory = _require_object(
        attestation["markdown_inventory"],
        name="Markdown inventory descriptor",
        keys={"format", "path", "sha256", "document_count"},
    )
    if (
        inventory["format"] != MARKDOWN_INVENTORY_FORMAT
        or inventory["path"] != INVENTORY_PATH
        or inventory["sha256"] != _sha256(inventory_bytes)
    ):
        raise SnapshotMaterializationIntegrityError(
            "E1 attestation does not bind the exact embedded Markdown inventory bytes"
        )
    inventory_count = _require_nonnegative_int(
        inventory["document_count"],
        name="markdown_inventory.document_count",
    )

    indexer = _require_object(
        attestation["indexer_identity"],
        name="indexer identity",
        keys={"name", "version"},
    )
    if not all(isinstance(indexer[key], str) and indexer[key] for key in ("name", "version")):
        raise SnapshotMaterializationIntegrityError("indexer identity fields must be non-empty strings")

    schema = _require_object(
        attestation["sqlite_schema_identity"],
        name="SQLite schema identity",
        keys={"engine", "schema_info_version"},
    )
    if schema["engine"] != "sqlite":
        raise SnapshotMaterializationIntegrityError("unsupported SQLite schema engine")
    schema_version = _require_nonnegative_int(
        schema["schema_info_version"],
        name="sqlite_schema_identity.schema_info_version",
    )
    if schema_version < 1:
        raise SnapshotMaterializationIntegrityError("SQLite schema version must be positive")

    database = _require_object(
        attestation["database"],
        name="database descriptor",
        keys={"path", "sha256", "byte_size"},
    )
    if (
        database["path"] != E1_DATABASE_PATH
        or database["sha256"] != _sha256(database_bytes)
        or database["byte_size"] != len(database_bytes)
    ):
        raise SnapshotMaterializationIntegrityError(
            "E1 attestation does not bind the exact embedded SQLite bytes"
        )

    counts = _require_object(
        attestation["counts"],
        name="E1 counts",
        keys={
            "document_count",
            "active_document_count",
            "node_count",
            "active_node_count",
            "passage_count",
        },
    )
    parsed_counts = {
        key: _require_nonnegative_int(value, name=f"counts.{key}")
        for key, value in counts.items()
    }
    if parsed_counts["active_document_count"] > parsed_counts["document_count"]:
        raise SnapshotMaterializationIntegrityError("active document count exceeds document count")
    if parsed_counts["active_node_count"] > parsed_counts["node_count"]:
        raise SnapshotMaterializationIntegrityError("active node count exceeds node count")

    indexer_identity = IndexerIdentity(name=indexer["name"], version=indexer["version"])
    schema_identity = SqliteSchemaIdentity(
        engine=schema["engine"],
        schema_info_version=schema_version,
    )
    if indexer_identity != ref.indexer_identity:
        raise SnapshotMaterializationIntegrityError(
            "E1 attested indexer identity does not match the outer CloudSnapshotRef v2"
        )
    if schema_identity != ref.sqlite_schema_identity:
        raise SnapshotMaterializationIntegrityError(
            "E1 attested SQLite schema identity does not match the outer CloudSnapshotRef v2"
        )

    return PreparedCloudSnapshotBundle(
        bundle_format=BUNDLE_FORMAT,
        source_revision=ref.source_revision,
        source_object=PreparedBundleObject(
            key=ref.source_bundle.key,
            payload=source_payload,
            sha256=ref.source_bundle.sha256,
            byte_size=ref.source_bundle.byte_size,
        ),
        index_object=PreparedBundleObject(
            key=ref.index_bundle.key,
            payload=index_payload,
            sha256=ref.index_bundle.sha256,
            byte_size=ref.index_bundle.byte_size,
        ),
        markdown_inventory_bytes=inventory_bytes,
        markdown_inventory_sha256=inventory["sha256"],
        markdown_document_count=inventory_count,
        attestation_bytes=attestation_bytes,
        indexer_identity=indexer_identity,
        sqlite_schema_identity=schema_identity,
        source_file_count=source_file_count,
        document_count=parsed_counts["document_count"],
        active_document_count=parsed_counts["active_document_count"],
        node_count=parsed_counts["node_count"],
        active_node_count=parsed_counts["active_node_count"],
        passage_count=parsed_counts["passage_count"],
        e1_legacy_verifier="rechecked_by_public_bundle_verifier",
    )


class CloudSnapshotMaterializer:
    """Resolve, verify and materialize one immutable snapshot ID exactly once."""

    def __init__(
        self,
        catalogue: SnapshotCataloguePort,
        object_store: ObjectStoreReadPort,
    ) -> None:
        self._catalogue = catalogue
        self._object_store = object_store

    def materialize(
        self,
        snapshot_id: str,
        workspace: str | Path,
    ) -> MaterializedCloudSnapshot:
        if not isinstance(snapshot_id, str) or not snapshot_id:
            raise SnapshotMaterializationError("snapshot_id must be a non-empty exact identity")
        entry = self._get_exact_entry(snapshot_id)
        ref = entry.snapshot

        source_result = self._read_object(ref.source_bundle)
        self._recheck_binding(ref)
        index_result = self._read_object(ref.index_bundle)
        self._recheck_binding(ref)

        manifest = CloudSnapshotManifestV1(
            source_revision=ref.source_revision,
            source_bundle=ref.source_bundle,
            index_bundle=ref.index_bundle,
            indexer_identity=ref.indexer_identity,
            sqlite_schema_identity=ref.sqlite_schema_identity,
        )
        try:
            manifest_bytes = serialize_cloud_snapshot_manifest(manifest)
            verify_cloud_snapshot_manifest(ref, manifest_bytes)
            source_members = _read_deterministic_zip(source_result.payload, "source bundle")
            index_members = _read_deterministic_zip(index_result.payload, "index bundle")
            if not source_members or any(
                not name.startswith(SOURCE_ARCHIVE_PREFIX) for name in source_members
            ):
                raise BundleIntegrityError("source archive has an unexpected member layout")
            prepared = _extract_attestation_metadata(
                index_members,
                ref,
                source_payload=source_result.payload,
                index_payload=index_result.payload,
                source_file_count=len(source_members),
            )
            report = verify_prepared_cloud_snapshot_bundle(prepared)
            if (
                report.bundle_format != BUNDLE_FORMAT
                or report.source_archive_sha256 != ref.source_bundle.sha256
                or report.source_archive_byte_size != ref.source_bundle.byte_size
                or report.index_archive_sha256 != ref.index_bundle.sha256
                or report.index_archive_byte_size != ref.index_bundle.byte_size
                or report.schema_info_version != ref.sqlite_schema_identity.schema_info_version
                or report.markdown_inventory_sha256 != prepared.markdown_inventory_sha256
                or report.markdown_document_count != prepared.markdown_document_count
            ):
                raise BundleIntegrityError(
                    "public #119 bundle verification report does not match the outer v2 identity"
                )
        except (BundleIntegrityError, CloudSnapshotContractError, KeyError, TypeError, ValueError) as exc:
            raise SnapshotMaterializationIntegrityError(
                "outer manifest or prepared source/index bundle verification failed"
            ) from exc

        self._recheck_binding(ref)
        workspace_root, source_root, index_root, database_path, attestation_path, inventory_path = (
            self._write_workspace(
                workspace,
                snapshot_id=snapshot_id,
                source_members=source_members,
                index_members=index_members,
            )
        )
        try:
            self._recheck_binding(ref)
        except Exception:
            shutil.rmtree(workspace_root, ignore_errors=True)
            raise

        return MaterializedCloudSnapshot(
            snapshot_ref=ref,
            workspace_root=workspace_root,
            source_root=source_root,
            index_root=index_root,
            index_database_path=database_path,
            attestation_path=attestation_path,
            markdown_inventory_path=inventory_path,
            attestation_bytes=index_members[ATTESTATION_PATH],
            markdown_inventory_bytes=index_members[INVENTORY_PATH],
            manifest_bytes=manifest_bytes,
            bundle_report=report,
        )

    def _get_exact_entry(self, snapshot_id: str) -> SnapshotCatalogueEntry:
        try:
            entry = self._catalogue.get_exact(snapshot_id)
        except SnapshotCatalogueError:
            raise
        except Exception as exc:
            raise SnapshotBindingChangedError(
                "catalogue could not resolve the requested exact snapshot identity"
            ) from exc
        if type(entry) is not SnapshotCatalogueEntry:
            raise SnapshotBindingChangedError(
                "catalogue returned an unsupported entry type"
            )
        if type(entry.snapshot) is not CloudSnapshotRefV2:
            raise SnapshotBindingChangedError(
                "catalogue entry does not contain the exact CloudSnapshotRefV2 type"
            )
        if entry.snapshot.snapshot_id != snapshot_id:
            raise SnapshotBindingChangedError(
                "catalogue returned an identity different from the requested snapshot_id"
            )
        if entry.state is SnapshotLifecycleState.RETIRED:
            raise SnapshotRetiredError("the requested exact snapshot has been retired")
        if entry.state not in (
            SnapshotLifecycleState.STAGED,
            SnapshotLifecycleState.VERIFIED,
            SnapshotLifecycleState.ACTIVE,
        ):
            raise SnapshotBindingChangedError("catalogue returned an unsupported lifecycle state")
        return entry

    def _recheck_binding(self, expected: CloudSnapshotRefV2) -> None:
        try:
            current = self._get_exact_entry(expected.snapshot_id)
        except SnapshotCatalogueError as exc:
            raise SnapshotBindingChangedError(
                "the exact snapshot became unavailable while materialization was in flight"
            ) from exc
        if current.snapshot.to_dict() != expected.to_dict():
            raise SnapshotBindingChangedError(
                "the exact snapshot identity changed while materialization was in flight"
            )

    def _read_object(self, object_ref: ImmutableObjectVersion) -> ObjectStoreReadResult:
        try:
            result = self._object_store.read_exact(
                object_ref.key,
                object_ref.version_id,
            )
        except ObjectStoreObjectNotFoundError as exc:
            raise SnapshotObjectUnavailableError(
                "the exact immutable object version is unavailable"
            ) from exc
        except SnapshotMaterializationError:
            raise
        except Exception as exc:
            raise SnapshotMaterializationError(
                "the read-only object-store port failed the exact-version read"
            ) from exc

        if type(result) is not ObjectStoreReadResult:
            raise SnapshotObjectVersionMismatchError(
                "read port did not return the required exact-version result type"
            )
        if result.key != object_ref.key or result.version_id != object_ref.version_id:
            raise SnapshotObjectVersionMismatchError(
                "read port returned a different object key or immutable version ID"
            )
        if not isinstance(result.payload, bytes):
            raise SnapshotObjectIntegrityError("read port payload must be exact bytes")
        if (
            len(result.payload) != object_ref.byte_size
            or _sha256(result.payload) != object_ref.sha256
        ):
            raise SnapshotObjectIntegrityError(
                "exact object payload does not match the outer SHA-256 and byte-size identity"
            )
        return result

    @staticmethod
    def _write_workspace(
        workspace: str | Path,
        *,
        snapshot_id: str,
        source_members: Mapping[str, bytes],
        index_members: Mapping[str, bytes],
    ) -> tuple[Path, Path, Path, Path, Path, Path]:
        base = Path(workspace).expanduser()
        if base.is_symlink() or not base.exists() or not base.is_dir():
            raise SnapshotWorkspaceError(
                "workspace must be an existing real directory, not a symlink"
            )
        try:
            base = base.resolve(strict=True)
            workspace_root = Path(
                tempfile.mkdtemp(
                    prefix="sfra-snapshot-" + snapshot_id[-12:] + "-",
                    dir=base,
                )
            )
        except OSError as exc:
            raise SnapshotWorkspaceError("could not create a unique request workspace") from exc

        source_root = workspace_root / "source"
        index_root = workspace_root / "index"
        try:
            source_root.mkdir()
            index_root.mkdir()
            written_paths: set[PurePosixPath] = set()
            for archive_path, payload in source_members.items():
                if not archive_path.startswith(SOURCE_ARCHIVE_PREFIX):
                    raise SnapshotMaterializationIntegrityError(
                        "source archive contains a member outside the source/ prefix"
                    )
                relative = archive_path[len(SOURCE_ARCHIVE_PREFIX):]
                pure = PurePosixPath(relative)
                if (
                    pure.is_absolute()
                    or not pure.parts
                    or any(part in ("", ".", "..") for part in pure.parts)
                    or "\\" in relative
                ):
                    raise SnapshotMaterializationIntegrityError(
                        "source archive contains an unsafe relative path"
                    )
                if pure in written_paths or any(parent in written_paths for parent in pure.parents):
                    raise SnapshotMaterializationIntegrityError(
                        "source archive paths collide during materialization"
                    )
                written_paths.add(pure)
                target = source_root.joinpath(*pure.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as stream:
                    stream.write(payload)

            database_path = index_root / E1_DATABASE_PATH
            database_path.parent.mkdir(parents=True, exist_ok=True)
            with database_path.open("xb") as stream:
                stream.write(index_members[E1_DATABASE_PATH])

            attestation_path = index_root / ATTESTATION_PATH
            with attestation_path.open("xb") as stream:
                stream.write(index_members[ATTESTATION_PATH])

            inventory_path = index_root / INVENTORY_PATH
            with inventory_path.open("xb") as stream:
                stream.write(index_members[INVENTORY_PATH])
        except (OSError, KeyError) as exc:
            shutil.rmtree(workspace_root, ignore_errors=True)
            raise SnapshotWorkspaceError(
                "could not write the verified snapshot into the disposable workspace"
            ) from exc
        except Exception:
            shutil.rmtree(workspace_root, ignore_errors=True)
            raise

        return (
            workspace_root,
            source_root,
            index_root,
            database_path,
            attestation_path,
            inventory_path,
        )


__all__ = [
    "CloudSnapshotMaterializer",
    "InMemoryVersionedObjectStore",
    "MaterializedCloudSnapshot",
    "ObjectStoreObjectNotFoundError",
    "ObjectStoreReadPort",
    "ObjectStoreReadResult",
    "SnapshotBindingChangedError",
    "SnapshotMaterializationError",
    "SnapshotMaterializationIntegrityError",
    "SnapshotObjectIntegrityError",
    "SnapshotObjectUnavailableError",
    "SnapshotObjectVersionMismatchError",
    "SnapshotWorkspaceError",
]
