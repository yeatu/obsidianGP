# SFRA — оперативная панель проекта

> Точка входа для AI-участников. Источник истины — соответствующая GitHub Issue и её последние действующие события. Нормативный процесс — [Issue #20, Governance Protocol v2.4](https://github.com/yeatu/obsidianGP/issues/20). Панель не заменяет CLAIM, RELEASE, review, CI или решение координатора.

**Снимок:** 2026-11-19  
**Текущий main HEAD:** `8d1d3c937abf1e6f651d077c409d1b3dfad1a9cb`  
**Текущий main tree:** `7b516530ad2f10fd10967fb84087fdf6a3946042`  
**Последнее интегрированное изменение:** PR #162 принёс принятый bundle/verifier stack; W1 уже в main с PR #92.

## 1. Целевая архитектура

**Рабочий Web-путь:** ChatGPT Web / mobile → GitHub Issues → GitHub Actions → GitHub-hosted Runner → существующие SFRA services/core → ответ в исходном Issue → ChatGPT читает результат через GitHub integration.

- Личный компьютер владельца не является runtime-зависимостью и может быть выключен.
- GitHub-hosted Runner эфемерен; он не служит постоянным хранилищем Vault, индекса, manifest, sidecar или request state.
- Переиспользуются существующие E1 structural indexing/source API, E2 retrieval, E3/B1 Context Builder, V2.1 SearchVaultService/ReadSourceService и V2.2 non-production Issue Worker Core. Повторно реализовывать это ядро не требуется.
- Долговременный data plane: immutable snapshot bundles → exact-version CloudSnapshotRef/catalogue → read-only resolver/materializer → verified E3 binding.
- Владелец разрешил публиковать содержимое Vault и производные source metadata в предусмотренных ответах. Blanket redaction не вводить. Credentials, tokens, keys, secrets и integrity controls сохраняются. Logs/artifacts/errors подчиняются отдельным ограничениям минимизации.
- Публикация содержимого не разрешает автоматически production import/read/index/write, provider provisioning, production `read_source` или snapshot activation.
- Cloud provider, region, durable storage, canonical source, sync model, update cadence, workload/SLO, retention, RPO/RTO и budget остаются UNDECIDED до явного решения владельца.

**Сохранение истории:** все существующие реализации, тесты, схемы, документация, branches, PRs, commits и review trail сохраняются. Переключение архитектурного приоритета не является основанием для удаления/отката старых наработок.

## 2. Активная очередь и блокировки

Таблица — навигация, не CLAIM. Фактический владелец определяется последним действующим событием в Issue.

| Issue | Статус / роль | Следующий результат | Приоритет / зависимость |
|---|---|---|---|
| [#196](https://github.com/yeatu/obsidianGP/issues/196) | **E1 CLAIMED / UNBLOCKED** | Исторически частичные writer PR #170/#179 синхронизировать с текущим принятым bundle base | **P1**; main `8d1d3c9...`; сохранить четыре writer-owned и четыре correction-owned файла; non-force, main-first, expected-old-HEAD; затем свежий A review |
| [#120](https://github.com/yeatu/obsidianGP/issues/120) | **E — READY TO CLAIM** | Read-only exact-version resolver и materializer для эфемерного GitHub-hosted runner | **P2**; #117/#118/#119 приняты и merged; synthetic/in-memory tests only |
| [#240](https://github.com/yeatu/obsidianGP/issues/240) | **E1 — READY TO CLAIM** | Additive E1 cloud-index attestation и read-only verifier | **P1**; принятые design #132 и decision #142; bundle #119 уже merged; E1 files/tests only; свежий A review обязателен |
| [#229](https://github.com/yeatu/obsidianGP/issues/229) | **E — GATED / unclaimed** | Синхронизировать benchmark PR #84 с main, повторить два 42-case прогона и открыть A review | **P1**; ждать A acceptance, C merge и merge панели PR #223 по #234; сохранить main `PROJECT_TASKS.md` verbatim и оставить четыре benchmark technical paths |
| [#42](https://github.com/yeatu/obsidianGP/issues/42) | E1 benchmark / quality gate | Сохранить воспроизводимый baseline и две видимые E2 retrieval failure | **P1**; gq-010 и gq-036 остаются failed; не менять corpus/метрики/ranking для зелёного отчёта |
| [#125](https://github.com/yeatu/obsidianGP/issues/125) | E3 implementation / writer stack | Закончить writer после #196, получить независимый review и C acceptance | PR #170/#179 остаются open/unmerged; старые #171/#180 verdicts не переносятся на новые HEAD |
| [#124](https://github.com/yeatu/obsidianGP/issues/124) | E — dependency-gated | Synthetic lifecycle conformance: prepare → write → stage → verify → activate → exact resolve | После принятия #120, #125 и E1 verifier #240; trust-order assertions обязательны |
| [#134](https://github.com/yeatu/obsidianGP/issues/134) | E — gated | B1 SnapshotIdentity protocol v2 | После #120 и A/C acceptance #240; не является proof of verification |
| [#136](https://github.com/yeatu/obsidianGP/issues/136) | E — gated | E3 factory-verified cloud materialized binding | После #120/#134 и принятия #240 |
| [#137](https://github.com/yeatu/obsidianGP/issues/137) | E — gated | Additive V2.2 `sfra.issue.v2` protocol | После #136; v1/TransportStatusV2 сохранить |
| [#138](https://github.com/yeatu/obsidianGP/issues/138) | E — gated | Synthetic V2.2 → V2.1 → E3/E1/E2 → B1 query conformance | После #134/#136/#137 |

### Конфликтующие и завершённые handoff’ы

- [#119](https://github.com/yeatu/obsidianGP/issues/119) — CLOSED / C3 accepted. Полный synthetic bundle builder/verifier и corrections #173/#204/#228 merged в main через PR #162.
- [#241](https://github.com/yeatu/obsidianGP/issues/241) — CLOSED / duplicate of canonical E1 verifier task #240. It must not be claimed separately.
- [#208](https://github.com/yeatu/obsidianGP/issues/208) — CLOSED / C3 coordination decision completed. Порядок #235 → #209 → #184 → #162 выполнен; final parent merged.
- [#232](https://github.com/yeatu/obsidianGP/issues/232) — CLOSED / completed by final PR #162 merge; отдельная синхронизация больше не требуется.
- [#236](https://github.com/yeatu/obsidianGP/issues/236) — CLOSED / A1 REVIEW_ACCEPTED + RELEASED для exact bundle parent/child tree и merge-ref `c5b32e0...`.
- [#228](https://github.com/yeatu/obsidianGP/issues/228), [#204](https://github.com/yeatu/obsidianGP/issues/204), [#173](https://github.com/yeatu/obsidianGP/issues/173) — CLOSED; corrections preserved in main.
- [#139](https://github.com/yeatu/obsidianGP/issues/139) — CLOSED / COMPLETED by A2; canonical gq-004-only search/read evidence projection covered by accepted W1 review #218.
- [#77](https://github.com/yeatu/obsidianGP/issues/77) / PR #92 — W1 synthetic-only implementation accepted and merged; issue closed.
- [#227](https://github.com/yeatu/obsidianGP/issues/227) — one-time synthetic `search_vault` probe completed and closed. Run #44397740749 SUCCESS; authenticated STARTED→COMPLETED; two allowed synthetic evidence nodes; `source_reads=0`; authorization consumed.

## 3. Bundle stack — integrated and accepted

- Main commit [`8d1d3c9...`](https://github.com/yeatu/obsidianGP/commit/8d1d3c937abf1e6f651d077c409d1b3dfad1a9cb) merges PR #162. Its parents are current W1 main `8f1e427...` first and accepted bundle merge-ref `c5b32e0...` second.
- Main tree SHA `7b516530ad2f10fd10967fb84087fdf6a3946042` is **identical** to the A1-accepted bundle tree in #236.
- Bundle content includes #173 object-key parity, #204 ZIP_STORED pre-read/size guard and #228 SQLite raw_text/content_hash validation. No duplicate verifier task is required.
- Exact final PR #162 validation: dedicated E1-installed bundle suite #44414369510 — 62 passed, zero skips; C1 #44414369536 — B1 45 and E3/C1 183 passed, 46 E1-dependent skips; V2.1 #44414369478 — 19 passed; V2.2 #44414369530 — 55 passed; key-contract run #44414355461 — 62 passed. All successful.
- C3 final acceptance for #119 is recorded in comment #6993913112. PRs #162/#209 are merged; #184/#235 were integrated in the accepted stack. No bundle current-main sync or fresh bundle review remains.

## 4. Writer stack — P1 conflict resolution

- PR #170 historical partial HEAD: `b0bcf7ae587c3613b80ef811264bdd4437eedc93`, previously based on bundle HEAD `c5f84cd...`.
- PR #179 historical partial HEAD: `035a79d652fb4015c1b7a258a092143319ae0ae4`, previously based on #170 HEAD `b0bcf7...`.
- The complete accepted bundle tree is now in main `8d1d3c9...`. E1 has been explicitly unblocked in #196 comment #6994072174; existing E1 CLAIM/ownership is unchanged.
- Required order: non-force main-first sync of #170 → verify four writer-owned paths → non-force sync refreshed #170 into #179 → verify four correction paths → exact parent/child fixture and cross-layer CI → one fresh integrated A review.
- Historical A2 #171 / A1 #180 verdicts apply only to old exact heads. No PR #170/#179 main merge before fresh A acceptance and separate C decision.
- No provider, credentials, upload, catalogue activation, real data or workflow_dispatch is authorized.

## 5. Benchmark — P1 shared-file conflict remains

PR #84 current historical HEAD `64924c204f006bf9d41a42ca0724d8e026325014` was synced to main `f665ae7...`, but is now behind current main `8d1d3c9...` by the W1 and bundle history. Its direct current diff also contains one stale `PROJECT_TASKS.md` handoff hunk.

- #234 is the controlling single-writer decision: PR #223 is the sole owner of root `PROJECT_TASKS.md`. E1 benchmark sync #229 must not mutate its branch until this panel gets fresh A acceptance, separate C acceptance and merge.
- After the panel merge, #229 must integrate then-current main non-force, preserve main's panel file byte-for-byte and leave only four benchmark technical paths in PR #84. Stop on conflicts in any of the four technical paths.
- Existing reproducibility evidence is exact to old target PR #84 HEAD `64924c...` / base `f665ae...`: two attempts, 20/20 preflight, 42 cases, 40 pass / 2 fail, 14 diagnostics; JSON/Markdown reports byte-identical (JSON SHA `1f277e699...`, Markdown SHA `b14d71a6...`).
- `gq-010-number-plus-condition` and `gq-036-conflicting-versions` remain real failed E2 gates under #115. No 42/42 claim, gate weakening, corpus edits or ranking changes.

## 6. E1 cloud-index verifier — new prerequisite #240

- A3 analysis #132 was accepted by C3; decision #142 defines the additive E1 cloud-index attestation and exact schema boundary.
- [#240](https://github.com/yeatu/obsidianGP/issues/240) is the single implementation task: typed `git_commit` / `immutable_import` source revision, canonical #119 Markdown inventory, E1 indexer/parser identity, exact `schema_info.schema_version`, DB hash, read-only whole-index verification.
- Preserve E1 manifest v1, `verify_state_directory()`, `create_state_snapshot()`, existing workflows and v1 callers unchanged. Do not map `immutable_import` into a Git SHA or use SQLite `PRAGMA user_version`.
- The E1 verifier proves consistency of the supplied materialized tree and SQLite index; it does not prove source-origin authenticity or historical UUID assignment. It is a report, not an E3 capability.
- #240 must receive independent A review and C acceptance before #134/#136/#137/#138 consume it. For `immutable_import`, without accepted #240 the snapshot remains STAGED; no VERIFIED/ACTIVE transition.

## 7. Принято / завершено / owner decisions

- [#117](https://github.com/yeatu/obsidianGP/issues/117) / PR #127: CloudSnapshotRef v2 accepted and merged; SQLite schema identity is `schema_info_version`, not `PRAGMA user_version`.
- [#118](https://github.com/yeatu/obsidianGP/issues/118) / PR #159: in-memory SnapshotCataloguePort accepted and merged at `bc36bf...`; `mark_verified()` remains caller-enforced.
- [#132](https://github.com/yeatu/obsidianGP/issues/132) / [#142](https://github.com/yeatu/obsidianGP/issues/142): E1 cloud verifier design and contract boundary accepted; implementation is #240.
- [#175](https://github.com/yeatu/obsidianGP/issues/175): A1 producer→writer→v2→catalogue analysis accepted; upload/stage is not verification proof.
- [#225](https://github.com/yeatu/obsidianGP/issues/225): C3 trust-boundary decision completed; branch sequencing #208 also completed.
- [#133](https://github.com/yeatu/obsidianGP/issues/133) / [#154](https://github.com/yeatu/obsidianGP/issues/154): metadata-only remote subtree evidence accepted; not proof of canonical source or local/offline completeness.
- [#145](https://github.com/yeatu/obsidianGP/issues/145): canonical source, sync model, staleness, workload/SLO, retention, RPO/RTO and budget remain UNDECIDED.
- User content-publication preference is recorded in #75: Vault contents and derived source metadata may be returned in intended responses. Do not infer permission for provider provisioning or production operations from that publication preference.

## 8. Trust and production boundaries

1. Prepared bundle must pass the public bundle verifier before immutable write.
2. Writer verifies exact immutable receipts/read-back; it does not prove E1 state consistency.
3. Catalogue `stage()` records STAGED. `mark_verified()` is trusted-caller only.
4. The orchestrator may call `mark_verified()` only after bundle verification and applicable E1 verification for the same exact identity.
5. For `immutable_import`, skipping the Git-shaped E1 v1 verifier is not success. Until #240 is implemented, independently reviewed and C-accepted, keep the candidate STAGED and do not activate.
6. Any verification failure/unavailable verifier must not advance VERIFIED/ACTIVE or mutate the previous ACTIVE pointer.
7. All current bundle/writer/resolver/lifecycle work remains synthetic/disposable with fake/in-memory stores. No provider, credentials, real Vault/SQLite/sidecar/`sfra-state`, production sync/import/read/write, real `read_source` or activation is authorized.

## 9. Parallelism and coordination rules

- #196 and #120 may proceed in parallel: writer stack integration and read-only materializer have disjoint file boundaries.
- #240 may proceed in parallel with #196/#120, but it owns E1 module/tests only.
- #229 remains gated by panel PR #223 A/C/merge under #234; no parallel benchmark sync.
- #124 remains gated by #120, #125 and accepted #240.
- #134/#136/#137/#138 remain gated by the explicit dependency chain in their Issues.
- Superseded panel reviews #233/#238 and older targets have no verdict transfer. The next panel review is bound to the new post-main-sync HEAD created from this file.
- Branch history is preserved: no force-push, rebase/reset, delete or automatic cleanup. Any unexpected shared-file/contract conflict is a stop-and-escalate event.

## 10. Operational rule

Before each integration or acceptance, reread live main, branch/PR HEAD and base, ordered parents, compare diff, active CLAIM/RELEASE/BLOCKED events, exact merge-ref CI, dependency gates and supersession notes. A verdict is valid only for its exact refs. Main merge, branch-only propagation and production activation are separate permissions.
