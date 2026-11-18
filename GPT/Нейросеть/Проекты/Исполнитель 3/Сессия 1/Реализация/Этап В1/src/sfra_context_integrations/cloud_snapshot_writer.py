"""Provider-neutral immutable object writer and synthetic in-memory adapter."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import re
from threading import RLock
from typing import Protocol

from .cloud_snapshot_bundle import (
    PreparedCloudSnapshotBundle,
    PreparedBundleObject,
    verify_prepared_cloud_snapshot_bundle,
)
from .cloud_snapshot_v2 import BuiltCloudSnapshotV2, CloudSnapshotContractError

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ObjectStoreWriteError(RuntimeError):
    """Base class for typed immutable object write failures."""


class ObjectStoreWriteContractError(ObjectStoreWriteError):
    """The requested immutable write violates the port contract."""


class ObjectStoreConditionalConflictError(ObjectStoreWriteError):
    """A key already holds different immutable bytes and cannot be overwritten."""


class ObjectStorePartialWriteError(ObjectStoreWriteError):
    """A partial payload was written without a valid immutable acknowledgement."""


class ObjectStoreAcknowledgementError(ObjectStoreWriteError):
    """The storage port did not acknowledge the immutable write."""


class ObjectStoreReadBackError(ObjectStoreWriteError):
    """The exact-version read-back did not match the prepared payload."""


class PreparedBundleRejectedError(ObjectStoreWriteError):
    """The prepared bundle failed its public verification boundary."""


class InMemoryWriteFault(str, Enum):
    PARTIAL_WRITE = "partial_write"
    MISSING_ACKNOWLEDGEMENT = "missing_acknowledgement"
    CORRUPT_READ_BACK = "corrupt_read_back"


@dataclass(frozen=True, slots=True)
class ObjectWriteReceipt:
    key: str
    version_id: str
    sha256: str
    byte_size: int

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key:
            raise ObjectStoreWriteContractError("receipt key must be non-empty")
        if not isinstance(self.version_id, str) or not self.version_id or self.version_id != self.version_id.strip():
            raise ObjectStoreWriteContractError("receipt version_id must be an exact non-empty opaque value")
        if not isinstance(self.sha256, str) or not _SHA256_RE.fullmatch(self.sha256):
            raise ObjectStoreWriteContractError("receipt sha256 must be lowercase sha256:<64 hex>")
        if type(self.byte_size) is not int or self.byte_size <= 0:
            raise ObjectStoreWriteContractError("receipt byte_size must be a positive integer")


class ObjectStoreWritePort(Protocol):
    """Small write-side contract; deliberately has no list, overwrite or delete API."""

    def put_if_absent(
        self,
        key: str,
        payload: bytes,
        *,
        expected_sha256: str,
        expected_byte_size: int,
    ) -> ObjectWriteReceipt | None: ...

    def read_exact(self, key: str, version_id: str) -> bytes | None: ...


@dataclass(frozen=True, slots=True)
class UploadedCloudSnapshotBundle:
    prepared_bundle: PreparedCloudSnapshotBundle
    source_receipt: ObjectWriteReceipt
    index_receipt: ObjectWriteReceipt
    built_snapshot: BuiltCloudSnapshotV2

    def __post_init__(self) -> None:
        if type(self.prepared_bundle) is not PreparedCloudSnapshotBundle:
            raise ObjectStoreWriteContractError("prepared_bundle must be the exact prepared bundle type")
        if self.source_receipt.key != self.prepared_bundle.source_object.key:
            raise ObjectStoreWriteContractError("source receipt key differs from the prepared descriptor")
        if self.index_receipt.key != self.prepared_bundle.index_object.key:
            raise ObjectStoreWriteContractError("index receipt key differs from the prepared descriptor")
        _check_receipt_matches_object(self.source_receipt, self.prepared_bundle.source_object)
        _check_receipt_matches_object(self.index_receipt, self.prepared_bundle.index_object)
        if self.built_snapshot.ref.source_bundle.version_id != self.source_receipt.version_id:
            raise ObjectStoreWriteContractError("v2 source version differs from the verified write receipt")
        if self.built_snapshot.ref.index_bundle.version_id != self.index_receipt.version_id:
            raise ObjectStoreWriteContractError("v2 index version differs from the verified write receipt")

    @property
    def snapshot_id(self) -> str:
        return self.built_snapshot.ref.snapshot_id

    @property
    def snapshot_ref(self):
        return self.built_snapshot.ref


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _validate_key(key: str) -> str:
    if not isinstance(key, str) or not key or key.startswith("/") or "\\" in key or "\x00" in key:
        raise ObjectStoreWriteContractError("object key must be a non-empty relative POSIX path")
    if any(part in {"", ".", ".."} for part in key.split("/")):
        raise ObjectStoreWriteContractError("object key contains an unsafe path component")
    try:
        key.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ObjectStoreWriteContractError("object key is not valid UTF-8") from exc
    return key


def _validate_expected_payload(
    key: str, payload: bytes, expected_sha256: str, expected_byte_size: int
) -> None:
    _validate_key(key)
    if not isinstance(payload, bytes) or not payload:
        raise ObjectStoreWriteContractError("immutable object payload must be non-empty bytes")
    if not isinstance(expected_sha256, str) or not _SHA256_RE.fullmatch(expected_sha256):
        raise ObjectStoreWriteContractError("expected_sha256 must be lowercase sha256:<64 hex>")
    if type(expected_byte_size) is not int or expected_byte_size <= 0:
        raise ObjectStoreWriteContractError("expected_byte_size must be a positive integer")
    if len(payload) != expected_byte_size or _sha256(payload) != expected_sha256:
        raise ObjectStoreWriteContractError("payload bytes do not match the exact expected hash/size")


def _check_receipt_matches_object(receipt: ObjectWriteReceipt, obj: PreparedBundleObject) -> None:
    if type(receipt) is not ObjectWriteReceipt:
        raise ObjectStoreAcknowledgementError("write acknowledgement has an unsupported type")
    if (
        receipt.key != obj.key
        or receipt.sha256 != obj.sha256
        or receipt.byte_size != obj.byte_size
        or not receipt.version_id
    ):
        raise ObjectStoreAcknowledgementError("write acknowledgement does not match the prepared object")


def _put_and_verify_exact(
    store: ObjectStoreWritePort, obj: PreparedBundleObject
) -> ObjectWriteReceipt:
    _validate_expected_payload(obj.key, obj.payload, obj.sha256, obj.byte_size)
    try:
        receipt = store.put_if_absent(
            obj.key,
            obj.payload,
            expected_sha256=obj.sha256,
            expected_byte_size=obj.byte_size,
        )
    except ObjectStoreWriteError:
        raise
    except Exception as exc:
        raise ObjectStoreWriteError("immutable object write failed without a trusted acknowledgement") from exc
    if receipt is None:
        raise ObjectStoreAcknowledgementError("immutable object write returned no acknowledgement")
    _check_receipt_matches_object(receipt, obj)
    try:
        observed = store.read_exact(receipt.key, receipt.version_id)
    except ObjectStoreWriteError:
        raise
    except Exception as exc:
        raise ObjectStoreReadBackError("exact immutable object read-back failed") from exc
    if not isinstance(observed, bytes):
        raise ObjectStoreReadBackError("exact immutable object version is missing on read-back")
    if observed != obj.payload or len(observed) != obj.byte_size or _sha256(observed) != obj.sha256:
        raise ObjectStoreReadBackError("exact immutable object read-back hash/size/bytes mismatch")
    return receipt


def write_prepared_cloud_snapshot_bundle(
    bundle: PreparedCloudSnapshotBundle,
    store: ObjectStoreWritePort,
) -> UploadedCloudSnapshotBundle:
    """Write both prepared objects immutably, read each exact version back, then bind v2."""
    if type(bundle) is not PreparedCloudSnapshotBundle:
        raise PreparedBundleRejectedError("writer accepts only PreparedCloudSnapshotBundle")
    if not callable(getattr(store, "put_if_absent", None)) or not callable(getattr(store, "read_exact", None)):
        raise ObjectStoreWriteContractError("store does not implement the minimal immutable write port")
    try:
        verify_prepared_cloud_snapshot_bundle(bundle)
    except Exception as exc:
        raise PreparedBundleRejectedError("prepared bundle failed public verification before upload") from exc

    # A failure on the second object may leave the first immutable object orphaned.
    # No delete/rollback operation is available or attempted; no v2 identity is returned.
    source_receipt = _put_and_verify_exact(store, bundle.source_object)
    index_receipt = _put_and_verify_exact(store, bundle.index_object)

    try:
        built = bundle.build_cloud_snapshot_v2(
            source_version_id=source_receipt.version_id,
            index_version_id=index_receipt.version_id,
        )
    except (CloudSnapshotContractError, Exception) as exc:
        raise ObjectStoreWriteContractError("verified object receipts could not be bound to CloudSnapshotRef v2") from exc
    return UploadedCloudSnapshotBundle(
        prepared_bundle=bundle,
        source_receipt=source_receipt,
        index_receipt=index_receipt,
        built_snapshot=built,
    )


@dataclass(frozen=True, slots=True)
class _StoredObject:
    receipt: ObjectWriteReceipt
    payload: bytes


class InMemoryImmutableObjectStore:
    """Disposable put-if-absent store with one-shot fault injection for unit tests."""

    def __init__(
        self,
        *,
        faults: dict[str, InMemoryWriteFault | str] | None = None,
    ) -> None:
        self._objects: dict[str, _StoredObject] = {}
        self._faults: dict[str, InMemoryWriteFault] = {}
        self._corrupt_readback_for: set[tuple[str, str]] = set()
        self._lock = RLock()
        for key, fault in (faults or {}).items():
            try:
                self._faults[_validate_key(key)] = InMemoryWriteFault(fault)
            except ValueError as exc:
                raise ObjectStoreWriteContractError("unsupported in-memory write fault") from exc

    def put_if_absent(
        self,
        key: str,
        payload: bytes,
        *,
        expected_sha256: str,
        expected_byte_size: int,
    ) -> ObjectWriteReceipt | None:
        _validate_expected_payload(key, payload, expected_sha256, expected_byte_size)
        with self._lock:
            existing = self._objects.get(key)
            if existing is not None:
                if existing.payload != payload:
                    raise ObjectStoreConditionalConflictError(
                        "immutable object key already contains different bytes; overwrite is forbidden"
                    )
                if (
                    existing.receipt.sha256 != expected_sha256
                    or existing.receipt.byte_size != expected_byte_size
                ):
                    raise ObjectStoreConditionalConflictError(
                        "existing immutable object metadata conflicts with the requested payload"
                    )
                return existing.receipt

            fault = self._faults.pop(key, None)
            if fault is InMemoryWriteFault.PARTIAL_WRITE:
                partial = payload[: max(1, len(payload) // 2)]
                partial_digest = _sha256(partial)
                partial_receipt = ObjectWriteReceipt(
                    key=key, version_id="memory-partial:" + partial_digest.removeprefix("sha256:"),
                    sha256=partial_digest, byte_size=len(partial),
                )
                self._objects[key] = _StoredObject(partial_receipt, partial)
                raise ObjectStorePartialWriteError(
                    "injected partial immutable write; no valid receipt was returned"
                )

            version_id = "memory-v1:" + hashlib.sha256(
                (key + "\\0" + expected_sha256).encode("utf-8")
            ).hexdigest()
            receipt = ObjectWriteReceipt(
                key=key, version_id=version_id, sha256=expected_sha256, byte_size=expected_byte_size
            )
            self._objects[key] = _StoredObject(receipt, payload)

            if fault is InMemoryWriteFault.MISSING_ACKNOWLEDGEMENT:
                return None
            if fault is InMemoryWriteFault.CORRUPT_READ_BACK:
                self._corrupt_readback_for.add((key, version_id))
            return receipt

    def read_exact(self, key: str, version_id: str) -> bytes | None:
        key = _validate_key(key)
        if not isinstance(version_id, str) or not version_id:
            raise ObjectStoreWriteContractError("read_exact requires an opaque immutable version ID")
        with self._lock:
            stored = self._objects.get(key)
            if stored is None or stored.receipt.version_id != version_id:
                return None
            fault_key = (key, version_id)
            if fault_key in self._corrupt_readback_for:
                self._corrupt_readback_for.remove(fault_key)
                return stored.payload + b"corrupt-readback"
            return stored.payload

    def stored_object_count(self) -> int:
        """Test-only aggregate; the public protocol has no list operation."""
        with self._lock:
            return len(self._objects)


__all__ = [
    "InMemoryImmutableObjectStore",
    "InMemoryWriteFault",
    "ObjectStoreAcknowledgementError",
    "ObjectStoreConditionalConflictError",
    "ObjectStorePartialWriteError",
    "ObjectStoreReadBackError",
    "ObjectStoreWriteContractError",
    "ObjectStoreWriteError",
    "ObjectStoreWritePort",
    "ObjectWriteReceipt",
    "UploadedCloudSnapshotBundle",
    "write_prepared_cloud_snapshot_bundle",
]
