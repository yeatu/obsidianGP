# SFRA Web adapter W1 — synthetic-only

This package is the transport boundary for the approved GitHub Issues → GitHub Actions → SFRA worker path. It is separate from the preserved Local MCP lane.

## Implemented slice

- Fail-closed issues.opened event gate.
- Exact repository (yeatu/obsidianGP), exact owner login (yeatu), non-PR Issue, [SFRA] title prefix and 32 KiB UTF-8 body cap.
- Exact-byte SHA-256 binding.
- Comment-marker ledger for first observation, interrupted-run retry, terminal idempotency and changed-body rejection.
- GitHub Actions must serialize a single Issue (cancel-in-progress disabled) before consulting the comment ledger.

The next slice wires these primitives to the existing V2.2 IssueWorkerCore through injected ports, adds a bounded allowlist-only response comment, and supplies fixture-only end-to-end tests.

## Safety boundary

- Synthetic corpus v1.0.0 and disposable fixtures only.
- Never check out or mount the real Vault, production SQLite or sidecar.
- Never invoke production source readers or indexers.
- read_source mechanics remain injected/mock-only until verifier chain #36/#51/#67 receives A review and C acceptance.
- Do not log Issue bodies, queries, task text, hashes, source paths, node IDs, excerpts or fragments.
- Do not upload response bodies or source-bearing artifacts.
- Only the intended synthetic response Issue comment may contain synthetic test output.
- No issues.edited, issue_comment, pull-request, HTTP, MCP or production workflow triggers.

## Tests

    python -m pip install -e ".[test]"
    pytest

This initial slice has no network client and cannot access GitHub or any Vault.
