# SFRA Web adapter W1 — synthetic-only

This isolated package implements the approved GitHub Issues → GitHub Actions → SFRA worker transport. The preserved Local MCP lane is not used by this adapter.

## Implemented

- Fail-closed issues.opened gate: exact repository (yeatu/obsidianGP), owner-authored Issue, matching webhook sender, non-PR Issue and [SFRA] title prefix.
- Strict 32 KiB UTF-8 body cap and SHA-256 over exact event-body bytes.
- Comment-backed immutable first-seen digest; marker authors must match the exact GitHub Actions bot login `github-actions[bot]` and stable numeric user ID `41898282`. If GitHub comment metadata includes an account `type`, it must be `Bot`; missing or mismatched numeric IDs fail closed. The stable ID is verified from GitHub's public user profile API: https://api.github.com/users/github-actions%5Bbot%5D. Both `MarkerLedger` and `GitHubCommentStatusStore` consume markers through the same `authenticated_markers()` function.
- Bounded comment pagination reads at most 10 pages of 100 comments; excess history fails closed.
- GitHub REST Issue/comment ports with bounded responses, sanitized failures and no request/response logging.
- Thin handler around the existing V2.2 IssueWorkerCore contract.
- Actions runner injects synthetic-only V2.1-shaped search/read application ports. It does not instantiate production E1 readers, E2 indexes, SQLite, Vault or sidecar.
- V2.2 status-v2 aggregate plus a separate W1-specific allowlisted synthetic evidence projection in the intended response comment only.
- Canonical case gq-004-exception-pair from synthetic gold corpus v1.0.0, pinned by digest sha256:915304e812906f64003d9aacb0dd4b7701f7fbcf4f24fdc3cda21d1108b13068. The response contains only node IDs, synthetic paths, content hashes, line spans and bounded excerpts from that corpus.
- Per-Issue Actions concurrency with cancel-in-progress disabled. Fixture tests and issue-worker jobs have separate event gates and permissions.

## Workflow

Only an owner-authored [SFRA] Issue opened in yeatu/obsidianGP enters the worker job. issues.edited, issue_comment, pull requests, workflow_dispatch and other repositories do not execute the worker. The worker job uses only contents: read and issues: write.

The body must contain the exact sfra.issue.v1 request envelope accepted by V2.2. The handler binds the immutable event body digest, then the worker rereads the Issue through the GitHub API and compares its current body with the first-seen digest before invoking either application port. A response is written as a comment on that same synthetic request Issue.

## Delivery and recovery

Delivery is at-least-once for service execution, not exactly-once. Per-Issue concurrency serializes active runs but is not a durable FIFO queue; GitHub may replace a pending run in a concurrency group. A crash after a read-only application call but before the terminal comment can cause the application call to repeat. A bot-authored terminal marker suppresses later duplicate deliveries as best-effort deduplication.

- STARTED with no terminal marker is retryable after a runner interruption.
- COMPLETED, REJECTED and FAILED are terminal for that Issue/body digest.
- A changed body under the same Issue is rejected and never rebound.
- A FAILED marker is terminal. Recovery requires preserving the original Issue and all markers, then opening a new owner-authored [SFRA] Issue with a new request ID and unchanged payload intent, linking it to the failed Issue. Do not edit or delete the original Issue/comments.
- Only bot-authored markers count. Human comments containing marker-shaped text are ignored.
- Comment history is bounded to fewer than 1000 entries (10 pages × 100). At 1000 or more comments the worker fails closed rather than silently dropping the first-seen marker. Recovery from the history cap is to preserve the original Issue and comments, open a new owner-authored `[SFRA]` Issue with a new request ID, and link it to the history-capped Issue. Do not delete/edit old markers or bypass the cap.

## Safety

- Synthetic corpus v1.0.0 and disposable fixture data only.
- Never check out or mount the real Vault, production SQLite or sidecar.
- read_source is serviced by an injected synthetic port only. Production read_source activation remains blocked pending independent A review and C acceptance of the verifier chain.
- No issues.edited, issue_comment, HTTP server, MCP, production persistence or source-bearing artifacts.
- Workflow stdout contains only a bounded outcome label. Synthetic excerpts and provenance are emitted only in the intended Issue response comment, never in logs, artifacts or exception text.

## Tests

    python -m pip install -e ".[test]"
    pytest

All adapter tests are synthetic. The fixture workflow installs the accepted B1, V2.1 integration, E2 search and V2.2 core layers without production data.
