# SFRA — оперативная панель

> Точка входа для AI-участников и снимок активной работы. Нормативные правила — [Issue #20, Governance Protocol v2.4](https://github.com/yeatu/obsidianGP/issues/20).
> GitHub Issue — источник истины по задаче. Эта панель показывает только активные задачи и не дублирует CLAIM, review, CI или evidence.

**Снимок:** 2026-11-18 (C3 refresh after cloud-data decision #112 and PR #107 merge)  
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

**Quality:** accepted synthetic gold corpus v1.0.0 — 42 cases, 32 synthetic docs, 69 nodes (PR #58). End-to-end benchmark [#42](https://github.com/yeatu/obsidianGP/issues/42) остаётся активной shared-core quality задачей и работает только на disposable fixtures.
## 2. Активные задачи

Таблица отражает актуальные задачи целевого cloud/Web направления и shared-core quality/security. Источники истины — Issue/PR/commit/Actions; CLAIM и зависимости повторно проверяются в соответствующей Issue.

| Issue | Приоритет | Тип | Роль | Следующий результат | Зависимости / владелец |
|---|---:|---|:---:|---|---|
| [#109](https://github.com/yeatu/obsidianGP/issues/109) | P1 | `REVIEW_REQUEST` | **A** | Независимый аудит benchmark #42 и пяти сохранённых failed gates | A3 CLAIM на PR #84 HEAD `a18e2b27c02cf3e772768aa0ce01b7ccf0e4b0d5`; base `8e853783b8ccd47571e7402c57b9e935684a0b25` устарела относительно current main `4e3fb5ae464b0db8db0b3071ab2dc7f3f320d466`; текущая compare: 4 ahead / 5 behind. E1 sync + exact-head CI/evidence before verdict; не ослаблять пять failed gates |
| [#77](https://github.com/yeatu/obsidianGP/issues/77) | P1 | `IMPLEMENTATION` | **E** | Синхронизировать W1 PR #92 с current main, повторить exact-head fixture CI и передать на свежий независимый A review | E3 завершил предыдущую синхронизацию и RELEASE; PR #92 HEAD `593521b66f1adeb8fc5bb29d41a305855d8204b2`, base `52f1bdda1dd6b281b1fbe91add06e5fceda541fe`; current main `4e3fb5ae464b0db8db0b3071ab2dc7f3f320d466` (5 commits behind); A1 RELEASED #108 after BLOCKED. Task is available to a free eligible E; no worker round-trip or production action |
| [#112](https://github.com/yeatu/obsidianGP/issues/112) | P1 | `COORDINATOR_DECISION` | **C** | Получить решение владельца по статусу существующего E1 persistence workflow: оставить действующим или поставить на HOLD | C3 CLAIM; выбор A/B владельца требуется до дальнейшего использования workflow |

**На HOLD по решению владельца:** Local MCP-only Issues #38/#39/#40/#43/#72. Все ранее созданные code/tests/docs/branches/PRs сохранены; не продолжать и не merge без explicit owner re-scope. PR #47/#57/#66/#94 остаются Draft/HOLD. Review #95 закрыт как not planned для MCP-only кода. #53 закрыта после owner waiver на удаление старого публичного run/artifact; сам real-Vault workflow остаётся выключенным.

**Завершено / принято:** #36/#51/#67/#79 — cumulative verifier chain merged and accepted; #88 A review accepted; #96 C1 decision; #91 C2 decision по W1 exact-head CI path; #97 closed as stale because PR #92 base moved; #75 cloud-only Web direction; #80 W1 preflight findings incorporated into #77; #81 threat model; #53 retention/removal waiver; #86 cloud data-plane analysis accepted by C3 in #112, report PR #107 merged (commit `8e853783b8ccd47571e7402c57b9e935684a0b25`). #35 — исторический milestone, его история не переписывается.
## 2.1. Новое правило декомпозиции: parallel-first

По Governance Protocol v2.4 (§5) каждую новую крупную задачу сначала разбиваем на минимальные самостоятельно полезные и проверяемые результаты. Для каждого пакета фиксируются один владелец, целевая роль, deliverable, затрагиваемые компоненты/файлы, прямые блокирующие зависимости, конфликты и интеграционная граница. Родительская связь не считается зависимостью автоматически. Независимые анализ, контракты, компоненты, тестовые наборы, fixtures, документация и conformance-проверки открываются отдельными Issues, когда их можно завершать параллельно. Не создаём микрозадачи без собственного результата и не расширяем scope ради занятости.

## 3. Открытые PR

| PR | Состояние | Трактовка |
|---|---|---|
| [#92 — synthetic Web adapter W1](https://github.com/yeatu/obsidianGP/pull/92) | Открыт / needs latest-main refresh | HEAD `593521b66f1adeb8fc5bb29d41a305855d8204b2`; base `52f1bdda1dd6b281b1fbe91add06e5fceda541fe`; current main `4e3fb5ae464b0db8db0b3071ab2dc7f3f320d466` (5 commits behind). Run #44244614340 (44 passed) applies only to its old merge-ref. A1 RELEASED review #108 after stale-base BLOCKED; sync, fresh CI and new A review are required |
| [#84 — synthetic gold benchmark](https://github.com/yeatu/obsidianGP/pull/84) | Открыт / Draft / needs latest-main refresh | HEAD `a18e2b27c02cf3e772768aa0ce01b7ccf0e4b0d5`; current PR base `8e853783b8ccd47571e7402c57b9e935684a0b25`; main `4e3fb5ae464b0db8db0b3071ab2dc7f3f320d466`; compare current main→HEAD: 4 ahead / 5 behind. Previous 42-case report artifact is bound to implementation HEAD `9d17998d401137763f2bddec904e2dcd775ac21c`, not current PR HEAD. E1 must sync, rerun and refresh #109 before review verdict |
| [#47 — historical Local MCP bootstrap](https://github.com/yeatu/obsidianGP/pull/47) | Открыт / Draft / HOLD | Preserved, not a target, do not merge |
| [#57 — historical MCP search adapter](https://github.com/yeatu/obsidianGP/pull/57) | Открыт / Draft / HOLD | Preserved; no further MCP-only work or merge |
| [#66 — historical read_source parser preparation](https://github.com/yeatu/obsidianGP/pull/66) | Открыт / Draft / HOLD | Accepted parser-only slice preserved for possible adaptation |
| [#94 — historical MCP schema correction](https://github.com/yeatu/obsidianGP/pull/94) | Открыт / Draft / HOLD | E3 completed exact-head work and CI; do not spend A review or merge while MCP is off target |
| [#103 — cloud-only governance panel refresh](https://github.com/yeatu/obsidianGP/pull/103) | Открыт / awaiting independent A review #104 | C3 refresh now targets current main `4e3fb5ae464b0db8db0b3071ab2dc7f3f320d466`; exact new HEAD, diff and compare are recorded in #104. Do not merge before fresh A acceptance and separate C decision |
| [#110 — W1 review handoff panel patch](https://github.com/yeatu/obsidianGP/pull/110) | Открыт / stacked on PR #103 branch | E3's narrow #77→#108 status patch is preserved; parent branch refresh requires E3 to re-sync this stacked PR before integration |
| [#107 — cloud data-plane analysis](https://github.com/yeatu/obsidianGP/pull/107) | **Merged** | C3 accepted report under #112; merge commit `8e853783b8ccd47571e7402c57b9e935684a0b25` |
| [#87 — PinnedSnapshot exact-type correction](https://github.com/yeatu/obsidianGP/pull/87) | **Merged** | Main merge `9ba9d0403de0683c97938d0d323d96799157fc57`; A1 and C1 accepted |
| [#54 / #70 — prior verifier attempts](https://github.com/yeatu/obsidianGP/pulls) | **Closed / superseded** | Their accepted cumulative correction is in merged PR #87; branch/commit/review history preserved |
| [#85 — earlier W1 implementation branch](https://github.com/yeatu/obsidianGP/pull/85) | **Closed / superseded** | Current W1 delivery is PR #92 |
| [#44 — previous governance dashboard branch](https://github.com/yeatu/obsidianGP/pull/44) | **Closed / superseded** | Old dashboard PR and review #99 are closed; branch, commits and review history remain preserved |


## 4. Действующие ограничения и решения

- **Cloud-only runtime:** ChatGPT Web/mobile → GitHub Issues → Actions → GitHub-hosted runners → SFRA. No personal computer, self-hosted runner, local daemon/tunnel or MCP transport.
- **Durable source data:** provider-neutral immutable snapshot bundles + versioned catalogue + read-only resolver/materializer are the accepted target direction in #112. Provider, region, source authority and retention are not selected; hosted runner workspace remains ephemeral, not the data store.
- **Publication:** publication of Vault content and source-derived metadata is allowed by owner preference; do not impose blanket confidentiality redaction. Protect credentials/secrets and preserve provenance/integrity. Select delivery channels based on size, cost, retention and usefulness.
- **Production boundary:** permission to publish content does not authorize real Vault reads, import, indexing, production Actions execution, write or mutation. The E3 integration workflow remains fail-closed. Separately, the current `.github/workflows/sfra-state-persistence.yml` has a push trigger + workflow_dispatch + `contents:write` and publishes SQLite/manifest to `sfra-state`; #112 does not authorize invoking it for the new data plane. The file is unchanged, and its Actions enablement/run history is not verified. Owner choice A/B in #112 is required before further use.
- **W1 #77 / PR #92:** synthetic-only. The fixture CI event proves 44 tests, not a live Issue round-trip; worker job is skipped for pull_request event. Keep the worker dormant until E2 rebases PR #92 to current main, exact-head fixture CI passes, a fresh independent A review of that HEAD is accepted, and C separately accepts/merges the synthetic-only workflow. Review #97 is closed as stale and must not be reused. Only then authorize one marked synthetic `issues.opened` round-trip.
- **PinnedSnapshot:** shared verifier guard is accepted/merged at #87. This does **not** enable production `read_source`. A future Web composition needs its own reviewed cloud SnapshotRef provider/materializer and response-worker path, then a separate C/owner activation decision under #112.
- **Local MCP legacy work:** Issues #38/#39/#40/#43/#72 and PRs #47/#57/#66/#94 are preserved on HOLD; no new CLAIM, review, implementation or merge without explicit owner re-scope.
- **Benchmark #42:** synthetic-only. Keep exact corpus schema/digest/reference/span/hash checks. A failed quality gate remains failed; don't weaken forbidden-node or completeness assertions.
- Do not add embeddings/vector search, alter retrieval ranking or change E3 token budget before benchmark evidence. Never report truncated source text as complete.
- Governance protocol: [#20](https://github.com/yeatu/obsidianGP/issues/20); cloud-only Web decision: [#75](https://github.com/yeatu/obsidianGP/issues/75); cloud data-plane analysis: [#86](https://github.com/yeatu/obsidianGP/issues/86); cloud architecture decision: [#112](https://github.com/yeatu/obsidianGP/issues/112); verifier threat model: [#81](https://github.com/yeatu/obsidianGP/issues/81).


## 5. Передача E → A → E и обновление панели

Нормативные правила находятся в [Issue #20](https://github.com/yeatu/obsidianGP/issues/20). После каждого перехода исполнитель или аналитик обновляет свою строку через PR. Координатор вправе обновлять весь active register и архитектурные указания. Панель остаётся кратким снимком: Issue, PR, commit и Actions — источники истины.

C принимает архитектурные, security, cross-module, milestone и integration результаты только после проверки точного HEAD и evidence. Обычные leaf-задачи внутри утверждённого scope принимает независимый A. Никакой CLAIM или merge не отменяет ограничений #53, #75, #81 либо иных актуальных C/owner decisions.


Из панели удаляются только строки. GitHub Issues, комментарии, PR, commits и evidence сохраняются. Issue/PR/commit/Actions остаются источниками истины; панель — только краткий список следующего действия.
