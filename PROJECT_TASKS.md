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
| [#196](https://github.com/yeatu/obsidianGP/issues/196) | **E1 CLAIMED / IMPLEMENTATION COMPLETE — RELEASE pending** | Branch sync, parent/child writer fixtures and cross-layer CI complete; hand off cumulative writer stack for integrated A review | **P1**; #170 `5612a705...` (main 10/0, 4 paths; fixture 18 passed); #179 `85126e33...` (main 21/0, merge-ref `de621bb...`, same 4 unique paths; fixture 27 passed); C1/V2.1/V2.2 green on both; inherited #119 bundle suite accepted (62 passed, exact tree on main). E1 formal RELEASE + fresh integrated A review remain
| [#120](https://github.com/yeatu/obsidianGP/issues/120) | **E2 RELEASED / A1 CLAIMED exact-head review #258** | Exact-version resolver/materializer complete; independent acceptance is in progress | **P2**; PR #250 HEAD `52570ceb...`, main 7/0, 4 E2-owned paths; merge-ref `5eec2db...` (main first / exact PR HEAD second); dedicated materializer #44425962091 and push #44425953403 both SUCCESS, 13 passed; C1 #44425962139, V2.1 #44425962000, V2.2 #44425962021 all SUCCESS (59 E1-dependent partial-layer skips disclosed); E2 RELEASE #6995419580; A1 CLAIM #6995407153 on #258. PR remains Draft/open/unmerged pending A verdict and separate C decision |
| [#240](https://github.com/yeatu/obsidianGP/issues/240) | **E4 CLAIMED / REVIEW_CHANGES_REQUESTED; correction #257 open** | Исправить четыре P1 finding A1 в additive E1 cloud-index verifier, затем повторить exact-head CI и новый независимый A review | **P1**; PR #248 HEAD `1cb300d...`, main 27/0, 5 E1-owned paths; CI #44423746094/#44423753534/#44423753470/#44423753510 all SUCCESS on reviewed HEAD. A1 #255 returned CHANGES_REQUESTED: outer↔inner revision binding, directory symlink race, unbounded tree/payload, historical node-version parents/spans. Correction #257 is open; no merge or downstream use
| [#229](https://github.com/yeatu/obsidianGP/issues/229) | **E — GATED / unclaimed** | Synchronize benchmark PR #84 only after panel PR #223 is independently accepted, separately C-accepted and merged | **P1**; #234 single-writer rule. Current main→#84: 32 ahead / 128 behind from merge base `f665ae7...`; 4 benchmark technical paths + stale `PROJECT_TASKS.md` handoff hunk. No #84 mutation before panel merge; then preserve main panel verbatim and keep `gq-010`/`gq-036` failed
| [#42](https://github.com/yeatu/obsidianGP/issues/42) | E1 benchmark / quality gate | Сохранить воспроизводимый baseline и две видимые E2 retrieval failure | **P1**; gq-010 и gq-036 остаются failed; не менять corpus/метрики/ranking для зелёного отчёта |
| [#125](https://github.com/yeatu/obsidianGP/issues/125) | E3 implementation / writer stack | Закончить writer после #196, получить независимый review и C acceptance | PR #170/#179 остаются open/unmerged; старые #171/#180 verdicts не переносятся на новые HEAD |
| [#124](https://github.com/yeatu/obsidianGP/issues/124) | E — dependency-gated | Synthetic lifecycle conformance: prepare → write → stage → verify → activate → exact resolve | После принятия #120, #125 и E1 verifier #240; trust-order assertions обязательны |
| [#134](https://github.com/yeatu/obsidianGP/issues/134) | E — gated | B1 SnapshotIdentity protocol v2 | После #120 и A/C acceptance #240; не является proof of verification |
| [#136](https://github.com/yeatu/obsidianGP/issues/136) | E — gated | E3 factory-verified cloud materialized binding | После #120/#134 и принятия #240 |
| [#137](https://github.com/yeatu/obsidianGP/issues/137) | E — gated | Additive V2.2 `sfra.issue.v2` protocol | После #136; v1/TransportStatusV2 сохранить |
| [#138](https://github.com/yeatu/obsidianGP/issues/138) | E — gated | Synthetic V2.2 → V2.1 → E3/E1/E2 → B1 query conformance | После #134/#136/#137 |

### Конфликтующие и завершённые handoff’ы

- [#119](https://github.com/yeatu/obsidianGP/issues/119) — CLOSED / C3 accepted. Полный synthetic bundle builder/verifier и corrections #173/#204/#228 merged в main через PR #162.
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

## 4. Writer stack — P1 conflict resolution

- PR #170 HEAD: `5612a70520c91efcb9d4ccdd955f207c63bef641`, base main `8d1d3c9...`; compare **10 ahead / 0 behind**, exactly four writer-owned paths. Guarded sync commit `123de377...` has current main first / prior writer HEAD `b0bcf7...` second; the subsequent documentation baseline note is `5612a705...`.
- PR #179 cumulative HEAD: `85126e3301e127b125d2ed4b8a554f0cdb32d15a`, base main; merge-ref `de621bb325446cc25193b29b7cbeb723c2a1d88c`, main first / exact child HEAD second. Parent #170 → child compare **11 ahead / 0 behind**; main → child **21 ahead / 0 behind**. The combined diff is exactly **four unique paths**; parent and correction deltas both touch the same writer workflow/docs/module/tests.
- Exact writer fixtures: parent #44420253244 SUCCESS, **18 passed** on HEAD `5612a7...`; child #44420909911 SUCCESS, **27 passed** on HEAD `85126e...`.
- Cross-layer parent runs #44420262234/#44420262255/#44420262274 (C1/V2.1/V2.2) all SUCCESS; child runs #44420917905/#44420917898/#44420918378 all SUCCESS on final merge-ref `de621bb...`. Parent and child E1-dependent skips (57 / 59) are disclosed and not counted as passes.
- C3 accepted inherited bundle coverage in #196 comment #6994996868: bundle run #44414369510 SUCCESS, **62 passed / zero skips**, accepted tree `7b516530...`; this is identical to current main's tree. No bundle path changes in writer diff, so no duplicate bundle workflow run or workflow_dispatch is required.
- **Current state:** all writer branch sync, writer-specific fixtures and cross-layer suites are complete. #196 remains E1-CLAIMED pending E1's formal implementation-complete RELEASE and one fresh integrated independent A review of the cumulative #170/#179 stack. Keep both PRs open/unmerged until A acceptance and a separate C integration decision.
- Historical A2 #171 / A1 #180 verdicts apply only to earlier exact heads. No provider, credentials, upload, catalogue activation, real data, workflow_dispatch or production operation is authorized.

## 5. Benchmark — P1 shared-file conflict remains

PR #84 remains open/Draft at HEAD `64924c204f006bf9d41a42ca0724d8e026325014`. The live compare from current main `8d1d3c937abf1e6f651d077c409d1b3dfad1a9cb` is **diverged: 32 ahead / 128 behind**, merge base `f665ae7251387ee86b3f5adb48662b79406f392b`. Its effective current-main diff is five paths: four benchmark technical paths and one stale `PROJECT_TASKS.md` #156 handoff hunk.

- #234 is the controlling single-writer decision: PR #223 alone owns root `PROJECT_TASKS.md`. #229 remains GATED until this panel receives a fresh independent A acceptance, C3 records a separate merge decision and PR #223 is merged.
- After that merge, #229 must re-read live main/#84 refs, perform a non-force/main-first sync and preserve main's `PROJECT_TASKS.md` byte-for-byte; only the four benchmark workflow/README/runner/tests paths may remain in the PR diff. Stop on conflicts in those four technical files.
- Existing exact-head reproducibility evidence remains 42 cases, **40 pass / 2 fail**, 20/20 preflight, 14 diagnostics, zero explicit SourceRead mismatches, byte-identical JSON/Markdown reports. The two actual E2 quality failures remain `gq-010-number-plus-condition` and `gq-036-conflicting-versions`; no 42/42 claim, gate weakening, corpus edits or ranking changes.
- No parallel benchmark sync or PR #84 mutation is authorized before the panel A/C/merge gate.

## 6. E1 cloud-index verifier — P1 trust prerequisite #240

- [#240](https://github.com/yeatu/obsidianGP/issues/240) is the sole E1-owned additive verifier implementation. E4 owns the parent task. PR [#248](https://github.com/yeatu/obsidianGP/pull/248) was reviewed by A1 at exact HEAD `1cb300dce839173261ea3f38963bb1e20422b04a`, main base `8d1d3c9...`, merge-ref `b4a7a1e...`, 27 ahead / 0 behind, five E1-owned paths. The four exact-head workflows #44423746094/#44423753534/#44423753470/#44423753510 all succeeded.
- A1 returned `REVIEW_CHANGES_REQUESTED` in #255 comment #6995243544 and RELEASED review #255 in #6995247033. The review found four blocking P1 gaps; correction [#257](https://github.com/yeatu/obsidianGP/issues/257) is open and must be completed before any new A review or C acceptance:
  1. **Outer↔inner source revision binding:** verifier must accept an E1-owned expected tagged revision and require exact variant/value equality to attestation for both Git and immutable-import cases.
  2. **Directory symlink race:** root and descendants must be pinned/descriptor-relative with no-follow directory/file opens; add a deterministic directory replacement race test proving no out-of-root file is opened.
  3. **Unbounded resource use:** set documented limits for attestation/inventory/parser/path/tree work; stream hashes and do not retain non-Markdown payload bytes; add exact-boundary and over-limit tests.
  4. **Historical node-version integrity:** independently validate historical same-document parent links, node type and ordered line/character/UTF-8 byte spans; add tamper tests with recomputed DB digest.
- Keep the five-file E1 ownership boundary and accepted #119 wire formats. Preserve E1 manifest v1, `verify_state_directory()`, `create_state_snapshot()`, legacy callers and workflows. No E3 imports/provider access or production data.
- C3 decision [#260](https://github.com/yeatu/obsidianGP/issues/260) approves the initial F-3 verifier-only execution envelope: attestation 2 MiB, inventory 64 MiB, 100,000 Markdown rows, 256 parser pairs, 500,000 total source-tree entries, 32 MiB per Markdown file, 2 GiB aggregate Markdown bytes, and 4,096-character paths. Enforce incrementally with streaming/no-follow traversal and typed `resource_limit_exceeded`; bundles outside the E1 execution envelope remain STAGED. This does not change #119 wire format or producer validity.
- A fresh exact-head A review will be required after #257 is accepted and its new PR/CI target is established. C3 acceptance remains mandatory before #136/#124 or immutable-import verification can consume this report.

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

- #196 writer handoff is implementation-complete at exact refs and waits for E1 RELEASE + fresh integrated A review.
- #120 implementation is RELEASED by E2 and is under independent A1 review #258 at exact HEAD `52570ceb...` / merge-ref `5eec2db...`; dedicated 13-test E1-installed suites, C1, V2.1 and V2.2 all pass. PR #250 remains Draft/open/unmerged pending A verdict and separate C acceptance; #254 STAGED-only verification path is implemented.
- #240 remains E4-owned through PR #248, but A1 returned REVIEW_CHANGES_REQUESTED in #255; correction #257 is the active P1 work, with numeric F-3 limits approved in C3 decision #260. No fresh A review or downstream #136/#124 use until F-1–F-4 are closed.
- #120 and #240 remain parallel but their file/API boundaries must stay separate; #120 supplies exact bytes and a verification-only materialization, while #240 verifies it without E3 imports or object-store access.
- #229 remains gated by panel PR #223 A/C/merge under #234; no parallel benchmark sync.
- #124 remains gated by #120, #125 and A/C acceptance of #240.
- #134/#136/#137/#138 remain gated by the explicit dependency chain in their Issues.
- Earlier panel reviews #233/#238 returned CHANGES_REQUESTED on older targets; #244 was RELEASED by A1 without verdict after HEAD drift; #245 was closed before CLAIM because writer refs advanced. No verdict transfers. The next panel review must be opened only after the writer ref/evidence snapshot is stable.
- Branch history is preserved: no force-push, rebase/reset, delete or automatic cleanup. Any unexpected shared-file/contract conflict is a stop-and-escalate event.

## 10. Operational rule

Before each integration or acceptance, reread live main, branch/PR HEAD and base, ordered parents, compare diff, active CLAIM/RELEASE/BLOCKED events, exact merge-ref CI, dependency gates and supersession notes. A verdict is valid only for its exact refs. Main merge, branch-only propagation and production activation are separate permissions.
