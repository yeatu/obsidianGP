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
