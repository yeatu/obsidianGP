# SFRA — рабочий реестр задач и двухэтапная проверка

> **Реестр ведут аналитики.** Они самостоятельно проверяют отчёты исполнителей, ставят отметки, обновляют HEAD и статусы и продолжают утверждённый спектр задач.
>
> **Координатора вызывают только по сигналу аналитика:** весь его спектр задач завершён либо возникло ограничение, требующее архитектурного решения или нового указания. Координатор не обновляет файл после каждого промежуточного отчёта.
>
> Последняя координаторская актуализация: **2026-11-17**. Основной контур E1/E2/E3 и SFRA-E3-V2.1 объединены в main; PR #10 → `5e274fc`, PR #11 → `d654bdc`, PR #7 → `d3e4196`, PR #14 → `9a0bfa0`.

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
| SFRA-E1-01 | E1 | Единый атомарный Source Scope API + current-node resolver | **DONE** | PR [#11](https://github.com/yeatu/obsidianGP/pull/11) merged: `d654bdc009c566608e76d5d25ba219a3d6c2b6ed`. Финальные E1 API tests: 88 passed; structural CI: 88 passed. Отдельный `unit-tests` job был skipped и не считается успешным. Код интегрирован; повторная реализация не требуется. |
| SFRA-E3-01 | E3 | C1: SourceReader, SearchAdapter, dependency resolver, E1 adapter и Snapshot binding | **DONE** | PR [#10](https://github.com/yeatu/obsidianGP/pull/10) merged: `5e274fc85d2d5f9f9fc3a4faaa48657cd7a2b7ec`; проверенный HEAD `4b446c3`. Финальный C1 CI [44038459416](https://github.com/yeatu/obsidianGP/actions/runs/44038459416): 45 B1 + 56 C1 passed. Runtime code принят и находится в main. |
| SFRA-E3-02 | E3 | Реальная интеграция E2 → E3 → E1 → Context Pack и negative matrix | **DONE** | PR #10 merged. Финальная real integration [44038459427](https://github.com/yeatu/obsidianGP/actions/runs/44038459427): success; artifact `14308411701`, SHA-256 `6b096d78395e23a6aadd904a449da0cb48a94131c0c3b03fb17c53108057524a`. Все четыре scope, parent dependency, negative matrix и read-only guards подтверждены. Context Pack остаётся `budget_limited` (1 included / 2 deferred), не `complete`. |
| SFRA-E2-01 | E2 | Active-only фильтрация и интеграционная проверка | **DONE** | PR [#7](https://github.com/yeatu/obsidianGP/pull/7) merged: `d3e41965f916746225cb8f76fd4c96fc9e95486c`. Post-merge workflow [44041253438](https://github.com/yeatu/obsidianGP/actions/runs/44041253438): success, 64 passed / 0 failures / 0 errors / 0 skipped; artifact `14309710985`. |
| SFRA-E3-V2.1 | E3 | Transport-independent SearchVaultService / ReadSourceService application services | **DONE** | PR [#14](https://github.com/yeatu/obsidianGP/pull/14) merged 2026-11-17 09:33:20 UTC: `9a0bfa012269590466a3b314770425a2a97dfe7f`. Implementation HEAD `b093c51833f47b9a4e83e83235ea7fbf591f81a7`; Analyst 3 review [5935543022](https://github.com/yeatu/obsidianGP/pull/14#pullrequestreview-5935543022); Coordinator acceptance reviews [5935913900](https://github.com/yeatu/obsidianGP/pull/14#pullrequestreview-5935913900). Final pre-merge checks on `516d1590744e88574bc9e67724aaaae0c5e4e13d`: C1 [44054181018](https://github.com/yeatu/obsidianGP/actions/runs/44054181018) (45 B1 + 56 C1), V2.1 [44054181091](https://github.com/yeatu/obsidianGP/actions/runs/44054181091) (45 B1 + 56 C1 + 18 V2.1; transport guard), real integration [44054181144](https://github.com/yeatu/obsidianGP/actions/runs/44054181144), artifact `14314428318`. Issue #13 closed as completed. Production Issue worker/recovery/MCP and source-content publication remain out of scope and not authorized. |
| SFRA-E3-V2.2 | E3 | Non-production Issue validation and safe worker core | **COORDINATOR_ACCEPTED_NOT_MERGED** | [Issue #15](https://github.com/yeatu/obsidianGP/issues/15), implementation PR [#16](https://github.com/yeatu/obsidianGP/pull/16), coordinator-reviewed HEAD `b80b5d7fff762afec94634a106f4f2383c74c103`; PR review [5945371158](https://github.com/yeatu/obsidianGP/pull/16#pullrequestreview-5945371158). Analyst re-review [5945263999](https://github.com/yeatu/obsidianGP/pull/16#pullrequestreview-5945263999) confirmed both prior blockers fixed, regression-tested, no further blocker in the agreed non-production scope. Final V2.2 CI [44157175275](https://github.com/yeatu/obsidianGP/actions/runs/44157175275) success: 45 B1 + 56 C1 + 18 V2.1 + 55 V2.2 passed (174 total); dependency/import guard passed. PR remains Open / Draft / unmerged. PR base is `98747f52e3a3b09adfbcdec9084fda32692ab4b4`; main has since advanced with documentation/registry-only updates, including the coordinator acceptance record. Runtime implementation and tests on reviewed HEAD `b80b5d7fff762afec94634a106f4f2383c74c103` were not changed by those main commits. Before merge, sync branch with current main, resolve any documentation conflicts, re-check compare, and rerun the required PR checks on the synchronized HEAD. No GitHub API/SDK, credentials, active event workflows, real Issue/comment writes, source publication, retries/leases/recovery, MCP/HTTP/webhooks or deployment. V2.3/V2.4 remain separate gates and are not authorized. |

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

---

## 7. Координаторская актуализация — 2026-11-17, основной контур объединён

### Состояние GitHub

- Текущий main: `d3e41965f916746225cb8f76fd4c96fc9e95486c`.
- PR [#10 / E3](https://github.com/yeatu/obsidianGP/pull/10) merged в 07:36:29 UTC, merge commit `5e274fc85d2d5f9f9fc3a4faaa48657cd7a2b7ec`. Финальный проверенный HEAD: `4b446c39d40cc7337960e71bb0a1efa5a9359b46`.
- PR [#11 / E1](https://github.com/yeatu/obsidianGP/pull/11) merged в 07:43:42 UTC, merge commit `d654bdc009c566608e76d5d25ba219a3d6c2b6ed`. Проверенный HEAD: `a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef`.
- PR [#7 / E2](https://github.com/yeatu/obsidianGP/pull/7) merged в 07:46:12 UTC, merge commit `d3e41965f916746225cb8f76fd4c96fc9e95486c`. Проверенный HEAD: `af4469d3badf0aa902568ae1926f5b5309a70655`.

### Доказательства после merge

- E3 C1 CI [44038459416](https://github.com/yeatu/obsidianGP/actions/runs/44038459416): success, 45 B1 + 56 C1 passed на финальном E3 HEAD.
- E3 real integration [44038459427](https://github.com/yeatu/obsidianGP/actions/runs/44038459427): success на E3 HEAD `4b446c3` и E1 API `a9ba344`; artifact `14308411701`, SHA-256 `6b096d78395e23a6aadd904a449da0cb48a94131c0c3b03fb17c53108057524a`.
- E1 API CI [44026684195](https://github.com/yeatu/obsidianGP/actions/runs/44026684195): целевой job success, 88 passed; отдельный unit-tests job skipped. Structural CI [44026684168](https://github.com/yeatu/obsidianGP/actions/runs/44026684168): 88 passed.
- E2 post-merge workflow [44041253438](https://github.com/yeatu/obsidianGP/actions/runs/44041253438): success на main merge commit `d3e4196`. 64 tests passed, 0 failures/errors/skipped; SQLite integrity `ok`; 66/66 документов и 9 080/9 080 допустимых узлов; три оригинальных источника SHA-256 verified; Vault digest, E1 SQLite и `sfra-state` остались неизменными. Artifact `14309710985`, SHA-256 `05d4a755d4a2ce72e9840a354ca9301ef42e444f1cc08edfbe58bc1422d872c5`.

**Координаторское решение:** E1-01, E2-01, E3-01 и E3-02 закрыты (`DONE`). Основной retrieval/context контур интегрирован в main. В merge-процессах не делались новые изменения Vault или production sidecar.

### Следующий этап: SFRA-E3-V2.1

Начать с transport-independent application services:
- `SearchVaultService` поверх E2 SearchAdapter и E3 ContextIntegrationPipeline/ContextBuilder;
- `ReadSourceService` поверх публичных E1 `read_source_scope()` и `resolve_current_node()`;
- typed request/result contracts и unit/contract tests;
- отсутствие зависимости от GitHub Issues, comments, workflow SDK, прямого SQL к E1 и transport state;
- один SnapshotRef, provenance и существующая E3 budget policy остаются обязательными.

PR [#12](https://github.com/yeatu/obsidianGP/pull/12) остаётся Draft proposal, не production worker. V2.1 может реализовываться независимо от GitHub transport; PR #12 не даёт разрешения включать worker/recovery.

### Решения координатора по V2 transport gates

1. **Публичная публикация:** deny by default. Нельзя помещать `raw_text`, цитаты, фрагменты, заголовки или source paths из Vault в публичные Issue/comments. На начальном этапе допускаются только операционные статусы и безопасные агрегированные метаданные. Исключение возможно позже только для corpus, явно включённого владельцем в public-export allowlist, и отдельного maintainer approval на Issue. До такой приёмки публикация source content отключена.
2. **Авторизация:** начальный allowlist — только точный GitHub login `yeatu`; пустой или отсутствующий allowlist означает fail-closed. Расширение — отдельное решение.
3. **Схема:** request envelope сохраняется как `sfra.issue.v1`. Добавить `status_schema_version: 2` и обязательные `request_body_sha256` + `worker_commit_sha` в transport status. Не менять request schema ради полей transport state.
4. **Лимиты:** request body ≤ 32 KiB UTF-8; result chunk ≤ 45 KiB; aggregate serialized result ≤ 256 KiB; worker timeout 30 минут; RUNNING lease 35 минут.
5. **Recovery/retry:** interval 5 минут; max-parallel 5; max attempts 3; backoff 5 и 15 минут. Concurrency per Issue без cancel-in-progress; worker повторно валидирует Issue, body hash, status и SnapshotRef на каждом запуске.
6. **Budget:** только существующая E3 token budget policy; transport не может повышать бюджет, усекать source text или подменять `budget_limited` на `complete`.
7. **Операционное владение:** первоначальный владелец — владелец/администратор репозитория `yeatu`; отключение worker workflow и удаление ошибочно опубликованных комментариев — maintainer action.

Production Issue worker, recovery и публикация source content не разрешены до отдельной security/readiness проверки V2.2–V2.4. MCP остаётся optional и не является зависимостью V2 MVP.

## 8. Промежуточная координаторская приёмка SFRA-E3-V2.1 — 2026-11-17 (до merge; historical)

Этот раздел фиксирует состояние до объединения PR #14. Его пункты о Draft / not merged superseded финальным разделом 9 ниже.

- [x] Аналитик завершил V2.1: review #5935543022, `ANALYST_COMPLETE_UNREVIEWED`, блокирующих дефектов в согласованном scope не выявлено.
- [x] README и analyst handoff синхронизированы; прежние evidence на `9b57c68` помечены как исторические.
- [x] Проверены PR head `974d56be8fb57ae8a02eeaf97ae15ff09cc4b47c` и compare: ahead 16 / behind 0 относительно main `5090047cb6a47be4783f4625c1d175fd23083bae`.
- [x] Повторный C1 CI #44053145639: 45 B1 + 56 C1 passed.
- [x] Повторный V2.1 CI #44053145836: 45 B1 + 56 C1 + 18 V2.1 passed; transport dependency guard passed.
- [x] Повторная real integration #44053145679: success; artifact `14315355448`, SHA-256 `d510864636b373169d5285613bb1786cfdad41c9957f8dc815da13c19f95931b`.
- [x] Проверены один pinned SnapshotRef, четыре source scopes, сохранение `budget_limited`, E3-owned `budget_exceeded` без partial fragments и неизменность production state / Vault / sidecar.
- [x] Координаторская приёмка: `COORDINATOR_ACCEPTED_NOT_MERGED`.
- [ ] PR #14 переведён из Draft в Ready.
- [ ] PR #14 merged.

**Решение:** V2.1 принят только как transport-independent application services. PR #14 остаётся Open / Draft / not merged. Никакого разрешения на production Issue worker/recovery, MCP, HTTP/webhooks или публикацию Vault source content не выдано. Public source-content policy остаётся deny-by-default.


## 9. Завершение SFRA-E3-V2.1 — merge 2026-11-17

- [x] PR #14 переведён в Ready for review.
- [x] PR #14 merged в `main` в 09:33:20 UTC: `9a0bfa012269590466a3b314770425a2a97dfe7f`.
- [x] Runtime implementation принята в согласованном transport-independent scope.
- [x] Issue #13 закрыт как completed.
- [x] README, analyst handoff, PROJECT_TASKS и Coordinator Session 3 registry обновлены после merge.
- [x] Pre-merge C1 / V2.1 / real integration gates прошли на `516d1590744e88574bc9e67724aaaae0c5e4e13d`; implementation code не менялся после проверки.
- [x] Проверена конфигурация post-merge workflow triggers: целевые workflow не настроены на push в `main`, поэтому отдельный post-merge run не создан. Pre-merge зелёные проверки остаются валидным evidence для неизменённого runtime code.

**Итог:** SFRA-E3-V2.1 = `DONE`. Это не включает GitHub Issue worker/recovery, MCP, HTTP/webhooks или публикацию Vault source content. Public source-content publication remains deny-by-default.


## 10. SFRA-E3-V2.2 — non-production Issue core

- [x] V2.1 завершена и merged: PR #14, `9a0bfa012269590466a3b314770425a2a97dfe7f`; Issue #13 closed/completed.
- [x] Создан отдельный Issue [#15](https://github.com/yeatu/obsidianGP/issues/15) для V2.2.
- [x] Scope ограничен non-production parser/validator, status schema v2, request body hash, safe aggregate projector и IssueWorkerCore over fake/in-memory ports.
- [x] Явно запрещены GitHub API/SDK, credentials/network/write calls, active event workflows, реальные Issue/comment writes, source-content serialization, leases/retries/recovery, MCP/HTTP/deployment.
- [x] Исполнитель 3 реализовал V2.2 по Issue #15 в согласованном scope; runtime/test HEAD: `b80b5d7fff762afec94634a106f4f2383c74c103`.
- [x] Аналитик 3 провёл независимую проверку исходного runtime HEAD: review [5945263999](https://github.com/yeatu/obsidianGP/pull/16#pullrequestreview-5945263999); оба блокирующих замечания исправлены, 174 теста и dependency/import guard прошли.
- [x] PR синхронизирован с актуальным `main` без force-push: итоговый HEAD `75a7432555029e60edc67463f92ada9d6179651b`; base и merge base `e2e64a0339fe0e94e237b7de5b401af5b69d8635`; compare ahead 13 / behind 0.
- [x] Повторный CI на точном синхронизированном HEAD: [run 44163173690](https://github.com/yeatu/obsidianGP/actions/runs/44163173690) — B1 45, C1 56, V2.1 18, V2.2 55; всего 174 passed, dependency/import guard passed.
- [x] Аналитик 3 провёл повторную независимую проверку синхронизированного HEAD: [review 5945559834](https://github.com/yeatu/obsidianGP/pull/16#pullrequestreview-5945559834). Sync commit меняет только `PROJECT_TASKS.md` и реестр аналитика; runtime, tests, schemas и workflow не менялись относительно ранее проверенного HEAD.
- [ ] Финальная координаторская проверка синхронизированного HEAD.
- [ ] PR #16 переведён из Draft в Ready и merged (только после отдельного решения координатора).

**Текущий статус:** `ANALYST_COMPLETE_UNREVIEWED` на HEAD `75a7432555029e60edc67463f92ada9d6179651b`. PR #16 остаётся Open / Draft / unmerged. Ранее выданная координаторская приёмка V2.2 относится к согласованной реализации на HEAD `b80b5d7`; после синхронизации координатору поручена финальная проверка актуального HEAD перед любым решением о merge.

**Ограничения:** V2.3 (реальный GitHub transport/recovery) и V2.4 (controlled rollout) не запускать. Это обновление не разрешает production execution, GitHub API/SDK, credentials, реальные Issue/comment writes, активные event workflows, source-content publication, leases/retries/recovery, MCP/HTTP/webhooks или deployment.
