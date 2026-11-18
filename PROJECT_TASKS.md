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
| [#118](https://github.com/yeatu/obsidianGP/issues/118) | E — E3 RELEASED / A review #160 | Provider-neutral catalogue state machine и in-memory CAS adapter implemented in [PR #159](https://github.com/yeatu/obsidianGP/pull/159) | Exact HEAD `278c94baa2a28c299161dea380a6099cff39e352`; 4 catalogue files; fixture run #44272211955 SUCCESS, 12 passed; pending independent A review and C acceptance |
| [#119](https://github.com/yeatu/obsidianGP/issues/119) | E — E3 CLAIMED | Deterministic immutable bundle builder/verifier и canonical Markdown inventory | #117 accepted/merged; synthetic fixtures only; bundle files отдельно от #118 |
| [#157](https://github.com/yeatu/obsidianGP/issues/157) | A — A3 CLAIMED | Independent review of W1 PR #92 at HEAD `9ac913bbac479a5326e44d0679817c31153be5ac` / base `2996e0f...`; exact fixture run #44273234745 passed 56 tests and skipped the synthetic worker |
| [#156](https://github.com/yeatu/obsidianGP/issues/156) | E — E1 CLAIMED | Устранить остаточный межпроцессный drift benchmark PR #84 и получить побайтно одинаковые JSON/Markdown отчёты | Current PR #84 HEAD `99ccda870205acc4c40267f454d18aa85f0e113f`; run #44274741041 preflight 18 passed, 42 cases 40/42, two preserved E2 failures, 14 diagnostics; only gq-033 Token Efficiency still differs between attempts. #151/#158 closed as superseded; no A review until #156 acceptance evidence |
| [#121](https://github.com/yeatu/obsidianGP/issues/121) | E — E1 RELEASED | Benchmark corrections #113/#114/#121 implemented on PR #84; final review waits on #156 repeatability correction | Do not claim benchmark acceptance: 40/42 pass, two E2 forbidden-node failures preserved per #115; 14 diagnostics remain visible |
| [#139](https://github.com/yeatu/obsidianGP/issues/139) | E — E3 RELEASED | W1 canonical evidence allowlist correction awaits independent review #157, then separate C acceptance | W1-only correction; preserve shared V2.2 contracts |
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
- [#154](https://github.com/yeatu/obsidianGP/issues/154): A1 metadata-only source-tree comparison принят C3. На main и candidate source branch tracked `ГП/` subtree идентичен (SHA `94fd80ee95ab0514d1c1223c6fa0a763bd3bbb9f`): 66 Markdown blobs / 988,098 reported bytes / 30 directories / `truncated=false`. Это не подтверждает local/offline completeness или canonical source authority; выбор владельца в #145 остаётся UNDECIDED.
- [#152](https://github.com/yeatu/obsidianGP/issues/152): E2 current-main sync PR #92 принят и закрыт. Non-force two-parent merge preserved; exact PR HEAD `9ac913bbac479a5326e44d0679817c31153be5ac`, 14 W1 files, fixture run #44273234745 SUCCESS (56 passed), synthetic worker skipped. Fresh A review #157 is active.
- [#145](https://github.com/yeatu/obsidianGP/issues/145): owner-input coordination завершена; canonical source, sync/staleness, workload, latency, retention/RPO/RTO и budget оставлены UNDECIDED. Candidate branch не назначен canonical.
- [#113](https://github.com/yeatu/obsidianGP/issues/113) и [#114](https://github.com/yeatu/obsidianGP/issues/114): benchmark correction slices RELEASED; входят в финальный PR #84.
- [#121](https://github.com/yeatu/obsidianGP/issues/121): RELEASED; его final independent review remains gated by benchmark-wide byte-identical repeatability under #156.
- [#118](https://github.com/yeatu/obsidianGP/issues/118) / [PR #159](https://github.com/yeatu/obsidianGP/pull/159): E3 implementation RELEASED, 12 fixture tests passed, awaiting independent A review #160 and separate C acceptance.
- [#122](https://github.com/yeatu/obsidianGP/issues/122): W1 implementation handoff RELEASED; #152 current-main sync is completed, #148 closed as superseded, #139 awaits independent review #157.

## 3. Точные открытые PR

| PR | Состояние | Точный контекст |
|---|---|---|
| [#92 — synthetic Web adapter W1](https://github.com/yeatu/obsidianGP/pull/92) | Open, unmerged | Current HEAD `9ac913bbac479a5326e44d0679817c31153be5ac`; base/current main `2996e0f...`; 89 ahead / 0 behind; exactly 14 W1 files. History-preserving two-parent sync #152 completed. Fixture run #44273234745 passed 56 tests; synthetic worker skipped. Independent A review #157 is A3-CLAIMED; no Issue write/round-trip or merge before A and C gates |
| [#84 — synthetic gold benchmark](https://github.com/yeatu/obsidianGP/pull/84) | Open / Draft / unmerged | Current HEAD `99ccda870205acc4c40267f454d18aa85f0e113f`; current main `2996e0f...`; 19 ahead / 0 behind. E1 correction #156 changed fixture IDs to UUIDv5 and pinned `PYTHONHASHSEED=0`; run #44274741041 passed 18 preflight tests and ran 42 cases (40 pass / 2 preserved E2 failures / 14 diagnostics). Two artifacts still differ only at gq-033 Token Efficiency (-13.0244 vs -12.9512; aggregate -11.4911 vs -11.4890). #156 remains active; #151/#158 are superseded; no A review until two reports are byte-identical |
| [#159 — snapshot catalogue](https://github.com/yeatu/obsidianGP/pull/159) | Open, unmerged | HEAD `278c94baa2a28c299161dea380a6099cff39e352`; current main `2996e0f...`; four catalogue-owned files; fixture run #44272211955 passed 12 tests; independent review #160 is open |
| [#103 — previous governance panel](https://github.com/yeatu/obsidianGP/pull/103) | Closed / superseded by this fresh panel branch | Old PR branch/commits/history preserved. Do not merge; review #146 is closed as superseded |
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

- #118 implementation is RELEASED and awaits A review #160; #119 remains E3-CLAIMED on a disjoint bundle/inventory boundary.
- #121 is RELEASED, but its benchmark acceptance/review remains gated by active correction #156; no A review is currently valid for PR #84.
- W1 PR #92 is synchronized and fixture-validated; A3 owns fresh review #157. Old request #148 is closed as superseded and carries no verdict.
- Catalogue review #160 and E3 bundle implementation #119 remain independent; #120 waits for #118 and #119 acceptance; #125 waits for #119.
- E1 cloud verifier implementation is a later bounded task, not yet open: C creates it only after #119 review and C acceptance.
- Consumer tasks #134/#136/#137/#138 and lifecycle conformance #124 retain their explicit prerequisites.
- #145 is supported by accepted metadata-only comparison #154, but owner choices remain UNDECIDED. Do not infer canonical source from remote tree equality.
- Do not create overlapping Issues for work already CLAIMED. Decompose only when a distinct independently reviewable result exists.

## 6. Operational rule

Issues and their latest events are authoritative. Before claiming or accepting any task, verify the current issue state, latest CLAIM/RELEASE/BLOCKED events, PR HEAD/base/diff, exact CI checkout, and all dependencies. Keep one owner per Issue. Do not merge on the basis of a stale review target or a successful test run that still reports failed quality gates.

