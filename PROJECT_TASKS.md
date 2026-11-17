# SFRA — рабочий реестр задач и двухэтапная проверка

> **Реестр ведут аналитики.** Они самостоятельно проверяют отчёты исполнителей, ставят отметки, обновляют HEAD и статусы и продолжают утверждённый спектр задач.
>
> **Координатора вызывают только по сигналу аналитика:** весь его спектр задач завершён либо возникло ограничение, требующее архитектурного решения или нового указания. Координатор не обновляет файл после каждого промежуточного отчёта.
>
> Последняя независимая пакетная проверка: **2026-11-17**. Основная ветка: `main`.

## 1. Роли и статусы

### Аналитик ведёт рабочую часть реестра

Аналитик самостоятельно:
- проверяет PR, код, тесты, CI и интеграционные артефакты;
- отмечает выполненные критерии в своём чек-листе;
- фиксирует проверенный HEAD commit, дату и ссылки на доказательства;
- ставит `ANALYST_COMPLETE_UNREVIEWED` для завершённой задачи в рамках согласованного контракта;
- снимает техническую блокировку, когда её критерии выполнены и доказательства доступны;
- продолжает следующую задачу утверждённого спектра без ожидания координатора;
- добавляет технические подзадачи, необходимые для исполнения уже утверждённого контракта.

Аналитик вызывает координатора только тогда, когда:
1. весь текущий порученный спектр выполнен: `ANALYST_SCOPE_COMPLETE`;
2. дальнейшая работа требует изменения контракта, приоритета, зависимости или решения за пределами полномочий аналитика: `ANALYST_BLOCKED_NEEDS_COORDINATOR`.

В случае блокировки аналитик фиксирует конкретный вопрос, варианты решения и последствия. Формулировка «не получается» без технической причины недостаточна.

### Координатор ведёт отдельную часть реестра

Координатор:
- не участвует в каждом цикле исполнения;
- проводит пакетный аудит накопившихся результатов по сигналу аналитика;
- отмечает только собственные пункты в отдельных чек-листах;
- фиксирует архитектурное решение, приёмку или возврат;
- не подменяет отметки аналитика и не требует своего подтверждения для продолжения работы в уже согласованных границах.

### Статусы

| Статус | Кто устанавливает | Значение |
|---|---|---|
| `WAITING_FOR_IMPLEMENTATION` | Аналитик | Исполнитель ещё должен реализовать требования. |
| `IMPLEMENTATION_IN_PROGRESS` | Аналитик | Исполнитель работает над задачей. |
| `WAITING_FOR_ANALYST` | Аналитик | Реализация поступила, проверка аналитика ещё не завершена. |
| `ANALYST_REVIEW_IN_PROGRESS` | Аналитик | Аналитик проверяет код и доказательства. |
| `ANALYST_COMPLETE_UNREVIEWED` | Аналитик | Критерии задачи проверены; задача готова в рамках утверждённого контракта. Координаторский аудит ещё не выполнен, но это само по себе не блокирует следующие согласованные задачи. |
| `ANALYST_SCOPE_COMPLETE` | Аналитик | Весь его текущий спектр завершён; нужен пакетный обзор координатора. |
| `ANALYST_BLOCKED_NEEDS_COORDINATOR` | Аналитик | Требуется решение за пределами утверждённого контракта. |
| `COORDINATOR_REVIEWED_ACCEPTED` | Координатор | Координатор провёл аудит и подтвердил результат. |
| `COORDINATOR_REVIEWED_RETURNED` | Координатор | Координатор вернул результат с конкретными замечаниями. |
| `COORDINATOR_ACCEPTED_NOT_MERGED` | Координатор | Техническая работа принята, но PR ещё не объединён. |
| `BLOCKED` | Аналитик / координатор | Есть конкретная незакрытая зависимость или ограничение. |
| `DONE` | Аналитик отмечает выполнение; координатор подтверждает при пакетном аудите | Все критерии и необходимые действия по интеграции/закрытию выполнены. |

### Привязка проверок к commit

Отметки проверки кода действительны только для указанного HEAD. Если PR получает новые коммиты:
- аналитик указывает новый HEAD;
- затронутые критерии проверяются заново;
- устаревшие галочки снимаются; не затронутые можно сохранить только с явным обоснованием;
- координаторское подтверждение не переносится на новый HEAD автоматически.

---

## 2. Текущий статус проекта

| ID | Исполнитель | Работа | Статус | Что блокирует / следующий шаг |
|---|---|---|---|---|
| SFRA-E1-01 | E1 | Единый атомарный Source Scope API + current-node resolver | **WAITING_FOR_ANALYST** | Реализация появилась в PR #11; нужна независимая проверка аналитика и согласование E3 response adapter. |
| SFRA-E3-01 | E3 | C1: SourceReader, SearchAdapter, dependency metadata и E1 API adapter | **WAITING_FOR_IMPLEMENTATION** | Response adapter E1/E3 и real smoke уже работают; остаются E3-side parent/sibling cross-checks, adversarial tests, fail-closed unknown metadata, SearchAdapter diagnostic propagation и актуализация docs. |
| SFRA-E3-02 | E3 | Реальная интеграция E2 → E3 → E1 → Context Pack | **BLOCKED** | PR-triggered real E1/E2/E3 smoke успешен (run 44020916667), но полный спектр заблокирован оставшимися критериями SFRA-E3-01 и неполными негативными сценариями. |
| SFRA-E2-01 | E2 | Active-only фильтрация и интеграционная проверка | **COORDINATOR_ACCEPTED_NOT_MERGED** | Повторная реализация не требуется; PR #7 ещё открыт. |

---

## 3. Последняя пакетная сверка PR #10 и PR #11

Проверка выполнена по текущим HEAD веток, а не только по HEAD, указанным в комментариях координатора 2.

### PR #11 — E1

- [PR #11 — E1 source-verified structural node lookup API](https://github.com/yeatu/obsidianGP/pull/11)
- Текущий HEAD: `ebb5c92abac01e1316a5165a8f45897bd06758df`
- Состояние: open, not merged.
- CI:
  - [Run 44019097575 — E1 / Context Builder tests](https://github.com/yeatu/obsidianGP/actions/runs/44019097575): success. Шаг проверки атомарного Source Scope API на изолированной копии production snapshot завершился успешно.
  - [Run 44019097699 — structural indexer stages B/C](https://github.com/yeatu/obsidianGP/actions/runs/44019097699): success; повторный индексаторный прогон на закреплённом Vault также завершился успешно.

**Что изменилось с предыдущей проверки:** E1 уже экспортирует:
- `read_source_scope(..., scope, snapshot_id)`;
- `resolve_current_node(..., snapshot_id)`;
- типы `SourceScopeResult` и `CurrentNodeAddress`.

Реализованы четыре scope: node / parent / neighbors / document. Код использует одно read-only SQLite connection и одну read-транзакцию на scope-вызов, один исходный file read и передаёт `snapshot_id` без изменений. Результаты содержат `document_hash`, `index_generation` и исходные metadata. Старые функции чтения оставлены как обёртки.

CI подтверждает, что текущий E1 API вызывается против изолированной копии production `sfra-state` SQLite и Vault checkout по commit из manifest; в этом прогоне проверены все четыре scope. Отдельная индексация закреплённого реального Vault показала 66 документов, 9 080 узлов, 21 Passage и 2 пустых документа. Production sidecar и исходный Vault не должны изменяться.

**Оставшаяся граница:** E1 возвращает типизированные dataclass-объекты. Их формат пока не совпадает с Mapping/envelope, который ожидает E3. Это не отменяет прогресс E1 по атомарному чтению; совместимость должна быть закрыта явным E3 adapter или согласованным изменением публичного контракта. Не требовать от E1 выдумывать policy metadata.

#### Чек-лист аналитика E1

- [ ] Проверен текущий HEAD `ebb5c92...` и diff PR #11.
- [ ] Подтверждены один SQLite connection и одна read-транзакция для каждого scope.
- [ ] Проверены node / parent / neighbors / document.
- [ ] Проверена корректность parent/sibling связей и source order на уровне E1 API.
- [ ] Проверены `document_hash`, `index_generation`, source path, coordinates и exact raw_text.
- [ ] Проверены fail-closed статусы и пустые fragments при ошибках.
- [ ] Проверен `resolve_current_node()` и отсутствие fuzzy/historical fallback.
- [ ] Проверен snapshot echo.
- [ ] Проверены CI runs и изолированный production snapshot прогон.
- [ ] Подтверждено отсутствие изменений production Vault и `sfra-state`.

**Итог аналитика**
- [ ] Аналитик считает SFRA-E1-01 выполненной в рамках утверждённого контракта.
- [ ] Если это закрывает весь текущий спектр E1, выставлен `ANALYST_SCOPE_COMPLETE`.
- [ ] Если обнаружено архитектурное ограничение, выставлен `ANALYST_BLOCKED_NEEDS_COORDINATOR` с конкретным вопросом.

HEAD аналитика: `не указан`  
Дата проверки: `не указана`  
Отчёт / артефакты: `не указаны`

### PR #10 — E3 C1

- [PR #10 — E3 C1: E2 SearchAdapter and snapshot binding](https://github.com/yeatu/obsidianGP/pull/10)
- Проверенный HEAD аналитика: `dfe887738655b7ea35bb06fe89caeb6d7ee53ab3`
- Состояние: open, draft.
- Ветка: ahead 17 / behind 7 относительно актуального `main` на момент проверки.
- [Run 44020916692 — C1 contract tests](https://github.com/yeatu/obsidianGP/actions/runs/44020916692): success; B1 **45 passed**, C1 **49 passed**.
- [Run 44020916667 — real E1/E2/E3 integration](https://github.com/yeatu/obsidianGP/actions/runs/44020916667): success, event `pull_request` (не `workflow_dispatch`).

**Независимое решение:** C1 остаётся **WAITING_FOR_IMPLEMENTATION**. E1 dataclass adapter и фактическая интеграция уже подтверждены; остаются E3-A, E3-B и E3-E.

#### Подтверждённый прогресс

1. E3 `E1SourceReader._mapping()` теперь принимает E1 dataclass result через `to_dict()`. `_normalize_native_scope()` переводит E1 `anchor / parent / previous / next / document` в E3 envelope и роли фрагментов. Есть тест `test_source_reader_accepts_e1_public_result_dataclasses`.
2. Snapshot binder получает фактические Git HEAD через `git rev-parse`, проверяет чистоту checkout, manifest source commit и SQLite digest.
3. Бюджет считается E3 TokenCounter после чтения полного scope; E1 не получает budget, исходный текст не обрезается.
4. PR-CI на проверенном HEAD успешен: B1 45 / C1 49.
5. Реальный workflow run 44020916667 вызвал опубликованный E2 runtime и реальные E1 `resolve_current_node()` / `read_source_scope()` на закреплённых checkouts:
   - E1 API branch HEAD: `a5456c471d9bd97a8da34b90da13cc4fa7b486ea`;
   - `sfra-state` HEAD: `fb0b45ae0e5043e342c790d43e2b341ca65d7f2b`;
   - Vault commit из manifest: `2a3c54fa7a9e910f4c9621c8fe00f41a061fc158`;
   - все четыре scope вернули `ok`; resolver вернул текущий адрес; wrong hash вернул `stale_source`, неизвестный Node ID — `not_found`;
   - Context Pack включил один source-backed candidate; статус `budget_limited`, два кандидата отложены; scope budget вернул `budget_exceeded`, владелец бюджета — E3;
   - SHA-256 SQLite, manifest, sidecar tracked tree и Vault tree не изменились; HEAD sidecar и Vault остались прежними; оба checkout чистые.
   
   Это реальный E1/E2/E3 smoke test, запущенный по событию PR. Он не является ручным `workflow_dispatch` и не закрывает все негативные/metadata gates.

#### Блокер E3-A — проверка идентичности родителя и соседей

Текущий normalizer сверяет каждый fragment с соответствующей именованной записью E1 по полному набору provenance fields и отклоняет неизвестные/повторные fragment Node ID. Но он пока не проверяет сами cross-relations между named records:
- `parent.node_id == anchor.parent_node_id`;
- `previous.parent_node_id == anchor.parent_node_id` и `next.parent_node_id == anchor.parent_node_id`;
- source order: previous < anchor < next;
- Node ID не повторяется между target / parent / previous / next.

E1 публичная функция сама отбирает parent и immediate siblings в одной read-транзакции, но E3 должен валидировать контракт на своей границе, а не только переносить доверенные relation fields.

**Требуется от E3:** добавить эти проверки в `source_reader.py` и adversarial tests:
- wrong parent ID;
- sibling from another parent;
- reversed neighbors;
- duplicate Node IDs across roles.

#### Блокер E3-B — отсутствие dependency metadata не должно давать complete

На текущем HEAD `search_adapter.py` применяет placeholder defaults `normal / [] / false` и создаёт diagnostic `dependency_policy_defaults_applied` с severity `info`. При этом:
- отсутствие одного/нескольких policy fields не меняет `SearchBatch.complete`;
- `ContextIntegrationPipeline.run()` не переносит `SearchAdapterResult.diagnostics` в Context Pack;
- статус pack не понижается из-за неизвестной dependency metadata;
- `E1DependencyResolver` также применяет defaults, а его diagnostics хранятся в изменяемом списке экземпляра между вызовами.

Следовательно, отсутствующие policy metadata всё ещё могут быть восприняты как явное отсутствие ограничений.

**Требуется от E3:**
- различать explicit policy values и unknown/missing values;
- передавать SearchAdapter diagnostics в Context Pack;
- при missing/partial metadata не допускать `status=complete`: использовать явный `integrity_warning` / `incomplete` или отказ;
- изолировать/reset resolver diagnostics на каждый pipeline run;
- добавить pipeline tests: missing/partial metadata не даёт complete; все три явно заданных значения, включая явное отсутствие зависимостей, обрабатываются как complete при отсутствии иных проблем.

E1 не должен выдумывать policy metadata. Defaults допустимы только как технические placeholders и не подтверждают полноту dependency information.

#### E3-C — адаптер типов E1/E3 закрыт

На проверенном HEAD E3 принимает E1 dataclasses через `to_dict()`, нормализует native `anchor / parent / previous / next / document` в E3 envelope. Это дополнительно подтверждено реальным run 44020916667, который использовал E1 API branch `a5456c4...`, а не FixtureE1ScopeAPI. Блокер несовместимости форматов E1/E3 снимаю.

#### E3-D — Snapshot binder и real E1/E2/E3 smoke

Snapshot binder получает фактические HEAD и проверяет clean checkout, manifest, SQLite digest. Run 44020916667 подтверждает реальный E2 → E3 → E1 → Context Pack на закреплённом snapshot и неизменность Vault/sidecar. Однако run был запущен событием `pull_request`, а не `workflow_dispatch`. Он доказывает рабочий integration path, но не закрывает весь набор негативных сценариев E3-02.

#### Блокер E3-E — устаревшая документация

README всё ещё утверждает, что PR #11 предоставляет только `get_node_by_id()`, и содержит старые CI/head values. `E1_Source_Scope_API_v1.md` всё ещё включает `budget_tokens` в сигнатуру E1 и описывает token accounting на стороне E1. Обновить документацию под фактические `read_source_scope()` / `resolve_current_node()`, native dataclass adapter и правило: бюджет принадлежит E3, E1 отдаёт полный scope.

#### Чек-лист аналитика E3 / C1

- [x] Проверен текущий HEAD `dfe8877...` и актуальный diff PR #10.
- [x] Проверен актуальный C1 CI: 45 B1 + 49 C1 tests, run 44020916692.
- [x] Проверено использование реального опубликованного E2 runtime в C1 CI.
- [ ] SourceReader валидирует parent ID, sibling parent IDs, source order и отсутствие дублирующихся Node ID между ролями.
- [ ] Пройдены adversarial tests: wrong parent, wrong-parent sibling, reversed neighbors, duplicate IDs.
- [ ] Dependency metadata unknown/partial явно диагностируется и не приводит к complete.
- [ ] SearchAdapter diagnostics передаются в Context Pack; повторные pipeline runs не наследуют старые resolver diagnostics.
- [x] E3 response adapter преобразует реальные E1 dataclass results в E3 envelope; подтверждено unit contract test и real run 44020916667.
- [x] Реальные E1 функции проверены на node / parent / neighbors / document и resolver в run 44020916667.
- [x] Snapshot binder получает реальные Git HEAD и проверяет чистоту checkout.
- [ ] README и E1 Source Scope contract обновлены.
- [x] C1 остаётся в границах SearchAdapter / SourceReader boundary / Snapshot binding; Issue worker, recovery sweep и MCP adapter не добавлены.

**Итог аналитика**
- [ ] Аналитик считает C1 завершённым только после закрытия E3-A / E3-B / E3-E.
- [ ] Если C1 закрывает текущий спектр E3, выставлен `ANALYST_SCOPE_COMPLETE` и подготовлен сводный отчёт.
- [ ] Если нужен пересмотр архитектуры/контракта, выставлен `ANALYST_BLOCKED_NEEDS_COORDINATOR` с конкретным вопросом.

HEAD аналитика: `dfe887738655b7ea35bb06fe89caeb6d7ee53ab3`  
Дата проверки: `2026-11-17`  
Отчёт / артефакты: [PR #10](https://github.com/yeatu/obsidianGP/pull/10), [C1 CI 44020916692](https://github.com/yeatu/obsidianGP/actions/runs/44020916692), [real E1/E2/E3 run 44020916667](https://github.com/yeatu/obsidianGP/actions/runs/44020916667)  
Статус аналитика: **WAITING_FOR_IMPLEMENTATION**

### SFRA-E3-02 — реальная интеграция E2 → E3 → E1 → Context Pack

**Исполнитель:** E3  
**Статус:** BLOCKED  
**Текущий блокер:** SFRA-E3-01 — parent/neighbors validation, fail-closed dependency metadata, diagnostic propagation и документация.

**Фактический smoke test уже выполнен:** [Run 44020916667 — real E1/E2/E3 integration](https://github.com/yeatu/obsidianGP/actions/runs/44020916667), success, event `pull_request`, HEAD `dfe887738655b7ea35bb06fe89caeb6d7ee53ab3`. Он использовал:
- E1 public API branch `executor-1/e1-source-read-api-mainline`, commit `a5456c471d9bd97a8da34b90da13cc4fa7b486ea`;
- immutable `sfra-state` HEAD `fb0b45ae0e5043e342c790d43e2b341ca65d7f2b`;
- Vault commit из manifest `2a3c54fa7a9e910f4c9621c8fe00f41a061fc158`;
- snapshot ID `2a3c54fa7a9e910f4c9621c8fe00f41a061fc158:fb0b45ae0e5043e342c790d43e2b341ca65d7f2b:sha256:3d5eacf5fc2f7f927af8f591f317ea95d56d0c0f53de1bc61cb54d23677fd072`.

В run подтверждены E2 status=ok (3 hits/candidates), current-node resolver, четыре scope со status=ok, wrong hash → stale_source, unknown Node ID → not_found, Context Pack Included=1 / Deferred=2 / status=budget_limited, scope budget → budget_exceeded / owner=E3. SQLite, manifest, sidecar tree, Vault tree и оба checkout HEAD не изменились; sidecar и Vault остались clean.

Этот PR-triggered smoke доказывает рабочий реальный путь, но не заменяет полный E3-02: metadata completeness/fail-closed, E3 cross-check parent/neighbors и расширенные негативные сценарии ещё не закрыты. Координаторский статус остаётся BLOCKED до закрытия SFRA-E3-01.

#### Чек-лист аналитика E3 / real integration

- [x] Сквозной прогон использует реальные E1/E2 API, не Fixture E1.
- [x] `bind_pinned_snapshot()` доказал actual sidecar/Vault HEAD и clean checkout.
- [x] Snapshot ID проверен на всех scope вызовах; resolver и pipeline используют тот же SnapshotRef.
- [x] Все четыре scope и resolver работают через adapter с фактическими E1 dataclass objects.
- [ ] Parent/neighbors relationships дополнительно проверены E3 adversarial contract tests.
- [ ] Metadata unknown/partial не даёт `complete`; проверка пока не реализована.
- [x] Context Pack содержит source-backed candidate с точным raw_text и Content Hash.
- [ ] Полный набор негативных сценариев (ambiguous/deleted, повреждённый source, cross-document/generation/snapshot mismatch) и budget handling проверен. В smoke проверены wrong hash, unknown ID и budget_exceeded.
- [x] C1 CI и real integration workflow прошли; evidence находится в job logs [44020916667](https://github.com/yeatu/obsidianGP/actions/runs/44020916667). Отдельный artifact не выгружался.
- [x] Production Vault, manifest и SQLite не изменились; sidecar/Vault tree hashes и HEAD до/после совпали.

**Итог аналитика**
- [ ] Реальная интеграция завершена, весь текущий спектр E3 закрыт; передан сводный отчёт.
- [ ] Либо отмечена блокировка с конкретным вопросом координатору.

HEAD аналитика: `dfe887738655b7ea35bb06fe89caeb6d7ee53ab3`  
Дата проверки: `2026-11-17`  
Отчёт / артефакты: [PR #10](https://github.com/yeatu/obsidianGP/pull/10), [run 44020916667](https://github.com/yeatu/obsidianGP/actions/runs/44020916667)


---

## 4. E2 — ранее принятая работа

### SFRA-E2-01 — фильтрация только актуальных active-узлов

**Исполнитель:** E2  
**Статус:** COORDINATOR_ACCEPTED_NOT_MERGED  
**PR:** [#7 — E2 active-only source filtering](https://github.com/yeatu/obsidianGP/pull/7)  
**Проверенный HEAD:** `af4469d3badf0aa902568ae1926f5b5309a70655`  
**CI:** [Run 44010638395 — success](https://github.com/yeatu/obsidianGP/actions/runs/44010638395).

Техническая работа принята в согласованных границах: active-only фильтрация, исключение ambiguous/stale/deleted как источников, корректная проекция parent ID, сохранение null document hash, полный integrity check и проверка пересобранного архивного пакета. Подтверждены 64 passed, 0 failures/errors/skipped, реальный source hash и отсутствие изменений Vault/SQLite.

Дополнительная реализация E2 не требуется. PR #7 остаётся открытым и не объединён в `main`. Это не повод повторно привлекать E2 к уже принятой задаче.

---

## 5. Личный чек-лист координатора — аудит 2026-11-17

> Этот блок принадлежит координатору. Аналитики его не заполняют. Он заполняется при пакетном вызове координатора. Галочки ниже фиксируют только то, что координатор действительно проверил в этой сверке.

### E1 / PR #11

- [x] Сверен текущий PR HEAD `ebb5c92...`, он отличается от старого HEAD `74cc68e...`, на котором основаны комментарии 6938152254 и 6938268190.
- [x] Подтверждены публичные `read_source_scope()` и `resolve_current_node()`.
- [x] Проверен код одного connection / одной read-транзакции на scope.
- [x] Проверены тестовые сценарии четырёх scope, snapshot echo и resolver.
- [x] Проверен успешный CI run 44019097575: production `sfra-state` скопирован в изолированную SQLite; все четыре scope вызваны успешно.
- [x] Проверен run 44019097699: structural suite и реальный Vault indexing прошли успешно.
- [x] Зафиксирован несовпадающий с E3 тип/response contract; не выдаётся за отсутствие самого E1 API.
- [ ] Выполнена отдельная независимая аналитическая приёмка E1.

**Решение координатора:** реализация E1 существенно продвинулась и закрыла атомарный API на уровне собственного публичного контракта. Ожидает аналитическую приёмку. Совместимость с E3 должна быть закрыта на уровне явно определённого adapter/contract.

### E3 C1 / PR #10

- [x] Сверен текущий PR HEAD `c5398cd...` и фактический код.
- [x] Проверен успешный CI run 44018830452: 45 B1 + 48 C1 tests.
- [x] Подтверждено, что C1 CI использует fixture E1 для source reads; real E1/Vault integration этим run не доказана.
- [x] Подтверждено отсутствие parent ID / sibling parent / ordering / cross-role duplicate проверки в текущем E3 SourceReader.
- [x] Подтвержден fail-open путь при отсутствующей dependency metadata: defaults + warning, SearchBatch остаётся complete, pipeline не передаёт SearchAdapter diagnostics в pack.
- [x] Подтверждён response mismatch: E1 dataclasses/field names не соответствуют Mapping/envelope, ожидаемому E3.
- [x] Подтверждено, что Snapshot binder теперь читает actual Git HEAD и проверяет clean checkout.
- [x] Проверено, что real integration workflow пока manual и успешного run не найдено.
- [x] Проверено, что README E3 всё ещё описывает старый E1 API.
- [ ] Принята C1.

**Решение координатора:** C1 остаётся частично реализованным и не принимается до закрытия E3-A / E3-B / E3-C и обновления документации. Real integration остаётся отдельной следующей контрольной точкой.

### E3 real integration

- [ ] Запущен и проверен реальный сквозной workflow.
- [ ] Проверен результат с реальными E1 dataclasses через adapter.
- [ ] Проверены реальные четыре scope и Context Pack.
- [ ] Проверены metadata completeness и fail-closed ошибки.
- [ ] Подтверждена неизменность production Vault/sidecar.

**Решение координатора:** оставить BLOCKED до устранения C1 блокеров.

---

## 6. Обновление и вызов координатора

### Обычный цикл

1. Исполнитель отправляет отчёт и обновляет PR.
2. Аналитик проверяет его, обновляет свои галочки, HEAD, ссылки и замечания.
3. Аналитик возвращает исполнителю конкретные дефекты либо принимает задачу в рамках текущего контракта.
4. Аналитик продолжает следующие согласованные задачи. Координатор не вызывается после каждого отчёта.

### Когда аналитик завершил спектр

Аналитик ставит `ANALYST_SCOPE_COMPLETE` и передаёт один сводный отчёт со ссылками на все соответствующие задачи/PR/HEAD. Тогда пользователь вызывает координатора для пакетного аудита.

### Когда аналитик упёрся в ограничение

Аналитик ставит `ANALYST_BLOCKED_NEEDS_COORDINATOR`, формулирует конкретный вопрос, варианты и последствия. Тогда пользователь вызывает координатора для решения.

### Что координатор обновляет после пакетной проверки

Только свои чек-листы, итоговое решение, архитектурные указания и новые зависимости/критерии, если они действительно изменились. Аналитик продолжает быть владельцем текущих рабочих статусов и своих отметок.

**Главный принцип SFRA:** поисковый индекс ускоряет обнаружение, но не становится второй базой знаний. В Context Pack попадает только проверенный текст первоисточника, связанный с актуальным индексным snapshot.
