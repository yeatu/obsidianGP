# PinnedSnapshot operation-boundary verification

`bind_pinned_snapshot()` constructs the SnapshotRef from the actual clean Git checkouts, exact manifest bytes and E1-verified SQLite state. It is the only production factory for `PinnedSnapshot`.

`PinnedSnapshot` is a frozen, slots-based value object with direct public construction disabled. The public snapshot type and `bind_pinned_snapshot()` binder are created by a module-initialization factory that keeps the weak verifier registry and its registration function in local closure state; no module-level registrar, verifier class or seal is exported. The active callback is not stored in an instance attribute and cannot be obtained through ordinary attribute access. Each live snapshot is registered once; an unregistered or forged instance fails closed. Test-only synthetic snapshots use a separate subclass in `tests/fixtures/pinned_snapshot.py`, outside the production package, with its own fixture-controlled verifier.

`E1SourceReader` executes the verifier during construction and fails before accepting the reader if the pinned state is no longer valid. It also repeats verification at every operation boundary.

Before and after E2 search and before/after each E1 address/source read, the verifier checks:
- resolved sidecar, database, manifest, Vault checkout and Vault-root paths have not been redirected;
- sidecar and Vault Git HEADs still equal the pinned SnapshotRef;
- sidecar remains on the expected `sfra-state` branch;
- both checkouts remain clean;
- manifest bytes still hash to the pinned manifest digest and its parsed object is unchanged;
- the manifest remains byte-identical to the manifest accepted by E1 during initial binding;
- the SQLite bytes still match the manifest database SHA-256.

If any check fails, E3 returns a typed `snapshot_changed` contract error and does not return fragments from that operation. The checks are repeated after the E1/E2 call so a sidecar replacement during the call also discards its result. Unit tests use temporary sidecar/Vault fixtures; no production state is written.
