# Read-only exact-version snapshot materializer

## Responsibility boundary

`CloudSnapshotMaterializer` resolves one caller-supplied `snapshot_id` through the accepted `SnapshotCataloguePort.get_exact()` API. It does not consult a mutable `latest` alias, read or write the ACTIVE pointer, upload objects, mutate catalogue state, or create provider-specific clients.

The read port is intentionally small:

- `ObjectStoreReadPort.read_exact(key, version_id)` returns the exact key/version pair and its payload bytes.
- The interface contains no list, write, overwrite, delete, or upload operation.
- Both source and index payloads are checked against the complete SHA-256 and byte size in the immutable `CloudSnapshotRefV2` before archive processing.

## Two purpose-specific materialization paths

### STAGED verification input for E1 #240

`materialize_for_verification(snapshot_id, workspace)` accepts only an exact `STAGED` catalogue entry and returns the distinct frozen `VerificationMaterialization` type. The output records `catalogue_state=STAGED` and carries:

- exact snapshot ID and full immutable `CloudSnapshotRefV2`;
- tagged source revision and exact source/index object key/version/hash/size identities;
- verified outer manifest and #119 bundle report;
- disposable source-root and SQLite paths;
- exact raw #119 `attestation.json` and `markdown-inventory.json` bytes.

This is a non-query-capable input to E1 verifier #240 only. It is not a `MaterializedCloudSnapshot`, cannot be passed as that exact runtime type, and exposes no source-read, search, dependency, Context Pack or V2.2 query methods. It does not call `mark_verified()` or `activate()`. No promotion occurs in #120.

### ACTIVE input for the later #136 factory

`materialize(snapshot_id, workspace)` accepts only an exact `ACTIVE` catalogue entry and returns the separate `MaterializedCloudSnapshot` type. This is still not a query capability. Only #136 may mint the factory-only request query handle after it validates the accepted E1 report, exact full snapshot identity, workspace and current ACTIVE catalogue state. `STAGED` and `VERIFIED` entries are rejected before any object read on this path.

The two operations share the same internal exact-version read, outer manifest, deterministic ZIP and public #119 bundle-verification implementation, but their public result types and lifecycle gates are distinct. Each request performs one exact catalogue lookup and remains pinned to that returned immutable identity; the resolver never silently rebinds to a new ACTIVE snapshot during object reads.

## Verification sequence

1. Resolve the exact snapshot ID once and retain the immutable v2 identity for the whole operation.
2. Read source and index by exact key and opaque immutable version ID; verify each returned key/version, full payload SHA-256 and byte size.
3. Reconstruct the canonical outer manifest and verify its detached digest and all identity fields.
4. Admit both archives only through the accepted #119 deterministic ZIP reader, which rejects compressed members before payload read/decompression, unsafe paths, duplicates, special files and non-canonical ZIP bytes.
5. Reconstruct the prepared #119 descriptor from the exact payloads and embedded E1 attestation metadata. Run public `verify_prepared_cloud_snapshot_bundle()` and compare the report against the outer v2 identity.
6. Materialize the verified source files, SQLite database and exact raw attestation/inventory bytes into a newly created child directory under a caller-supplied disposable workspace.

For a STAGED entry, the result is only the E1 #240 verification input. The caller/orchestrator must independently run #240, bind its successful report to the same snapshot ID/full v2 reference and outer digest, and only then call #118 `mark_verified(snapshot_id)` under the accepted CAS contract. Activation is a separate explicit #118 transition. Any failed or mismatched verification leaves the entry STAGED.

For an ACTIVE entry, the result is input to #136's later factory; #120 does not itself bind query adapters or expose request-level source/search APIs.

## Failure behavior

Typed failures distinguish an unavailable exact object version, returned key/version mismatch, payload hash/size mismatch, malformed outer manifest or archive, changed/retired catalogue binding, invalid lifecycle state and invalid workspace. A latest-only response is a version mismatch, never a reason to retry against latest. No partial result is returned after failed verification; a newly allocated directory is removed if materialization fails.

## Synthetic fixtures and safety

The in-memory object-store adapter is initialized with immutable `(key, version_id) -> bytes` entries and exposes only `read_exact`. Tests use the accepted E1 public indexer to create disposable SQLite fixtures, the #119 bundle builder, the accepted in-memory catalogue and temporary directories.

No provider SDK, network, credentials, OIDC/KMS, persistent storage, production Vault/SQLite/sidecar/`sfra-state`, real reads/writes, workflow dispatch, worker integration, catalogue mutation/activation or provider operation is included.
