# SFRA — рабочий реестр задач и двухэтапная проверка

> **Реестр ведут аналитики.** Они самостоятельно проверяют отчёты исполнителей, ставят отметки, обновляют HEAD и статусы и продолжают утверждённый спектр задач.
>
> **Координатора вызывают только по сигналу аналитика:** весь его спектр задач завершён либо возникло ограничение, требующее архитектурного решения или нового указания. Координатор не обновляет файл после каждого промежуточного отчёта.
>
> Последняя независимая пакетная проверка: **2026-11-17, после E1 HEAD `a5456c4` и E3 HEAD `dfe8877`**. Основная ветка: `main`.

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
| SFRA-E1-01 | E1 | Единый атомарный Source Scope API + current-node resolver | **ANALYST_COMPLETE_UNREVIEWED** | Проверенный финальный PR HEAD `f9b0edef6d5bdc05c73be6a10d9e66c5b10c8cf5` (implementation tree `433a474147b9353afdd4dee4af205a79dc21253d`); E1 scope завершён (`ANALYST_SCOPE_COMPLETE`), передан координатору на пакетный аудит. PR #11 открыт, mergeable, не объединён. |
| SFRA-E3-01 | E3 | C1: SourceReader, SearchAdapter, dependency metadata и E1 API adapter | **WAITING_FOR_IMPLEMENTATION** | Response adapter E1/E3 и real smoke уже работают; остаются E3-side parent/sibling cross-checks, adversarial tests, очистка resolver diagnostics между запусками, обновление README/PR description и синхронизация ветки с `main`. B1 policy defaults разрешены как defaults, не как source annotations. |
| SFRA-E3-02 | E3 | Реальная интеграция E2 → E3 → E1 → Context Pack | **WAITING_FOR_ANALYST** | Manual run `44020916667` успешен на E3 HEAD `dfe8877` и E1 HEAD `a5456c4`; аналитик должен проверить доказательства. Итог был `budget_limited` (1 included, 2 deferred), а не `complete`; финальная приёмка зависит от закрытия C1 integrity checks. |
| SFRA-E2-01 | E2 | Active-only фильтрация и интеграционная проверка | **COORDINATOR_ACCEPTED_NOT_MERGED** | Повторная реализация не требуется; PR #7 ещё открыт. |

---

## 3. Последняя пакетная сверка PR #10 и PR #11

Проверка выполнена по актуальным HEAD `a5456c4...` (E1) и `dfe8877...` (E3), с повторной проверкой последних CI и manual integration workflow. Более ранние HEAD и комментарии ниже трактуются как история, а не как действующее состояние.

### PR #11 — E1

- [PR #11 — E1 atomic Source Scope API and current-node resolver](https://github.com/yeatu/obsidianGP/pull/11)
- Финальный проверенный PR HEAD: `f9b0edef6d5bdc05c73be6a10d9e66c5b10c8cf5`.
- Implementation tree: `433a474147b9353afdd4dee4af205a79dc21253d`; финальный HEAD дополнительно содержит merge-sync с актуальным `main` и аналитическую запись.
- Состояние: open, not merged, mergeable.
- Ветка `executor-1/e1-source-read-api-mainline`: **ahead 10 / behind 0** относительно `main` на момент проверки.
- Force-push не использовался.

**CI на финальном HEAD**
- [Run 44023930642 — E1 source API](https://github.com/yeatu/obsidianGP/actions/runs/44023930642): `e1-source-api-tests` success, **88 passed**; production snapshot copy, manifest-pinned Vault checkout, все четыре scope + resolver и Vault clean guards завершились успешно. Job `unit-tests` — **skipped**, не success и не failure.
- [Run 44023930630 — structural indexer](https://github.com/yeatu/obsidianGP/actions/runs/44023930630): success, **88 passed**; повторная индексация реального Vault дала 66 unchanged skips, stale/ambiguous nodes — 0.

**Что подтверждено в реализации E1**
- Публичные `read_source_scope(db_path, vault_root, node_id, expected_hash, *, scope, snapshot_id)` и `resolve_current_node(db_path, node_id, *, snapshot_id)` экспортированы из `sfra_indexer`.
- Все четыре scope: `node`, `parent`, `neighbors`, `document`.
- Один SQLite connection и одна read-транзакция на каждый `read_source_scope`; SQL-чтения выполняются в этой транзакции.
- Для каждого фрагмента проверяются current lifecycle/version, document identity/generation, source path, Content Hash и coordinates. Возвращаются exact raw text, `document_hash` и `index_generation`.
- Исходный файл читается один раз на scope-вызов через secure path/symlink и file-integrity проверки. `document` возвращает полный Markdown без truncation.
- Fail-closed результат: при ошибке `fragments=[]`, content fields отсутствуют.
- `resolve_current_node()` возвращает только exact active/unambiguous Node ID и актуальный Content Hash; fuzzy/historical fallback отсутствует.
- Старые публичные `get_*_by_id` — wrappers единого API; типизированные результаты документированы в README и API spec.
- В E1 не добавлены token budget и синтезированные policy metadata; SQLite schema v2 не изменялась.

**Production snapshot / Vault integration**
- Production `sfra-state` checkout использован с `persist-credentials=false`; manifest и SQLite скопированы в `/tmp/e1-production-snapshot`. Integrity verification и все четыре scope + resolver исполнялись на изолированной копии.
- Manifest source ref: `executor-1/sfra-indexer-session-1`; Vault commit: `2a3c54fa7a9e910f4c9621c8fe00f41a061fc158`.
- Opaque snapshot ID: `sha256:3d5eacf5fc2f7f927af8f591f317ea95d56d0c0f53de1bc61cb54d23677fd072`.
- Real Vault: 66 документов, 9 080 узлов, 21 Passage, 2 пустых документа. Повторный индексатор пропустил 66 неизменённых документов; stale/ambiguous nodes — 0. Diff/status guards Vault прошли.
- Production SQLite не использовалась как writable target; SQLite API проверялся на изолированной копии. В workflow не сохраняются credentials для `sfra-state`.

**Граница snapshot-контракта**
- E1 принимает opaque `snapshot_id` и echo-ит его в success/error result.
- Проверка соответствия Snapshot ID manifest/Git/Vault, включая snapshot mismatch, относится к E3 Snapshot binder. E1 не выполняет Git/manifest validation и не делает checkout.

#### Чек-лист аналитика E1

- [x] Проверен финальный PR HEAD `f9b0edef6d5bdc05c73be6a10d9e66c5b10c8cf5` и implementation tree `433a474...`.
- [x] Подтверждены один SQLite connection и одна read-транзакция для каждого scope.
- [x] Проверены node / parent / neighbors / document.
- [x] Проверены `document_hash`, `index_generation`, source path, coordinates и exact raw_text.
- [x] Проверены fail-closed статусы и пустые fragments при ошибках.
- [x] Проверен `resolve_current_node()` и отсутствие fuzzy/historical fallback.
- [x] Проверен snapshot echo; snapshot binding/mismatch оставлены E3 согласно контракту.
- [x] Проверены CI runs 44023930642 и 44023930630; отдельно отмечен skipped `unit-tests`.
- [x] Проверены read-only checkout/copy процедуры для production `sfra-state` и clean Vault guards.
- [x] Проверена актуальность PR body/README/API spec и синхронизация с текущим `main`; CI повторён после sync.

**Итог аналитика**
- [x] Аналитик считает SFRA-E1-01 выполненной в рамках утверждённого контракта.
- [x] Весь текущий спектр E1 завершён: `ANALYST_SCOPE_COMPLETE`.
- [ ] `ANALYST_BLOCKED_NEEDS_COORDINATOR` не выставлен: архитектурного ограничения в согласованном E1 scope не обнаружено.

HEAD аналитика: `f9b0edef6d5bdc05c73be6a10d9e66c5b10c8cf5`  
Implementation tree: `433a474147b9353afdd4dee4af205a79dc21253d`  
Дата проверки: `2026-11-17`  
Отчёт / артефакты: [PR verification comment](https://github.com/yeatu/obsidianGP/pull/11#issuecomment-6939402215), [E1 CI run 44023930642](https://github.com/yeatu/obsidianGP/actions/runs/44023930642), [structural CI run 44023930630](https://github.com/yeatu/obsidianGP/actions/runs/44023930630)

Статус аналитика: **ANALYST_COMPLETE_UNREVIEWED / ANALYST_SCOPE_COMPLETE**

### PR #10 — E3 C1

- [PR #10 — E3 C1: E2 SearchAdapter and snapshot binding](https://github.com/yeatu/obsidianGP/pull/10)
- Текущий HEAD: `dfe887738655b7ea35bb06fe89caeb6d7ee53ab3`
- Состояние: open, **draft**.
- Ветка `executor-3/context-integration-stage-c1`: **ahead 18 / behind 7** относительно текущего `main`.
- [Run 44020916692 — SFRA E3 integration C1 tests](https://github.com/yeatu/obsidianGP/actions/runs/44020916692): success.
  - B1 regression: **45 passed**.
  - C1: **49 passed**.
- [Run 44020916667 — SFRA E3 real E1/E2 integration (manual)](https://github.com/yeatu/obsidianGP/actions/runs/44020916667): success. Job `real-e1-e2-e3` завершён успешно.

**Что исправлено после предыдущей пакетной проверки:**

1. **Формат E1/E3 ответа.** Текущий `source_reader.py` принимает E1 dataclass-объекты через `to_dict()`, нормализует `SourceScopeResult` (`anchor/parent/previous/next/document`) в E3 envelope (`target_source` и role-labelled fragments), а плоский `CurrentNodeAddress` преобразует во вложенный `address`. Добавлен тест `test_source_reader_accepts_e1_public_result_dataclasses`.
2. **Реальный integration workflow.** Workflow checkout-ит E3 HEAD `dfe8877...`, E1 ref `executor-1/e1-source-read-api-mainline` на HEAD `a5456c4...`, production `sfra-state` и Vault commit из manifest. Поэтому прежнее замечание «есть только ручной workflow, но запуска не было» устарело.
3. **Snapshot binding.** Проверены фактические Vault/sidecar HEAD, manifest digest, SQLite digest и clean checkout.

**Доказательства успешного реального прогона 44020916667:**

- Snapshot:
  - Vault commit: `2a3c54fa7a9e910f4c9621c8fe00f41a061fc158`;
  - sidecar commit: `fb0b45ae0e5043e342c790d43e2b341ca65d7f2b`;
  - manifest SHA-256: `sha256:3d5eacf5fc2f7f927af8f591f317ea95d56d0c0f53de1bc61cb54d23677fd072`.
- E2 вернул 3 hits и 3 source-verifiable candidates.
- E1 resolver вернул `ok`; dependency candidate разрешён.
- Все четыре scope вернули `ok`: node, parent, neighbors, document. Для каждого проверен тот же SnapshotRef.
- Неверный Content Hash дал `stale_source`; неизвестный Node ID — `not_found`.
- Превышение scope budget дало `budget_exceeded` с пустыми fragments; исходный текст не обрезался.
- Context Pack создан: `budget_limited`, 1 included и 2 deferred при лимите запроса 6 000 токенов. Это успешный ограниченный pack, а не статус `complete`.
- До/после совпали SQLite, manifest, tracked sidecar tree, Vault tree и HEAD обоих checkout; оба checkout остались clean.

**Оставшиеся блокеры на текущем HEAD:**

#### E3-A — проверка идентичности parent/neighbors

Адаптер теперь назначает роли по именованным relation records E1 и сравнивает их с набором E1 fragments. Но текущая реализация всё ещё не выполняет все обязательные cross-relation проверки:

- `parent_context.node_id == target_source.parent_node_id`;
- `previous_neighbor.parent_node_id == target_source.parent_node_id` и то же для next;
- source order: previous действительно расположен до target, next — после target;
- уникальность Node ID между target/parent/previous/next ролями.

В текущем наборе тестов нет adversarial сценариев для wrong parent ID, sibling from another parent, reversed neighbors и duplicate IDs.

**Требуется от E3:** добавить `parent_node_id` в обязательные поля каждого node fragment (кроме document fragment), реализовать проверки и добавить четыре adversarial tests. E1 уже выполняет проверки relations в своём собственном scope API; E3 обязан независимо корректно валидировать полученный контракт на своей границе.

#### E3-B — жизненный цикл diagnostics DependencyResolver

`E1DependencyResolver.diagnostics` — изменяемый список на весь срок жизни resolver. `ContextIntegrationPipeline.run()` его не сбрасывает. Если один pipeline сначала обработает stale/ambiguous dependency, а затем успешный запрос, старые diagnostics могут попасть во второй Context Pack.

**Требуется от E3:** изолировать diagnostics на границе каждого `run()` (или сделать их локальным результатом конкретного вызова) и добавить тест двух последовательных запросов на одном экземпляре pipeline: первый с dependency failure, второй без неё. Второй Context Pack не должен содержать старые сообщения.

#### E3-C — документация и синхронизация PR

- README E3 на текущем HEAD всё ещё утверждает, что E1 предоставляет только `get_node_by_id()`, и что реальная E1/Vault integration не доказана. Оба утверждения устарели.
- Контрактный документ E1 Source Scope API уже описывает нативные dataclass results и adapter boundary; однако он требует проверок parent identity / sibling parent / source order, которых пока нет в коде E3. Критерий документа соответствует требуемому контракту, реализация ещё отстаёт.
- PR description также не отражает новый HEAD, 49 C1 tests и успешный manual integration run.
- Ветка E3 отстаёт от текущего `main` на 7 коммитов. Требуется синхронизировать ветку и повторно запустить CI после синхронизации.

#### Решение по dependency metadata

Предыдущее требование «отсутствие metadata само по себе запрещает `status=complete`» снимается и заменяется следующим явным решением контракта:

- E1 возвращает только фактически существующие `NodeRecord.metadata`; E1 не создаёт policy metadata.
- B1 defaults `preservation="normal"`, `required_with=()`, `parent_context_required=False` разрешены как policy defaults, а не source annotations. Это согласуется с моделью B1 и аналитическим заключением в PR #10 comment 5933124374.
- E3 должен сохранять различие между source metadata и применёнными policy defaults. Диагностика `dependency_policy_defaults_applied` должна оставаться доступной вызывающему коду/итоговому integration result. Нельзя описывать defaults как сведения, найденные в первоисточнике.
- Отсутствие этих полей само по себе не требует `integrity_warning` и не является отдельным блокером C1. Если позже появится авторитетный источник обязательных dependency annotations, это будет отдельное версионированное изменение контракта.

#### Чек-лист аналитика E3 / C1

- [ ] Проверен текущий HEAD `dfe8877...` и актуальный diff PR #10.
- [ ] Проверен актуальный CI: 45 B1 + 49 C1 tests.
- [ ] Проверено, что E3 принимает реальные E1 dataclass results через adapter.
- [ ] Проверено, что parent ID exact match, siblings share target parent, source order корректен и Node IDs уникальны между ролями.
- [ ] Пройдены adversarial tests: wrong parent, sibling from another parent, reversed neighbors, duplicate IDs.
- [ ] Проверено, что diagnostics resolver из предыдущего pipeline run не попадают в следующий Context Pack.
- [ ] Policy defaults отличимы от source annotations и diagnostic доступна в результате интеграции.
- [ ] Проверены четыре scope и resolver на реальных E1 API.
- [ ] Snapshot binder проверяет actual Git HEAD, manifest/SQLite digest и clean checkout.
- [ ] README, контракт и PR description отражают текущий E1 API и реальные integration run.
- [ ] Ветка синхронизирована с актуальным `main`, CI повторён после sync.
- [ ] C1 остаётся ограниченным SearchAdapter / SourceReader boundary / Snapshot binding; Issue worker, recovery sweep и MCP adapter не добавляются.

**Итог аналитика**
- [ ] Аналитик считает C1 завершённым только после закрытия всех оставшихся пунктов.
- [ ] Если C1 закрывает текущий спектр E3, выставлен `ANALYST_SCOPE_COMPLETE` и подготовлен сводный отчёт.
- [ ] Если нужен пересмотр архитектуры или контракта, выставлен `ANALYST_BLOCKED_NEEDS_COORDINATOR` с точным вопросом.

HEAD аналитика: `не указан`  
Дата проверки: `не указана`  
Отчёт / артефакты: `не указаны`

### SFRA-E3-02 — реальная интеграция E2 → E3 → E1 → Context Pack

**Исполнитель:** E3  
**Статус:** WAITING_FOR_ANALYST  
**Текущий прогон:** [manual run 44020916667](https://github.com/yeatu/obsidianGP/actions/runs/44020916667), success, E3 HEAD `dfe8877...`, E1 HEAD `a5456c4...`.

Реальная связка E2 → E3 → E1 → Context Pack уже запущена успешно. Не нужно повторять сам smoke run без причины. Аналитик должен проверить артефакт/логи, SnapshotRef, все четыре scope, resolver, budget и read-only guards. Результат Context Pack был `budget_limited` (1 included, 2 deferred), что ожидаемо при бюджете текущего smoke request и не является доказательством `complete`.

#### Чек-лист аналитика E3 / real integration

- [x] Сквозной прогон использует реальные E1/E2 API, не fixture E1.
- [x] `bind_pinned_snapshot()` подтвердил actual sidecar/Vault HEAD и clean checkout.
- [x] Snapshot ID совпадает на каждом этапе.
- [x] Все четыре scope и resolver отработали на реальном snapshot.
- [x] Budget handling вернул `budget_exceeded` без partial/truncated source.
- [x] Production Vault, manifest, SQLite и tracked sidecar tree не изменились.
- [ ] Аналитик независимо проверил run 44020916667 и подтвердил соответствие текущему контракту.
- [ ] После закрытия E3-A/E3-B повторно проверены relationship negative cases и отсутствие diagnostics leakage.
- [ ] Context Pack с обычным бюджетом проверен отдельно; ожидаемый статус зависит от фактического budget/deferred результата, а не искусственно фиксируется как `complete`.

**Итог аналитика**
- [ ] Реальная интеграция принята в пределах проверенных условий.
- [ ] Либо отмечена конкретная блокировка, требующая решения координатора.

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

## 5. Личный чек-лист координатора — повторный аудит 2026-11-17

> Этот блок принадлежит координатору. Аналитики его не заполняют. Он фиксирует проверку после новых коммитов E1/E3 и заменяет предыдущие чек-листы для старых HEAD.

### E1 / PR #11 — HEAD `a5456c4...`

- [x] Сверен актуальный PR HEAD и PR state: open, not merged.
- [x] Подтверждены `read_source_scope()`, `resolve_current_node()`, dataclass result types и четыре scope.
- [x] Проверен job `e1-source-api-tests` в run 44019577613: success.
- [x] Проверено, что отдельный `unit-tests` job в run 44019577613 пропущен.
- [x] Проверен structural run 44019577558: 88 passed и повторный индекс реального Vault.
- [x] Проверено, что production snapshot копируется в isolated test area и четыре scope вызываются без записи в production branch.
- [x] Проверено текущее отставание E1 branch от main: 8 commits.
- [ ] Аналитик выполнил независимую приёмку текущего HEAD.
- [ ] Ветка синхронизирована с актуальным main и проверки повторены.

**Решение координатора:** сохранить `ANALYST_COMPLETE_UNREVIEWED`, установленный аналитиком. Координаторская приёмка ещё не выставлена. Реализацию не возвращать на доработку только из-за пропущенного отдельного job; аналитик должен явно указать, какие гарантии покрыты целевым E1 job. Перед финальным merge необходимо синхронизировать branch drift и повторить проверки.

### E3 / PR #10 — HEAD `dfe8877...`

- [x] Сверен актуальный PR HEAD и статус open/draft.
- [x] Проверен CI run 44020916692: 45 B1 + 49 C1 tests, success.
- [x] Проверено, что E3 теперь нормализует реальные E1 dataclass results через `to_dict()`.
- [x] Проверен manual real integration run 44020916667: success.
- [x] Подтверждено, что manual workflow использовал E1 HEAD `a5456c4...`.
- [x] Проверены четыре реальные scope, current-node resolver, stale hash, unknown Node ID, budget exceeded и read-only guards.
- [x] Подтверждено, что Context Pack имел status `budget_limited`, 1 included и 2 deferred; не приписывать ему status `complete`.
- [x] Подтверждено, что relationship identity/order checks в нормализаторе E3 ещё неполны.
- [x] Подтверждено, что diagnostics E1DependencyResolver сохраняются между run и не очищаются в pipeline.
- [x] Подтверждено, что README E3 всё ещё содержит устаревшие заявления про старый E1 API и отсутствие real integration.
- [x] Проверено отставание E3 branch от main: 7 commits.
- [x] Зафиксировано решение по B1 policy defaults: разрешены как policy defaults, не как source annotations; отдельный fail-closed blocker за их отсутствие снимается.
- [ ] Пройдены adversarial relationship tests.
- [ ] Исправлено накопление diagnostics между pipeline runs.
- [ ] README/PR description актуализированы.
- [ ] Ветка синхронизирована с main, CI повторён.
- [ ] C1 принята.

**Решение координатора:** C1 остаётся не принятой. Форматный E1/E3 blocker закрыт кодом и успешным real workflow. Остались E3-A, E3-B и документация/branch sync. Не возвращать E1 к переписыванию API без нового доказательства несовместимости.

### E3-02 / реальная интеграция

- [x] Успешный ручной real E1/E2/E3 workflow найден.
- [x] Все четыре Source Scope вызова вернули ok.
- [x] Context Pack сформирован из source-backed candidate.
- [x] SQLite, manifest, sidecar tree, Vault tree и HEAD не изменились.
- [x] SnapshotRef привязан к фактическим commit SHA и raw manifest digest.
- [ ] Аналитик независимо принимает результат run 44020916667.
- [ ] После закрытия relationship/diagnostics issues выполнены заключительные негативные интеграционные проверки.

**Решение координатора:** E3-02 больше не BLOCKED отсутствием real workflow. Статус WAITING_FOR_ANALYST для проверки уже успешного прогона; финальная приёмка зависит от закрытия оставшихся C1 integrity checks.

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
