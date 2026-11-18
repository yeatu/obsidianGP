# Cloud SnapshotRef v2 contract

**Status:** synthetic-only additive contract for Issue #117, approved by C3 in Issue #112 comment #6970682005.

## Compatibility boundary

The existing \`sfra_context_builder.models.SnapshotRef\` v1 remains unchanged:

- \`vault_commit_sha\`
- \`sidecar_commit_sha\`
- \`manifest_sha256\`

The new \`sfra_context_integrations.cloud_snapshot_v2.CloudSnapshotRefV2\` is a separate type. Do not overload v1 fields or put object-store version IDs into Git SHA fields. No E1/E2/E3/B1/V2.1/V2.2 consumer migration is part of this contract task.

A v2 source revision is a tagged union:

- \`{"kind":"git_commit","commit_sha":"<lowercase 40-hex>" }\`
- \`{"kind":"immutable_import","import_id":"<immutable ID>" }\`

An object-store version ID is an opaque provider value. It is stored separately from the SHA-256 and byte size; it is never interpreted as a Git commit.

There is no automatic v2-to-v1 conversion in this contract. A Git-backed v2 source revision can provide the v1 \`vault_commit_sha\`, but v1 also requires an independently verified sidecar Git commit SHA. The v2 index object version is not that SHA. A future bridge may be defined only when both genuine Git commit identities are explicitly available and verified. An immutable import ID cannot satisfy v1's Git-commit field and cannot be converted.

## Canonical manifest v1

The canonical UTF-8 JSON manifest has exactly these fields:

\`\`\`json
{
  "manifest_schema_version": 1,
  "source_revision": {
    "kind": "git_commit",
    "commit_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  },
  "source_bundle": {
    "key": "snapshots/source.tar",
    "version_id": "opaque-source-version-17",
    "sha256": "sha256:<64 lowercase hex>",
    "byte_size": 12345
  },
  "index_bundle": {
    "key": "snapshots/index.sqlite3",
    "version_id": "opaque-index-version-17",
    "sha256": "sha256:<64 lowercase hex>",
    "byte_size": 67890
  },
  "indexer_identity": {
    "name": "sfra-indexer",
    "version": "4.2.0"
  },
  "sqlite_schema_identity": {
    "engine": "sqlite",
    "schema_info_version": 2
  }
}
\`\`\`

The import variant replaces \`commit_sha\` with \`import_id\`. Both object identities are required and each includes key, immutable version ID, full-payload SHA-256 and positive byte size. Mutable aliases such as \`latest\`, \`current\`, \`head\` and \`*\` are rejected.

For `sqlite_schema_identity`, `schema_info_version` is the value stored in E1's singleton `schema_info.schema_version` row. It is not SQLite `PRAGMA user_version`: current E1 writers/readers do not set or read that PRAGMA, and the two metadata locations must not be treated as aliases. A cloud E1 verifier must require exact equality with the schema version supported by E1 read APIs (`SCHEMA_VERSION`, currently `2`); the legacy restore verifier's permissive `<=` rule is not valid for this contract. The old `user_version` property is rejected as unknown.

Canonical serialization uses UTF-8, Unicode NFC strings, lexicographically sorted object keys, compact separators, no NaN/Infinity, no duplicate JSON keys and no trailing whitespace. Parsers reject non-canonical encodings even if they are semantically equivalent JSON. The JSON Schema Draft 2020-12 files are a structural preflight layer: they reject empty/space-wrapped immutable identifiers and exact mutable aliases where expressible. Python runtime parsing remains the fail-closed authority for Unicode NFC and control/surrogate character checks that JSON Schema cannot portably express. Opaque IDs are never trimmed or normalized; accepted values are preserved exactly.

The manifest does **not** contain \`manifest_sha256\` or \`snapshot_id\`. Its digest is the detached value \`sha256:<hex>\` over the exact canonical manifest bytes. This avoids a self-referential digest.

## Cloud SnapshotRef v2

The identity tuple binds:

1. \`snapshot_schema_version = 2\`;
2. typed immutable source revision;
3. exact source bundle object key, opaque version ID, SHA-256 and byte size;
4. exact index bundle object key, opaque version ID, SHA-256 and byte size;
5. detached canonical manifest SHA-256;
6. indexer name/version;
7. SQLite engine and the E1 application schema version stored in `schema_info.schema_version`, named `schema_info_version`.

\`snapshot_id\` is derived as \`sha256:<hex>\` from canonical UTF-8 JSON serialization of the complete tuple above, excluding only the \`snapshot_id\` field itself. The tuple is deterministic and any change to any bound value changes the ID.

The ref parser requires exact fields and exact schema version. It recomputes the ID and rejects forged, incomplete, unknown or unsupported values. \`verify_cloud_snapshot_manifest()\` additionally checks the digest over exact bytes, canonical serialization, and equality of every identity component with the ref.

## Machine-readable schemas

- `schemas/cloud-snapshot-manifest-v1.schema.json` — canonical manifest payload v1.
- `schemas/cloud-snapshot-ref-v2.schema.json` — cloud SnapshotRef v2 wire identity.

Both files use JSON Schema Draft 2020-12 and close root and nested objects with `additionalProperties: false`. Immutable object version IDs and immutable import IDs reject leading/trailing whitespace and the mutable aliases `latest`, `current`, `head` and `*`, case-insensitively. The schemas are a structural preflight layer; the Python runtime remains authoritative for Unicode NFC and control/surrogate validation that is not expressed portably in JSON Schema. Accepted opaque identifiers are not trimmed or normalized.

## Public module API

Import from \`sfra_context_integrations.cloud_snapshot_v2\`:

- \`GitCommitSourceRevision\`
- \`ImmutableImportSourceRevision\`
- \`ImmutableObjectVersion\`
- \`IndexerIdentity\`
- \`SqliteSchemaIdentity\`
- \`CloudSnapshotManifestV1\`
- \`CloudSnapshotRefV2\`
- \`build_cloud_snapshot_v2(manifest)\`
- \`cloud_snapshot_ref_v2_from_dict(value)\`
- \`serialize_cloud_snapshot_manifest(manifest)\`
- \`parse_canonical_cloud_snapshot_manifest(raw_bytes, expected_sha256=None)\`
- \`verify_cloud_snapshot_manifest(ref, raw_manifest_bytes)\`

The builder returns a ref plus canonical manifest bytes. It does not write files, contact storage, sign, upload or activate anything.

## Scope and safety

This contract is pure Python and provider-neutral. It has no network, filesystem, SQLite, GitHub, credential, signature or cloud-provider side effects. Tests use synthetic identifiers and in-memory bytes only. Signing envelopes may be added by a later contract, but no signing key or signing service is provisioned here.
