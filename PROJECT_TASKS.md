# SFRA — оперативная панель проекта

> Точка входа для AI-участников и краткий снимок текущей работы. Нормативный протокол — [Issue #20, Governance Protocol v2.4](https://github.com/yeatu/obsidianGP/issues/20).
> GitHub Issue является источником истины по задаче и её последним событиям. Эта панель не заменяет CLAIM, RELEASE, review, CI или решения координатора.

**Снимок:** 2026-11-18  
**Main HEAD:** `2996e0f6a2cf4e65271d92330138e77899cad692`  
**Панель:** обновляется отдельной веткой/PR; предыдущие панели и их история сохраняются.

## 1. Текущий курс проекта

**Целевая архитектура исполнения:**

ChatGPT Web / mobile → GitHub Issues → GitHub Actions → GitHub-hosted Runner → SFRA shared core/services → результат в исходном Issue → ChatGPT читает результат.

- Личный компьютер владельца не является runtime-зависимостью и может быть выключен.
- GitHub-hosted Runner — эфемерная среда исполнения, не постоянное хранилище Vault, индекса или sidecar.
- Долговременный data plane: provider-neutral immutable snapshot bundles + versioned catalogue + read-only exact-version resolver/materializer. Направление принято в [#112](https://github.com/yeatu/obsidianGP/issues/112); провайдер и production source authority ещё не выбраны.
- Первый Web-адаптер W1 (#77 / PR #92) остаётся synthetic-only и развивается отдельно от cloud data-plane компонентов.
- Содержимое Vault и производные source metadata разрешено публиковать; владелец прямо указал, что сама публичность не является барьером конфиденциальности. Не вводить blanket redaction. Credentials, access tokens, signing keys, provenance и integrity controls защищаются.
- Публикация данных сама по себе не разрешает production import/read/index/write/activation. Эти операции остаются отдельными воротами решения.

**Общее ядро уже существует; не разрабатывать его повторно:**

- E1: structural indexing, node identity, source API.
- E2: lexical retrieval.
- E3/B1: Context Builder и integration pipeline.
- V2.1: SearchVaultService / ReadSourceService.
- V2.2: non-production Issue Worker Core.
- PinnedSnapshot verifier chain принята и объединена через PR #87 / decision #96. Это не включает production read_source.

**Сохранение прежних наработок:** ранее созданные локальные адаптеры, код, тесты, схемы, документация, ветки и PR остаются в истории и на HOLD. Они не удаляются и не превращаются в обязательную зависимость Web-runtime. Повторное использование возможно в согласованной границе; возобновлять отдельную локальную ветку без нового owner scope не нужно.

## 2. Активная очередь и владельцы

Фактический владелец определяется последним действующим CLAIM/RELEASE в самой Issue. Таблица не назначает задачи повторно.

| Issue | Роль / статус | Следующий результат | Зависимости и границы |
|---|---|---|---|
| [#118](https://github.com/yeatu/obsidianGP/issues/118) | E — E3 CLAIMED | Provider-neutral catalogue state machine и in-memory CAS adapter | #117 accepted/merged; synthetic in-memory only; отдельные catalogue files |
| [#119](https://github.com/yeatu/obsidianGP/issues/119) | E — E3 CLAIMED | Deterministic immutable bundle builder/verifier и canonical Markdown inventory | #117 accepted/merged; synthetic fixtures only; bundle files отдельно от #118 |
| [#148](https://github.com/yeatu/obsidianGP/issues/148) | A — stale REVIEW_REQUEST / awaiting replacement | A3 RELEASED old review claim #6973934758 after PR #92/main divergence; exact old target is superseded. E2 owns current-main sync #152. A fresh exact-head review request must be issued only after #152 fixture CI; #148 remains open to preserve review trail until replacement is linked |
| [#151](https://github.com/yeatu/obsidianGP/issues/151) | A — REVIEW_REQUEST needs target refresh | A3 RELEASED old claim #6973988363 because PR #84 advanced. Current PR #84 HEAD `62466d1abacc4b77730fb4a5f6e728117ae54d59`; current main/merge base `2996e0f6a2cf4e65271d92330138e77899cad692`; 18 ahead / 0 behind. Double full-run evidence belongs to code HEAD `f9b12dc...`; exact current-head run #44272093810: preflight 17 passed, 42 cases 40 passed / 2 failed, 14 status mismatches; artifacts #14413395861 and #14413366511. Refresh #151 to the current exact HEAD and require reviewer to distinguish code-equivalent prior double-run evidence from this exact-head attempt |
| [#121](https://github.com/yeatu/obsidianGP/issues/121) | E — E1 RELEASED | Реализация передана на A review #151 | Не считать benchmark прошедшим без оговорок: 40/42 cases pass, две E2 forbidden-node failures сохранены по #115 |
| [#139](https://github.com/yeatu/obsidianGP/issues/139) | E — E3 RELEASED | Ожидает независимую проверку #148, затем отдельную C acceptance | W1-only allowlist correction; не менять shared V2.2 contracts |
| [#77](https://github.com/yeatu/obsidianGP/issues/77) | P1 — W1 acceptance | A review → C acceptance → отдельное разрешение на один synthetic round-trip | Нет worker execution, Issue write или merge до завершения ворот |
| [#120](https://github.com/yeatu/obsidianGP/issues/120) | E — queued | Read-only exact-version resolver/materializer | После принятия #118 и #119; #117 уже принят |
| [#125](https://github.com/yeatu/obsidianGP/issues/125) | E — queued | Synthetic immutable upload port/reference writer | После принятия #119; без provider SDK/credentials |
| [#134](https://github.com/yeatu/obsidianGP/issues/134) | E — gated | B1 SnapshotIdentity v2 seam | По #131/#142; не начинать consumer migration раньше E1 verifier boundary |
| [#136](https://github.com/yeatu/obsidianGP/issues/136) | E — gated | Verified E3 cloud materialized handle | После #120, #134 и отдельной E1 verifier implementation/review |
| [#137](https://github.com/yeatu/obsidianGP/issues/137) | E — gated | Additive V2.2 `sfra.issue.v2` request/status | После #136; сохранить v1/TransportStatusV2 |
| [#138](https://github.com/yeatu/obsidianGP/issues/138) | E — gated | Synthetic V2.2 → B1 query-path conformance | После #134/#136/#137 и cloud contracts |
| [#124](https://github.com/yeatu/obsidianGP/issues/124) | E — later integration | End-to-end synthetic snapshot lifecycle conformance | После #117–#120 и #125 |

### Завершено / передано / принято

- [#112](https://github.com/yeatu/obsidianGP/issues/112): C3 принял cloud-only data-plane и отдельную operational disposition legacy E1 workflow.
- [#117](https://github.com/yeatu/obsidianGP/issues/117) / [PR #127](https://github.com/yeatu/obsidianGP/pull/127): CloudSnapshotRef v2 независимо проверен и merged в main commit `2996e0f...`; [C2 decision #150](https://github.com/yeatu/obsidianGP/issues/150) принял результат и разблокировал #118/#119.
- [#143](https://github.com/yeatu/obsidianGP/issues/143): correction использует `schema_info_version`, связанный с E1 `schema_info.schema_version`, а не SQLite `PRAGMA user_version`.
- [#123](https://github.com/yeatu/obsidianGP/issues/123), [#131](https://github.com/yeatu/obsidianGP/issues/131), [#132](https://github.com/yeatu/obsidianGP/issues/132), [#142](https://github.com/yeatu/obsidianGP/issues/142): интеграционная архитектура и additive E1 verifier design приняты. C откроет E1 implementation issue только после независимой проверки и C acceptance #119, как предписывает #142.
- [#133](https://github.com/yeatu/obsidianGP/issues/133): metadata-only sizing analysis принят; provider/region не выбраны.
- [#145](https://github.com/yeatu/obsidianGP/issues/145): owner-input coordination завершена; canonical source, sync/staleness, workload, latency, retention/RPO/RTO и budget оставлены UNDECIDED. Candidate branch не назначен canonical.
- [#113](https://github.com/yeatu/obsidianGP/issues/113) и [#114](https://github.com/yeatu/obsidianGP/issues/114): benchmark correction slices RELEASED; входят в финальный PR #84.
- [#121](https://github.com/yeatu/obsidianGP/issues/121): RELEASED после синхронизации PR #84 с текущим main и двух детерминированных прогонов; передан на #151.
- [#122](https://github.com/yeatu/obsidianGP/issues/122): W1 current-main integration handoff RELEASED; #139/#148 остаются отдельными correction/review этапами.

## 3. Точные открытые PR

| PR | Состояние | Точный контекст |
|---|---|---|
| [#92 — synthetic Web adapter W1](https://github.com/yeatu/obsidianGP/pull/92) | Open, unmerged | Prior W1 HEAD `c20e322...` / base `0be15bba...` was reviewed only on pre-sync evidence. A3 released #148 claim #6973934758 after main advanced to `2996e0f...`; E2 now owns non-force current-main sync #152. Require exact final merge-ref CI and a replacement independent A review before any merge; no synthetic Issue write/round-trip |
| [#84 — synthetic gold benchmark](https://github.com/yeatu/obsidianGP/pull/84) | Open / Draft / unmerged | Latest branch HEAD `62466d1abacc4b77730fb4a5f6e728117ae54d59`, current main/merge base `2996e0f6a2cf4e65271d92330138e77899cad692`, 18 ahead / 0 behind. Code HEAD `f9b12dc...` had two deterministic full runs (40/42, 2 E2 failures); later exact current-head run #44272093810 passed 17 preflight tests and again produced 40/42, 2 failures, 14 status mismatches. Artifacts #14413395861/#14413366511. #151 must be rebound to current HEAD; preserve the two E2 failures and 14 diagnostics, no gate weakening |
| [#103 — previous governance panel](https://github.com/yeatu/obsidianGP/pull/103) | Superseded by this fresh panel branch | Old PR branch/commits/history preserved. It was bound to stale main and its HEAD-specific review #146 no longer matches the live branch. Do not merge it |
| [#127 — CloudSnapshotRef v2](https://github.com/yeatu/obsidianGP/pull/127) | Merged | Merge commit `2996e0f6a2cf4e65271d92330138e77899cad692` |
| [#87 — PinnedSnapshot verifier](https://github.com/yeatu/obsidianGP/pull/87) | Merged | Accepted through #96; no production read activation |
| [#47, #57, #66, #94](https://github.com/yeatu/obsidianGP/pulls) | Historical / HOLD | Preserve branches, PRs, reviews and implementation assets. Not runtime dependencies; no deletion |

## 4. Decisions, gates and open unknowns

1. **Cloud execution:** GitHub-hosted runners only; no dependency on the owner's personal computer. A Runner workspace is ephemeral.
2. **Source authority:** the candidate remote branch is not confirmed as the complete/current canonical Vault. The matching remote `ГП/` subtree does not establish whether local/unpublished material exists. Do not restore, merge, overwrite or designate a production source without owner evidence.
3. **Provider and sync:** no cloud provider, region, bucket, durable storage service, import mechanism, update cadence or retention policy selected. Owner workload and SLO values remain UNDECIDED.
4. **Data publication:** Vault content and source-derived metadata may be published. Do not invent confidentiality restrictions. Protect credentials/keys and preserve source provenance, exact hashes and snapshot identity.
5. **Synthetic-only boundary:** #118/#119/#120/#124/#125 and dependent consumer tasks use disposable fixtures. No real Vault, SQLite, sidecar or `sfra-state` read/write; no provider provisioning, production sync, real ingestion, production `read_source`, or activation.
6. **Legacy persistence workflow:** `.github/workflows/sfra-state-persistence.yml` remains unchanged. Do not manually dispatch, rerun or intentionally trigger it. It is not the new data plane.
7. **Quality gate:** gold corpus v1.0.0 remains immutable (42 cases / 32 docs / 69 nodes). The two E2 forbidden-node failures in gq-010 and gq-036 remain visible failures; do not weaken retrieval gates, edit gold labels or retune ranking before accepted evidence.
8. **Historical work:** all former local-interface code, schemas, tests, docs, branches and PRs are preserved. No cleanup/deletion or forced transplant.

## 5. Parallelism and coordination

- #118 and #119 are independently claimed by E3 on disjoint component/file boundaries and may proceed in parallel.
- #121 has been released by E1; #151 is the next independent A handoff.
- #148 is currently claimed by A3 for W1. The old W1 review target is not a merge authorization; current-main sync and exact-head CI must be checked before integration.
- #120 waits for #118 and #119 acceptance; #125 waits for #119.
- E1 cloud verifier implementation is a later bounded task, not yet open: C creates it only after #119 review and C acceptance.
- Consumer tasks #134/#136/#137/#138 and lifecycle conformance #124 retain their explicit prerequisites.
- Do not create overlapping Issues for work already CLAIMED. Decompose only when a distinct independently reviewable result exists.

## 6. Operational rule

Issues and their latest events are authoritative. Before claiming or accepting any task, verify the current issue state, latest CLAIM/RELEASE/BLOCKED events, PR HEAD/base/diff, exact CI checkout, and all dependencies. Keep one owner per Issue. Do not merge on the basis of a stale review target or a successful test run that still reports failed quality gates.

