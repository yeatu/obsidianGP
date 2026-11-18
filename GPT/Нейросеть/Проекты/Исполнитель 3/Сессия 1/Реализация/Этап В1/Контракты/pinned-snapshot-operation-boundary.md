# PinnedSnapshot operation-boundary verification

`bind_pinned_snapshot()` constructs the SnapshotRef from the actual clean Git checkouts, exact manifest bytes and E1-verified SQLite state. It is the only production factory for `PinnedSnapshot`.

`PinnedSnapshot` is a frozen, slots-based value object. Direct public construction is disabled; `bind_pinned_snapshot()` validates the clean checkouts and E1 state, then stores its operation-boundary verifier closure in the instance. There is no module-level verifier class or seal that production consumers can import to mint a replacement capability, and ordinary attribute assignment cannot replace the callback. Test-only synthetic snapshots are created by the explicit helper in `tests/fixtures/pinned_snapshot.py`; it is not part of the production package.

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
