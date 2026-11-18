# SFRA — оперативная панель

> Точка входа для AI-участников и снимок активной работы. Нормативные правила — [Issue #20, Governance Protocol v2.4](https://github.com/yeatu/obsidianGP/issues/20).
> GitHub Issue — источник истины по задаче. Эта панель показывает только активные задачи и не дублирует CLAIM, review, CI или evidence.

**Снимок:** 2026-11-18  
**main base for this dashboard update:** `3388e0409a81b5f40c3155674fe33247ce5e044e`  
**Базовая версия кода:** `bb2275ece19f3d7cf1aa655b89d8d037803976c6`

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

## 1. Текущий этап

**Local milestone:** [Issue #35](https://github.com/yeatu/obsidianGP/issues/35) remains the approved Local MCP stdio + measured-quality decision. Its history and scope are unchanged.

**ChatGPT Web milestone:** architecture report [#63](https://github.com/yeatu/obsidianGP/issues/63) was accepted and merged in [PR #68](https://github.com/yeatu/obsidianGP/pull/68). C1 decision [#75](https://github.com/yeatu/obsidianGP/issues/75) selects GitHub Issues + Actions as the first Web adapter, delivered separately and sequentially. Synthetic-only implementation is tracked in [#77](https://github.com/yeatu/obsidianGP/issues/77), currently claimed by E2. This is not a production worker and does not authorize real-Vault checkout or public production source export.

**Shared Core already in main:** E1 structural indexer / Node identity / source API; E2 SQLite/FTS retrieval; E3/B1 Context Builder; V2.1 transport-independent SearchVaultService / ReadSourceService; V2.2 non-production Issue Worker Core. Transport code must remain a thin adapter over these services.

**PinnedSnapshot security:** A2 review #55 found a mutable callback `__code__` bypass in PR #54. E2 implemented #67 in PR #70, but A1 review #78 found closure-registry introspection and subclass-override bypasses plus a stacked-base CI evidence gap. C decision [#81](https://github.com/yeatu/obsidianGP/issues/81) explicitly narrows the threat model: arbitrary hostile Python code already running in the same interpreter is trusted/out of scope; no tamper-proof or non-forgeable claim is permitted. Correction [#79](https://github.com/yeatu/obsidianGP/issues/79) remains required to enforce the exact factory-created PinnedSnapshot type at every production E1/E2/E3 consumer, isolate fixtures and preserve fail-closed checks. #36/#51/#67 are not accepted; no `read_source` runtime until #79, fresh independent A review and C acceptance.

**Local MCP public contract:** A1 review #65 found actual MCP SDK-generated tool schemas did not enforce all constraints accepted in #37. Canonical correction [#72](https://github.com/yeatu/obsidianGP/issues/72) is open and free; #71 is a duplicate. PR #47 remains unmerged and handlers stay fail-closed pending #72 correction, fresh A review and C acceptance.

**read_source preparation:** A1 accepted the parser-only slice in PR #66 at exact HEAD `b6db66655fa1ab476413c5259246e22d5279c43d` (26 fixture tests). Review #69 is closed. This does not complete #40 or enable runtime reading.

**Quality:** synthetic gold corpus v1.0.0 was accepted and merged in PR #58 (merge commit `b5baf3e660d0271265e9d343608d0588fd9a0267`): 42 cases, 32 synthetic documents, 69 nodes. Benchmark runner #42 is claimed by E1; validate Draft 2020-12 schema, digest, references, spans and hashes before execution.

**Security / operational boundary:** real-Vault Actions workflow remains disabled after run #44222117959. Exposed artifact/run not deleted; #53 tracks owner-side remediation. W1 #77 is synthetic-only; no production Vault, SQLite or sidecar checkout/write.

## 2. Активные задачи

Перед CLAIM проверь последние события, зависимости, file conflicts и независимость непосредственно в Issue. Открытая Issue не обязательно свободна. Фактический владелец определяется последним действующим CLAIM/RELEASE/BLOCKED/HANDOFF.

| Issue | Приоритет | Тип | Роль | Следующий результат | Зависимости / владелец |
|---|---:|---|:---:|---|---|
| [#34](https://github.com/yeatu/obsidianGP/issues/34) | P2 | `REVIEW_REQUEST` | **A** | Независимый аудит Governance v2.4 и PR #44 | Свободна после C1 force-reassignment по §10; новый независимый A CLAIMs current exact HEAD |
| [#39](https://github.com/yeatu/obsidianGP/issues/39) | P2 | `IMPLEMENTATION` | **E** | `search_vault` handler | E1 CLAIM; PR #57 Draft; runtime registration после acceptance #38 |
| [#40](https://github.com/yeatu/obsidianGP/issues/40) | P2 | `IMPLEMENTATION` | **E** | `read_source` handler / service integration | E3 CLAIM; parser prep PR #66 принят по #69; runtime wiring после verifier и #38 gates |
| [#42](https://github.com/yeatu/obsidianGP/issues/42) | P1 | `IMPLEMENTATION` | **E** | Synthetic benchmark runner и метрики Context Pack | E1 CLAIM; corpus v1.0.0 принят; Draft 2020-12 schema validation before execution |
| [#53](https://github.com/yeatu/obsidianGP/issues/53) | P1 | `COORDINATOR_DECISION` | **C** | Owner-side retention/removal review старого Actions run/artifact | C1 CLAIM; Actions DELETE требует `Actions: write`; текущая интеграция не предоставляет DELETE |
| [#72](https://github.com/yeatu/obsidianGP/issues/72) | P2 | `IMPLEMENTATION` | **E** | Enforce accepted #37 constraints in actual generated MCP tool schemas | Canonical correction to #65/#47; свободна; только tools.py/schema/tests |
| [#77](https://github.com/yeatu/obsidianGP/issues/77) | P1 | `IMPLEMENTATION` | **E** | Synthetic ChatGPT Web Issues → Actions → SFRA response worker | E2 CLAIM; decision #75; isolated package/workflow/tests; synthetic fixtures only |
| [#80](https://github.com/yeatu/obsidianGP/issues/80) | P1 | `ANALYSIS` | **A** | Preflight audit of W1 event/auth, immutable body binding, idempotency, recovery, retry semantics and Actions permissions | A1 CLAIM; read-only; independent of E2 implementation #77 |
| [#79](https://github.com/yeatu/obsidianGP/issues/79) | P1 | `IMPLEMENTATION` | **E** | Enforce exact PinnedSnapshot type at production consumers, isolate test seam and rerun combined-base CI | C threat model #81; follow-up to #67/PR #70; currently free; verifier/security boundary |

**Закрыты / приняты:** #37 (tool contracts), #41 (gold corpus), #49 (parallelization analysis), #63 (architecture analysis), #69 (parser-only review), #75 (Web adapter decision), . #81 (PinnedSnapshot process threat model). #55/#65/#78 завершены с CHANGES_REQUESTED; #71 — duplicate #72; #76 — duplicate review request #78. #80 is an active A1 preflight review (not a completed task). #36/#51/#67 остаются не приняты до #79, свежего A review и C acceptance. #38/#47 остаются не приняты до #72, свежего A review и C acceptance. #40 runtime remains blocked.


## 2.1. Новое правило декомпозиции: parallel-first

По Governance Protocol v2.4 (§5) каждую новую крупную задачу сначала разбиваем на минимальные самостоятельно полезные и проверяемые результаты. Для каждого пакета фиксируются один владелец, целевая роль, deliverable, затрагиваемые компоненты/файлы, прямые блокирующие зависимости, конфликты и интеграционная граница. Родительская связь не считается зависимостью автоматически. Независимые анализ, контракты, компоненты, тестовые наборы, fixtures, документация и conformance-проверки открываются отдельными Issues, когда их можно завершать параллельно. Не создаём микрозадачи без собственного результата и не расширяем scope ради занятости.

## 3. Открытые PR

| PR | Состояние | Указание |
|---|---|---|
| [#44 — governance / active panel](https://github.com/yeatu/obsidianGP/pull/44) | Открыт | Точный review HEAD указан в Issue #34; merge только после нового независимого A review |
| [#47 — local MCP bootstrap](https://github.com/yeatu/obsidianGP/pull/47) | Открыт | HEAD `9abf82036b71a8b1a55b3e4f43f124c4611ed2f3`; A1 CHANGES_REQUESTED #65; correction #72; не merge |
| [#54 — PinnedSnapshot verifier correction](https://github.com/yeatu/obsidianGP/pull/54) | Открыт | HEAD `f234c5e2de0f8ed8684a8605bafc50d83abf5d74`; A2 CHANGES_REQUESTED #55; corrections #67/#79; не merge |
| [#70 — hide verifier callback](https://github.com/yeatu/obsidianGP/pull/70) | Открыт / changes requested | HEAD `c7d99a822229c31d21688e04f23cf0a5ce06f722`; A1 CHANGES_REQUESTED #78; correction #79 under C threat model #81; no merge |
| [#57 — search_vault handler](https://github.com/yeatu/obsidianGP/pull/57) | Открыт / Draft | Подготовительный handler для #39; интеграция после принятия #38 |
| [#66 — read_source request parser](https://github.com/yeatu/obsidianGP/pull/66) | Открыт | Exact HEAD `b6db66655fa1ab476413c5259246e22d5279c43d`; accepted parser-only under #69; not full #40 |
| [#12 — GitHub Issue Worker/Recovery proposal](https://github.com/yeatu/obsidianGP/pull/12) | Открыт / Draft | Историческое proposal; не является разрешением на production worker |
| [#1 / #2 — исторические прототипы](https://github.com/yeatu/obsidianGP/pulls) | Открыты | Не объединять без отдельного решения C |


## 4. Ограничения этапа

- #35 остаётся отдельным Local MCP stdio + measured-quality milestone. #75 добавляет независимую Web adapter lane, но только synthetic-only W1 через #77.
- Для MCP: не подключать `read_source` runtime до прохождения verifier chain #36/#51/#67/#79, независимого A review и C acceptance; #47 не принимать до schema correction #72, fresh A review и C acceptance.
- Для verifier действуют C decision #81: защита не является sandbox против hostile Python code в том же interpreter. #79 must enforce exact concrete PinnedSnapshot type at production consumers, isolate fixtures and pass combined #54+#79 fixture CI. Не заявлять tamper-proof/non-forgeable against arbitrary same-process introspection.
- Для Web W1: только marked owner-authored `issues.opened` requests, strict envelope/allowlist/idempotency, минимум permissions `contents: read` и `issues: write`, synthetic corpus v1.0.0, disposable fixtures. No `issues.edited`/`issue_comment` trigger.
- Synthetic excerpts/provenance may appear only in the marked synthetic response Issue comment. Actions stdout/artifacts/errors must contain aggregate-only data; no real source-derived content or metadata.
- Real-Vault GitHub Actions workflow remains disabled. No real Vault/SQLite/sidecar checkout, indexing or writes in CI; do not rerun the exposed run.
- Issue #53 owner-side artifact/log remediation remains open. GitHub REST DELETE requires repository `Actions: write`; the connected integration has no DELETE Actions method.
- No production worker, source publication, production read-only rollout, remote MCP, HTTP/SSE/WebSocket or arbitrary filesystem/write tool is authorized by #75. Any such activation requires a separate reviewed C decision.
- Benchmark #42 must validate Draft 2020-12 schema, corpus digest, Node ID references, exact spans and document/node hashes before executing cases.
- Do not add embeddings/vector search or change ranking/token budget before benchmark evidence. Never report truncated source text as complete.
- [Issue #20](https://github.com/yeatu/obsidianGP/issues/20) is normative Governance v2.4. [Issue #34](https://github.com/yeatu/obsidianGP/issues/34) audits the current panel. [Issue #75](https://github.com/yeatu/obsidianGP/issues/75) records the Web adapter decision. [Issue #81](https://github.com/yeatu/obsidianGP/issues/81) defines the PinnedSnapshot in-process threat model.


## 5. Передача E → A → E и обновление панели

Подробные нормативные правила находятся в §6.4 и §8 [Issue #20](https://github.com/yeatu/obsidianGP/issues/20). Оперативная схема:

1. **E завершает реализацию или correction task:** публикует результат, PR, полный HEAD, тесты и ограничения; создаёт связанную `REVIEW_REQUEST` для A. Удаляет строку реализации из панели и добавляет строку проверки. Исходная Issue остаётся открытой в `REVIEW`, но не доступна для повторного CLAIM.
2. **A принимает результат:** публикует `REVIEW_ACCEPTED`, закрывает запрос проверки и только те реализации/correction Issues, которые полностью покрыты проверенным HEAD; удаляет строку проверки. Для архитектурного, контрактного, межмодульного, milestone-результата, релиза или интеграции A передаёт evidence C через `COORDINATOR_DECISION`; строка ожидания решения C остаётся в панели до его вердикта. Корневая Issue закрывается лишь после приёмки всех обязательных исправлений.
3. **A обнаруживает дефекты внутри исходного scope:** публикует `REVIEW_CHANGES_REQUESTED`, создаёт конкретные correction Issues типа `IMPLEMENTATION` для E, закрывает текущий запрос как завершённую проверку с отрицательным результатом и заменяет строку review строками исправлений.
4. **E исправляет:** публикует новый HEAD, создаёт новый `REVIEW_REQUEST`, заменяет строку correction task строкой проверки. Цикл повторяется до приёмки A.
5. **Выход за scope или обязательная координаторская приёмка:** A создаёт `COORDINATOR_DECISION` для C. Не расширяет задачу самостоятельно.

**После каждого перехода панель обновляет сам участник, выполнивший его: E или A.** Изменение `PROJECT_TASKS.md` вносится через PR; пользователь не редактирует реестр и не передаёт задачи вручную. E/A меняют только строки своих переходов, C может менять весь список и управляющие атрибуты. Если записи в репозиторий нет, участник прикладывает готовый patch и фиксирует конкретное препятствие.

Из панели удаляются только строки. GitHub Issues, комментарии, PR, commits и evidence сохраняются. Issue/PR/commit/Actions остаются источниками истины; панель — только краткий список следующего действия.
