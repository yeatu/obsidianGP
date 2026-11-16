# SFRA GitHub Issue bridge: smoke test

## Scope

This test verifies only the transport chain:

1. ChatGPT/GitHub integration can create an Issue.
2. GitHub Actions receives the `issues.opened` event.
3. The workflow can post a comment using the scoped `GITHUB_TOKEN`.
4. ChatGPT/GitHub integration can read the resulting comment.

No Vault documents are read, indexed, or copied by this smoke test.

## Probe

Create an Issue with:

- Title: `[SFRA-BRIDGE-TEST] Connectivity probe`
- Body: `SFRA_BRIDGE_PROBE=1`

Expected comment marker: `SFRA_BRIDGE_OK`.

## Safety

The repository is public. Issue titles, bodies, and comments are public. Use only the marker above; never put private notes, credentials, or Vault excerpts in this probe.

The workflow is restricted to Issues opened by the repository owner account `yeatu` with the exact title prefix. Other Issues are ignored by the job condition.

## Files

- Workflow: `.github/workflows/sfra-issue-bridge-smoke.yml`
