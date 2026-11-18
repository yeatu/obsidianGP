# SFRA — оперативная панель

> Точка входа для AI-участников и снимок активной работы. Нормативные правила — [Issue #20, Governance Protocol v2.4](https://github.com/yeatu/obsidianGP/issues/20).
> GitHub Issue — источник истины по задаче. Эта панель показывает только активные задачи и не дублирует CLAIM, review, CI или evidence.

**Снимок:** 2026-11-18 (C3 refresh after W1 #129 review, new #139 correction, #132/#133 analysis and CloudSnapshotRef consumer queue #134–#138)  
**main base for this dashboard update:** `4e3fb5ae464b0db8db0b3071ab2dc7f3f320d466`  
**Базовая версия кода:** `4e3fb5ae464b0db8db0b3071ab2dc7f3f320d466`

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
| [#104](https://github.com/yeatu/obsidianGP/issues/104) | P1 | `REVIEW_REQUEST` | **A** | Независимо проверить точный актуальный HEAD cloud-only панели PR #103 | Previous A verdict applies only to superseded panel heads. This C3 refresh adds W1 correction #139, exact PR #127/#84 status and queued cloud consumer tasks #134/#136–#138. Fresh A CLAIM must target the exact HEAD recorded in #104 after this commit; no merge before A acceptance and separate C decision |
| [#109](https://github.com/yeatu/obsidianGP/issues/109) | P1 | `REVIEW_REQUEST` | **A** | После #121 и финальной двойной проверки независимо проверить PR #84, метрики и сохранённые failed gates | Current PR #84 HEAD `9f1a9fd9ec432518162f353c540604e5f65a8c3f`; metadata base `8e853783b8ccd47571e7402c57b9e935684a0b25`; current main `4e3fb5ae464b0db8db0b3071ab2dc7f3f320d466`; compare current main→HEAD 13 ahead / 0 behind. #113/#114 slices RELEASED; E1 owns #121. Final 42-case workflow must run twice only after #121 on final synchronized HEAD; then refresh #109 with exact HEAD and both artifact hashes, followed by a fresh A CLAIM. Previous A3 target is stale. Preserve all five quality findings |
| [#122](https://github.com/yeatu/obsidianGP/issues/122) | P1 | `INTEGRATION` | **E** | W1 implementation handoff completed; allowlist correction #139 has green fixture validation | E3 RELEASED after #129 returned CHANGES_REQUESTED on the old PR #92 HEAD `2dccd6057269a8860549275ae1cc7f693d47be09`. E3's #139 correction is now present on PR #92 HEAD `9db7f1b05ec21bccf992c3386e524ce16580656a`; run #44258981526 passed 56 tests, worker skipped. Formal E3 handoff and fresh A review request still required. No round-trip, merge or production action |

| [#139](https://github.com/yeatu/obsidianGP/issues/139) | P1 | `IMPLEMENTATION` | **E** | Enforce canonical gq-004-only evidence allowlist; fixture correction validated | E3 CLAIM #6971849725. PR #92 current HEAD `9db7f1b05ec21bccf992c3386e524ce16580656a`; run #44258981526 passed 56 tests, synthetic-issue-worker skipped. Earlier #44258664482 had one stale assertion-message failure, now corrected. Only `gq-004-exception-pair` and nodes `gate_rule`/`gate_exception` with pinned paths/hashes. Awaiting E3 formal RELEASE/REVIEW_HANDOFF and a fresh A review. No live Issue write, round-trip, workflow dispatch or production operation |
| [#113](https://github.com/yeatu/obsidianGP/issues/113) | P2 | `IMPLEMENTATION` | **E** | Token Efficiency baseline fix delivered; awaiting combined final benchmark validation | E1 RELEASED implementation slice on PR #84; relevant paths now include required ∪ allowed-additional nodes and deduplicate documents. Intermediate preflight had one fixture failure; no post-fix passing run is claimed. Final full run x2 after #121 |
| [#114](https://github.com/yeatu/obsidianGP/issues/114) | P2 | `IMPLEMENTATION` | **E** | Fallback Rate instrumentation fix delivered; awaiting combined final benchmark validation | E1 RELEASED implementation slice on PR #84; counts actual dependency read_scope calls separately from address resolutions, E2 reads and explicit SourceRead. Intermediate preflight had one fixture failure; no post-fix passing run is claimed. Final full run x2 after #121 |
| [#121](https://github.com/yeatu/obsidianGP/issues/121) | P2 | `IMPLEMENTATION` | **E** | Separate Pack completeness from explicit SourceRead status in benchmark | E1 CLAIM #6971085966; follows released #113/#114 on same PR #84 branch. Preserve gold corpus v1.0.0; final 42-case benchmark must run twice after this correction |
| [#117](https://github.com/yeatu/obsidianGP/issues/117) | P2 | `IMPLEMENTATION` | **E** | CloudSnapshotRef v2 delivered; correction #130 is active on PR #127 | E3 RELEASED. Current PR #127 HEAD `6fd89c896aea39e79cc6cc7d3fae2c306b7c167b`, base/current main `4e3fb5ae464b0db8db0b3071ab2dc7f3f320d466`, compare 11 ahead / 0 behind, seven changed files. A1 review #128 returned CHANGES_REQUESTED on the old HEAD `09e575936d5f342c7f2d9f711de5d53faef42ede`; that verdict/evidence does not apply to the current HEAD. E1 owns #130 (winning CLAIM #6971514735); E3's later claim yielded. No fresh passing CI/review or C acceptance is recorded yet. #118/#119/#125 remain gated |
| [#118](https://github.com/yeatu/obsidianGP/issues/118) | P2 | `IMPLEMENTATION` | **E** | Implement versioned snapshot catalogue state machine/CAS | Unclaimed; blocked until #130 correction, fresh A review and C acceptance of #117 |
| [#119](https://github.com/yeatu/obsidianGP/issues/119) | P2 | `IMPLEMENTATION` | **E** | Build and verify immutable snapshot bundles from synthetic fixtures | Unclaimed; ready in parallel with #118 only after #130 correction, fresh A review and C acceptance of #117 |
| [#120](https://github.com/yeatu/obsidianGP/issues/120) | P2 | `IMPLEMENTATION` | **E** | Read-only exact-version snapshot resolver/materializer | Unclaimed; starts after #117–#119 are independently accepted |
| [#128](https://github.com/yeatu/obsidianGP/issues/128) | P2 | `REVIEW_REQUEST` | **A** | Review of PR #127 returned CHANGES_REQUESTED; fresh review is required after #130 | A1 reviewed exact HEAD `09e575...` and created #130. Do not carry the old verdict to a corrected HEAD. #130 is E1-owned; new exact-head A review must follow the correction |
| [#125](https://github.com/yeatu/obsidianGP/issues/125) | P2 | `IMPLEMENTATION` | **E** | Immutable object upload port + synthetic in-memory writer | Unclaimed; blocked by accepted #117 and #119; no cloud SDK/credentials/provider provisioning |
| [#130](https://github.com/yeatu/obsidianGP/issues/130) | P2 | `IMPLEMENTATION` | **E** | Исправить mutable-alias whitespace и schema validation в PR #127 | E1 winning CLAIM #6971514735. E3 later competing CLAIM #6971543706 is not valid and must yield. New exact-head fixture CI and A re-review required |
| [#132](https://github.com/yeatu/obsidianGP/issues/132) | P2 | `ANALYSIS` | **A** | Спроектировать additive E1 cloud-state verifier для Git/import source revisions | A3 CLAIM #6971873835. Read-only analysis; preserve manifest v1 and legacy verifier; treat #117 fields as unaccepted until its correction/review/C gate is complete |
| [#133](https://github.com/yeatu/obsidianGP/issues/133) | P3 | `ANALYSIS` | **A** | Metadata-only inventory of source/index sizes, growth and workflow frequency | Свободна для A; no blob content, real-data access, workflow runs or provider selection
| [#134](https://github.com/yeatu/obsidianGP/issues/134) | P2 | `IMPLEMENTATION` | **E** | Add B1-owned SnapshotIdentity protocol without importing E3 cloud types | Queued behind #131 gates: accepted #117, #120 and the E1 verifier seam specified in #132, implemented/reviewed in a later C-opened task. B1 files/tests only; no early speculative consumer work |
| [#136](https://github.com/yeatu/obsidianGP/issues/136) | P2 | `IMPLEMENTATION` | **E** | Add factory-verified E3 cloud materialized handle and preserve v2 identity through E3 pipeline | Queued behind accepted #117/#120, accepted #134, and the separate E1 verifier implementation/review following #132. E3 files only; no provider code |
| [#137](https://github.com/yeatu/obsidianGP/issues/137) | P2 | `IMPLEMENTATION` | **E** | Add additive V2.2 sfra.issue.v2 request/status with snapshot_id | Queued after #136 acceptance; preserve sfra.issue.v1 and TransportStatusV2 unchanged |
| [#138](https://github.com/yeatu/obsidianGP/issues/138) | P2 | `IMPLEMENTATION` | **E** | Synthetic query-path conformance from V2.2 through B1 | Later integration after accepted #117–#120, E1 verifier implementation, #134, #136 and #137; distinct from lifecycle suite #124 |
| [#124](https://github.com/yeatu/obsidianGP/issues/124) | P3 | `IMPLEMENTATION` | **E** | Сквозной synthetic conformance suite для snapshot lifecycle | Unclaimed later integration task; blocked until #117–#120 and #125 accepted |


**На HOLD по решению владельца:** Local MCP-only Issues #38/#39/#40/#43/#72. Все ранее созданные code/tests/docs/branches/PRs сохранены; не продолжать и не merge без explicit owner re-scope. PR #47/#57/#66/#94 остаются Draft/HOLD. Review #95 закрыт как not planned для MCP-only кода. #53 закрыта после owner waiver на удаление старого публичного run/artifact; сам real-Vault workflow остаётся выключенным.

**Завершено / принято:** #112 — C3 cloud data-plane/legacy workflow decision completed; #116 — A1 legacy E1 workflow assessment accepted by C3 and closed (10 historical successful runs; present Actions enablement remains unknown; workflow unchanged); #123 — A1 CloudSnapshotRef consumer-integration analysis accepted by C3 and closed; #131 — C3 accepted the additive B1/E3/V2.1/V2.2 integration boundary and opened E1 verifier analysis #132; #15 / PR #16 — V2.2 non-production Issue Worker Core accepted and merged (merge commit `05a067e1348b2871e403159f060d49b61d4fef7d`); #18 / PR #21 — E2 synthetic lexical baseline accepted and merged (`2bb84ea536e60605c33be3bb03f5a4da7dee30af`); #115 — C3 disposition for E2 false positives and SourceRead/ContextPack semantics; #36/#51/#67/#79 — cumulative verifier chain merged and accepted; #88 A review accepted; #96 C1 decision; #91 C2 decision по W1 exact-head CI path; #97 closed as stale because PR #92 base moved; #75 cloud-only Web direction; #80 W1 preflight findings incorporated into #77; #81 threat model; #53 retention/removal waiver; #86 cloud data-plane analysis accepted by C3 in #112, report PR #107 merged (commit `8e853783b8ccd47571e7402c57b9e935684a0b25`). #35 — исторический milestone, его история не переписывается. #129 — A3 review completed with CHANGES_REQUESTED; correction #139 is active. #131 — C3 consumer-integration decision completed. #135 — premature E1 implementation placeholder closed as not planned before #132 review; no work or code change was performed and its history remains. #129 — independent W1 review completed with CHANGES_REQUESTED; its correction is tracked in #139. #131 — C3 integration decision completed. #135 — premature E1 implementation placeholder closed as not planned before #132 analysis; no work was performed and history is preserved.
## 2.1. Новое правило декомпозиции: parallel-first

По Governance Protocol v2.4 (§5) каждую новую крупную задачу сначала разбиваем на минимальные самостоятельно полезные и проверяемые результаты. Для каждого пакета фиксируются один владелец, целевая роль, deliverable, затрагиваемые компоненты/файлы, прямые блокирующие зависимости, конфликты и интеграционная граница. Родительская связь не считается зависимостью автоматически. Независимые анализ, контракты, компоненты, тестовые наборы, fixtures, документация и conformance-проверки открываются отдельными Issues, когда их можно завершать параллельно. Не создаём микрозадачи без собственного результата и не расширяем scope ради занятости.

## 3. Открытые PR

| PR | Состояние | Трактовка |
|---|---|---|
| [#92 — synthetic Web adapter W1](https://github.com/yeatu/obsidianGP/pull/92) | Открыт / W1 correction fixture CI green; fresh A review pending | HEAD `9db7f1b05ec21bccf992c3386e524ce16580656a`; base/current main `4e3fb5ae464b0db8db0b3071ab2dc7f3f320d466`; compare 87 ahead / 0 behind; 14 W1 files only. Run #44258981526 succeeded with 56 passed; `synthetic-issue-worker` skipped. This HEAD enforces canonical gq-004 query/case plus only approved `gate_rule`/`gate_exception` nodes and pinned provenance. #129's CHANGES_REQUESTED applies only to old HEAD `2dccd605...`; #139 correction done in code, awaiting E3 formal handoff and new independent A review. No synthetic round-trip or merge |
| [#84 — synthetic gold benchmark](https://github.com/yeatu/obsidianGP/pull/84) | Открыт / Draft / final correction #121 in progress | HEAD `9f1a9fd9ec432518162f353c540604e5f65a8c3f`; PR metadata base `8e853783b8ccd47571e7402c57b9e935684a0b25`; current main `4e3fb5ae464b0db8db0b3071ab2dc7f3f320d466`; compare current main→HEAD 13 ahead / 0 behind. #113/#114 slices RELEASED; #121 E1-claimed. No passing post-fix full run claimed. After #121, synchronize, run all 42 cases twice, record both artifact hashes and refresh #109; previous review evidence is stale |
| [#127 — cloud SnapshotRef v2 contract](https://github.com/yeatu/obsidianGP/pull/127) | Открыт / correction #130 active; no fresh acceptance | Current HEAD `6fd89c896aea39e79cc6cc7d3fae2c306b7c167b`, base/current main `4e3fb5ae464b0db8db0b3071ab2dc7f3f320d466`, 11 ahead / 0 behind, seven files. A1 review #128 CHANGES_REQUESTED applies only to old HEAD `09e575936d5f342c7f2d9f711de5d53faef42ede`; original 117-pass run is historical. E1 owns #130; current HEAD still needs exact-head fixture CI, fresh A review and C acceptance |
| [#47 — historical Local MCP bootstrap](https://github.com/yeatu/obsidianGP/pull/47) | Открыт / Draft / HOLD | Preserved, not a target, do not merge |
| [#57 — historical MCP search adapter](https://github.com/yeatu/obsidianGP/pull/57) | Открыт / Draft / HOLD | Preserved; no further MCP-only work or merge |
| [#66 — historical read_source parser preparation](https://github.com/yeatu/obsidianGP/pull/66) | Открыт / Draft / HOLD | Accepted parser-only slice preserved for possible adaptation |
| [#94 — historical MCP schema correction](https://github.com/yeatu/obsidianGP/pull/94) | Открыт / Draft / HOLD | E3 completed exact-head work and CI; do not spend A review or merge while MCP is off target |
| [#103 — cloud-only governance panel refresh](https://github.com/yeatu/obsidianGP/pull/103) | Открыт / latest governance refresh; independent A review #104 required | This update records W1 correction #139, CloudSnapshotRef correction #130, A3 ownership of #132, free metadata inventory #133, consumer queue #134/#136–#138, and #110 supersession. Exact HEAD/base/diff are recorded in #104 after this commit. No merge before fresh A acceptance and separate C decision |
| [#110 — W1 review handoff panel patch](https://github.com/yeatu/obsidianGP/pull/110) | **Closed / superseded** | Its narrow #122→#129 / PR #92 evidence patch is already present in current parent panel PR #103. The PR #110 branch, commits and discussion remain preserved; no branch deletion or history rewrite |
| [#107 — cloud data-plane analysis](https://github.com/yeatu/obsidianGP/pull/107) | **Merged** | C3 accepted report under #112; merge commit `8e853783b8ccd47571e7402c57b9e935684a0b25` |
| [#87 — PinnedSnapshot exact-type correction](https://github.com/yeatu/obsidianGP/pull/87) | **Merged** | Main merge `9ba9d0403de0683c97938d0d323d96799157fc57`; A1 and C1 accepted |
| [#54 / #70 — prior verifier attempts](https://github.com/yeatu/obsidianGP/pulls) | **Closed / superseded** | Their accepted cumulative correction is in merged PR #87; branch/commit/review history preserved |
| [#85 — earlier W1 implementation branch](https://github.com/yeatu/obsidianGP/pull/85) | **Closed / superseded** | Current W1 delivery is PR #92 |
| [#44 — previous governance dashboard branch](https://github.com/yeatu/obsidianGP/pull/44) | **Closed / superseded** | Old dashboard PR and review #99 are closed; branch, commits and review history remain preserved |


## 4. Действующие ограничения и решения

- **Cloud-only runtime:** ChatGPT Web/mobile → GitHub Issues → Actions → GitHub-hosted runners → SFRA. No personal computer, self-hosted runner, local daemon/tunnel or MCP transport.
- **Durable source data:** provider-neutral immutable snapshot bundles + versioned catalogue + read-only resolver/materializer are the accepted target direction in #112. #117 remains unaccepted; E1 owns #130 and the current PR #127 HEAD still needs exact-head CI/A/C acceptance. #118/#119/#125 wait for #117; #120 waits for #117–#119; #124 is later lifecycle conformance. #132 (A3-claimed) designs the E1 typed-revision verifier; #133 remains a free metadata-only sizing analysis. Consumer queue: #134 B1 identity waits for accepted #117/#120 and the E1 verifier seam; #136 E3 binding waits for those plus #134; #137 V2.2 waits for #136; #138 query-path conformance waits for all component/materializer gates. #135 was a premature E1 placeholder and is closed not planned; C will open the E1 implementation only after accepting #132 and #117. Provider, region, source authority and retention remain unselected; hosted runner workspace is ephemeral, not the data store.
- **Publication:** publication of Vault content and source-derived metadata is allowed by owner preference; do not impose blanket confidentiality redaction. Protect credentials/secrets and preserve provenance/integrity. Select delivery channels based on size, cost, retention and usefulness.
- **Production boundary:** permission to publish content does not authorize real Vault reads, import, indexing, production Actions execution, write or mutation. The E3 integration workflow remains fail-closed. Separately, `.github/workflows/sfra-state-persistence.yml` has configured push + workflow_dispatch triggers, `contents:write`, and publishes SQLite/manifest to `sfra-state`; #116 verified 10 historical successful runs but could not verify present repository Actions enablement/settings. It remains unchanged, must not be manually dispatched or deliberately triggered, and is neither approved nor required for the new data plane. Avoid changes matching its push filters. Any future workflow change requires a separate narrow decision/explicit approval.
- **W1 #77 / PR #92:** synthetic-only. A3's #129 review returned CHANGES_REQUESTED on old HEAD `2dccd605...`: runtime search/read/projection accepted non-canonical corpus cases/nodes. E3's #139 correction is now present on PR #92 HEAD `9db7f1b05ec21bccf992c3386e524ce16580656a`; exact-head fixture run #44258981526 passed 56 tests and skipped `synthetic-issue-worker`. The code now enforces only `gq-004-exception-pair` and approved nodes `gate_rule`/`gate_exception` with pinned provenance. Await E3 formal handoff and fresh A review; keep worker dormant until A acceptance and separate C merge/round-trip decision. No live Issue write or production action has occurred.
- **PinnedSnapshot:** shared verifier guard is accepted/merged at #87. This does **not** enable production `read_source`. A future Web composition needs its own reviewed cloud SnapshotRef provider/materializer and response-worker path, then a separate C/owner activation decision under #112.
- **Local MCP legacy work:** Issues #38/#39/#40/#43/#72 and PRs #47/#57/#66/#94 are preserved on HOLD; no new CLAIM, review, implementation or merge without explicit owner re-scope.
- **Benchmark #42:** synthetic-only. Keep exact corpus schema/digest/reference/span/hash checks. A failed quality gate remains failed; don't weaken forbidden-node or completeness assertions.
- Do not add embeddings/vector search, alter retrieval ranking or change E3 token budget before benchmark evidence. Never report truncated source text as complete.
- Governance protocol: [#20](https://github.com/yeatu/obsidianGP/issues/20); cloud-only Web decision: [#75](https://github.com/yeatu/obsidianGP/issues/75); cloud data-plane analysis: [#86](https://github.com/yeatu/obsidianGP/issues/86); cloud architecture decision: [#112](https://github.com/yeatu/obsidianGP/issues/112); verifier threat model: [#81](https://github.com/yeatu/obsidianGP/issues/81).


## 5. Передача E → A → E и обновление панели

Нормативные правила находятся в [Issue #20](https://github.com/yeatu/obsidianGP/issues/20). После каждого перехода исполнитель или аналитик обновляет свою строку через PR. Координатор вправе обновлять весь active register и архитектурные указания. Панель остаётся кратким снимком: Issue, PR, commit и Actions — источники истины.

C принимает архитектурные, security, cross-module, milestone и integration результаты только после проверки точного HEAD и evidence. Обычные leaf-задачи внутри утверждённого scope принимает независимый A. Никакой CLAIM или merge не отменяет ограничений #53, #75, #81 либо иных актуальных C/owner decisions.


Из панели удаляются только строки. GitHub Issues, комментарии, PR, commits и evidence сохраняются. Issue/PR/commit/Actions остаются источниками истины; панель — только краткий список следующего действия.
