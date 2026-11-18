# E3 exact-version cloud snapshot resolver

The resolver implements the read-only E3 materialization boundary in Issue #120.
It resolves one exact snapshot ID from the catalogue port, then retains that
returned immutable reference for the entire operation.

## Trust and data flow

1. CloudSnapshotResolver.resolve(snapshot_id, workspace=...) performs one
   get_exact(snapshot_id) catalogue lookup. Only VERIFIED and ACTIVE entries
   are readable; STAGED and RETIRED entries fail closed.
2. The canonical manifest is reconstructed from the immutable v2 identity and
   checked against its detached manifest digest and derived snapshot ID.
3. The resolver calls only ObjectStoreReadPort.get_exact(key, version_id) for
   the two exact object versions. The returned key and version ID must echo the
   request, and full payload SHA-256 and byte size are recomputed before archive
   parsing.
4. The accepted #119 deterministic ZIP verifier rejects unsafe members,
   unsupported compression, non-canonical bytes and bundle/inventory/SQLite/
   attestation disagreement. No second archive or inventory dialect is added.
5. The verified source tree, SQLite database and exact raw attestation.json /
   markdown-inventory.json bytes are written to a private request directory
   under the caller's ephemeral workspace. File creation is exclusive and
   post-write bytes are checked for replacement or mutation.
6. The returned immutable MaterializedCloudSnapshotHandle retains the exact
   CloudSnapshotRefV2, object-version records, source revision, source root,
   database path and raw inner E1 bytes. The caller owns workspace cleanup.

The E1 deep verifier in Issue #240 is intentionally separate. This resolver
verifies the complete outer #119 bundle and prepares exact materialized inputs
for #240; it does not claim E1 whole-index attestation acceptance, source-origin
authenticity, provider immutability, or historical UUID assignment.

## Ports

ObjectStoreReadPort exposes one method only:

    def get_exact(*, key: str, version_id: str) -> ObjectVersionRead: ...

There is no upload, overwrite, delete, or list-all capability. A latest-only
response, absent immutable version, wrong key/version, or changed payload raises
a typed resolver failure. There is no retry against "latest" and no catalogue
re-resolution after the initial lookup.

## Fixture validation

The dedicated workflow installs disposable E1/B1/E2/E3 packages and exercises
Git and immutable-import revisions, byte-exact materialization, missing/latest/
corrupt object outcomes, unverified/retired catalogue states, an active-pointer
switch during an in-flight request, and workspace symlink rejection. It uses
synthetic Markdown files, temporary SQLite databases, and an in-memory object
store only.
