# SFRA — оперативная панель проекта

> Краткая точка входа для участников. Источник истины по каждой задаче — её GitHub Issue и последние действующие события. Нормативный процесс — [Issue #20, Governance Protocol v2.4](https://github.com/yeatu/obsidianGP/issues/20). Панель не заменяет CLAIM, RELEASE, review, CI или решения C.

**Снимок:** 2026-11-18  
**Текущий main HEAD:** `f665ae7251387ee86b3f5adb48662b79406f392b`  
**Последний кодовый baseline:** `553392dbbe9d3782683593bb92b88ac3ad6d9721`  
**Изменение main после baseline:** два коммита с принятым документационным исправлением `CLOUD_SNAPSHOT_V2.md` (#197/#198); кодовые компоненты не менялись.

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
| [#215](https://github.com/yeatu/obsidianGP/issues/215) | E2 — CLAIMED / sync + CI complete; handoff pending | Завершить PR/Issue evidence, открыть fresh integrated A review, RELEASE #215 | P1. PR #209 HEAD `4839d218...`; current main `f665ae7...`; 24/0, five paths; four fixture workflows green on merge-ref `441bb826...`. A2 claim #211 is stale and RELEASE requested |
| [#218](https://github.com/yeatu/obsidianGP/issues/218) | A — свободный REVIEW_REQUEST | Независимый exact-head audit W1 PR #92 | HEAD `42cecfef...` / base `f665ae7...`; 14 W1 files; run #44393224276: 65 passed, worker skipped |
| [#211](https://github.com/yeatu/obsidianGP/issues/211) | A2 — stale CLAIM, RELEASE requested | Освободить устаревший review target без verdict | HEAD `edbbdff...` / base `553392...`; его заменит integrated review после #215. Не использовать как Gate A |
| [#208](https://github.com/yeatu/obsidianGP/issues/208) | C3 — active COORDINATOR_DECISION | Условно разрешить branch-only propagation #204 → #184 → #162 после A acceptance | P1. Gate A: exact CI + независимое A принятие полного стека. Gate B: non-force parent-preserving merges. Gate C: только потом writer refresh #196 |
| [#196](https://github.com/yeatu/obsidianGP/issues/196) | E — blocked / waiting #208 | Обновить writer PR #170/#179 на окончательный принятый bundle parent; fresh integrated writer review | P1 conflict-prevention. Не выполнять до завершения #208 Gate A/B; предыдущие writer reviews относятся только к старым refs |
| [#204](https://github.com/yeatu/obsidianGP/issues/204) | E2 — correction implementation in PR #209 | Guard до ZIP decompression; implementation и CI handoff завершены, integration evidence ведётся в #215 | Проверять только вместе с #162 + #184; no main merge |
| [#172](https://github.com/yeatu/obsidianGP/issues/172) | E2 — correction RELEASED; writer stack held | Завершённая writer correction в PR #179: full v2 identity binding + immutable version ID validation | PR #179 остаётся дочерней веткой PR #170. Не принимать writer до final bundle tree и fresh integrated review |
| [#206](https://github.com/yeatu/obsidianGP/issues/206) | A1 — REVIEW_ACCEPTED / RELEASED, historical target | Benchmark reproducibility review accepted only for its exact older target | PR #84 HEAD `c4cff0a...` / base `553392...`; 42 cases 40/42, two preserved failures; reports byte-identical. Current synced target is tracked by #217 |
| [#156](https://github.com/yeatu/obsidianGP/issues/156) | E1 — RELEASED | Benchmark determinism correction завершена | PR #84; gold corpus v1.0.0 неизменен; #115 quality failures остаются. Current-main refresh/provenance is a separate #217 handoff |
| [#77](https://github.com/yeatu/obsidianGP/issues/77) | P1 — W1 parent | После A review #218 — отдельное C acceptance/merge decision; затем одна отмеченная synthetic event round-trip | PR #92 открыт/unmerged. Round-trip ещё не выполнялся; worker остаётся dormant |
| [#119](https://github.com/yeatu/obsidianGP/issues/119) | E3 — RELEASED / acceptance pending | Принять integrated deterministic bundle builder/verifier | PR #162 + #184 + #209; новый integrated A review появится после #215 |
| [#125](https://github.com/yeatu/obsidianGP/issues/125) | E3 — RELEASED / writer acceptance pending | Завершить writer gate после bundle acceptance | PR #170 + #179; #196 удерживается до final bundle stack |
| [#120](https://github.com/yeatu/obsidianGP/issues/120) | E — queued / dependency-gated | Read-only exact-version resolver/materializer | После C acceptance #119; #118 уже принят |
| [#124](https://github.com/yeatu/obsidianGP/issues/124) | E — queued / dependency-gated | Cross-component lifecycle conformance | После принятия #117–#120 и #125; обязан соблюдать caller-enforced verification order из C3 addendum |
| [#132](https://github.com/yeatu/obsidianGP/issues/132) | A — analysis accepted; E implementation gated | Additive E1 cloud-index verifier | E1 implementation не открывать до принятия #119 и проверки #142/#131 gates |
| [#134](https://github.com/yeatu/obsidianGP/issues/134) | E — gated | B1 SnapshotIdentity v2 seam | После #117/#120 и E1 verifier |
| [#136](https://github.com/yeatu/obsidianGP/issues/136) | E — gated | Verified E3 cloud materialized handle | После #120/#134 и E1 verifier acceptance |
| [#137](https://github.com/yeatu/obsidianGP/issues/137) | E — gated | Additive V2.2 `sfra.issue.v2` request protocol | После #136; v1/TransportStatusV2 сохранить |
| [#138](https://github.com/yeatu/obsidianGP/issues/138) | E — gated | Synthetic V2.2 → B1 cloud query-path conformance | После #134/#136/#137 |
| [#145](https://github.com/yeatu/obsidianGP/issues/145) | C / owner decision pending | Canonical source, sync/staleness, workload, SLO, retention and budget | UNDECIDED; никаких производственных предположений |

### Завершено / принято

- [#112](https://github.com/yeatu/obsidianGP/issues/112): C3 принял provider-neutral cloud data-plane direction; issue закрыта.
- [#117](https://github.com/yeatu/obsidianGP/issues/117) / [PR #127](https://github.com/yeatu/obsidianGP/pull/127): CloudSnapshotRef v2 accepted/merged.
- [#118](https://github.com/yeatu/obsidianGP/issues/118) / [PR #159](https://github.com/yeatu/obsidianGP/pull/159): A2 REVIEW_ACCEPTED #160; C3 acceptance; merge commit `bc36bf...`. Catalogue in-memory only.
- [#175](https://github.com/yeatu/obsidianGP/issues/175): A1 cross-component trace accepted by C3 and closed. Binding trust order recorded in #124.
- [#197](https://github.com/yeatu/obsidianGP/issues/197) / [PR #198](https://github.com/yeatu/obsidianGP/pull/198): A1 accepted docs-only correction of E1 indexer example; C3 accepted and PR merged. Current main includes `sfra-structural-indexer` example.
- [#214](https://github.com/yeatu/obsidianGP/issues/214): W1 main sync RELEASED by E2. PR #92 current HEAD `42cecfef...`, base main `f665ae7...`, 99 ahead / 0 behind, exactly 14 W1 files; fixture run #44393224276: 65 passed, worker skipped. Fresh review #218 open. PR #92 remains unmerged.
- [#203](https://github.com/yeatu/obsidianGP/issues/203): A1 accepted previous W1 tree only at HEAD `ff87c563...` / base `553392...`; historical verdict, not transferable to #218.
- [#217](https://github.com/yeatu/obsidianGP/issues/217): E2-CLAIMED benchmark current-main sync. PR #84 is now HEAD `64924c2...` / base `f665ae7...`; run #44395073244 produced two artifacts and the expected 40/42 result; report byte-comparison and fresh A handoff remain open.
- [#206](https://github.com/yeatu/obsidianGP/issues/206): A1 accepted benchmark reproducibility handoff for exact PR #84 HEAD `c4cff0a...` / base `553392...`. Acceptance covers deterministic evidence only, not 42/42 quality or main merge.
- [#210](https://github.com/yeatu/obsidianGP/issues/210): C3 duplicate docs task closed; canonical #197/#198 remains in history.
- [#212](https://github.com/yeatu/obsidianGP/issues/212) and [#216](https://github.com/yeatu/obsidianGP/issues/216): duplicate sync tasks closed in favour of canonical #214 and #215, respectively.

## 3. Exact PR and branch state

| PR | Current state / exact target | Gate |
|---|---|---|
| [#92 — W1 Web adapter](https://github.com/yeatu/obsidianGP/pull/92) | OPEN / non-Draft. HEAD `42cecfef...`, base `f665ae7...`; direct compare 99/0; 14 W1 paths | A review #218, then C acceptance. Do not merge or run worker/round-trip before C gate |
| [#209 — integrated bundle #162/#184/#204](https://github.com/yeatu/obsidianGP/pull/209) | OPEN / Draft. HEAD `4839d218...`; direct current-main compare `f665ae7...` → HEAD: 24/0, exactly five bundle paths; merge-ref `441bb826...` | #215 E2-CLAIMED; all four exact workflows green (bundle 58; C1 183/42 skips; V2.1 19; V2.2 55). Fresh A review handoff pending, then C3 #208 Gate A |
| [#162 — bundle parent](https://github.com/yeatu/obsidianGP/pull/162) | OPEN / unmerged. Feature HEAD `c5f84cd...` | Preserve until #208 branch-only propagation after Gate A |
| [#184 — accepted key correction](https://github.com/yeatu/obsidianGP/pull/184) | OPEN / Draft / stacked on #162. HEAD `8169827...` | Correction branch preserved; branch-only merge under #208 only |
| [#170 — immutable writer](https://github.com/yeatu/obsidianGP/pull/170) | OPEN / unmerged / partial parent refresh. HEAD `b0bcf7a...`, four writer-owned files | Hold under #196 until final bundle acceptance |
| [#179 — writer integrity correction](https://github.com/yeatu/obsidianGP/pull/179) | OPEN / unmerged / child of #170. HEAD `035a79d...`, four writer correction files | Hold under #196; no verdict transfers after parent refresh |
| [#84 — gold benchmark](https://github.com/yeatu/obsidianGP/pull/84) | OPEN / Draft. Synced HEAD `64924c2...` / base `f665ae7...`; 32 ahead / 0 behind; five benchmark-owned paths | #217 E2-CLAIMED. Run #44395073244: preflight 20/20; full 42 cases, 40 pass / 2 fail; artifacts for both attempts #14469634537/#14471780183. JSON/MD byte comparison and fresh A review pending. gq-010/gq-036 remain failed |
| [#198 — v2 docs correction](https://github.com/yeatu/obsidianGP/pull/198) | MERGED | Merge contains only accepted `CLOUD_SNAPSHOT_V2.md` docs correction |
| [#176 — prior project panel](https://github.com/yeatu/obsidianGP/pull/176) | CLOSED / superseded | History preserved; fresh panel branch is based on current main |

**Metadata caveat:** PR #209 REST summary still reports base SHA `553392...` and six files. The direct Git compare against current main `f665ae7...` and the exact Actions merge-ref show the effective current tree is 24 ahead / 0 behind with five unique bundle-owned paths. Review handoff must state both the metadata discrepancy and the exact two-parent checkout evidence.

## 4. Bundle and writer gate order

1. PR #209 integrated bundle candidate has the pre-decompression guard: only `ZIP_STORED`; `compress_size == file_size` checked before `ZipFile.read()`. Tests use DEFLATED/BZIP2/LZMA traps, malformed stored size and a positive stored archive.
2. Exact current-main merge-ref for PR #209: `441bb826c407e4f10e86964a658db041141ac4dc`; parents `f665ae7...` then `4839d218...`.
3. Exact Actions runs on that merge-ref:
   - Bundle #44394269474: **58 passed** (E1 installed; full bundle suite).
   - C1 #44394269412: B1 **45 passed**; E3/C1 **183 passed / 42 skipped** (E1-only cases skipped because package absent).
   - V2.1 #44394269344: B1 **45**, E3/C1 **183 / 42 skipped**, V2.1 **19 passed**.
   - V2.2 #44394269281: B1 **45**, E3/C1 **183 / 42 skipped**, V2.1 **19**, V2.2 **55 passed**.
   All four succeeded on the same merge-ref. Partial cross-layer skips are not substituted for E1 coverage; the dedicated bundle workflow executes all E1-dependent tests.
4. A2 still holds stale claim #211 for old HEAD `edbbdff...` / base `553392...`. C3 requested RELEASE as superseded; no verdict may be transferred. New integrated A review must be opened after E2 completes #215.
5. Only after fresh integrated A acceptance and C3 recheck may #208 authorize branch-only sequence #204 → #184 → #162, preserving every branch history. This is not a main merge.
6. Only after final bundle stack acceptance may #196 refresh #170 then #179 and request fresh integrated writer A review.

## 5. Security and unresolved design decisions

- **Catalogue trust order:** #118 `stage()` produces STAGED only. `mark_verified(snapshot_id)` is caller-enforced; the orchestrator must call it only after successful public bundle verification and the required E1 cloud-index verification for the same immutable snapshot.
- **Immutable imports:** never coerce an `immutable_import` identity into a Git SHA. Until the additive E1 cloud verifier from #132/#142 is implemented, independently reviewed and C-accepted, such a candidate cannot progress beyond STAGED.
- **Verification failure:** do not call `mark_verified()`; activation must fail without changing the previous ACTIVE pointer/generation.
- **Legacy workflow:** preserve it unchanged; do not dispatch or rerun it. It is not the new data plane.
- **Production:** no provider, credentials, real Vault/SQLite/sidecar/`sfra-state`, ingestion, production source reads/writes, snapshot activation or worker rollout authorized by synthetic fixture acceptance.
- **Source authority and SLO:** #145 remains UNDECIDED. #154 proves only a metadata-only tracked remote subtree identity, not completeness of local/offline Vault or canonical source authority.
- **Benchmark:** gold corpus v1.0.0 remains pinned (42 cases / 32 docs / 69 nodes). PR #84 has two preserved E2 forbidden-node failures: gq-010 and gq-036. Current report evidence is 40/42, 14 status diagnostics, 0 explicit SourceRead mismatches. Do not weaken gates or relabel failures as passing.
- **Web worker:** PR fixture runs deliberately skip `synthetic-issue-worker`. No synthetic Issue write/round-trip has yet been authorized or run. That is a separate post-merge C gate for one marked request.

## 6. Parallelism / conflict rules

- #215 is E-CLAIMED; do not duplicate or alter the integrated bundle branch.
- #218 is the current free A review request for W1 PR #92 exact HEAD `42cecfef...` / base `f665ae7...`.
- #211 is A2-CLAIMED but stale; A2 was asked to RELEASE without verdict. Do not treat it as active Gate A.
- #208 is the single controlling C3 bundle/writer stack decision. Do not bypass its Gate A/B/C sequence.
- #196 is held; no writer final review or integration until the complete bundle parent is accepted.
- #206 is completed/accepted only for exact benchmark head/base; no ranking, corpus or token-budget changes authorized.
- Use a single task per owned file/branch. If the current main or a parent stack advances, create one narrow sync issue for the affected feature branch and supersede the stale exact-head review only after a replacement exists.
- Preserve all branches, PRs, commits and historical reviews. No force-push, rebase, reset or cleanup based only on a changed architectural direction.

## 7. Operational rule

Before any claim, review, acceptance or integration decision, verify live issue events, current main, PR head/base, ordered parents, direct compare/file list, actual Actions merge-ref and job logs. A verdict is valid only for its exact HEAD/base. Merge is always a separate C decision after required independent A acceptance.
