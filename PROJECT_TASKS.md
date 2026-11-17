# SFRA — рабочий реестр задач и двухэтапная проверка

> **Реестр ведут аналитики.** Они самостоятельно проверяют отчёты исполнителей, ставят отметки, обновляют HEAD и статусы и продолжают утверждённый спектр задач.
>
> **Координатора вызывают только по сигналу аналитика:** весь его спектр задач завершён либо возникло ограничение, требующее архитектурного решения или нового указания. Координатор не обновляет файл после каждого промежуточного отчёта.
>
> Последняя координаторская проверка E3: **2026-11-17**, PR #10 HEAD `a10023930c4dbf75adcf9ce4bb200af2cd3fe3fe`; E1 API HEAD `a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef`; main на момент проверки `84f51e36dfaa029ea059d00fbf29efc066b9c298`.

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
| SFRA-E3-01 | E3 | C1: SourceReader, SearchAdapter, dependency resolver, E1 adapter и Snapshot binding | **COORDINATOR_ACCEPTED_NOT_MERGED** | Координаторская приёмка по PR #10 HEAD `a10023930c4dbf75adcf9ce4bb200af2cd3fe3fe`. Аналитик завершил C1: PR CI [44032755769](https://github.com/yeatu/obsidianGP/actions/runs/44032755769) и push CI [44032747813](https://github.com/yeatu/obsidianGP/actions/runs/44032747813), по 45 B1 + 56 C1 passed. SourceReader, relationship integrity, resolver diagnostics lifecycle, native E1 adapter, snapshot binding и E3-owned budget проверены. PR #10 open / Draft / not merged. Относительно текущего main `84f51e36dfaa029ea059d00fbf29efc066b9c298`: ahead 36 / behind 2; оба входящих коммита меняют только `PROJECT_TASKS.md`, implementation tree не затронут. Перед merge синхронизировать registry drift и повторить проверки на финальном HEAD. |
| SFRA-E3-02 | E3 | Реальная интеграция E2 → E3 → E1 → Context Pack и negative matrix | **COORDINATOR_ACCEPTED_NOT_MERGED** | Координаторская приёмка по real PR run [44032755754](https://github.com/yeatu/obsidianGP/actions/runs/44032755754) и push run [44032747843](https://github.com/yeatu/obsidianGP/actions/runs/44032747843) на E3 HEAD `a100239`, E1 HEAD `a9ba344`. Artifacts `14306375346` и `14304974673`. Подтверждены 4 scope, current-node resolver, реальная parent dependency, stale/not_found/corrupt/ambiguous/deleted/snapshot/document/generation negative matrix, fail-closed и read-only guards. Ambiguous/deleted воспроизведены на disposable E1 indexes, mismatch cases — fault injection на E3 boundary; это не выдаётся за состояние production sidecar. Context Pack `budget_limited` (1 included / 2 deferred), scope budget `budget_exceeded`; pack не `complete`. PR открыт, Draft, не объединён. |
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
- Проверенный PR HEAD аналитика и координатора: `a10023930c4dbf75adcf9ce4bb200af2cd3fe3fe`.
- PR #10: open / Draft / not merged.
- Main: `84f51e36dfaa029ea059d00fbf29efc066b9c298`. Compare: ahead 36 / behind 2. Два входящих main-коммита содержат только изменения `PROJECT_TASKS.md`; реализационные файлы E3 не изменились.
- PR description соответствует проверенному HEAD и его CI / real integration evidence.

#### C1 CI и кодовая проверка

- [PR CI 44032755769](https://github.com/yeatu/obsidianGP/actions/runs/44032755769): success, **45 B1 + 56 C1 passed**.
- [Push CI 44032747813](https://github.com/yeatu/obsidianGP/actions/runs/44032747813): success, **45 B1 + 56 C1 passed**.
- Проверены E1 native `SourceScopeResult` / `CurrentNodeAddress` adapters через `to_dict()`.
- SourceReader проверяет exact parent identity, общий parent у siblings, source order previous → target → next, cross-role unique Node IDs, provenance, UTF-8 SHA, source/document hash, generation и coordinates.
- Четыре adversarial tests покрывают wrong parent, sibling с чужим parent, reversed neighbors и duplicate Node IDs.
- Resolver diagnostics очищаются в начале каждого `pipeline.run()`; regression на последовательных запросах проходит.
- B1 defaults `normal / () / False` применяются как policy defaults, а не source annotations.
- Snapshot binder проверяет фактические Git HEADs, чистый `sfra-state`, manifest raw SHA, SQLite digest и чистоту checkout.
- E3 владеет token budget; E1 возвращает полный source text; truncation не используется; error responses fail-closed.

#### Реальная интеграция и negative matrix

- [PR-triggered real integration 44032755754](https://github.com/yeatu/obsidianGP/actions/runs/44032755754): success; artifact `14306375346`, digest `sha256:d6175f30641bb7221232817df3e5cd09c10e92e81f7a99079ab28090ba519fa5`.
- [Push-triggered real integration 44032747843](https://github.com/yeatu/obsidianGP/actions/runs/44032747843): success; artifact `14304974673`, digest `sha256:eb99af10b8706815627dea361d1eecaf55ef3d9c231b213968c6e3cdca06c9b1`.
- Оба прогона использовали E3 `a10023930c4dbf75adcf9ce4bb200af2cd3fe3fe` и E1 `a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef`.

Подтверждены:
- E2: 3 hits / 3 source-verifiable candidates; current-node resolver `ok`.
- Реальная `parent_context` dependency разрешена через current address и exact source read; identity/hash/path/document generation совпали.
- Все четыре scope `node / parent / neighbors / document` прошли на одном SnapshotRef.
- Document scope вернул полный Markdown: 110 809 UTF-8 bytes, hash/size совпали, truncation отсутствует.
- Wrong hash → `stale_source`; unknown Node ID → `not_found`; corrupt isolated source copy → `stale_source`.
- Ambiguous neighbor → `ambiguous`, deleted node → `deleted`. Эти статусы воспроизведены через публичный E1 `index_vault()` / Source Scope API на disposable Vault/SQLite; они не заявляются как существующие в production sidecar.
- Snapshot echo/request mismatch → `snapshot_mismatch`; tampered document hash → `document_hash_mismatch`; generation mismatch → `snapshot_generation_mismatch`. Это fault-injection проверки E3 boundary.
- Все failure responses вернули пустые fragments.
- Scope budget в 1 token → `budget_exceeded`, без partial fragments.
- Context Pack: `budget_limited`, 1 Included / 2 Deferred при request budget 6000. Это ожидаемый ограниченный pack, не `complete`.
- Production SQLite, manifest, sidecar tree, Vault tree и HEADs не изменились; оба checkout остались clean.

#### Итог аналитика

Аналитик завершил C1 и E3-02 в согласованном scope: `ANALYST_COMPLETE_UNREVIEWED / ANALYST_SCOPE_COMPLETE`. Все аналитические пункты и доказательства зафиксированы в основном реестре.

#### Решение координатора

**C1 и E3-02 принимаются: `COORDINATOR_ACCEPTED_NOT_MERGED` на проверенном code HEAD `a100239`.** Архитектурных или реализационных блокеров в согласованном scope не осталось. PR #10 открыт, Draft, не объединён.

Два коммита текущего main сверх PR base меняют только `PROJECT_TASKS.md`; это registry drift, не implementation drift. Перед merge следует синхронизировать ветку и повторить C1 CI + real integration на финальном HEAD. Merge не выполнялся.

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

### E3 / PR #10 — HEAD `a10023930c4dbf75adcf9ce4bb200af2cd3fe3fe`

- [x] Проверен PR: open / Draft / not merged.
- [x] Проверен актуальный HEAD аналитика `a100239`; реализационный diff и ключевые модули SourceReader, SearchAdapter, DependencyResolver, Pipeline и Snapshot binder изучены.
- [x] C1 PR CI [44032755769](https://github.com/yeatu/obsidianGP/actions/runs/44032755769): 45 B1 + 56 C1 passed.
- [x] C1 push CI [44032747813](https://github.com/yeatu/obsidianGP/actions/runs/44032747813): 45 B1 + 56 C1 passed.
- [x] SourceReader native E1 adapter, четыре scope, parent/sibling identity/order, duplicate IDs, exact hashes/generation/coordinates подтверждены.
- [x] Четыре adversarial relationship tests проверены.
- [x] Diagnostics isolation между последовательными pipeline runs подтверждена.
- [x] B1 policy defaults отделены от E1 source annotations.
- [x] Snapshot binder подтверждён: actual Git HEAD, clean sidecar branch, manifest raw SHA, SQLite SHA, Vault/sidecar clean guards.
- [x] PR-triggered real run [44032755754](https://github.com/yeatu/obsidianGP/actions/runs/44032755754) успешен; artifact 14306375346.
- [x] Push-triggered real run [44032747843](https://github.com/yeatu/obsidianGP/actions/runs/44032747843) успешен; artifact 14304974673.
- [x] Проверены четыре scope, current-node resolver и реальная parent dependency на одном SnapshotRef.
- [x] Negative matrix подтверждена: stale hash, not_found, corrupt source, ambiguous, deleted, snapshot echo/request mismatch, document hash и generation mismatch.
- [x] Уточнены границы доказательств: ambiguous/deleted — disposable E1 lifecycle indexes; mismatch — fault injection; эти сценарии не приписываются production sidecar.
- [x] Budget и read-only guards подтверждены; Context Pack `budget_limited` (1 included / 2 deferred), не complete.
- [x] Аналитик завершил спектр: `ANALYST_SCOPE_COMPLETE`.
- [x] Координаторская приёмка C1 и E3-02 выполнена.
- [ ] Ветка синхронизирована с текущим main: сейчас ahead 36 / behind 2; оба входящих коммита — только `PROJECT_TASKS.md`.
- [ ] После registry sync повторены C1 CI и real integration на финальном PR HEAD.
- [ ] PR #10 merged.

**Решение:** `COORDINATOR_ACCEPTED_NOT_MERGED` для C1 и E3-02 на code HEAD `a100239`. Implementation/code gates приняты. Два коммита отставания затрагивают только проектный реестр, не E3 implementation. Перед merge синхронизировать registry drift и повторить проверки. PR остаётся open / Draft; merge не выполнялся.

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
