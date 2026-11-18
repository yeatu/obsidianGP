# SFRA — оперативная панель проекта

> Точка входа для AI-участников и краткий снимок текущей работы. Нормативный протокол — [Issue #20, Governance Protocol v2.4](https://github.com/yeatu/obsidianGP/issues/20).
> GitHub Issue и её последние действующие события — источник истины. Панель не заменяет CLAIM, RELEASE, review, CI или решение координатора.

**Снимок:** 2026-11-18  
**Текущий main HEAD:** `94bd689917ed7ed39dd100a92ef592581139f586`  
**Последний кодовый baseline:** `bc36bfdeceb34447f0cb8e1ae7978ecfe12de9c1`  
**Изменение main после code baseline:** два commit только с реестрами сессий #6 и #12; код SFRA не менялся.

## 1. Целевая архитектура и границы

**Целевой Web-путь:**

ChatGPT Web / mobile → GitHub Issues → GitHub Actions → GitHub-hosted Runner → SFRA shared core/services → ответ в исходном Issue → ChatGPT читает ответ.

- Личный компьютер владельца не является runtime-зависимостью; он может быть выключен.
- GitHub-hosted Runner — эфемерная среда исполнения, а не постоянное хранилище Vault, индекса или sidecar.
- Долговременный data plane: provider-neutral immutable snapshot bundles → versioned catalogue → read-only exact-version resolver/materializer.
- Web adapter W1 (#77 / PR #92) и cloud data-plane компоненты развиваются отдельными очередями через узкие порты и явные acceptance gates.
- Уже существуют и должны переиспользоваться: E1 structural indexing / source API; E2 lexical retrieval; E3/B1 Context Builder; V2.1 SearchVaultService / ReadSourceService; V2.2 non-production Issue Worker Core. Повторная реализация этих компонентов не требуется.
- Содержимое Vault и производные source metadata владелец разрешил публиковать; blanket redaction не вводить. Credentials, tokens, keys, provenance и integrity controls сохраняются.
- Публикация контента не означает автоматического разрешения production import/read/index/write, provider provisioning или snapshot activation.

**Сохранение исторических наработок:** ранее созданные адаптеры, реализации, тесты, схемы, документация, ветки, PR, commits и review trail сохраняются. Новое направление не является основанием удалять или переписывать их. Повторное использование допускается только в отдельной согласованной границе; прежние реализации не становятся обязательной runtime-зависимостью.

## 2. Активная очередь

Таблица — навигация, а не CLAIM. Фактический владелец определяется последним действующим событием в соответствующей Issue.

| Issue | Роль / действующий статус | Следующий результат | Граница / зависимость |
|---|---|---|---|
| [#167](https://github.com/yeatu/obsidianGP/issues/167) | A — A3 REVIEW_CHANGES_REQUESTED | Независимый аудит bundle PR #162 завершён с замечаниями | Exact HEAD `c9ab808...` / base `bc36bf...`; четыре bundle-owned files; correction #173; PR #162 не принят |
| [#174](https://github.com/yeatu/obsidianGP/issues/174) | A — свободный REVIEW_REQUEST | Независимый аудит benchmark PR #84 после синхронизации | Exact HEAD `7d6cd0d...` / base `94bd689...`; 29/0; two independent attempts; 42 cases, 40 pass / 2 сохранённых E2 failures; JSON/MD byte-identical; 14 diagnostics |
| [#178](https://github.com/yeatu/obsidianGP/issues/178) | E — свободная INTEGRATION | Синхронизировать W1 PR #92 с текущим main и перевалидировать | HEAD `a7eed176...`; main `94bd689...`; 90 ahead / 2 behind; incoming changes are two session registries only; new exact-head fixture CI + A handoff |
| [#172](https://github.com/yeatu/obsidianGP/issues/172) | E — E2 CLAIMED | Исправить два writer integrity finding из review #171 | PR #170 only; complete v2 identity binding + immutable version-ID validation; четыре writer-owned files |
| [#173](https://github.com/yeatu/obsidianGP/issues/173) | E — свободная correction task | Исправить parity object-key validation между prepared bundle и CloudSnapshotRef v2 | Correction for #167 / PR #162; только #119 builder/verifier + tests/docs; не менять #117 | 
| [#175](https://github.com/yeatu/obsidianGP/issues/175) | A — A1 CLAIMED | Read-only interface trace: prepared bundle → immutable writer receipt → v2 ref → catalogue | Independent integration analysis; no duplicate audit or code changes |
| [#119](https://github.com/yeatu/obsidianGP/issues/119) | E — E3 RELEASED / ждёт correction #173 | Принять deterministic immutable bundle builder/verifier | PR #162 exact HEAD `c9ab808...`; A3 review #167 CHANGES_REQUESTED; correction #173 свободна для E; затем fresh A review и C acceptance |
| [#125](https://github.com/yeatu/obsidianGP/issues/125) | E — E3 RELEASED / correction pending | Завершить writer boundary через #172, затем новое A review | PR #170 stacked on #162; не merge до #119 acceptance и correction review |
| [#156](https://github.com/yeatu/obsidianGP/issues/156) | E — E1 RELEASED / ждёт A #174 | Проверить cross-process reproducibility | PR #84 exact HEAD `7d6cd0d...` / base `94bd689...`; run #44366201687: 20/20 preflight, 42 cases, 40/42; report JSON/MD byte-identical; 2 E2 failures and 14 diagnostics preserved |
| [#77](https://github.com/yeatu/obsidianGP/issues/77) | P1 — W1 integration/review gate | #178 current-main sync → fresh A review → C acceptance → separate approval for one synthetic round-trip | PR #92 remains open/unmerged; worker dormant until all gates |
| [#120](https://github.com/yeatu/obsidianGP/issues/120) | E — queued / dependency-gated | Read-only exact-version resolver/materializer | После C acceptance #119; #118 уже принят/merged |
| [#124](https://github.com/yeatu/obsidianGP/issues/124) | E — queued / later integration | Synthetic snapshot lifecycle conformance | После принятия #117–#120 и #125 |
| [#134](https://github.com/yeatu/obsidianGP/issues/134) | E — gated | B1 SnapshotIdentity v2 seam | По #131/#142 и E1 verifier boundary |
| [#136](https://github.com/yeatu/obsidianGP/issues/136) | E — gated | Verified E3 cloud materialized handle | После #120/#134 и E1 verifier acceptance |
| [#137](https://github.com/yeatu/obsidianGP/issues/137) | E — gated | Additive V2.2 `sfra.issue.v2` protocol | После #136; v1/TransportStatusV2 сохранить |
| [#138](https://github.com/yeatu/obsidianGP/issues/138) | E — gated | Synthetic V2.2 → B1 query-path conformance | После #134/#136/#137 |
| [#139](https://github.com/yeatu/obsidianGP/issues/139) | E — E3 RELEASED / ждёт fresh review после #178 | W1 canonical evidence allowlist correction | W1-only; historical #157 accepted only prior HEAD; no shared V2.2 contract changes |

### Принято / завершено / историческое evidence

- [#112](https://github.com/yeatu/obsidianGP/issues/112): C3 принял cloud-only data-plane direction и disposition старого persistence workflow; issue закрыта.
- [#117](https://github.com/yeatu/obsidianGP/issues/117) / [PR #127](https://github.com/yeatu/obsidianGP/pull/127): CloudSnapshotRef v2 accepted и merged.
- [#118](https://github.com/yeatu/obsidianGP/issues/118) / [PR #159](https://github.com/yeatu/obsidianGP/pull/159): C3 acceptance зафиксирована после A2 REVIEW_ACCEPTED #160; merge commit `bc36bf...`. Каталог in-memory only; #119 verifier остаётся отдельной доверенной предпосылкой для `mark_verified()`.
- [#119](https://github.com/yeatu/obsidianGP/issues/119): E3 implementation RELEASED; review target #167 canonical. Ранее созданный #166 закрыт как дубликат/устаревший.
- [#125](https://github.com/yeatu/obsidianGP/issues/125): writer implementation RELEASED; A2 review #171 вернул CHANGES_REQUESTED и создал correction #172. PR #170 не принят.
- [#145](https://github.com/yeatu/obsidianGP/issues/145): canonical source, sync/staleness, workload, latency, retention/RPO/RTO и budget остаются UNDECIDED.
- [#154](https://github.com/yeatu/obsidianGP/issues/154): metadata-only remote tree comparison принят C3. В main и candidate branch tracked `ГП/` subtree совпадал (SHA `94fd80ee...`, 66 Markdown blobs, 988,098 reported bytes). Это не доказывает полноту локального/offline Vault и не выбирает canonical source.
- [#152](https://github.com/yeatu/obsidianGP/issues/152) и [#165](https://github.com/yeatu/obsidianGP/issues/165): W1 current-main sync handoffs завершены; прежние A reviews остаются применимы только к своим точным старым HEAD/base.
- [#164](https://github.com/yeatu/obsidianGP/issues/164): bundle current-main sync завершён; точный review handoff — #167.
- [#156](https://github.com/yeatu/obsidianGP/issues/156): E1 correction RELEASED after current-main sync. PR #84 exact HEAD `7d6cd0d...` / base `94bd689...`; two independent full attempts in run #44366201687, 20/20 preflight each, 42 cases each (40 pass / 2 fail), 14 status diagnostics, 0 explicit SourceRead mismatches. Actual reports are byte-identical: JSON SHA-256 `004b064df537dbed613d82fcf16ad6d08b07f9d72eaebc734602d6e6558327c6`, Markdown SHA-256 `5a41a391ce45856959906d9f0047ff06bb08582483a77e207cfa9562fd16c1b1`. Two E2 failures gq-010/gq-036 remain failed per #115; workflow conclusion is nonzero because these gates are preserved, not an all-green quality result. Fresh A review #174.
- W1 [#157](https://github.com/yeatu/obsidianGP/issues/157): A3 REVIEW_ACCEPTED только для исторического PR #92 HEAD `9ac913bb...` / base `2996e0f...`; не переносится на HEAD `a7eed176...`. Ранее #169 был review-запросом для этого более нового HEAD/base `bc36bf...`, но закрыт как superseded; #178 отвечает за новую синхронизацию с main `94bd689...` и свежий review.

## 3. PR и точные проверочные targets

| PR | Состояние | Контекст |
|---|---|---|
| [#92 — W1 Web adapter](https://github.com/yeatu/obsidianGP/pull/92) | Open / unmerged | HEAD `a7eed176...`; current main `94bd689...`; compare 90 ahead / 2 behind, merge base `bc36bf...`; current-main diff still exactly 14 W1 files. Historical run #44282727870 (56 passed; worker skipped) validates base `bc36bf...` only. #178 owns non-force sync, new exact-head fixture run and fresh A review; old #169 closed superseded |
| [#84 — gold benchmark](https://github.com/yeatu/obsidianGP/pull/84) | Open / Draft / unmerged | HEAD `7d6cd0d...`; current main/base `94bd689...`; compare 29 ahead / 0 behind; five benchmark-owned paths. Run #44366201687 two independent attempts: 20 preflight each, 42 cases, 40 pass / 2 preserved E2 fails, 14 diagnostics; report JSON/MD byte-identical. Fresh A review #174. Workflow conclusion is failure solely because gq-010/gq-036 remain failed quality gates |
| [#162 — immutable snapshot bundles](https://github.com/yeatu/obsidianGP/pull/162) | Open / unmerged | HEAD `c9ab808...`; base `bc36bf...`; 14 ahead / 0 behind that base; exactly four bundle-owned files. Dedicated run #44280944430: 28 passed; cross-layer C1/V2.1/V2.2 runs green on merge-ref `2b241665...`. A3 review #167 returned CHANGES_REQUESTED for object-key contract parity; E correction #173 is open. Current main is two registry-only commits ahead; sync/merge only after correction and fresh review |
| [#170 — immutable snapshot writer](https://github.com/yeatu/obsidianGP/pull/170) | Open / stacked / unmerged | HEAD `8c957c9...`; stacked base #162 HEAD `c9ab808...`; four writer-owned files; fixture run #44285246645: 18 passed. A2 #171 CHANGES_REQUESTED on full v2 identity binding and early immutable version-ID validation; correction #172 is E2-CLAIMED. Cannot merge ahead of #162/#119 or before fresh A review |
| [#176 — current governance panel](https://github.com/yeatu/obsidianGP/pull/176) | Open / unmerged | This one-file operational panel refresh; after this status reconciliation it remains based on current main `94bd689...`. Independent review request #177 is retained and rebound to the new exact HEAD. Previous PR #153 is closed unmerged/superseded; its branch and history are preserved |
| [#159 — snapshot catalogue](https://github.com/yeatu/obsidianGP/pull/159) | Merged | Merge commit `bc36bfde...`; A2 accepted, C3 accepted |
| [#127 — CloudSnapshotRef v2](https://github.com/yeatu/obsidianGP/pull/127) | Merged | Merge commit `2996e0f...` |
| [#87 — PinnedSnapshot verifier](https://github.com/yeatu/obsidianGP/pull/87) | Merged | Accepted via #96; no production read activation |

## 4. Решения, зависимости и неизвестные

1. **Cloud execution:** GitHub-hosted runners; personal PC is not a runtime requirement. Runner workspace is ephemeral.
2. **Source authority:** candidate branch is not confirmed as the complete/current canonical Vault. No restore/copy/merge/overwrite or production source designation without owner evidence.
3. **Provider and sync:** no provider, region, bucket, import/update mechanism, staleness target or retention policy chosen. Workload and SLO remain UNDECIDED.
4. **Synthetic-only work:** #119/#120/#124/#125 and dependent consumer tasks use disposable fixtures. No real Vault/SQLite/sidecar/`sfra-state` read/write, provider provisioning, production sync/ingestion, production `read_source` or activation.
5. **Legacy persistence workflow:** keep unchanged; do not manually dispatch, rerun or deliberately trigger it. It is not the new data plane.
6. **Quality:** gold corpus v1.0.0 remains immutable (42 cases / 32 docs / 69 nodes). Two E2 forbidden-node failures gq-010/gq-036 remain visible failures. No gate weakening, corpus edits or ranking retuning to make the aggregate green.
7. **W1:** no worker execution, Issue write or round-trip until A #169 accepts the current exact tree and C separately authorizes a single marked synthetic round-trip.
8. **Writer:** no provider, network, credentials, OIDC/KMS, persistent storage or production upload. #172 must fix both review findings before another A review.
9. **History:** previous implementations and branches stay preserved. No cleanup, deletion, force-push or history rewriting.

## 5. Parallelism and coordination

- #167 A3 review is complete with REVIEW_CHANGES_REQUESTED; #173 is the sole E correction for the bundle object-key validation gap.
- #174 is open for a free independent Role A review of PR #84. #169 is closed/superseded; do not review its stale target.
- #172 is E2-CLAIMED and is the single correction task for #171. Do not create a duplicate writer correction. #173 is the separate unclaimed E correction for #167.
- #119 bundle implementation is RELEASED; #125 writer implementation is RELEASED but has a blocking correction; #120 waits for #119 acceptance; #124 waits for the full snapshot component set.
- #84 is synced to current main `94bd689...` and its exact A request is #174. #92 still needs the #178 sync. #162 is under #173 correction; its later merge must include the two registry-only main commits by a history-preserving update.
- Consumer tasks #134/#136/#137/#138 retain their explicit gates.
- Do not claim an E/A task as C3, do not overlap another agent's CLAIM, and do not infer acceptance from a successful workflow when the quality report contains failed gates.

## 6. Operational rule

Before any claim, acceptance or integration decision, verify the Issue's latest CLAIM/RELEASE/BLOCKED events, current PR HEAD/base/diff, merge base, exact CI checkout, all dependencies and whether a later event superseded the target. A verdict is valid only for its exact HEAD/base. Merge remains a separate C decision after required A acceptance.