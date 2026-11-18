# Gold corpus annotation guide

Corpus: sfra.synthetic.gold.e2-e3-context-pack v1.0.0. Purpose: independent evaluation of E2 retrieval → E3 source verification → B1 Context Pack.

## Evidence boundaries
- Only documents[].content and its exact node span are source evidence. Entity/facet/preservation/dependency labels are metadata, not facts.
- Node raw_text must equal the exact source line slice, including final LF for non-empty spans. Empty root is only 1..0 with empty text.
- Hashes are SHA-256 of exact UTF-8 bytes; do not normalize Unicode, spaces, case or newlines.
- All paths begin synthetic/. Do not use production Vault, SQLite, sidecar or private source material.

## Field semantics
- retrieval.expected_node_ids: required relevant candidates for E2 under the declared retrieval policy.
- retrieval.acceptable_node_ids: permissible additional candidates; never a substitute for required nodes.
- retrieval.forbidden_node_ids: distractors and false positives.
- context_pack.required_node_ids: required delivery targets; evaluate Included, Known or Deferred by scenario controls.
- allowed_additional_node_ids: admissible extra context only.
- forbidden_node_ids: nodes that cannot be delivered as evidence for the query.
- expected_status: B1 Context Pack status. budget_exceeded belongs to E1 read_source and is stored in expected_read_source.
- critical_constraints: conditions that cannot be silently omitted.
- required_dependency_groups: atomic sets; include all or defer all.
- facet_evaluation: score every requested facet independently.
- source_assertions: exact source path/span/hash and independent-source constraints.
- scenario_controls: fixture controls for missing dependencies, incomplete batch, Known versions and conflicts.
- expected_read_source: expected E1 scope-read outcome, including stale/deleted/ambiguous/not_found/budget_exceeded.

## Metrics
1. Retrieval recall: share of expected_node_ids returned under the run's top-k / complete retrieval fixture.
2. False positives: returned IDs from forbidden_node_ids.
3. Context precision: relevant Included divided by all Included; report Known and Deferred separately.
4. Facet coverage: every required Node ID per facet must be represented; do not hide missed facets in one average.
5. Source fidelity: exact raw_text/span/hash equality plus provenance tuple (Node ID, path, heading path, line range, hash).
6. Dependency fidelity: atomic groups, recursive closure and parent context.
7. Completeness honesty: incomplete retrieval, unresolved dependency, stale/ambiguous/deleted and budget defer cannot be reported as complete.
8. Budget behaviour: include/defer whole nodes and groups; source text truncation is invalid.
9. Known/version behaviour: same Node ID + Content Hash is Known; changed hash is a Version Change; conflicting hashes are not arbitrated.

## Ranking independence
Do not alter gold labels after observing ranking results. An E2 miss is a retrieval miss, not a reason to rewrite the expected set. Additional nodes are allowed only when declared acceptable or required by a contract dependency.

## Reproducibility
Validate schema, unique case and Node IDs, all ID references, line ranges, exact spans and all SHA-256 values before evaluation. Record corpus/schema/runner versions and baseline commit. Keep E2, E3 and Context Pack metrics distinct.

## Synthetic-only policy
Every document, entity, number, identifier, path and sentence is fabricated. Changing labels or required source nodes requires a new corpus version.
