# SFRA — оперативная панель проекта

> Краткая сводка текущего состояния и навигация по активной работе.  
> **Источник истины по задаче:** соответствующая GitHub Issue и её последние действующие события.  
> **Нормативный протокол:** [Issue #20 — Governance Protocol v2](https://github.com/yeatu/obsidianGP/issues/20).  
> Этот файл не заменяет Issues и не хранит дублирующие CLAIM, review или CI evidence.

**Снимок проверен:** 2026-11-18  
**Main HEAD before this dashboard update:** `6f655e77a8071445544f77ee4b8c75278649e100`  
**Последний кодовый baseline:** `bb2275ece19f3d7cf1aa655b89d8d037803976c6`

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

Все задачи ниже открыты и доступны для самостоятельного CLAIM подходящим свободным участником. E/A-префикс не ограничивает захват. Фактический владелец определяется последним действующим CLAIM в соответствующей Issue.

| Issue | Приоритет | Тип | Задача / следующий результат | Зависимости |
|---|---:|---|---|---|
| [#34](https://github.com/yeatu/obsidianGP/issues/34) | P2 | REVIEW_REQUEST | Независимый post-merge audit Governance Protocol v2 | Нет; параллельно |
| [#36](https://github.com/yeatu/obsidianGP/issues/36) | P1 | IMPLEMENTATION | Обязательный активный verifier для PinnedSnapshot до любого E1 read | Нет |
| [#37](https://github.com/yeatu/obsidianGP/issues/37) | P1 | ANALYSIS | Shared MCP tool contracts и SnapshotRef continuity для stateless вызовов | Нет |
| [#65](https://github.com/yeatu/obsidianGP/issues/65) | P2 | REVIEW_REQUEST | Независимая проверка Issue #38 / PR #47 на точном HEAD 6f356763abe9b6d55dd1fc66839c6b01a7023f2d | Проверить exact HEAD; после A review требуется C acceptance по §8.7 |
| [#39](https://github.com/yeatu/obsidianGP/issues/39) | P2 | IMPLEMENTATION | `search_vault` adapter поверх SearchVaultService | #37, #38 |
| [#40](https://github.com/yeatu/obsidianGP/issues/40) | P2 | IMPLEMENTATION | `read_source` adapter поверх ReadSourceService | #36, #37, #38 |
| [#41](https://github.com/yeatu/obsidianGP/issues/41) | P1 | ANALYSIS | 30–50 synthetic gold cases с обязательными Node IDs и критическими условиями | Нет; параллельно |
| [#42](https://github.com/yeatu/obsidianGP/issues/42) | P1 | IMPLEMENTATION | End-to-end benchmark runner и метрики Context Pack | #41 |
| [#43](https://github.com/yeatu/obsidianGP/issues/43) | P2 | IMPLEMENTATION | MCP conformance, read-only/security checks и quickstart | #36–#40 |
| [#51](https://github.com/yeatu/obsidianGP/issues/51) | P1 | IMPLEMENTATION | Correction: сделать capability PinnedSnapshot verifier неизменяемым и исключить no-op bypass | #36, #46 |

## 3. Порядок параллельной работы

**Можно начинать сразу и независимо:** #36, #37, #41, #34.  
**Bootstrap lane:** #38 может начать базовый stdio lifecycle и конфигурацию, пока #37 фиксирует public signatures.  
**Tool handlers:** #39 после #37/#38; #40 после #36/#37/#38.  
**Quality runner:** #42 после утверждения gold corpus #41.  
**Финальная интеграция:** #43 после двух handlers и snapshot guard.

Родительская запись #35 закрыта как завершённое координаторское решение. Это не означает завершение milestone: дочерние Issues остаются активными.

## 4. Открытые PR, требующие контекстного учёта

| PR | Состояние | Трактовка |
|---|---|---|
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
