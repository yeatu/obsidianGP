# Этап В1 — интеграция Context Builder: контрольный рубеж C1

**Статус C1:** адаптеры, Snapshot binding и fixture-проверки реализованы; PR #10 остаётся draft до независимого coordinator review.  
**Подтверждено CI:** опубликованный E2 runtime на временной SQLite fixture, E3 pipeline и fake E1 provider, четыре scope, E3-only token accounting, dependency resolution и fail-closed поведение.  
**Не заявляется:** real E1 + production \`sfra-state\` + Vault end-to-end. Эта проверка относится к SFRA-E3-02 и выполняется после формального завершения SFRA-E1-01 в \`PROJECT_TASKS.md\`.

## 1. E2 SearchAdapter

\`E2SearchAdapter\` вызывает опубликованный \`sfra_search.runtime.search_structural_database()\`.

- Поиск, FTS5, морфология и ранжирование остаются в E2.
- Producer Node ID + Content Hash сохраняются без fuzzy/semantic replacement.
- Tier/BM25 и порядок E2 переносятся без синтетического score.
- E2 excerpt остаётся только \`signals.match_excerpt\`.
- Полный \`raw_text\` поступает только через E1 public reader port и сверяется по exact UTF-8 SHA-256.
- E2 \`index_generation\` не заменяет E1 document-local generation.
- Empty retrieval, runtime failure, possible truncation at limit, post-filter и source rejection различаются явно.

## 2. Публичная граница E1 Source Scope

Production boundary теперь соответствует опубликованным E1 функциям из PR #11:

\`\`\`python
read_source_scope(
    db_path,
    vault_root,
    node_id,
    expected_hash,
    *,
    scope,
    snapshot_id,
) -> SourceScopeResult

resolve_current_node(
    db_path,
    node_id,
    *,
    snapshot_id,
) -> CurrentNodeAddress
\`\`\`

У E1 нет аргумента \`budget_tokens\`. \`snapshot_id\` является opaque correlation token: E1 возвращает его без изменений, а Git binding и проверка manifest принадлежат E3.

Реальная форма ответа E1 — \`SourceScopeResult.to_dict()\`:
- \`snapshot_id\`, \`scope\`, \`status\`;
- \`anchor\`, \`parent\`, \`previous\`, \`next\`;
- \`fragments\` с \`NodeRecord.to_dict()\` для node/parent/neighbors;
- \`document\` с полным \`DocumentRecord.to_dict()\` для document scope;
- \`error\` при неуспехе.

\`CurrentNodeAddress.to_dict()\` содержит только current address/provenance (\`node_id\`, \`content_hash\`, \`source_path\`, \`document_hash\`, \`index_generation\`) и не содержит source text.

\`E1SourceReader\` адаптирует эти реальные result shapes к внутреннему E3 envelope и проверяет:
- snapshot echo и запрошенный scope;
- точный target Node ID + Content Hash;
- named parent/neighbor fields против \`fragments\`;
- parent ID против \`target.parent_node_id\`;
- общий parent и source order для immediate siblings;
- уникальность Node ID между ролями;
- \`source_path\`, \`document_hash\`, \`source_sha256\`, document-local \`index_generation\`;
- точные node/document SHA-256 и структурные координаты;
- отсутствие любых partial records при error status.

В E3 нет SQL-запросов к E1 и нет собственного Markdown parser. Fixture provider моделирует публичный API и используется только для изолированных тестов.

## 3. Snapshot binding

E3 создаёт \`SnapshotRef\` до обращения к E1. Binder проверяет:
- фактический Vault checkout HEAD равен manifest \`source_commit\` (или \`vault_commit_sha\`);
- фактический sidecar HEAD относится к checkout ветки \`sfra-state\`;
- оба checkout чистые;
- E1 \`verify_state_directory()\` успешно проверяет manifest и SQLite;
- manifest-файл прочитан как точные байты, а \`manifest_sha256\` рассчитан по ним;
- SQLite digest равен \`manifest.database_sha256\`;
- Vault root находится внутри pinned Vault checkout.

E1 не получает Git refs и не выполняет fetch/checkout/branch resolution. Один \`SnapshotRef\` проходит через SearchAdapter, DependencyResolver и каждый SourceReader вызов.

## 4. DependencyResolver и token budget

Для каждого dependency Node ID E3:
1. вызывает \`resolve_current_node(..., snapshot_id=...)\`;
2. получает текущий точный Content Hash;
3. читает \`scope="node"\` по этому Hash;
4. сверяет snapshot и exact source response.

Not found, stale, ambiguous, deleted и integrity errors не заменяются похожим или историческим узлом. Требуемые группы остаются атомарными.

Бюджет целиком принадлежит E3:
- E1 возвращает полный source scope без truncation;
- E3 считает токены через существующий \`TokenCounterProtocol\`;
- превышение даёт \`budget_exceeded\` с пустым списком fragments для scope read либо откладывает atomic group в Context Builder;
- \`raw_text\` не обрезается;
- E1 не считает токены.

Метаданные \`preservation\`, \`required_with\`, \`parent_context_required\` берутся только из фактических E1 metadata, если они присутствуют. Иначе E3 применяет policy defaults \`normal\`, \`()\`, \`False\` и отдельно диагностирует, что это defaults E3, а не аннотации первоисточника.

## 5. Проверки и границы доказательств

C1 CI устанавливает опубликованный E2 пакет и выполняет:
- 45 B1 regression tests;
- C1 tests на fake E1 public API и временной search SQLite;
- exact Snapshot binding fixtures;
- positive/negative checks для четырёх scope, snapshot, fragment identity, parent/sibling relationships, budgets, required-group atomicity и повторных \`pipeline.run()\`.

Тест реального E2 runtime использует временную structural SQLite fixture. Его E1 source reads остаются fake-provider reads. Этот тест не является реальной E1/Vault интеграцией.

Ручной workflow \`.github/workflows/sfra-e3-real-e1-integration.yml\` подготовлен для последующего запуска на:
- отдельном checkout E1 API;
- отдельной копии ветки \`sfra-state\`;
- Vault checkout на commit из manifest.

Он перед запуском сверяет и после запуска повторно проверяет digest SQLite, manifest и Vault checkout.

**Текущая блокировка SFRA-E3-02:** E1 код уже публикует unified API и отдельный current-node resolver в PR #11, CI на его текущем head успешен. Но \`PROJECT_TASKS.md\` всё ещё показывает SFRA-E1-01 как \`WAITING_FOR_IMPLEMENTATION\`, а E1 analyst completion/checklist не заполнены. Согласно координационному gate E3 не объявляет и не закрывает real integration до статуса \`ANALYST_COMPLETE_UNREVIEWED\` у E1.

PR #10 остаётся draft и не слит. Production Vault и production \`sfra-state\` не изменялись.
