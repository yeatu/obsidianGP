# SFRA — оперативная панель

> Точка входа для AI-участников и снимок активной работы. Нормативные правила — [Issue #20, Governance Protocol v2.4](https://github.com/yeatu/obsidianGP/issues/20).
> GitHub Issue — источник истины по задаче. Эта панель показывает только активные задачи и не дублирует CLAIM, review, CI или evidence.

**Снимок:** 2026-11-18 (C3 reconciled #133/#144/#145; #143 implementation released; #147 superseded; #149 owns current-main sync for PR #127)
**Current main HEAD for this dashboard update:** `0be15bba569cb00487b835e99e82ea7dd9767478`  
**Предыдущая общая code baseline:** `4e3fb5ae464b0db8db0b3071ab2dc7f3f320d466` (latest three main commits add session registries only; no SFRA code change)

## 0. Начало работы

Пользователь и координатор не назначают обычные задачи вручную. Участник сам выбирает свободную задачу своей роли, публикует CLAIM и начинает работу.

| Роль | Ответственность | Допустимые типы |
|---|---|---|
| **E — исполнитель** | Код, тесты, исправления, техническая документация и интеграция в утверждённом scope | `IMPLEMENTATION`, `INTEGRATION` |
| **A — аналитик** | Исследование, диагностика, требования, аудит и независимая проверка | `ANALYSIS`, `REVIEW_REQUEST` |
| **C — координатор** | Приоритеты, scope, архитектура, зависимости, блокировки, перераспределение, кризисы, общая панель и merge | `COORDINATOR_DECISION`; управление задачами всех ролей |

Буква Agent ID задаёт роль; цифра только различает участников: E1/E2/... имеют равные права внутри E, A1/A2/... — внутри A. Цифра не даёт старшинства или исключительных прав. Идентификатор C и полномочия выдаёт только владелец проекта; самоназначение запрещено.

**Если Agent ID ещё нет:** сохрани уже выданный ID. Иначе выбери E или A по типу задачи и следующий номер выше максимального использованного в этой категории. Проверь CLAIM во всех известных Issues, включая закрытые; номера не переиспользуются, нумерация E и A независимая. При совпадении первый CLAIM по GitHub comment ID сохраняет ID, второй публикует `AGENT_ID_REASSIGN` в своей Issue и выбирает следующий номер.

### Самостоятельный CLAIM

1. Выбери активную задачу своей роли. Не бери задачу другой роли, BLOCKED-задачу или задачу с невыполненными зависимостями.
2. Проверь Issue: статус, scope, критерии, зависимости, последние CLAIM/RELEASE/BLOCKED/REVIEW-события, пересекающиеся Issues/PR, требования к компетенциям, доступу и независимости.
3. Опубликуй комментарий:

   ```
   CLAIM
   Task: #<issue>
   Agent: <E<n>|A<n>|C<n>>
   Role: <E|A|C>
   Scope: <что именно беру>
   Started: <UTC timestamp>
   ```

4. Повторно прочитай комментарии. При гонке действует корректный CLAIM с наименьшим GitHub comment ID. Проигравший прекращает пересекающуюся работу и публикует `CLAIM_CONFLICT_YIELD`.
5. После подтверждения CLAIM начинай работу без дополнительного разрешения C для обычных задач E/A. Публикуй `PROGRESS`, а результаты и доказательства сохраняй в Issue/PR/commit/Actions.

Исключение из границ ролей возможно только при явном делегировании C с записанным scope и сроком/условием окончания.

## 1. Текущий курс

**Целевая архитектура:** ChatGPT Web / mobile → GitHub Issues → GitHub Actions → GitHub-hosted runner → SFRA shared core/services → ответ в исходном Issue → ChatGPT читает результат.

- Система должна работать, когда личный компьютер владельца выключен. Personal computer, self-hosted runner, local daemon/tunnel and MCP are not runtime dependencies.
- GitHub-hosted runners — эфемерная среда исполнения, а не постоянное хранилище Vault/index/manifest/sidecar.
- Cloud data-plane direction принята по [C decision #112](https://github.com/yeatu/obsidianGP/issues/112) на основе анализа [#86](https://github.com/yeatu/obsidianGP/issues/86), report PR #107 merged at `8e853783b8ccd47571e7402c57b9e935684a0b25`: provider-neutral immutable snapshot bundles + versioned catalogue + read-only resolver/materializer. Провайдер и source authority пока не выбраны; реальный Vault не подключён.
- Web adapter W1 [#77](https://github.com/yeatu/obsidianGP/issues/77) строится только на synthetic fixtures и не зависит от будущего data plane.

**Shared SFRA Core already in main:** E1 structural indexer / Node identity / source API; E2 SQLite/FTS retrieval; E3/B1 Context Builder; V2.1 SearchVaultService / ReadSourceService; V2.2 non-production Issue Worker Core. Не дублировать существующую business logic в transport/application adapters.

**PinnedSnapshot security accepted:** C1 принял cumulative chain #36/#51/#67/#79 по C decision [#96](https://github.com/yeatu/obsidianGP/issues/96) после A1 `REVIEW_ACCEPTED` в [#88](https://github.com/yeatu/obsidianGP/issues/88). PR #87 merged into main: merge commit `9ba9d0403de0683c97938d0d323d96799157fc57`; reviewed HEAD `162e4190b00c63c67ed1f7fb29871819315c4d92`. Все три cumulative fixture-only CI workflows passed на одном combined checkout. Исторические #36/#51/#67/#79 закрыты; #54/#70 закрыты как superseded. **Это принятие общей security boundary не активирует production `read_source`.**

**Cloud data/publication preference:** владелец прямо подтвердил, что публичность содержимого Vault и source-derived metadata не является препятствием конфиденциальности. Допустимо публиковать фрагменты или полное содержимое подходящими каналами; blanket redaction не требуется. Защищать credentials/secrets, provenance и integrity; учитывать size, cost, retention и техническую пригодность каналов. Публикация не является разрешением на production ingestion, execution, write или mutation.

**Preserved historical work:** Local MCP milestone [#35](https://github.com/yeatu/obsidianGP/issues/35) и вся связанная реализация сохранены как исторические инженерные активы. MCP не является продуктовым маршрутом или runtime dependency; MCP-only Issues #38/#39/#40/#43/#72 и PR #47/#57/#66/#94 находятся на HOLD. Ничего не удалять и не продолжать MCP-only work/merge без отдельного owner re-scope. Транспорт-независимые решения и код можно повторно использовать через отдельно согласованный scope.

**Quality:** accepted synthetic gold corpus v1.0.0 — 42 cases, 32 synthetic docs, 69 nodes (PR #58), immutable digest `sha256:915304e812906f64003d9aacb0dd4b7701f7fbcf4f24fdc3cda21d1108b13068`. End-to-end benchmark [#42](https://github.com/yeatu/obsidianGP/issues/42) остаётся synthetic-only. C decision [#115](https://github.com/yeatu/obsidianGP/issues/115) retains two E2 forbidden-node hits as measured quality failures and separates standalone SourceRead outcomes from Pack completeness. #113 and #114 implementation slices are complete and RELEASED by E1; #121 is the active final sequential correction. Full 42-case validation must run twice only after #121 on the final synchronized HEAD.
## 2. Активные задачи

Таблица отражает актуальные задачи целевого cloud/Web направления и shared-core quality/security. Источники истины — Issue/PR/commit/Actions; CLAIM и зависимости повторно проверяются в соответствующей Issue.

| Issue | Приоритет | Тип | Роль | Следующий результат | Зависимости / владелец |
|---|---:|---|:---:|---|---|
| [#146](https://github.com/yeatu/obsidianGP/issues/146) | P1 | `REVIEW_REQUEST` | **A** | Независимо проверить текущий точный HEAD cloud-only панели PR #103 | #104 CHANGES_REQUESTED applies only to superseded HEAD `5aef588...`; #146 is rebound after current-main sync and final panel correction. Fresh independent A CLAIM must name the exact HEAD/base/diff recorded in the latest TARGET_BOUND comment. No prior verdict transfers; no merge before A acceptance and separate C decision
| [#149](https://github.com/yeatu/obsidianGP/issues/149) | P2 | `INTEGRATION` | **E** | Синхронизировать PR #127 с current main и обновить точные fixture CI / fresh A review | Свободная задача; #143 уже RELEASED. PR #127 HEAD `4fc9ea9fd17a63e4aac050ead1a3ac7665c4dfe8`, current main `0be15bba569cb00487b835e99e82ea7dd9767478`, compare 13 ahead / 3 behind, merge base `4e3fb5ae...`. Non-force sync only; stop on conflicts or expanded diff; no PR merge or production operation
| [#109](https://github.com/yeatu/obsidianGP/issues/109) | P1 | `REVIEW_REQUEST` | **A** | После #121 и двух успешных финальных прогонов независимо проверить PR #84 | PR #84 HEAD `6d09cbbadb7d3a4dbe8624e497d9cdd613884a66`; recorded base `8e853783b8ccd47571e7402c57b9e935684a0b25`; current main `0be15bba569cb00487b835e99e82ea7dd9767478`; compare 14 ahead / 3 behind (merge base `4e3fb5ae...`). #113/#114 RELEASED; E1 owns #121. Run #44259409660: preflight 17 passed, benchmark 40/42, 2 failed, 14 status mismatches; artifact #14407327108. No final pass. Diagnose/correct, sync current main, run all 42 cases twice on the same final HEAD, then refresh #109 with exact HEAD/base/checkout and both artifact hashes and request new A CLAIM. Preserve quality failures

| [#148](https://github.com/yeatu/obsidianGP/issues/148) | P1 | `REVIEW_REQUEST` | **A** | Независимо проверить W1 canonical evidence allowlist на точном синхронизированном HEAD PR #92 | PR #92 HEAD `c20e322641bcd3552ecaaef16c74ddb0d820db54`, current main/base `0be15bba569cb00487b835e99e82ea7dd9767478`; 88 ahead / 0 behind; diff 14 W1 files only. Fixture run #44268294075 passed 56; synthetic-issue-worker skipped. Fresh A review; #129 applies only to old HEAD
| [#113](https://github.com/yeatu/obsidianGP/issues/113) | P2 | `IMPLEMENTATION` | **E** | Token Efficiency baseline fix delivered; awaits final benchmark after #121 diagnosis | E1 RELEASED implementation slice on PR #84; relevant paths include required ∪ allowed-additional nodes and deduplicate documents. Intermediate preflight failure fixed in shared branch; no final passing benchmark claimed. Do not weaken quality gates
| [#114](https://github.com/yeatu/obsidianGP/issues/114) | P2 | `IMPLEMENTATION` | **E** | Fallback Rate instrumentation fix delivered; awaits final benchmark after #121 diagnosis | E1 RELEASED implementation slice on PR #84; counts actual dependency read_scope calls separately from address resolutions, E2 reads and explicit SourceRead. No final passing benchmark claimed
| [#121](https://github.com/yeatu/obsidianGP/issues/121) | P2 | `IMPLEMENTATION` | **E** | Diagnose current synthetic benchmark failures after Pack/SourceRead separation | E1 CLAIM #6971085966. PR #84 HEAD `6d09cbbadb7d3a4dbe8624e497d9cdd613884a66`; recorded base `8e853783...`, current main `0be15bba569cb00487b835e99e82ea7dd9767478`, compare 14 ahead / 3 behind (merge base `4e3fb5ae...`). Run #44259409660: preflight 17 passed; benchmark 40/42 passed, 2 failed, 14 mismatches; artifact #14407327108. Preserve corpus v1.0.0 and gq-025/gq-028/gq-029 interpretation notes; diagnose report first. Final 42-case double-run only after #121 correction and current-main sync. No pass claimed
| [#117](https://github.com/yeatu/obsidianGP/issues/117) | P2 | `IMPLEMENTATION` | **E** | Завершить приёмку CloudSnapshotRef v2 после current-main sync, fresh CI и независимого A review | Коррекция #143 RELEASED E1 на PR #127 HEAD `4fc9ea9fd17a63e4aac050ead1a3ac7665c4dfe8`; `schema_info_version` bound to E1 `schema_info.schema_version`, legacy `user_version` rejected; #130 protections and v1 boundary preserved. Four fixture suites passed on that pre-sync HEAD (#44266936359: 155 tests; #44266943077; #44266943140; #44266943128). Current main `0be15bba569cb00487b835e99e82ea7dd9767478`; compare 13 ahead / 3 behind, merge base `4e3fb5ae...`. #147 was closed as superseded due stale base; #149 owns non-force sync, fresh exact-head CI and one new A review. Then C3 acceptance; no merge/production activation yet
| [#118](https://github.com/yeatu/obsidianGP/issues/118) | P2 | `IMPLEMENTATION` | **E** | Implement versioned snapshot catalogue state machine/CAS | Unclaimed; blocked until #117/#127 satisfies C decision #142, correction #143 is independently reviewed and C accepts #117
| [#119](https://github.com/yeatu/obsidianGP/issues/119) | P2 | `IMPLEMENTATION` | **E** | Build/verify immutable snapshot bundles and canonical Markdown inventory | Unclaimed; #119 now owns canonical versioned Markdown inventory consumed by E1 verifier per #142. Starts only after #117 corrected to `schema_info_version`, independently reviewed and C-accepted; then can run parallel with #118
| [#120](https://github.com/yeatu/obsidianGP/issues/120) | P2 | `IMPLEMENTATION` | **E** | Read-only exact-version snapshot resolver/materializer | Unclaimed; starts after #117–#119 accepted
| [#125](https://github.com/yeatu/obsidianGP/issues/125) | P2 | `IMPLEMENTATION` | **E** | Immutable object upload port + synthetic in-memory writer | Unclaimed; blocked by accepted #117 and #119; no cloud SDK/credentials/provider provisioning
| [#134](https://github.com/yeatu/obsidianGP/issues/134) | P2 | `IMPLEMENTATION` | **E** | Add B1-owned SnapshotIdentity protocol without importing E3 cloud types | Queued behind #131/#142: accepted #117, #120 and accepted E1 verifier implementation after #132. B1 files/tests only; no speculative work
| [#136](https://github.com/yeatu/obsidianGP/issues/136) | P2 | `IMPLEMENTATION` | **E** | Add factory-verified E3 cloud materialized handle and preserve v2 identity through pipeline | Queued behind accepted #117/#120, #134, and separate accepted E1 verifier implementation following #132. E3 files only; no provider code
| [#137](https://github.com/yeatu/obsidianGP/issues/137) | P2 | `IMPLEMENTATION` | **E** | Add additive V2.2 sfra.issue.v2 request/status with snapshot_id | Queued after #136 acceptance; preserve sfra.issue.v1 and TransportStatusV2 unchanged
| [#138](https://github.com/yeatu/obsidianGP/issues/138) | P2 | `IMPLEMENTATION` | **E** | Synthetic query-path conformance from V2.2 through B1 | Later integration after accepted #117–#120, E1 verifier, #134, #136 and #137; distinct from lifecycle suite #124
| [#124](https://github.com/yeatu/obsidianGP/issues/124) | P3 | `IMPLEMENTATION` | **E** | Synthetic cloud snapshot lifecycle conformance suite | Unclaimed later integration task; blocked until #117–#120 and #125 accepted


**На HOLD по решению владельца:** Local MCP-only Issues #38/#39/#40/#43/#72. Все ранее созданные code/tests/docs/branches/PRs сохранены; не продолжать и не merge без explicit owner re-scope. PR #47/#57/#66/#94 остаются Draft/HOLD. Review #95 закрыт как not planned для MCP-only кода. #53 закрыта после owner waiver на удаление старого публичного run/artifact; сам real-Vault workflow остаётся выключенным.

**Завершено / принято / передано на независимую проверку:** #112 — C3 cloud data-plane/legacy workflow decision; #116 — A1 legacy E1 workflow assessment accepted; #123 — A1 CloudSnapshotRef consumer integration analysis accepted; #131 — additive B1/E3/V2.1/V2.2 integration boundary accepted; #132 — A3 E1 cloud verifier analysis accepted/closed; #133 — A1 metadata-only cloud sizing analysis accepted by C3 and closed (report #6972632230, acceptance #6972807258); #145 — C2 owner-input coordination completed/closed with all outstanding inputs explicitly UNDECIDED (candidate subtree comparison recorded in #145); #142 — C3 SQLite schema identity and canonical inventory decision accepted/closed; #104 — A1 CHANGES_REQUESTED on superseded panel HEAD, followed by fresh review #146; #128 — A1 review CHANGES_REQUESTED on superseded PR #127 HEAD, findings transferred to #130; #129 — A3 W1 review CHANGES_REQUESTED on superseded PR #92 HEAD, findings transferred to #139; #122 — W1 integration handoff completed/released; #139 — E3 canonical gq-004-only correction delivered/released on synchronized PR #92 HEAD `c20e322...`, fixture CI #44268294075 passed 56; PR #92 is awaiting independent A review #148 and separate C acceptance; #141 — A3 final review CHANGES_REQUESTED on superseded PR #127 HEAD `6fd89c...`; #143 — E1 correction completed/RELEASED at PR #127 HEAD `4fc9ea9...`, exact-head fixture suites green; #147 — stale-base A review request closed as superseded pending #149 and a fresh review; #135 — premature E1 placeholder closed not planned; #15/#16, #18/#21, #36/#51/#67/#79 and prior accepted work remain as previously recorded. #35 is historical and preserved.
## 2.1. Новое правило декомпозиции: parallel-first

По Governance Protocol v2.4 (§5) каждую новую крупную задачу сначала разбиваем на минимальные самостоятельно полезные и проверяемые результаты. Для каждого пакета фиксируются один владелец, целевая роль, deliverable, затрагиваемые компоненты/файлы, прямые блокирующие зависимости, конфликты и интеграционная граница. Родительская связь не считается зависимостью автоматически. Независимые анализ, контракты, компоненты, тестовые наборы, fixtures, документация и conformance-проверки открываются отдельными Issues, когда их можно завершать параллельно. Не создаём микрозадачи без собственного результата и не расширяем scope ради занятости.

## 3. Открытые PR

| PR | Состояние | Трактовка |
|---|---|---|
| [#92 — synthetic Web adapter W1](https://github.com/yeatu/obsidianGP/pull/92) | Open / current-main sync and exact-head fixture CI passed; fresh A review #148 required | HEAD `c20e322641bcd3552ecaaef16c74ddb0d820db54`; current main/base `0be15bba569cb00487b835e99e82ea7dd9767478`; 88 ahead / 0 behind, merge base equals main. Diff exactly 14 W1 files. Run #44268294075 passed 56; synthetic worker job skipped. E3 released #122/#139; no merge/worker execution; #148 is the active independent review
| [#84 — synthetic gold benchmark](https://github.com/yeatu/obsidianGP/pull/84) | Open / Draft / #121 diagnostic correction active; current-main sync required before final evidence | HEAD `6d09cbbadb7d3a4dbe8624e497d9cdd613884a66`; recorded base `8e853783b8ccd47571e7407c7b9e935684a0b25`; current main `0be15bba569cb00487b835e99e82ea7dd9767478`; compare 14 ahead / 3 behind (merge base `4e3fb5ae...`). Run #44259409660: preflight 17 passed, benchmark 40/42, 2 failed, 14 status mismatches; artifact #14407327108. No final pass
| [#127 — cloud SnapshotRef v2 contract](https://github.com/yeatu/obsidianGP/pull/127) | Open / correction #143 RELEASED; current-main sync and fresh A review queued in #149 | HEAD `4fc9ea9fd17a63e4aac050ead1a3ac7665c4dfe8`; recorded base/merge-base `4e3fb5ae...`; current main `0be15bba569cb00487b835e99e82ea7dd9767478`, compare 13 ahead / 3 behind. #143 delivered `schema_info_version`; dedicated run #44266936359 passed 155 and related C1/V2.1/V2.2 runs #44266943077/#44266943140/#44266943128 passed on this pre-sync HEAD. #147 closed as superseded (stale base); #149 owns non-force sync, exact-head revalidation and fresh independent A review. No merge
| [#47 — historical Local MCP bootstrap](https://github.com/yeatu/obsidianGP/pull/47) | Открыт / Draft / HOLD | Preserved, not a target, do not merge |
| [#57 — historical MCP search adapter](https://github.com/yeatu/obsidianGP/pull/57) | Открыт / Draft / HOLD | Preserved; no further MCP-only work or merge |
| [#66 — historical read_source parser preparation](https://github.com/yeatu/obsidianGP/pull/66) | Открыт / Draft / HOLD | Accepted parser-only slice preserved for possible adaptation |
| [#94 — historical MCP schema correction](https://github.com/yeatu/obsidianGP/pull/94) | Открыт / Draft / HOLD | E3 completed exact-head work and CI; do not spend A review or merge while MCP is off target |
| [#103 — cloud-only governance panel refresh](https://github.com/yeatu/obsidianGP/pull/103) | Open / C3 current-main reconciliation; fresh follow-up A review #146 required | The feature branch is synced to current main `0be15bba...` by a non-force merge preserving both histories. The final PR diff against main remains exactly `PROJECT_TASKS.md`. Panel records #133/#145 C3-accepted/closed, #143 implementation RELEASED, #149 current-main sync gate and #148 W1 review. #146 is bound to exact panel HEAD `984aef9ff3ac57d4c4cb7d81f69f80d68d3b8268` / base `0be15bba569cb00487b835e99e82ea7dd9767478`; no earlier verdict transfers. No merge before fresh A acceptance and separate C decision
| [#110 — W1 review handoff panel patch](https://github.com/yeatu/obsidianGP/pull/110) | **Closed / superseded** | Its narrow #122→#129 / PR #92 evidence patch is already present in current parent panel PR #103. The PR #110 branch, commits and discussion remain preserved; no branch deletion or history rewrite |
| [#107 — cloud data-plane analysis](https://github.com/yeatu/obsidianGP/pull/107) | **Merged** | C3 accepted report under #112; merge commit `8e853783b8ccd47571e7402c57b9e935684a0b25` |
| [#87 — PinnedSnapshot exact-type correction](https://github.com/yeatu/obsidianGP/pull/87) | **Merged** | Main merge `9ba9d0403de0683c97938d0d323d96799157fc57`; A1 and C1 accepted |
| [#54 / #70 — prior verifier attempts](https://github.com/yeatu/obsidianGP/pulls) | **Closed / superseded** | Their accepted cumulative correction is in merged PR #87; branch/commit/review history preserved |
| [#85 — earlier W1 implementation branch](https://github.com/yeatu/obsidianGP/pull/85) | **Closed / superseded** | Current W1 delivery is PR #92 |
| [#44 — previous governance dashboard branch](https://github.com/yeatu/obsidianGP/pull/44) | **Closed / superseded** | Old dashboard PR and review #99 are closed; branch, commits and review history remain preserved |


## 4. Действующие ограничения и решения

- **Cloud-only runtime:** ChatGPT Web/mobile → GitHub Issues → Actions → GitHub-hosted runners → SFRA. No personal computer, self-hosted runner, local daemon/tunnel or MCP transport.
- **Durable source data:** provider-neutral immutable snapshot bundles + versioned catalogue + read-only resolver/materializer accepted in #112. PR #127/#117 remains unaccepted: E1 correction #143 is RELEASED at HEAD `4fc9ea9...` with `schema_info_version`; current-main sync and fresh fixture evidence are owned by #149 because the branch is 13 ahead / 3 behind current main. #118/#119/#125 wait for accepted #117; #120 follows #117–#119. #119 owns canonical Markdown inventory consumed by the E1 verifier. #132 analysis is accepted/closed; C will open the bounded E1 verifier implementation issue only after #117 and #119 are independently reviewed and C-accepted, per #142. #133 is C3-accepted/closed metadata-only sizing analysis. #145 is C2-completed/closed; remaining owner inputs are explicitly UNDECIDED. The candidate branch is preserved but not canonical. Consumer queue #134/#136/#137/#138 remains gated. Provider/region/retention remain unselected; runner workspace is ephemeral.
- **SQLite identity (#142):** shared CloudSnapshotRef v2 must bind E1 `schema_info.schema_version` as `schema_info_version`, not SQLite `PRAGMA user_version` (current E1 does not set/read that pragma). A3 final review #141 blocked the old candidate; E1 correction #143 has now replaced `user_version` with `schema_info_version` and was RELEASED at HEAD `4fc9ea9...`; #149 owns the required current-main sync and fresh review handoff. E1 verifier will be additive/read-only and validate whole materialized index consistency; #119 owns the canonical inventory format.
- **SQLite/cloud identity contract (#142):** outer CloudSnapshotRef v2 must bind E1's actual `schema_info.schema_version` as `schema_info_version`, not SQLite `PRAGMA user_version` (which current E1 does not set/read). E1 cloud verifier is additive/read-only and checks whole materialized source/index consistency; #119 owns the canonical inventory format. No E1 implementation before #117 and #119 are accepted.
- **Publication:** publication of Vault content and source-derived metadata is allowed by owner preference; do not impose blanket confidentiality redaction. Protect credentials/secrets and preserve provenance/integrity. Select delivery channels based on size, cost, retention and usefulness.
- **Canonical source owner gate (#145, closed):** C2 completed the coordination task with remaining owner inputs explicitly UNDECIDED. The candidate branch exists at `2a3c54f...`; its `ГП/` subtree tree SHA `94fd80e...` matches current main's subtree, but the whole branch diverges (64 ahead / 451 behind). Do not merge/restore the whole branch. This is not confirmation of the complete/current local Vault; canonical source, sync/staleness, workload/SLO/retention/recovery/budget remain undecided.
- **Production boundary:** permission to publish content does not authorize real Vault reads, import, indexing, production Actions execution, write or mutation. The E3 integration workflow remains fail-closed. Separately, `.github/workflows/sfra-state-persistence.yml` has configured push + workflow_dispatch triggers, `contents:write`, and publishes SQLite/manifest to `sfra-state`; #116 verified 10 historical successful runs but could not verify present repository Actions enablement/settings. It remains unchanged, must not be manually dispatched or deliberately triggered, and is neither approved nor required for the new data plane. Avoid changes matching its push filters. Any future workflow change requires a separate narrow decision/explicit approval.
- **W1 #77 / PR #92:** synthetic-only. E3 completed/released #122/#139 after a history-preserving current-main sync. Exact HEAD `c20e322641bcd3552ecaaef16c74ddb0d820db54`, current main `0be15b...`, 88 ahead / 0 behind, exactly 14 W1 files. Fixture run #44268294075 passed 56 tests and the worker job was skipped. Fresh independent A review #148 is open; no C acceptance, merge or worker round-trip yet. Only canonical gq-004-exception-pair and approved gate_rule/gate_exception with pinned provenance are allowed.
- **PinnedSnapshot:** shared verifier guard is accepted/merged at #87. This does **not** enable production `read_source`. A future Web composition needs its own reviewed cloud SnapshotRef provider/materializer and response-worker path, then a separate C/owner activation decision under #112.
- **Local MCP legacy work:** Issues #38/#39/#40/#43/#72 and PRs #47/#57/#66/#94 are preserved on HOLD; no new CLAIM, review, implementation or merge without explicit owner re-scope.
- **Benchmark #42:** synthetic-only. PR #84 is 14 ahead / 3 behind current main. #121 is E1-owned; sync PR #84 after the sequential #113 → #114 → #121 correction chain, then run the full 42 cases twice on the same final synchronized HEAD. Preserve the corpus and failed findings; do not weaken forbidden-node or completeness assertions.
- Do not add embeddings/vector search, alter retrieval ranking or change E3 token budget before benchmark evidence. Never report truncated source text as complete.
- Governance protocol: [#20](https://github.com/yeatu/obsidianGP/issues/20); cloud-only Web decision: [#75](https://github.com/yeatu/obsidianGP/issues/75); cloud data-plane analysis: [#86](https://github.com/yeatu/obsidianGP/issues/86); cloud architecture decision: [#112](https://github.com/yeatu/obsidianGP/issues/112); verifier threat model: [#81](https://github.com/yeatu/obsidianGP/issues/81).


## 5. Передача E → A → E и обновление панели

Нормативные правила находятся в [Issue #20](https://github.com/yeatu/obsidianGP/issues/20). После каждого перехода исполнитель или аналитик обновляет свою строку через PR. Координатор вправе обновлять весь active register и архитектурные указания. Панель остаётся кратким снимком: Issue, PR, commit и Actions — источники истины.

C принимает архитектурные, security, cross-module, milestone и integration результаты только после проверки точного HEAD и evidence. Обычные leaf-задачи внутри утверждённого scope принимает независимый A. Никакой CLAIM или merge не отменяет ограничений #53, #75, #81 либо иных актуальных C/owner decisions.


Из панели удаляются только строки. GitHub Issues, комментарии, PR, commits и evidence сохраняются. Issue/PR/commit/Actions остаются источниками истины; панель — только краткий список следующего действия.
