# Этап В1 — интеграция Context Builder: C1 и E3-02

**Область:** E2 SearchAdapter → E3 Context Builder → E1 Source Scope API.  
**C1:** адаптеры, snapshot binding, dependency resolver и fixture tests.  
**E3-02:** реальная read-only интеграция и расширенная negative matrix.  
**Состояние:** реализация и CI проверки выполнены; PR #10 остаётся draft до независимой аналитической приёмки.

## 1. E2 SearchAdapter

\`E2SearchAdapter\` вызывает опубликованный \`sfra_search.runtime.search_structural_database()\`. E3 не копирует E2 поиск, FTS, morphology или ranking.

- Producer Node ID и Content Hash сохраняются.
- Tier/BM25 и исходное направление сортировки переносятся без синтетического score.
- E2 excerpt остаётся retrieval signal и не становится source text.
- Полный raw_text поступает только через E1 public reader API по точной паре node_id + content_hash.
- E2 index_generation не подменяет E1 document-local generation.
- Empty results, runtime errors, limit/truncation, post-filter и source rejection отражаются отдельно.

## 2. E1 SourceReader и DependencyResolver

Используются только публичные E1 функции:

\`\`\`python
read_source_scope(
    db_path, vault_root, node_id, expected_hash,
    *, scope, snapshot_id,
) -> SourceScopeResult

resolve_current_node(
    db_path, node_id, *, snapshot_id,
) -> CurrentNodeAddress
\`\`\`

E3 принимает нативные E1 result dataclasses через публичный \`to_dict()\`. Прямого SQL к внутренним таблицам E1 и собственного Markdown parsing в E3 нет.

SourceReader проверяет:
- snapshot echo и scope echo;
- exact target Node ID + Content Hash;
- parent relation Node ID против target.parent_node_id;
- одинаковый parent у previous/next siblings и source order;
- уникальность Node ID между ролями;
- source_path, document_hash/source_sha256 и document-local index_generation;
- SHA-256 exact UTF-8 текста и координаты;
- отсутствие partial fragments при любом error status.

DependencyResolver сначала вызывает \`resolve_current_node()\`, затем читает exact current Content Hash через node scope. Fuzzy/historical fallback отсутствуют. Resolver diagnostics очищаются на границе каждого pipeline run.

## 3. Snapshot binding и token budget

E3 создаёт SnapshotRef до первого E1 вызова:
- Vault HEAD совпадает с manifest source_commit;
- sidecar HEAD относится к чистой ветке sfra-state;
- SQLite SHA совпадает с manifest database_sha256;
- manifest SHA вычислен по точным байтам manifest.json;
- Vault root находится внутри pinned Vault checkout.

Один SnapshotRef передаётся в search, dependency resolution и каждый Source Scope вызов. E1 получает только opaque snapshot_id и возвращает его без изменений.

Token budget принадлежит E3 через B1 TokenCounterProtocol. E1 возвращает полный source text. E3 не обрезает raw_text: при превышении бюджета возвращается budget_exceeded без fragments либо контекст откладывается атомарно.

При отсутствии фактических policy metadata E3 применяет B1 defaults normal / () / False и помечает их как policy defaults, а не как source annotations.

## 4. C1 fixture CI

[Run 44030495828](https://github.com/yeatu/obsidianGP/actions/runs/44030495828): success.

- B1 regression: **45 passed**.
- C1 fixture/contract suite: **56 passed**.
- Включены adversarial checks для wrong parent, sibling under another parent, reversed source order и duplicate Node IDs.
- Проверяется отсутствие diagnostic leakage между последовательными pipeline runs.
- Также покрыты hash/snapshot/generation errors, budget atomicity и pipeline error path.

Эти тесты используют fake E1 provider и не считаются доказательством реальной интеграции.

## 5. Real E2 → E3 → E1 → Context Pack

[Run 44030495939](https://github.com/yeatu/obsidianGP/actions/runs/44030495939): **success**, все workflow steps и cleanup jobs завершились. Machine-readable artifact: [sfra-e3-real-integration-44030495939, ID 14305311024](https://github.com/yeatu/obsidianGP/actions/runs/44030495939).

Проверенные implementation refs:
- E3 code HEAD: \`6e7b4fde4ed1d9eb73cb26f200975199842506f2\`.
- E1 public API HEAD: \`a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef\`.

SnapshotRef:
- Vault commit: \`2a3c54fa7a9e910f4c9621c8fe00f41a061fc158\`.
- sidecar commit: \`fb0b45ae0e5043e342c790d43e2b341ca65d7f2b\`.
- manifest SHA-256: \`sha256:3d5eacf5fc2f7f927af8f591f317ea95d56d0c0f53de1bc61cb54d23677fd072\`.
- SQLite SHA-256: \`sha256:2a6d792d5e5c458ffa87df32a082229fc548c42dab2d91a5cc8fa1195bcf6674\`.

E2:
- Search status: ok; 3 hits, 3 source-verifiable candidates.
- Top candidate tier 5, BM25 -0.3146491266567555.
- Node ID: \`node_9ca9ad76-8f04-48d5-a2b6-d163f60bcc9e\`.
- Content Hash: \`sha256:4efd270b3959a6c57799e94397d5583875e42be5d870967b3f3c61bdba628ed7\`.

E1 current-node resolution: ok. DependencyResolver разрешил фактический parent из parent scope: \`node_9b0e90f9-ac0c-44c3-84ce-92f035e0a32c\`; content hash, source path, document hash и generation совпали.

| Scope | Status | Fragments / roles | UTF-8 bytes |
|---|---|---|---:|
| node | ok | target | 37 575 |
| parent | ok | target, parent_context | 37 575 + 37 606 |
| neighbors | ok | target, next_neighbor | 37 575 + 4 |
| document | ok | document | **110 809** |

Все четыре scope и pipeline использовали один snapshot_id. Полный Markdown document совпал по SHA-256 и size_bytes; truncation отсутствовала.

## 6. E3-02 real negative matrix

Следующие проверки выполнены тем же real runner через публичные E1/E3 boundaries.

### Production-pinned snapshot и временная копия source
- Wrong Content Hash: \`stale_source\`, fragments пуст.
- Unknown Node ID: \`not_found\`, address отсутствует.
- Повреждённая временная копия исходного Markdown: E1 вернул \`stale_source\`, fragments пуст. Production Vault не менялся.
- Изменённый snapshot echo от E1: E3 отверг \`snapshot_mismatch\`.
- Запрос с другим SnapshotRef: E3 отверг \`snapshot_mismatch\` до чтения source.
- Подменённый document hash: E3 отверг \`document_hash_mismatch\`.
- Подменённый document generation: E3 отверг \`snapshot_generation_mismatch\`.

### Disposable E1 lifecycle indexes

Ambiguous/deleted состояния не присутствуют в текущем production snapshot, поэтому они созданы в отдельных временных Vault/SQLite copies через публичный E1 \`index_vault()\`. E3 не выполняет SQL и не меняет production state.

- Ambiguous immediate sibling после one-to-many remap: публичный E1 scope API вернул \`ambiguous\`; fragments пуст.
- Удалённый документ после E1 re-index: публичный E1 scope API вернул \`deleted\`; fragments пуст.
- В отчёте оба результата явно помечены как disposable E1 lifecycle fixtures, а не как состояния production sidecar.

### Token budget и Context Pack

- Scope document при бюджете 1 token: E3 \`budget_exceeded\`, fragments пуст.
- Context Pack при request budget 6000: \`budget_limited\`, **1 Included / 2 Deferred**. Это фактический результат, не \`complete\`.

### Read-only assertions

В run 44030495939:
- SQLite SHA до/после совпал;
- manifest SHA до/после совпал;
- tracked sidecar tree SHA совпал;
- Vault tree SHA совпал;
- sidecar и Vault HEAD не изменились;
- оба checkout остались clean.

Production \`sfra-state\` и Vault использовались только для чтения. Ambiguous/deleted lifecycle tests использовали отдельные disposable paths.

## 7. Границы и следующий шаг

C1 implementation и E3-02 integration/negative matrix выполнены на проверенном runner commit \`6e7b4fd\`. После последующего sync/doc-only commit требуется повторить оба workflow на окончательном PR HEAD.

PR #10 остаётся draft и не слит до независимой аналитической приёмки. E3 не выставляет analyst/coordinator status и не отмечает их checklist.

GitHub Issue worker, recovery sweep и MCP adapter не входят в PR #10. Отдельное предложение V2 содержится в PR #12 и не включает transport implementation.
