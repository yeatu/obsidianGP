# SFRA — оперативная панель

> Точка входа для AI-участников и снимок активной работы. Нормативные правила — [Issue #20, Governance Protocol v2.4](https://github.com/yeatu/obsidianGP/issues/20).
> GitHub Issue — источник истины по задаче. Эта панель показывает только активные задачи и не дублирует CLAIM, review, CI или evidence.

**Снимок:** 2026-11-18 (C3 refresh after PR #87 / W1 handoff)  
**main base for this dashboard update:** `9ba9d0403de0683c97938d0d323d96799157fc57`  
**Базовая версия кода:** `9ba9d0403de0683c97938d0d323d96799157fc57`

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
- Облачная доступность исходных данных и компьютер-независимый import/sync остаются отдельным нерешённым этапом [#86](https://github.com/yeatu/obsidianGP/issues/86). До его анализа и отдельного C/owner approval реальный Vault не подключать.
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
| [#42](https://github.com/yeatu/obsidianGP/issues/42) | P1 | `IMPLEMENTATION` | **E** | Исправить benchmark integrity/gate findings, обновить PR к current main, повторить 42 synthetic cases и выпустить exact-head report | E1 CLAIM; PR #84 Draft на старой base `3388e040…`; report: 40/42 gates passed, два gate failures и отдельный completeness invariant; rebase на `9ba9d040…` и rerun обязательны; не ослаблять assertions |
| [#77](https://github.com/yeatu/obsidianGP/issues/77) | P1 | `IMPLEMENTATION` | **E** | Обновить W1 branch к текущему main, повторить exact-head fixture CI, затем передать на новый A review; позже отдельно провести один marked synthetic `issues.opened` round-trip | E2 CLAIM; PR #92 HEAD `e78576f483c688aa01f633e9293257416bc0778f`; прежний run #44240799599: 44 passed на старой base `2051d0…`; review #97 закрыт как stale после merge PR #87; текущий main `9ba9d040…` |
| [#86](https://github.com/yeatu/obsidianGP/issues/86) | P1 | `ANALYSIS` | **A** | Спроектировать cloud data plane и computer-independent import/sync; сравнить durable storage и каналы публикации | A1 CLAIM; analysis-only; не читать/экспортировать/переносить production Vault |

**На HOLD по решению владельца:** Local MCP-only Issues #38/#39/#40/#43/#72. Все ранее созданные code/tests/docs/branches/PRs сохранены; не продолжать и не merge без explicit owner re-scope. PR #47/#57/#66/#94 остаются Draft/HOLD. Review #95 закрыт как not planned для MCP-only кода. #53 закрыта после owner waiver на удаление старого публичного run/artifact; сам real-Vault workflow остаётся выключенным.

**Завершено / принято:** #36/#51/#67/#79 — cumulative verifier chain merged and accepted; #88 A review accepted; #96 C1 decision; #91 C2 decision по W1 exact-head CI path; #97 closed as stale because PR #92 base moved; #75 cloud-only Web direction; #80 W1 preflight findings incorporated into #77; #81 threat model; #53 retention/removal waiver. #35 — исторический Local MCP milestone, его история не переписывается.
## 2.1. Новое правило декомпозиции: parallel-first

По Governance Protocol v2.4 (§5) каждую новую крупную задачу сначала разбиваем на минимальные самостоятельно полезные и проверяемые результаты. Для каждого пакета фиксируются один владелец, целевая роль, deliverable, затрагиваемые компоненты/файлы, прямые блокирующие зависимости, конфликты и интеграционная граница. Родительская связь не считается зависимостью автоматически. Независимые анализ, контракты, компоненты, тестовые наборы, fixtures, документация и conformance-проверки открываются отдельными Issues, когда их можно завершать параллельно. Не создаём микрозадачи без собственного результата и не расширяем scope ради занятости.

## 3. Открытые PR

| PR | Состояние | Трактовка |
|---|---|---|
| [#92 — synthetic Web adapter W1](https://github.com/yeatu/obsidianGP/pull/92) | Открыт / awaiting rebase | HEAD `e78576f483c688aa01f633e9293257416bc0778f`; base `2051d0ce6cdbceab1fc825c617708f8255266476` устарела после PR #87 merge; run #44240799599: 44 passed на прежней merge-ref; rebase на `9ba9d040…` и новый exact-head CI обязательны до нового A review |
| [#84 — synthetic gold benchmark](https://github.com/yeatu/obsidianGP/pull/84) | Открыт / Draft / stale base | HEAD `a16698266f5ceafa27ef4174a067517ca346663e`; base `3388e040…` predates PR #87 merge; prior fixture report 40/42 with unresolved failures; E1 must rebase to `9ba9d040…` and rerun before final review |
| [#47 — historical Local MCP bootstrap](https://github.com/yeatu/obsidianGP/pull/47) | Открыт / Draft / HOLD | Preserved, not a target, do not merge |
| [#57 — historical MCP search adapter](https://github.com/yeatu/obsidianGP/pull/57) | Открыт / Draft / HOLD | Preserved; no further MCP-only work or merge |
| [#66 — historical read_source parser preparation](https://github.com/yeatu/obsidianGP/pull/66) | Открыт / Draft / HOLD | Accepted parser-only slice preserved for possible adaptation |
| [#94 — historical MCP schema correction](https://github.com/yeatu/obsidianGP/pull/94) | Открыт / Draft / HOLD | E3 completed exact-head work and CI; do not spend A review or merge while MCP is off target |
| [#87 — PinnedSnapshot exact-type correction](https://github.com/yeatu/obsidianGP/pull/87) | **Merged** | Main merge `9ba9d0403de0683c97938d0d323d96799157fc57`; A1 and C1 accepted |
| [#54 / #70 — prior verifier attempts](https://github.com/yeatu/obsidianGP/pulls) | **Closed / superseded** | Their accepted cumulative correction is in merged PR #87; branch/commit/review history preserved |
| [#85 — earlier W1 implementation branch](https://github.com/yeatu/obsidianGP/pull/85) | **Closed / superseded** | Current W1 delivery is PR #92 |
| [#44 — previous governance dashboard branch](https://github.com/yeatu/obsidianGP/pull/44) | **Closed / superseded** | Old dashboard PR and review #99 are closed; branch, commits and review history remain preserved |


## 4. Действующие ограничения и решения

- **Cloud-only runtime:** ChatGPT Web/mobile → GitHub Issues → Actions → GitHub-hosted runners → SFRA. No personal computer, self-hosted runner, local daemon/tunnel or MCP transport.
- **Durable source data:** cloud storage/index/snapshot/manifest/sidecar design remains unapproved and is analyzed only in #86. GitHub-hosted runner workspace is ephemeral, not the data store.
- **Publication:** publication of Vault content and source-derived metadata is allowed by owner preference; do not impose blanket confidentiality redaction. Protect credentials/secrets and preserve provenance/integrity. Select delivery channels based on size, cost, retention and usefulness.
- **Production boundary:** permission to publish content does not authorize real Vault reads, import, indexing, production Actions execution, write or mutation. The #53 real-Vault workflow remains disabled. Any new cloud-backed real-data path needs #86 design, independent review and explicit C/owner activation decision.
- **W1 #77 / PR #92:** synthetic-only. The fixture CI event proves 44 tests, not a live Issue round-trip; worker job is skipped for pull_request event. Keep the worker dormant until E2 rebases PR #92 to current main, exact-head fixture CI passes, a fresh independent A review of that HEAD is accepted, and C separately accepts/merges the synthetic-only workflow. Review #97 is closed as stale and must not be reused. Only then authorize one marked synthetic `issues.opened` round-trip.
- **PinnedSnapshot:** shared verifier guard is accepted/merged at #87. This does **not** enable production `read_source`. A future Web composition needs its own reviewed source/data-plane path and C/owner decision after #86.
- **Local MCP legacy work:** Issues #38/#39/#40/#43/#72 and PRs #47/#57/#66/#94 are preserved on HOLD; no new CLAIM, review, implementation or merge without explicit owner re-scope.
- **Benchmark #42:** synthetic-only. Keep exact corpus schema/digest/reference/span/hash checks. A failed quality gate remains failed; don't weaken forbidden-node or completeness assertions.
- Do not add embeddings/vector search, alter retrieval ranking or change E3 token budget before benchmark evidence. Never report truncated source text as complete.
- Governance protocol: [#20](https://github.com/yeatu/obsidianGP/issues/20); cloud-only Web decision: [#75](https://github.com/yeatu/obsidianGP/issues/75); cloud data-plane analysis: [#86](https://github.com/yeatu/obsidianGP/issues/86); verifier threat model: [#81](https://github.com/yeatu/obsidianGP/issues/81).


## 5. Передача E → A → E и обновление панели

Нормативные правила находятся в [Issue #20](https://github.com/yeatu/obsidianGP/issues/20). После каждого перехода исполнитель или аналитик обновляет свою строку через PR. Координатор вправе обновлять весь active register и архитектурные указания. Панель остаётся кратким снимком: Issue, PR, commit и Actions — источники истины.

C принимает архитектурные, security, cross-module, milestone и integration результаты только после проверки точного HEAD и evidence. Обычные leaf-задачи внутри утверждённого scope принимает независимый A. Никакой CLAIM или merge не отменяет ограничений #53, #75, #81 либо иных актуальных C/owner decisions.


Из панели удаляются только строки. GitHub Issues, комментарии, PR, commits и evidence сохраняются. Issue/PR/commit/Actions остаются источниками истины; панель — только краткий список следующего действия.
