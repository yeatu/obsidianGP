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
| [#196](https://github.com/yeatu/obsidianGP/issues/196) | **E1 CLAIMED / P1 CURRENT-MAIN RESYNC REQUIRED** | Пересинхронизировать stacked writer PR #170/#179 после merge resolver #250; затем повторить exact-head writer/cross-layer CI и передать integrated A review | Current main `372c1b8...`; #170 HEAD `5612a705...` is 10 ahead / 8 behind; #179 HEAD `85126e...` is 21 ahead / 8 behind. A1 conflict map #268 found no file overlap between the four resolver and four writer paths. Sync in order: current main → #170 → #179, main-first/non-force/expected-old-HEAD. The parent writer workflow's push/path filter needs an in-scope writer-doc note after sync to trigger its dedicated suite; rerun parent/child writer and C1/V2.1/V2.2 suites on the exact refreshed targets |
| [#240](https://github.com/yeatu/obsidianGP/issues/240) | **E3 RELEASED / P1 F-5/F-6 CORRECTION #277 OPEN** | Завершить cumulative E1 verifier через correction #277, fresh A review и отдельную C3 acceptance | A2 вынес REVIEW_CHANGES_REQUESTED #6997144102 на exact PR #271 HEAD `3094d163...`; E3 RELEASE #6996973158. PR #271 сохранён без изменений. #277 — единственная активная реализация F-5/F-6; no #136/#124 use or VERIFIED/ACTIVE promotion before fresh A + C acceptance. E3's separate #40 claim remains BLOCKED by #36/#51 and #38 |
| [#283](https://github.com/yeatu/obsidianGP/issues/283) | **A — READY TO CLAIM / P1 panel review** | Независимо проверить актуальную governance panel PR #223 после включения #277 и superseded review #276 | Exact panel HEAD/base/merge-ref and one-file PROJECT_TASKS-only diff are pinned in #283. No panel merge until A acceptance + separate C3 decision under #234 |
| [#277](https://github.com/yeatu/obsidianGP/issues/277) | **E — READY TO CLAIM / P1 VERIFIER CORRECTION** | Исправить F-5/F-6: семантическая проверка current/historical content spans и единственной строки schema_info | Correction for #240 / review #272; preserve reviewed PR #271 HEAD `3094d163...` unchanged. Fresh correction-only branch/PR; scope verifier module, focused tests and narrow docs. Preserve #119 and E1 v1; synthetic fixtures only |
| [#229](https://github.com/yeatu/obsidianGP/issues/229) | **E — GATED / unclaimed** | Synchronize benchmark PR #84 only after panel PR #223 is independently accepted, separately C-accepted and merged | **P1**; #234 single-writer rule. Current main→#84: 32 ahead / 136 behind from merge base `f665ae7...`; 4 benchmark technical paths + stale `PROJECT_TASKS.md` handoff hunk. No #84 mutation before panel merge; then preserve main panel verbatim and keep `gq-010`/`gq-036` failed
| [#42](https://github.com/yeatu/obsidianGP/issues/42) | E1 benchmark / quality gate | Сохранить воспроизводимый baseline и две видимые E2 retrieval failure | **P1**; gq-010 и gq-036 остаются failed; не менять corpus/метрики/ranking для зелёного отчёта |
| [#125](https://github.com/yeatu/obsidianGP/issues/125) | E3 implementation / writer stack | Закончить writer после #196, получить независимый review и C acceptance | PR #170/#179 остаются open/unmerged; старые #171/#180 verdicts не переносятся на новые HEAD |
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

- Previous validated parent PR #170 HEAD: `5612a70520c91efcb9d4ccdd955f207c63bef641`; previous cumulative child PR #179 HEAD: `85126e3301e127b125d2ed4b8a554f0cdb32d15a`; both remain open/unmerged.
- Since those refs, E2 resolver PR #250 was A/C accepted and merged to main at `372c1b854a39c436969d3835d0656c46a4758677`. The new main tree is `b1612bd11d71f2a4a6563b39a4d119c2371e1f40`.
- Live comparisons now show main → #170 **diverged 10 ahead / 8 behind** and main → #179 **diverged 21 ahead / 8 behind**; merge base remains old main `8d1d3c9...`. The new incoming main commit set is the already accepted #120 resolver/materializer (four E2-owned paths) and is disjoint from the four writer-owned workflow/docs/module/tests paths.
- C3 has not modified writer branches. E1's existing CLAIM on #196 remains owner. Required next sequence: non-force main-first two-parent merge of current main `372c1b8...` into #170 preserving former #170 HEAD `5612a7...` second; verify exactly four writer-owned files; then propagate refreshed #170 first / former #179 HEAD `85126e...` second into #179, preserving the same four paths; expected-old-HEAD guards for both updates.
- Prior writer fixtures remain valid historical evidence only: parent #44420253244 (18 passed) and child #44420909911 (27 passed); prior C1/V2.1/V2.2 runs also apply only to their old exact HEADs. Rerun parent/child writer fixtures and C1/V2.1/V2.2 on the refreshed exact merge-ref after the resync. Inherited bundle run #44414369510 (62 passed, zero skips) remains valid because the accepted #119 tree is unchanged inside current main.
- After new exact-head CI, E1 must publish formal RELEASE and open one fresh integrated A review pinned to current #179 HEAD/base/merge-ref. Do not merge #170/#179 until fresh A acceptance and separate C3 integration decision.
- No provider, credentials, upload, catalogue activation, real data, workflow_dispatch or production operation is authorized.

## 5. Benchmark — P1 shared-file conflict remains

PR #84 remains open/Draft at HEAD `64924c204f006bf9d41a42ca0724d8e026325014`. The live compare from current main `372c1b854a39c436969d3835d0656c46a4758677` is **diverged: 32 ahead / 136 behind**, merge base `f665ae7251387ee86b3f5adb48662b79406f392b`. Its effective current-main diff remains five paths: four benchmark technical paths and one stale `PROJECT_TASKS.md` #156 handoff hunk.

- #234 is the controlling single-writer decision: PR #223 alone owns root `PROJECT_TASKS.md`. #229 remains GATED until this panel receives fresh independent A acceptance, C3 records a separate merge decision and PR #223 is merged.
- After that merge, #229 must re-read live main/#84 refs, perform a non-force/main-first sync and preserve main's `PROJECT_TASKS.md` byte-for-byte; only the four benchmark workflow/README/runner/tests paths may remain in the PR diff. Stop on conflicts in those four technical files.
- Existing exact-head reproducibility evidence remains 42 cases, **40 pass / 2 fail**, 20/20 preflight, 14 diagnostics, zero explicit SourceRead mismatches, byte-identical JSON/Markdown reports. The two actual E2 quality failures remain `gq-010-number-plus-condition` and `gq-036-conflicting-versions`; no 42/42 claim, gate weakening, corpus edits or ranking changes.
- No parallel benchmark sync or PR #84 mutation is authorized before the panel A/C/merge gate.

## 6. E1 cloud-index verifier — P1 trust prerequisite #240

- [#240](https://github.com/yeatu/obsidianGP/issues/240) remains OPEN / awaiting correction after E3's RELEASE #6996973158. PR [#271](https://github.com/yeatu/obsidianGP/pull/271) exact HEAD `3094d163...`, base `372c1b8...`, merge-ref `64605afa...`, 45/0 and five E1-owned paths received A2 REVIEW_CHANGES_REQUESTED #6997144102. The two new findings F-5/F-6 are tracked only in [#277](https://github.com/yeatu/obsidianGP/issues/277): current/historical content-span semantic validation and strict whole-table schema_info validation. PR #271 and its reviewed branch stay unchanged; #277 uses one fresh correction-only branch/PR and exact-head A re-review. The former parent CLAIM #6994736722 remains invalid. E3's separate #40 claim remains BLOCKED by #36/#51 and #38. No downstream #136/#124 use, immutable_import VERIFIED/ACTIVE transition or C3 acceptance is authorized before correction and fresh A/C acceptance.
- Correction [#257](https://github.com/yeatu/obsidianGP/issues/257) was RELEASED by E3 after F1–F4 were delivered in PR #271. A2 reviewed the cumulative candidate and identified the additional F-5/F-6 gaps in #277; the correction task now tracks those two findings. Prior candidate PRs #267/#270 and review #269 are closed without verdict and carry no transferable evidence.
  1. **Outer↔inner source revision binding:** verifier must accept an E1-owned expected tagged revision and require exact variant/value equality to attestation for both Git and immutable-import cases.
  2. **Directory symlink race:** root and descendants must be pinned/descriptor-relative with no-follow directory/file opens; add a deterministic directory replacement race test proving no out-of-root file is opened.
  3. **Unbounded resource use:** set documented limits for attestation/inventory/parser/path/tree work; stream hashes and do not retain non-Markdown payload bytes; add exact-boundary and over-limit tests.
  4. **Historical node-version integrity:** independently validate historical same-document parent links, node type and ordered line/character/UTF-8 byte spans; add tamper tests with recomputed DB digest.
- Keep the five-file E1 ownership boundary and accepted #119 wire formats. Preserve E1 manifest v1, `verify_state_directory()`, `create_state_snapshot()`, legacy callers and workflows. No E3 imports/provider access or production data.
- C3 decision [#260](https://github.com/yeatu/obsidianGP/issues/260) approves the initial F-3 verifier-only execution envelope: attestation 2 MiB, inventory 64 MiB, 100,000 Markdown rows, 256 parser pairs, 500,000 total source-tree entries, 32 MiB per Markdown file, 2 GiB aggregate Markdown bytes, and 4,096-character paths. Enforce incrementally with streaming/no-follow traversal and typed `resource_limit_exceeded`; bundles outside the E1 execution envelope remain STAGED. This does not change #119 wire format or producer validity.
- A2 review #272 is CLOSED / REVIEW_CHANGES_REQUESTED (#6997144102); F-5/F-6 are assigned to #277. A fresh exact-head A review is required after that correction. C3 must separately accept #240 before #136/#124 or immutable-import verification can consume the report.

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

- #196 remains E1-owned and now requires a fresh current-main writer-stack resync because main advanced by the accepted #120 merge; do not transfer its claim.
- #120 is CLOSED / COMPLETED: E2 RELEASED, A1 REVIEW_ACCEPTED, C3 ACCEPTED, PR #250 merged to main at `372c1b8...`. The four materializer files are now inherited main; no active resolver task remains.
- #240 remains OPEN / E3 CLAIMED via #6996704817; C3 recognition #6996843151. PR #271 is under A2's independent review #272 (CLAIM #6996863329); no verdict or C3 acceptance yet. The former parent CLAIM #6994736722 remains invalid. E3 RELEASED correction #257 and now explicitly owns parent #240; a separate E3 #40 claim remains BLOCKED by dependencies and is non-overlapping. PR #267/#269 remain closed without verdict. Preserve PR #248 and all historical refs. C3 decision #260 approves F3 limits.
- #240/#257 remain a separate E1 trust-verification stream from the now-merged E3 #120 materializer. No #136/#124 consumer work, VERIFIED/ACTIVE transition or downstream immutable_import use before F1–F4 correction, fresh A acceptance and C3 acceptance.
- #229 remains gated by panel PR #223 A/C/merge under #234; no parallel benchmark sync.
- #124 remains gated by #125 and A/C acceptance of #240; #134/#136/#137/#138 remain gated by their explicit #240 and downstream dependencies.
- Earlier panel reviews #249/#256/#261/#263/#264/#265/#266 returned changes requested on stale exact snapshots or were superseded; #274 was closed as target-superseded without verdict after PR #271 became the canonical correction candidate. No verdict or evidence transfers; this panel revision requires a fresh exact-head A review.
- Branch history is preserved: no force-push, rebase/reset, delete or automatic cleanup. Any unexpected shared-file/contract conflict is a stop-and-escalate event.

## 10. Operational rule

Before each integration or acceptance, reread live main, branch/PR HEAD and base, ordered parents, compare diff, active CLAIM/RELEASE/BLOCKED events, exact merge-ref CI, dependency gates and supersession notes. A verdict is valid only for its exact refs. Main merge, branch-only propagation and production activation are separate permissions.
