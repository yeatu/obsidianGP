# SFRA — рабочий реестр задач и двухэтапная проверка

> **Реестр ведут аналитики.** Они самостоятельно проверяют отчёты исполнителей, ставят отметки, обновляют HEAD и статусы и продолжают утверждённый спектр задач.
>
> **Координатора вызывают только по сигналу аналитика:** весь его спектр задач завершён либо возникло ограничение, требующее архитектурного решения или нового указания. Координатор не обновляет файл после каждого промежуточного отчёта.
>
> Последняя независимая пакетная проверка: **2026-11-17, E1 API `f9b0ede` и PR #10 E3 HEAD `7fb528981b00053c5e7f498366334f7f68139e7f`**. Основная ветка: `main` (`729e877c684995dc8194ff6f0556e3571c89e75f`).

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
| SFRA-E1-01 | E1 | Единый атомарный Source Scope API + current-node resolver | **ANALYST_COMPLETE_UNREVIEWED** | Проверенный финальный PR HEAD `f9b0edef6d5bdc05c73be6a10d9e66c5b10c8cf5` (implementation tree `433a474147b9353afdd4dee4af205a79dc21253d`); E1 scope завершён (`ANALYST_SCOPE_COMPLETE`). PR #11 открыт, не объединён; mergeability требует повторной проверки после новых registry-only коммитов `main`. |
| SFRA-E3-01 | E3 | C1: SourceReader, SearchAdapter, dependency metadata и E1 API adapter | **WAITING_FOR_IMPLEMENTATION** | Кодовые gates и docs закрыты на HEAD `7fb5289`; CI 45 B1 / 56 C1 и real smoke успешны. Осталось обновить PR description и синхронизировать ветку с current `main` (ahead 25 / behind 1). |
| SFRA-E3-02 | E3 | Реальная интеграция E2 → E3 → E1 → Context Pack | **WAITING_FOR_IMPLEMENTATION** | Real E1/E2/E3 run `44026131789` успешен на E3 `7fb5289` и E1 `f9b0ede`: все 4 scope, реальная parent dependency, read-only guards и report artifact подтверждены. Полная real negative matrix ещё не закрыта; Context Pack `budget_limited` (1 included, 2 deferred). |
| SFRA-E2-01 | E2 | Active-only фильтрация и интеграционная проверка | **COORDINATOR_ACCEPTED_NOT_MERGED** | Повторная реализация не требуется; PR #7 ещё открыт. |

---

## 3. Последняя пакетная сверка PR #10 и PR #11

Проверка выполнена по актуальным HEAD `a5456c4...` (E1) и `dfe8877...` (E3), с повторной проверкой последних CI и manual integration workflow. Более ранние HEAD и комментарии ниже трактуются как история, а не как действующее состояние.

### PR #11 — E1

- [PR #11 — E1 atomic Source Scope API and current-node resolver](https://github.com/yeatu/obsidianGP/pull/11)
- Финальный проверенный PR HEAD: `f9b0edef6d5bdc05c73be6a10d9e66c5b10c8cf5`.
- Implementation tree: `433a474147b9353afdd4dee4af205a79dc21253d`; финальный HEAD дополнительно содержит merge-sync с актуальным `main` и аналитическую запись.
- Состояние: open, not merged.
- После финальной синхронизации PR (`f9b0ede`) `main` получил дополнительные коммиты, затрагивающие только `PROJECT_TASKS.md`; E1 implementation files не менялись. Compare показывает, что PR-ветка отстаёт от `main`; REST PR endpoint возвращает `mergeable=true / clean`, тогда как структурированный PR-ответ сообщает `mergeable=false`. Эти mergeability-сигналы расходятся, поэтому готовность к merge не считается подтверждённой до refresh/sync и повторной проверки.
- Force-push не использовался; текущий PR HEAD остаётся `f9b0edef6d5bdc05c73be6a10d9e66c5b10c8cf5`.

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
- Проверенный HEAD аналитика: `7fb528981b00053c5e7f498366334f7f68139e7f`
- Состояние: open, **draft**; PR description всё ещё содержит исходное описание c99d902 и требует обновления.
- Сравнение с текущим `main` (`729e877c684995dc8194ff6f0556e3571c89e75f`): ahead 25 / behind 1.
- [Run 44026131751 — C1 contract tests](https://github.com/yeatu/obsidianGP/actions/runs/44026131751): success; B1 **45 passed**, C1 **56 passed**.
- [Run 44026131789 — real E1/E2/E3 integration](https://github.com/yeatu/obsidianGP/actions/runs/44026131789): success, event `pull_request`; machine report artifact ID `14302679025`.

#### Проверенные критерии C1

1. E1 public dataclass adapter принимает SourceScopeResult / CurrentNodeAddress через to_dict() и нормализует native relations в E3 envelope.
2. SourceReader проверяет exact parent identity, общий parent siblings, source order previous → target → next, уникальность Node ID между ролями, coordinates и hashes.
3. Четыре adversarial tests проходят: wrong parent, sibling from another parent, reversed source order, duplicate Node ID across roles.
4. Resolver diagnostics очищаются на каждом pipeline.run(); последовательный-run regression проходит.
5. B1 policy defaults normal / () / False отделены от source annotations и доступны как diagnostics.
6. README, E1 consumer contract и handoff обновлены под native E1 API и реальные границы доказательств.
7. Machine report runner теперь записывает E1/E3 commit SHA, проверяет JSON после записи и формирует корректный GitHub Step Summary с реальными переводами строк.

#### C1 CI на HEAD 7fb5289

Run 44026131751: B1 **45 passed**, C1 **56 passed**; job adapter-contract-tests — success.

#### Реальная E1/E2/E3 интеграция

Run 44026131789 завершился успешно на том же HEAD. Implementation refs:
- E3: `7fb528981b00053c5e7f498366334f7f68139e7f`;
- E1 API: `f9b0edef6d5bdc05c73be6a10d9e66c5b10c8cf5`;
- `sfra-state`: `fb0b45ae0e5043e342c790d43e2b341ca65d7f2b`;
- Vault commit из manifest: `2a3c54fa7a9e910f4c9621c8fe00f41a061fc158`;
- manifest SHA-256: `sha256:3d5eacf5fc2f7f927af8f591f317ea95d56d0c0f53de1bc61cb54d23677fd072`.

В отчёте подтверждены:
- E2: 3 hits / 3 source-verifiable candidates;
- current-node resolver: ok;
- DependencyResolver разрешил реальную parent_context dependency и совпадающий current address;
- node / parent / neighbors / document: все четыре scope ok на одном SnapshotRef;
- wrong hash → stale_source; unknown Node ID → not_found;
- Context Pack: budget_limited, 1 included / 2 deferred; scope budget: budget_exceeded, owner E3, без truncation;
- SQLite, manifest, sidecar tree, Vault tree и оба Git HEAD не изменились; checkout clean.

Artifact: [sfra-e3-real-integration-44026131789](https://github.com/yeatu/obsidianGP/actions/runs/44026131789), ID `14302679025`, SHA-256 `sha256:cc52a6db5a6b471da76bb6eb04030751398e4a285de2c21a2e37b4ddfcdbc644`.

Real smoke подтверждает рабочую интеграцию на pinned snapshot. Он не закрывает полную real negative matrix: ambiguous/deleted, повреждённый source и все варианты snapshot/document/generation mismatch в этом runner отдельно не прогнаны. Context Pack budget_limited не следует называть complete.

#### Остаточные действия

1. PR description всё ещё содержит первоначальные сведения c99d902, 45/43 tests и утверждение, что E1 unified API и real integration отсутствуют. Обновить body под 7fb5289, CI 45/56 и run 44026131789.
2. Синхронизировать ветку с current main (сейчас ahead 25 / behind 1) и повторить оба workflow на финальном HEAD.
3. Для полного E3-02 расширить real negative matrix: ambiguous/deleted, corrupt source, snapshot/document/generation mismatch.

#### Чек-лист аналитика E3 / C1

- [x] Проверен текущий HEAD `7fb528981b00053c5e7f498366334f7f68139e7f`.
- [x] C1 CI успешен: 45 B1 / 56 C1, run 44026131751.
- [x] Реальные E1 dataclass results проходят через adapter.
- [x] Parent identity, sibling parent IDs, source order и cross-role Node ID uniqueness проверены.
- [x] Четыре adversarial relationship tests проходят.
- [x] Resolver diagnostics изолированы между pipeline runs.
- [x] Policy defaults отличимы от source annotations и диагностируются.
- [x] Реальный smoke проверил четыре scope и parent dependency на E1 API.
- [x] Snapshot binding, source hashes, budget ownership и read-only guards подтверждены.
- [x] README, E1 consumer contract и handoff обновлены.
- [ ] PR description отражает текущую реализацию и evidence.
- [ ] Ветка синхронизирована с current main (behind 1), CI повторён после sync.
- [x] Issue worker, recovery sweep и MCP implementation не добавлены в PR #10.

**Решение аналитика:** code/test/real-smoke gates C1 подтверждены на 7fb5289. Формальная отметка complete пока не ставится из-за устаревшего PR description и одного commit рассинхронизации с main. PR остаётся Draft.

Проверенный HEAD: `7fb528981b00053c5e7f498366334f7f68139e7f`  
Дата проверки: `2026-11-17`  
C1 CI: [44026131751](https://github.com/yeatu/obsidianGP/actions/runs/44026131751)  
Real integration: [44026131789](https://github.com/yeatu/obsidianGP/actions/runs/44026131789)  
Artifact ID: `14302679025`  
Статус аналитика: **WAITING_FOR_IMPLEMENTATION**
### SFRA-E3-02 — реальная интеграция E2 → E3 → E1 → Context Pack

**Исполнитель:** E3  
**Статус:** WAITING_FOR_IMPLEMENTATION  
**Последний real integration run:** [44026131789](https://github.com/yeatu/obsidianGP/actions/runs/44026131789), success, E3 HEAD `7fb528981b00053c5e7f498366334f7f68139e7f`.

Run использовал реальные E1/E2 API и отдельные pinned checkout:
- E1 API `f9b0edef6d5bdc05c73be6a10d9e66c5b10c8cf5`;
- `sfra-state` `fb0b45ae0e5043e342c790d43e2b341ca65d7f2b`;
- Vault `2a3c54fa7a9e910f4c9621c8fe00f41a061fc158`;
- manifest SHA-256 `sha256:3d5eacf5fc2f7f927af8f591f317ea95d56d0c0f53de1bc61cb54d23677fd072`.

Подтверждены E2 retrieval, current-node resolver, реальная parent_context dependency, четыре scope на одном SnapshotRef, stale hash, unknown ID, E3-only budget/no truncation и неизменность SQLite/manifest/Vault/sidecar. Context Pack `budget_limited`, 1 included и 2 deferred; это не complete pack.

Machine-readable report: artifact ID `14302679025` на [run 44026131789](https://github.com/yeatu/obsidianGP/actions/runs/44026131789).

#### Оставшиеся требования E3-02

- [x] Реальный E1/E2/E3 smoke на pinned snapshot.
- [x] Все четыре scope и resolver работают через E1 dataclass adapter.
- [x] Parent dependency identity проверена на реальном E1 API.
- [x] Read-only guards подтвердили неизменность Vault и sidecar.
- [ ] Пройти real negative matrix: ambiguous, deleted, corrupt source, snapshot/document/generation mismatch. В runner подтверждены stale hash, unknown ID и budget failure; другие сценарии пока доказаны только отдельными E1/C1 tests.
- [ ] После sync с main повторить C1 CI и real integration на финальном HEAD.

**Итог аналитика:** real integration smoke подтверждён; весь E3-02 пока не закрыт из-за неполной real negative matrix и необходимости повторить прогоны после sync с main. Архитектурный вопрос координатору не требуется.

Проверенный HEAD: `7fb528981b00053c5e7f498366334f7f68139e7f`  
Дата проверки: `2026-11-17`  
Evidence: [run 44026131789](https://github.com/yeatu/obsidianGP/actions/runs/44026131789), artifact `14302679025`

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
