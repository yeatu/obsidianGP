# SFRA Structural Indexer — Stage B + C

This package provides source-preserving Markdown parsing, a structural tree, exact source extraction, parent-aware Passage context, SQLite storage, persistent Node IDs, SHA-256 Content Hashes, node versions, conservative remapping, incremental Vault indexing, a Python API, and a CLI.

**Scope:** structural indexing only. FTS5, entities, aliases, facets, embeddings, Context Builder and MCP are intentionally absent.

## Requirements and installation

- Python 3.10+
- markdown-it-py 4.x
- pytest for the test suite

~~~bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e . pytest
~~~

The dependency range is `markdown-it-py>=4.2.0,<5.0.0`. CI has verified this implementation on markdown-it-py 4.3.0 and Python 3.13.

## Run tests

~~~bash
python -m pytest
~~~

## Python API

Parse a document in memory:

~~~python
from sfra_indexer import parse_markdown, extract_source_slice

source = "# Heading\n\nOriginal **Markdown** text.\n"
doc = parse_markdown(source, source_path="folder/note.md")

for node in doc.iter_nodes():
    assert extract_source_slice(source, node.span) == node.raw_text
~~~

Index a Vault to an external sidecar directory:

~~~python
from sfra_indexer import index_vault, get_database_summary

result = index_vault("/path/to/Vault", "/path/outside/Vault/.sfra-index")
print(result.documents_indexed, result.documents_skipped)
print(get_database_summary(result.database_path))
~~~

Main functions:

- `parse_markdown(source, source_path, max_passage_words=900)` parses one in-memory string.
- `ParsedDocument.extract_node(local_key)` returns the exact source slice for a parse-local node.
- `extract_source_slice(source, span)` extracts a node or Passage using half-open character offsets.
- `build_passages(document, max_words=900)` partitions only on existing child boundaries. It does not split atomic constructs.
- `content_hash(raw_text)` returns `sha256:<hex>` for the exact UTF-8 source slice.
- `index_vault(vault_path, index_dir)` hashes files, skips unchanged documents and atomically reindexes only changed documents.

## CLI

Parse one file and print its structural tree:

~~~bash
sfra-index parse path/to/note.md
~~~

Incrementally index every Markdown file in a Vault:

~~~bash
sfra-index index --vault /path/to/Vault --index-dir /path/outside/Vault/.sfra-index
~~~

Show sidecar counts and node lifecycle states:

~~~bash
sfra-index info --db /path/outside/Vault/.sfra-index/structure.sqlite3
~~~

The index directory must be outside the source Vault. The parser reads UTF-8 with `newline=""` and preserves source LF/CRLF. Empty Markdown files are represented as documents with zero bytes and a document-root node. Deleted source files remain in SQLite with document status `deleted`, and their former active nodes become `stale`.

## Atomic Source Scope API (E1)

The canonical public API is `read_source_scope`. It reads one source scope through one SQLite read transaction and one safe source-file read. The four legacy methods remain public compatibility wrappers over this implementation; they do not maintain separate lookup paths.

```python
from pathlib import Path
from sfra_indexer import (
    NodeLookupStatus,
    read_source_scope,
    resolve_current_node,
)

db_path = Path("/path/to/isolated-snapshot/state/structure.sqlite3")
vault_root = Path("/path/to/the-matching-checkout/ГП")
snapshot_id = "sha256:<manifest-digest-computed-by-E3>"

address = resolve_current_node(
    db_path, "node_<UUID4>", snapshot_id=snapshot_id
)
if address.status is NodeLookupStatus.OK:
    result = read_source_scope(
        db_path,
        vault_root,
        address.node_id,
        address.content_hash,
        scope="parent",  # node | parent | neighbors | document
        snapshot_id=address.snapshot_id,
    )
```

### Four scopes

- `node`: the exact target Structural Node.
- `parent`: target and its immediate structural parent, when present.
- `neighbors`: target and its immediate previous/next siblings under the same parent. `result.fragments` is in source order: previous, anchor, next (omitting a missing boundary neighbor). An ambiguous immediate neighbor fails the whole request; the implementation never skips it.
- `document`: the complete original Markdown file, byte-for-byte as decoded from strict UTF-8. It is returned as `result.document.raw_text`; it is not reconstructed from SQLite node versions.

For `node`, `parent`, and `neighbors`, `result.fragments` contains the verified NodeRecords. Every NodeRecord carries `node_id`, `content_hash`, `source_path`, `document_hash` (the exact `documents.source_sha256` value), `index_generation` (the exact `documents.generation` value), exact `raw_text`, coordinates, and only the metadata already stored for that node. No policy fields such as `preservation`, `required_with`, or `parent_context_required` are synthesized.

For `document`, `result.document` contains `source_path`, `document_hash`, `index_generation`, byte size, the anchor Node ID/Content Hash, and the complete Markdown text. `result.anchor` contains the independently verified anchor fragment.

### Atomicity and failure behavior

A scope call opens one existing SQLite file in read-only/query-only mode, begins one read transaction, and uses that connection for all node, parent, neighbor, document, version, lifecycle and event queries. The associated Markdown file is opened once beneath the supplied Vault root; its whole-file hash is checked once, and all selected node slices are derived from those same bytes. Related nodes must belong to the same document record, path, source hash and current document generation as the anchor.

If any required record is absent, stale, ambiguous, deleted, inactive, cross-document, incorrectly bound, or fails Hash/coordinate/source validation, the call returns an explicit status and an empty `fragments` list. It never returns a partial parent, neighbor set, or document. Text is never sourced from historical `node_versions`.

`snapshot_id` is opaque to E1. It is echoed unchanged in every `SourceScopeResult` and `CurrentNodeAddress`. E1 does not verify Git commits, manifests, SnapshotRef, or the relationship between a sidecar and a Vault commit. E3 owns that verification and passes the matching `db_path`, `vault_root`, and `snapshot_id`.

### Resolving the current address

`resolve_current_node(db_path, node_id, *, snapshot_id)` returns a `CurrentNodeAddress` with the current `node_id`, `content_hash`, `source_path`, `document_hash`, and `index_generation`. It uses only the exact Node ID, accepts only one active/unambiguous current row, and does not perform fuzzy matching or return historical versions. This resolver is DB-only because it has no Vault argument; the subsequent `read_source_scope` call verifies the address against the original Markdown.

### Compatibility methods

The existing public methods remain available and delegate to the unified API:

- `get_node_by_id` → `scope="node"`
- `get_parent_by_id` → `scope="parent"`
- `get_neighbors_by_id` → `scope="neighbors"`
- `get_document_by_id` → `scope="document"`

### Result statuses

The common status set is `ok`, `stale_source`, `deleted`, `ambiguous`, `not_found`, `invalid_request`, and `integrity_error`. On any failed Source Scope operation, `fragments=[]`, `anchor=null`, and `document=null`. Error messages/codes do not contain source excerpts or absolute paths.

No token budget or content truncation is applied. E1 returns complete verified source text; Context Builder budgeting belongs to E3.
 
## Structural model

- Headings H1–H6 form nested section nodes. A heading's `raw_text` and span include descendant sections up to the next heading of equal or higher rank. Its `content_spans` separately list its own heading line and direct block content, excluding child heading sections.
- Lists are explicit `list → list_item → nested blocks`. A list item's `raw_text` includes its nested list subtree; `content_spans` contains only its direct blocks, excluding nested list children.
- Blockquotes and Obsidian `> [!TYPE]` callouts are retained as atomic block nodes.
- Tables, fenced/indented code, and quotes are not arbitrarily split. Tables are enabled using markdown-it-py's table rule.
- Markdown links remain inside their original block. Resolved targets are stored as navigation metadata; the indexer does not fetch external pages.
- Documents without headings are represented as block nodes under the document root. Adjacent paragraphs are not merged in this version.

## Passage and parent context

A Passage's `raw_text` and coordinates always identify only its exact source slice. Parent context is stored separately in `context_text` and `context_spans`.

For nested lists, every ancestor list item contributes only its own `content_spans` to Passage context. This preserves a parent condition or rule without copying descendant branches into context or changing the Passage source range. Heading ancestors contribute their original heading lines.

The word estimate is a Unicode word-character count. It is approximate and is not a model-token count. The 400–900 target is soft: when a single block has no safe child boundary, it remains whole and receives an explicit warning.

## Coordinate contract

- `line_start` / `line_end`: 1-based, inclusive;
- `char_start` / `char_end`: 0-based, half-open Python Unicode code-point offsets;
- `byte_start` / `byte_end`: 0-based, half-open UTF-8 byte offsets.

For every node and Passage:

~~~python
source[node.char_start:node.char_end] == node.raw_text
source.encode("utf-8")[node.byte_start:node.byte_end].decode("utf-8") == node.raw_text
~~~

## Node ID, Content Hash and versions

Node ID and Content Hash are independent:

- `node_id` is an opaque `node_<UUID4>` identity stored in SQLite. It is reused only when old and new nodes have an unambiguous structural match.
- `content_hash` is SHA-256 of the exact original Markdown in `raw_text`. It changes when that exact source slice changes, even when Node ID remains stable.
- `node_versions` stores snapshots of content, source coordinates, heading path, parent Node ID and metadata. A new version is stored when content or its source locator/parent changes.

Matching is conservative:

1. unique same-type, same-Content-Hash match within the document;
2. unique heading match by exact `level + title`, including a moved heading;
3. unique 1:1 same-type sibling slot under an already matched parent;
4. unresolved many-to-many candidates are marked `ambiguous`, receive new Node IDs and record previous candidate IDs. Previous IDs become `stale`; they are never silently assigned to one candidate.

A heading rename is not inferred from similarity alone. A moved block whose content also changed and whose parent changed has no reliable anchor and is not guessed. Use the recorded match events to inspect such cases.

## Incremental synchronization

Each file is hashed using SHA-256 of its exact UTF-8 content. If its source hash is unchanged and the document is active, parsing and writes are skipped. If changed, only that document is parsed and updated in a SQLite transaction.

The `index` command reports `documents_seen`, `documents_indexed`, and `documents_skipped`. A new Vault index starts each document at generation 1. A later changed document increments only its own generation. Unchanged documents keep their node versions and match-event history untouched.

Removed files are not physically deleted from the sidecar history. Their document state becomes `deleted`, active node rows become `stale`, and previous `node_versions` remain queryable.

## SQLite schema

- `schema_info` — current schema version;
- `documents` — source path, file SHA-256, generation and active/deleted status;
- `structural_nodes` — current and stale node rows, Node ID, Content Hash, parent link, coordinates, raw Markdown, status and lifecycle generations;
- `passages` — exact source ranges, owner node, separate parent context and approximate word count;
- `node_versions` — immutable node snapshots indexed by Node ID and sequential version number;
- `node_match_events` — reason for each match/new/stale/ambiguous decision and candidate Node IDs.

Schema migration upgrades Stage-B databases from version 1 to version 2, assigns initial UUIDs, computes initial Content Hashes, records version 1 and derives each stored file hash from the saved document-root text. No FTS or entity tables are created.

## Known limitations

1. Matching is deliberately conservative. Ambiguous repeated structures may receive new IDs instead of a risky inherited ID.
2. A heading rename is treated as a new heading unless it can be uniquely matched by unchanged content hash.
3. A document reappearing after it was marked deleted is treated as a new active lineage; stale IDs from deleted generations are not silently revived.
4. Callout, blockquote, table and code contents remain atomic in this stage. Child structure inside a Callout is not separately exposed.
5. Obsidian syntax beyond callouts (for example, embeds, wikilinks, properties and community-plugin blocks) is retained verbatim but not semantically interpreted.
6. Parsing uses CommonMark plus GFM tables. Other extensions are not enabled implicitly.


## GitHub Actions state persistence

The \`sfra-state\` branch is a true orphan branch with one root commit and no parent. Its tree is restricted to \`README.md\`, \`state/structure.sqlite3\`, and \`state/manifest.json\`. The production workflow restores the saved database, checks its manifest digest and SQLite integrity, indexes the Vault into a temporary directory outside the Vault, and then publishes a consistent SQLite Backup API snapshot.

The first production initialization is explicit: run \`SFRA persistent SQLite state\` with \`initialize_state=true\`. Normal pushes never silently replace missing state with a new database. Subsequent runs restore the previous database and use a regular fast-forward push after checking the remote branch head. A concurrency group serializes writers.

The state branch separates files and Git history from the source Vault but does not restrict repository access. SQLite includes source text in current and historical node snapshots. Anyone who can read the repository and this branch can read that content.

Each persistence run checks out an explicit `vault_ref` input (default: `executor-1/sfra-indexer-session-1`; never an implicit switch to `main`), resolves its actual `vault_commit_sha` using `git rev-parse HEAD`, indexes only that checkout's `ГП/` tree, and stores both values in `state/manifest.json`. Legacy `source_branch` and `source_commit` keys remain as aliases so existing manifest readers continue to work. When manually dispatching the workflow, choose the Vault ref deliberately; the implementation branch and Vault source ref are separate concepts.

The independent-run integration test will use its own fixture Vault, SQLite database, and \`sfra-state-test\` branch. It must never write test data to production \`sfra-state\`.


## Additive E1 cloud-index verification

The public, read-only cloud-index verification API is additive and separate from
the Git-backed v1 state manifest and restore workflow:

- parse_cloud_index_attestation(raw_bytes) parses the exact canonical
  sfra.e1.cloud-index-attestation.v1 payload into immutable E1-owned types.
- verify_materialized_cloud_index(database_path, source_root, *,
  expected_source_revision=..., attestation=..., markdown_inventory=...) verifies
  the already-materialized Markdown tree, the exact #119 inventory/attestation
  bytes, and the E1 SQLite database. expected_source_revision must be the exact
  E1-owned tagged revision (or its strict primitive mapping) from the outer
  verified snapshot reference; the tag and value must match the attestation.
- The result is an immutable CloudIndexVerificationReport; failures raise
  CloudIndexVerificationError with a stable code and a safe message.

The verifier opens SQLite read-only, enables query-only mode, checks the exact
schema_info.schema_version value (currently 2), and never calls the mutating
database connection or migration path. The public SourceRevision union keeps Git revisions and opaque immutable-import
IDs as separate tagged variants. The report establishes consistency of the
materialized snapshot; it does not authenticate source origin or provider
immutability. All tests use temporary synthetic fixtures only.


### E1 verifier resource envelope (C3 decision #260)

The verifier applies these operational admission limits without changing the
accepted #119 inventory/attestation wire format or Markdown selection rules:
attestation 2 MiB; inventory 64 MiB; 100,000 Markdown rows; 256 parser identity
pairs; 500,000 total source-tree entries (including directories and
non-Markdown files); one Markdown file 32 MiB; aggregate Markdown bytes 2 GiB;
and relative path length 4,096 characters. Limits are enforced during parsing
or traversal. Markdown bytes are hashed in chunks and at most one Markdown file
is retained for span verification. Non-Markdown attachment payloads are not
read. Exceeding any ceiling raises the stable `resource_limit_exceeded` code.
A larger valid #119 bundle remains valid at producer level but must not be
promoted by an E1 verifier invocation outside this execution envelope.
