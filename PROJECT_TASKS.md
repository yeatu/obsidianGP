# SFRA — оперативная панель проекта

> Точка входа для AI-участников. Источник истины — соответствующая GitHub Issue и её последние действующие события. Нормативный процесс — [Issue #20, Governance Protocol v2.4](https://github.com/yeatu/obsidianGP/issues/20). Панель не заменяет CLAIM, RELEASE, review, CI или решение координатора.

**Снимок:** 2026-11-19  
**Текущий main HEAD:** `372c1b854a39c436969d3835d0656c46a4758677`  
**Текущий main tree:** `b1612bd11d71f2a4a6563b39a4d119c2371e1f40`  
**Последнее интегрированное изменение:** PR #250 добавил принятый synthetic-only exact-version resolver/materializer; PR #162 bundle/verifier и W1 PR #92 уже в main.

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
| [#196](https://github.com/yeatu/obsidianGP/issues/196) | **E1 RELEASED / P1 integrated A review #289 pending** | Независимо принять writer stack #170 → #179 на текущих refs; после A — отдельное C3 integration decision | E1 IMPLEMENTATION COMPLETE / RELEASE #6997701052. Parent #170 HEAD `8d8559e...`, main 12/0, merge-ref `4470f113...`; child #179 HEAD `a80d3e7...`, main 25/0, parent→child 13/0, merge-ref `d89e0b3...`; four unique writer paths, no resolver overlap (#268). Parent fixture/C1/V2.1/V2.2 #44442178689/#44442182960/#44442182948/#44442182935 SUCCESS (18 fixture passes); child #44442511134/#44442517044/#44442517095/#44442517185 SUCCESS (27 fixture passes). Inherited bundle #44414369510 accepted (62/0). Fresh integrated A review #289 is open/unclaimed. Both PRs OPEN/unmerged; no main merge before A + separate C3 decision |
| [#240](https://github.com/yeatu/obsidianGP/issues/240) | **E3 RELEASED / P1 verifier acceptance BLOCKED by #287** | Закрыть residual F-5 zero-width span gap, fresh A review, затем отдельная C3 acceptance | Parent RELEASE #6996973158; #277 RELEASE #6997423293. A2 ранее запросил изменения на PR #271 (#6997144102). PR #282 HEAD `074bca4d...`, base `372c1b8...`, merge-ref `7206a590...`, 50/0, five E1 paths; exact-head E1/B-C/B1 #44441003002/#44441003043/#44441002985 SUCCESS. A3 review #284 CLOSED / REVIEW_CHANGES_REQUESTED #6997673555: F-6 accepted, F-5 still accepts zero-width entries. Sole follow-up #287 open/unclaimed. Keep #271/#282 immutable. No #136/#124 or VERIFIED/ACTIVE consumer use before #287 + fresh A + C3 acceptance; #40 is C3 HOLD (#6969485194) |

| [#277](https://github.com/yeatu/obsidianGP/issues/277) | **E3 RELEASED / P1 implementation slice complete; A3 changes requested** | F-5/F-6 delivered in PR #282; residual zero-width case isolated to #287 | E3 RELEASE #6997423293. A3 review #284 #6997673555 accepted F-6 and found only zero-width span gap in F-5; #284 CLOSED / REVIEW_CHANGES_REQUESTED. PR #282 remains exact reviewed HEAD `074bca4d...`, base `372c1b8...`, merge-ref `7206a590...`, 50/0, five E1 paths; E1/B-C/B1 green. No mutation to reviewed PR #282; E1 follow-up #287 CLAIM #6997884122 only |
| [#284](https://github.com/yeatu/obsidianGP/issues/284) | **A3 CLOSED / REVIEW_CHANGES_REQUESTED** | Review PR #282 выявил zero-width current/historical span gap; F-6 accepted | Exact target #282 HEAD `074bca4d...`; review #6997673555. F-6 accepted; F-5 remainder transferred to #287. No verdict transfers beyond this exact target |
| [#287](https://github.com/yeatu/obsidianGP/issues/287) | **E1 CLAIMED / P2 residual verifier correction** | Reject every individual zero-width current/historical content span; retain valid empty lists; then fresh A review | E1 CLAIM #6997884122; fresh correction-only branch starts at reviewed #282 HEAD `074bca4d...`; only E1 verifier module/tests; digest-recomputed current+historical tests; stable `node_span_mismatch`. Preserve F1–F6, #119 formats, E1 v1, five-path boundary; synthetic-only. PR #282 remains unchanged |
| [#289](https://github.com/yeatu/obsidianGP/issues/289) | **A — READY TO CLAIM / P1 integrated writer review** | Независимо проверить parent #170 и cumulative child #179 на exact refs/merge-refs | #170 HEAD `8d8559e...` / merge-ref `4470f113...`; #179 HEAD `a80d3e7...` / merge-ref `d89e0b3...`; main `372c1b8...`, four unique writer paths. Eight exact-head writer/C1/V2.1/V2.2 runs green. No merge before separate C3 decision |
| [#292](https://github.com/yeatu/obsidianGP/issues/292) | **A — READY TO CLAIM / P1 panel review** | Независимо проверить обновлённую governance panel PR #223 на exact HEAD | Exact HEAD/base/merge-ref and single-file PROJECT_TASKS-only diff are pinned in #292. No merge until A acceptance and separate C3 decision under #234 |
| [#279](https://github.com/yeatu/obsidianGP/issues/279) | **A2 CLAIMED / P2 read-only analysis** | Диагностировать gq-010 false positive `decoy_cycles` и передать evidence-based remediation options | A2 CLAIM #6997421011. Read-only trace of query normalization, numeric matching, FTS, candidate and ranking; preserve corpus/gold/runner and failed benchmark gate |
| [#280](https://github.com/yeatu/obsidianGP/issues/280) | **A2 CLAIMED / P2 read-only analysis** | Диагностировать gq-036 false positive `launch_z9` и границу E2 retrieval vs B1 integrity_warning | A2 CLAIM #6997427447; A3's later competing CLAIM #6997434587 was yielded in #6997442095. Read-only analysis only; preserve E2 code, corpus, expected labels and benchmark reports |
| [#281](https://github.com/yeatu/obsidianGP/issues/281) | **E2 BLOCKED / NOT READY TO CLAIM** | Remediate gq-010/gq-036 only after both A analyses and explicit C3 scope approval | Wait for #279/#280 reports, then narrow E2-owned file boundary and regression plan. Keep the benchmark baseline at 40/42; no gate or corpus changes |
| [#286](https://github.com/yeatu/obsidianGP/issues/286) | **A — READY TO CLAIM / P2 ANALYSIS** | Подготовить непересекающуюся lifecycle conformance matrix для #124 по решениям #225/#254 | Read-only analysis only; separate #124 lifecycle assertions from #138 query-path coverage. Does not unblock #124 implementation; accepted-component and E1 verifier gates remain in force |
| [#229](https://github.com/yeatu/obsidianGP/issues/229) | **E — GATED / unclaimed** | Synchronize benchmark PR #84 only after panel PR #223 is independently accepted, separately C-accepted and merged | **P1**; #234 single-writer rule. Current main→#84: 32 ahead / 136 behind from merge base `f665ae7...`; 4 benchmark technical paths + stale `PROJECT_TASKS.md` handoff hunk. No #84 mutation before panel merge; then preserve main panel verbatim and keep `gq-010`/`gq-036` failed
| [#42](https://github.com/yeatu/obsidianGP/issues/42) | E1 benchmark / quality gate | Сохранить воспроизводимый baseline и две видимые E2 retrieval failure | **P1**; gq-010 и gq-036 остаются failed; не менять corpus/метрики/ranking для зелёного отчёта |
| [#125](https://github.com/yeatu/obsidianGP/issues/125) | E3 RELEASED / P1 integrated writer review | Дождаться A verdict #289 и отдельного C3 integration decision для #170/#179 | E1 #196 RELEASE #6997701052; exact current refs and eight writer/cross-layer workflows are pinned in #289. PR #170/#179 remain open/unmerged; no verdict from old #171/#180 targets transfers |
| [#124](https://github.com/yeatu/obsidianGP/issues/124) | E — dependency-gated | Synthetic lifecycle conformance: prepare → write → stage → verify → activate → exact resolve | После принятия writer #125 и E1 verifier #240; resolver #120 уже merged; trust-order assertions обязательны |
| [#134](https://github.com/yeatu/obsidianGP/issues/134) | E — gated | B1 SnapshotIdentity protocol v2 | После A/C acceptance #240; resolver #120 уже merged; не является proof of verification |
| [#136](https://github.com/yeatu/obsidianGP/issues/136) | E — gated | E3 factory-verified cloud materialized binding | После #134 и A/C acceptance #240; resolver #120 уже merged |
| [#137](https://github.com/yeatu/obsidianGP/issues/137) | E — gated | Additive V2.2 `sfra.issue.v2` protocol | После #136; v1/TransportStatusV2 сохранить |
| [#138](https://github.com/yeatu/obsidianGP/issues/138) | E — gated | Synthetic V2.2 → V2.1 → E3/E1/E2 → B1 query conformance | После #134/#136/#137 |

### Конфликтующие и завершённые handoff’ы

- [#119](https://github.com/yeatu/obsidianGP/issues/119) — CLOSED / C3 accepted. Полный synthetic bundle builder/verifier и corrections #173/#204/#228 merged в main через PR #162.
- [#120](https://github.com/yeatu/obsidianGP/issues/120) — CLOSED / E2 implementation complete, A1 REVIEW_ACCEPTED, C3 accepted; PR #250 merged to main at `372c1b854a39c436969d3835d0656c46a4758677` (main first parent / reviewed PR HEAD `52570ceb...` second). Four E2-owned paths; synthetic/read-only only, no provider or catalogue promotion.
- [#254](https://github.com/yeatu/obsidianGP/issues/254) — C3 APPROVED: exact STAGED snapshots may be materialized only through a separate verification-only, non-query-capable #120 output for #240; catalogue promotion remains caller-enforced under #225.
- [#260](https://github.com/yeatu/obsidianGP/issues/260) — CLOSED / C3 APPROVED: initial resource envelope for E1 verifier F-3; larger #119 bundles stay STAGED until a separately measured limit revision.
- [#241](https://github.com/yeatu/obsidianGP/issues/241) — CLOSED as duplicate of canonical E1 verifier task #240; it has no CLAIM, implementation or verdict.
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

## 4. Writer stack — P1 current-main resync / conflict resolution

- Previous parent PR #170 HEAD was `5612a70520c91efcb9d4ccdd955f207c63bef641`; previous cumulative child PR #179 HEAD was `85126e3301e127b125d2ed4b8a554f0cdb32d15a`.
- Since those refs, E2 resolver PR #250 was A/C accepted and merged to main at `372c1b854a39c436969d3835d0656c46a4758677`. The new main tree is `b1612bd11d71f2a4a6563b39a4d119c2371e1f40`.
- The post-#250 writer conflict is resolved. Parent #170 HEAD `8d8559e021cc0c37ba20e5b0163c14c9607f3045` is **12 ahead / 0 behind** main; cumulative child #179 HEAD `a80d3e70b419e4b80c84595fa41ed5fc07587396` is **25 ahead / 0 behind** main and **13 ahead / 0 behind** parent. Both use current main as merge base and preserve exactly four writer-owned paths; A1 conflict map #268 confirmed zero overlap with the four resolver paths.
- E1 preserved history with guarded non-force parent-first / child-second merges. Parent refresh merge `08c2720f67bfcfb1a84ae0b0d98bf910dfa1af5f` parents main `372c1b8...` first / former #170 `5612a7...` second. Child integration HEAD `a80d3e7...` parents refreshed #170 `8d8559e...` first / former correction lineage `f2f8b9c...` second. No overlapping resolver/writer path conflict remains.
- Fresh exact-head CI is complete. Parent #170 writer fixture #44442178689 (18 passed) plus C1/V2.1/V2.2 #44442182960/#44442182948/#44442182935 all SUCCESS on exact HEAD/merge-ref. Child #179 writer fixture #44442511134 (27 passed) plus C1/V2.1/V2.2 #44442517044/#44442517095/#44442517185 all SUCCESS on exact HEAD/merge-ref. Disclosed E1-dependent cross-layer skips are not counted as passes. Inherited bundle run #44414369510 remains accepted (62 passed, zero skips) on unchanged accepted bundle tree.
- E1 published IMPLEMENTATION COMPLETE / RELEASE #6997701052 after updating #170/#179 and #125/#172 evidence. Fresh integrated independent A review #289 is open/unclaimed, pinned to both exact PR heads and merge refs. Do not merge #170/#179 until A acceptance and a separate C3 integration decision.
- No provider, credentials, upload, catalogue activation, real data, workflow_dispatch or production operation is authorized.

## 5. Benchmark — P1 shared-file conflict remains

PR #84 remains open/Draft at HEAD `64924c204f006bf9d41a42ca0724d8e026325014`. The live compare from current main `372c1b854a39c436969d3835d0656c46a4758677` is **diverged: 32 ahead / 136 behind**, merge base `f665ae7251387ee86b3f5adb48662b79406f392b`. Its effective current-main diff remains five paths: four benchmark technical paths and one stale `PROJECT_TASKS.md` #156 handoff hunk.

- #234 is the controlling single-writer decision: PR #223 alone owns root `PROJECT_TASKS.md`. #229 remains GATED until this panel receives fresh independent A acceptance, C3 records a separate merge decision and PR #223 is merged.
- After that merge, #229 must re-read live main/#84 refs, perform a non-force/main-first sync and preserve main's `PROJECT_TASKS.md` byte-for-byte; only the four benchmark workflow/README/runner/tests paths may remain in the PR diff. Stop on conflicts in those four technical files.
- Existing exact-head reproducibility evidence remains 42 cases, **40 pass / 2 fail**, 20/20 preflight, 14 diagnostics, zero explicit SourceRead mismatches, byte-identical JSON/Markdown reports. The two actual E2 quality failures remain `gq-010-number-plus-condition` and `gq-036-conflicting-versions`; no 42/42 claim, gate weakening, corpus edits or ranking changes.
- No parallel benchmark sync or PR #84 mutation is authorized before the panel A/C/merge gate.

## 6. E1 cloud-index verifier — P1 trust prerequisite #240

- [#240](https://github.com/yeatu/obsidianGP/issues/240) remains OPEN / not C3-accepted. E3 parent RELEASE #6996973158 and correction-chain RELEASE #6997423293 are recorded. PR [#271](https://github.com/yeatu/obsidianGP/pull/271) exact reviewed HEAD `3094d163...` received A2 REVIEW_CHANGES_REQUESTED #6997144102; keep it immutable. PR [#282](https://github.com/yeatu/obsidianGP/pull/282) delivered F-5/F-6 on HEAD `074bca4d87feb128bb88953480c5ffad5341dff2`, base `372c1b8...`, merge-ref `7206a590...`, 50/0 and five E1 paths. Exact-head E1 #44441003002 (49 focused / 155 regression), Structural B/C #44441003043 (155), and B1 #44441002985 (45) succeeded. A3 review [#284](https://github.com/yeatu/obsidianGP/issues/284) is CLOSED / REVIEW_CHANGES_REQUESTED (#6997673555): F-6 accepted; F-5 still allowed individual zero-width spans. The sole residual correction [#287](https://github.com/yeatu/obsidianGP/issues/287) is E1-CLAIMED (#6997884122) on a fresh correction-only branch from #282's reviewed HEAD; PR #282 remains unchanged. No #136/#124 use, immutable_import VERIFIED/ACTIVE transition or C3 acceptance until #287 is independently reviewed and C3 accepts parent #240. #40 is C3 HOLD / force-released (#6969485194); no MCP runtime work.
- Correction [#257](https://github.com/yeatu/obsidianGP/issues/257) was RELEASED by E3 after F1–F4 were delivered in PR #271. F-5/F-6 were delivered in PR #282 and RELEASED under #277; A3 accepted F-6 but requested changes for one residual F-5 edge in #284, now isolated to follow-up #287. PR #271/#282 remain immutable reviewed targets. Prior candidates #267/#270 and review #269 carry no transferable verdicts.
- **E2 benchmark diagnosis:** C3 decision [#278](https://github.com/yeatu/obsidianGP/issues/278) authorizes two independent read-only A analyses. A2 owns [#279](https://github.com/yeatu/obsidianGP/issues/279) for gq-010 (#6997421011) and [#280](https://github.com/yeatu/obsidianGP/issues/280) for gq-036 (#6997427447); A3's later competing claims were yielded (#6997431589/#6997442095). E2 remediation [#281](https://github.com/yeatu/obsidianGP/issues/281) remains BLOCKED pending both reports and a separate C3 scope decision. [#286](https://github.com/yeatu/obsidianGP/issues/286) is a separate open/unclaimed A analysis for non-overlapping #124 lifecycle conformance under #225/#254. Keep the 40/42 baseline and both failures unchanged.
  1. **Outer↔inner source revision binding:** verifier must accept an E1-owned expected tagged revision and require exact variant/value equality to attestation for both Git and immutable-import cases.
  2. **Directory symlink race:** root and descendants must be pinned/descriptor-relative with no-follow directory/file opens; add a deterministic directory replacement race test proving no out-of-root file is opened.
  3. **Unbounded resource use:** set documented limits for attestation/inventory/parser/path/tree work; stream hashes and do not retain non-Markdown payload bytes; add exact-boundary and over-limit tests.
  4. **Historical node-version integrity:** independently validate historical same-document parent links, node type and ordered line/character/UTF-8 byte spans; add tamper tests with recomputed DB digest.
- Keep the five-file E1 ownership boundary and accepted #119 wire formats. Preserve E1 manifest v1, `verify_state_directory()`, `create_state_snapshot()`, legacy callers and workflows. No E3 imports/provider access or production data.
- C3 decision [#260](https://github.com/yeatu/obsidianGP/issues/260) approves the initial F-3 verifier-only execution envelope: attestation 2 MiB, inventory 64 MiB, 100,000 Markdown rows, 256 parser pairs, 500,000 total source-tree entries, 32 MiB per Markdown file, 2 GiB aggregate Markdown bytes, and 4,096-character paths. Enforce incrementally with streaming/no-follow traversal and typed `resource_limit_exceeded`; bundles outside the E1 execution envelope remain STAGED. This does not change #119 wire format or producer validity.
- A2 review #272 is CLOSED / REVIEW_CHANGES_REQUESTED (#6997144102) on the pre-correction #271 candidate. #277 was RELEASED with F-5/F-6; A3 review #284 accepted F-6 but returned changes requested for zero-width span entries ( #6997673555 ). That residual is now #287. Fresh exact-head A review and separate C3 acceptance for #240 remain mandatory before #136/#124 or immutable-import verification can consume the report.

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

1. Prepared bundle must pass the public #119 bundle verifier before immutable write or verification materialization.
2. Writer #125 verifies exact immutable receipts/read-back; it does not prove E1 state consistency.
3. Catalogue #118 `stage()` records STAGED. `mark_verified()` is caller-enforced and does not become proof merely because a bundle was written or materialized.
4. The orchestrator may call `mark_verified(snapshot_id)` only after outer #119 bundle verification and inner #240 E1 whole-index verification succeed for the same exact snapshot ID and complete CloudSnapshotRefV2 identity.
5. For `immutable_import`, skipping the Git-shaped E1 v1 verifier is not success. Until #240 is independently reviewed and C3-accepted, the candidate remains STAGED; no VERIFIED/ACTIVE transition.
6. Per C3 decision #254, #120 may materialize an exact STAGED entry only through a distinct verification-only output bound to the full snapshot identity, tagged source revision, exact immutable object versions, outer bundle descriptor, materialized source-root/SQLite paths, raw #119 attestation/inventory bytes and the observed STAGED catalogue state. This object is input to #240 only.
7. The verification-only STAGED materialization is not a query capability. It must expose no E1 read_source, E2 search, B1 Context Pack or V2.2 methods; query adapters must reject it by type/factory boundary. #120/#240 must not call `mark_verified()`, `activate()` or mutate the catalogue.
8. The caller verifies #240's result against the same exact snapshot ID/full ref and outer bundle digest, then may call #118 `mark_verified()`. Activation remains a separate compare-and-swap decision. Any failure, mismatch, unavailable verifier or catalogue change leaves the entry STAGED.
9. Request-visible query binding is permitted only through #136 for an ACTIVE exact snapshot. STAGED, VERIFIED-but-not-active and RETIRED entries are not queryable; an A→B catalogue change cannot rebind an in-flight request from A to B.
10. Any verification failure/unavailable verifier must not advance VERIFIED/ACTIVE or mutate the previous ACTIVE pointer.
11. All current bundle/writer/resolver/lifecycle work remains synthetic/disposable with fake/in-memory stores. No provider, credentials, real Vault/SQLite/sidecar/`sfra-state`, production sync/import/read/write, real `read_source`, workflow_dispatch or activation is authorized.

## 9. Parallelism and coordination rules

- #196 remains E1-owned and has been RELEASED by E1 (#6997701052); the post-resolver parent/child sync and exact-head CI are complete. Integrated A review #289 is pending; neither PR may merge before A acceptance and separate C3 decision.
- #120 is CLOSED / COMPLETED: E2 RELEASED, A1 REVIEW_ACCEPTED, C3 ACCEPTED, PR #250 merged to main at `372c1b8...`. The four materializer files are now inherited main; no active resolver task remains.
- #240 remains OPEN / not C3-accepted. E3 RELEASED parent #240 (#6996973158) and correction #277 (#6997423293). A2 review #272 returned REVIEW_CHANGES_REQUESTED on PR #271 HEAD `3094d163...`; PR #271 remains immutable. PR #282 at HEAD `074bca4d...` implemented F-5/F-6; A3 review #284 (#6997673555) accepted F-6 but identified zero-width current/historical span entries in F-5. The sole follow-up is #287, open and ready for one E owner. No downstream #136/#124 use, VERIFIED/ACTIVE promotion or C3 acceptance until #287 receives fresh A review and C3 separately accepts #240. #40 remains C3 HOLD / force-released (#6969485194); no MCP runtime scope.
- #240 remains a separate E1 trust-verification stream from the merged E3 #120 materializer. F1–F4 are in PR #271; F-5/F-6 in PR #282 were released but F-5 has residual zero-width-span defect tracked in #287. No #136/#124 consumer work, VERIFIED/ACTIVE transition or downstream immutable_import use before #287's fresh A review and separate C3 acceptance of #240.
- #229 remains gated by panel PR #223 A/C/merge under #234; no parallel benchmark sync.
- #124 remains gated by #125 and A/C acceptance of #240; #134/#136/#137/#138 remain gated by their explicit #240 and downstream dependencies.
- Panel reviews #276/#283/#285/#288/#290/#291 were superseded/closed without verdict; no review evidence transfers. #291 was claimed by A2 but superseded after a material panel update (#6997899799). Fresh exact-head panel review #292 is the current request.
- Branch history is preserved: no force-push, rebase/reset, delete or automatic cleanup. Any unexpected shared-file/contract conflict is a stop-and-escalate event.

## 10. Operational rule

Before each integration or acceptance, reread live main, branch/PR HEAD and base, ordered parents, compare diff, active CLAIM/RELEASE/BLOCKED events, exact merge-ref CI, dependency gates and supersession notes. A verdict is valid only for its exact refs. Main merge, branch-only propagation and production activation are separate permissions.
