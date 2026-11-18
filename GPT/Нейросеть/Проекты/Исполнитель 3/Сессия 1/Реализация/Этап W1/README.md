# SFRA Web adapter W1 — synthetic-only

This isolated package implements the approved GitHub Issues → GitHub Actions → SFRA worker transport. The preserved Local MCP lane is not used by this adapter.

## Implemented

- Fail-closed issues.opened event gate: exact repository (yeatu/obsidianGP), exact owner login (yeatu), non-PR Issue and [SFRA] title prefix.
- Strict 32 KiB UTF-8 body cap and SHA-256 over exact body bytes.
- Comment-backed immutable first-seen digest; only comments authored by the exact `github-actions[bot]` identity are trusted as ledger markers, so human marker spoofing cannot poison first-seen binding.
- Event `sender.login` must match the owner-authorized Issue author; missing or mismatched senders fail closed.
- Bounded comment pagination reads at most 10 pages of 100 comments and fails closed if history exceeds that limit.
- GitHub REST reader/comment ports with bounded responses, sanitized failures and no request/response logging.
- Thin event handler around the existing V2.2 IssueWorkerCore contract.
- GitHub Actions runner injects synthetic-only search/read application ports. It does not instantiate production E1 readers, E2 indexes, SQLite, Vault or sidecar.
- Allowlist-only transport status v2 comment. The worker's V2.2 projector emits counts/status/diagnostic codes only; source fragments, paths, titles, hashes and raw text are not serialized.
- Per-Issue Actions concurrency with cancel-in-progress disabled and a fixture-only PR test job.

## Workflow

Only an owner-authored [SFRA] Issue opened in yeatu/obsidianGP enters the worker job. issues.edited, issue_comment, pull requests and other repositories do not execute it. The job uses only contents: read and issues: write.

The body must contain the exact sfra.issue.v1 request envelope accepted by V2.2. A response is written as a comment on that same synthetic request Issue. Workflow stdout contains only a bounded outcome label.

## Safety and recovery

- Synthetic corpus v1.0.0 and disposable fixture data only.
- Never check out or mount the real Vault, production SQLite or sidecar.
- read_source is serviced by an injected synthetic port only. Production read_source activation remains blocked pending independent A review and C acceptance of #36/#51/#67.
- No issues.edited, issue_comment, HTTP server, MCP, production workflow, production persistence or source-bearing artifacts.
- Delivery is **at least once**, not exactly once: a crash after application execution but before the terminal comment can cause a retry and repeated application call. A bot-authored terminal marker suppresses later duplicate deliveries; this is best-effort deduplication after read-before-write.
- A STARTED marker with no terminal marker is retryable after a runner interruption. A changed body under the same Issue is rejected and never re-bound.
- A FAILED marker is terminal. Recovery requires an operator to preserve the original request and markers, then open a new owner-authored `[SFRA]` Issue with a new request ID and unchanged payload intent; do not edit or delete the original Issue/comments.
- Issue comment history at or above 100 entries fails closed rather than silently ignoring older markers. Manual recovery must preserve the first marker; do not delete or rewrite it.

## Tests

    python -m pip install -e ".[test]"
    pytest

All adapter tests are synthetic. The fixture workflow installs the accepted B1, V2.1 integration, E2 search and V2.2 core layers so imports and contracts are exercised without production data.
