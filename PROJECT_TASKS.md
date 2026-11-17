# SFRA — рабочий реестр задач и двухэтапная проверка

> **Реестр ведут аналитики.** Они самостоятельно проверяют отчёты исполнителей, ставят отметки, обновляют HEAD и статусы и продолжают утверждённый спектр задач.
>
> **Координатора вызывают только по сигналу аналитика:** весь его спектр задач завершён либо возникло ограничение, требующее архитектурного решения или нового указания. Координатор не обновляет файл после каждого промежуточного отчёта.
>
> Последняя координаторская пакетная сверка: **2026-11-17**, PR #11 HEAD `a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef`, PR #10 HEAD `6e7b4fde4ed1d9eb73cb26f200975199842506f2`, main на момент сверки `aaf85dd3854bfbd200ad79b8883829847dff8f18`.

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
| SFRA-E3-01 | E3 | C1: SourceReader, SearchAdapter, dependency resolver, E1 adapter и Snapshot binding | **WAITING_FOR_ANALYST** | Текущий PR #10 HEAD `6e7b4fde4ed1d9eb73cb26f200975199842506f2`, open / Draft; ahead 30 / behind 4 относительно main `aaf85dd3854bfbd200ad79b8883829847dff8f18`. C1 CI [44030503164](https://github.com/yeatu/obsidianGP/actions/runs/44030503164): success, 45 B1 + 56 C1 passed. Новый real negative-matrix runner успешно завершился [44030503204](https://github.com/yeatu/obsidianGP/actions/runs/44030503204). Требуется независимая аналитическая проверка этого HEAD и sync с main; coordinator acceptance не выставлена. |
| SFRA-E3-02 | E3 | Реальная интеграция E2 → E3 → E1 → Context Pack и negative matrix | **WAITING_FOR_IMPLEMENTATION** | Новый real run [44030503204](https://github.com/yeatu/obsidianGP/actions/runs/44030503204) завершился success на E3 HEAD `6e7b4fd` и E1 HEAD `a9ba344`. Проверены ambiguous/deleted/corrupt source, snapshot echo/request mismatch, document hash и generation mismatch; все ошибки fail-closed. Четыре scope и реальная parent dependency успешны; read-only guards прошли. Context Pack `budget_limited` (1 included / 2 deferred), scope budget `budget_exceeded`. Последний аналитический статус `WAITING_FOR_IMPLEMENTATION` зафиксирован до этого run и ещё не обновлён аналитиком; требуется его независимая проверка и обновление статуса. |
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
- Текущий PR HEAD: `6e7b4fde4ed1d9eb73cb26f200975199842506f2`; состояние: open / Draft / not merged.
- Main на момент сверки: `aaf85dd3854bfbd200ad79b8883829847dff8f18`. Compare: ahead 30 / behind 4. Входящие main-коммиты на момент сравнения касались только `PROJECT_TASKS.md` и координационного реестра; код E3 ими не менялся.
- Commit `6e7b4fd` устранил падение disposable lifecycle runner: временный Markdown теперь собирается реальными строками и parser/hash функции E1 передаются в изолированные сценарии.

**C1 CI на HEAD 6e7b4fd**
- [Run 44030503164](https://github.com/yeatu/obsidianGP/actions/runs/44030503164): success; B1 **45 passed**, C1 **56 passed**.

**Real E1/E2/E3 integration и negative matrix**
- [Run 44030503204](https://github.com/yeatu/obsidianGP/actions/runs/44030503204): **success**.
- E3 HEAD: `6e7b4fde4ed1d9eb73cb26f200975199842506f2`; E1 API HEAD: `a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef`.
- Machine-readable artifact: `sfra-e3-real-integration-44030503204`, ID `14305690505`, ZIP SHA-256 `sha256:2a521dd2e4b67817993abed2759c099e32b2ab872ff43fb3d09db68f01a91d43`.

Pinned snapshot:
- Vault commit: `2a3c54fa7a9e910f4c9621c8fe00f41a061fc158`;
- sidecar commit: `fb0b45ae0e5043e342c790d43e2b341ca65d7f2b`;
- manifest SHA-256: `sha256:3d5eacf5fc2f7f927af8f591f317ea95d56d0c0f53de1bc61cb54d23677fd072`;
- SQLite SHA-256: `sha256:2a6d792d5e5c458ffa87df32a082229fc548c42dab2d91a5cc8fa1195bcf6674`.

Отчёт run 44030503204 подтвердил:
- E2: 3 hits / 3 source-verifiable candidates; current-node resolver: `ok`.
- DependencyResolver разрешил реальную `parent_context` dependency; address/hash соответствуют current source.
- node / parent / neighbors / document: четыре scope `ok` на одном SnapshotRef.
- Wrong hash → `stale_source`; unknown Node ID → `not_found`.
- Corrupt source copy → `stale_source`, fragments empty.
- Ambiguous sibling scope → `ambiguous`, fragments empty.
- Deleted node scope → `deleted`, fragments empty.
- Snapshot echo fault и request SnapshotRef mismatch → `snapshot_mismatch`.
- Document hash fault → `document_hash_mismatch`; generation fault → `snapshot_generation_mismatch`.
- Scope budget → `budget_exceeded` без partial fragments.
- Context Pack → `budget_limited`, 1 Included / 2 Deferred при request budget 6000; это не `complete`.
- SQLite, manifest, sidecar tree, Vault tree и HEADs не изменились; sidecar и Vault checkout clean.

**Статус и оставшиеся действия**
1. Тестовый дефект из run [44029568490](https://github.com/yeatu/obsidianGP/actions/runs/44029568490) исправлен на HEAD `6e7b4fd`; новый real run 44030503204 прошёл и создал artifact.
2. Синхронизировать E3 branch с актуальным main (на момент сверки behind 4) и повторить C1 CI + real integration на синхронизированном HEAD.
3. Независимый аналитик должен проверить HEAD `6e7b4fd`, CI 44030503164 и artifact 14305690505, затем обновить собственные статусы.
4. PR #10 остаётся Draft; coordinator acceptance и merge не выполнялись.

#### Чек-лист аналитика E3 / C1

- [x] Relationship identity/order, unique IDs и четыре adversarial relationship tests на implementation tree.
- [x] Resolver diagnostics lifecycle regression.
- [x] Policy defaults отделены от source annotations.
- [x] C1 CI на HEAD 6e7b4fd: 45 B1 + 56 C1 passed.
- [x] Real E1/E2/E3 integration на HEAD 6e7b4fd завершилась success.
- [x] Ambiguous / deleted / corrupt source scenarios прошли fail-closed.
- [x] Snapshot echo/request mismatch, document hash и generation mismatch отвергнуты.
- [x] Четыре scope, parent dependency, budget handling и final read-only guards подтверждены.
- [ ] Аналитик независимо принимает C1 и E3-02 на HEAD 6e7b4fd.
- [ ] E3 branch синхронизирована с актуальным main; после sync повторены CI и real integration.

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
