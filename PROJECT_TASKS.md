# SFRA — оперативная панель проекта

> Краткая сводка текущего состояния и навигация по активной работе.  
> **Источник истины по задаче:** соответствующая GitHub Issue и её последние действующие события.  
> **Нормативный протокол:** [Issue #20 — Governance Protocol v2](https://github.com/yeatu/obsidianGP/issues/20).  
> Этот файл не заменяет Issues и не хранит дублирующие CLAIM, review или CI evidence.

**Снимок проверен:** 2026-11-18  
**Main HEAD before this dashboard update:** `2795307045bc2af98bc918daffe1d688e4418cd2`  
**Последний кодовый baseline:** `bb2275ece19f3d7cf1aa655b89d8d037803976c6`

## 1. Текущий этап

**SFRA MVP — Local Retrieval Interface + Measured Quality.**

Координаторское решение и декомпозиция зафиксированы в [Issue #35](https://github.com/yeatu/obsidianGP/issues/35), закрытой после создания дочерних задач.

Цели этапа:
- закрыть остаточную границу верификации PinnedSnapshot;
- реализовать локальный stateless MCP stdio server с двумя read-only инструментами: `search_vault` и `read_source`;
- подтвердить качество цепочки E2 → E3 → Context Pack на 30–50 synthetic gold cases.

В main уже находятся E1 structural indexing/source API, E2 lexical retrieval, E3/B1 Context Builder/integration, V2.1 application services и V2.2 non-production Issue core.

**Важное уточнение по A1-03:** regression на замену sidecar во время E1 read уже присутствует в `test_snapshot.py`. Реализация guard и correction capability завершены на [PR #54](https://github.com/yeatu/obsidianGP/pull/54), точный HEAD `f234c5e2de0f8ed8684a8605bafc50d83abf5d74`; fixture-only C1/V2.1/V2.2 CI успешно прошёл. Исходная [Issue #36](https://github.com/yeatu/obsidianGP/issues/36) и correction [#51](https://github.com/yeatu/obsidianGP/issues/51) находятся в REVIEW через [запрос #55](https://github.com/yeatu/obsidianGP/issues/55). До независимой приёмки и C acceptance guard не считается завершённым для зависимых интеграций. [A1 follow-up](https://github.com/yeatu/obsidianGP/issues/19#issuecomment-6964082653) остаётся в истории #19.

## 2. Активные задачи

Таблица отражает текущие открытые work items. Доступность для CLAIM определяется последними событиями и выполненными зависимостями в самой Issue; REVIEW_REQUEST и COORDINATOR_DECISION не являются реализационными задачами.

| Issue | Приоритет | Тип | Задача / следующий результат | Зависимости |
|---|---:|---|---|---|
| [#34](https://github.com/yeatu/obsidianGP/issues/34) | P2 | REVIEW_REQUEST | Независимый post-merge audit Governance Protocol v2 | Нет; параллельно |
| [#55](https://github.com/yeatu/obsidianGP/issues/55) | P1 | REVIEW_REQUEST | Независимая повторная проверка PinnedSnapshot verifier guard (#36/#51) по точному HEAD | PR #54, HEAD `f234c5e2de0f8ed8684a8605bafc50d83abf5d74`; C acceptance перед подключением `read_source` |
| [#65](https://github.com/yeatu/obsidianGP/issues/65) | P2 | REVIEW_REQUEST | Независимая проверка локального MCP stdio scaffold/composition (#38 / PR #47) | Точный HEAD и fixture-only CI в #65; C acceptance до интеграции handlers |
| [#39](https://github.com/yeatu/obsidianGP/issues/39) | P2 | IMPLEMENTATION | `search_vault` adapter поверх SearchVaultService | #37 принят; #38 ожидает #65/A+C acceptance |
| [#40](https://github.com/yeatu/obsidianGP/issues/40) | P2 | IMPLEMENTATION | `read_source` adapter поверх ReadSourceService | #55/#36 guard acceptance, #37 принято, #65/#38 C acceptance |
| [#61](https://github.com/yeatu/obsidianGP/issues/61) | P1 | COORDINATOR_DECISION | Принять synthetic gold corpus v1 для #41 / PR #58 | A1 передал corpus; координаторское решение ожидается |
| [#42](https://github.com/yeatu/obsidianGP/issues/42) | P1 | IMPLEMENTATION | End-to-end benchmark runner и метрики Context Pack | #61 acceptance corpus v1 |
| [#43](https://github.com/yeatu/obsidianGP/issues/43) | P2 | IMPLEMENTATION | MCP conformance, read-only/security checks и quickstart | #36–#40 |


## 3. Порядок параллельной работы

**Независимые передачи на проверку:** #55 (PinnedSnapshot verifier) и #65 (MCP composition) ожидают A; #61 ожидает решения C по quality corpus.  
**Tool handlers:** #39 имеет владельца E1 и может готовить отдельный handler slice; runtime integration ждёт принятия #38 через #65. #40 имеет владельца E3; read_source остаётся отключённым до принятия #36/#51 и #38.  
**Quality runner:** #42 после координаторского принятия corpus v1 в #61.  
**Финальная интеграция:** #43 после принятия guard/composition и завершения #39/#40.

Родительская запись #35 закрыта как завершённое координаторское решение. Это не означает завершение milestone: дочерние Issues остаются активными.

## 4. Открытые PR, требующие контекстного учёта

| PR | Состояние | Трактовка |
|---|---|---|
| [#54 — PinnedSnapshot verifier correction](https://github.com/yeatu/obsidianGP/pull/54) | OPEN / READY | Correction PR for #36/#51; exact HEAD and fixture-only CI evidence are recorded in [review request #55](https://github.com/yeatu/obsidianGP/issues/55). Do not merge before independent review and Coordinator disposition where required. |
| [#47 — Local MCP stdio bootstrap](https://github.com/yeatu/obsidianGP/pull/47) | OPEN / READY | Composition handoff for #38; independent A review in #65 and C acceptance required before handler integration. |
| [#58 — Synthetic gold corpus v1](https://github.com/yeatu/obsidianGP/pull/58) | OPEN / READY | A1 deliverable for #41, awaiting coordinator decision #61. |
| [#12 — GitHub Issue Worker and Recovery proposal](https://github.com/yeatu/obsidianGP/pull/12) | OPEN / DRAFT | Отдельное предложение по GitHub transport/worker/recovery. Не входит в текущий milestone и не разрешает production worker, recovery, real Issue writes, event workflows или публикацию source content. |
| [#1 — structural indexer v1](https://github.com/yeatu/obsidianGP/pull/1) | OPEN | Исторический PR раннего прототипа; не активная задача текущего этапа. Не объединять без отдельного решения координатора. |
| [#2 — structural indexer pytest harness](https://github.com/yeatu/obsidianGP/pull/2) | OPEN | Исторический PR раннего тестового стенда; не активная задача текущего этапа. Не объединять без отдельного решения координатора. |

## 5. Действующие ограничения

- [Issue #20](https://github.com/yeatu/obsidianGP/issues/20) — нормативный протокол CLAIM, динамических функций, декомпозиции, review, эскалации и полномочий координатора.
- [Issue #34](https://github.com/yeatu/obsidianGP/issues/34) — независимая проверка Governance v2. Она продолжается параллельно и не блокирует независимые инженерные задачи, если reviewer не обнаружит затрагивающий их governance defect.
- GitHub Issue Worker/Recovery, GitHub API writes, remote MCP HTTP/SSE/WebSocket, production indexing/persistence и публикация содержимого Vault в публичные Issues/comments не разрешаются этим milestone.
- MCP MVP ограничен локальным stdio и двумя read-only tools. Не добавлять произвольный доступ к файловой системе или write tools.
- E1 routine CI должен оставаться fixture-only. Не индексировать реальный Vault ради проверки задач.
- Не включать embeddings/vector search или ranking changes до появления benchmark evidence.
- Бюджет контекста остаётся под контролем E3. Нельзя обрезать source text и представлять неполный результат как complete.

## 6. Правила ведения панели

1. Координатор поддерживает этот файл как короткий снимок активной работы, а не как хронику.
2. Для каждой активной задачи указываются Issue, приоритет, тип, следующий результат и зависимости. Фактический владелец берётся из последнего действующего CLAIM в Issue.
3. Подробные findings, отчёты, review, CI runs, артефакты и HEAD-specific evidence остаются в соответствующей Issue, PR, commit или Actions run.
4. Завершённые задачи удаляются из активной таблицы. История остаётся в GitHub и Git.
5. Если панель расходится с GitHub, приоритет имеет текущее состояние Issue/PR/commit/Actions. Панель исправляется, но не переопределяет источник истины.

---

**Рабочее правило:** открой эту панель, чтобы понять, что активно, какие зависимости существуют и какой этап развивается. Точный статус и права на CLAIM всегда проверяй в самой Issue.
