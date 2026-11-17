# Этап В1 — интеграция Context Builder: C1

**Состав:** E2 SearchAdapter, E1 public SourceReader adapter, Snapshot binding, dependency resolver integration, fixture pipeline.  
**Состояние:** реализация закрыла прежние E3-A/E3-B defects и синхронизирована с \`main\`; PR #10 остаётся draft до независимой аналитической приёмки.  
**Реальная проверка:** полный E2 → E3 → E1 → Context Pack успешно выполнен в изолированных Actions checkout. Fixture CI и реальный workflow учитываются отдельно.

## 1. SearchAdapter

\`E2SearchAdapter\` вызывает опубликованный \`sfra_search.runtime.search_structural_database()\`. E3 не копирует FTS/morphology/search/ranking.

- Producer Node ID и Content Hash сохраняются.
- E2 tier/BM25 и исходное направление сортировки переносятся без синтетического score.
- E2 excerpt используется только как retrieval signal, не как источник.
- Полный raw_text принимается только через E1 public scope API по точной паре node_id + content_hash и сверяется по UTF-8 SHA-256.
- E2 generation не подменяет document-local generation E1.
- Empty results, runtime error, truncated/limit-sized results, post-filter и source rejection имеют отдельную диагностику.

## 2. E1 SourceReader

E3 вызывает только публичные функции E1:

\`\`\`python
read_source_scope(
    db_path, vault_root, node_id, expected_hash,
    *, scope, snapshot_id,
) -> SourceScopeResult

resolve_current_node(
    db_path, node_id, *, snapshot_id,
) -> CurrentNodeAddress
\`\`\`

\`E1SourceReader\` принимает E1 dataclass results и их публичный \`to_dict()\`, а не внутренние SQLite таблицы. Нативный shape \`SourceScopeResult\` включает \`snapshot_id/scope/status/fragments/anchor/parent/previous/next/document/error\`; \`CurrentNodeAddress\` возвращает только current address, без raw_text.

На E3 boundary валидируются:
- snapshot echo и точное совпадение scope;
- target Node ID + Content Hash;
- parent relation Node ID против \`target.parent_node_id\`;
- одинаковый parent у previous/next siblings и правильный source order;
- уникальность Node ID между ролями и отсутствие partial fragments;
- source_path, document_hash/source_sha256, document-local index_generation;
- SHA-256 каждого exact UTF-8 fragment и всего Markdown document;
- типы и координаты source records.

Fixtures — отдельный fake E1 provider. Они не выполняют SQL и не разбирают Markdown.

## 3. Snapshot binding

E3 фиксирует SnapshotRef до первого E1 вызова:

- \`vault_commit_sha\` совпадает с actual Vault checkout HEAD и manifest \`source_commit\` (или согласованным \`vault_commit_sha\`);
- \`sidecar_commit_sha\` — actual HEAD чистого checkout ветки \`sfra-state\`;
- \`manifest_sha256\` — SHA-256 точных байтов manifest;
- E1 \`verify_state_directory()\` подтверждает manifest/SQLite, а database hash совпадает с manifest;
- Vault root расположен внутри pinned Vault checkout.

E1 получает только непрозрачный \`snapshot_id\` и возвращает его без изменений. Git refs, checkout и branch resolution остаются ответственностью E3.

## 4. DependencyResolver и token budget

Для dependency Node ID E3 выполняет:
1. \`resolve_current_node(node_id, snapshot_id)\`;
2. читает точный текущий hash через \`read_source_scope(scope="node")\`;
3. сверяет snapshot, current Node ID, hash и provenance.

Fuzzy/historical fallback отсутствуют. При stale/ambiguous/deleted/not_found/integrity errors dependency остаётся unresolved, required group не включается частично. Диагностики resolver очищаются в начале каждого pipeline run.

Token budget принадлежит E3. E1 возвращает полный текст; E3 считает токены через B1 \`TokenCounterProtocol\`. При превышении budget E3 откладывает контекст/atomic group или возвращает \`budget_exceeded\` с пустым fragments. Source text не обрезается и E1 не получает budget argument.

Если E1 не передал реальную policy metadata, E3 применяет \`preservation="normal"\`, \`required_with=()\`, \`parent_context_required=False\` как defaults B1 и обозначает их диагностикой. Это не source annotations.

## 5. Fixture CI и real integration — раздельные доказательства

C1 CI использует опубликованный пакет E2 и fake E1 provider:
- B1 regression: 45 tests;
- C1 fixture/contract: 56 tests;
- отдельные adversarial cases для wrong parent, sibling from another parent, reversed order, duplicate IDs;
- regression для диагностики на двух последовательных \`pipeline.run()\`;
- wrong hash, stale/ambiguous/deleted/not_found, snapshot mismatch, path/hash/generation, budget atomicity.

Real integration workflow использует отдельные checkout:
- E3 branch under review;
- E1 PR #11 public API branch;
- production \`sfra-state\` checkout без записей;
- Vault checkout на commit, указанном в manifest.

Workflow выполняет реальный E2 search, E1 current-node resolution, dependency resolution, четыре scope, ContextBuilder и проверку Context Pack. Runner фиксирует E1/E3 commit SHA, SnapshotRef, source identities и machine-readable отчёт. До/после сравниваются SQLite, manifest, tracked sidecar tree, Vault tree, Git HEADs и clean checkout state.

**Результат последнего подтверждённого real run:** см. PR-CI / workflow artifact в PR #10. Статус Context Pack и число Included/Deferred всегда приводятся фактически; smoke не маркирует pack complete искусственно.

## 6. Статус и границы

C1 implementation готова к независимой аналитической приёмке; PR #10 остаётся draft и не слит до проверки аналитиком. Реальный integration workflow уже проходит, но это не снимает аналитическую приёмку C1/E3-02.

GitHub Issue worker, recovery sweep и MCP adapter не входят в PR #10. Отдельное техническое предложение по Issue worker/recovery ведётся самостоятельным документом, без транспортной реализации в этом PR.
