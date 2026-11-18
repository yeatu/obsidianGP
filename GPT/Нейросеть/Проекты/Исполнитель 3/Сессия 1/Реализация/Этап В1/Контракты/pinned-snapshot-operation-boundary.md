# PinnedSnapshot operation-boundary verification

bind_pinned_snapshot() is the only production factory. It binds a SnapshotRef to the actual clean Git checkouts, exact manifest bytes and E1-verified SQLite state. Direct construction and manually allocated/unregistered instances fail closed.

The public PinnedSnapshot class is a frozen, slots-based dataclass. Its verifier registry is held in module-initialization closure state, not in an instance attribute. Python closures and module objects remain introspectable by code already executing in the same interpreter. Per coordinator threat-model decision #81, this package is not a sandbox against hostile same-process Python code and makes no tamper-proof or closure-inaccessibility claim. The trusted-process assumption is explicit.

Production E1/E2/E3 consumer boundaries require the exact concrete factory-created PinnedSnapshot type, not isinstance compatibility. E1SourceReader, E2SearchAdapter and ContextIntegrationPipeline reject user-defined subclasses before using the snapshot. Each consumer also verifies the active factory binding; an exact but manually allocated/unregistered object fails closed. Exact type checks prevent a subclass override of verify_current() from replacing the production check at these boundaries.

Synthetic test snapshots remain a subclass under tests/fixtures. They are intentionally rejected by all production constructors. Tests that need a synthetic verifier use the separate tests/fixtures/consumer_seams.py helpers, which instantiate test subjects inside the test tree and bypass only the production constructor gate. These helpers are never imported by the production package or composition path.

E1SourceReader executes the verifier during construction and fails before accepting the reader if the pinned state is no longer valid. It repeats verification at every operation boundary.

Before and after E2 search and before/after each E1 address/source read, the verifier checks:
- resolved sidecar, database, manifest, Vault checkout and Vault-root paths have not been redirected;
- sidecar and Vault Git HEADs still equal the pinned SnapshotRef;
- sidecar remains on the expected sfra-state branch;
- both checkouts remain clean;
- manifest bytes still hash to the pinned manifest digest and its parsed object is unchanged;
- the manifest remains byte-identical to the manifest accepted by E1 during initial binding;
- the SQLite bytes still match the manifest database SHA-256.

If any check fails, E3 returns a typed snapshot_changed contract error and does not return fragments from that operation. The checks are repeated after the E1/E2 call so a sidecar replacement during the call also discards its result. Unit tests use temporary sidecar/Vault fixtures; no production state is written.
