# SFRA — рабочий реестр задач и двухэтапная проверка

> **Реестр ведут аналитики.** Они самостоятельно проверяют отчёты исполнителей, ставят отметки, обновляют HEAD и статусы и продолжают утверждённый спектр задач.
>
> **Координатора вызывают только по сигналу аналитика:** весь его спектр задач завершён либо возникло ограничение, требующее архитектурного решения или нового указания. Координатор не обновляет файл после каждого промежуточного отчёта.
>
> Последняя координаторская пакетная сверка: **2026-11-17**, PR #11 HEAD a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef, PR #10 HEAD 31069151326e726255c5a053d8908034c32b9665, current main 61476e7e387e77980ee55e393d636122311e78ba.

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
| SFRA-E1-01 | E1 | Единый атомарный Source Scope API + current-node resolver | **COORDINATOR_ACCEPTED_NOT_MERGED** | Аудит координатора завершён по implementation tree 433a474147b9353afdd4dee4af205a79dc21253d. Аналитик выставил ANALYST_SCOPE_COMPLETE. PR #11 HEAD a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef, open / non-draft, ahead 12 / behind 0. CI 44026684195: 88 passed, unit-tests skipped; structural CI 44026684168: 88 passed. Слияние не выполнялось. |
| SFRA-E3-01 | E3 | C1: SourceReader, SearchAdapter, dependency resolver, E1 adapter и Snapshot binding | **WAITING_FOR_ANALYST** | PR #10 HEAD 31069151326e726255c5a053d8908034c32b9665, open / Draft, ahead 27 / behind 0. После sync C1 CI 44028691360: 45 B1 + 56 C1 passed. Кодовые gates и описание PR актуальны; требуется независимая аналитическая приёмка этого synced HEAD. |
| SFRA-E3-02 | E3 | Реальная интеграция E2 → E3 → E1 → Context Pack | **WAITING_FOR_IMPLEMENTATION** | Real workflow после sync [44028691353](https://github.com/yeatu/obsidianGP/actions/runs/44028691353) завершился success на E1 HEAD a9ba344 и E3 HEAD 3106915. Все 4 scope, resolver и реальная parent dependency ok; wrong hash stale_source, unknown ID not_found; budget_exceeded без partial fragments; read-only guards passed. Context Pack budget_limited (1 included, 2 deferred). Полная negative matrix ambiguous/deleted/corrupt source/snapshot-document-generation mismatch ещё не закрыта. |
| SFRA-E2-01 | E2 | Active-only фильтрация и интеграционная проверка | **COORDINATOR_ACCEPTED_NOT_MERGED** | Повторная реализация не требуется; PR #7 открыт и не объединён. |

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

### PR #10 — E3 C1

- [PR #10 — E3 C1: E2 SearchAdapter and snapshot binding](https://github.com/yeatu/obsidianGP/pull/10)
- Текущий PR HEAD: 31069151326e726255c5a053d8908034c32b9665; commit синхронизации изменил только PROJECT_TASKS.md. Последний code implementation tree: 7fb528981b00053c5e7f498366334f7f68139e7.
- Состояние: open, Draft, not merged; ahead 27 / behind 0 относительно main 61476e7....
- PR description обновлено и отражает текущую синхронизацию и gates.

**C1 CI после синхронизации**
- [Run 44028691360](https://github.com/yeatu/obsidianGP/actions/runs/44028691360): success; 45 B1 + 56 C1 passed.

**Подтверждённые code gates**
1. Проверка exact parent identity, общего parent у siblings, source order previous → target → next и уникальности Node IDs.
2. Четыре adversarial tests: wrong parent, foreign-parent sibling, reversed neighbors, duplicate IDs.
3. Resolver diagnostics очищаются на границе каждого pipeline run; regression на последовательные запросы.
4. B1 policy defaults отделены от source annotations.
5. README, E1 consumer contract, handoff и PR description описывают native E1 API и E3 token-budget ownership.
6. Snapshot binder сверяет Git HEAD, sfra-state, manifest raw SHA, SQLite digest и clean checkout.

**Real integration**
- [Run 44028691353](https://github.com/yeatu/obsidianGP/actions/runs/44028691353): success на E1 HEAD a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef и E3 HEAD 31069151326e726255c5a053d8908034c32b9665.
- Artifact ID 14303694552; SHA-256 sha256:257de5ee5383f77286c6f6a6aacb5da0a52094caa7c165dc2f8afdce64dec496.
- Resolver и реальная parent dependency: ok; все четыре scope вернули ok на одном pinned snapshot.
- Wrong hash → stale_source; unknown ID → not_found; scope budget → budget_exceeded с пустыми fragments.
- Context Pack: budget_limited, 1 included / 2 deferred. Это не complete.
- SQLite, manifest, sidecar tree, Vault tree и HEADs не изменились; clean checkout assertions passed.

**Оставшиеся gates**
- C1 code/fixture gates закрыты; synced C1 CI повторно успешен.
- Требуется независимая аналитическая приёмка C1 на текущем synced HEAD; PR остаётся Draft.
- E3-02 real negative matrix всё ещё неполная: ambiguous, deleted, corrupt source и snapshot/document/generation mismatch пока не покрыты как реальные E3 API scenarios. Fixture/E1 tests не заменяют эту проверку.
- Real run 44028691353 проверен и завершился успешно; оставшийся E3-02 gate — полная negative matrix.

#### Чек-лист аналитика E3 / C1
- [x] Relationship identity/order и unique IDs.
- [x] Четыре adversarial tests.
- [x] Diagnostics lifecycle regression.
- [x] Policy defaults отделены от source annotations.
- [x] README, contract, handoff и PR description обновлены.
- [x] C1 CI после sync: 45 B1 + 56 C1 passed.
- [ ] Аналитик независимо принимает C1 на synced HEAD 3106915.
- [x] Real integration run 44028691353 завершён и проверен.
- [ ] Real negative matrix E3-02 закрыта.
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

### E1 / PR #11 — HEAD a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef
- [x] Проверен PR: open, non-draft, not merged.
- [x] Implementation tree 433a474 принят в пределах Source Scope API v1.
- [x] Проверены четыре scope, atomic SQLite read transaction, exact text/provenance, fail-closed и current-node resolver.
- [x] Аналитик завершил спектр (ANALYST_SCOPE_COMPLETE).
- [x] Ветка синхронизирована: ahead 12 / behind 0 относительно main.
- [x] E1 API CI 44026684195: 88 passed; unit-tests skipped.
- [x] Structural CI 44026684168: 88 passed.
- [x] Координаторская приёмка выполнена.
- [ ] PR #11 merged.

**Решение:** COORDINATOR_ACCEPTED_NOT_MERGED. Не возвращать E1 к реализации; merge не выполнялся.

### E3 / PR #10 — HEAD 31069151326e726255c5a053d8908034c32b9665
- [x] Проверен PR: open, Draft, not merged.
- [x] Ветка синхронизирована с main: ahead 27 / behind 0.
- [x] C1 CI 44028691360: 45 B1 + 56 C1 passed.
- [x] Relationship identity/order, duplicate IDs и четыре adversarial tests подтверждены на code tree.
- [x] Diagnostics очищаются между pipeline runs; regression подтверждён.
- [x] Policy defaults отделены от source annotations.
- [x] README, consumer contract, handoff и PR description обновлены.
- [ ] Аналитик независимо принимает C1 на synced HEAD.
- [x] Real integration run 44028691353 завершён и проверен.
- [ ] E3-02 real negative matrix закрыта.

**Решение:** C1 готова к независимой аналитической приёмке; не объявлять coordinator acceptance до её результата. E3-02 остаётся в реализации до закрытия реальной негативной матрицы. PR #10 остаётся Draft.

### E2 / PR #7
- [x] Предыдущая координаторская приёмка сохранена на проверенном HEAD `af4469d3badf0aa902568ae1926f5b5309a70655`.
- [x] PR #7 остаётся open / not merged; актуальный PR HEAD не изменился.
- [x] Проверен финальный CI [44010638395](https://github.com/yeatu/obsidianGP/actions/runs/44010638395): success, 64 passed, 0 failures/errors/skipped.
- [x] Сверено положение ветки относительно текущего main `61476e7`: compare diverged, PR branch ahead 20 / behind 23. Новых E2 implementation commits и более свежих CI runs не обнаружено.
- [x] Повторная реализация E2 не требуется; ранее вынесенная coordinator acceptance сохраняется для проверенного HEAD.
- [ ] Если будет принято решение о merge PR #7, отдельно обновить branch/base comparison и повторить релевантный CI на финальном HEAD.

**Решение по текущей сверке:** статус остаётся `COORDINATOR_ACCEPTED_NOT_MERGED`. Ветку E2 не синхронизировала и merge не выполняла: это не требуется для обновления статуса уже принятой работы. При возможном merge нельзя считать старую проверку автоматически распространяющейся на новый HEAD.
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
