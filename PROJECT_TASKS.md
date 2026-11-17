# SFRA — рабочий реестр задач и двухэтапная проверка

> **Реестр ведут аналитики.** Они самостоятельно проверяют отчёты исполнителей, ставят отметки, обновляют HEAD и статусы и продолжают утверждённый спектр задач.
>
> **Координатора вызывают только по сигналу аналитика:** весь его спектр задач завершён либо возникло ограничение, требующее архитектурного решения или нового указания. Координатор не обновляет файл после каждого промежуточного отчёта.
>
> Последняя координаторская пакетная сверка: **2026-11-17**, PR #11 HEAD `a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef`, PR #10 HEAD `98b29b0069f6d7df69d932646e8a57b908462d31`, main на момент сверки `cb6f83a58a82892bed968d06be02185751329c68`.

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
| SFRA-E1-01 | E1 | Единый атомарный Source Scope API + current-node resolver | **COORDINATOR_ACCEPTED_NOT_MERGED** | Координаторская приёмка сохранена по implementation tree `433a474147b9353afdd4dee4af205a79dc21253d`; аналитик завершил спектр. PR #11 HEAD `a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef`, open / non-draft. На момент сверки branch ahead 12 / behind 3 относительно main `cb6f83a58a82892bed968d06be02185751329c68`; входящие 3 коммита касались только координационного реестра. CI [44026684195](https://github.com/yeatu/obsidianGP/actions/runs/44026684195): E1 job 88 passed, `unit-tests` skipped; structural CI [44026684168](https://github.com/yeatu/obsidianGP/actions/runs/44026684168): 88 passed. Перед merge синхронизировать registry drift; код E1 не возвращать на реализацию. |
| SFRA-E3-01 | E3 | C1: SourceReader, SearchAdapter, dependency resolver, E1 adapter и Snapshot binding | **WAITING_FOR_ANALYST** | Текущий PR #10 HEAD `98b29b0069f6d7df69d932646e8a57b908462d31`, open / Draft. На момент сверки ahead 28 / behind 3 относительно main `cb6f83a58a82892bed968d06be02185751329c68`; входящие main-коммиты затрагивали только реестр. C1 CI [44029568509](https://github.com/yeatu/obsidianGP/actions/runs/44029568509): success, 45 B1 + 56 C1 passed. Прежние relationship/diagnostics code gates подтверждены; текущий HEAD требует повторной аналитической проверки после исправления integration harness и sync. |
| SFRA-E3-02 | E3 | Реальная интеграция E2 → E3 → E1 → Context Pack и negative matrix | **WAITING_FOR_IMPLEMENTATION** | Предыдущий real smoke [44028691353](https://github.com/yeatu/obsidianGP/actions/runs/44028691353) успешен на E3 HEAD `3106915`; Context Pack `budget_limited` (1 included / 2 deferred), не `complete`. Новый negative-matrix run [44029568490](https://github.com/yeatu/obsidianGP/actions/runs/44029568490) завершился failure на disposable lifecycle fixture: E2 не нашёл абзац `Middle paragraph marker`, потому что `note.write_text()` записывает буквальные `\\n` (двойное экранирование), а не переводы строк. Ambiguous/deleted матрица не была завершена; integration report artifact не создан. Требуется исправить fixture, повторить real workflow, синхронизировать branch с main и пройти аналитическую проверку. |
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

### PR #10 — E3 C1 и negative-matrix runner

- [PR #10 — E3 C1: E2 SearchAdapter and snapshot binding](https://github.com/yeatu/obsidianGP/pull/10)
- Текущий PR HEAD: `98b29b0069f6d7df69d932646e8a57b908462d31`; состояние: open / Draft / not merged.
- Main на момент сверки: `cb6f83a58a82892bed968d06be02185751329c68`. Compare: ahead 28 / behind 3. Три входящих main-коммита касались только `PROJECT_TASKS.md` и координационного реестра; реализационные файлы E3 ими не затронуты.
- Новый commit `98b29b0` расширил `tests/run_real_e1_integration.py`: disposable ambiguous/deleted lifecycle cases, corrupt source copy, snapshot echo/request mismatch, document hash и generation mismatch.

**C1 CI на HEAD 98b29b0**
- [Run 44029568509](https://github.com/yeatu/obsidianGP/actions/runs/44029568509): success; B1 **45 passed**, C1 **56 passed**.
- Это подтверждает C1 contract/fixture tests, но не успешность нового real negative-matrix workflow.

**Ранее подтверждённые C1 code gates**
1. Exact parent identity, общий parent у siblings, source order previous → target → next и уникальность Node IDs.
2. Четыре adversarial tests: wrong parent, foreign-parent sibling, reversed neighbors, duplicate IDs.
3. Resolver diagnostics сбрасываются на границе каждого pipeline run; последовательный-run regression проходит.
4. B1 policy defaults отделены от source annotations.
5. README и E1 consumer contract описывают native E1 API и ownership token budget за E3.
6. Snapshot binder сверяет Git HEAD, sfra-state, manifest raw SHA, SQLite digest и clean checkout.

**Последний real integration workflow**
- [Run 44029568490](https://github.com/yeatu/obsidianGP/actions/runs/44029568490): **failure** на disposable lifecycle test.
- Checkout E1 API, production `sfra-state`, manifest-pinned Vault и установка E1/E2/E3 packages прошли.
- Падение в `tests/run_real_e1_integration.py:471` → `_run_disposable_e1_lifecycle_cases()` → `_search_fixture_node()`, строка 125:
  `RuntimeError: E2 did not return the expected disposable fixture node: 'Middle paragraph marker'`.
- Причина подтверждена исходником на HEAD `98b29b0`: временные заметки создаются строками с двойным экранированием `\\n`, поэтому записываются буквальные символы backslash+n вместо реальных переводов строк. E2 не получает ожидаемый Markdown paragraph.
- Ошибка происходит в disposable temporary Vault/state, а не в production source. Но runner завершился до отчёта и финального набора read-only assertions; machine-readable artifact не создан.
- Следовательно, ambiguous/deleted lifecycle cases и расширенная negative matrix пока **не приняты**.

**Исторический успешный smoke**
- [Run 44028691353](https://github.com/yeatu/obsidianGP/actions/runs/44028691353) успешно прошёл на предыдущем E3 HEAD `3106915` и E1 HEAD `a9ba344`: четыре scope, реальная parent dependency, wrong hash → `stale_source`, unknown ID → `not_found`, budget exceeded без partial fragments, read-only guards.
- Context Pack был `budget_limited`, 1 included / 2 deferred. Это не `complete` и не доказательство прохождения новой negative matrix.

**Оставшиеся действия**
1. Исправить fixture strings в `run_real_e1_integration.py`: в Python source должны быть escape-последовательности `\n` с одним backslash, чтобы файл содержал реальные переводы строк; сейчас записываются буквальные `\\n`.
2. Повторить real integration workflow и получить machine-readable report. Проверить ambiguous, deleted, corrupt source, snapshot echo/request mismatch, document hash и generation mismatch, а также финальные read-only assertions.
3. Синхронизировать E3 branch с актуальным main после coordinator registry update; повторить C1 CI и real integration на финальном HEAD.
4. Передать новый синхронизированный HEAD аналитику для независимой проверки. До неё PR #10 остаётся Draft.

#### Чек-лист аналитика E3 / C1

- [x] Relationship identity/order и unique IDs на ранее проверенном implementation tree.
- [x] Четыре adversarial relationship tests.
- [x] Diagnostics lifecycle regression.
- [x] Policy defaults отделены от source annotations.
- [x] C1 CI на HEAD 98b29b0: 45 B1 + 56 C1 passed.
- [ ] Исправлен temporary Markdown fixture в real integration runner.
- [ ] Реальный negative-matrix workflow завершился success и создал machine-readable report.
- [ ] После sync с актуальным main повторены CI и real integration на финальном HEAD.
- [ ] Аналитик независимо принимает C1 на финальном HEAD.
- [ ] E3-02 real negative matrix закрыта.

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

**Решение:** `COORDINATOR_ACCEPTED_NOT_MERGED`. Не возвращать E1 к реализации. На момент сверки PR отставал от main на 3 коммита, содержащих только координационный реестр и `PROJECT_TASKS.md`; перед merge синхронизировать ветку и повторно подтвердить PR state. Код E1 этими коммитами не затронут.

### E3 / PR #10 — HEAD `98b29b0069f6d7df69d932646e8a57b908462d31`

- [x] Проверен PR: open, Draft, not merged.
- [x] C1 CI [44029568509](https://github.com/yeatu/obsidianGP/actions/runs/44029568509): 45 B1 + 56 C1 passed.
- [x] Проверены существующие relationship identity/order checks, duplicate IDs и четыре adversarial tests на ранее проверенном implementation tree.
- [x] Diagnostics очищаются между pipeline runs; regression подтверждён.
- [x] Policy defaults отделены от source annotations.
- [x] Изучен diff нового negative-matrix runner.
- [x] Установлена конкретная причина падения real workflow: двойное экранирование `\\n` в disposable Markdown fixture; E2 не находит paragraph.
- [ ] Исправлен fixture.
- [ ] Real negative-matrix workflow успешен и содержит machine-readable artifact.
- [ ] E3 branch синхронизирована с актуальным main; C1 CI и real workflow повторены.
- [ ] Аналитик независимо принимает C1 на финальном HEAD.
- [ ] E3-02 real negative matrix закрыта.

**Решение:** C1 code/test gates подтверждены по 45/56, но новый HEAD требует аналитической перепроверки после исправления runner. Real negative matrix не принята: run 44029568490 завершился failure в disposable test fixture до создания отчёта. PR #10 остаётся Draft; merge не выполнять.

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
