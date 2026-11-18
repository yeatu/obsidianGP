# Snapshot catalogue v1 (provider-neutral)

## Responsibility and public boundary

The catalogue stores the complete accepted CloudSnapshotRef v2 identity and its lifecycle state. The public `SnapshotCataloguePort` exposes only staging, exact-ID lookup, verification marking, state reads, compare-and-swap activation and retirement. The included `InMemorySnapshotCatalogue` is a thread-safe disposable reference adapter for tests.

The catalogue does not build or verify source/index bundles, upload or download objects, select providers, persist data, manage credentials, or read production source state. Bundle preparation/verification is owned by Issue #119; the materializer is a later boundary.

## Lifecycle

| Current state | Operation | Next state | Notes |
|---|---|---|---|
| absent | `stage(snapshot)` | `STAGED` | Stores the exact CloudSnapshotRef v2 identity; exact duplicate staging is idempotent. |
| `STAGED` | `mark_verified(snapshot_id)` | `VERIFIED` | Caller may mark verified only after the separate bundle verifier succeeds. |
| `VERIFIED` | `activate(snapshot_id, expected_generation, expected_active_snapshot_id)` | `ACTIVE` | Requires exact CAS match and successful verification. |
| `ACTIVE` | activate a different `VERIFIED` identity | `RETIRED` + new `ACTIVE` | The old active entry is retired in the same atomic catalogue mutation. |
| `STAGED`, `VERIFIED`, or `ACTIVE` | `retire(snapshot_id, expected_generation, expected_active_snapshot_id)` | `RETIRED` | Explicit retirement retains metadata; active retirement clears the active pointer. |

`RETIRED` is terminal. A retired identity cannot be restaged, verified or activated. No content or object is deleted by this adapter.

## Generation and compare-and-swap

`read_state()` returns the current `generation` and `active_snapshot_id`. Mutating callers pass both observed values to `activate()` or `retire()`. The operation succeeds only if both still match while holding the catalogue lock. A stale generation or changed active identity raises `SnapshotCatalogueCASConflictError` and leaves state unchanged.

The generation increases once for each committed state mutation: a new stage, STAGED→VERIFIED, activation, or retirement. Exact duplicate staging and idempotent verification do not increment it. Replacing an active snapshot retires the previous ACTIVE record and activates the new VERIFIED record in one generation change, so no intermediate state exposes two active entries.

## Exact identity and unavailable outcomes

Every staged input must be the exact `CloudSnapshotRefV2` type and must round-trip through the canonical public parser. The complete immutable identity is stored and returned unchanged. Lookup accepts only `sha256:` plus 64 lowercase hexadecimal characters; aliases such as `latest` are not valid identifiers.

`get_exact()` raises `SnapshotNotFoundError` for an absent ID and `SnapshotRetiredError` for a retired ID. `SnapshotTransitionError` represents an invalid lifecycle transition; `SnapshotCatalogueConflictError` rejects a key whose stored identity differs; `SnapshotCatalogueCASConflictError` reports a stale activation/retirement precondition.

## Synthetic-only validation

The catalogue tests use only in-memory records and synthetic CloudSnapshotRef v2 values. They cover idempotent staging, Git/import identity preservation, invalid IDs, missing/retired outcomes, unverified activation rejection, atomic replacement, stale CAS, two competing activation attempts, explicit retirement and conflicting stored identity. They do not create a persistent catalogue or activate a production pointer.