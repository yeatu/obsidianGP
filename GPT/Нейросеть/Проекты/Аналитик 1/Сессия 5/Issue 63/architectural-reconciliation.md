# A1 — архитектурное согласование ChatGPT Web и Local MCP

**Issue:** [#63](https://github.com/yeatu/obsidianGP/issues/63)  
**Тип:** ANALYSIS / P1  
**Аналитик:** A1  
**Проверенная база:** \`main\` HEAD \`2795307045bc2af98bc918daffe1d688e4418cd2\`  
**Дата проверки:** 18 ноября 2026  
**Режим:** read-only анализ; код, workflows, Vault, SQLite, sidecar, Issue #20 и чужие PR не изменялись.

## 1. Итоговая рекомендация

**Рекомендую вариант C: сохранить два транспорта как отдельные адаптеры к одному transport-independent SFRA Core, но вводить их последовательно, а не строить одновременно.**

1. Не отменять и не переопределять закрытое координаторское решение [#35](https://github.com/yeatu/obsidianGP/issues/35). В его текущем scope Local MCP stdio остаётся локальным интерфейсом для совместимых MCP-hosts.
2. Довести уже согласованный Local MCP milestone через текущие задачи #36–#43/#51: verifier guard, composition, отдельные handlers и conformance. #41/#42 остаются независимой quality lane.
3. Отдельным решением C определить Web-facing интерфейс. Историческая цель Сессии 2 — GitHub Issues + Actions — остаётся документированной пользовательской целью, но не имеет разрешения на production-выполнение в текущем scope.
4. Перед любым Web transport сначала разрешить конфликт #35/#53: определить допустимый канал выдачи source evidence, границу публичного экспорта, safe execution environment и retention/remediation уже раскрытого Actions evidence.
5. После решения C реализовывать только один Web adapter поверх уже существующих SearchVaultService / ReadSourceService и V2.2 Issue Worker Core. Не дублировать retrieval, source verification, ranking, Context Pack или budget policy.

Это сохраняет исходный пользовательский сценарий как цель, но не выдаёт Local MCP за его реализацию и не обходит действующие ограничения.

## 2. Что именно было исходной целью

### 2.1. Подтверждённые требования пользователя

| Источник | Подтверждённое требование | Что из этого следует |
|---|---|---|
| Реестр Координатора, Сессия 2 | Пользователь прямо указал: «Публичность не имеет значения» | Публичность GitHub сама по себе не была пользовательским блокером первоначального выбора Issues + Actions. |
| Сессия 2, исходная схема | \`ChatGPT Web → GitHub Issues → GitHub Actions → Python/SFRA → комментарий к Issue → ChatGPT Web\` | Целевой пользовательский вход был через ChatGPT Web и GitHub Issue, а не через локальный stdio process. |
| Сессия 2, операции | Две операции: \`search_vault\` и \`read_source\`; отдельная Issue для последующего чтения | Внешний транспорт должен передавать строгий request envelope, Node ID, Content Hash и SnapshotRef. |
| Сессия 2, состояние | Node ID и история версий должны сохраняться между одноразовыми runner-ами; FTS/search/context вычисляются временно | Нужно разделять постоянную адресацию источников и эфемерные вычисления. |
| Сессия 2, эксперимент | Описан успешный smoke cycle: Issue → Actions → комментарий → чтение ответа; отдельный поисковый эксперимент | Существовала демонстрация технической осуществимости транспорта, но не доказательство готовности полного MVP. |
| Сессия 7 | Пользователь одновременно запретил опасные workflow и касание production data после инцидента, а также выразил безразличие к публичности | Эти две части нельзя сводить к «разрешено всё»: публичность и integrity/production safety — разные вопросы. |
| Задача Сессии 1 | Прямо разделены требования к целевой Web-схеме и позднейшие governance gates | Пользовательская цель не отменяет действующие решения проекта; конфликт обязан разрешить C. |

Важная оговорка по Сессии 7: фраза о безразличии к публичности следует **после** прямого запрета запускать опасные workflow и трогать production data. Нельзя использовать вторую фразу как разрешение нарушать первую.

### 2.2. Позднейшие решения проекта

| Решение | Текущий смысл |
|---|---|
| [Issue #20, Governance v2.4](https://github.com/yeatu/obsidianGP/issues/20) | Нормативный источник полномочий, CLAIM и gates. A может анализировать и рекомендовать; изменение архитектуры, scope, security policy и merge — полномочия C. |
| [Issue #35](https://github.com/yeatu/obsidianGP/issues/35), закрыта | Утверждён отдельный milestone **Local Retrieval Interface + Measured Quality**. В нём Local MCP stdio — целевой локальный интерфейс; production GitHub worker/Recovery, GitHub writes, remote MCP HTTP и публикация source excerpts/paths в публичных Issues/comments исключены. |
| [Issue #37](https://github.com/yeatu/obsidianGP/issues/37), закрыта и принята C | Зафиксирован контракт двух локальных MCP tools и SnapshotRef continuity. Логика остаётся в application services; локальный MCP — только адаптер. |
| [Issue #53](https://github.com/yeatu/obsidianGP/issues/53), открыта P1 | Реальный Actions log раскрыл source-derived metadata. C отключил real-Vault workflow; real Vault checkout в публичных Actions запрещён до нового отдельно проверенного и принятого sanitized design. Вопрос удаления/retention старых log/artifact ещё не закрыт. |

Следовательно, #35 — действующее и формально принятое направление текущего milestone. Оно не доказывает, что исходный Web-сценарий реализован; одновременно аналитический отчёт A1 не может самостоятельно отменить #35.

## 3. Текущая архитектура и степень готовности

### 3.1. Общий слой, который уже существует

На проверенном \`main\` находятся:

- E1/E2/E3: индексирование, retrieval, Context Builder и source reading.
- V2.1: transport-independent \`SearchVaultService\` / \`ReadSourceService\` в \`sfra_context_integrations/application.py\`. Модуль прямо запрещает помещать в себя GitHub, MCP, HTTP, webhook или persistence code.
- \`ContextIntegrationPipeline\`: проводит E2 retrieval, B1 Context Pack и E1 reads через один закреплённый SnapshotRef.
- V2.2 \`sfra_issue_core\`: strict Issue parser, body hash binding, status v2, safe result projector и injected worker core.

V2.2 — **не production worker**. README и код подтверждают отсутствие GitHub API client, network, credentials, write permissions, event handlers, workflow trigger, production status store, retries/leases/recovery и deployment. Worker вызывает только внедрённые application-service ports и получает SnapshotRef снаружи.

Особенно важна граница публикации: \`SafeResultProjector\` в V2.2 возвращает только allowlisted status, operation, scope, aggregate counts и диагностические коды. Он намеренно **не** сериализует raw_text, fragments, source paths, node IDs, content hashes, query/task или diagnostic details. Это безопасный агрегатный результат, но не полноценный Context Pack для ответа ChatGPT.

### 3.2. Текущие адаптеры и зависимые задачи

| Компонент | Состояние на проверке | Ограничение |
|---|---|---|
| Local MCP bootstrap, [PR #47](https://github.com/yeatu/obsidianGP/pull/47) | Open, non-Draft, mergeable; HEAD \`70bb88e77c12b6e3649fd7fe6ee84d68ee0df745\`, base current main; dedicated fixture CI success | Это локальный stdio scaffold, не Web endpoint. Ветки handlers #39/#40 отдельны. |
| [Issue #38](https://github.com/yeatu/obsidianGP/issues/38) | Implementation handoff E3 → review request #56/#65; последний точный PR HEAD отличается от ранее запрошенного A2 review target | До независимого review точного текущего HEAD bootstrap не считать принятым. |
| [Issue #39](https://github.com/yeatu/obsidianGP/issues/39) | E1 CLAIM; изолированная подготовка handler | Финальная интеграция зависит от #38. |
| [Issue #40](https://github.com/yeatu/obsidianGP/issues/40) | E3 CLAIM; конкурирующий CLAIM E1 уступил | Runtime read_source запрещён до принятия #36/#51 и готовности #38. |
| [Issue #36](https://github.com/yeatu/obsidianGP/issues/36) / [#51](https://github.com/yeatu/obsidianGP/issues/51) | Correction implementation в [PR #54](https://github.com/yeatu/obsidianGP/pull/54), HEAD \`f234c5e2de0f8ed8684a8605bafc50d83abf5d74\`; exact-fixture workflows succeeded; A2 claimed independent review #55 | Нужны независимый review и C acceptance security-boundary correction. PR #54 stacked on PR #46, поэтому review должен оценить incremental diff и base вместе, а не переносить старое принятие на новый HEAD. Нельзя выдавать CI merge-commit за прямой запуск на bare PR HEAD. |
| [Issue #41](https://github.com/yeatu/obsidianGP/issues/41) / #42 | Synthetic corpus A1 подготовлен в PR #58 и ожидает C acceptance по #61; benchmark runner #42 зависит от #41 | Не считать gold corpus принятым до решения C; #42 — задача E, не A. |
| [Issue #43](https://github.com/yeatu/obsidianGP/issues/43) | Open, E implementation | Конечный conformance/quickstart gate зависит от #36–#40. |
| [Issue #53](https://github.com/yeatu/obsidianGP/issues/53) | Open, C1 CLAIM; containment активен | Не запускать real-Vault Actions и не публиковать source-derived metadata. |

### 3.3. Что в main реально есть для GitHub Issues

В \`.github/workflows/sfra-issue-bridge-smoke.yml\` существует smoke workflow на \`issues.opened\` и \`issues.edited\`. Он проверяет фиксированный автора, title prefix и тестовый payload, затем публикует технический статус-комментарий. Он **не** читает Vault, не строит SnapshotRef, не вызывает SearchVaultService/ReadSourceService и не реализует идемпотентный worker/recovery.

[PR #12](https://github.com/yeatu/obsidianGP/pull/12) остаётся Draft proposal. В нём прямо указано, что smoke workflow доказывает только доставку события Issue и публикацию комментария, но не request validation полного протокола, E2/E3 execution, SnapshotRef binding, idempotency или recovery.

Следовательно, наличие smoke workflow и V2.2 IssueWorkerCore не равняется наличию production GitHub Issue Worker.

## 4. Матрица архитектурных вариантов A/B/C

| Критерий | A. Local MCP stdio | B. GitHub Issues + Actions для Web | C. Последовательные два адаптера |
|---|---|---|---|
| Пользовательский сценарий | Локальный MCP host запускает SFRA process и вызывает tools по stdio | ChatGPT Web формирует Issue с JSON; Actions обрабатывает запрос; ответ читается из комментария | Локальные клиенты используют stdio; Web получает отдельный адаптер после отдельного решения |
| Совместимость с ChatGPT Web | **Нет напрямую.** Локальный stdio process не является удалённым endpoint для ChatGPT Web | Возможна только при наличии write-capable Issue creation path, чтения Issue/comment и разрешённого Actions worker | Да, если второй адаптер реализован и его реальный канал доступа проверен |
| Компоненты | MCP SDK, CLI, локальные пути Vault/sidecar, verified composition root, два tool handlers | Issue envelope, GitHub event workflow, authorization, Issue reader/comment writer, status persistence, leases/retries, application services | Оба тонких транспорта над общим core; независимые lifecycle/config/security |
| Application core | Существующий V2.1 и E1/E2/E3 | Тот же V2.1 и E1/E2/E3; V2.2 worker core может быть основой | Общий, неизменяемый transport-independent core |
| SnapshotRef | Один pinned snapshot внутри local process; caller переносит identity между tools | Один SnapshotRef на один worker request; follow-up read — новая Issue с той же identity; другой runner не должен незаметно rebinding | Общая семантика SnapshotRef; transport передаёт identity, core валидирует |
| Idempotency | В основном запрос/ответ одного процесса; нет GitHub retry/event delivery | Обязательны request_id, body hash, first-seen immutability, dedup событий, статус, lease/timeout/retry/recovery | Каждый adapter реализует transport-specific delivery semantics, core не зависит от них |
| Provenance / данные | Локальный tool может возвращать полный локальный Context Pack и точные source fragments | Текущий V2.2 projector отдаёт только агрегаты; публикация source content запрещена #35, а real checkout заблокирован #53 | Можно иметь локальную полную выдачу; Web data channel отдельно утверждается C |
| Публичная экспозиция | Локальный ответ не публикуется автоматически в GitHub | Issue body/comment и Actions logs могут стать публичными и сохраняться | Локальный adapter изолирован; Web adapter имеет отдельную export policy |
| Операционные затраты | Локальная установка, процессы и права доступа к двум Git checkouts | GitHub App/token, event workflow, Actions minutes, durable state/lease/recovery, incident response и retention | Выше двух одиночных вариантов; затраты минимизируются последовательной реализацией |
| Главное ограничение сейчас | Не закрывает Web-сценарий напрямую; #35 пока не завершён | Не разрешён как production transport; публичный data channel запрещён; текущий GitHub app experience имеет ограничения записи | Требует отдельного C decision после завершения текущих gates |
| Готовность | В разработке: PR #47 scaffold, #39/#40 handlers и #36/#51 gate ещё не приняты | Только smoke bridge и non-production core; production worker отсутствует | Архитектурно чистый целевой путь, но это план, а не текущая реализация |

### 4.1. A — Local MCP stdio

Целевой поток:

\`\`\`text
Local MCP host (desktop/Codex/other compatible client)
          |
          | stdio
          v
SFRA MCP process
          |
          | typed request / SnapshotRef
          v
SearchVaultService / ReadSourceService
          |
          v
E2 retrieval -> E3 source verification -> B1 Context Pack -> E1 exact source
          |
          v
MCP tool response to local caller
\`\`\`

Сильные стороны:
- минимальный транспортный слой, не требует GitHub event worker;
- локальные пути и полный source response остаются в локальном контуре;
- хорошо совпадает с существующими V2.1 services и #37 contract;
- current #38 PR already demonstrates a stdio-only composition scaffold with fixture CI.

Ограничения:
- ChatGPT Web не подключает локальный STDIO process напрямую. По актуальной документации OpenAI ChatGPT Web использует remote MCP tools; для локального/private server предусмотрен Secure MCP Tunnel на поддерживаемых продуктах. Custom MCP connections на Web доступны не на всех планах и разрешениях: full MCP/write в документации ограничен Business/Enterprise/Edu; Pro ограничен read/fetch.
- В рамках #35 remote MCP HTTP/SSE/WebSocket был исключён, поэтому перевод локального сервера в remote endpoint нельзя делать без C decision.
- До завершения #36/#51 и #40 source reads не должны подключаться к runtime composition.

**Вердикт A:** правильный optional adapter для локальных MCP hosts. Не является самостоятельным доказательством интеграции именно ChatGPT Web.

### 4.2. B — GitHub Issues + Actions adapter для ChatGPT Web

Целевой поток из исходной Сессии 2:

\`\`\`text
ChatGPT Web / authorized Issue-writing integration
          |
          | create [SFRA] Issue + strict JSON envelope
          v
GitHub Issue (request_id, operation, payload, body hash)
          |
          | issues.opened event
          v
GitHub Actions one-shot worker
          |
          | authenticate + validate + deduplicate + pin snapshot
          v
V2.2 IssueWorkerCore / production transport ports
          |
          | call existing V2.1 application services only
          v
E2 -> E3 -> B1 -> E1
          |
          | status/result projection
          v
Comment on original Issue
          |
          | authorized read of Issue/comment
          v
ChatGPT Web
\`\`\`

Отдельный follow-up read:

\`\`\`text
ChatGPT Web -> new [SFRA] read_source Issue
            -> same Node ID + Content Hash + SnapshotRef
            -> worker validates same pinned identity
            -> explicit result / stale / mismatch / budget status
\`\`\`

Что нужно реализовать:
1. **Write path.** Инструмент или отдельная авторизованная GitHub App должна уметь создать Issue. Одного read-only GitHub repository connection недостаточно.
2. **Event worker.** Событие \`issues.opened\` запускает worker; событие comment/edit не должно порождать рекурсивные команды. Проверяются repository identity, Issue type/title prefix, author allowlist, envelope version, body size/hash, schema и operation allowlist.
3. **Idempotency.** На один Issue/request_id сохраняется exact body SHA-256; повторная доставка события не запускает несовместимое повторное выполнение. Нужны durable status, atomic first-seen body hash, lease/timeout, retry/backoff, per-Issue concurrency control и recovery policy.
4. **Snapshot.** Worker использует один SnapshotRef для E2/E3/E1; identity возвращается вызывающему. Follow-up read несёт исходную identity; mismatch/stale fail-closed, никаких автоматических переходов на current snapshot.
5. **Core reuse.** Worker только валидирует транспортный envelope и вызывает V2.1 services. Retrieval, source verification, budget, Context Pack и token counting остаются в E1/E2/E3.
6. **Output channel.** Текущий SafeResultProjector намеренно возвращает лишь агрегаты. Этого недостаточно для полноценного source-grounded ответа ChatGPT. Но #35 запрещает public raw_text/excerpts/path/title в Issue comments, а #53 запрещает real Vault workflow и content-derived logs/metadata до нового security decision. Значит, полезный source payload сейчас **не разрешён** к публикации в Issues/comments.

**Критическое расхождение B:** если публиковать только агрегатные статусы и counts, Web получит факт выполнения поиска, но не сам Context Pack и не сможет делать анализ по найденным источникам. Если отправлять raw source/context в публичные комментарии, это прямо нарушит #35 без отдельного C decision. Следовательно, B нельзя считать готовым Web transport, пока не решён вопрос разрешённого канала source evidence.

### 4.3. C — последовательное внедрение двух адаптеров

Рекомендуемая схема:

\`\`\`text
                    SFRA Core
      E1 + E2 + E3/B1 + V2.1 application services
                         |
                typed contracts / SnapshotRef
                    /               \\
                   /                 \\
       Local MCP stdio         Web adapter (future)
       for local hosts         selected by C:
       #38-#40/#43             Issues+Actions OR remote MCP/tunnel
\`\`\`

Порядок:
- сохраняет уже оплаченный прогресс по #37/#38, verifier guard и gold benchmark;
- не вынуждает менять бизнес-логику под один transport;
- позволяет проверить Local MCP и Web adapter независимо;
- не делает текущий MCP milestone автоматическим препятствием для всех будущих Web-интерфейсов;
- даёт C возможность отдельно принять data publishing, remote transport и real execution design.

Недостаток: два адаптера требуют двух наборов conformance tests, permission model и operational maintenance. Это не повод реализовывать оба одновременно; общий core снижает стоимость.

**Вердикт C:** лучший вариант для сохранения обоих сценариев. Сначала закончить утверждённый Local MCP milestone, затем отдельным C decision выбрать и разрешить Web adapter.

## 5. Отдельный Web-native вариант, который следует учитывать до решения B

Современная документация OpenAI различает Local STDIO MCP и remote MCP:

- ChatGPT Web подключает custom MCP server как remote HTTPS endpoint либо через Secure MCP Tunnel; локальный STDIO server напрямую не подключается.
- Полная поддержка custom MCP с write actions зависит от плана/workspace; документация Help Center указывает Business и Enterprise/Edu для full MCP, а Pro — read/fetch.
- Документация по GitHub connection описывает built-in GitHub app как read-only для репозиториев; она не должна автоматически рассматриваться как Issue-create/write integration. Work event-triggered GitHub tasks документированы для PR activity, не как общий \`issues.opened\` worker.

Источники OpenAI:
- [Connecting custom MCP servers in ChatGPT](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt)
- [Model Context Protocol — ChatGPT Learn](https://learn.chatgpt.com/docs/extend/mcp)
- [Connecting GitHub to ChatGPT](https://help.openai.com/en/articles/11145903-connecting-github-to-chatgpt)

Поэтому перед выбором B C следует сравнить B с отдельным **remote MCP + Secure MCP Tunnel** Web adapter. Это не входит в текущий #35 scope и не является разрешением внедрять remote transport: Issue #35 прямо исключила remote MCP HTTP/SSE/WebSocket. Это лишь архитектурный вариант для отдельного решения C, если план/workspace и tunnel действительно доступны целевому пользователю.

Кроме того, в данной среде A1 доступен write-capable GitHub integration, но это не доказывает, что стандартный GitHub app connector во всех ChatGPT Web surfaces/планах даёт create-Issue и read-comment permissions. Проверять нужно именно тот connector/app и workspace, которыми будет пользоваться конечный сценарий.

## 6. Security / threat model и обязательные gates

| Актив / граница | Угроза | Минимальная защита / acceptance |
|---|---|---|
| Issue body | Prompt injection, JSON ambiguity, duplicate keys, oversized payload, unsupported fields | Strict UTF-8, size limit, duplicate-key rejection, schema \`additionalProperties:false\`, operation allowlist; body трактуется только как data |
| Инициатор | Неавторизованный запуск | Точный repository, issue marker/title, author allowlist, least-privilege GitHub token; отсутствие allowlist — fail-closed |
| События GitHub | Повторная доставка, edit/replay, случайная рекурсия | request_id + immutable first-seen body hash + persisted status; trigger только на разрешённые issue events; не запускать команды по comments |
| Sidecar / Snapshot | Конкурентная перезапись, переход на другой snapshot, stale source | Один immutable SnapshotRef на request; serialized/leased sidecar writes; hash verification; никакого current fallback |
| Source payload | Публичная утечка имён, путей, hashes, raw_text и derived metadata | Отдельная export policy; explicit source-field allowlist per destination; не сериализовать unreviewed \`SourceFragment.attributes\` |
| GitHub Actions logs/artifacts | Утечка через stdout, exceptions, pytest output, artifact | Synthetic/disposable fixtures only; no raw payload, path, hash, content sizes, excerpt, arbitrary metadata; только non-identifying aggregates |
| Worker privileges | Избыточные токены/изменение данных | Минимальные job permissions; разделить read и comment-write; нет Vault/SQLite/sidecar writes в текущем MVP; исключить secrets из request context |
| Source semantics | Partial source, truncation, false completeness, wrong provenance | E1/E3 fail-closed; non-ok => fragments=[]; preserve Included/Deferred, coverage, exact hashes and budget semantics |
| Public retention | Невозможность отозвать уже опубликованные комментарии/логи | До запуска определить retention/remediation owner и срок; публичный комментарий трактовать как durable disclosure |

### Текущее решение #53

Issue #53 — не абстрактное опасение. В ней зафиксирован реальный публичный Actions run, содержащий source paths и source-derived metadata. Координатор C1 отключил real-Vault workflow на \`main\` commit \`7a3808713a46f54a1cfd17c2df39ca9e581bc87f\`, запретил повторный run и потребовал synthetic/disposable fixtures only. По последней записи C1 artifact/log всё ещё опубликованы; owner-side removal/retention review не завершён.

Поэтому:
- не запускать \`sfra-e3-real-e1-integration.yml\` и эквивалентный real-Vault checkout;
- не считать public issue comments безопасным местом для source payload только потому, что логи sanitized;
- не заявлять, что старый artifact/log удалён;
- не пытаться исправить #53 изменением кода без решения C;
- новый production/sanitized execution design требует independent security review и отдельной C acceptance.

## 7. Рекомендуемая последовательность и зависимости

| Шаг | Что сделать | Gate / зависимость | Кто решает |
|---|---|---|---|
| 0. Зафиксировать архитектурную цель | Признать, что #35 — approved Local MCP milestone, а Web goal отдельно не закрыт | Текущий анализ #63 | C1 |
| 1. Закрыть verifier security prerequisite | Независимо проверить exact #54 delta, затем принять #36/#51 | A review #55 → C acceptance по §8.7 | A2 reviewer, затем C |
| 2. Закончить Local MCP scaffold | Независимый review current PR #47 HEAD, принять #38 | Review target должен совпадать с текущим HEAD; затем #39/#40 | A reviewer, затем C для cross-boundary |
| 3. Завершить local handlers | #39 search_vault; #40 read_source после принятого verifier и композиции | #37 accepted; #38 accepted; #36/#51 accepted для read_source | E owners + A review |
| 4. Завершить quality lane | Принять synthetic corpus #41; реализовать #42 runner | #41 C acceptance → #42; synthetic-only | C принимает corpus; E выполняет runner |
| 5. Local conformance | #43 E2E, quickstart, safety and no-write proof | #36–#40 and #42 | A review + C acceptance |
| 6. Web transport decision | Выбрать B (Issues/Actions), remote MCP/tunnel либо отложить Web adapter | Отдельное COORDINATOR_DECISION; оценка actual ChatGPT connector/plan/workspace; изменение #35 scope | C |
| 7. Web transport security design | Разрешённый source-return channel, GitHub actor/token permissions, durable idempotency/leases, sanitized logs/artifacts, retention/remediation | #53 owner remediation + independent security review + explicit C approval | C + owner/security reviewer |
| 8. Реализация Web adapter | Тонкий adapter поверх V2.1/V2.2 core; никакой второй retrieval implementation | Только после шагов 6–7; synthetic/disposable first | E, затем A review и C |

Здесь шаги 1–5 — текущая утверждённая Local MCP lane. Шаги 6–8 — будущая Web lane, которая не начинается автоматически от закрытия #35 или merge #47.

## 8. Открытые вопросы, которые действительно требуют C

1. **Какую Web-интеграцию выбрать?** GitHub Issues/Actions, remote MCP через HTTPS/Tunnel, либо отложить Web adapter до проверки доступности соответствующего ChatGPT surface/плана.
2. **Какой source payload может покидать worker?** Только агрегаты, explicit approved public export allowlist, или приватный remote tool channel. Без этого B не возвращает полноценный Context Pack.
3. **Нужно ли менять #35?** Если C утверждает Web adapter, надо официально обозначить его как дополнительный transport milestone, а Local MCP оставить отдельным client adapter. Не менять issue закрытым задним числом.
4. **Что считается завершением #53?** Owner-side removal/retention review опубликованного run/artifact, и утверждённый sanitized CI policy.
5. **Как получить issue-create capability именно в конечном ChatGPT Web workspace?** Проверить конкретный connected app/plugin/Work action, а не выводить write permissions из факта read-only доступа к репозиторию.
6. **Где хранится production status/idempotency state?** V2.2 использует in-memory test store; production persistence, atomic lease and recovery остаются отсутствующими.
7. **Как обеспечить source identity в новом Actions runner?** Только через явно выбранный immutable source commit + sidecar commit + manifest digest; запрещено скрыто rebinding к текущему состоянию.

## 9. Финальный вывод A1

- **A Local MCP stdio** — корректный и полезный локальный адаптер, но не ChatGPT Web endpoint.
- **B GitHub Issues + Actions** — соответствует исторической Web-схеме Сессии 2 и имеет smoke-test доказательство транспорта, но production worker не реализован, встроенный GitHub app connector сам по себе не следует считать issue-write API, а публикация source payload запрещена текущими #35/#53.
- **C Два адаптера на общем Core, вводимые последовательно** — наиболее устойчивое решение, если проект действительно должен поддерживать и локальные MCP clients, и ChatGPT Web.

**Рекомендация C1:** сохранить #35 без немедленного переписывания; завершить существующие Local MCP / SnapshotRef / benchmark gates; затем отдельным решением определить Web-facing adapter и его разрешённый data channel. Если первична именно работа ChatGPT Web, сравнить GitHub Issue bridge с remote MCP/Tunnel на реальном целевом плане и workspace. Не заявлять, что Local MCP stdio уже решает Web-сценарий; не запускать production Actions до нового security approval.

Это архитектурная рекомендация, а не координаторское решение. A1 не меняла scope #35/#53, не создавала дочерних задач, не меняла чужие CLAIM/PR, не запускала workflow и не обращалась к production Vault/SQLite/sidecar.

## 10. Проверяемые источники

### Внутренние источники проекта
- [Задача Координатора, Сессия 1](https://github.com/yeatu/obsidianGP/blob/main/GPT/Нейросеть/Проекты/Координатор%201/Сессия%201/Задача%20сессии.md) — нормативная постановка архитектурного reconciliation.
- [Реестр Координатора, Сессия 2](https://github.com/yeatu/obsidianGP/blob/main/GPT/Нейросеть/Проекты/Координатор%201/Сессия%202/Реестр%20сессии%202.md) — исходная Web схема и пользовательское указание о публичности.
- [Реестр Координатора, Сессия 3](https://github.com/yeatu/obsidianGP/blob/main/GPT/Нейросеть/Проекты/Координатор%201/Сессия%203/Реестр%20сессии%203.md) — V2.1 separation и DENY BY DEFAULT.
- [Реестры Координатора, Сессии 4–6](https://github.com/yeatu/obsidianGP/tree/main/GPT/%D0%9D%D0%B5%D0%B9%D1%80%D0%BE%D1%81%D0%B5%D1%82%D1%8C/%D0%9F%D1%80%D0%BE%D0%B5%D0%BA%D1%82%D1%8B/%D0%9A%D0%BE%D0%BE%D1%80%D0%B4%D0%B8%D0%BD%D0%B0%D1%82%D0%BE%D1%80%201) — V2.1/V2.2, production worker и V2.3/V2.4 gates.
- [Реестр Координатора, Сессия 7](https://github.com/yeatu/obsidianGP/blob/main/GPT/%D0%9D%D0%B5%D0%B9%D1%80%D0%BE%D1%81%D0%B5%D1%82%D1%8C/%D0%9F%D1%80%D0%BE%D0%B5%D0%BA%D1%82%D1%8B/%D0%9A%D0%BE%D0%BE%D1%80%D0%B4%D0%B8%D0%BD%D0%B0%D1%82%D0%BE%D1%80%201/%D0%A1%D0%B5%D1%81%D1%81%D0%B8%D1%8F%207/%D0%A0%D0%B5%D0%B5%D1%81%D1%82%D1%80%20%D1%81%D0%B5%D1%81%D1%81%D0%B8%D0%B8%207.md) — пользовательские ограничения после инцидента.
- [Реестры Координатора, Сессии 8–9](https://github.com/yeatu/obsidianGP/tree/main/GPT/%D0%9D%D0%B5%D0%B9%D1%80%D0%BE%D1%81%D0%B5%D1%82%D1%8C/%D0%9F%D1%80%D0%BE%D0%B5%D0%BA%D1%82%D1%8B/%D0%9A%D0%BE%D0%BE%D1%80%D0%B4%D0%B8%D0%BD%D0%B0%D1%82%D0%BE%D1%80%201) — Local MCP pivot and governance model.
- [Issue #20](https://github.com/yeatu/obsidianGP/issues/20), [#35](https://github.com/yeatu/obsidianGP/issues/35), [#37](https://github.com/yeatu/obsidianGP/issues/37), [#49](https://github.com/yeatu/obsidianGP/issues/49), [#53](https://github.com/yeatu/obsidianGP/issues/53), [#63](https://github.com/yeatu/obsidianGP/issues/63).
- [PR #12](https://github.com/yeatu/obsidianGP/pull/12), [PR #47](https://github.com/yeatu/obsidianGP/pull/47), [PR #54](https://github.com/yeatu/obsidianGP/pull/54).

### Внешние источники о возможностях ChatGPT на дату проверки
- [OpenAI Help Center — Connecting custom MCP servers in ChatGPT](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt): web custom MCP connections use a remote HTTPS endpoint or Secure MCP Tunnel; local MCP is not connected directly; availability and write permissions depend on plan/workspace.
- [OpenAI ChatGPT Learn — Model Context Protocol](https://learn.chatgpt.com/docs/extend/mcp): ChatGPT Web uses remote MCP tools through plugins; local STDIO support is a local-client configuration.
- [OpenAI Help Center — Connecting GitHub to ChatGPT](https://help.openai.com/en/articles/11145903-connecting-github-to-chatgpt): the built-in GitHub app is described as read-only for repository access; eligible Work event triggers documented here relate to GitHub pull-request activity. This does not establish a general issues.create permission for every ChatGPT surface.
