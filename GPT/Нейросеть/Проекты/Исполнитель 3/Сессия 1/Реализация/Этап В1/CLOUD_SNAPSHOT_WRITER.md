# Immutable cloud snapshot writer v1

## Responsibility

The writer consumes an already prepared and publicly verified `PreparedCloudSnapshotBundle` from #119. It exposes a narrow provider-neutral `ObjectStoreWritePort`, plus an in-memory immutable reference adapter used only by synthetic tests.

The writer does not build bundles, change the catalogue, select a provider, persist state, create credentials, or activate a snapshot. It has no list, overwrite, delete or catalogue mutation operation.

## Port contract

`ObjectStoreWritePort` exposes only:

- `put_if_absent(key, payload, expected_sha256, expected_byte_size)`: conditionally creates an immutable object and returns an `ObjectWriteReceipt` or no acknowledgement;
- `read_exact(key, version_id)`: reads back precisely the acknowledged immutable version.

Before the port is called, the writer revalidates the prepared bundle with #119's public `verify_prepared_cloud_snapshot_bundle()`. Each payload's complete SHA-256 and byte size are checked again before conditional creation. A receipt must echo the exact key/hash/size and carry an opaque immutable version ID. The writer then reads that exact version back and compares exact bytes, size and SHA-256.

Only after both source and index objects have acknowledged writes and passed exact-version read-back does the writer call `PreparedCloudSnapshotBundle.build_cloud_snapshot_v2()` with the two returned opaque version IDs. It returns an `UploadedCloudSnapshotBundle` containing the verified receipts and complete v2 identity. Object version IDs are never interpreted as Git commit SHAs.

## Retry, conflict and failure semantics

- Identical key + identical payload is idempotent and returns the same immutable receipt/version.
- Existing key + different payload is a conditional conflict; earlier bytes are never overwritten.
- Wrong expected hash or byte size is rejected before storage mutation.
- Partial write, missing acknowledgement, missing exact-version read-back, or read-back byte/hash/size mismatch raises a typed error. No v2 reference or uploaded-bundle result is returned.
- The source and index objects are written sequentially. If the second write fails, the first successful immutable object may remain as an orphan. The protocol intentionally has no delete/rollback capability. The caller must not mark the catalogue entry verified or active; a retry is safe only with the exact same key and bytes, and conflicting data remains rejected.
- A successful `UploadedCloudSnapshotBundle` proves both immutable payloads were acknowledged and read back exactly. It does not verify or change catalogue state.

## In-memory adapter

`InMemoryImmutableObjectStore` uses an in-memory dictionary and deterministic opaque `memory-v1:` version IDs. Optional one-shot synthetic faults exercise partial write, missing acknowledgement and corrupt read-back paths. It is a disposable test adapter, not a cloud or persistence implementation.

## Validation

The dedicated fixture workflow installs E1, B1, E3 and E2 packages, creates temporary source/SQLite fixtures through E1's public `index_vault()` API, and tests the writer only. No real source or durable state is used.

## Safety boundary

No provider SDK, remote storage, network, credentials, OIDC/KMS, real Vault/SQLite/sidecar/manifest/sfra-state, workflow dispatch, production upload, catalogue activation, retention or delete operation is used. The read-only resolver/query port remains separate from this write-only seam.


## Current stack integration baseline (2026-11-18)

This writer branch consumes the refreshed bundle-builder dependency:
- Bundle PR #162 exact HEAD: `c5f84cd64877167b9feef3140fe20adf39c616cd`.
- Current main/base incorporated by that bundle HEAD: `553392dbbe9d3782683593bb92b88ac3ad6d9721`.
- Writer branch sync commit: `c9b21be108ae7943b475838559b6bd2c163ba1bf`, with the refreshed bundle HEAD as first parent and the former writer HEAD `8c957c9e2554ebef8458978a4245b7a27bbe866e` as second parent.

This records branch ancestry for the stacked implementation only. It does not change the writer contract or enable a provider, upload, catalogue activation or production operation.


## Corrected bundle baseline after current-main refresh (2026-11-19)

This writer parent now consumes the independently accepted and merged bundle/verifier stack:
- Current main and accepted #162 merge: 8d1d3c937abf1e6f651d077c409d1b3dfad1a9cb (tree 7b516530ad2f10fd10967fb84087fdf6a3946042).
- Writer refresh merge: 123de3771cc2aab1664bbecdfc5533df90696c6a, with current main as first parent and former writer HEAD b0bcf7ae587c3613b80ef811264bdd4437eedc93 as second.
- This note records ancestry only; writer runtime behavior and test semantics are unchanged by the baseline refresh.


## Current-main refresh after exact-version resolver acceptance (2026-11-19)

The accepted E2 resolver/materializer PR #250 was merged into main at 372c1b854a39c436969d3835d0656c46a4758677 (tree b1612bd11d71f2a4a6563b39a4d119c2371e1f40). This parent writer branch now includes that accepted resolver history as part of its main-first refresh merge 08c2720f67bfcfb1a84ae0b0d98bf910dfa1af5f, whose second parent is the former writer HEAD 5612a70520c91efcb9d4ccdd955f207c63bef641. The effective writer delta remains restricted to the four writer-owned files. This note records ancestry only; no writer runtime/test semantics change.
