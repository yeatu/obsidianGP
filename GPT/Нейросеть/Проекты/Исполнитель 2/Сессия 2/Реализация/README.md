# E2 / Session 2: lexical search quality benchmark

## Scope
This folder contains a deterministic regression benchmark for the existing SFRA lexical search implementation. It measures the current baseline; it does not change production retrieval behavior.
The corpus is synthetic and self-contained. It contains no real Vault excerpts, private note titles or real source paths. Every fixture uses a synthetic/ locator and a stable benchmark-only Node ID.
## Coverage
- Russian inflection through the configured morphology channel.
- Exact phrase versus a near-miss containing the same terms in a different order.
- A rare synthetic term.
- A one-character typo as a diagnostic only. Fuzzy matching is not part of the current contract.
- A mixed lexical + exact-number query, including lexical-only and number-only decoys.
- The documented low-priority OR fallback.
- Stable tie-break order and duplicate-result checks.
- Noise-only and empty-query behavior.
## Run
Run from repository root after installing the E2 package and development dependencies:
```bash
python -m pip install -e "GPT/Нейросеть/Проекты/Исполнитель 2/Сессия 1/Реализация/source[dev]"
python "GPT/Нейросеть/Проекты/Исполнитель 2/Сессия 2/Реализация/lexical_benchmark/runner.py" --repeats 5 --expected-engine pymorphy3 --output-json /tmp/e2-lexical-benchmark.json --output-md /tmp/e2-lexical-benchmark.md
python -m pytest "GPT/Нейросеть/Проекты/Исполнитель 2/Сессия 2/Реализация/lexical_benchmark/test_runner.py"
```
The runner fails closed if the installed morphology engine is not pymorphy3. It creates one in-memory SQLite FTS5 index and closes it after the benchmark. The only files written are optional JSON and Markdown reports specified by the caller.
## Metrics
For each query the runner records recall@1, recall@k, precision@k, reciprocal rank, result order, duplicate count and stability across repeated runs. Aggregate recall/MRR are macro averages over gated cases with non-empty expected relevance sets.
The typo case is kept outside the pass/fail gate so the report measures the current limitation without silently changing the product contract. Empty/noise cases are evaluated by their explicit expected behavior.
## CI
The dedicated e2-lexical-search-benchmark.yml workflow is benchmark-only. It uses contents: read, installs the existing E2 package, runs benchmark unit tests and the synthetic baseline, then uploads JSON/Markdown evidence. Production search workflows are not modified.

## Baseline (synthetic corpus)

The first successful baseline on Python 3.13.18, SQLite 3.46.1 and pymorphy3 2.0.6 returned 8/8 gated cases successfully. Macro recall@1 was 0.9167, recall@3 was 1.0000, precision@3 was 0.3889 and MRR was 1.0000. The result order was stable in 8/8 gated cases and no duplicate results were observed.

The phrase case also surfaced a known precision limitation: a near-miss document containing the same query words in a different order is returned after the exact phrase hit. The partial OR fallback also returns an additional lower-relevance candidate. These findings are recorded for future prioritization; this benchmark does not alter ranking.
