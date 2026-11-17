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

## Source-verified exact node lookup (E1)

The public API `get_node_by_id` returns a current Structural Node only after verifying it against the original Markdown file. The database path is explicit; no package-level global database configuration is used.

```python
from pathlib import Path
from sfra_indexer import NodeLookupStatus, get_node_by_id

result = get_node_by_id(
    db_path=Path("/path/to/restored-index/structure.sqlite3"),
    node_id="node_<UUID4>",
    expected_hash="sha256:<64 lowercase hex>",
    vault_root=Path("/path/to/checkout/ГП"),
)

if result.status is NodeLookupStatus.OK:
    print(result.node.raw_text)  # exact slice from the current Markdown file
else:
    print(result.status.value, result.error_code)
    assert result.node is None
```

The successful response includes `node_id`, `content_hash`, `source_path`, `node_type`, `parent_node_id`, `heading_path`, exact `raw_text`, line/character/UTF-8-byte coordinates and the verified whole-file `source_sha256`. `NodeLookupResult.to_dict()` emits `{"status": "...", "node": null}` for every unsuccessful status.

Possible statuses:

- `ok`: the active node and its exact source slice were verified.
- `stale_source`: the current file is missing/changed, or the requested Hash is no longer current.
- `deleted`: the indexed document or node address was deleted.
- `ambiguous`: matching history does not identify one safe current node.
- `not_found`: the Node ID is absent from the index.
- `invalid_request`: malformed Node ID/Hash, database path, or Vault root.
- `integrity_error`: damaged SQLite/history, unsafe stored path, invalid coordinates, unsupported secure-open semantics, or inconsistent stored data.

The API opens SQLite in read-only/query-only mode and never calls the schema-creating `connect_database()`. It checks the complete event history, saved-text and latest-version integrity before resolving terminal statuses. For an active node it then opens the source under the supplied Vault root using descriptor-relative no-follow resolution, checks file identity before/after reading, hashes the whole file, reconstructs the exact slice using Python character offsets, cross-checks UTF-8 byte and line offsets, and compares the slice SHA-256 with both the stored Content Hash and `expected_hash`. No text is returned for a failed status. The stored `raw_text` is only a consistency witness, never the returned source.

The current schema stores a relative path, not the Git ref. The caller must therefore pass the intended Vault checkout root explicitly. The persistence workflow records that checkout's ref and actual commit SHA in the manifest as described below.


## Public source-reading interface for E3

The package exposes four source-reading operations through sfra_indexer. E3 must use these public functions and result types; it must not query the implementation's SQLite tables directly.

All four operations take the same anchor and environment:

~~~python
from pathlib import Path
from sfra_indexer import (
    get_document_by_id,
    get_neighbors_by_id,
    get_node_by_id,
    get_parent_by_id,
)

db_path = Path("/path/to/restored-index/structure.sqlite3")
vault_root = Path("/path/to/the/selected/checkout/ГП")

node = get_node_by_id(db_path, node_id, expected_hash, vault_root)
parent = get_parent_by_id(db_path, node_id, expected_hash, vault_root)
neighbors = get_neighbors_by_id(db_path, node_id, expected_hash, vault_root)
document = get_document_by_id(db_path, node_id, expected_hash, vault_root)
~~~

### Shared address and version rules

- The input address is always the exact pair node_id + expected_hash. The pair addresses the current Structural Node; the API never searches by text or chooses a similar node.
- The SQLite path and selected Vault root are explicit arguments. No environment variable, global package setting, or implicit checkout selection is used.
- The anchor must pass the same schema-v2 DB-only preflight and current source verification as get_node_by_id.
- Every additional NodeRecord returned by a relation operation is independently resolved by its current node_id + content_hash and verified against the same source checkout.
- stale_source, deleted, ambiguous, not_found, invalid_request and integrity_error are propagated as result statuses. On any failed operation, all content fields for that operation are null; no partial parent, neighbor or document text is returned.
- Historical hashes are not accepted as a way to retrieve an older version. A changed anchor Hash returns stale_source; a deleted or ambiguous anchor returns its corresponding status.
- All success text is read from current Markdown bytes. SQLite raw_text remains a consistency witness only.

### 1. Node

get_node_by_id(db_path, node_id, expected_hash, vault_root) -> NodeLookupResult

Returns exactly one currently active and unambiguous Structural Node. The node text is the original source slice identified by the stored half-open character offsets, with verified UTF-8 byte offsets, line coordinates, whole-file SHA-256 and expected Content Hash.

### 2. Parent

get_parent_by_id(db_path, node_id, expected_hash, vault_root) -> NodeParentResult

The node field is the verified anchor. parent is its immediate structural parent according to the current parent_node_pk, cross-checked against the latest node_versions.parent_node_id. The parent is then read through the same public Node ID + Content Hash checks.

A document-root node has no parent and returns status="ok", parent=null. If the parent is stale, deleted, ambiguous or cannot be source-verified, the operation fails with that status and returns neither anchor nor parent content.

### 3. Neighbors

get_neighbors_by_id(db_path, node_id, expected_hash, vault_root) -> NodeNeighborsResult

Returns only the immediate previous and next siblings in source order. A sibling is a current structural node in the same document with the same parent; the ordering key is the structural source range (char_start, char_end, node_pk as a deterministic tie-breaker).

Document boundaries are represented by previous=null or next=null. An ambiguous immediate sibling is not skipped to select a more distant neighbor: the whole operation returns ambiguous. A selected sibling is returned only after its own current Hash and source slice have been verified. If any selected neighbor is stale, deleted, ambiguous or otherwise invalid, no partial neighbor list is returned.

### 4. Document

get_document_by_id(db_path, node_id, expected_hash, vault_root) -> DocumentLookupResult

The Node ID + Content Hash pair is an anchor into one document. After validating the anchor, the operation reads the complete Markdown file at the indexed relative path, checks its full SHA-256 against documents.source_sha256 (surfaced as anchor.source_sha256), and strictly decodes UTF-8 without newline or Unicode normalization. document.raw_text is the complete original file; document.source_path, document.source_sha256 and document.size_bytes describe that exact byte sequence.

If the anchor is stale, deleted or ambiguous, the document is not returned. If the file changes or disappears between anchor verification and complete-document reading, the operation returns stale_source without text.

### Result types

- NodeLookupResult: status, node, optional error_code/message.
- NodeParentResult: status, verified anchor node, optional parent, optional error.
- NodeNeighborsResult: status, verified anchor node, optional previous/next, optional error.
- DocumentLookupResult: status, verified anchor, optional complete document, optional error.
- DocumentRecord: source_path, source_sha256, size_bytes, complete source raw_text.

All result classes provide to_dict(). For failure results, the content fields are null; safe error details contain codes and messages only, never excerpts or absolute source paths.

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
