# SFRA — оперативная панель проекта

> Краткая точка входа для участников. Источник истины по каждой задаче — её GitHub Issue и последние действующие события. Нормативный процесс — [Issue #20, Governance Protocol v2.4](https://github.com/yeatu/obsidianGP/issues/20). Панель не заменяет CLAIM, RELEASE, review, CI или решения C.

**Снимок проверен:** 2026-11-18
**Текущий main HEAD:** `8f1e427fe0e356eafb449c073c34923eb07dda71`  
**Последний кодовый baseline:** `8f1e427fe0e356eafb449c073c34923eb07dda71`  
**Изменение main после baseline:** W1 PR #92 принят C3 и влит в main; один разрешённый синтетический Issue round-trip #227 завершён. Текущий bundle/benchmark кодовый стек остаётся отдельным и не принят.

## 1. Целевая архитектура

**Web-путь:** ChatGPT Web / mobile → GitHub Issues → GitHub Actions → GitHub-hosted Runner → существующие SFRA services/core → ответ в исходном Issue → ChatGPT читает результат через GitHub integration.

- Личный компьютер владельца не является runtime-зависимостью и может быть выключен.
- GitHub-hosted Runner эфемерен; он не является постоянным хранилищем Vault, индекса, manifest, sidecar или request state.
- Используются существующие компоненты: E1 structural indexing/source API; E2 retrieval; E3/B1 Context Builder; V2.1 SearchVaultService / ReadSourceService; V2.2 non-production Issue Worker Core. Повторно реализовывать их не нужно.
- Data plane для будущего cloud execution: immutable snapshot bundles → exact-version identity/catalogue → read-only resolver/materializer. Сейчас это только provider-neutral synthetic implementation; provider, region, storage, import/sync policy и production activation не выбраны.
- Владелец разрешил публиковать содержимое Vault и производные source metadata в предназначенных для этого ответах. Не вводить blanket redaction. Credentials, tokens, keys, secrets и integrity controls остаются защищёнными. Logs/artifacts/errors сохраняют согласованную минимизацию.
- Публикация содержимого не означает автоматического разрешения production import/read/index/write, provider provisioning или snapshot activation.
- Ранее созданные реализации, тесты, схемы, документация, ветки, PR, commits и review trail сохраняются. Новая архитектура не является основанием удалять/переписывать их; возможное повторное использование — по отдельной границе.

## 2. Активная очередь и handoff

Таблица показывает навигацию и последнее проверенное состояние. Захват/владелец определяется только последним действующим CLAIM в конкретной Issue.

| Issue | Роль / владелец | Следующий результат | Зависимость / граница |
|---|---|---|---|
| [#215](https://github.com/yeatu/obsidianGP/issues/215) | E2 — RELEASED / historical handoff | Синхронизация integrated bundle PR #209 с тогдашним current main завершена | HEAD `4839d218...`, base `f665ae7...`, compare 24/0, пять путей; четыре workflow успешны. После W1 merge появился новый drift; см. #228/#231 |
| [#218](https://github.com/yeatu/obsidianGP/issues/218) | A2 — REVIEW_ACCEPTED / RELEASED | W1 exact-head audit принят; затем C3 принял и втащил PR #92 | HEAD `42cecfef...`; PR #92 merge `8f1e427...`; run #44397740749 SUCCESS, synthetic worker job SUCCESS; #227 COMPLETED, `source_reads: 0` |
| [#221](https://github.com/yeatu/obsidianGP/issues/221) | A2 — REVIEW_CHANGES_REQUESTED / RELEASED | Bundle exact-head review завершён с P1 finding | Старый PR #209 HEAD `4839d218...`; BLOB `raw_text` + NULL `content_hash` bypass выделен в #228. Verdict не переносится на исправленный стек |
| [#226](https://github.com/yeatu/obsidianGP/issues/226) | A — stale review target / supersession pending | Старый benchmark review target PR #84 | HEAD `64924c2...` / base `f665ae7...`; main теперь `8f1e427...`; сначала canonical sync task #229, затем новый A review |
| [#229](https://github.com/yeatu/obsidianGP/issues/229) | E — canonical integration task / OPEN | Синхронизировать benchmark PR #84 с main после W1 merge | Текущий main `8f1e427...`, PR #84 HEAD `64924c2...` / base `f665ae7...`, 32 ahead / 100 behind; сохранить пять benchmark путей и 2 failed gates; #230 закрыта как дубль |
| [#211](https://github.com/yeatu/obsidianGP/issues/211) | A2 — RELEASED / SUPERSEDED | Исторический stale review target без verdict | HEAD `edbbdff...` / base `553392...`; заменён актуальным #221. Не использовать как Gate A |
| [#208](https://github.com/yeatu/obsidianGP/issues/208) | C3 — active COORDINATOR_DECISION | Единый порядок исправления bundle-стека и writer hold | P1. #228 → exact CI + fresh A review → sync corrected #209 to current main → second A review → branch-only #209→#184→#162 → fresh parent review; только потом #196 |
| [#196](https://github.com/yeatu/obsidianGP/issues/196) | E1 — BLOCKED / CLAIM retained | Обновить writer PR #170/#179 только от окончательного accepted bundle parent | P1 conflict-prevention. Ни refs, ни handoff не менять до полного выполнения #208; четыре writer-owned paths сохраняются |
| [#204](https://github.com/yeatu/obsidianGP/issues/204) | E2 — implementation RELEASED / integrated pending | ZIP pre-decompression guard реализован в PR #209 | Проверяется только вместе с #162 + #184 + #228; bundle stack ещё не принят |
| [#228](https://github.com/yeatu/obsidianGP/issues/228) | E2 — CLAIMED / IN_PROGRESS | Fail-closed для SQLite BLOB `raw_text` и NULL `content_hash` | Child от точного PR #209 HEAD `4839d218...`; только E3 verifier + synthetic tests; затем CI и fresh A review |
| [#231](https://github.com/yeatu/obsidianGP/issues/231) | E — BLOCKED / queued integration | Синхронизировать corrected bundle child stack с main после #228 | Начинать только после RELEASE #228; current main `8f1e427...`; main-first non-force merge, четыре fixture workflow, fresh integrated A review |
| [#172](https://github.com/yeatu/obsidianGP/issues/172) | E2 — correction RELEASED; writer stack held | Завершённая writer correction в PR #179: full v2 identity binding + immutable version ID validation | PR #179 остаётся дочерней веткой PR #170. Не принимать writer до final bundle tree и fresh integrated review |
| [#206](https://github.com/yeatu/obsidianGP/issues/206) | A1 — REVIEW_ACCEPTED / RELEASED, historical target | Benchmark reproducibility review accepted only for its exact older target | PR #84 HEAD `c4cff0a...` / base `553392...`; 42 cases 40/42, two preserved failures. No verdict transfers to synced target #226 |
| [#156](https://github.com/yeatu/obsidianGP/issues/156) | E1 — RELEASED | Benchmark determinism correction завершена | PR #84; gold corpus v1.0.0 неизменен; #115 quality failures остаются. Current-main sync/reproducibility handoff #217 RELEASED |
| [#77](https://github.com/yeatu/obsidianGP/issues/77) | C3 — DONE / closed | W1 synthetic-only adapter принят, слит и проверен end-to-end | PR #92 merge `8f1e427...`; один owner-authored probe #227 завершён через GitHub-hosted worker; production read не включён |
| [#139](https://github.com/yeatu/obsidianGP/issues/139) | E3 — RELEASED / A disposition pending | W1 allowlist correction полностью входит в принятый PR #92 | PR #92 HEAD `42cecfef...` принят #218 и merged; по §8 A reviewer должен закрыть correction Issue, если scope целиком покрыт |
| [#119](https://github.com/yeatu/obsidianGP/issues/119) | E3 — implementation / acceptance pending | Принять integrated deterministic bundle builder/verifier | PR #162 + #184 + #209; обязательная последняя коррекция #228 и новый exact-head review/CI через #231 |
| [#125](https://github.com/yeatu/obsidianGP/issues/125) | E3 — RELEASED / writer acceptance pending | Завершить writer gate после bundle acceptance | PR #170 + #179; #196 удерживается до final bundle stack |
| [#120](https://github.com/yeatu/obsidianGP/issues/120) | E — queued / dependency-gated | Read-only exact-version resolver/materializer | После C acceptance #119; #118 уже принят |
| [#124](https://github.com/yeatu/obsidianGP/issues/124) | E — queued / dependency-gated | Cross-component lifecycle conformance | После принятия #117–#120 и #125; обязан соблюдать caller-enforced verification order из C3 addendum |
| [#132](https://github.com/yeatu/obsidianGP/issues/132) | A — analysis accepted; E implementation gated | Additive E1 cloud-index verifier | E1 implementation не открывать до принятия #119 и проверки #142/#131 gates |
| [#134](https://github.com/yeatu/obsidianGP/issues/134) | E — gated | B1 SnapshotIdentity v2 seam | После #117/#120 и E1 verifier |
| [#136](https://github.com/yeatu/obsidianGP/issues/136) | E — gated | Verified E3 cloud materialized handle | После #120/#134 и E1 verifier acceptance |
| [#137](https://github.com/yeatu/obsidianGP/issues/137) | E — gated | Additive V2.2 `sfra.issue.v2` request protocol | После #136; v1/TransportStatusV2 сохранить |
| [#138](https://github.com/yeatu/obsidianGP/issues/138) | E — gated | Synthetic V2.2 → B1 cloud query-path conformance | После #134/#136/#137 |
| [#145](https://github.com/yeatu/obsidianGP/issues/145) | C / owner decision pending | Canonical source, sync/staleness, workload, SLO, retention and budget | UNDECIDED; никаких производственных предположений |
| [#232](https://github.com/yeatu/obsidianGP/issues/232) | A — fresh REVIEW_REQUEST | Независимый review обновлённой панели PR #223 | Exact base `8f1e427...`, новый panel HEAD и единственный diff `PROJECT_TASKS.md`; #224 закрыта как stale target |

### Завершено / принято

- [#112](https://github.com/yeatu/obsidianGP/issues/112): C3 принял provider-neutral cloud data-plane direction; issue закрыта.
- [#117](https://github.com/yeatu/obsidianGP/issues/117) / [PR #127](https://github.com/yeatu/obsidianGP/pull/127): CloudSnapshotRef v2 accepted/merged.
- [#118](https://github.com/yeatu/obsidianGP/issues/118) / [PR #159](https://github.com/yeatu/obsidianGP/pull/159): A2 REVIEW_ACCEPTED #160; C3 acceptance; merge commit `bc36bf...`. Catalogue in-memory only.
- [#175](https://github.com/yeatu/obsidianGP/issues/175): A1 cross-component trace accepted by C3 and closed. Binding trust order recorded in #124.
- [#197](https://github.com/yeatu/obsidianGP/issues/197) / [PR #198](https://github.com/yeatu/obsidianGP/pull/198): A1 accepted docs-only correction of E1 indexer example; C3 accepted and PR merged. Current main includes `sfra-structural-indexer` example.
- [#218](https://github.com/yeatu/obsidianGP/issues/218): A2 accepted W1 PR #92 exact HEAD `42cecfef...`; C3 then accepted/merged it at `8f1e427...`. One-time synthetic probe [#227](https://github.com/yeatu/obsidianGP/issues/227) completed on Actions run [#44397740749](https://github.com/yeatu/obsidianGP/actions/runs/44397740749): `synthetic-issue-worker` SUCCESS, two synthetic nodes returned, `source_reads: 0`. Parent #77 closed completed; this did not activate production read_source.
- [#221](https://github.com/yeatu/obsidianGP/issues/221): A2 completed exact integrated bundle review with CHANGES_REQUESTED and RELEASED. The P1 BLOB/NULL finding is tracked in #228; old verdict is not an acceptance of the corrected tree.
- [#224](https://github.com/yeatu/obsidianGP/issues/224): stale dashboard review request released/closed after main advanced; no verdict was issued. It is superseded by fresh panel review #232 after the panel file update.
- [#229](https://github.com/yeatu/obsidianGP/issues/229): canonical benchmark branch sync after W1 merge. Duplicate #230 was closed with duplicate reason; all history retained.
- [#214](https://github.com/yeatu/obsidianGP/issues/214): W1 current-main sync RELEASED before final C gate. Exact A handoff #218 accepted; PR #92 then merged to main at `8f1e427fe0e356eafb449c073c34923eb07dda71`. Do not use the earlier `f665ae7...` base as current.
- [#203](https://github.com/yeatu/obsidianGP/issues/203): A1 accepted previous W1 tree only at HEAD `ff87c563...` / base `553392...`; historical verdict, not transferable to #218.
- [#217](https://github.com/yeatu/obsidianGP/issues/217): benchmark sync/repro evidence is valid only for PR #84 HEAD `64924c2...` / base `f665ae7...`. W1 merge moved main to `8f1e427...`; canonical re-sync #229 is now required before fresh A review.
- [#206](https://github.com/yeatu/obsidianGP/issues/206): A1 accepted benchmark reproducibility handoff only for historical PR #84 HEAD `c4cff0a...` / base `553392...`; no verdict transfers to later targets.
- [#210](https://github.com/yeatu/obsidianGP/issues/210): C3 duplicate docs task closed; canonical #197/#198 remains in history.
- [#212](https://github.com/yeatu/obsidianGP/issues/212) and [#216](https://github.com/yeatu/obsidianGP/issues/216): duplicate sync tasks closed in favour of canonical #214 and #215, respectively.

## 3. Exact PR and branch state

| PR | Current state / exact target | Gate |
|---|---|---|
| [#92 — W1 Web adapter](https://github.com/yeatu/obsidianGP/pull/92) | MERGED. Reviewed HEAD `42cecfef...`; merge commit `8f1e427...` | C3 accepted after A2 #218. One synthetic-only Issue #227 round-trip succeeded; no production read path |
| [#209 — integrated bundle #162/#184/#204 + #228 child correction pending](https://github.com/yeatu/obsidianGP/pull/209) | OPEN / Draft. HEAD `4839d218...`; was 24/0 vs old main `f665ae7...`, now 24 ahead / 100 behind main `8f1e427...`; historical five-path delta | #228 correction is in progress on child branch. #231 handles current-main sync after correction; no branch propagation or main merge yet |
| [#162 — bundle parent](https://github.com/yeatu/obsidianGP/pull/162) | OPEN / unmerged. Feature HEAD `c5f84cd...` | Preserve until #208 branch-only propagation after Gate A |
| [#184 — accepted key correction](https://github.com/yeatu/obsidianGP/pull/184) | OPEN / Draft / stacked on #162. HEAD `8169827...` | Correction branch preserved; branch-only merge under #208 only |
| [#170 — immutable writer](https://github.com/yeatu/obsidianGP/pull/170) | OPEN / unmerged / partial parent refresh. HEAD `b0bcf7a...`, four writer-owned files | Hold under #196 until final bundle acceptance |
| [#179 — writer integrity correction](https://github.com/yeatu/obsidianGP/pull/179) | OPEN / unmerged / child of #170. HEAD `035a79d...`, four writer correction files | Hold under #196; no verdict transfers after parent refresh |
| [#84 — gold benchmark](https://github.com/yeatu/obsidianGP/pull/84) | OPEN / Draft. HEAD `64924c2...` / old base `f665ae7...`; now 32 ahead / 100 behind main `8f1e427...`; five historical benchmark-owned paths | #229 is the canonical re-sync task. Preserve gq-010/gq-036 as failures; fresh exact-head A review only after two post-sync byte-identical reports |
| [#223 — SFRA governance panel](https://github.com/yeatu/obsidianGP/pull/223) | OPEN. Branch currently includes main `8f1e427...`; pre-update HEAD `ff28dc5...`, direct compare 6 ahead / 0 behind, `PROJECT_TASKS.md` only | C3 updates the single dashboard file with post-merge W1, #227, #228, #229 and review states; fresh A review #232 before any merge |
| [#198 — v2 docs correction](https://github.com/yeatu/obsidianGP/pull/198) | MERGED | Merge contains only accepted `CLOUD_SNAPSHOT_V2.md` docs correction |
| [#176 — prior project panel](https://github.com/yeatu/obsidianGP/pull/176) | CLOSED / superseded | History preserved; fresh panel branch is based on current main |

**PR #209 exact metadata:** current base/main `f665ae7...`, exact HEAD `4839d218...`, direct compare 24 ahead / 0 behind with five unique bundle-owned paths; Actions merge-ref `441bb826...` has current main as first parent and PR HEAD as second. REST base metadata is aligned.

## 4. Bundle and writer gate order

1. PR #209 historical integrated bundle tree contains #173/#184 key parity and #204 pre-decompression admission. A2's exact review #221 returned CHANGES_REQUESTED because active SQLite BLOB `raw_text` with NULL `content_hash` could pass via `None == None`. The new P1 correction is #228, owned by E2, child of exact #209 HEAD `4839d218...`.
2. Current main is `8f1e427fe0e356eafb449c073c34923eb07dda71`, including the accepted W1 merge. #209 still targets old base `f665ae7...`; its current-main comparison is 24 ahead / 100 behind. Do not integrate the old #209 tree or writer branches as-is.
3. Canonical correction/integration sequence from C3 decision #208:
   - E2 completes #228 with a disposable SQLite BLOB + NULL regression through the public bundle verification API.
   - Exact child fixture and applicable cross-layer CI; fresh independent A review of the complete #162/#184/#204/#228 child stack.
   - After A acceptance, C3 performs the expected-old-HEAD, non-force branch-only merge of the accepted #228 child into #209's feature branch.
   - Sync the corrected #209 branch to current main with main as first parent and corrected #209 HEAD second; rerun bundle/C1/V2.1/V2.2 workflows on one exact merge-ref and open a fresh integrated A review.
   - Only after this new A acceptance and a fresh C live-ref check: merge updated #209 → #184, then updated #184 → #162 as feature-branch-only two-parent merges. Run post-integration fixtures and open a fresh A review for final #162.
   - Only then may #196 refresh #170 and #179, preserving four-file writer ownership boundaries and requiring fresh writer CI/A review.
4. #231 is the queued current-main integration handoff for the corrected bundle stack. It remains blocked until #228 is RELEASED with PR and exact-child evidence. #196 remains blocked throughout.
5. Historical fixture evidence remains valid only for its recorded old refs: #209 merge-ref `441bb826...` had bundle 58; C1 183 + 42 E1-only skips; V2.1 19; V2.2 55. It is not acceptance of #228 or the current-main corrected target.

## 5. Security and unresolved design decisions

- **Catalogue trust order:** #118 `stage()` produces STAGED only. `mark_verified(snapshot_id)` is caller-enforced; the orchestrator must call it only after successful public bundle verification and the required E1 cloud-index verification for the same immutable snapshot.
- **Immutable imports:** never coerce an `immutable_import` identity into a Git SHA. Until the additive E1 cloud verifier from #132/#142 is implemented, independently reviewed and C-accepted, such a candidate cannot progress beyond STAGED.
- **Verification failure:** do not call `mark_verified()`; activation must fail without changing the previous ACTIVE pointer/generation.
- **Legacy workflow:** preserve it unchanged; do not dispatch or rerun it. It is not the new data plane.
- **Production:** no provider, credentials, real Vault/SQLite/sidecar/`sfra-state`, ingestion, production source reads/writes, snapshot activation or worker rollout authorized by synthetic fixture acceptance.
- **Source authority and SLO:** #145 remains UNDECIDED. #154 proves only a metadata-only tracked remote subtree identity, not completeness of local/offline Vault or canonical source authority.
- **Benchmark:** gold corpus v1.0.0 remains pinned (42 cases / 32 docs / 69 nodes). PR #84 has two preserved E2 forbidden-node failures: gq-010 and gq-036. Current report evidence is 40/42, 14 status diagnostics, 0 explicit SourceRead mismatches. Do not weaken gates or relabel failures as passing.
- **Web worker:** PR #92 was merged after A2 #218 and C3 acceptance. One-time synthetic Issue #227 completed via Actions run #44397740749; worker job succeeded, returned exactly the approved synthetic nodes and `source_reads: 0`. This is not production read activation.

## 6. Parallelism / conflict rules

- #218 A2 review accepted W1 PR #92 at exact HEAD `42cecfef...`; C3 then merged PR #92 at `8f1e427...` and completed the one-time synthetic Issue #227 probe.
- #221 A2 review is closed/released with CHANGES_REQUESTED on old bundle HEAD `4839d218...`; P1 correction #228 is now the active E2 task. Do not edit bundle-owned files in parallel.
- #228 E2 owns the non-text `raw_text` / NULL hash correction; #231 is the sole queued current-main sync handoff after #228. Old #221 evidence remains historical.
- #208 remains the single C3 authority for corrected bundle branch propagation and writer hold; #225 remains normative for caller-enforced verification before catalogue `mark_verified()`.
- #196 writer refresh stays blocked; preserve #170/#179 refs and their existing four-path partial deltas.
- #226 review target is stale after main advanced; #229 is the single canonical benchmark re-sync task. #230 was closed as duplicate. Keep gq-010/gq-036 failed.
- #224 is closed/released as stale after main advanced; refreshed dashboard review is #232. C3's PR #223 remains one-file-only.
- #139's W1 correction is included in the accepted/merged PR #92 tree; A2 should close it under Governance Protocol §8 if the exact #218 review fully covers its scope.
- Use a single task per owned file/branch. If main or a parent stack advances, use one canonical sync task and replace stale exact-head review only after the new target is recorded.
- Preserve all branches, PRs, commits and historical reviews. No force-push, rebase, reset or cleanup based only on changed architecture.

## 7. Operational rule

Before any claim, review, acceptance or integration decision, verify live issue events, current main, PR head/base, ordered parents, direct compare/file list, actual Actions merge-ref and job logs. A verdict is valid only for its exact HEAD/base. Merge is always a separate C decision after required independent A acceptance.
