# SFRA synthetic gold corpus

Version: 1.0.0
Gold cases: 42
Synthetic documents: 32
Annotated nodes: 69
Branch: analyst-1/issue-41-synthetic-gold-corpus

## Files
- corpus.v1.json — synthetic source documents, spans and gold annotations.
- gold-case.schema.json — JSON Schema Draft 2020-12.
- annotation-guide.md — field semantics and scoring.
- coverage-matrix.md — Issue #41 coverage.

## Integrity
Corpus UTF-8 SHA-256: sha256:915304e812906f64003d9aacb0dd4b7701f7fbcf4f24fdc3cda21d1108b13068
Hashing: exact UTF-8 SHA-256; non-empty node spans include final LF.
Structural checks: unique case/Node IDs, all references resolve, spans reconstruct exactly, all source/node hashes match.
Synthetic-only declaration embedded in corpus metadata.

## Scope
Analysis/test data only. No runtime, retrieval, ranking, budget, SQLite, sidecar, production Vault or CI changes. End-to-end benchmark runner remains Issue #42.
