"""Provider-neutral snapshot catalogue state machine with an in-memory adapter."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import re
from threading import RLock
from typing import Protocol

from .cloud_snapshot_v2 import (
    CloudSnapshotContractError,
    CloudSnapshotRefV2,
    cloud_snapshot_ref_v2_from_dict,
)

_SNAPSHOT_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class SnapshotCatalogueError(RuntimeError):
    """Base class for typed snapshot catalogue outcomes."""


class InvalidSnapshotIdentityError(SnapshotCatalogueError):
    """The supplied object is not a valid canonical CloudSnapshotRefV2."""


class InvalidSnapshotIdError(SnapshotCatalogueError):
    """An exact sha256 snapshot ID was not supplied."""


class SnapshotNotFoundError(SnapshotCatalogueError):
    """No catalogue entry exists for the exact snapshot ID."""


class SnapshotRetiredError(SnapshotCatalogueError):
    """The exact snapshot exists but has been retired and is unavailable."""


class SnapshotTransitionError(SnapshotCatalogueError):
    """The requested catalogue state transition is not permitted."""


class SnapshotCatalogueConflictError(SnapshotCatalogueError):
    """An existing snapshot ID is associated with a different identity."""


class SnapshotCatalogueCASConflictError(SnapshotCatalogueError):
    """The catalogue generation or active identity changed before mutation."""


class SnapshotCatalogueInvariantError(SnapshotCatalogueError):
    """The in-memory catalogue contains an impossible internal state."""


class SnapshotLifecycleState(str, Enum):
    STAGED = "STAGED"
    VERIFIED = "VERIFIED"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


@dataclass(frozen=True, slots=True)
class SnapshotCatalogueEntry:
    snapshot: CloudSnapshotRefV2
    state: SnapshotLifecycleState
    created_generation: int
    updated_generation: int


@dataclass(frozen=True, slots=True)
class SnapshotCatalogueState:
    generation: int
    active_snapshot_id: str | None


class SnapshotCataloguePort(Protocol):
    """Minimal catalogue port with exact identities and CAS lifecycle methods."""

    def stage(self, snapshot: CloudSnapshotRefV2) -> SnapshotCatalogueEntry: ...
    def get_exact(self, snapshot_id: str) -> SnapshotCatalogueEntry: ...
    def mark_verified(self, snapshot_id: str) -> SnapshotCatalogueEntry: ...
    def read_state(self) -> SnapshotCatalogueState: ...
    def activate(
        self,
        snapshot_id: str,
        *,
        expected_generation: int,
        expected_active_snapshot_id: str | None,
    ) -> SnapshotCatalogueEntry: ...
    def retire(
        self,
        snapshot_id: str,
        *,
        expected_generation: int,
        expected_active_snapshot_id: str | None,
    ) -> SnapshotCatalogueEntry: ...


def _validate_snapshot(snapshot: CloudSnapshotRefV2) -> CloudSnapshotRefV2:
    if type(snapshot) is not CloudSnapshotRefV2:
        raise InvalidSnapshotIdentityError(
            "snapshot must be the exact CloudSnapshotRefV2 type"
        )
    try:
        canonical = cloud_snapshot_ref_v2_from_dict(snapshot.to_dict())
    except (CloudSnapshotContractError, AttributeError, KeyError, TypeError, ValueError) as exc:
        raise InvalidSnapshotIdentityError(
            "snapshot is not a valid canonical CloudSnapshotRefV2"
        ) from exc
    if canonical != snapshot:
        raise InvalidSnapshotIdentityError(
            "snapshot identity does not round-trip through its canonical representation"
        )
    return canonical


def _validate_snapshot_id(snapshot_id: str) -> str:
    if not isinstance(snapshot_id, str) or not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise InvalidSnapshotIdError(
            "snapshot_id must be an exact lowercase sha256:<64 hex> identity"
        )
    return snapshot_id


def _validate_expected_generation(value: int) -> int:
    if type(value) is not int or value < 0:
        raise SnapshotCatalogueCASConflictError(
            "expected_generation must be a non-negative integer"
        )
    return value


def _validate_expected_active_id(value: str | None) -> str | None:
    if value is None:
        return None
    return _validate_snapshot_id(value)


class InMemorySnapshotCatalogue:
    """Thread-safe disposable reference adapter for the catalogue protocol."""

    def __init__(self) -> None:
        self._entries: dict[str, SnapshotCatalogueEntry] = {}
        self._generation = 0
        self._active_snapshot_id: str | None = None
        self._lock = RLock()

    def read_state(self) -> SnapshotCatalogueState:
        with self._lock:
            return SnapshotCatalogueState(
                generation=self._generation,
                active_snapshot_id=self._active_snapshot_id,
            )

    def stage(self, snapshot: CloudSnapshotRefV2) -> SnapshotCatalogueEntry:
        canonical = _validate_snapshot(snapshot)
        snapshot_id = canonical.snapshot_id
        with self._lock:
            existing = self._entries.get(snapshot_id)
            if existing is not None:
                if existing.snapshot != canonical:
                    raise SnapshotCatalogueConflictError(
                        "snapshot_id is already bound to a different canonical identity"
                    )
                if existing.state is SnapshotLifecycleState.RETIRED:
                    raise SnapshotRetiredError(
                        "a retired snapshot_id cannot be staged again"
                    )
                return existing

            self._generation += 1
            entry = SnapshotCatalogueEntry(
                snapshot=canonical,
                state=SnapshotLifecycleState.STAGED,
                created_generation=self._generation,
                updated_generation=self._generation,
            )
            self._entries[snapshot_id] = entry
            return entry

    def get_exact(self, snapshot_id: str) -> SnapshotCatalogueEntry:
        key = _validate_snapshot_id(snapshot_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                raise SnapshotNotFoundError(
                    "no catalogue entry exists for the requested exact snapshot_id"
                )
            if entry.state is SnapshotLifecycleState.RETIRED:
                raise SnapshotRetiredError(
                    "the requested snapshot has been retired"
                )
            return entry

    def mark_verified(self, snapshot_id: str) -> SnapshotCatalogueEntry:
        key = _validate_snapshot_id(snapshot_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                raise SnapshotNotFoundError(
                    "no catalogue entry exists for the requested exact snapshot_id"
                )
            if entry.state is SnapshotLifecycleState.RETIRED:
                raise SnapshotRetiredError(
                    "a retired snapshot cannot be marked verified"
                )
            if entry.state in (SnapshotLifecycleState.VERIFIED, SnapshotLifecycleState.ACTIVE):
                return entry
            if entry.state is not SnapshotLifecycleState.STAGED:
                raise SnapshotTransitionError(
                    "only STAGED snapshots may transition to VERIFIED"
                )
            self._generation += 1
            verified = replace(
                entry,
                state=SnapshotLifecycleState.VERIFIED,
                updated_generation=self._generation,
            )
            self._entries[key] = verified
            return verified

    def activate(
        self,
        snapshot_id: str,
        *,
        expected_generation: int,
        expected_active_snapshot_id: str | None,
    ) -> SnapshotCatalogueEntry:
        key = _validate_snapshot_id(snapshot_id)
        expected_generation = _validate_expected_generation(expected_generation)
        expected_active_snapshot_id = _validate_expected_active_id(expected_active_snapshot_id)
        with self._lock:
            self._check_cas(expected_generation, expected_active_snapshot_id)
            entry = self._entries.get(key)
            if entry is None:
                raise SnapshotNotFoundError(
                    "no catalogue entry exists for the requested exact snapshot_id"
                )
            if entry.state is SnapshotLifecycleState.RETIRED:
                raise SnapshotRetiredError(
                    "a retired snapshot cannot be activated"
                )
            if entry.state is SnapshotLifecycleState.ACTIVE:
                if self._active_snapshot_id == key:
                    return entry
                raise SnapshotCatalogueInvariantError(
                    "an ACTIVE entry does not match the active catalogue pointer"
                )
            if entry.state is not SnapshotLifecycleState.VERIFIED:
                raise SnapshotTransitionError(
                    "only VERIFIED snapshots may be activated"
                )

            next_generation = self._generation + 1
            previous_id = self._active_snapshot_id
            if previous_id is not None:
                previous = self._entries.get(previous_id)
                if previous is None or previous.state is not SnapshotLifecycleState.ACTIVE:
                    raise SnapshotCatalogueInvariantError(
                        "active pointer does not reference one ACTIVE catalogue entry"
                    )
                self._entries[previous_id] = replace(
                    previous,
                    state=SnapshotLifecycleState.RETIRED,
                    updated_generation=next_generation,
                )

            activated = replace(
                entry,
                state=SnapshotLifecycleState.ACTIVE,
                updated_generation=next_generation,
            )
            self._entries[key] = activated
            self._active_snapshot_id = key
            self._generation = next_generation
            return activated

    def retire(
        self,
        snapshot_id: str,
        *,
        expected_generation: int,
        expected_active_snapshot_id: str | None,
    ) -> SnapshotCatalogueEntry:
        key = _validate_snapshot_id(snapshot_id)
        expected_generation = _validate_expected_generation(expected_generation)
        expected_active_snapshot_id = _validate_expected_active_id(expected_active_snapshot_id)
        with self._lock:
            self._check_cas(expected_generation, expected_active_snapshot_id)
            entry = self._entries.get(key)
            if entry is None:
                raise SnapshotNotFoundError(
                    "no catalogue entry exists for the requested exact snapshot_id"
                )
            if entry.state is SnapshotLifecycleState.RETIRED:
                return entry
            next_generation = self._generation + 1
            if entry.state is SnapshotLifecycleState.ACTIVE:
                if self._active_snapshot_id != key:
                    raise SnapshotCatalogueInvariantError(
                        "ACTIVE entry does not match the active catalogue pointer"
                    )
                self._active_snapshot_id = None
            retired = replace(
                entry,
                state=SnapshotLifecycleState.RETIRED,
                updated_generation=next_generation,
            )
            self._entries[key] = retired
            self._generation = next_generation
            return retired

    def _check_cas(
        self,
        expected_generation: int,
        expected_active_snapshot_id: str | None,
    ) -> None:
        if expected_generation != self._generation:
            raise SnapshotCatalogueCASConflictError(
                "catalogue generation changed before the requested mutation"
            )
        if expected_active_snapshot_id != self._active_snapshot_id:
            raise SnapshotCatalogueCASConflictError(
                "active snapshot identity changed before the requested mutation"
            )
