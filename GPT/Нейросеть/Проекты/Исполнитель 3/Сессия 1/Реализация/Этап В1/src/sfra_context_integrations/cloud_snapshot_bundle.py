"""Synthetic immutable snapshot bundle builder, inventory and verifier.

The builder prepares content-addressed payloads only. It never uploads objects or
assigns provider version IDs; a later write port supplies those IDs before the
outer CloudSnapshotRef v2 manifest is finalized.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import stat
import tempfile
from typing import Any, Iterable, Mapping
from zipfile import BadZipFile, ZIP_STORED, ZipFile, ZipInfo

from .cloud_snapshot_v2 import (
    BuiltCloudSnapshotV2,
    CloudSnapshotContractError,
    CloudSnapshotManifestV1,
    GitCommitSourceRevision,
    ImmutableImportSourceRevision,
    ImmutableObjectVersion,
    IndexerIdentity,
    SourceRevision,
    SqliteSchemaIdentity,
    build_cloud_snapshot_v2,
)

BUNDLE_FORMAT = "sfra.cloud-snapshot-bundle.v1"
MARKDOWN_INVENTORY_FORMAT = "sfra.e1.markdown-inventory.v1"
E1_CLOUD_INDEX_ATTESTATION_FORMAT = "sfra.e1.cloud-index-attestation.v1"
E1_SCHEMA_INFO_VERSION = 2
E1_DATABASE_PATH = "state/structure.sqlite3"
INVENTORY_PATH = "markdown-inventory.json"
ATTESTATION_PATH = "attestation.json"
SOURCE_ARCHIVE_PREFIX = "source/"


class CloudSnapshotBundleError(ValueError):
    """Base class for bundle preparation and verification failures."""


class UnsafeSourceTreeError(CloudSnapshotBundleError):
    """The source tree contains unsafe paths, links or special files."""


class BundleIntegrityError(CloudSnapshotBundleError):
    """A source/index bundle payload or internal identity is inconsistent."""


class E1VerifierUnavailableError(CloudSnapshotBundleError):
    """The public E1 verifier is not installed for a Git-backed fixture."""


@dataclass(frozen=True, slots=True)
class MarkdownDocument:
    path: str
    byte_size: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "byte_size": self.byte_size, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class MarkdownInventory:
    documents: tuple[MarkdownDocument, ...]
    canonical_bytes: bytes
    sha256: str

    @property
    def document_count(self) -> int:
        return len(self.documents)


@dataclass(frozen=True, slots=True)
class PreparedBundleObject:
    """A complete immutable payload awaiting a separate upload/version assignment."""

    key: str
    payload: bytes
    sha256: str
    byte_size: int


@dataclass(frozen=True, slots=True)
class PreparedCloudSnapshotBundle:
    """Two verified payloads plus the E1 inventory/attestation needed by #125."""

    bundle_format: str
    source_revision: SourceRevision
    source_object: PreparedBundleObject
    index_object: PreparedBundleObject
    markdown_inventory_bytes: bytes
    markdown_inventory_sha256: str
    markdown_document_count: int
    attestation_bytes: bytes
    indexer_identity: IndexerIdentity
    sqlite_schema_identity: SqliteSchemaIdentity
    source_file_count: int
    document_count: int
    active_document_count: int
    node_count: int
    active_node_count: int
    passage_count: int
    e1_legacy_verifier: str

    def build_cloud_snapshot_v2(
        self,
        *,
        source_version_id: str,
        index_version_id: str,
    ) -> BuiltCloudSnapshotV2:
        """Bind actual immutable upload version IDs after the #125 writer succeeds."""
        _validate_prepared_bundle(self)
        manifest = CloudSnapshotManifestV1(
            source_revision=self.source_revision,
            source_bundle=ImmutableObjectVersion(
                key=self.source_object.key,
                version_id=source_version_id,
                sha256=self.source_object.sha256,
                byte_size=self.source_object.byte_size,
            ),
            index_bundle=ImmutableObjectVersion(
                key=self.index_object.key,
                version_id=index_version_id,
                sha256=self.index_object.sha256,
                byte_size=self.index_object.byte_size,
            ),
            indexer_identity=self.indexer_identity,
            sqlite_schema_identity=self.sqlite_schema_identity,
        )
        return build_cloud_snapshot_v2(manifest)


@dataclass(frozen=True, slots=True)
class BundleVerificationReport:
    bundle_format: str
    source_archive_sha256: str
    source_archive_byte_size: int
    index_archive_sha256: str
    index_archive_byte_size: int
    markdown_inventory_sha256: str
    markdown_document_count: int
    source_file_count: int
    active_document_count: int
    active_node_count: int
    schema_info_version: int
    e1_legacy_verifier: str


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


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
        raise CloudSnapshotBundleError("value cannot be encoded as canonical UTF-8 JSON") from exc


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BundleIntegrityError("canonical JSON contains a duplicate object key")
        result[key] = value
    return result


def _parse_canonical_json(raw: bytes, name: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                BundleIntegrityError(f"{name} contains unsupported JSON constant")
            ),
        )
    except BundleIntegrityError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleIntegrityError(f"{name} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or _canonical_json_bytes(value) != raw:
        raise BundleIntegrityError(f"{name} is not canonical JSON")
    return value


def _validate_relative_posix_path(path: str) -> str:
    if not isinstance(path, str) or not path or path.startswith("/") or "\\" in path or "\x00" in path:
        raise UnsafeSourceTreeError("source path must be a non-empty relative POSIX path")
    try:
        path.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise UnsafeSourceTreeError("source path is not valid UTF-8") from exc
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise UnsafeSourceTreeError("source path contains an empty or dot path component")
    if PurePosixPath(path).is_absolute():
        raise UnsafeSourceTreeError("absolute source paths are not allowed")
    return path


def _validate_object_key(key: str, name: str) -> str:
    if not isinstance(key, str) or not key or key.startswith("/") or "\\" in key:
        raise CloudSnapshotBundleError(f"{name} must be a non-empty relative POSIX object key")
    try:
        key.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise CloudSnapshotBundleError(f"{name} is not valid UTF-8") from exc
    if any(part in {"", ".", ".."} for part in key.split("/")):
        raise CloudSnapshotBundleError(f"{name} contains an unsafe path component")
    return key


def _collect_source_files(source_root: str | Path) -> tuple[tuple[str, bytes], ...]:
    requested_root = Path(source_root).expanduser()
    if requested_root.is_symlink():
        raise UnsafeSourceTreeError("source root must not be a symlink")
    try:
        root = requested_root.resolve(strict=True)
    except OSError as exc:
        raise UnsafeSourceTreeError("source root does not exist or cannot be resolved") from exc
    if not root.is_dir():
        raise UnsafeSourceTreeError("source root must be a directory")

    collected: list[tuple[str, bytes]] = []
    seen_paths: set[str] = set()

    def walk(directory: Path, prefix: str) -> None:
        try:
            with os.scandir(directory) as scan:
                entries = list(scan)
        except OSError as exc:
            raise UnsafeSourceTreeError("source directory cannot be enumerated") from exc

        try:
            entries.sort(key=lambda entry: entry.name.encode("utf-8", errors="strict"))
        except UnicodeEncodeError as exc:
            raise UnsafeSourceTreeError("source path contains invalid UTF-8") from exc

        for entry in entries:
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            relative = _validate_relative_posix_path(relative)
            if relative in seen_paths:
                raise UnsafeSourceTreeError("duplicate canonical source path")
            seen_paths.add(relative)

            try:
                if entry.is_symlink():
                    raise UnsafeSourceTreeError("symlinks are not allowed in the source tree")
                if entry.is_dir(follow_symlinks=False):
                    walk(Path(entry.path), relative)
                elif entry.is_file(follow_symlinks=False):
                    raw = Path(entry.path).read_bytes()
                    if PurePosixPath(relative).suffix.lower() == ".md":
                        raw.decode("utf-8", errors="strict")
                    collected.append((relative, raw))
                else:
                    raise UnsafeSourceTreeError("special files are not allowed in the source tree")
            except UnsafeSourceTreeError:
                raise
            except (OSError, UnicodeDecodeError) as exc:
                raise UnsafeSourceTreeError("source file is unreadable or invalid UTF-8 Markdown") from exc

    walk(root, "")
    collected.sort(key=lambda item: item[0].encode("utf-8", errors="strict"))
    return tuple(collected)


def _inventory_from_files(files: Iterable[tuple[str, bytes]]) -> MarkdownInventory:
    documents: list[MarkdownDocument] = []
    seen: set[str] = set()
    for relative_path, raw in files:
        path = _validate_relative_posix_path(relative_path)
        if path in seen:
            raise UnsafeSourceTreeError("duplicate canonical Markdown path")
        seen.add(path)
        if PurePosixPath(path).suffix.lower() != ".md":
            continue
        try:
            raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise UnsafeSourceTreeError("Markdown files must contain exact valid UTF-8 bytes") from exc
        documents.append(
            MarkdownDocument(path=path, byte_size=len(raw), sha256=_sha256(raw))
        )

    documents.sort(key=lambda item: item.path.encode("utf-8", errors="strict"))
    payload = {
        "format": MARKDOWN_INVENTORY_FORMAT,
        "documents": [item.to_dict() for item in documents],
    }
    canonical = _canonical_json_bytes(payload)
    return MarkdownInventory(
        documents=tuple(documents),
        canonical_bytes=canonical,
        sha256=_sha256(canonical),
    )


def build_markdown_inventory(source_root: str | Path) -> MarkdownInventory:
    """Inventory exactly the regular Markdown files selected by E1 index_vault()."""
    return _inventory_from_files(_collect_source_files(source_root))


def _deterministic_zip(files: Mapping[str, bytes]) -> bytes:
    stream = BytesIO()
    with ZipFile(stream, mode="w", compression=ZIP_STORED, strict_timestamps=True) as archive:
        for name in sorted(files, key=lambda value: value.encode("utf-8", errors="strict")):
            _validate_relative_posix_path(name)
            raw = files[name]
            if not isinstance(raw, bytes):
                raise CloudSnapshotBundleError("archive members must be bytes")
            info = ZipInfo(filename=name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_STORED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.flag_bits = 0
            info.extra = b""
            info.comment = b""
            archive.writestr(info, raw)
    return stream.getvalue()


def _read_deterministic_zip(raw: bytes, name: str) -> dict[str, bytes]:
    try:
        with ZipFile(BytesIO(raw), mode="r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if names != sorted(names, key=lambda value: value.encode("utf-8", errors="strict")):
                raise BundleIntegrityError(f"{name} members are not sorted canonically")
            if len(names) != len(set(names)):
                raise BundleIntegrityError(f"{name} contains duplicate archive paths")

            files: dict[str, bytes] = {}
            for info in infos:
                try:
                    member = _validate_relative_posix_path(info.filename)
                except UnsafeSourceTreeError as exc:
                    raise BundleIntegrityError(f"{name} contains an unsafe archive path") from exc
                if info.is_dir() or (info.external_attr >> 16) & stat.S_IFMT(0o170000) == stat.S_IFLNK:
                    raise BundleIntegrityError(f"{name} contains a non-regular archive member")
                mode = (info.external_attr >> 16) & 0o170000
                if mode not in (0, stat.S_IFREG):
                    raise BundleIntegrityError(f"{name} contains a special archive member")
                if info.flag_bits & 0x1:
                    raise BundleIntegrityError(f"{name} contains an encrypted archive member")
                payload = archive.read(info)
                if len(payload) != info.file_size:
                    raise BundleIntegrityError(f"{name} member size does not match its directory entry")
                files[member] = payload
            if _deterministic_zip(files) != raw:
                raise BundleIntegrityError(f"{name} is not a canonical deterministic ZIP archive")
            return files
    except BundleIntegrityError:
        raise
    except (BadZipFile, OSError, UnicodeEncodeError, RuntimeError) as exc:
        raise BundleIntegrityError(f"{name} is not a valid deterministic ZIP archive") from exc


def _validate_source_revision(source_revision: SourceRevision) -> SourceRevision:
    if type(source_revision) not in (GitCommitSourceRevision, ImmutableImportSourceRevision):
        raise CloudSnapshotBundleError("source_revision must be a tagged Git or immutable-import identity")
    try:
        # Reuse the public v2 constructor to validate the tagged revision and all source fields.
        if type(source_revision) is GitCommitSourceRevision:
            GitCommitSourceRevision(source_revision.commit_sha)
        else:
            ImmutableImportSourceRevision(source_revision.import_id)
    except (CloudSnapshotContractError, AttributeError, TypeError, ValueError) as exc:
        raise CloudSnapshotBundleError("source_revision is not a valid immutable identity") from exc
    return source_revision


def _validate_indexer_identity(identity: IndexerIdentity) -> IndexerIdentity:
    if type(identity) is not IndexerIdentity or identity.name != "sfra-structural-indexer":
        raise CloudSnapshotBundleError("indexer_identity must name sfra-structural-indexer")
    try:
        installed = version("sfra-structural-indexer")
    except PackageNotFoundError as exc:
        raise E1VerifierUnavailableError("the E1 indexer package is not installed") from exc
    if identity.version != installed:
        raise CloudSnapshotBundleError(
            "indexer_identity.version does not match the installed E1 distribution"
        )
    return identity


def _validate_sqlite_schema_identity(identity: SqliteSchemaIdentity) -> SqliteSchemaIdentity:
    if (
        type(identity) is not SqliteSchemaIdentity
        or identity.engine != "sqlite"
        or identity.schema_info_version != E1_SCHEMA_INFO_VERSION
    ):
        raise CloudSnapshotBundleError(
            "sqlite_schema_identity must bind sqlite schema_info.schema_version=2"
        )
    return identity


def _inspect_database_bytes(
    database_bytes: bytes,
    inventory: MarkdownInventory,
) -> dict[str, Any]:
    if not isinstance(database_bytes, bytes) or not database_bytes:
        raise BundleIntegrityError("SQLite snapshot is missing or empty")

    with tempfile.TemporaryDirectory(prefix="sfra-cloud-bundle-") as temporary:
        database_path = Path(temporary) / "structure.sqlite3"
        database_path.write_bytes(database_bytes)
        try:
            connection = sqlite3.connect(database_path.resolve().as_uri() + "?mode=ro", uri=True)
        except sqlite3.Error as exc:
            raise BundleIntegrityError("SQLite snapshot cannot be opened read-only") from exc

        try:
            connection.execute("PRAGMA query_only = ON")
            integrity = [row[0] for row in connection.execute("PRAGMA integrity_check").fetchall()]
            if integrity != ["ok"]:
                raise BundleIntegrityError("SQLite integrity_check did not return exactly ok")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise BundleIntegrityError("SQLite foreign_key_check found violations")

            schema_row = connection.execute(
                "SELECT schema_version FROM schema_info WHERE singleton = 1"
            ).fetchone()
            if schema_row is None or type(schema_row[0]) is not int:
                raise BundleIntegrityError("E1 schema_info.schema_version is missing or malformed")
            schema_info_version = int(schema_row[0])
            if schema_info_version != E1_SCHEMA_INFO_VERSION:
                raise BundleIntegrityError(
                    "SQLite schema_info.schema_version does not match the supported E1 v2 schema"
                )

            active_rows = connection.execute(
                "SELECT source_path, source_size_bytes, source_sha256, parser_name, "
                "parser_version, generation, status FROM documents WHERE status = 'active'"
            ).fetchall()
            expected_documents = {document.path: document for document in inventory.documents}
            observed_documents: dict[str, tuple[Any, ...]] = {}
            parser_pairs: set[tuple[str, str]] = set()
            for row in active_rows:
                path, size, digest, parser_name, parser_version, generation, status = row
                if not isinstance(path, str) or path in observed_documents:
                    raise BundleIntegrityError("active E1 documents contain an invalid or duplicate path")
                if type(size) is not int or size < 0:
                    raise BundleIntegrityError("active E1 document source_size_bytes is invalid")
                if not isinstance(digest, str) or not isinstance(parser_name, str) or not parser_name:
                    raise BundleIntegrityError("active E1 document identity is incomplete")
                if not isinstance(parser_version, str) or not parser_version:
                    raise BundleIntegrityError("active E1 parser version is missing")
                if type(generation) is not int or generation < 1 or status != "active":
                    raise BundleIntegrityError("active E1 document generation/status is invalid")
                observed_documents[path] = row
                parser_pairs.add((parser_name, parser_version))

            if set(observed_documents) != set(expected_documents):
                raise BundleIntegrityError(
                    "active E1 document paths do not equal the canonical Markdown inventory"
                )
            for path, row in observed_documents.items():
                document = expected_documents[path]
                if row[1] != document.byte_size or row[2] != document.sha256:
                    raise BundleIntegrityError(
                        "active E1 document size/hash does not match the canonical Markdown inventory"
                    )

            total_document_count = connection.execute(
                "SELECT COUNT(*) FROM documents"
            ).fetchone()[0]
            total_node_count = connection.execute(
                "SELECT COUNT(*) FROM structural_nodes"
            ).fetchone()[0]
            passage_count = connection.execute("SELECT COUNT(*) FROM passages").fetchone()[0]

            active_nodes = connection.execute(
                "SELECT node_id, content_hash, raw_text FROM structural_nodes "
                "WHERE status IN ('active', 'ambiguous') AND stale_generation IS NULL"
            ).fetchall()
            seen_node_ids: set[str] = set()
            for node_id, content_hash, raw_text in active_nodes:
                if not isinstance(node_id, str) or not node_id or node_id in seen_node_ids:
                    raise BundleIntegrityError("active E1 nodes contain missing or duplicate Node IDs")
                seen_node_ids.add(node_id)
                expected_hash = _sha256(raw_text.encode("utf-8", errors="strict")) if isinstance(raw_text, str) else None
                if content_hash != expected_hash:
                    raise BundleIntegrityError("active E1 node Content Hash does not match exact raw_text bytes")

            parser_identities = [
                {"name": name, "version": parser}
                for name, parser in sorted(
                    parser_pairs,
                    key=lambda pair: (pair[0].encode("utf-8"), pair[1].encode("utf-8")),
                )
            ]
            return {
                "schema_info_version": schema_info_version,
                "document_count": int(total_document_count),
                "active_document_count": len(active_rows),
                "node_count": int(total_node_count),
                "active_node_count": len(active_nodes),
                "passage_count": int(passage_count),
                "parser_identities": parser_identities,
            }
        except sqlite3.Error as exc:
            raise BundleIntegrityError("SQLite schema or index inspection failed") from exc
        finally:
            connection.close()


def _run_legacy_e1_verifier_if_compatible(
    database_bytes: bytes,
    source_revision: SourceRevision,
    database_sha256: str,
) -> str:
    if type(source_revision) is ImmutableImportSourceRevision:
        # E1's v1 state manifest is explicitly Git-commit-shaped. Never coerce import_id.
        return "skipped_immutable_import_requires_additive_e1_verifier"

    if type(source_revision) is not GitCommitSourceRevision:
        raise CloudSnapshotBundleError("unsupported tagged source revision")

    try:
        from sfra_indexer import verify_state_directory
    except ImportError as exc:
        raise E1VerifierUnavailableError(
            "public sfra_indexer.verify_state_directory is unavailable"
        ) from exc

    with tempfile.TemporaryDirectory(prefix="sfra-e1-state-v1-") as temporary:
        root = Path(temporary)
        state = root / "state"
        state.mkdir()
        (state / "structure.sqlite3").write_bytes(database_bytes)
        manifest = {
            "format_version": 1,
            "database": "state/structure.sqlite3",
            "database_sha256": database_sha256,
            "sqlite_schema_version": E1_SCHEMA_INFO_VERSION,
            "source_repository": "synthetic-fixture",
            "vault_ref": "synthetic-fixture",
            "vault_commit_sha": source_revision.commit_sha,
            "source_branch": "synthetic-fixture",
            "source_commit": source_revision.commit_sha,
            "indexer_version": "0.2.0",
            "workflow_run_id": "synthetic-fixture",
            "updated_at": "2000-01-01T00:00:00+00:00",
        }
        (state / "manifest.json").write_bytes(_canonical_json_bytes(manifest))
        try:
            verified = verify_state_directory(root)
        except Exception as exc:
            raise BundleIntegrityError(
                "public E1 v1 state verifier rejected the disposable Git-backed fixture"
            ) from exc
        if verified.get("database_sha256") != database_sha256:
            raise BundleIntegrityError("public E1 verifier returned a mismatched database digest")
    return "verified_with_public_e1_v1_git_state_api"


def _attestation_payload(
    *,
    source_revision: SourceRevision,
    inventory: MarkdownInventory,
    indexer_identity: IndexerIdentity,
    database_bytes: bytes,
    database_report: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "attestation_version": 1,
        "format": E1_CLOUD_INDEX_ATTESTATION_FORMAT,
        "source_revision": source_revision.to_dict(),
        "markdown_inventory": {
            "format": MARKDOWN_INVENTORY_FORMAT,
            "path": INVENTORY_PATH,
            "sha256": inventory.sha256,
            "document_count": inventory.document_count,
        },
        "indexer_identity": {
            "name": indexer_identity.name,
            "version": indexer_identity.version,
        },
        "parser_identities": database_report["parser_identities"],
        "sqlite_schema_identity": {
            "engine": "sqlite",
            "schema_info_version": database_report["schema_info_version"],
        },
        "database": {
            "path": E1_DATABASE_PATH,
            "sha256": _sha256(database_bytes),
            "byte_size": len(database_bytes),
        },
        "counts": {
            "document_count": database_report["document_count"],
            "active_document_count": database_report["active_document_count"],
            "node_count": database_report["node_count"],
            "active_node_count": database_report["active_node_count"],
            "passage_count": database_report["passage_count"],
        },
    }


def _validate_prepared_object(obj: PreparedBundleObject, name: str) -> None:
    if type(obj) is not PreparedBundleObject or not isinstance(obj.payload, bytes):
        raise BundleIntegrityError(f"{name} must be a PreparedBundleObject with byte payload")
    _validate_object_key(obj.key, f"{name}.key")
    if obj.byte_size != len(obj.payload) or obj.sha256 != _sha256(obj.payload):
        raise BundleIntegrityError(f"{name} payload hash/size does not match its descriptor")


def _validate_prepared_bundle(bundle: PreparedCloudSnapshotBundle) -> None:
    if type(bundle) is not PreparedCloudSnapshotBundle:
        raise BundleIntegrityError("bundle must be the exact PreparedCloudSnapshotBundle type")
    if bundle.bundle_format != BUNDLE_FORMAT:
        raise BundleIntegrityError("unsupported prepared bundle format")
    _validate_source_revision(bundle.source_revision)
    _validate_prepared_object(bundle.source_object, "source_object")
    _validate_prepared_object(bundle.index_object, "index_object")
    if not isinstance(bundle.markdown_inventory_bytes, bytes) or not isinstance(bundle.attestation_bytes, bytes):
        raise BundleIntegrityError("inventory/attestation payloads must be bytes")
    _validate_indexer_identity(bundle.indexer_identity)
    try:
        _validate_sqlite_schema_identity(bundle.sqlite_schema_identity)
    except (CloudSnapshotBundleError, AttributeError, TypeError, ValueError) as exc:
        raise BundleIntegrityError("sqlite_schema_identity is invalid") from exc


def build_prepared_cloud_snapshot_bundle(
    source_root: str | Path,
    index_database_path: str | Path,
    *,
    source_revision: SourceRevision,
    source_object_key: str,
    index_object_key: str,
    indexer_identity: IndexerIdentity,
    sqlite_schema_identity: SqliteSchemaIdentity,
) -> PreparedCloudSnapshotBundle:
    """Build and verify deterministic source/index payloads without uploading them."""
    source_revision = _validate_source_revision(source_revision)
    source_object_key = _validate_object_key(source_object_key, "source_object_key")
    index_object_key = _validate_object_key(index_object_key, "index_object_key")
    indexer_identity = _validate_indexer_identity(indexer_identity)
    sqlite_schema_identity = _validate_sqlite_schema_identity(sqlite_schema_identity)

    source_files = _collect_source_files(source_root)
    inventory = _inventory_from_files(source_files)
    source_members = {SOURCE_ARCHIVE_PREFIX + path: raw for path, raw in source_files}
    source_archive = _deterministic_zip(source_members)

    database_path = Path(index_database_path).expanduser()
    if database_path.is_symlink() or not database_path.is_file():
        raise BundleIntegrityError("E1 SQLite fixture must be a regular file, not a symlink")
    database_bytes = database_path.read_bytes()
    database_report = _inspect_database_bytes(database_bytes, inventory)
    if database_report["schema_info_version"] != sqlite_schema_identity.schema_info_version:
        raise BundleIntegrityError("E1 database schema_info version does not match v2 identity")
    legacy_verifier_status = _run_legacy_e1_verifier_if_compatible(
        database_bytes,
        source_revision,
        _sha256(database_bytes),
    )

    attestation = _attestation_payload(
        source_revision=source_revision,
        inventory=inventory,
        indexer_identity=indexer_identity,
        database_bytes=database_bytes,
        database_report=database_report,
    )
    attestation_bytes = _canonical_json_bytes(attestation)
    index_members = {
        ATTESTATION_PATH: attestation_bytes,
        INVENTORY_PATH: inventory.canonical_bytes,
        E1_DATABASE_PATH: database_bytes,
    }
    index_archive = _deterministic_zip(index_members)

    prepared = PreparedCloudSnapshotBundle(
        bundle_format=BUNDLE_FORMAT,
        source_revision=source_revision,
        source_object=PreparedBundleObject(
            key=source_object_key,
            payload=source_archive,
            sha256=_sha256(source_archive),
            byte_size=len(source_archive),
        ),
        index_object=PreparedBundleObject(
            key=index_object_key,
            payload=index_archive,
            sha256=_sha256(index_archive),
            byte_size=len(index_archive),
        ),
        markdown_inventory_bytes=inventory.canonical_bytes,
        markdown_inventory_sha256=inventory.sha256,
        markdown_document_count=inventory.document_count,
        attestation_bytes=attestation_bytes,
        indexer_identity=indexer_identity,
        sqlite_schema_identity=sqlite_schema_identity,
        source_file_count=len(source_files),
        document_count=database_report["document_count"],
        active_document_count=database_report["active_document_count"],
        node_count=database_report["node_count"],
        active_node_count=database_report["active_node_count"],
        passage_count=database_report["passage_count"],
        e1_legacy_verifier=legacy_verifier_status,
    )
    verify_prepared_cloud_snapshot_bundle(prepared)
    return prepared


def verify_prepared_cloud_snapshot_bundle(
    bundle: PreparedCloudSnapshotBundle,
) -> BundleVerificationReport:
    """Recheck exact archive bytes, inventory, attestation and SQLite before upload."""
    _validate_prepared_bundle(bundle)
    source_members = _read_deterministic_zip(bundle.source_object.payload, "source bundle")
    if not source_members or any(not name.startswith(SOURCE_ARCHIVE_PREFIX) for name in source_members):
        raise BundleIntegrityError("source archive has an unexpected member layout")
    source_files: list[tuple[str, bytes]] = []
    for name, raw in source_members.items():
        relative = name[len(SOURCE_ARCHIVE_PREFIX):]
        relative = _validate_relative_posix_path(relative)
        source_files.append((relative, raw))
    inventory = _inventory_from_files(source_files)
    if (
        inventory.canonical_bytes != bundle.markdown_inventory_bytes
        or inventory.sha256 != bundle.markdown_inventory_sha256
        or inventory.document_count != bundle.markdown_document_count
        or len(source_files) != bundle.source_file_count
    ):
        raise BundleIntegrityError("source archive and canonical Markdown inventory disagree")

    index_members = _read_deterministic_zip(bundle.index_object.payload, "index bundle")
    if set(index_members) != {ATTESTATION_PATH, INVENTORY_PATH, E1_DATABASE_PATH}:
        raise BundleIntegrityError("index archive has missing or unexpected members")
    if index_members[INVENTORY_PATH] != bundle.markdown_inventory_bytes:
        raise BundleIntegrityError("index archive inventory bytes do not match the descriptor")
    if index_members[ATTESTATION_PATH] != bundle.attestation_bytes:
        raise BundleIntegrityError("index archive attestation bytes do not match the descriptor")

    parsed_inventory = _parse_canonical_json(index_members[INVENTORY_PATH], "Markdown inventory")
    if parsed_inventory != {
        "format": MARKDOWN_INVENTORY_FORMAT,
        "documents": [item.to_dict() for item in inventory.documents],
    }:
        raise BundleIntegrityError("embedded Markdown inventory is inconsistent")

    database_bytes = index_members[E1_DATABASE_PATH]
    database_report = _inspect_database_bytes(database_bytes, inventory)
    if database_report["schema_info_version"] != bundle.sqlite_schema_identity.schema_info_version:
        raise BundleIntegrityError("SQLite schema_info version does not match the descriptor")
    legacy_verifier_status = _run_legacy_e1_verifier_if_compatible(
        database_bytes,
        bundle.source_revision,
        _sha256(database_bytes),
    )
    expected_attestation = _attestation_payload(
        source_revision=bundle.source_revision,
        inventory=inventory,
        indexer_identity=bundle.indexer_identity,
        database_bytes=database_bytes,
        database_report=database_report,
    )
    expected_attestation_bytes = _canonical_json_bytes(expected_attestation)
    if bundle.attestation_bytes != expected_attestation_bytes:
        raise BundleIntegrityError("E1 cloud-index attestation does not match inventory/database identity")
    parsed_attestation = _parse_canonical_json(bundle.attestation_bytes, "E1 cloud-index attestation")
    if parsed_attestation != expected_attestation:
        raise BundleIntegrityError("E1 cloud-index attestation fields are inconsistent")

    observed_counts = {
        "document_count": database_report["document_count"],
        "active_document_count": database_report["active_document_count"],
        "node_count": database_report["node_count"],
        "active_node_count": database_report["active_node_count"],
        "passage_count": database_report["passage_count"],
    }
    expected_counts = {
        "document_count": bundle.document_count,
        "active_document_count": bundle.active_document_count,
        "node_count": bundle.node_count,
        "active_node_count": bundle.active_node_count,
        "passage_count": bundle.passage_count,
    }
    if observed_counts != expected_counts:
        raise BundleIntegrityError("prepared bundle count metadata does not match its E1 database")

    return BundleVerificationReport(
        bundle_format=BUNDLE_FORMAT,
        source_archive_sha256=bundle.source_object.sha256,
        source_archive_byte_size=bundle.source_object.byte_size,
        index_archive_sha256=bundle.index_object.sha256,
        index_archive_byte_size=bundle.index_object.byte_size,
        markdown_inventory_sha256=inventory.sha256,
        markdown_document_count=inventory.document_count,
        source_file_count=len(source_files),
        active_document_count=database_report["active_document_count"],
        active_node_count=database_report["active_node_count"],
        schema_info_version=database_report["schema_info_version"],
        e1_legacy_verifier=legacy_verifier_status,
    )


__all__ = [
    "ATTESTATION_PATH",
    "BUNDLE_FORMAT",
    "BundleIntegrityError",
    "BundleVerificationReport",
    "CloudSnapshotBundleError",
    "E1_CLOUD_INDEX_ATTESTATION_FORMAT",
    "E1_DATABASE_PATH",
    "E1_SCHEMA_INFO_VERSION",
    "E1VerifierUnavailableError",
    "INVENTORY_PATH",
    "MARKDOWN_INVENTORY_FORMAT",
    "MarkdownDocument",
    "MarkdownInventory",
    "PreparedBundleObject",
    "PreparedCloudSnapshotBundle",
    "UnsafeSourceTreeError",
    "build_markdown_inventory",
    "build_prepared_cloud_snapshot_bundle",
    "verify_prepared_cloud_snapshot_bundle",
]
