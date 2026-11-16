# SFRA Structural Indexer — Stage B

This stage provides a source-preserving Markdown AST parser, a structural tree, exact source extraction, structural Passage records, a basic SQLite sidecar schema, a Python API, and a CLI.

**Scope:** structural parsing only. Stable Node ID assignment, Content Hash versioning, ambiguous remapping, and incremental synchronization belong to stage C. FTS5, entities, facets, embeddings, Context Builder and MCP are intentionally absent.

## Requirements

- Python 3.10+
- markdown-it-py 4.x
- pytest for running the test suite

Install into a virtual environment:

~~~bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e . pytest
~~~

The PyPI release history currently lists markdown-it-py 4.3.0. The dependency range is >=4.2.0,<5.0.0 for compatibility with the 4.x API. The execution environment used for stage-B validation had 4.2.0 available offline, so 4.3.0 itself could not be installed or separately exercised here.

## Run tests

~~~bash
python -m pytest
~~~

## Python API

~~~python
from sfra_indexer import parse_markdown, extract_source_slice

source = "# Heading\n\nOriginal **Markdown** text.\n"
doc = parse_markdown(source, source_path="folder/note.md")

for node in doc.iter_nodes():
    original = extract_source_slice(source, node.span)
    assert original == node.raw_text

heading = next(node for node in doc.iter_nodes() if node.node_type == "heading")
print(heading.heading_path, heading.line_start, heading.line_end)
~~~

Main functions:

- parse_markdown(source, source_path, max_passage_words=900) parses one in-memory string.
- ParsedDocument.extract_node(local_key) returns the exact original source slice for a node.
- extract_source_slice(source, span) extracts a node or Passage using its half-open character offsets.
- build_passages(document, max_words=900) partitions only on existing child boundaries. It does not split atomic constructs.
- index_vault(vault_path, index_dir) performs a batch parse of all Markdown files into index_dir/structure.sqlite3.

local_key is only a deterministic key inside one parse result. It is not a persistent Node ID. node_id and content_hash remain None until stage C.

## CLI

Parse one file and print a JSON tree:

~~~bash
sfra-index parse path/to/note.md
~~~

Index an entire Vault to an external directory:

~~~bash
sfra-index index --vault /path/to/Vault --index-dir /path/outside/Vault/.sfra-index
~~~

Show counts:

~~~bash
sfra-index info --db /path/outside/Vault/.sfra-index/structure.sqlite3
~~~

The index directory must be outside the source Vault. The parser reads Markdown in UTF-8 with newline="" and preserves source LF/CRLF. Empty Markdown files are represented as documents with zero bytes and a document root node.

## Structural rules

- Headings H1–H6 form nested section nodes. A heading's raw_text and span include its descendant sections up to the next heading of equal or higher rank. Its content_spans separately list the heading marker and its direct block content, excluding child heading sections.
- Lists are explicit list → list_item → nested blocks. A list item's raw_text includes its nested list subtree; content_spans contains only its direct blocks, excluding nested list children.
- Blockquotes and Obsidian > [!TYPE] callouts are retained as atomic block nodes.
- Tables, fenced/indented code, and quotes are not arbitrarily split. Tables are enabled using markdown-it-py's built-in table rule.
- Markdown links remain inside their original block. Resolved link targets are recorded as navigation metadata; the indexer does not rewrite or separately fetch them.
- Documents without headings are represented as block nodes under the document root. Adjacent paragraphs are not merged in this first parser version.

## Coordinate contract

line_start and line_end are 1-based and inclusive. Character and UTF-8 byte offsets are 0-based, half-open ([start, end)). Character offsets count Python Unicode code points. For every node and Passage:

~~~python
source[node.char_start:node.char_end] == node.raw_text
source.encode("utf-8")[node.byte_start:node.byte_end].decode("utf-8") == node.raw_text
~~~

A Passage raw_text contains only its source slice. Parent heading context is stored separately in context_text with original heading-line coordinates in context_spans.

The word estimate is a Unicode word-character count. It is approximate and is not a model-token count. The 400–900 target is soft: when a single block has no safe child boundary, it remains whole and receives an explicit warning.

## SQLite schema

structure.sqlite3 contains:

- schema_info — schema version;
- documents — source path, UTF-8 byte size and parser version;
- structural_nodes — node type, parent reference, heading path, source coordinates, content spans, raw Markdown and parser metadata;
- passages — exact source ranges, owner node, separate context, approximate word count and warnings.

No FTS or entity tables are created. Stage B uses local_key plus an internal SQLite primary key. The node_id column exists for forward compatibility but is NULL in this stage.

## Stage-B limitations

1. index_vault is a batch snapshot rebuild, not an incremental synchronizer. Stage C will add file-version checks and stable matching.
2. The word estimate is only a coarse heuristic; there is no model-specific tokenizer.
3. Callout contents are intentionally atomic in this stage. Child structure inside a Callout is not separately exposed.
4. Obsidian-specific syntax beyond callouts (for example, embeds, wikilinks, properties and community-plugin blocks) is retained verbatim but not semantically interpreted.
5. Markdown parsing uses CommonMark plus GFM tables. Other extensions are not enabled implicitly.
