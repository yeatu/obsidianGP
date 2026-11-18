# Synthetic E2 → E3 → B1 benchmark

Task: GitHub Issue #42  
Role: E1  
Runner: 1.0.0  
Corpus: accepted gold corpus v1.0.0 from Issue #41 / PR #58

## Purpose

Run the accepted 42-case corpus through the existing SFRA components:

1. E1 builds a structural index over disposable synthetic Markdown files.
2. E2 runs the existing lexical search runtime.
3. E3 binds a real immutable SnapshotRef, verifies source reads and resolves declared dependencies.
4. B1 builds the Context Pack using the existing ContextBuilder.

No retrieval, ranking, normalization, or token-budget implementation is copied into this runner.

## Run locally

Install the four existing packages plus the Draft 2020-12-capable schema validator:

```bash
python -m pip install "jsonschema[format]==4.25.1"
python -m pip install -e "GPT/Нейросеть/Проекты/Исполнитель 1/Сессия 1/Реализация"
python -m pip install -e "GPT/Нейросеть/Проекты/Исполнитель 2/Сессия 1/Реализация/source"
python -m pip install -e "GPT/Нейросеть/Проекты/Исполнитель 3/Сессия 1/Реализация/Этап Б1"
python -m pip install -e "GPT/Нейросеть/Проекты/Исполнитель 3/Сессия 1/Реализация/Этап В1"
PYTHONHASHSEED=0 python "GPT/Нейросеть/Проекты/Исполнитель 1/Сессия 2/Benchmark/runner.py" --output-dir benchmark-output
```

The runner requires Git and creates only temporary repositories below the operating-system temporary directory. Both the Vault and sidecar Git checkouts are destroyed automatically after the run. Set PYTHONHASHSEED=0 for cross-process repeatability; the report records the effective seed. After each E1 indexing pass, the benchmark canonicalizes every Node ID in the disposable SQLite fixture to UUIDv5 derived from corpus version + source_path + parser local_key, then rewrites references in node versions, match events and metadata. Extra gold-span IDs and the not-found case ID are also deterministic. The shared E1 indexer remains unchanged.

## Preflight

Before executing a benchmark case, the runner:

- validates the schema itself and the corpus with JSON Schema Draft 2020-12;
- checks the accepted corpus digest and version;
- verifies unique case and Node IDs and resolves all gold references;
- reconstructs all 69 annotated source spans from their exact 1-based line coordinates;
- recomputes SHA-256 for all 32 synthetic documents and 69 node spans;
- binds each available gold node to exactly one E1-generated fixture identity.

The accepted corpus file is read-only input. Gold labels are never adjusted to fit observed retrieval results.

## Metrics and gates

Per-case and aggregate metrics include retrieval Recall, Context Precision, Token Efficiency, Source Fidelity, facet coverage, fallback rate and tool cost. The report also records actual Context Pack and source-read statuses, deterministic repeatability, forbidden-node hits, dependency-group atomicity and completeness honesty.

Token Efficiency is calculated as:

`1 - Included raw_text token count / relevant full-document token count`

The relevant baseline is the set of unique source documents containing either `required_node_ids` or `allowed_additional_node_ids`. If several relevant nodes belong to one document, that full document is counted once. This keeps explicitly allowed additional context inside the denominator rather than treating it as unrelated material.

Both sides use the same `TiktokenCounter("o200k_base")`. Included source text is counted without JSON/provenance metadata, so the comparison uses consistent units. A negative value is still possible when the selected Included source spans contain more tokens than the chosen baseline documents; it is a diagnostic, not a gate threshold.

Invariant failures fail the workflow. Recall, precision and expected-versus-actual status differences are retained as visible outcomes; they are not silently relabelled as passing gates. Pack completeness honesty is evaluated only from E2 SearchBatch completeness, B1 Pack status and Pack-level deferrals. A `complete` Pack is invalid if Deferred contains `unresolved_required_dependency` or a B1 budget-deferral reason. Optional standalone SourceRead outcomes are checked independently and do not retroactively change ContextPack.status. Non-ok explicit reads must contain zero fragments. The runner does not invent a new quality threshold that Issue #42 did not specify.

Scenario controls are applied only to named synthetic cases. These include incomplete search, a missing dependency, Known/version state, conflicting versions and small budgets. The gq-036 version conflict is injected into the controlled synthetic E2 result and then evaluated by the actual B1 Context Builder path. The runner also keeps any forbidden-node results from E2 visible as failures. It does not filter real search results or alter ranking to make the gold cases pass.

## Safety boundary

- No real Vault checkout, indexing, source read, production SQLite, sidecar, manifest or `sfra-state` is accessed.
- No GitHub network operation is used by the fixture runtime.
- The real-Vault integration workflow remains outside this runner and is not invoked.
- JSON and Markdown reports contain case IDs, categories, metrics and aggregate state only. They omit query text, source text, source paths and per-node content hashes.
- Only the synthetic corpus digest and synthetic test counts are recorded.

## Known interpretation limits

E2 remains the existing lexical engine; a low Recall value is a measured result, not grounds to rewrite expected Node IDs. E2 does not provide a native facet retrieval channel, so facet coverage is evaluated against the returned and delivered gold IDs rather than pretending that facet-aware retrieval is available.

Explicit E1 source-read outcomes are recorded separately from the B1 Context Pack status, including actual status, fragment count and expected-versus-actual read-status match. A standalone `budget_exceeded`, `ambiguous` or `not_found` read can coexist with a `complete` Pack when the Pack itself was built from complete inputs. The three immutable corpus expected Pack-status mismatches in gq-025, gq-028 and gq-029 remain visible and are classified as legacy corpus/contract interpretation diagnostics, not Pack-completeness failures. Pack-level incomplete search, unresolved/deferred required dependencies and B1 budget/integrity outcomes remain subject to their existing gates.

Fallback Rate is `dependency_source_reads / max(1, initial E2 engine_result_count)`. The numerator counts actual E1 `read_source_scope` calls made after a successful dependency address resolution. A failed `resolve_current_node` contributes no fallback read. E2 exact-hit verification reads and explicit `SourceReadRequest` reads are counted and reported separately, and neither is included in the fallback numerator. Per-case reports include the raw numerator, denominator and dependency-resolution count; aggregate reports include each read category separately.

Each report records four distinct references: PR head SHA, PR base SHA, actual checkout SHA and the workflow checkout SHA. The latter may be GitHub's pull-request merge ref; it must not be described as the bare PR head.

## CI

The dedicated workflow `.github/workflows/sfra-gold-benchmark.yml` runs on pull requests and uses fixture-only data. It has read-only repository permissions and never checks out a user Vault or the production sidecar.


## Checkout and PR identity

The report records the PR head, the effective PR base verified from the checked-out merge-commit parents, the raw webhook event base, the actual checkout SHA and workflow checkout SHA separately. This avoids reporting a stale webhook base as the tree actually tested after a current-main synchronization. If the merge-ref graph cannot prove the base/head pairing, the report retains the event base and leaves the verified parent fields unavailable.\n\nThe merge parents are read from the raw commit object with `git cat-file -p`, not `git rev-list --parents`. This matters for the default depth-one GitHub Actions checkout: shallow boundaries can hide parents from revision traversal even though the checked-out merge commit object still contains both parent headers. The first parent is reported as the tested base only when the commit has exactly two parents and the second parent matches the exact PR head; otherwise the raw event base is retained and the verified parent fields remain unavailable.

## Final correction handoff — cross-process fixture identity

The final two independent CI attempts on PR #84 HEAD `62466d1abacc4b77730fb4a5f6e728117ae54d59` reproduced the same 40/42 gate count, but four cases had different precision/token-efficiency values. The root cause was benchmark-local random UUIDv4 assignment to synthetic E1 Node IDs. B1's documented deterministic rank tie-breaker includes Node ID, so different disposable fixture UUIDs could change tie outcomes. Correction #156 replaces those IDs with UUIDv5 derived from corpus version + purpose + stable identity. Indexed nodes bind source path + parser local key + exact content hash, so a new node that reuses a parser key after an ambiguous document update cannot collide with the preserved tombstone ID. Both E1 retirement markers (`__archived__{node_pk}` and `__deleted__{node_pk}`) retain the already-assigned canonical UUIDv5. The expected-not-found fixture ID is also stable; CI/local instructions pin `PYTHONHASHSEED=0`, and the effective strategy is recorded in report environment. No shared runtime or corpus is changed.

The correction is being implemented on PR #84 under [Issue #156](https://github.com/yeatu/obsidianGP/issues/156). Previous review request #151 is superseded; it was released by A3 without verdict because its target changed. Fresh A review will be requested only after two new independent full runs on the final exact HEAD produce byte-identical JSON and Markdown reports. The benchmark-local UUIDv5 normalizer also preserves the already-canonical ID of a deleted tombstone after E1 retires its parser `local_key` as either `__archived__{node_pk}` (changed document) or `__deleted__{node_pk}` (deleted document); it fails closed if an archived row does not already carry a canonical UUIDv5 ID. The focused preflight regression models the second index pass and verifies stale/deleted markers, node IDs and metadata/version/event references survive normalization.

The accepted quality findings remain unchanged: 42 corpus cases, 40 pass, 2 preserved E2 failed gates (gq-010, gq-036), three legacy ContextPack expectation diagnostics and 11 other visible status mismatches. Corpus v1.0.0 digest remains unchanged.
