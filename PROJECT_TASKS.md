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
| SFRA-E3-01 | E3 | C1: SourceReader, SearchAdapter, dependency metadata и E1 API adapter | **WAITING_FOR_IMPLEMENTATION** | Не закрыты проверки родителя/соседей, fail-closed metadata и совместимость типов ответов E1/E3. |
| SFRA-E3-02 | E3 | Реальная интеграция E2 → E3 → E1 → Context Pack | **BLOCKED** | Снять блокеры SFRA-E3-01 и запустить manual real-integration workflow. |
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
- Текущий HEAD: `c5398cd2495586dcc5fdc49bb89ef7cc7797a838`
- Состояние: open, draft.
- [Run 44018830452 — SFRA E3 integration C1 tests](https://github.com/yeatu/obsidianGP/actions/runs/44018830452): success.
  - B1 regression: 45 passed.
  - C1 tests: 48 passed.
  - Это fixture/contract CI, не production E1 end-to-end.

**Независимое решение:** C1 — существенная частичная реализация, но приёмка остаётся отклонённой. Подтверждены следующие блокеры на текущем HEAD.

#### Блокер E3-A — проверка идентичности родителя и соседей

В `source_reader.py` проверяется наличие роли `parent_context` и допустимость ролей соседей. Однако E3 не проверяет:
- что `parent_context.node_id` точно равен `target_source.parent_node_id`;
- что previous/next принадлежат тому же `parent_node_id`, что и target;
- что предыдущий сосед действительно расположен до target, а следующий — после него;
- что один Node ID не возвращён под разными ролями.

Текущие проверки наличия ролей, общего path/hash/generation и уникальности имён ролей недостаточны.

**Требуется от E3:** добавить в response/fragment contract идентификаторы родителя и координаты source order; проверять точное соответствие parent ID, общность родителя соседей, последовательность previous → target → next и отсутствие дублирующихся Node ID между ролями.

Обязательные adversarial tests: wrong parent, sibling from another parent, reversed neighbors, duplicate IDs across roles.

#### Блокер E3-B — отсутствие dependency metadata не должно давать complete

В `search_adapter.py` при отсутствии dependency metadata подставляются значения `normal / [] / false` и добавляется warning `dependency_metadata_unavailable`. Но:
- это предупреждение не меняет `SearchBatch.complete`;
- `pipeline.py` передаёт в ContextBuilder только SearchBatch;
- `SearchAdapterResult.diagnostics` не включаются в диагностики Context Pack;
- pipeline не понижает статус Context Pack из-за отсутствия dependency metadata.

Следовательно, отсутствие сведений о зависимостях может остаться незаметным для итогового Context Pack, а его статус — `complete`.

**Решение по архитектуре metadata:** E1 передаёт только действительно сохранённые в `metadata_json` значения. E1 не выдумывает `preservation`, `required_with` или `parent_context_required`. Но отсутствие metadata не является доказательством отсутствия зависимостей. E3 должен различать «значения явно заданы» и «значения неизвестны».

**Требуется от E3:**
- сохранить placeholder defaults, если они нужны для технического построения candidate, но явно помечать dependency metadata как unavailable/unknown;
- передавать SearchAdapter diagnostics в итоговый Context Pack;
- при отсутствии/неполноте необходимых dependency metadata отказывать в `complete` либо выставлять явный `integrity_warning` / `incomplete`;
- не терять диагностику на уровне pipeline.

Обязательный pipeline regression test: пустая или неполная metadata не может приводить к `status=complete`. Отдельно проверить случай, когда все dependency поля присутствуют и явно обозначают отсутствие зависимостей.

#### Блокер E3-C — фактический формат E1/E3 API пока несовместим

Это уточнение к замечанию координатора 2: E1 теперь уже реализовал единый scope API, однако текущий формат ответа всё ещё не подходит E3 напрямую.

На текущем HEAD E1:
- `read_source_scope()` возвращает объект `SourceScopeResult`, а не `Mapping`;
- `resolve_current_node()` возвращает объект `CurrentNodeAddress`, а не `Mapping`;
- `SourceScopeResult.to_dict()` использует поля `anchor / parent / previous / next / document`; в нём нет E3-поля `target_source`;
- fragments сериализуются как NodeRecord без E3-поля `role`;
- `CurrentNodeAddress.to_dict()` возвращает address-поля на верхнем уровне, а E3 ожидает вложенный `address`.

E3 `E1SourceReader._mapping()` требует Mapping и не вызывает `to_dict()`. Новый `run_real_e1_integration.py` передаёт функции E1 напрямую через `SimpleNamespace`. Поэтому фактический production вызов сейчас не проходит E3 response boundary.

**Требуется от E3:** добавить явный публичный adapter/normalizer, который принимает типизированные E1 dataclass-результаты и переводит их в согласованный E3 envelope, включая роли fragments и `target_source`. Либо согласовать и реализовать один общий публичный response schema. Нельзя обходить это через прямой SQL к E1 или через fixture-only имитацию.

Обязательные contract tests должны вызывать реальные экспортированные функции E1 и проверять node / parent / neighbors / document, resolver, success/error и snapshot echo.

#### Блокер E3-D — Snapshot binder: код исправлен, реальная интеграция ещё не доказана

Предыдущее замечание о том, что `bind_pinned_snapshot()` не устанавливает фактический HEAD, устарело для текущего HEAD PR #10.

В текущем `snapshot.py`:
- `_git_head()` вызывает `git rev-parse --verify HEAD^{commit}`;
- `_git_status()` проверяет чистоту checkout;
- binder получает фактические HEAD sidecar и Vault;
- Vault HEAD сравнивается с commit из manifest;
- manifest проверяется через E1 verifier, точные байты хешируются;
- ручной workflow checkout-ит sidecar по `sfra-state` и Vault по commit из manifest.

**Что осталось:** новый workflow `sfra-e3-real-e1-integration.yml` имеет `workflow_dispatch`. В проверенных PR-CI runs текущего HEAD отдельный успешный run этого workflow не представлен; поэтому реальная E1/E2/E3 интеграция пока не доказана. Само наличие workflow не заменяет успешный ручной прогон. После исправления API response adapter нужно запустить его и приложить run/артефакты.

#### Блокер E3-E — устаревшая документация

Текущий `README.md` PR #10 всё ещё утверждает, что PR #11 предоставляет только `get_node_by_id()`. Это уже не соответствует текущему HEAD E1: доступны `read_source_scope()` и `resolve_current_node()`. README/контрактный документ нужно обновить и описать фактический response adapter gap.

#### Чек-лист аналитика E3 / C1

- [ ] Проверен текущий HEAD `c5398cd...` и актуальный diff PR #10.
- [ ] Проверен актуальный CI: 45 B1 + 48 C1 tests.
- [ ] Проверено, что SourceReader валидирует parent ID, sibling parent IDs, source order и отсутствие дублирующихся Node ID.
- [ ] Пройдены adversarial tests для wrong parent, wrong parent sibling, reversed neighbors и duplicate IDs.
- [ ] Dependency metadata unavailable/partial явно диагностируется и не приводит к `complete`.
- [ ] SearchAdapter diagnostics передаются в Context Pack.
- [ ] Есть pipeline-level regression test на fail-closed metadata.
- [ ] E3 response adapter преобразует реальные E1 dataclass-результаты в согласованный envelope.
- [ ] Проверены все четыре scope и resolver с реальными E1 функциями, а не только FixtureE1ScopeAPI.
- [ ] Snapshot binder получает реальные Git HEAD и проверяет чистоту checkout.
- [ ] README/контракт обновлены и отражают текущий E1 API.
- [ ] C1 остаётся ограниченным SearchAdapter / SourceReader boundary / Snapshot binding; Issue worker, recovery sweep и MCP adapter не добавляются.

**Итог аналитика**
- [ ] Аналитик считает C1 завершённым только после закрытия всех применимых пунктов.
- [ ] Если C1 закрывает текущий спектр E3, выставлен `ANALYST_SCOPE_COMPLETE` и подготовлен сводный отчёт.
- [ ] Если нужен пересмотр архитектуры или контракта, выставлен `ANALYST_BLOCKED_NEEDS_COORDINATOR` с точным вопросом.

HEAD аналитика: `не указан`  
Дата проверки: `не указана`  
Отчёт / артефакты: `не указаны`

### SFRA-E3-02 — реальная интеграция E2 → E3 → E1 → Context Pack

**Исполнитель:** E3  
**Статус:** BLOCKED  
**Текущий блокер:** SFRA-E3-01 — response adapter и fail-closed исправления C1.

После их закрытия требуется:
1. Запустить manual workflow реальной интеграции.
2. Использовать реальные E2 runtime и E1 public functions, зафиксированные Vault/sidecar checkouts и один SnapshotRef.
3. Пройти SearchAdapter → DependencyResolver → E1 Source Scope API → Context Builder → Context Pack.
4. Проверить все четыре scope, resolver, source identity, metadata completeness, негативные сценарии и budget.
5. Сверить database/manifest/Vault checksums до/после и убедиться, что production данные не изменились.

#### Чек-лист аналитика E3 / real integration

- [ ] Сквозной прогон использует реальные E1/E2 API, не fixture E1.
- [ ] `bind_pinned_snapshot()` доказал actual sidecar/Vault HEAD и clean checkout.
- [ ] Snapshot ID совпадает на каждом этапе.
- [ ] Все четыре scope и resolver работают через adapter с фактическими E1 dataclass-объектами.
- [ ] Parent/neighbors relationships подтверждены.
- [ ] Metadata unknown/partial не даёт `complete`.
- [ ] Context Pack содержит точный исходный текст с согласованными хешами.
- [ ] Негативные случаи и budget handling проходят без partial/truncated source.
- [ ] CI/workflow run успешен, артефакты приложены.
- [ ] Production Vault, manifest и SQLite не изменились.

**Итог аналитика**
- [ ] Реальная интеграция завершена, весь текущий спектр E3 закрыт; передан сводный отчёт.
- [ ] Либо отмечена блокировка с конкретным вопросом координатору.

HEAD аналитика: `не указан`  
Дата проверки: `не указана`  
Отчёт / артефакты: `не указаны`

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
