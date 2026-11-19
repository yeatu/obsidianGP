# SFRA — оперативная панель проекта

> Точка входа для AI-участников. Источник истины — соответствующая GitHub Issue и её последние действующие события. Нормативный процесс — [Issue #20, Governance Protocol v2.4](https://github.com/yeatu/obsidianGP/issues/20). Панель не заменяет CLAIM, RELEASE, review, CI или решение координатора.

**Снимок:** 2026-11-19  
**Текущий main HEAD:** `8605b84ce166a16fc4d738b13cce3993aa87393f`  
**Текущий main tree:** `1b00aa3a2a169a7fcc69f9782c3f5d4a12886f2a`  
**Последнее интегрированное изменение:** PR #223 с single-writer панелью независимо A-принят (#301), отдельно C3-авторизован (#302) и merged в main (`8605b84...`). После новых CLAIM E2 #281, E1 #296/#298 создан follow-up panel PR #304; он отражает актуальные ownership-переходы и ждёт свежую A/C-приёмку. Writer child #179 sync is complete (14/0, four paths); its exact-head dedicated writer fixture and fresh A review remain pending. Verifier #293 sync and exact-head CI are complete (52/0, five paths); fresh A review #307 and C3 decision #303 remain pending.

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
| [#196](https://github.com/yeatu/obsidianGP/issues/196) | **E1 CLAIMED #296 / child sync complete; final writer fixture + A review pending** | E1 to complete the dedicated writer fixture on exact #179 HEAD and request a fresh integrated A review | CLAIM #7001206337. PR #179 HEAD `d2939f85537049226e689cf5e0c6d64d96204d58`; sync parents: current main `8605b84...` first / prior child `a80d3e70...` second. Direct compare **14 ahead / 0 behind**, exactly four writer-owned paths. Exact-head C1 #44470296680, V2.1 #44470296688 and V2.2 #44470296631 succeeded; common suite had 197 passed / 72 dependency/path skips, V2.1 19 passed, V2.2 55 passed. No dedicated writer fixture run found for `d2939f8...`; old fixture #44442511134 is on prior HEAD and does not transfer. No fresh A request yet. #295 stays HOLD; PR #179 remains open/unmerged |
| [#240](https://github.com/yeatu/obsidianGP/issues/240) | **E1 sync complete / fresh A review #307 pending; C3 decision #303 on HOLD** | A to review exact post-sync verifier candidate; C3 decides integration only after exact-target `REVIEW_ACCEPTED` | E1 RELEASE #7001502066 / integration #298 complete. PR #293 HEAD `4e41d71e82dda45758ee0d8a99c63af852ddd6d6`; main `8605b84...` first parent / former HEAD `f876db4...` second. Merge-ref `cb750b3a3696fb3a284df55b3123ed770f8d80d3`; direct compare **52 ahead / 0 behind**, exactly five E1 verifier paths. Exact-head E1 #44470332333: focused 52, full regression 158, CLI success; Structural B/C #44470332402: 158 passed, CLI/boundary success; B1 #44470332259: 45 passed, unrelated E1 source API job path-filtered skipped. Fresh A request [#307](https://github.com/yeatu/obsidianGP/issues/307) is open; no verdict yet. Old #294 does not transfer. #303 stays HOLD; no merge, #136/#124 use or VERIFIED/ACTIVE promotion before A+C |

| [#277](https://github.com/yeatu/obsidianGP/issues/277) | **E3 RELEASED / P1 implementation slice complete; A3 changes requested** | F-5/F-6 delivered in PR #282; residual zero-width case isolated to #287 | E3 RELEASE #6997423293. A3 review #284 #6997673555 accepted F-6 and found only zero-width span gap in F-5; #284 CLOSED / REVIEW_CHANGES_REQUESTED. PR #282 remains exact reviewed HEAD `074bca4d...`, base `372c1b8...`, merge-ref `7206a590...`, 50/0, five E1 paths; E1/B-C/B1 green. No mutation to reviewed PR #282; E1 follow-up #287 CLAIM #6997884122 only |
| [#284](https://github.com/yeatu/obsidianGP/issues/284) | **A3 CLOSED / REVIEW_CHANGES_REQUESTED** | Review PR #282 выявил zero-width current/historical span gap; F-6 accepted | Exact target #282 HEAD `074bca4d...`; review #6997673555. F-6 accepted; F-5 remainder transferred to #287. No verdict transfers beyond this exact target |
| [#287](https://github.com/yeatu/obsidianGP/issues/287) | **E1 RELEASED / P2 correction complete; A3 accepted** | Zero-width current/historical span correction delivered in PR #293; current-main sync handled under #298 | E1 RELEASE / handoff #6998106227; PR #293 HEAD `f876db4...`, exact correction delta two E1 verifier paths from reviewed #282 HEAD. A3 accepted exact target in #294 (#6998500901) and RELEASED #294 (#6998505545). PR #282/#271 remain unchanged; do not transfer verdict to a new post-main-sync PR #293 ref |
| [#289](https://github.com/yeatu/obsidianGP/issues/289) | **A3 CLOSED / REVIEW_ACCEPTED for historical pre-merge refs** | Fresh A review required after child #179 sync #296 | A3 accepted #170 HEAD `8d8559e...` and #179 HEAD `a80d3e7...` in #6997973089; RELEASE #6997984701. C3 merged parent #170 afterwards, changing main ancestry; old verdict does not transfer to the refreshed child target |
| [#292](https://github.com/yeatu/obsidianGP/issues/292) | **A2 CLOSED / REVIEW_CHANGES_REQUESTED; historical target only** | Five findings reconciled in the current panel revision; replacement exact-head review is linked in PR #223 description | A2 review #6998083046 identified stale #279/#280, #281 gate, #286/#289 ownership and #287 status. A2 RELEASE #6998091191. No verdict transfers from #292 |
| [#279](https://github.com/yeatu/obsidianGP/issues/279) | **A2 CLOSED / ANALYSIS_COMPLETE + RELEASED** | Root cause handed to C3; no active analysis ownership | Report #6997723962, RELEASE #6997784656. Identified unconditional AND→OR fallback as false-positive admission point; no code/tests/corpus/benchmark changes |
| [#280](https://github.com/yeatu/obsidianGP/issues/280) | **A2 CLOSED / ANALYSIS_COMPLETE + RELEASED** | Root cause handed to C3; no active analysis ownership | Report #6997777804, RELEASE #6997787456. Isolated E2 OR-fallback admission of `launch_z9` from the separately injected B1 version-conflict pair; no code/tests/corpus/benchmark changes |
| [#281](https://github.com/yeatu/obsidianGP/issues/281) | **E2 CLAIMED / IN PROGRESS** | E2 implementing bounded tier-6 admission correction, focused regressions and scoped docs | CLAIM #7001141865; paths fixed by ref addenda #7001152432/#7001278874: E2 `sfra_search/db.py`, `source/tests/test_search_index.py`, and `source/README.md` (documentation only). Preserve exact/morphological AND, numeric equality and intentional one-token/partial behavior; keep corpus, reports and 40/42 baseline unchanged |
| [#286](https://github.com/yeatu/obsidianGP/issues/286) | **A3 CLOSED / ANALYSIS_COMPLETE + RELEASED** | Lifecycle conformance matrix для #124 передана в #6998185132; сама реализация #124 остаётся dependency-gated | A3 RELEASE #6998191043. Отчёт разделяет #124 lifecycle и #138 query-path tests; не разрешает реализацию, mark_verified или activation |
| [#229](https://github.com/yeatu/obsidianGP/issues/229) | **E1 READY AFTER PANEL #304 MERGE** | After #304 merges, E1 to CLAIM and sync benchmark PR #84 to then-current main; preserve `PROJECT_TASKS.md` verbatim, retain four benchmark paths, rerun two full 42-case attempts and request fresh A review | **P1**; #223 A4 #301/C3 #302 merged at `8605b84...`; #281's later E2 CLAIM #7001141865 is being recorded by #304, with A #305 and C3 #306 gates pending. PR #84 HEAD `64924c2...`; current compare 32 ahead / 207 behind from `f665ae7...`, four technical paths plus stale one-line panel hunk. Do not mutate before #304 merge; preserve 40/42 and gq-010/gq-036 failures |
| [#42](https://github.com/yeatu/obsidianGP/issues/42) | E1 benchmark / quality gate | Сохранить воспроизводимый baseline и две видимые E2 retrieval failure | **P1**; gq-010 и gq-036 остаются failed; не менять corpus/метрики/ranking для зелёного отчёта |
| [#125](https://github.com/yeatu/obsidianGP/issues/125) | E3 RELEASED / parent accepted; cumulative child validation pending | Writer parent PR #170 merged; child #179 sync under #296 completed at HEAD `d2939f8...`; dedicated writer fixture and fresh A/C acceptance still pending | C3 parent integration comment #6998472795; merge commit `710d194...`. Current child compare to main is 14/0 with four writer paths; C1/V2.1/V2.2 pass but the dedicated writer fixture is not yet rerun on the new HEAD. No writer provider/storage production permission |
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

## 4. Writer stack — parent merged; child branch sync complete, exact writer fixture outstanding

- Current main is `8605b84ce166a16fc4d738b13cce3993aa87393f` (tree `1b00aa3a2a169a7fcc69f9782c3f5d4a12886f2a`). Parent PR #170 was accepted in #289 and merged at `710d194...`; single-writer panel PR #223 was separately A/C-accepted and merged at `8605b84...`.
- PR #179 current HEAD is `d2939f85537049226e689cf5e0c6d64d96204d58`. Its sync commit parents are current main `8605b84...` first / former child HEAD `a80d3e70...` second. Direct current-main→child compare: **14 ahead / 0 behind**, merge base current main, exactly four writer-owned paths. GitHub reports mergeable. The REST PR-files list can show a stale `PROJECT_TASKS.md` entry; the direct compare against current main is authoritative and shows no panel-path delta.
- Exact-head C1 #44470296680, V2.1 #44470296688 and V2.2 #44470296631 all succeeded. Logs show 197 passed / 72 dependency/path-filtered skips in the common suite; V2.1 adds 19 passed and V2.2 adds 55 passed. Skipped E1 bundle/indexer/materializer/writer fixtures are not counted as passes.
- The dedicated writer fixture workflow has **not** been found for exact HEAD `d2939f8...`; the latest dedicated fixture run #44442511134 checked former HEAD `a80d3e7...` only. E1 must run that fixture on the current exact HEAD and then create one fresh integrated A review request. Prior A3 #289 and its fixture result do not transfer.
- E1's task-specific CLAIM is #7001206337 on [#296](https://github.com/yeatu/obsidianGP/issues/296). C3 child decision [#295](https://github.com/yeatu/obsidianGP/issues/295) remains HOLD until the exact writer fixture and fresh A acceptance exist. PR #179 remains open/unmerged.
- No provider SDK/credentials/remote storage, production upload/read/write, real Vault/SQLite/sidecar/sfra-state, workflow_dispatch or catalogue activation is authorized.

## 5. Benchmark — P1 shared-file conflict remains

PR #84 remains open/Draft at HEAD `64924c204f006bf9d41a42ca0724d8e026325014`. The live compare from current main `8605b84ce166a16fc4d738b13cce3993aa87393f` is **diverged: 32 ahead / 207 behind**, merge base `f665ae7251387ee86b3f5adb48662b79406f392b`. Its effective current-main diff remains five paths: four benchmark technical paths and one stale `PROJECT_TASKS.md` #156 handoff hunk.

- #234 is the controlling single-writer decision. PR #223 was merged, but E2's later valid CLAIM on #281 made its merged panel row stale. The current single-writer follow-up is PR [#304](https://github.com/yeatu/obsidianGP/pull/304), exact HEAD `e2c23e99ddb69307cfa57bc168c991d0ddcccd18`, base `8605b84...`; it remains under fresh A review #305 and separate C3 decision #306. #229 remains GATED until #304 is A-accepted, separately C3-authorized and merged.
- After #304 merges, #229/E1 must re-read live main/#84 refs, perform a non-force/main-first sync with expected-old-HEAD, and preserve main's `PROJECT_TASKS.md` byte-for-byte; only the four benchmark workflow/README/runner/tests paths may remain in PR #84's diff. Stop on conflict in any technical path.
- Existing exact-head reproducibility evidence remains 42 cases, **40 pass / 2 fail**, 20/20 preflight, 14 diagnostics, zero explicit SourceRead mismatches, byte-identical JSON/Markdown reports. The two actual E2 quality failures remain `gq-010-number-plus-condition` and `gq-036-conflicting-versions`; no 42/42 claim, gate weakening, corpus edits or ranking changes.
- No PR #84 mutation is authorized before the follow-up panel A/C/merge gate. After panel merge, E1 must publish a valid CLAIM on #229 before branch mutation.

## 6. E1 cloud-index verifier — exact-main sync and exact-head CI complete; independent A pending

- [#240](https://github.com/yeatu/obsidianGP/issues/240) remains OPEN / implementation released but not C3-accepted. Cumulative PR [#293](https://github.com/yeatu/obsidianGP/pull/293) HEAD is `4e41d71e82dda45758ee0d8a99c63af852ddd6d6`; main `8605b84...` first parent / former HEAD `f876db4...` second. Actual merge-ref is `cb750b3a3696fb3a284df55b3123ed770f8d80d3`, tree `e51c237...`; direct compare is **52 ahead / 0 behind**, exactly five E1-owned verifier paths.
- Exact-head E1 #44470332333: 52 focused tests passed, full E1 regression 158 passed, CLI successful. Structural B/C #44470332402: 158 passed, CLI and fixture-only boundary checks successful. B1 #44470332259: 45 passed; unrelated E1 source API job path-filtered skipped and not counted as passing. These results were checked against the exact HEAD/merge-ref.
- E1 completed integration task [#298](https://github.com/yeatu/obsidianGP/issues/298) in RELEASE #7001502066. The fresh independent A review is [#307](https://github.com/yeatu/obsidianGP/issues/307), open and awaiting verdict. Historical A3 #294 covers only the old target.
- Predecessor verifier PRs #248/#271/#282 remain closed as superseded; their branches and histories are retained. #293 is the sole active cumulative verifier candidate. Separate C3 acceptance/merge gate is [#303](https://github.com/yeatu/obsidianGP/issues/303); it remains HOLD until #307 accepts exact refs. No merge, #136/#124 use or immutable_import VERIFIED/ACTIVE transition before fresh A and C3 acceptance. #40 remains C3 HOLD / force-released (#6969485194).
- Correction chain preserved: E3 RELEASE #6997423293 delivered F1–F4 in historical #271; #277/#282 delivered F-5/F-6; E1 #287/#293 fixed zero-width current/historical spans. A3 #294 accepted the full cumulative five-path tree on its historical exact target only.
- **E2 benchmark diagnosis/remediation:** A2 completed/released #279/#280. C3 decision #297 approves bounded tier-6 AND→OR fallback correction. E2 validly CLAIMED [#281](https://github.com/yeatu/obsidianGP/issues/281) in #7001141865; ref addenda #7001152432/#7001278874 bind exact scope to E2 `sfra_search/db.py`, `source/tests/test_search_index.py`, and documentation-only `source/README.md`. E2 branch `executor-2/issue-281-tier6-fallback-admission` has been fast-forwarded to current main `8605b84...` and advanced to HEAD `4627bde490a11a1249b39948744122ec55e16116`; direct compare is 3/0 and exactly the three approved E2 paths (README, `db.py`, focused tests). Implementation remains IN PROGRESS; no final exact-head CI/A/benchmark validation yet. Preserve exact/morphological AND, numeric matching and intentional single-token/partial fallback; no corpus, labels, metrics, reports or benchmark runner changes. Keep the 40/42 baseline and both gq-010/gq-036 failures visible. Lifecycle analysis #286 is CLOSED/RELEASED; #124 remains dependency-gated.
  1. **Outer↔inner source revision binding:** verifier accepts an E1-owned expected tagged revision and requires exact variant/value equality to the attestation for both Git and immutable-import cases.
  2. **Directory symlink race:** root and descendants are pinned/descriptor-relative with no-follow directory/file opens; deterministic replacement-race test proves no out-of-root open.
  3. **Bounded resource use:** enforce the #260 envelope incrementally, stream hashes, and do not retain non-Markdown payload bytes.
  4. **Historical node-version integrity:** validate same-document parents, types and ordered line/character/UTF-8 byte spans with adversarial digest-recomputed tests.
- Keep the five-file E1 ownership boundary and accepted #119 wire formats. Preserve E1 manifest v1, `verify_state_directory()`, `create_state_snapshot()`, legacy callers and workflows. No E3 imports/provider access or production data.
- C3 decision #260 approves the initial F-3 verifier-only envelope: attestation 2 MiB, inventory 64 MiB, 100,000 Markdown rows, 256 parser pairs, 500,000 total source-tree entries, 32 MiB per Markdown file, 2 GiB aggregate Markdown bytes, 4,096-character paths. Enforce with typed `resource_limit_exceeded`; larger bundles stay STAGED. This does not change #119 wire format or producer validity.

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

- #196 parent integration is RELEASED; child integration #296 remains E1 CLAIMED. Parent PR #170 is merged at `710d194...`; child PR #179 sync is complete at `d2939f8...`, but the dedicated exact-head writer fixture and a fresh A review remain outstanding. Old A3 #289 does not transfer; separate C3 child decision #295 remains HOLD.
- #120 is CLOSED / COMPLETED: E2 RELEASED, A1 REVIEW_ACCEPTED, C3 ACCEPTED, PR #250 merged to main at `372c1b8...`. The four materializer files are inherited main; no active resolver task remains.
- #240 remains OPEN / not C3-accepted. PR #293 contains the cumulative E1 implementation/corrections; A3 accepted its exact old target in #294. E1 owns post-main sync #298, then fresh CI/A and separate C3 acceptance. No downstream #136/#124 use, VERIFIED/ACTIVE promotion or immutable_import activation before those gates. #40 remains C3 HOLD / force-released (#6969485194); no MCP runtime scope.
- #229 remains gated by corrected panel PR #223 A/C/merge under #234; no parallel benchmark sync. Live current-main compare is 32 ahead / 149 behind.
- #124 remains gated by integrated writer child and A/C acceptance of #240; A3's lifecycle matrix #286 is complete but does not unblock implementation. #134/#136/#137/#138 remain gated by their explicit #240 and downstream dependencies.
- Panel review #292 is CLOSED / REVIEW_CHANGES_REQUESTED (#6998083046; RELEASE #6998091191). C3 reconciled the five findings on the sole panel branch and main-first synced it to `710d194...`; the replacement exact-head A request is linked in PR #223. No verdict transfers from #292.
- Branch history is preserved: no force-push, rebase/reset, delete or automatic cleanup. Any unexpected shared-file/contract conflict is a stop-and-escalate event.

## 10. Operational rule

Before each integration or acceptance, reread live main, branch/PR HEAD and base, ordered parents, compare diff, active CLAIM/RELEASE/BLOCKED events, exact merge-ref CI, dependency gates and supersession notes. A verdict is valid only for its exact refs. Main merge, branch-only propagation and production activation are separate permissions.
