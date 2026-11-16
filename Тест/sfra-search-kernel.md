# SFRA FTS5 search-kernel smoke test

## Purpose

Verify the next dependency after the GitHub Issue bridge:

- the Stage-B/C structural indexer can process the real `ГП/` Vault snapshot;
- SQLite FTS5 is available in the GitHub Actions runner;
- structural nodes can be indexed into a temporary FTS5 table;
- a phrase query finds the expected real source document;
- every returned hit preserves its exact source slice and SHA-256;
- the original Vault stays unchanged.

## Implementation under test

Structural indexer source branch:

`executor-1/sfra-indexer-session-1`

The harness is intentionally kept in this `Тест/` folder. It adds a temporary FTS5 table on top of the structural indexer database without modifying the upstream structural schema or Vault notes.

This is a search-kernel prototype, not yet the final Stage-2 module. It tests exact phrase search with SQLite's `unicode61` tokenizer. Russian morphology, entity aliases, numeric normalization, faceting, ranking policy, and Context Builder are not included yet.

## Run through ChatGPT/GitHub Issue bridge

Create an Issue with title:

`[SFRA-SEARCH-KERNEL] Phrase search smoke test`

Use this JSON body:

```json
{
  "operation": "search_vault",
  "query": "остановка кровообращения",
  "expected_path": "персонажи/ученики/Молодая кровь/Генрих Фауст.md"
}
```

The workflow checks the author and title prefix before starting. It checks out the test harness from `main` and the structural indexer from `executor-1/sfra-indexer-session-1`, runs its regression tests, indexes `ГП/` into a temporary runner directory, builds FTS5, searches, verifies source slices and hashes, and posts a report as an Issue comment.

## Expected success

The comment begins with `SFRA_SEARCH_OK` and includes:

- documents and nodes indexed;
- FTS5 row count;
- number of matching nodes;
- expected source path;
- Node ID and Content Hash for each returned hit;
- a short source excerpt.

The run must also pass `git diff --exit-code -- ГП`, proving the index operation did not modify the Vault checkout.

## Public repository notice

This repository is public. Issue query, expected path, search result excerpts, Node IDs, hashes, and workflow logs are public. Do not submit credentials or unrelated private material.
