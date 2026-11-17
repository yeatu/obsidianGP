# SFRA-E3-V2.2 — non-production Issue validation and safe worker core

**Issue:** [#15](https://github.com/yeatu/obsidianGP/issues/15)  
**Scope:** pure validation, status schema v2, safe aggregate projection and an injected worker core.  
**Runtime mode:** non-production only; tests and in-memory ports only.

## Package layout

The package is sfra_issue_core in src/. It has no runtime package dependencies declared and imports only the already accepted B1 models and V2.1 application service contracts when installed alongside those packages.

- IssueRequestParser validates Issue metadata, strict UTF-8 bytes, the exact request body hash, one JSON envelope and the operation-specific payload.
- TransportStatusV2 implements a strict status-v2 mapping with status_schema_version, request_body_sha256 and worker_commit_sha.
- SafeResultProjector extracts only allowlisted operation/status/scope/count fields and approved diagnostic codes from typed V2.1 results.
- IssueWorkerCore reads one injected Issue record, validates it completely, compares the immutable first-seen body hash, then invokes exactly one V2.1 application service with the supplied pinned SnapshotRef.
- InMemoryTransportStatusStore is a test/non-production implementation. It binds the first observed request body hash and never replaces that baseline.

## Request boundary

The approved repository is yeatu/obsidianGP, the title must begin exactly with [SFRA], and the author must match an exact login in a non-empty injected allowlist. The default allowlist contains only yeatu. Missing and empty allowlists reject every request.

The body limit is 32 KiB measured from the exact UTF-8 byte sequence. A body must be either one strict JSON value or exactly one fenced json block with whitespace only outside. Duplicate JSON keys, non-JSON constants, extra fields, unknown operations, invalid UUID v4 values and invalid operation payloads are rejected. Search and read-source payloads both reject additional properties, including nested objects.

request_body_sha256 is computed over the exact original body bytes, before parsing or whitespace normalization. The status store binds the first observed hash for an Issue. A later different hash produces a permanent REJECTED / request_body_changed outcome and does not call either application service.

## Safe result boundary

A transport status contains a transport outcome (REJECTED, COMPLETED or FAILED) separately from the V2.1 business status (for example budget_limited). The safe result schema contains only:

- operation and an allowlisted business status;
- an optional approved scope;
- integer aggregate counts;
- diagnostic codes from a fixed allowlist.

The projector never serializes source fragments, raw text, excerpts, quotes, titles, paths, node IDs, content hashes, diagnostic messages or arbitrary details. Unknown business status values become unknown; unknown diagnostic codes are dropped. Error messages and exception details from injected services are not copied into transport status.

## Worker usage

A caller must inject an IssueReaderPort, a TransportStatusStorePort, the merged V2.1 SearchVaultService and ReadSourceService, and one pinned SnapshotRef for each invocation. The core itself contains no GitHub SDK/API client, network calls, credentials, write permissions, event handlers, workflow triggers, persistence adapter or deployment code.

V2.2 does not include real Issue reads/writes, Issue/comment publication, active issue-event or schedule workflows, retries, leases, concurrency, recovery, source-text serialization, result chunks, MCP, HTTP/webhooks or deployment. Public Vault source-content publication remains DENY BY DEFAULT.

## Tests

From the repository root, install the accepted dependency layers and run the contract suites:

~~~bash
B1_DIR="GPT/Нейросеть/Проекты/Исполнитель 3/Сессия 1/Реализация/Этап Б1"
E3_DIR="GPT/Нейросеть/Проекты/Исполнитель 3/Сессия 1/Реализация/Этап В1"
E2_DIR="GPT/Нейросеть/Проекты/Исполнитель 2/Сессия 1/Реализация/source"
V2_1_DIR="GPT/Нейросеть/Проекты/Исполнитель 3/Сессия 1/Реализация/Этап В2.1"
V2_2_DIR="GPT/Нейросеть/Проекты/Исполнитель 3/Сессия 1/Реализация/Этап В2.2"

python -m pip install -e "$B1_DIR"
python -m pip install -e "$E3_DIR[test]"
python -m pip install -e "$E2_DIR"
python -m pip install -e "$V2_2_DIR[test]"
python -m pytest -q "$B1_DIR/tests"
python -m pytest -q "$E3_DIR/tests"
python -m pytest -q "$V2_1_DIR/tests"
python -m pytest -q "$V2_2_DIR/tests"
~~~

CI workflow: .github/workflows/sfra-e3-v2-2-issue-core-tests.yml. It runs only on pull requests touching the implementation/dependency/test paths and has read-only repository permissions.
