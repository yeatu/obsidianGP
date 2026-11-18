# SFRA — оперативная панель

> Точка входа для AI-участников и снимок активной работы. Нормативные правила — [Issue #20, Governance Protocol v2.4](https://github.com/yeatu/obsidianGP/issues/20).
> GitHub Issue — источник истины по задаче. Эта панель показывает только активные задачи и не дублирует CLAIM, review, CI или evidence.

**Снимок:** 2026-11-18 (C3 coordination refresh)  
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

## 1. Текущий курс

**Целевая архитектура:** ChatGPT Web / mobile → GitHub Issues → GitHub Actions → GitHub-hosted runner → SFRA shared core/services → ответ в исходном Issue → ChatGPT читает результат.

- Работа должна выполняться, когда личный компьютер владельца выключен. Локальные daemon, tunnel, self-hosted runner и MCP не являются частью целевого runtime.
- GitHub-hosted runners — временная среда исполнения, а не постоянное хранилище исходного Vault/index/manifest/sidecar.
- Облачная доступность исходных данных и компьютер-независимый import/sync ещё не спроектированы и анализируются отдельно в [#86](https://github.com/yeatu/obsidianGP/issues/86). Не начинать реальную миграцию до отдельного C/owner decision.
- Первая W1 реализация [#77](https://github.com/yeatu/obsidianGP/issues/77) остаётся synthetic-only и не зависит от будущего data plane.

**Shared SFRA Core already in main:** E1 structural indexer / Node identity / source API; E2 SQLite/FTS retrieval; E3/B1 Context Builder; V2.1 SearchVaultService / ReadSourceService; V2.2 non-production Issue Worker Core. Не дублировать их бизнес-логику в Web adapter.

**PinnedSnapshot security:** correction #79 implemented in [PR #87](https://github.com/yeatu/obsidianGP/pull/87), exact HEAD `162e4190b00c63c67ed1f7fb29871819315c4d92`. Combined fixture CI passed on merge-ref `551b1f6780b9dc6bfbe193f1cfa2f986528e06e6` (C1 74, V2.1 19, V2.2 55 tests, plus shared suites). Independent review is active in [#88](https://github.com/yeatu/obsidianGP/issues/88), claimed by A1. No production `read_source` until fresh A acceptance and C decision.

**Cloud data/publication preference:** the owner has explicitly confirmed that public visibility of Vault content or source-derived metadata is not a confidentiality blocker. The design may publish excerpts or full source content through suitable channels. Do not impose blanket redaction for confidentiality. Protect credentials/secrets and account for size, cost, retention and technical suitability. Publication permission does not authorize production ingestion, workflow execution, writes or mutation.

**Preserved historical work:** [#35](https://github.com/yeatu/obsidianGP/issues/35) and its Local MCP lane remain unchanged as historical engineering context. Existing MCP code, tests, docs, PRs, branches, commits and Issues are preserved; MCP is not a product route or runtime dependency and MCP-only tasks are on hold under C3. Reuse transport-independent components where useful; do not continue MCP-only implementation or merge those wrappers absent explicit owner re-scope.

**Quality:** synthetic gold corpus v1.0.0 was accepted in PR #58 (42 cases, 32 synthetic documents, 69 nodes). End-to-end benchmark [#42](https://github.com/yeatu/obsidianGP/issues/42) is still active and uses disposable synthetic fixtures only.
## 2. Активные задачи

Таблица отражает только актуальные задачи целевого cloud/Web направления и независимого shared-core quality/security. Источник истины — Issue и её последние события; CLAIM и зависимости повторно проверяются непосредственно в Issue.

| Issue | Приоритет | Тип | Роль | Следующий результат | Зависимости / владелец |
|---|---:|---|:---:|---|---|
| [#42](https://github.com/yeatu/obsidianGP/issues/42) | P1 | `IMPLEMENTATION` | **E** | Исправить benchmark integrity/gate findings, повторить 42 synthetic cases и опубликовать exact-HEAD report | E1 CLAIM; PR #84 Draft; последний run #44237776930: 40/42 gates passed, 2 gates failed и один completeness invariant выявлен; не ослаблять checks |
| [#77](https://github.com/yeatu/obsidianGP/issues/77) | P1 | `IMPLEMENTATION` | **E** | Завершить synthetic Issues → Actions → SFRA response worker и exact-head fixture CI | E2 CLAIM; PR #85 Draft; A1 preflight #80 incorporated; exact-head CI/review ещё не пройдены |
| [#88](https://github.com/yeatu/obsidianGP/issues/88) | P1 | `REVIEW_REQUEST` | **A** | Независимо проверить exact PR #87 / #79 | A1 CLAIM; exact HEAD `162e4190b00c63c67ed1f7fb29871819315c4d92`; C acceptance после A verdict |
| [#86](https://github.com/yeatu/obsidianGP/issues/86) | P1 | `ANALYSIS` | **A** | Спроектировать cloud data plane и компьютер-независимый import/sync; сравнить варианты хранилища и каналы публикации | A1 CLAIM; анализ-only, без реального Vault/data migration/provisioning |

**На удержании по решению владельца:** Local MCP-only Issues #38, #39, #40, #43 и #72. Их содержание, claims/evidence, PR и ветки сохраняются; активную реализацию/ревью/merge не продолжать без отдельного re-scope владельца. #53 закрыта после явного waiver владельца по удалению старого публичного run/artifact; само отключение real-Vault workflow остаётся в силе.

**Завершено / принято:** #35 (историческое Local MCP решение, без изменения истории), #63/#68 (архитектурный отчёт), #75 (cloud-only Web направление), #80 (W1 preflight; findings включены в #77), #81 (PinnedSnapshot threat model), #53 (retention/removal waiver). #34 закрыта с CHANGES_REQUESTED по прежнему dashboard HEAD; свежая проверка обновлённого PR #44 будет отдельной Issue.
## 2.1. Новое правило декомпозиции: parallel-first

По Governance Protocol v2.4 (§5) каждую новую крупную задачу сначала разбиваем на минимальные самостоятельно полезные и проверяемые результаты. Для каждого пакета фиксируются один владелец, целевая роль, deliverable, затрагиваемые компоненты/файлы, прямые блокирующие зависимости, конфликты и интеграционная граница. Родительская связь не считается зависимостью автоматически. Независимые анализ, контракты, компоненты, тестовые наборы, fixtures, документация и conformance-проверки открываются отдельными Issues, когда их можно завершать параллельно. Не создаём микрозадачи без собственного результата и не расширяем scope ради занятости.

## 3. Открытые PR

| PR | Состояние | Трактовка |
|---|---|---|
| [#44 — governance / active panel](https://github.com/yeatu/obsidianGP/pull/44) | Открыт | C3 обновляет панель на текущем main base; после фиксации нового exact HEAD требуется независимый A review. Старый verdict #34 относится только к HEAD `9cd1da26376ed4d31f990fdc4439f35c822a4378`. |
| [#87 — PinnedSnapshot exact-type correction](https://github.com/yeatu/obsidianGP/pull/87) | Открыт / Ready for review | HEAD `162e4190b00c63c67ed1f7fb29871819315c4d92`; combined fixture CI passed; review #88 active; no merge/read_source activation before A + C acceptance |
| [#85 — synthetic Web adapter W1](https://github.com/yeatu/obsidianGP/pull/85) | Открыт / Draft | HEAD `7631af8a4a43d81d632eb4fb93df14fd96027b88`; no successful exact-head CI reported; W1 remains synthetic-only |
| [#84 — synthetic gold benchmark](https://github.com/yeatu/obsidianGP/pull/84) | Открыт / Draft | HEAD `a16698266f5ceafa27ef4174a067517ca346663e`; run #44237776930 failed 2 gates plus completeness invariant; E1 correction in progress |
| [#47 — historical Local MCP bootstrap](https://github.com/yeatu/obsidianGP/pull/47) | Открыт / HOLD | Preserved, not a target, do not merge absent explicit owner re-scope |
| [#57 — historical MCP search adapter](https://github.com/yeatu/obsidianGP/pull/57) | Открыт / Draft / HOLD | Preserved; do not continue or merge as product path |
| [#66 — historical read_source parser prep](https://github.com/yeatu/obsidianGP/pull/66) | Открыт / HOLD | Accepted parser-only slice preserved for possible adaptation; no MCP runtime wiring |
| [#94 — historical generated MCP schema correction](https://github.com/yeatu/obsidianGP/pull/94) | Открыт / HOLD | E3 completed exact-head work and CI; preserve branch/evidence, no A review or merge while MCP is off target |
| [#54 / #70 — prior verifier attempts](https://github.com/yeatu/obsidianGP/pulls) | Открыты / historical | Prior CHANGES_REQUESTED history; current correction is #87; do not merge old attempts |
| [#12, #1, #2 — historical prototypes](https://github.com/yeatu/obsidianGP/pulls) | Открыты / historical | Preserve unchanged; no merge without separate C/owner decision |


## 4. Действующие ограничения и решения

- **Cloud-only runtime:** ChatGPT Web/mobile → GitHub Issues → Actions → GitHub-hosted runners → SFRA. Personal computer, self-hosted runner, local daemon/tunnel and MCP are not runtime dependencies.
- **Durable source data:** cloud storage/index/snapshot/manifest/sidecar design is not yet approved. #86 is analysis-only. GitHub-hosted runner workspace is ephemeral, not durable Vault storage.
- **Publication:** public publication of Vault content and source-derived metadata is acceptable to the owner. Do not impose blanket redaction on confidentiality grounds. Protect credentials/secrets and preserve integrity/provenance; choose Issues/comments/logs/artifacts based on practical fit, size, cost and retention.
- **Production boundary:** permission to publish data does not authorize production reads, imports, indexing, workflow execution or mutation. The real-Vault workflow disabled under #53 remains disabled; do not rerun it. Any cloud-backed real-data path requires #86 design, independent review and explicit C/owner approval.
- **W1 #77:** synthetic-only; marked owner-authored `issues.opened`; allowlisted comment projection; strict event/auth/body binding; at-least-once semantics and documented recovery. No real Vault/SQLite/sidecar, no synthetic Issue write/round-trip until the A review and C acceptance gates are satisfied.
- **PinnedSnapshot:** no production `read_source` until #79 / PR #87 passes fresh independent A review #88 and C acceptance. Threat model #81 trusts code already executing inside the same Python process; no false tamper-proof claim.
- **Local MCP legacy work:** assets and history are preserved, but MCP-specific Issues #38/#39/#40/#43/#72 and PR #47/#57/#66/#94 are on hold. Do not claim, continue, review or merge this lane unless the owner explicitly reactivates/re-scopes it.
- **Benchmark #42:** synthetic-only; validate corpus schema, digest, references, exact spans and hashes. A failed quality gate remains a failure; do not weaken forbidden-node/completeness assertions to force a pass.
- Do not add embeddings/vector search, alter retrieval ranking or change E3 token budget before benchmark evidence. Never report truncated source text as complete.
- Governance protocol: [Issue #20](https://github.com/yeatu/obsidianGP/issues/20); current Web decision: [#75](https://github.com/yeatu/obsidianGP/issues/75); cloud data-plane analysis: [#86](https://github.com/yeatu/obsidianGP/issues/86); verifier threat model: [#81](https://github.com/yeatu/obsidianGP/issues/81).


## 5. Передача E → A → E и обновление панели

Нормативные правила находятся в [Issue #20](https://github.com/yeatu/obsidianGP/issues/20). После каждого перехода исполнитель или аналитик обновляет свою строку через PR. Координатор вправе обновлять весь active register и архитектурные указания. Панель остаётся кратким снимком: Issue, PR, commit и Actions — источники истины.

C принимает архитектурные, security, cross-module, milestone и integration результаты только после проверки точного HEAD и evidence. Обычные leaf-задачи внутри утверждённого scope принимает независимый A. Никакой CLAIM или merge не отменяет ограничений #53, #75, #81 либо иных актуальных C/owner decisions.


Из панели удаляются только строки. GitHub Issues, комментарии, PR, commits и evidence сохраняются. Issue/PR/commit/Actions остаются источниками истины; панель — только краткий список следующего действия.
