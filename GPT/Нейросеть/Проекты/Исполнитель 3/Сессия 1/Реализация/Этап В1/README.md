# Этап В1 — E3 C1 и E3-02 integration

**Область:** E2 SearchAdapter → E3 Context Builder → E1 public Source Scope API.  
**Accepted E3 code HEAD:** a10023930c4dbf75adcf9ce4bb200af2cd3fe3fe.  
**Main sync merge commits:** 722b77d5f4bb2d07ce9b75ff7ab10220690ae39b, 043834b9260d92fa9de386f8aa1641b17190d4cd.  
**Main at final sync:** e133a3716a28842055da6db3acfbe2c318e67904; branch ahead 39 / behind 0.  
**Статус:** C1 и E3-02 приняты аналитиком и координатором: `COORDINATOR_ACCEPTED_NOT_MERGED`. PR #10 остаётся open / Draft / not merged.

## 1. SearchAdapter

E2SearchAdapter вызывает опубликованный sfra_search.runtime.search_structural_database(). Поиск, FTS, morphology и ranking остаются в E2.

- Producer Node ID и Content Hash сохраняются.
- Tier/BM25 и исходное направление сортировки переносятся без synthetic score.
- E2 excerpt остаётся только retrieval signal.
- Полный raw_text поступает только через E1 public API по точной паре node_id + content_hash.
- E2 generation не подменяет E1 document-local generation.
- Empty results, runtime errors, limit/truncation, post-filter и source rejection отражаются отдельно.

## 2. SourceReader и DependencyResolver

E3 вызывает только публичные E1 функции:

    read_source_scope(db_path, vault_root, node_id, expected_hash, *, scope, snapshot_id)
    resolve_current_node(db_path, node_id, *, snapshot_id)

Native E1 dataclass results нормализуются через to_dict(). E3 не обращается к внутренним SQLite таблицам и не содержит собственного Markdown parser.

SourceReader проверяет snapshot/scope echo, exact target identity, parent ID, sibling parent/order, unique Node IDs, source/document hashes, document-local generation, UTF-8 SHA и source coordinates. Error responses обязаны содержать пустые fragments.

DependencyResolver выполняет resolve_current_node → exact current Content Hash → read_source_scope(node). Fuzzy/historical fallback нет. Diagnostics сбрасываются между pipeline runs.

## 3. Snapshot binding и token budget

E3 проверяет:
- actual Vault HEAD == manifest source_commit;
- sidecar checkout находится на чистой ветке sfra-state;
- SQLite SHA совпадает с manifest database_sha256;
- manifest SHA вычислен по точным байтам;
- Vault root расположен внутри pinned Vault checkout.

Один SnapshotRef проходит через search, dependency resolution и все scope reads. E1 получает opaque snapshot_id и echo-ит его.

Token budget полностью принадлежит E3 через B1 TokenCounterProtocol. E1 возвращает полный текст; E3 не обрезает raw_text. При превышении budget контекст откладывается атомарно либо возвращается budget_exceeded без fragments.

При отсутствии реальных policy metadata E3 использует B1 defaults normal / () / False и помечает их как policy defaults, не source annotations.

## 4. Fixture CI

[Run 44031251865](https://github.com/yeatu/obsidianGP/actions/runs/44031251865): success.
- B1 regression: **45 passed**.
- C1 fixture/contract suite: **56 passed**.

Покрыты relationship adversarial tests (wrong parent, foreign-parent sibling, reversed source order, duplicate Node IDs), diagnostics isolation, snapshot/hash/generation errors, budget atomicity и pipeline failure paths. Fixture CI не заменяет real E1 integration.

## 5. Real E2 → E3 → E1 → Context Pack

[Run 44031251877](https://github.com/yeatu/obsidianGP/actions/runs/44031251877): **success**, включая artifact upload и все cleanup steps. Artifact: [ID 14305746021](https://github.com/yeatu/obsidianGP/actions/runs/44031251877), digest sha256:998531d53110ff2ba22f2e36e1852a40a2343c7db3d10207d806e9b5950551c0.

Проверенные implementation refs из artifact:
- E3: 5105f9c92b19b3eb9372286e11603eaa9582af31.
- E1: a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef.

SnapshotRef:
- Vault commit: 2a3c54fa7a9e910f4c9621c8fe00f41a061fc158.
- sidecar commit: fb0b45ae0e5043e342c790d43e2b341ca65d7f2b.
- manifest SHA-256: sha256:3d5eacf5fc2f7f927af8f591f317ea95d56d0c0f53de1bc61cb54d23677fd072.
- SQLite SHA-256: sha256:2a6d792d5e5c458ffa87df32a082229fc548c42dab2d91a5cc8fa1195bcf6674.

E2 search:
- status ok; 3 hits, 3 candidates;
- top tier 5; BM25 -0.3146491266567555;
- target Node ID node_9ca9ad76-8f04-48d5-a2b6-d163f60bcc9e;
- target Content Hash sha256:4efd270b3959a6c57799e94397d5583875e42be5d870967b3f3c61bdba628ed7.

E1:
- current-node resolution ok;
- DependencyResolver разрешил фактический parent Node ID node_9b0e90f9-ac0c-44c3-84ce-92f035e0a32c;
- parent content hash, source_path, document_hash и generation сверены.

| Scope | Status | Roles | UTF-8 bytes |
|---|---|---|---:|
| node | ok | target | 37 575 |
| parent | ok | target, parent_context | 37 575 + 37 606 |
| neighbors | ok | target, next_neighbor | 37 575 + 4 |
| document | ok | document | **110 809** |

Все четыре scope и ContextIntegrationPipeline использовали один snapshot_id. Полный Markdown document сверён по SHA-256 и size_bytes; truncation отсутствует.

## 6. Real negative matrix

### Production-pinned snapshot / source boundary
- wrong Content Hash → stale_source, no fragments;
- unknown Node ID → not_found, no address;
- повреждённая временная копия source Markdown → stale_source, no fragments;
- tampered E1 snapshot echo → E3 snapshot_mismatch;
- mismatched request SnapshotRef → E3 snapshot_mismatch before E1 call;
- tampered document hash → document_hash_mismatch;
- tampered document generation → snapshot_generation_mismatch.

### Disposable E1 lifecycle indexes

В production snapshot нет ambiguous/deleted rows. Для этих статусов runner создаёт отдельные временные Vault/SQLite через публичный E1 index_vault() и вызывает публичный read_source_scope(). Никакого SQL в E3 нет.

- ambiguous immediate sibling after one-to-many remap → ambiguous, no fragments;
- deleted node after public E1 re-index with source file removed → deleted, no fragments.

Эти два статуса являются реальными ответами E1 API на disposable lifecycle indexes, а не заявлениями о состоянии production sidecar.

### Budget and read-only
- document scope, budget 1 token → E3 budget_exceeded, no fragments;
- Context Pack at request budget 6000 → budget_limited, 1 Included / 2 Deferred; не complete.

В production-pinned run до/после совпали SQLite SHA, manifest SHA, sidecar tree, Vault tree и оба HEAD. Оба checkout остались clean. Production Vault и sfra-state использовались read-only.

## 7. Границы

PR #10 не содержит GitHub Issue worker, recovery sweep или MCP adapter. Отдельное предложение V2 находится в PR #12. PR #10 остаётся draft до независимой аналитической приёмки; E3 не выставляет analyst/coordinator status.


---

## Финальная сверка после sync с main — 2026-11-17

- Code-under-review HEAD: `88926a254e61e299714dc0dae19378ee7c0f1332`.
- Branch synced: `main` = `83b86216fd70f3f4335bedbd216ce14e24ae2abd`; compare ahead 34 / behind 0.
- [C1 PR-CI run 44032512776](https://github.com/yeatu/obsidianGP/actions/runs/44032512776): success, **45 B1 + 56 C1 passed**.
- [Real E1/E2/E3 integration run 44032505574](https://github.com/yeatu/obsidianGP/actions/runs/44032505574): success, event push; artifact ID `14305902690`, SHA-256 `sha256:1a34a60425700534fe4ed7666433abad2d26c301ac816787d458c8a7c8d19afe`.
- E2: 3 hits / 3 candidates; tier 5; BM25 -0.3146491266567555.
- E1: current-node resolver `ok`; actual parent dependency resolved; all four scopes `node / parent / neighbors / document` returned `ok` on one SnapshotRef.
- Real negative matrix: stale hash, unknown node, corrupt source copy, ambiguous neighbor, deleted node, snapshot echo/request mismatch, document hash mismatch and generation mismatch all failed closed with empty fragments.
- Document scope returned full 110,809-byte UTF-8 Markdown. No truncation.
- E3 Context Pack: `budget_limited`, 1 included / 2 deferred. One-token scope: `budget_exceeded`, no fragments.
- Production SQLite, manifest, sidecar tree, Vault tree and HEADs unchanged; both checkouts clean.
- PR #10 remains open / Draft / not merged. No analyst or coordinator acceptance is claimed by E3.

The CI and real integration runs above target this code-under-review HEAD. Documentation-only registry sync did not alter E3 implementation files. PR body and handoff identify the exact tested commit and evidence.


---

## 8. Финальная проверка после sync с main — 2026-11-17

- E3 code under review remains the accepted implementation tree from `a10023930c4dbf75adcf9ce4bb200af2cd3fe3fe`.
- Sync merge commit: `722b77d5f4bb2d07ce9b75ff7ab10220690ae39b`, with previous E3 HEAD and main `33dfdd9d894a7bedd822168ba479c0989e889211` as parents.
- Branch compare after sync: ahead 37 / behind 0.
- [C1 CI 44035881585](https://github.com/yeatu/obsidianGP/actions/runs/44035881585): success, **45 B1 + 56 C1 passed**.
- [Real E1/E2/E3 integration 44035881339](https://github.com/yeatu/obsidianGP/actions/runs/44035881339): success, including report upload and checkout cleanup.
- Real integration artifact: ID `14306793519`; ZIP SHA-256 `sha256:ec7192b98c31ff9f5febb363678c49d0b52cd1538455207aaa08a7a57ba6c690`.
- Artifact records E3 `722b77d5f4bb2d07ce9b75ff7ab10220690ae39b` and E1 `a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef`.
- All four scopes and real parent dependency succeeded. Negative matrix again confirmed stale hash, not_found, corrupt source, ambiguous/deleted disposable lifecycle, snapshot echo/request mismatch, document hash mismatch and generation mismatch. All failure paths were fail-closed.
- Context Pack remains `budget_limited`, 1 included / 2 deferred. One-token source scope is `budget_exceeded`, with no partial fragments.
- Production SQLite, manifest, sidecar tree, Vault tree and HEADs remained unchanged; both checkouts clean.

The run above validates the synchronized merge commit. The following commit, if any, only updates this README/handoff documentation and does not alter E3 implementation code. PR #10 remains open / Draft / not merged.


---

## 9. Повторная проверка после импорта последнего registry commit — 2026-11-17

- Последний main registry commit: `e133a3716a28842055da6db3acfbe2c318e67904`.
- Второй sync merge commit: `043834b9260d92fa9de386f8aa1641b17190d4cd`; после merge E3 branch **ahead 39 / behind 0**.
- Импортированный diff содержит только `PROJECT_TASKS.md` и реестр сессии координатора; E3 runtime tree не менялся.
- [C1 PR CI 44037802824](https://github.com/yeatu/obsidianGP/actions/runs/44037802824): success, **45 B1 + 56 C1 passed**.
- [Real PR integration 44037802807](https://github.com/yeatu/obsidianGP/actions/runs/44037802807): success; artifact ID `14308715139`, SHA-256 `sha256:59c8711c832339b5db3545f04d267c0073c3ca9d915954a16c7eb1ae166e193f`.
- Report records E3 `043834b9260d92fa9de386f8aa1641b17190d4cd` and E1 `a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef`.
- All four scopes, real parent dependency, negative matrix, fail-closed paths, E3 budget and read-only guards passed.
- Context Pack: `budget_limited`, 1 included / 2 deferred. One-token scope: `budget_exceeded`, no partial fragments.
- Production SQLite, manifest, sidecar tree, Vault tree and HEADs unchanged; both checkouts clean.

This run revalidates the branch after the final registry sync. The following commit only refreshes these two documentation files; runtime code and integration configuration are unchanged.
