from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from sfra_context_integrations.cloud_snapshot_v2 import (
    CloudSnapshotManifestV1,
    GitCommitSourceRevision,
    ImmutableImportSourceRevision,
    ImmutableObjectVersion,
    IndexerIdentity,
    SqliteSchemaIdentity,
    build_cloud_snapshot_v2,
)
from sfra_context_integrations.snapshot_catalogue import (
    InMemorySnapshotCatalogue,
    InvalidSnapshotIdError,
    InvalidSnapshotIdentityError,
    SnapshotCatalogueCASConflictError,
    SnapshotCatalogueConflictError,
    SnapshotCatalogueEntry,
    SnapshotLifecycleState,
    SnapshotNotFoundError,
    SnapshotRetiredError,
    SnapshotTransitionError,
)


def _snapshot(label: str = "a", *, import_revision: bool = False):
    source_bytes = ("synthetic source " + label).encode("utf-8")
    index_bytes = ("synthetic index " + label).encode("utf-8")
    source_revision = (
        ImmutableImportSourceRevision("synthetic-import-" + label)
        if import_revision
        else GitCommitSourceRevision((label[0] * 40))
    )
    manifest = CloudSnapshotManifestV1(
        source_revision=source_revision,
        source_bundle=ImmutableObjectVersion(
            key="snapshots/source.tar",
            version_id="source-version-" + label,
            sha256="sha256:" + __import__("hashlib").sha256(source_bytes).hexdigest(),
            byte_size=len(source_bytes),
        ),
        index_bundle=ImmutableObjectVersion(
            key="snapshots/index.tar",
            version_id="index-version-" + label,
            sha256="sha256:" + __import__("hashlib").sha256(index_bytes).hexdigest(),
            byte_size=len(index_bytes),
        ),
        indexer_identity=IndexerIdentity("sfra-indexer", "v1"),
        sqlite_schema_identity=SqliteSchemaIdentity("sqlite", 2),
    )
    return build_cloud_snapshot_v2(manifest).ref


def _stage_verified(catalogue: InMemorySnapshotCatalogue, snapshot):
    staged = catalogue.stage(snapshot)
    assert staged.state is SnapshotLifecycleState.STAGED
    return catalogue.mark_verified(snapshot.snapshot_id)


def test_stage_is_idempotent_and_exact_lookup_preserves_full_v2_identity():
    catalogue = InMemorySnapshotCatalogue()
    snapshot = _snapshot()

    first = catalogue.stage(snapshot)
    state_after_first = catalogue.read_state()
    second = catalogue.stage(snapshot)
    fetched = catalogue.get_exact(snapshot.snapshot_id)

    assert first.state is SnapshotLifecycleState.STAGED
    assert second == first
    assert fetched.snapshot == snapshot
    assert fetched.snapshot.to_dict() == snapshot.to_dict()
    assert catalogue.read_state() == state_after_first


def test_git_and_immutable_import_revisions_are_stored_as_exact_distinct_variants():
    catalogue = InMemorySnapshotCatalogue()
    git_snapshot = _snapshot("a")
    import_snapshot = _snapshot("b", import_revision=True)

    git_entry = catalogue.stage(git_snapshot)
    import_entry = catalogue.stage(import_snapshot)

    assert git_entry.snapshot.source_revision == git_snapshot.source_revision
    assert import_entry.snapshot.source_revision == import_snapshot.source_revision
    assert import_entry.snapshot.source_revision.to_dict() == {
        "kind": "immutable_import", "import_id": "synthetic-import-b"
    }


def test_catalogue_rejects_noncanonical_identity_and_mutable_lookup_aliases():
    catalogue = InMemorySnapshotCatalogue()
    with pytest.raises(InvalidSnapshotIdentityError):
        catalogue.stage(object())
    with pytest.raises(InvalidSnapshotIdError):
        catalogue.get_exact("latest")
    with pytest.raises(InvalidSnapshotIdError):
        catalogue.get_exact("sha256:" + "A" * 64)


def test_missing_entry_returns_typed_not_found_outcome():
    catalogue = InMemorySnapshotCatalogue()
    with pytest.raises(SnapshotNotFoundError):
        catalogue.get_exact("sha256:" + "0" * 64)
    with pytest.raises(SnapshotNotFoundError):
        catalogue.mark_verified("sha256:" + "0" * 64)


def test_unverified_entry_cannot_be_activated_and_previous_active_is_preserved():
    catalogue = InMemorySnapshotCatalogue()
    active_snapshot = _snapshot("a")
    pending_snapshot = _snapshot("b")
    _stage_verified(catalogue, active_snapshot)
    state = catalogue.read_state()
    catalogue.activate(
        active_snapshot.snapshot_id,
        expected_generation=state.generation,
        expected_active_snapshot_id=None,
    )

    catalogue.stage(pending_snapshot)
    state_before = catalogue.read_state()
    with pytest.raises(SnapshotTransitionError):
        catalogue.activate(
            pending_snapshot.snapshot_id,
            expected_generation=state_before.generation,
            expected_active_snapshot_id=active_snapshot.snapshot_id,
        )

    assert catalogue.read_state().active_snapshot_id == active_snapshot.snapshot_id
    assert catalogue.read_state().generation == state_before.generation
    assert catalogue.get_exact(active_snapshot.snapshot_id).state is SnapshotLifecycleState.ACTIVE


def test_activation_replaces_previous_active_atomically_and_retires_old_identity():
    catalogue = InMemorySnapshotCatalogue()
    first = _snapshot("a")
    second = _snapshot("b")
    _stage_verified(catalogue, first)
    state = catalogue.read_state()
    catalogue.activate(
        first.snapshot_id,
        expected_generation=state.generation,
        expected_active_snapshot_id=None,
    )
    _stage_verified(catalogue, second)
    state = catalogue.read_state()

    activated = catalogue.activate(
        second.snapshot_id,
        expected_generation=state.generation,
        expected_active_snapshot_id=first.snapshot_id,
    )

    assert activated.state is SnapshotLifecycleState.ACTIVE
    assert activated.snapshot == second
    assert catalogue.read_state().active_snapshot_id == second.snapshot_id
    with pytest.raises(SnapshotRetiredError):
        catalogue.get_exact(first.snapshot_id)


def test_stale_generation_or_wrong_expected_active_id_fails_without_mutation():
    catalogue = InMemorySnapshotCatalogue()
    snapshot = _snapshot()
    _stage_verified(catalogue, snapshot)
    state = catalogue.read_state()

    with pytest.raises(SnapshotCatalogueCASConflictError):
        catalogue.activate(
            snapshot.snapshot_id,
            expected_generation=state.generation - 1,
            expected_active_snapshot_id=None,
        )
    with pytest.raises(SnapshotCatalogueCASConflictError):
        catalogue.activate(
            snapshot.snapshot_id,
            expected_generation=state.generation,
            expected_active_snapshot_id="sha256:" + "0" * 64,
        )

    assert catalogue.read_state() == state
    assert catalogue.get_exact(snapshot.snapshot_id).state is SnapshotLifecycleState.VERIFIED


def test_two_competing_cas_activations_allow_exactly_one_winner():
    catalogue = InMemorySnapshotCatalogue()
    first = _snapshot("a")
    second = _snapshot("b")
    _stage_verified(catalogue, first)
    _stage_verified(catalogue, second)
    observed = catalogue.read_state()
    barrier = Barrier(3)

    def attempt(snapshot_id: str) -> str:
        barrier.wait()
        try:
            catalogue.activate(
                snapshot_id,
                expected_generation=observed.generation,
                expected_active_snapshot_id=observed.active_snapshot_id,
            )
            return "activated"
        except SnapshotCatalogueCASConflictError:
            return "cas_conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(attempt, first.snapshot_id),
            pool.submit(attempt, second.snapshot_id),
        ]
        barrier.wait()
        outcomes = [future.result() for future in futures]

    assert outcomes.count("activated") == 1
    assert outcomes.count("cas_conflict") == 1
    state = catalogue.read_state()
    assert state.active_snapshot_id in {first.snapshot_id, second.snapshot_id}
    assert state.generation == observed.generation + 1
    active_entries = [
        catalogue._entries[snapshot_id]
        for snapshot_id in (first.snapshot_id, second.snapshot_id)
        if catalogue._entries[snapshot_id].state is SnapshotLifecycleState.ACTIVE
    ]
    assert len(active_entries) == 1


def test_explicit_retirement_clears_active_pointer_and_makes_exact_lookup_unavailable():
    catalogue = InMemorySnapshotCatalogue()
    snapshot = _snapshot()
    _stage_verified(catalogue, snapshot)
    state = catalogue.read_state()
    catalogue.activate(
        snapshot.snapshot_id,
        expected_generation=state.generation,
        expected_active_snapshot_id=None,
    )
    state = catalogue.read_state()

    retired = catalogue.retire(
        snapshot.snapshot_id,
        expected_generation=state.generation,
        expected_active_snapshot_id=snapshot.snapshot_id,
    )

    assert retired.state is SnapshotLifecycleState.RETIRED
    assert catalogue.read_state().active_snapshot_id is None
    with pytest.raises(SnapshotRetiredError):
        catalogue.get_exact(snapshot.snapshot_id)
    with pytest.raises(SnapshotRetiredError):
        catalogue.mark_verified(snapshot.snapshot_id)


def test_retiring_non_active_entry_does_not_change_active_pointer():
    catalogue = InMemorySnapshotCatalogue()
    active = _snapshot("a")
    staged = _snapshot("b")
    _stage_verified(catalogue, active)
    state = catalogue.read_state()
    catalogue.activate(
        active.snapshot_id,
        expected_generation=state.generation,
        expected_active_snapshot_id=None,
    )
    staged_entry = catalogue.stage(staged)
    state = catalogue.read_state()

    retired = catalogue.retire(
        staged.snapshot_id,
        expected_generation=state.generation,
        expected_active_snapshot_id=active.snapshot_id,
    )

    assert staged_entry.state is SnapshotLifecycleState.STAGED
    assert retired.state is SnapshotLifecycleState.RETIRED
    assert catalogue.read_state().active_snapshot_id == active.snapshot_id


def test_conflicting_identity_under_existing_snapshot_id_fails_closed():
    catalogue = InMemorySnapshotCatalogue()
    original = _snapshot("a")
    conflicting = _snapshot("b")
    entry = catalogue.stage(original)
    # Simulate a corrupted backing record, a condition a persistent adapter must also reject.
    catalogue._entries[original.snapshot_id] = SnapshotCatalogueEntry(
        snapshot=conflicting,
        state=entry.state,
        created_generation=entry.created_generation,
        updated_generation=entry.updated_generation,
    )

    with pytest.raises(SnapshotCatalogueConflictError):
        catalogue.stage(original)


def test_retired_snapshot_cannot_be_re_staged():
    catalogue = InMemorySnapshotCatalogue()
    snapshot = _snapshot()
    entry = catalogue.stage(snapshot)
    state = catalogue.read_state()
    catalogue.retire(
        snapshot.snapshot_id,
        expected_generation=state.generation,
        expected_active_snapshot_id=None,
    )
    assert entry.state is SnapshotLifecycleState.STAGED
    with pytest.raises(SnapshotRetiredError):
        catalogue.stage(snapshot)
