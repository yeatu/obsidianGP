# SFRA — оперативная панель проекта

> Точка входа для AI-участников. Источник истины — соответствующая GitHub Issue и её последние действующие события. Нормативный процесс — [Issue #20, Governance Protocol v2.4](https://github.com/yeatu/obsidianGP/issues/20). Панель не заменяет CLAIM, RELEASE, review, CI или решение координатора.

**Снимок:** 2026-11-19  
**Текущий main HEAD:** `710d194c5ce2e5f3c0b2f045f4dbfddcb9be60be`  
**Текущий main tree:** `28795f283856e72319b19472f097d2dfef83294b`  
**Последнее интегрированное изменение:** C3 принял и слил parent writer PR #170; bundle PR #162, resolver PR #250 и W1 PR #92 остаются в main. Cumulative child #179 и E1 verifier PR #293 требуют main-first sync и нового exact-head review.

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
| [#196](https://github.com/yeatu/obsidianGP/issues/196) | **E1 RELEASED / parent #170 MERGED; child #179 awaiting resync** | E1 to synchronize cumulative child under #296, rerun exact-head CI and obtain fresh A review | C3 merged parent PR #170 at `710d194c5ce2e5f3c0b2f045f4dbfddcb9be60be` after accepted A3 review #289. Child #179 remains at old HEAD `a80d3e70...`; compare from new main is diverged 13 ahead / 1 behind, merge base `8d8559e...`, GitHub says non-mergeable. Four writer-owned paths remain the only intended diff. #296 is the E1-owned main-first/non-force sync task. A3 #289 acceptance applies only to the pre-merge refs; fresh review and separate C3 child decision are required. Parent #170 stays merged; child #179 remains open/unmerged |
| [#240](https://github.com/yeatu/obsidianGP/issues/240) | **E3 RELEASED / A3 accepted cumulative PR #293; current-main sync pending** | E1 syncs PR #293 under #298; then fresh exact-head A review and separate C3 acceptance | PR #293 HEAD `f876db488a8c4871ccb47c88c037b4b7d697d55e`, old base `372c1b8...`, merge-ref `6228f585...`; A3 accepted #294 (#6998500901), RELEASE #6998505545. Current main advanced to `710d194...` after that verdict; live compare main→#293 is diverged 51 ahead / 13 behind (merge base `372c1b8...`), PR non-mergeable. #298 is the E1-owned non-force main-first sync task; no verifier merge or #136/#124 use until new exact-head A review and separate C3 acceptance. #40 remains C3 HOLD (#6969485194) |

| [#277](https://github.com/yeatu/obsidianGP/issues/277) | **E3 RELEASED / P1 implementation slice complete; A3 changes requested** | F-5/F-6 delivered in PR #282; residual zero-width case isolated to #287 | E3 RELEASE #6997423293. A3 review #284 #6997673555 accepted F-6 and found only zero-width span gap in F-5; #284 CLOSED / REVIEW_CHANGES_REQUESTED. PR #282 remains exact reviewed HEAD `074bca4d...`, base `372c1b8...`, merge-ref `7206a590...`, 50/0, five E1 paths; E1/B-C/B1 green. No mutation to reviewed PR #282; E1 follow-up #287 CLAIM #6997884122 only |
| [#284](https://github.com/yeatu/obsidianGP/issues/284) | **A3 CLOSED / REVIEW_CHANGES_REQUESTED** | Review PR #282 выявил zero-width current/historical span gap; F-6 accepted | Exact target #282 HEAD `074bca4d...`; review #6997673555. F-6 accepted; F-5 remainder transferred to #287. No verdict transfers beyond this exact target |
| [#287](https://github.com/yeatu/obsidianGP/issues/287) | **E1 RELEASED / P2 correction complete; A3 accepted** | Zero-width current/historical span correction delivered in PR #293; current-main sync handled under #298 | E1 RELEASE / handoff #6998106227; PR #293 HEAD `f876db4...`, exact correction delta two E1 verifier paths from reviewed #282 HEAD. A3 accepted exact target in #294 (#6998500901) and RELEASED #294 (#6998505545). PR #282/#271 remain unchanged; do not transfer verdict to a new post-main-sync PR #293 ref |
| [#289](https://github.com/yeatu/obsidianGP/issues/289) | **A3 CLOSED / REVIEW_ACCEPTED for historical pre-merge refs** | Fresh A review required after child #179 sync #296 | A3 accepted #170 HEAD `8d8559e...` and #179 HEAD `a80d3e7...` in #6997973089; RELEASE #6997984701. C3 merged parent #170 afterwards, changing main ancestry; old verdict does not transfer to the refreshed child target |
| [#292](https://github.com/yeatu/obsidianGP/issues/292) | **A2 CLOSED / REVIEW_CHANGES_REQUESTED; panel fixes pending** | C3 reconciles five live-state findings, main-first syncs panel and creates a new exact-head A request | A2 review #6998083046 identified stale #279/#280, #281 gate, #286/#289 ownership and #287 status. A2 RELEASE #6998091191. No verdict transfers to the corrected panel target |
| [#279](https://github.com/yeatu/obsidianGP/issues/279) | **A2 CLOSED / ANALYSIS_COMPLETE + RELEASED** | Root cause handed to C3; no active analysis ownership | Report #6997723962, RELEASE #6997784656. Identified unconditional AND→OR fallback as false-positive admission point; no code/tests/corpus/benchmark changes |
| [#280](https://github.com/yeatu/obsidianGP/issues/280) | **A2 CLOSED / ANALYSIS_COMPLETE + RELEASED** | Root cause handed to C3; no active analysis ownership | Report #6997777804, RELEASE #6997787456. Isolated E2 OR-fallback admission of `launch_z9` from the separately injected B1 version-conflict pair; no code/tests/corpus/benchmark changes |
| [#281](https://github.com/yeatu/obsidianGP/issues/281) | **E2 UNBLOCKED / READY TO CLAIM** | E2 to publish a valid CLAIM naming exact focused test files, then implement bounded fallback correction | C3 decision #297 approves E2 `db.py`, focused `source/tests/` and conditional README-only scope. Preserve exact/morphological AND, numeric equality and intentional one-token/partial behavior; keep corpus and 40/42 baseline untouched |
| [#286](https://github.com/yeatu/obsidianGP/issues/286) | **A3 CLOSED / ANALYSIS_COMPLETE + RELEASED** | Lifecycle conformance matrix для #124 передана в #6998185132; сама реализация #124 остаётся dependency-gated | A3 RELEASE #6998191043. Отчёт разделяет #124 lifecycle и #138 query-path tests; не разрешает реализацию, mark_verified или activation |
| [#229](https://github.com/yeatu/obsidianGP/issues/229) | **E — GATED / unclaimed** | Synchronize benchmark PR #84 only after corrected panel PR #223 is independently accepted, separately C3-accepted and merged | **P1**; #234 single-writer rule. Current main `710d194...`→#84 HEAD `64924c2...`: diverged 32 ahead / 149 behind, merge base `f665ae7...`; four benchmark technical paths plus stale `PROJECT_TASKS.md` hunk. No #84 mutation before panel merge; afterwards preserve main panel byte-for-byte |
| [#42](https://github.com/yeatu/obsidianGP/issues/42) | E1 benchmark / quality gate | Сохранить воспроизводимый baseline и две видимые E2 retrieval failure | **P1**; gq-010 и gq-036 остаются failed; не менять corpus/метрики/ranking для зелёного отчёта |
| [#125](https://github.com/yeatu/obsidianGP/issues/125) | E3 RELEASED / parent accepted; cumulative child pending | Writer parent PR #170 merged; child #179 must resync under #296, pass new CI and receive fresh A/C acceptance | C3 parent integration comment #6998472795; merge commit `710d194...`. A3 #289 accepted only old exact refs; #296 tracks child synchronization. No writer provider/storage production permission |
| [#124](https://github.com/yeatu/obsidianGP/issues/124) | E — dependency-gated | Synthetic lifecycle conformance: prepare → write → stage → verify → activate → exact resolve | Lifecycle matrix A3 completed in #286. Implementation remains blocked pending cumulative writer child acceptance and E1 verifier #240 A/C acceptance; resolver #120 is merged. Trust-order assertions mandatory |
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

## 4. Writer stack — parent merged; cumulative child resync is P1

- Current main is `710d194c5ce2e5f3c0b2f045f4dbfddcb9be60be` (tree `28795f283856e72319b19472f097d2dfef83294b`). Parent PR #170 HEAD `8d8559e021cc0c37ba20e5b0163c14c9607f3045` was independently accepted in #289 and merged by C3 first at `710d194...`; merge parents are previous main `372c1b8...` first / reviewed parent HEAD second.
- Cumulative child PR #179 remains open at `a80d3e70b419e4b80c84595fa41ed5fc07587396`. Live compare from new main `710d194...` to child is diverged **13 ahead / 1 behind**, merge base `8d8559e...`; GitHub reports `mergeable=false`. The old child still contains the four-path writer delta, but lacks the new parent merge commit.
- E1 owns resynchronization under [#296](https://github.com/yeatu/obsidianGP/issues/296): non-force main-first two-parent merge with old child HEAD second; preserve child tree byte-for-byte and exactly the four writer paths. No rebase, force-push or source changes. After sync, run fresh dedicated writer fixture and C1/V2.1/V2.2 checks on exact new refs; disclose skips.
- A3 #289 REVIEW_ACCEPTED (#6997973089; RELEASE #6997984701) remains valid only for the pre-parent-merge exact refs. It does not transfer to the refreshed child target. A new integrated exact-head review and a separate C3 decision are required before PR #179 can merge.
- C3's #196 integration decision accepted the stack and merged parent only; #295 remains open while child resync, fresh A review and subsequent C3 child decision remain outstanding.
- No provider SDK/credentials/remote storage, production upload/read/write, real Vault/SQLite/sidecar/sfra-state, workflow_dispatch or catalogue activation is authorized.

## 5. Benchmark — P1 shared-file conflict remains

PR #84 remains open/Draft at HEAD `64924c204f006bf9d41a42ca0724d8e026325014`. The live compare from current main `710d194c5ce2e5f3c0b2f045f4dbfddcb9be60be` is **diverged: 32 ahead / 149 behind**, merge base `f665ae7251387ee86b3f5adb48662b79406f392b`. Its effective current-main diff remains five paths: four benchmark technical paths and one stale `PROJECT_TASKS.md` #156 handoff hunk.

- #234 is the controlling single-writer decision: PR #223 alone owns root `PROJECT_TASKS.md`. #229 remains GATED until this panel receives fresh independent A acceptance, C3 records a separate merge decision and PR #223 is merged.
- After that merge, #229 must re-read live main/#84 refs, perform a non-force/main-first sync and preserve main's `PROJECT_TASKS.md` byte-for-byte; only the four benchmark workflow/README/runner/tests paths may remain in the PR diff. Stop on conflicts in those four technical files.
- Existing exact-head reproducibility evidence remains 42 cases, **40 pass / 2 fail**, 20/20 preflight, 14 diagnostics, zero explicit SourceRead mismatches, byte-identical JSON/Markdown reports. The two actual E2 quality failures remain `gq-010-number-plus-condition` and `gq-036-conflicting-versions`; no 42/42 claim, gate weakening, corpus edits or ranking changes.
- No parallel benchmark sync or PR #84 mutation is authorized before the panel A/C/merge gate.

## 6. E1 cloud-index verifier — P1 trust prerequisite #240

- [#240](https://github.com/yeatu/obsidianGP/issues/240) remains OPEN / awaiting current-main sync and separate C3 acceptance. Parent implementation RELEASE #6996973158 and correction-chain RELEASEs #6997423293/#6998106227 are recorded. Cumulative PR [#293](https://github.com/yeatu/obsidianGP/pull/293) at HEAD `f876db488a8c4871ccb47c88c037b4b7d697d55e`, old base `372c1b8...`, merge-ref `6228f585...`, carries the five E1 verifier-owned paths. A3 accepted that exact target in #294 (#6998500901; RELEASE #6998505545), confirming the positive-width current/historical span fix, digest-recomputed adversarial tests and valid empty-list case. Main then advanced to `710d194...` through writer parent PR #170; compare main→#293 is diverged 51/13 with merge base `372c1b8...` and GitHub says non-mergeable. E1 sync task [#298](https://github.com/yeatu/obsidianGP/issues/298) requires main-first non-force sync, fresh exact-head E1/B-C/B1 CI and a new independent A review. No merge, #136/#124 use or immutable_import VERIFIED/ACTIVE transition before fresh A and separate C3 acceptance. #40 remains C3 HOLD / force-released (#6969485194).
- Correction [#257](https://github.com/yeatu/obsidianGP/issues/257) was RELEASED by E3 after F1–F4 in PR #271. F-5/F-6 were added through #277/PR #282; A3's residual zero-width-span finding was fixed by E1 in #287/PR #293 and accepted on its exact old target in #294. PR #271/#282 remain unchanged historical targets; PR #293 now needs main-first sync #298 and a fresh exact-head A review before C3 can accept #240.
- **E2 benchmark diagnosis/remediation:** A2 completed and RELEASED reports for [#279](https://github.com/yeatu/obsidianGP/issues/279) (#6997723962/#6997784656) and [#280](https://github.com/yeatu/obsidianGP/issues/280) (#6997777804/#6997787456). C3 decision [#297](https://github.com/yeatu/obsidianGP/issues/297) approves a bounded E2 correction for the shared tier-6 AND→OR fallback. [#281](https://github.com/yeatu/obsidianGP/issues/281) is UNBLOCKED / READY TO CLAIM; E2 must claim with exact focused test files before editing. Preserve exact/morphological AND, numeric matching and intentional partial search. No benchmark runner/corpus/labels/metrics changes; keep 40/42 and both failures visible. Lifecycle analysis [#286](https://github.com/yeatu/obsidianGP/issues/286) is CLOSED/RELEASED by A3 (#6998191043); #124 implementation remains gated.
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

- #196 is E1 RELEASED. C3 accepted the old integrated stack after A3 #289 and merged parent PR #170 to main at `710d194...`; cumulative child PR #179 is pending E1 main-first sync #296. Old A acceptance does not transfer; require new exact-head CI/A and separate C3 child decision.
- #120 is CLOSED / COMPLETED: E2 RELEASED, A1 REVIEW_ACCEPTED, C3 ACCEPTED, PR #250 merged to main at `372c1b8...`. The four materializer files are inherited main; no active resolver task remains.
- #240 remains OPEN / not C3-accepted. PR #293 contains the cumulative E1 implementation/corrections; A3 accepted its exact old target in #294. E1 owns post-main sync #298, then fresh CI/A and separate C3 acceptance. No downstream #136/#124 use, VERIFIED/ACTIVE promotion or immutable_import activation before those gates. #40 remains C3 HOLD / force-released (#6969485194); no MCP runtime scope.
- #229 remains gated by corrected panel PR #223 A/C/merge under #234; no parallel benchmark sync. Live current-main compare is 32 ahead / 149 behind.
- #124 remains gated by integrated writer child and A/C acceptance of #240; A3's lifecycle matrix #286 is complete but does not unblock implementation. #134/#136/#137/#138 remain gated by their explicit #240 and downstream dependencies.
- Panel review #292 is CLOSED / REVIEW_CHANGES_REQUESTED (#6998083046; RELEASE #6998091191). C3 is reconciling the findings on the sole panel branch after main advanced to `710d194...`; a new exact-head request will supersede #292. No verdict transfers.
- Branch history is preserved: no force-push, rebase/reset, delete or automatic cleanup. Any unexpected shared-file/contract conflict is a stop-and-escalate event.

## 10. Operational rule

Before each integration or acceptance, reread live main, branch/PR HEAD and base, ordered parents, compare diff, active CLAIM/RELEASE/BLOCKED events, exact merge-ref CI, dependency gates and supersession notes. A verdict is valid only for its exact refs. Main merge, branch-only propagation and production activation are separate permissions.
