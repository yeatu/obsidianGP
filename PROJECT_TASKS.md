# SFRA — рабочий реестр задач и двухэтапная проверка

> **Реестр ведут аналитики.** Они самостоятельно проверяют отчёты исполнителей, ставят отметки, обновляют HEAD и статусы и продолжают утверждённый спектр задач.
>
> **Координатора вызывают только по сигналу аналитика:** весь его спектр задач завершён либо возникло ограничение, требующее архитектурного решения или нового указания. Координатор не обновляет файл после каждого промежуточного отчёта.
>
> Последняя независимая аналитическая проверка E3: **2026-11-17**, PR #10 HEAD `a10023930c4dbf75adcf9ce4bb200af2cd3fe3fe`; PR #11 E1 API HEAD `a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef`; main на момент проверки `83b86216fd70f3f4335bedbd216ce14e24ae2abd`.

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
| SFRA-E1-01 | E1 | Единый атомарный Source Scope API + current-node resolver | **COORDINATOR_ACCEPTED_NOT_MERGED** | Приёмка координатора сохранена по implementation tree `433a474147b9353afdd4dee4af205a79dc21253d`; аналитик завершил спектр. PR #11 HEAD `a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef`, open / non-draft. На момент сверки ahead 12 / behind 4 относительно main `aaf85dd3854bfbd200ad79b8883829847dff8f18`; входящие коммиты изменяли только реестры. CI [44026684195](https://github.com/yeatu/obsidianGP/actions/runs/44026684195): E1 job 88 passed, `unit-tests` skipped; [44026684168](https://github.com/yeatu/obsidianGP/actions/runs/44026684168): structural 88 passed. Перед merge синхронизировать registry drift; код E1 не возвращать на реализацию. |
| SFRA-E3-01 | E3 | C1: SourceReader, SearchAdapter, dependency resolver, E1 adapter и Snapshot binding | **WAITING_FOR_IMPLEMENTATION** | Кодовые критерии C1 повторно прошли на HEAD `a100239`: C1 CI [44032755769](https://github.com/yeatu/obsidianGP/actions/runs/44032755769), 45 B1 + 56 C1 passed. Реальный E1/E2/E3 workflow [44032755754](https://github.com/yeatu/obsidianGP/actions/runs/44032755754) также успешен. Ветка синхронизирована с main `83b8621` (ahead 36 / behind 0 на момент проверки). README и handoff обновлены. Остался устаревший PR description: он всё ещё ссылается на HEAD `6e7b4f` и run `44030503204`; требуется обновить текст PR под `a100239` и свежие доказательства. | 
| SFRA-E3-02 | E3 | Реальная интеграция E2 → E3 → E1 → Context Pack и negative matrix | **ANALYST_COMPLETE_UNREVIEWED** | Real run [44032755754](https://github.com/yeatu/obsidianGP/actions/runs/44032755754) успешен на E3 HEAD `a100239` и E1 API HEAD `a9ba344`; artifact `14306375346`. Подтверждены 4 scope, current-node resolver и реальная parent dependency; negative matrix: stale hash, not_found, corrupt source copy, ambiguous/deleted lifecycle на disposable E1 indexes, snapshot echo/request mismatch, document hash и generation mismatch. Ошибки fail-closed, read-only guards прошли. Context Pack `budget_limited` (1 included / 2 deferred), scope budget `budget_exceeded`; pack не `complete`. |
| SFRA-E2-01 | E2 | Active-only фильтрация и интеграционная проверка | **COORDINATOR_ACCEPTED_NOT_MERGED** | Приёмка сохраняется на проверенном HEAD `af4469d3badf0aa902568ae1926f5b5309a70655`; PR #7 открыт и не объединён. Повторная реализация E2 не требуется. |

---

## 3. Последняя пакетная сверка PR #10 и PR #11

Сверка выполнена 2026-11-17 по текущим PR HEAD и main 61476e7.... Старые HEAD в предыдущих записях — история.

### PR #11 — E1

- [PR #11 — E1 atomic Source Scope API and current-node resolver](https://github.com/yeatu/obsidianGP/pull/11)
- Текущий PR HEAD: a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef; implementation tree 433a474147b9353afdd4dee4af205a79dc21253d.
- Состояние: open, non-draft, not merged; ahead 12 / behind 0 относительно main.
- [Run 44026684195 — E1 source API](https://github.com/yeatu/obsidianGP/actions/runs/44026684195): e1-source-api-tests success, 88 passed; unit-tests job skipped.
- [Run 44026684168 — structural indexer](https://github.com/yeatu/obsidianGP/actions/runs/44026684168): success, 88 passed; real Vault: 66 документов, 9 080 узлов, 21 Passage, 2 пустых документа; повторный run пропустил 66 неизменённых документов, stale/ambiguous nodes — 0.

Координатор проверил единый API read_source_scope и resolve_current_node, четыре scope, одну SQLite read transaction, проверку provenance/hash/coordinates, fail-closed поведение, оригинальный Markdown без truncation и отсутствие fuzzy/historical fallback. Production SQLite не использовалась как writable target.

**Решение координатора:** SFRA-E1-01 принимается в рамках согласованного контракта: **COORDINATOR_ACCEPTED_NOT_MERGED**. Аналитик завершил спектр (ANALYST_SCOPE_COMPLETE, [comment 6939402215](https://github.com/yeatu/obsidianGP/pull/11#issuecomment-6939402215)). PR синхронизирован с main, свежие целевые CI успешны. Отдельный unit-tests job пропущен и не считается success. PR открыт, merge не выполнялся.

### PR #10 — E3 C1 и real negative matrix

- [PR #10 — E3 C1: E2 SearchAdapter and snapshot binding](https://github.com/yeatu/obsidianGP/pull/10)
- Проверенный PR HEAD аналитика: `a10023930c4dbf75adcf9ce4bb200af2cd3fe3fe`; состояние: open / Draft / not merged.
- Base/main: `83b86216fd70f3f4335bedbd216ce14e24ae2abd`; ветка синхронизирована, compare **ahead 36 / behind 0** на момент проверки.
- [C1 CI 44032755769](https://github.com/yeatu/obsidianGP/actions/runs/44032755769): success, **45 B1 + 56 C1 passed**.
- [Real integration 44032755754](https://github.com/yeatu/obsidianGP/actions/runs/44032755754): success; event `pull_request`; artifact ID `14306375346`, SHA-256 `sha256:d6175f30641bb7221232817df3e5cd09c10e92e81f7a99079ab28090ba519fa5`.

#### Проверенные изменения и C1 критерии

- E1 `SourceScopeResult` / `CurrentNodeAddress` dataclass adapter через `to_dict()`.
- SourceReader: exact parent identity, common parent у siblings, previous → target → next source order, cross-role unique Node IDs, source/document hashes, generation, UTF-8 text и coordinates.
- Четыре adversarial tests relationship integrity проходят.
- Resolver diagnostics сбрасываются на каждый `pipeline.run()`; sequential-run regression проходит.
- B1 policy defaults `normal / () / False` отделены от source annotations.
- Snapshot binder проверяет actual Git HEADs, `sfra-state`, manifest raw SHA, SQLite digest и clean checkouts.
- README и handoff обновлены, в том числе отдельная секция после sync с main. PR description при этом всё ещё устарел (см. остаточные действия).

#### C1 CI на HEAD a100239

Run 44032755769: B1 **45 passed**, C1 **56 passed**; job `adapter-contract-tests` success.

#### Real E1/E2/E3 и negative matrix

Run 44032755754 завершился success на E3 HEAD `a10023930c4dbf75adcf9ce4bb200af2cd3fe3fe` и E1 API HEAD `a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef`.

Snapshot:
- Vault commit: `2a3c54fa7a9e910f4c9621c8fe00f41a061fc158`;
- sidecar commit: `fb0b45ae0e5043e342c790d43e2b341ca65d7f2b`;
- manifest SHA-256: `sha256:3d5eacf5fc2f7f927af8f591f317ea95d56d0c0f53de1bc61cb54d23677fd072`;
- SQLite SHA-256: `sha256:2a6d792d5e5c458ffa87df32a082229fc548c42dab2d91a5cc8fa1195bcf6674`.

Результаты:
- E2: 3 hits / 3 source-verifiable candidates; current-node resolver `ok`.
- DependencyResolver разрешил фактическую `parent_context` dependency `node_9b0e90f9-ac0c-44c3-84ce-92f035e0a32c`, address/hash/path/document generation сверены.
- Все четыре scope `node / parent / neighbors / document` вернули `ok` на одном SnapshotRef; полный document scope: 110 809 UTF-8 bytes, без truncation.
- Wrong hash → `stale_source`; unknown ID → `not_found`.
- Corrupt source copy → `stale_source`, fragments пуст.
- Ambiguous neighbor → `ambiguous`, fragments пуст; deleted node → `deleted`, fragments пуст. Эти два lifecycle случая созданы через публичный E1 `index_vault()` на отдельных disposable Vault/SQLite, не являются состояниями production sidecar.
- Fault-injected E1 snapshot echo → `snapshot_mismatch`; неправильный request SnapshotRef → `snapshot_mismatch`; document hash → `document_hash_mismatch`; generation → `snapshot_generation_mismatch`. Эти сценарии проверяют fail-closed поведение E3 boundary через fault-injection adapter.
- Scope budget 1 token → `budget_exceeded`, fragments пуст.
- Context Pack → `budget_limited`, 1 Included / 2 Deferred при request budget 6000. Это ожидаемый ограниченный pack, не `complete`.
- Read-only guards: production SQLite, manifest, sidecar tree, Vault tree и HEADs не изменились; sidecar и Vault checkouts чистые.

Artifact: [sfra-e3-real-integration-44032755754](https://github.com/yeatu/obsidianGP/actions/runs/44032755754), ID `14306375346`.

#### Остаточный пункт перед формальной приёмкой

PR description всё ещё содержит устаревший HEAD `6e7b4f`, compare ahead 30 / behind 4 и run `44030503204`. Это противоречит текущему PR HEAD, sync и последним проверкам. Исполнителю нужно обновить только body PR под `a100239`, `44032755769` и `44032755754`.

#### Чек-лист аналитика E3 / C1

- [x] Проверен текущий HEAD `a10023930c4dbf75adcf9ce4bb200af2cd3fe3fe`.
- [x] C1 CI: 45 B1 + 56 C1 passed, run 44032755769.
- [x] Native E1 dataclass adapter и все четыре source scopes проверены.
- [x] Parent/sibling identity/order, уникальность Node IDs и четыре adversarial tests подтверждены.
- [x] Resolver diagnostics isolated per pipeline run.
- [x] Policy defaults отделены от source annotations.
- [x] Snapshot binding, source hashes, budget ownership и E3 fail-closed behaviour подтверждены.
- [x] Real integration и expanded negative matrix прошли, run 44032755754.
- [x] Ambiguous/deleted semantics проверены через реальные E1 public lifecycle calls на disposable indexes; production sidecar не изменялся.
- [x] Ветка синхронизирована с `main`; CI и real integration повторены на синхронизированном HEAD.
- [ ] PR description обновлён под актуальный HEAD и свежие evidence.

**Решение аналитика:** кодовые, C1 и real E3-02 negative-matrix gates подтверждены на `a100239`. Формальную отметку `ANALYST_COMPLETE_UNREVIEWED` для C1 пока не ставлю только из-за устаревшего PR description. Реализацию не возвращаю на доработку; требуется документальная актуализация body PR. PR остаётся Draft, coordinator acceptance и merge не выполнялись.

Проверенный HEAD: `a10023930c4dbf75adcf9ce4bb200af2cd3fe3fe`  
Дата проверки: `2026-11-17`  
C1 CI: [44032755769](https://github.com/yeatu/obsidianGP/actions/runs/44032755769)  
Real integration: [44032755754](https://github.com/yeatu/obsidianGP/actions/runs/44032755754)  
Artifact ID: `14306375346`
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

## 5. Личный чек-лист координатора — пакетная сверка 2026-11-17

### E1 / PR #11 — HEAD `a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef`

- [x] Проверен PR: open, non-draft, not merged.
- [x] Implementation tree `433a474147b9353afdd4dee4af205a79dc21253d` принят в пределах Source Scope API v1.
- [x] Проверены четыре scope, atomic SQLite read transaction, exact text/provenance, fail-closed и current-node resolver.
- [x] Аналитик завершил спектр (`ANALYST_SCOPE_COMPLETE`).
- [x] E1 API CI [44026684195](https://github.com/yeatu/obsidianGP/actions/runs/44026684195): целевой job 88 passed; отдельный `unit-tests` skipped.
- [x] Structural CI [44026684168](https://github.com/yeatu/obsidianGP/actions/runs/44026684168): 88 passed.
- [x] Координаторская приёмка выполнена.
- [ ] PR #11 merged.
- [ ] E1 branch синхронизирована с main после registry-only изменений.

**Решение:** `COORDINATOR_ACCEPTED_NOT_MERGED`. E1 к реализации не возвращать. На момент сверки PR отставал от main на 4 коммита; incoming changes касались только координационных файлов. Перед merge синхронизировать ветку и повторно подтвердить PR state.

### E3 / PR #10 — HEAD `6e7b4fde4ed1d9eb73cb26f200975199842506f2`

- [x] Проверен PR: open, Draft, not merged.
- [x] C1 CI [44030503164](https://github.com/yeatu/obsidianGP/actions/runs/44030503164): 45 B1 + 56 C1 passed.
- [x] Relationship identity/order, duplicate IDs, четыре adversarial tests и diagnostics lifecycle regression подтверждены на ранее проверенном implementation tree.
- [x] Исправленный real integration runner прошёл все добавленные negative scenarios.
- [x] Проверен machine-readable artifact 14305690505 и статусы ambiguous/deleted/corrupt/hash/snapshot/generation.
- [x] Проверены четыре scope, real parent dependency, budget handling и production read-only guards.
- [ ] Аналитик независимо принимает C1 и E3-02 на HEAD 6e7b4fd.
- [ ] E3 branch синхронизирована с актуальным main; после sync повторены CI и real integration.
- [ ] Coordinator acceptance C1 / E3-02.
- [ ] PR #10 merged.

**Решение:** Real negative matrix теперь подтверждена успешным run 44030503204; предыдущий failed run 44029568490 superseded исправленным HEAD. Реализация выглядит готовой к независимой аналитической приёмке, но PR остаётся Draft, coordinator acceptance не выставлена, merge не выполнялся.

### E2 / PR #7

- [x] Приёмка сохранена на проверенном HEAD `af4469d3badf0aa902568ae1926f5b5309a70655`.
- [x] PR #7 открыт и не объединён.
- [x] Последний известный CI [44010638395](https://github.com/yeatu/obsidianGP/actions/runs/44010638395): success, 64 passed, 0 failures/errors/skipped.
- [x] Новых E2 implementation commits или нового задания в текущей сверке не выявлено.
- [ ] При решении о merge проверить текущую ветку и повторить релевантные проверки на финальном HEAD.

**Решение:** `COORDINATOR_ACCEPTED_NOT_MERGED`. Повторная реализация E2 не требуется; merge не выполнялся.

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
