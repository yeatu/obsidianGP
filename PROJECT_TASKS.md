# SFRA — оперативная панель проекта

> Краткая сводка текущего состояния и точка входа для любой новой нейросети, подключающейся к работе.  
> **Источник истины по конкретной задаче:** соответствующая GitHub Issue и её последние действующие события.  
> **Нормативный протокол:** [Issue #20 — Governance Protocol v2.1](https://github.com/yeatu/obsidianGP/issues/20).  
> Этот файл не заменяет Issues и не хранит дублирующие CLAIM, review или CI evidence.

**Снимок проверен:** 2026-11-18  
**Main HEAD before this dashboard update:** `11ce3f2bd02e5bb9fb6974e1735aaacd0637846b`  
**Последний кодовый baseline:** `bb2275ece19f3d7cf1aa655b89d8d037803976c6`

## 0. Как новой нейросети начать работу

Не требуется отдельное назначение задачи пользователем или координатором. Прочитай эту панель, выбери свободную задачу своей роли, самостоятельно зафиксируй CLAIM и начинай работу.

### Роли

- **E — исполнитель.** Захватывает задачи `IMPLEMENTATION` и `INTEGRATION`.
- **A — аналитик.** Захватывает задачи `ANALYSIS` и `REVIEW_REQUEST`, включая независимый аудит.
- **Coordinator — координатор.** Только координатор захватывает `COORDINATOR_DECISION`; полномочия координатора определены в Issue #20.

Буква в Agent ID определяет роль. `E1`, `E2`, `E3` — участники одной роли E; `A1`, `A2`, `A3` — участники одной роли A. Цифра нужна только для уникальности участника. Она не задаёт старшинство, приоритет, исключительное право на конкретную задачу или запрет на её захват другим участником той же роли.

### Если у тебя ещё нет Agent ID

Сохрани Agent ID/роль, если они уже заданы средой или предыдущей договорённостью проекта. Если идентификатора нет, выбери роль по типу подходящей задачи и зарегистрируй следующий свободный номер этой роли: например, новый исполнитель может стать `E4`, новый аналитик — `A4`. Перед выбором проверь последние CLAIM и активные идентификаторы в GitHub, чтобы не дублировать действующий ID. Нумерация E и A независимая. Никакой автоматизации или предварительного назначения не требуется.

### Порядок самостоятельного CLAIM

1. Найди в таблице ниже задачу, тип которой соответствует твоей роли.
2. Выбери задачу без действующего владельца, без статуса BLOCKED и с выполненными зависимостями. Для зависимой задачи дождись выполнения перечисленных предварительных условий.
3. Открой её GitHub Issue. Проверь state, описание, критерии приёмки, scope, последние комментарии, действующие CLAIM/RELEASE/BLOCKED/REVIEW и пересекающуюся работу в соседних Issues/PR. Панель является навигацией, а не заменой этой проверки.
4. Опубликуй в Issue комментарий:
   ```
   CLAIM
   Task: #<issue>
   Agent: <E<n>|A<n>>
   Role: <E|A>
   Scope: <что именно беру>
   Started: <UTC timestamp>
   ```
5. Сразу повторно прочитай комментарии Issue. При одновременном захвате действует корректный CLAIM с наименьшим GitHub comment ID. Если твой CLAIM проиграл, прекрати пересекающуюся работу и зафиксируй `CLAIM_CONFLICT_YIELD`.
6. После успешной повторной проверки немедленно начинай работу. Не жди подтверждения координатора и не проси пользователя назначить задачу, если подходящая свободная задача существует.
7. В ходе работы публикуй `PROGRESS`, фиксируй evidence в Issue/PR/commit/Actions. По завершении самостоятельно создай `REVIEW_REQUEST`; независимый reviewer должен быть участником роли A и не должен участвовать в проверяемом результате.

**Запрещено:** E не захватывает задачи роли A, A не захватывает задачи роли E. Цифровой суффикс не меняет ролевые права. Если подходящей свободной задачи своей роли нет, проверь готовые подзадачи и зависимости и следуй §10 Issue #20.

## 1. Текущий этап

**SFRA MVP — Local Retrieval Interface + Measured Quality.**

Координаторское решение и декомпозиция зафиксированы в [Issue #35](https://github.com/yeatu/obsidianGP/issues/35), закрытой после создания дочерних задач.

Цели этапа:
- закрыть остаточную границу верификации PinnedSnapshot;
- реализовать локальный stateless MCP stdio server с двумя read-only инструментами: `search_vault` и `read_source`;
- подтвердить качество цепочки E2 → E3 → Context Pack на 30–50 synthetic gold cases.

В main уже находятся E1 structural indexing/source API, E2 lexical retrieval, E3/B1 Context Builder/integration, V2.1 application services и V2.2 non-production Issue core.

**Важное уточнение по A1-03:** regression на замену sidecar во время E1 read уже присутствует в текущем main (`test_snapshot.py`). Остаточный вопрос уже: публичный `PinnedSnapshot` допускает отсутствие активного verifier, а `verify_current()` тогда становится no-op. Это вынесено в [Issue #36](https://github.com/yeatu/obsidianGP/issues/36). [A1 follow-up](https://github.com/yeatu/obsidianGP/issues/19#issuecomment-6964082653) и координаторская disposition остаются в истории #19; сама #19 не переоткрывается.

## 2. Активные задачи

Целевая роль определяется типом по §4 Governance Protocol. Свободность и готовность к старту всегда подтверждай в самой Issue: открытая задача не считается свободной, если у неё есть действующий CLAIM, BLOCKED или невыполненные зависимости.

| Issue | Приоритет | Тип | Роль | Задача / следующий результат | Зависимости / условие старта |
|---|---:|---|:---:|---|---|
| [#34](https://github.com/yeatu/obsidianGP/issues/34) | P2 | REVIEW_REQUEST | **A** | Независимый аудит Governance Protocol v2.1 и этой панели | Проверить PR #44 и Issue #20; после merge сверить актуальный main HEAD |
| [#36](https://github.com/yeatu/obsidianGP/issues/36) | P1 | IMPLEMENTATION | **E** | Обязательный активный verifier для PinnedSnapshot до любого E1 read | Нет |
| [#37](https://github.com/yeatu/obsidianGP/issues/37) | P1 | ANALYSIS | **A** | Shared MCP tool contracts и SnapshotRef continuity для stateless вызовов | Нет |
| [#38](https://github.com/yeatu/obsidianGP/issues/38) | P2 | IMPLEMENTATION | **E** | Локальный MCP stdio scaffold, конфигурация и composition root | Можно начать bootstrap/lifecycle; public signatures не фиксировать до #37 |
| [#39](https://github.com/yeatu/obsidianGP/issues/39) | P2 | IMPLEMENTATION | **E** | `search_vault` adapter поверх SearchVaultService | Начать после #37 и #38 |
| [#40](https://github.com/yeatu/obsidianGP/issues/40) | P2 | IMPLEMENTATION | **E** | `read_source` adapter поверх ReadSourceService | Начать после #36, #37 и #38 |
| [#41](https://github.com/yeatu/obsidianGP/issues/41) | P1 | ANALYSIS | **A** | 30–50 synthetic gold cases с обязательными Node IDs и критическими условиями | Нет; параллельно |
| [#42](https://github.com/yeatu/obsidianGP/issues/42) | P1 | IMPLEMENTATION | **E** | End-to-end benchmark runner и метрики Context Pack | Начать после утверждения gold corpus в #41 |
| [#43](https://github.com/yeatu/obsidianGP/issues/43) | P2 | IMPLEMENTATION | **E** | MCP conformance, read-only/security checks и quickstart | Начать после #36–#40 |

## 3. Порядок параллельной работы

**Можно начинать независимо при условии, что Issue свободна:** #36 (E), #37 (A), #41 (A), #34 (A, независимый audit).  
**Bootstrap lane:** #38 (E) может начать базовый stdio lifecycle и конфигурацию, пока #37 фиксирует public signatures.  
**Tool handlers:** #39 (E) после #37/#38; #40 (E) после #36/#37/#38.  
**Quality runner:** #42 (E) после утверждения gold corpus #41.  
**Финальная интеграция:** #43 (E) после двух handlers и snapshot guard.

Родительская запись #35 закрыта как завершённое координаторское решение. Это не означает завершение milestone: дочерние Issues остаются активными.

## 4. Открытые PR, требующие контекстного учёта

| PR | Состояние | Трактовка |
|---|---|---|
| [#12 — GitHub Issue Worker and Recovery proposal](https://github.com/yeatu/obsidianGP/pull/12) | OPEN / DRAFT | Отдельное предложение по GitHub transport/worker/recovery. Не входит в текущий milestone и не разрешает production worker, recovery, real Issue writes, event workflows или публикацию source content. |
| [#1 — structural indexer v1](https://github.com/yeatu/obsidianGP/pull/1) | OPEN | Исторический PR раннего прототипа; не активная задача текущего этапа. Не объединять без отдельного решения координатора. |
| [#2 — structural indexer pytest harness](https://github.com/yeatu/obsidianGP/pull/2) | OPEN | Исторический PR раннего тестового стенда; не активная задача текущего этапа. Не объединять без отдельного решения координатора. |

## 5. Действующие ограничения

- [Issue #20](https://github.com/yeatu/obsidianGP/issues/20) — нормативный Governance Protocol v2.1: роли E/A, правила цифровой идентификации, CLAIM, декомпозиция, review, эскалация и полномочия координатора.
- [Issue #34](https://github.com/yeatu/obsidianGP/issues/34) — независимый audit v2.1. Он проверяет соответствие ролевой модели и автономного старта; не блокирует независимые инженерные задачи.
- GitHub Issue Worker/Recovery, GitHub API writes, remote MCP HTTP/SSE/WebSocket, production indexing/persistence и публикация содержимого Vault в публичные Issues/comments не разрешаются этим milestone.
- MCP MVP ограничен локальным stdio и двумя read-only tools. Не добавлять произвольный доступ к файловой системе или write tools.
- E1 routine CI должен оставаться fixture-only. Не индексировать реальный Vault ради проверки задач.
- Не включать embeddings/vector search или ranking changes до появления benchmark evidence.
- Бюджет контекста остаётся под контролем E3. Нельзя обрезать source text и представлять неполный результат как complete.

## 6. Правила ведения панели

1. Координатор поддерживает этот файл как короткий снимок активной работы и точку входа для новых участников, а не как хронику.
2. Для каждой активной задачи указываются Issue, приоритет, тип, целевая роль, следующий результат и зависимости. Фактический владелец берётся из последнего действующего CLAIM в Issue.
3. Подробные findings, отчёты, review, CI runs, артефакты и HEAD-specific evidence остаются в соответствующей Issue, PR, commit или Actions run.
4. Завершённые задачи удаляются из активной таблицы. История остаётся в GitHub и Git.
5. Если панель расходится с GitHub, приоритет имеет текущее состояние Issue/PR/commit/Actions. Панель исправляется, но не переопределяет источник истины.

---

**Рабочее правило:** начни с этой панели, выбери задачу своей роли, проверь её актуальное состояние в Issue, зафиксируй CLAIM и приступай. Точный статус и все ограничения всегда проверяй в GitHub.
