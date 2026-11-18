# SFRA — оперативная панель проекта

> Точка входа для AI-участников. Источник истины — соответствующая GitHub Issue и её последние действующие события. Нормативный процесс — [Issue #20, Governance Protocol v2.4](https://github.com/yeatu/obsidianGP/issues/20). Панель не заменяет CLAIM, RELEASE, review, CI или решения координатора.

**Снимок:** 2026-11-18  
**Текущий main:** `8f1e427fe0e356eafb449c073c34923eb07dda71`  
**Кодовый baseline:** `f665ae7251387ee86b3f5adb48662b79406f392b`  
**Последнее изменение main:** normal merge W1 PR #92; добавлены 14 принятых W1-файлов. Старые exact-head reviews для main `f665ae...` не переносятся на новые targets.

## 1. Целевая архитектура

**Рабочий Web-путь:** ChatGPT Web / mobile → GitHub Issues → GitHub Actions → GitHub-hosted Runner → существующие SFRA services/core → ответ в исходном Issue → ChatGPT читает результат через GitHub integration.

- Личный компьютер владельца не является runtime-зависимостью и может быть выключен.
- GitHub-hosted Runner эфемерен; он не служит постоянным хранилищем Vault, индекса, manifest, sidecar или request state.
- Переиспользуются существующие E1 structural indexing/source API, E2 retrieval, E3/B1 Context Builder, V2.1 SearchVaultService/ReadSourceService и V2.2 non-production Issue Worker Core. Повторно реализовывать это ядро не требуется.
- Долговременный data plane: immutable snapshot bundles → exact-version CloudSnapshotRef/catalogue → read-only resolver/materializer → verified E3 binding.
- Владелец разрешил публиковать содержимое Vault и производные source metadata в предусмотренных ответах. Blanket redaction не вводить. Credentials, tokens, keys, secrets и integrity controls сохраняются. Logs/artifacts/errors подчиняются отдельным ограничениям минимизации.
- Публикация содержимого не разрешает автоматически production import/read/index/write, provider provisioning, production `read_source` или snapshot activation.
- Cloud provider, region, durable storage, canonical source, sync model, update cadence, workload/SLO, retention, RPO/RTO и budget остаются UNDECIDED до явного решения владельца.

**Сохранение истории:** все существующие реализации, тесты, схемы, документация, branches, PRs, commits и review trail сохраняются. Переключение архитектурного приоритета не является основанием для удаления/отката старых наработок. Повторное использование допускается через отдельные согласованные границы.

## 2. Активная очередь и блокировки

Таблица — навигация, не CLAIM. Фактический владелец определяется последним действующим событием в Issue.

| Issue | Статус / роль | Следующий результат | Приоритет / зависимость |
|---|---|---|---|
| [#228](https://github.com/yeatu/obsidianGP/issues/228) | E2 CLAIMED | Закрыть BLOB + NULL `content_hash` bypass в E3 bundle verifier; public verifier regression | **P1**; child от PR #209 HEAD `4839d218...`; exact fixture CI + fresh A |
| [#229](https://github.com/yeatu/obsidianGP/issues/229) | Свободная E INTEGRATION | Sync benchmark PR #84 к main `8f1e427...` non-force; два полных прогона и byte comparison | **P1**; 5 benchmark-owned paths |
| [#232](https://github.com/yeatu/obsidianGP/issues/232) | E INTEGRATION, gated | Refresh integrated bundle stack к W1-updated main и выдать fresh A handoff | **P1**; после #228, independent A, explicit C gate |
| [#208](https://github.com/yeatu/obsidianGP/issues/208) | C3 controlling decision | Согласованный branch-only order #228 → #209 → #184 → #162; свежие A/C gates | **P1**; единственный authority для bundle stack |
| [#196](https://github.com/yeatu/obsidianGP/issues/196) | BLOCKED / E INTEGRATION | Обновить writer PR #170 и #179 поверх окончательно принятого bundle parent | **P1**; не начинать до финального #162 acceptance |
| [#42](https://github.com/yeatu/obsidianGP/issues/42) | E1 benchmark implementation / review pending | Сохранить воспроизводимую baseline и два видимых E2 false-positive gate | **P1**; PR #84; не ослаблять gates |
| [#120](https://github.com/yeatu/obsidianGP/issues/120) | E — dependency-gated | Read-only exact-version resolver/materializer для эфемерного runner | После принятия #119/#162 bundle chain, #118 уже merged |
| [#124](https://github.com/yeatu/obsidianGP/issues/124) | E — dependency-gated | Synthetic lifecycle conformance: prepare → write → stage → verify → activate → exact resolve | После #117–#120 и #125; trust-order тесты обязательны |
| [#134](https://github.com/yeatu/obsidianGP/issues/134) | E — gated | B1 SnapshotIdentity protocol v2 | После #120 и принятого E1 cloud verifier |
| [#136](https://github.com/yeatu/obsidianGP/issues/136) | E — gated | E3 factory-verified cloud materialized binding | После #120/#134 и E1 verifier acceptance |
| [#137](https://github.com/yeatu/obsidianGP/issues/137) | E — gated | Additive V2.2 `sfra.issue.v2` protocol | После #136; v1/TransportStatusV2 сохранить |
| [#138](https://github.com/yeatu/obsidianGP/issues/138) | E — gated | Synthetic V2.2 → V2.1 → E3/E1/E2 → B1 query conformance | После #134/#136/#137 |
| [#224](https://github.com/yeatu/obsidianGP/issues/224) | A2 RELEASED / no verdict | Старый panel review #223 target superseded | Fresh review будет привязан к новому panel HEAD |
| [#233](https://github.com/yeatu/obsidianGP/issues/233) | A — свежий REVIEW_REQUEST / OPEN | Независимая проверка обновлённой панели PR #223 | Exact HEAD/base/merge-ref зафиксированы в #233; #224 закрыта как stale target без verdict |

### Bundle stack — текущая точка остановки

- PR [#209](https://github.com/yeatu/obsidianGP/pull/209) current HEAD `4839d21815d30455355e2c2358262a93474489cb`, base `f665ae...`, five bundle-owned paths. A2 review #221 вернул **CHANGES_REQUESTED**.
- Correction #228 (E2 CLAIMED) закрывает P1 defect: SQLite BLOB `raw_text` + NULL `content_hash` не должен проходить verifier.
- PR [#184](https://github.com/yeatu/obsidianGP/pull/184) HEAD `8169827129e68f464496eb359ff31e89e64f58c2` содержит accepted #117 object-key parity correction.
- PR [#162](https://github.com/yeatu/obsidianGP/pull/162) HEAD `c5f84cd64877167b9feef3140fe20adf39c616cd` — bundle parent branch.
- ZIP pre-decompression correction #204 уже включён в интегрированный #209 candidate.
- Последовательность и обязательные стоп-гейты определены в #208. Никаких branch updates #209→#184→#162 и никаких writer updates до exact A acceptance и нового C live-ref guard.

## 3. PRs и точные evidence targets

| PR | Текущее состояние | Достоверная трактовка |
|---|---|---|
| [#92 — W1 Web adapter](https://github.com/yeatu/obsidianGP/pull/92) | **Merged** в main `8f1e427...` | A2 #218 принял HEAD `42cecfef...` / base `f665ae...`; 14 W1 files; PR fixture run #44393224276: 65 passed, worker skipped. Историческая A-приёмка относится только к этому exact HEAD |
| [#209 — integrated bundle stack](https://github.com/yeatu/obsidianGP/pull/209) | Open / Draft / unmerged | HEAD `4839d218...`, base `f665ae...`; five bundle paths; exact historical CI: bundle 58, C1 183 (42 E1 skips), V2.1 19, V2.2 55, all jobs SUCCESS. A2 #221: CHANGES_REQUESTED; #228 блокирует |
| [#84 — gold benchmark](https://github.com/yeatu/obsidianGP/pull/84) | Open / Draft / unmerged | HEAD `64924c...`, base `f665ae...`; five benchmark paths; #229 владеет current-main sync |
| [#170 — immutable writer](https://github.com/yeatu/obsidianGP/pull/170) | Open / stacked / unmerged | HEAD `b0bcf7...`, base #162 HEAD `c5f84...`; four writer files. Не содержит #184/#204/#228 |
| [#179 — writer correction](https://github.com/yeatu/obsidianGP/pull/179) | Open / stacked / unmerged | HEAD `035a79...`, base #170 HEAD `b0bcf7...`; четыре writer-owned files; A1 #180 accepted только historical correction target; #196 blocked |
| [#223 — panel refresh](https://github.com/yeatu/obsidianGP/pull/223) | Open / unmerged | Current-main diff — only `PROJECT_TASKS.md`; exact A review request #233 targets the latest panel HEAD; #224 is stale/released |

### Benchmark quality evidence

PR #84 HEAD `64924c...` / base `f665ae...` был проверен двумя независимыми full attempts в run #44395073244:
- preflight 20/20 для каждой попытки;
- все 42 gold cases выполнены;
- 40 passed / 2 failed;
- 14 видимых diagnostics, 0 explicit SourceRead mismatches;
- actual `benchmark.json` и `benchmark.md` побайтно совпали между attempts (JSON SHA `1f277e699...`, Markdown SHA `b14d71a6...`).
- Два E2 quality failures `gq-010-number-plus-condition` и `gq-036-conflicting-versions` остаются failed gates по #115. Это не all-green benchmark и не 42/42.

После merge W1 main advanced to `8f1e427...`; review #226 закрыт как superseded без claim/verdict. #229 обязан sync branch non-force и повторить обе попытки на новом exact merge-ref, затем открыть свежий A-review.

## 4. Принято / завершено / historical evidence

- [#75](https://github.com/yeatu/obsidianGP/issues/75): GitHub Issues + Actions Web architecture, synthetic-only first phase; user publication preference and preservation of old work recorded.
- [#77](https://github.com/yeatu/obsidianGP/issues/77) / PR #92: W1 synthetic-only implementation accepted and completed; issue closed.
- [#227](https://github.com/yeatu/obsidianGP/issues/227): one-time synthetic `search_vault` probe completed and closed. Actions run #44397740749 SUCCESS; `synthetic-issue-worker` succeeded, fixture job skipped; same authenticated bot ID/body digest STARTED→COMPLETED; only `gq-004-exception-pair` evidence returned; source_reads=0. Authorization consumed; no second request.
- [#117](https://github.com/yeatu/obsidianGP/issues/117) / PR #127: CloudSnapshotRef v2 accepted and merged; `schema_info_version`, not `PRAGMA user_version`.
- [#118](https://github.com/yeatu/obsidianGP/issues/118) / PR #159: in-memory SnapshotCataloguePort accepted and merged at `bc36bf...`; caller must verify before `mark_verified()`.
- [#175](https://github.com/yeatu/obsidianGP/issues/175): A1 producer→writer→v2→catalogue analysis accepted and closed. Catalogue verification is caller-enforced, not proof-carrying.
- [#225](https://github.com/yeatu/obsidianGP/issues/225): closed C3 trust-boundary decision. #208 is current stack-order authority.
- [#142](https://github.com/yeatu/obsidianGP/issues/142): closed. E1 schema identity must be exact `schema_info.schema_version` (currently 2); cloud verifier must be additive and preserve E1 v1.
- [#132](https://github.com/yeatu/obsidianGP/issues/132): A3 E1 cloud verifier design accepted. No E1 cloud verifier implementation may start until #119 is accepted per #142. Premature placeholder #135 remains closed; nothing is lost.
- [#133](https://github.com/yeatu/obsidianGP/issues/133): metadata-only source/state inventory accepted. Candidate `ГП/` subtree had 66 Markdown files / 988,098 reported bytes; this does not prove completeness or canonical source authority.
- [#145](https://github.com/yeatu/obsidianGP/issues/145): canonical source, update model, workload, latency, retention/RPO/RTO and budget remain UNDECIDED.
- [#154](https://github.com/yeatu/obsidianGP/issues/154): metadata-only Git tree comparison; not evidence of local/offline completeness.

## 5. Trust and production boundaries

1. `PreparedCloudSnapshotBundle` must pass the public bundle verifier before any immutable write.
2. Writer verifies exact receipts/versions and read-back; this does not itself prove E1 state consistency.
3. Catalogue `stage()` stores exact v2 identity as STAGED. `mark_verified()` is trusted-caller only.
4. Only the orchestrator may call `mark_verified()` after bundle verification and applicable E1 verification for the same exact identity.
5. For `immutable_import`, skipping Git-shaped E1 v1 verification is not success. Until additive E1 cloud verifier is implemented and accepted, the snapshot stays STAGED and cannot become ACTIVE.
6. Verification failure/unavailable verifier must not advance VERIFIED/ACTIVE or mutate the prior ACTIVE pointer.
7. All current bundle/writer/resolver/lifecycle work remains synthetic/disposable with fake/in-memory stores. No provider, credentials, real Vault/SQLite/sidecar/`sfra-state`, production sync/import/read/write, real `read_source`, or production activation is authorized.

## 6. Parallelism and coordination rules

- #228 is E2-CLAIMED; do not duplicate or overlap its verifier files/tests.
- #229 is the sole canonical benchmark sync task; do not create a parallel PR #84 sync.
- #232 is gated behind #228 implementation, exact-head A acceptance and explicit C order; do not claim/execute early.
- #196 writer refresh is BLOCKED until final #162 bundle parent is accepted and exact refs are authorized under #208.
- #120/#124/#134/#136/#137/#138 are dependency-gated; no placeholder implementation before upstream acceptance.
- #224/#226/#221 are stale/closed review records. No verdict transfers to a new HEAD/base.
- Branch history is preserved. No force push, rebase/reset, delete, automatic cleanup or direct-to-main merge of bundle/writer PRs.
- Any unexpected shared-contract/file conflict is a stop-and-escalate event. Resolve blocking/ref/ownership conflicts before ordinary implementation scheduling.

## 7. Operational rule

Before each integration or acceptance, reread live main, branch/PR HEAD and base, ordered parents, compare diff, active CLAIM/RELEASE/BLOCKED events, exact merge-ref CI, dependency gates and previous supersession notes. A verdict is valid only for its exact refs. Main merge, branch-only propagation and production activation are separate permissions.