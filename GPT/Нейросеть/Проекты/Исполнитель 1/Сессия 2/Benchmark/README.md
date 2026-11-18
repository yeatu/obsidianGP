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
python "GPT/Нейросеть/Проекты/Исполнитель 1/Сессия 2/Benchmark/runner.py" --output-dir benchmark-output
```

The runner requires Git and creates only temporary repositories below the operating-system temporary directory. Both the Vault and sidecar Git checkouts are destroyed automatically after the run.

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

Invariant failures fail the workflow. Recall, precision and expected-versus-actual status differences are retained as visible outcomes; they are not silently relabelled as passing gates. In particular, a source-read `budget_exceeded` result with no fragments must make `completeness_honesty=false` whenever the Context Pack status is `complete`. The runner does not invent a new quality threshold that Issue #42 did not specify.

Scenario controls are applied only to named synthetic cases. These include incomplete search, a missing dependency, Known/version state, conflicting versions and small budgets. The gq-036 version conflict is injected into the controlled synthetic E2 result and then evaluated by the actual B1 Context Builder path. The runner also keeps any forbidden-node results from E2 visible as failures. It does not filter real search results or alter ranking to make the gold cases pass.

## Safety boundary

- No real Vault checkout, indexing, source read, production SQLite, sidecar, manifest or `sfra-state` is accessed.
- No GitHub network operation is used by the fixture runtime.
- The real-Vault integration workflow remains outside this runner and is not invoked.
- JSON and Markdown reports contain case IDs, categories, metrics and aggregate state only. They omit query text, source text, source paths and per-node content hashes.
- Only the synthetic corpus digest and synthetic test counts are recorded.

## Known interpretation limits

E2 remains the existing lexical engine; a low Recall value is a measured result, not grounds to rewrite expected Node IDs. E2 does not provide a native facet retrieval channel, so facet coverage is evaluated against the returned and delivered gold IDs rather than pretending that facet-aware retrieval is available.

Explicit E1 source-read outcomes are recorded separately from the B1 Context Pack status. Stale, deleted, ambiguous and not-found read outcomes are retained as independent evidence, and any expected-versus-actual Context Pack status mismatch remains visible in the report. A source-read `budget_exceeded` outcome is additionally a failed completeness invariant if the Pack is reported as complete.

Fallback Rate is `dependency_source_reads / max(1, initial E2 engine_result_count)`. The numerator counts actual E1 `read_source_scope` calls made after a successful dependency address resolution. A failed `resolve_current_node` contributes no fallback read. E2 exact-hit verification reads and explicit `SourceReadRequest` reads are counted and reported separately, and neither is included in the fallback numerator. Per-case reports include the raw numerator, denominator and dependency-resolution count; aggregate reports include each read category separately.

Each report records four distinct references: PR head SHA, PR base SHA, actual checkout SHA and the workflow checkout SHA. The latter may be GitHub's pull-request merge ref; it must not be described as the bare PR head.

## CI

The dedicated workflow `.github/workflows/sfra-gold-benchmark.yml` runs on pull requests and uses fixture-only data. It has read-only repository permissions and never checks out a user Vault or the production sidecar.
