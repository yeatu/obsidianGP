# Cloud snapshot bundle and canonical Markdown inventory

## Scope

This module creates a prepared, provider-neutral immutable source/index bundle candidate from a synthetic source tree and a disposable E1 SQLite index. It does not upload objects, assign object-store version IDs, stage catalogue entries, or activate a snapshot. The prepared descriptor is the input boundary for the later write port.

## Bundle layout

`sfra.cloud-snapshot-bundle.v1` is represented by two deterministic ZIP payloads:

- Source object: every regular file beneath the supplied source root, stored under `source/` with its exact original bytes. This preserves non-Markdown assets and does not normalize CRLF, Unicode, whitespace or file contents.
- Index object: `state/structure.sqlite3`, `markdown-inventory.json`, and `attestation.json`. The SQLite database is captured as the exact full byte payload. The inventory and attestation are canonical UTF-8 JSON.

Both objects carry a complete-payload lowercase SHA-256 (`sha256:<64 hex>`) and exact byte size in `PreparedBundleObject`. ZIP entries are byte-sorted, stored without compression, have fixed timestamps/permissions and no extra/comment fields. Verification reopens the archives and regenerates their canonical ZIP byte representation.

## Canonical Markdown inventory

The inventory format is `sfra.e1.markdown-inventory.v1`. It includes exactly regular `.md` files selected with the existing E1 `index_vault()` extension rule (case-insensitive `.md` suffix). Other regular source files remain in the source archive but are not listed in the Markdown inventory.

Each inventory row contains only:

- `path`: relative POSIX path from the source root.
- `byte_size`: length of exact raw UTF-8 file bytes.
- `sha256`: lowercase full-file SHA-256 over those exact bytes.

Empty Markdown files remain rows. Paths are sorted by their UTF-8 byte sequence. The canonical payload is JSON with `ensure_ascii=False`, sorted keys, compact separators `(',', ':')`, no trailing newline and no duplicate keys. The inventory digest is separate from the full source archive digest.

The source walk never follows symlinks. It rejects symlinks, special files, absolute paths, backslashes, empty/dot/dot-dot path components, duplicate canonical paths and invalid UTF-8 paths/Markdown. Source bytes are held once and used for both the source archive and inventory, preventing a second read from silently producing a different inventory.

## E1 cloud-index attestation

The index bundle binds the source revision as a tagged `git_commit` or `immutable_import` value, canonical inventory digest/count, installed E1 indexer identity, SQLite schema identity, parser identities, exact database digest/size and document/node/passage counts.

The verifier checks SQLite `integrity_check`, foreign keys, schema version, exact active document path set, each active document size/hash against the Markdown inventory, unique active Node IDs, and each active/ambiguous raw-text Content Hash. It verifies that the embedded inventory and attestation are exact canonical bytes and match the descriptor.

For a Git-tagged synthetic fixture, the public E1 v1 `verify_state_directory()` API is additionally run on a disposable copy of the SQLite database and a synthetic v1 state manifest. For an immutable-import revision, the builder deliberately does not coerce `import_id` into a Git SHA field; the legacy verifier is recorded as skipped until the separate additive E1 verifier analysis/implementation is accepted.

## Public API

`build_markdown_inventory(source_root)` returns the canonical Markdown inventory.

`build_prepared_cloud_snapshot_bundle(source_root, index_database_path, *, source_revision, source_object_key, index_object_key, indexer_identity, sqlite_schema_identity)` prepares and verifies the two payloads. It requires the installed `sfra-structural-indexer` distribution and its exact version identity.

`verify_prepared_cloud_snapshot_bundle(bundle)` revalidates ZIP bytes, inventory, attestation, hashes/sizes and SQLite before the descriptor is handed to a separate writer.

`PreparedCloudSnapshotBundle.build_cloud_snapshot_v2(source_version_id=..., index_version_id=...)` attaches the opaque immutable versions returned by a later writer and produces the shared CloudSnapshotRef v2 result. This method performs no upload itself.

## Safety boundary

All fixture tests use temporary source directories and disposable SQLite files created by the E1 public `index_vault()` API. No real Vault, production SQLite, sidecar, manifest, `sfra-state`, provider, credentials, upload, workflow dispatch, catalogue activation or production path is used.

