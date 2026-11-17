# Этап В1 — интеграция Context Builder: контрольный рубеж C1

**Статус:** C1 адаптеры и fixture pipeline реализованы; PR #10 остаётся draft и ожидает независимой проверки аналитиком.
**Доказано:** реальный E2 runtime на временной SQLite fixture, сборка Context Pack на полном fixture-сценарии, четыре scope через тестовый E1 API, snapshot pinning и сохранность B1 regression.
**Не доказано:** production E1 Source Scope API и полный проход по реальному Vault.

## 1. E2 SearchAdapter

Адаптер вызывает существующий публичный runtime E2: sfra_search.runtime.search_structural_database(source_database, query, entities, limit, entity_config).

- Не копирует поиск, FTS5 или морфологию.
- Сохраняет Node ID, Content Hash, path, heading, line coordinates, match type, match reasons, tier и BM25.
- Сохраняет порядок E2: tier ascending, BM25 ascending; отдельный score не синтезирует.
- Передаёт excerpt только как signals.match_excerpt.
- Берёт raw_text только через E1 reader по точной паре node_id + content_hash.
- Отвергает несовпадающие locator поля и SHA-256 полного текста.
- Не использует E2 index_generation как E1 document-local generation.
- Различает not_found_in_retrieval, ошибку runtime и неполную выдачу.
- Ровно limit hits считает потенциально усечёнными, так как E2 не возвращает total_count/cursor.
- Не изобретает facet signals; зоны фильтруются только по точному первому сегменту path и консервативно помечают выдачу неполной.

## 2. SourceReader

E1SourceReader — транспортно-независимая проверяющая обёртка над публичным портом E1ScopeAPI. Она принимает scopes: node, parent, neighbors, document.

Проверяются snapshot_id, requested node address, document path, document-local generation, whole-document hash, exact fragment SHA-256 и отсутствие частичных fragments при ошибочном статусе. Ошибки stale_source, ambiguous, deleted, not_found, budget_exceeded, source_unavailable и integrity_error остаются явными.

Fixtures реализуют четыре режима на заранее описанных записях и sibling-связях. Они не выполняют SQL к E1, не парсят Markdown и не вычисляют соседей из текста.

**Ограничение:** открытый PR #11 E1 публикует exact node lookup (get_node_by_id), но не полный четырёхрежимный Source Scope API. Поэтому C1 имеет рабочий E3 SourceReader boundary и fixture implementation, но не E1-backed production scope reader. Реальные parent/neighbors/document остаются заблокированы до согласования и реализации публичного API E1.

## 3. Snapshot binding и pipeline

SnapshotRef собирается из:
- vault_commit_sha — фактический pinned Vault HEAD, равный manifest.source_commit;
- sidecar_commit_sha — фактический pinned checkout HEAD ветки sfra-state;
- manifest_sha256 — SHA-256 точных байтов state/manifest.json.

Snapshot binder требует официальный E1 verify_state_directory, сверяет manifest и SQLite digest. ContextIntegrationPipeline передаёт один и тот же SnapshotRef в E2 adapter, B1 dependency resolver и каждый последующий SourceReader scope-read.

Fixture-сценарий запускает:
real E2 runtime fixture → SearchAdapter → SearchBatch → ContextBuilder (B1) → ContextPack → SourceReader fixture (node / parent / neighbors / document).

Дополнительно проверяются dependency resolution, mismatch document-local generation, атомарный token budget, stale/ambiguous, полный hash и отказ при другом SnapshotRef.

## 4. Проверки

GitHub Actions workflow: .github/workflows/sfra-context-integration-c1-tests.yml.

**Последний PR-CI:** [run 44013125521](https://github.com/yeatu/obsidianGP/actions/runs/44013125521), conclusion success.
- B1 regression suite: **45 passed in 0.74s**.
- C1 fixture suite: **43 passed in 0.29s**.
- Python 3.11.
- E2 package устанавливается из опубликованного source проекта Исполнителя 2; реальный search_structural_database вызывается на временной структурной SQLite fixture.
- Тест проверяет, что digest временной SQLite не изменился. Это не production Vault и не production sfra-state.

## 5. Gates

| Gate | Условие |
|---|---|
| C1 | Аналитик принимает E2 mapping, E1 scope boundary, snapshot binder и fixture pipeline |
| C2 | E1 реализует node / parent / neighbors / document API и current-node resolver для B1 dependency edges |
| C3 | E3 подключает production SourceReader / DependencyResolver только через публичный E1 API |
| C4 | Real-Vault search → Context Pack → все scopes на одном pinned snapshot; Vault и SQLite только read-only |

GitHub Issue worker, recovery sweep и MCP adapter в этот PR не входят. Реальный Vault не изменялся.
