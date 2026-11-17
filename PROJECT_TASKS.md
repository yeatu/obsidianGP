# SFRA — рабочий реестр задач и двухэтапная проверка

> **Реестр ведут аналитики.** Они самостоятельно проверяют отчёты исполнителей, ставят отметки, обновляют HEAD и статусы и продолжают утверждённый спектр задач.
>
> **Координатора вызывают только по сигналу аналитика:** весь его спектр задач завершён либо возникло ограничение, требующее архитектурного решения или нового указания. Координатор не обновляет файл после каждого промежуточного отчёта.
>
> Последняя координаторская проверка E3: **2026-11-17**, PR #10 финальный проверенный HEAD `9c67641b2407f2ccb954bba564e8a682ac896baf`; sync merge `722b77d5f4bb2d07ce9b75ff7ab10220690ae39b`; E1 API HEAD `a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef`; main на момент final CI `33dfdd9d894a7bedd822168ba479c0989e889211`.

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
| SFRA-E3-01 | E3 | C1: SourceReader, SearchAdapter, dependency resolver, E1 adapter и Snapshot binding | **COORDINATOR_ACCEPTED_NOT_MERGED** | Финальная post-sync проверка на PR HEAD `9c67641b2407f2ccb954bba564e8a682ac896baf`. C1 PR CI [44036521942](https://github.com/yeatu/obsidianGP/actions/runs/44036521942) и push CI [44036515614](https://github.com/yeatu/obsidianGP/actions/runs/44036515614): каждый 45 B1 + 56 C1 passed. Runtime tree соответствует принятому code HEAD `a100239`; merge `722b77d5f4bb2d07ce9b75ff7ab10220690ae39b` подтянул main, docs-only commit `9c67641` освежил README/handoff. На момент проверки ahead 38 / behind 0 относительно main `33dfdd9d894a7bedd822168ba479c0989e889211`. PR #10 open / Draft / not merged. |
| SFRA-E3-02 | E3 | Реальная интеграция E2 → E3 → E1 → Context Pack и negative matrix | **COORDINATOR_ACCEPTED_NOT_MERGED** | Final PR integration [44036522448](https://github.com/yeatu/obsidianGP/actions/runs/44036522448), artifact `14306669437`, digest `sha256:81a402be4949fcf3528a368593e3715ccb23a692541838afc6d8502380fca997`; push run [44036515582](https://github.com/yeatu/obsidianGP/actions/runs/44036515582), artifact `14306674023`, digest `sha256:7d76980bc3935e431cb7d157ceaa9c135af2083d2894d44a52c057c55a0b9675`. Оба success на E3 `9c67641b2407f2ccb954bba564e8a682ac896baf` и E1 `a9ba344`. Подтверждены 4 scope, настоящая parent dependency, stale/not_found/corrupt/ambiguous/deleted/snapshot/document/generation negative matrix, fail-closed и production read-only guards. Ambiguous/deleted воспроизведены на disposable E1 indexes, mismatch cases — fault injection на E3 boundary. Context Pack `budget_limited` (1 included / 2 deferred), scope budget `budget_exceeded`; pack не `complete`. PR открыт, Draft, не объединён. |
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
- Финальный PR HEAD после sync и обновления README/handoff: `9c67641b2407f2ccb954bba564e8a682ac896baf`.
- Sync merge commit: `722b77d5f4bb2d07ce9b75ff7ab10220690ae39b`; parents — исходный E3 HEAD `a100239` и main `33dfdd9d894a7bedd822168ba479c0989e889211`.
- Main / PR base на момент финальной проверки: `33dfdd9d894a7bedd822168ba479c0989e889211`; compare **ahead 38 / behind 0**.
- PR #10: open / Draft / not merged.
- Runtime implementation соответствует принятому code tree `a100239`; коммиты `722b77d` и `9c67641` подтянули main/обновили только registry и документы, не меняя runtime code.

#### Финальный C1 CI на HEAD 9c67641

- [PR CI 44036521942](https://github.com/yeatu/obsidianGP/actions/runs/44036521942): success, **45 B1 + 56 C1 passed**.
- [Push CI 44036515614](https://github.com/yeatu/obsidianGP/actions/runs/44036515614): success, **45 B1 + 56 C1 passed**.
- SourceReader native E1 adapter, четыре scope, parent/sibling identity/order, duplicate IDs, exact hashes/generation/coordinates подтверждены.
- Diagnostics isolation между последовательными pipeline runs проходит; B1 defaults отделены от E1 source annotations.
- Snapshot binder проверяет actual Git HEADs, clean `sfra-state`, manifest raw SHA, SQLite SHA и checkout cleanliness.
- Token budget принадлежит E3; source text не truncates; error paths fail-closed.

#### Финальная real integration на HEAD 9c67641

- [PR real integration 44036522448](https://github.com/yeatu/obsidianGP/actions/runs/44036522448): success; artifact `14306669437`, digest `sha256:81a402be4949fcf3528a368593e3715ccb23a692541838afc6d8502380fca997`.
- [Push real integration 44036515582](https://github.com/yeatu/obsidianGP/actions/runs/44036515582): success; artifact `14306674023`, digest `sha256:7d76980bc3935e431cb7d157ceaa9c135af2083d2894d44a52c057c55a0b9675`.
- Оба отчёта фиксируют E3 `9c67641b2407f2ccb954bba564e8a682ac896baf` и E1 API `a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef`.

Pinned snapshot:
- Vault commit: `2a3c54fa7a9e910f4c9621c8fe00f41a061fc158`;
- sidecar commit: `fb0b45ae0e5043e342c790d43e2b341ca65d7f2b`;
- manifest SHA: `sha256:3d5eacf5fc2f7f927af8f591f317ea95d56d0c0f53de1bc61cb54d23677fd072`;
- SQLite SHA: `sha256:2a6d792d5e5c458ffa87df32a082229fc548c42dab2d91a5cc8fa1195bcf6674`.

Оба final real runs подтвердили:
- E2: 3 hits / 3 source-verifiable candidates; current-node resolver `ok`.
- Реальную `parent_context` dependency через current address и exact source read.
- Все четыре scope node / parent / neighbors / document на одном SnapshotRef.
- Полный document scope: 110 809 UTF-8 bytes, hash/size совпали, truncation отсутствует.
- Wrong hash → `stale_source`; unknown ID → `not_found`; corrupt isolated source copy → `stale_source`.
- Ambiguous neighbor → `ambiguous`; deleted node → `deleted`. Оба сценария воспроизведены на disposable E1 lifecycle indexes через публичный API, не как свойства production sidecar.
- Snapshot echo/request mismatch → `snapshot_mismatch`; document hash mismatch → `document_hash_mismatch`; generation mismatch → `snapshot_generation_mismatch` через fault injection.
- Все failure responses вернули пустые fragments.
- Scope budget 1 token → `budget_exceeded`; Context Pack → `budget_limited`, 1 Included / 2 Deferred, не `complete`.
- Production SQLite, manifest, sidecar tree, Vault tree и HEADs не изменились; оба checkout clean.

#### Решение аналитика и координатора

Аналитик завершил спектр: `ANALYST_COMPLETE_UNREVIEWED / ANALYST_SCOPE_COMPLETE`. Координатор принял C1 и E3-02 в согласованном scope: **`COORDINATOR_ACCEPTED_NOT_MERGED`**.

На синхронизированной ветке и финальном HEAD повторены C1 CI и real integration по PR и push events. Технических блокеров E3 не осталось. PR #10 открыт, Draft, не объединён. Merge не выполнялся.

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

### E3 / PR #10 — финальный HEAD `9c67641b2407f2ccb954bba564e8a682ac896baf`

- [x] PR открыт / Draft / not merged.
- [x] Main синхронизирован в E3-ветку merge-коммитом `722b77d5f4bb2d07ce9b75ff7ab10220690ae39b`; compare ahead 37 / behind 0 сразу после merge.
- [x] README и handoff обновлены docs-only commit `9c67641`; runtime code unchanged.
- [x] Финальный compare на момент workflow: ahead 38 / behind 0 относительно main `33dfdd9d894a7bedd822168ba479c0989e889211`.
- [x] C1 PR CI [44036521942](https://github.com/yeatu/obsidianGP/actions/runs/44036521942): 45 B1 + 56 C1 passed.
- [x] C1 push CI [44036515614](https://github.com/yeatu/obsidianGP/actions/runs/44036515614): 45 B1 + 56 C1 passed.
- [x] PR real integration [44036522448](https://github.com/yeatu/obsidianGP/actions/runs/44036522448): success, artifact 14306669437.
- [x] Push real integration [44036515582](https://github.com/yeatu/obsidianGP/actions/runs/44036515582): success, artifact 14306674023.
- [x] Оба real reports фиксируют E3 HEAD `9c67641`, E1 `a9ba344`, полный набор negative matrix и clean read-only guards.
- [x] SourceReader, four scopes, actual parent dependency, identity/order, diagnostics, snapshot, hashes/generation и budget проверены.
- [x] Контекстные границы evidence документированы: ambiguous/deleted на disposable indexes; mismatch — fault injection.
- [x] Аналитик завершил спектр.
- [x] Координаторская приёмка C1 и E3-02 выполнена: `COORDINATOR_ACCEPTED_NOT_MERGED`.
- [ ] PR #10 переведён из Draft в Ready.
- [ ] PR #10 merged.

**Решение:** C1 и E3-02 приняты; финальная синхронизация и повторные CI/real integration завершены успешно на HEAD `9c67641b2407f2ccb954bba564e8a682ac896baf`. PR остаётся open / Draft / not merged. Перевод в Ready и merge не выполнялись.

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
