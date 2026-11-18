# Read-only exact-version snapshot materializer

## Responsibility boundary

`CloudSnapshotMaterializer` resolves one caller-supplied `snapshot_id` through the accepted `SnapshotCataloguePort.get_exact()` API. It does not consult a mutable `latest` alias, read or write the ACTIVE pointer, upload objects, mutate catalogue state, or create provider-specific clients.

The read port is intentionally small:

- `ObjectStoreReadPort.read_exact(key, version_id)` returns the exact key/version pair and its payload bytes.
- The interface contains no list, write, overwrite, delete, or upload operation.
- Both source and index payloads are checked against the complete SHA-256 and byte size in the immutable `CloudSnapshotRefV2` before archive processing.

## Verification sequence

1. Resolve the exact snapshot ID once and retain the immutable v2 identity.
2. Read the source object by its exact key and opaque version ID. Re-read the same catalogue ID and compare the complete identity before continuing.
3. Read the index object by its exact key and opaque version ID. Recheck the same catalogue identity again.
4. Reconstruct the canonical outer manifest from the ref, verify its detached manifest digest and all identity fields.
5. Admit both archives only through the accepted #119 deterministic ZIP reader. It rejects compressed members before their payloads are read, as well as unsafe paths, duplicates, special files, and non-canonical ZIP bytes.
6. Reconstruct the prepared #119 descriptor from the two exact payloads and the embedded E1 attestation metadata. Run the public `verify_prepared_cloud_snapshot_bundle()` API and compare its report against the outer v2 ref.
7. Recheck the catalogue binding, then materialize the verified source files, SQLite database, and exact raw `attestation.json` / `markdown-inventory.json` bytes into a newly created child directory under a caller-supplied disposable workspace.
8. Recheck the exact catalogue identity after materialization. If it changed, became retired, or disappeared, delete the newly created child workspace and fail closed.

The returned frozen `MaterializedCloudSnapshot` is request-scoped. It retains the full `CloudSnapshotRefV2`, tagged source revision, exact paths, the exact raw E1 attestation and inventory bytes, the canonical manifest bytes, and the public #119 verification report. The raw E1 JSON is not reserialized. The additive E1 cloud-index verifier #240 consumes these files/bytes separately; #120 does not perform the deep E1 verification.

## Failure behavior

Typed failures distinguish an unavailable exact object version, a returned key/version mismatch, payload hash/size mismatch, malformed outer manifest or archive, changed/retired catalogue binding, and an invalid workspace. A latest-only response is a version mismatch, never a reason to retry against latest. No partial fragments or materialized directory are returned after a failed check; a newly allocated directory is removed if the final catalogue check fails.

## Synthetic fixtures and safety

The in-memory versioned object-store adapter is initialized with immutable `(key, version_id) -> bytes` entries and exposes only `read_exact`. Tests use the accepted E1 public indexer to create disposable SQLite fixtures, the #119 bundle builder to produce deterministic ZIP bytes, the accepted in-memory catalogue, and temporary directories.

No provider SDK, network, credentials, OIDC/KMS, persistent storage, production Vault/SQLite/sidecar/`sfra-state`, real reads/writes, workflow dispatch, worker integration, catalogue activation, or provider operation is included.
