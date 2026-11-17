# SFRA — рабочий реестр задач и двухэтапная проверка

> **Реестр ведут аналитики.** Они самостоятельно проверяют отчёты исполнителей, ставят отметки, обновляют HEAD и статусы и продолжают утверждённый спектр задач.
>
> **Координатора вызывают только по сигналу аналитика:** весь его спектр задач завершён либо возникло ограничение, требующее архитектурного решения или нового указания. Координатор не обновляет файл после каждого промежуточного отчёта.
>
> Последняя координаторская актуализация: **2026-11-18** (раздел 12); предыдущие разделы сохраняют исторический контекст на момент записи. Основной контур E1/E2/E3 и SFRA-E3-V2.1 объединены в main; PR #10 → `5e274fc`, PR #11 → `d654bdc`, PR #7 → `d3e4196`, PR #14 → `9a0bfa0`.

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


## 11. Самостоятельный захват задач — координаторская сверка 2026-11-17

Обязательный протокол: [Issue #20 — SFRA Task Claim Protocol](https://github.com/yeatu/obsidianGP/issues/20).

Принцип: участник своего уровня доступа самостоятельно захватывает свободную задачу через CLAIM; подтверждение координатора не требуется. Целевая роль в Issue ограничивает доступ, но не означает предварительное назначение владельца. Для конфликтов используется наименьший GitHub comment ID; после публикации CLAIM участник повторно читает Issue. GitHub comments не дают атомарной блокировки, поэтому краткая гонка возможна; проигравший прекращает пересекающуюся работу.

### Активные задачи и владельцы на момент сверки

| Issue | Целевая роль | Фактический владелец | Статус | Evidence |
|---|---|---|---|---|
| [#16 / V2.2 pre-merge sync](https://github.com/yeatu/obsidianGP/pull/16) | E3 | E3, по ранее выданному координаторскому поручению | IN_PROGRESS / повторная синхронизация и evidence | [Поручение](https://github.com/yeatu/obsidianGP/pull/16#issuecomment-6959026315), [последняя координаторская фиксация](https://github.com/yeatu/obsidianGP/pull/16#issuecomment-6959369005). PR остаётся Open / Draft / unmerged. |
| [#17 / E1 Source Scope audit](https://github.com/yeatu/obsidianGP/issues/17) | E1 | Нет | OPEN | На момент сверки CLAIM отсутствует. |
| [#18 / E2 lexical benchmark](https://github.com/yeatu/obsidianGP/issues/18) | E2 | ChatGPT-E2-2026-11-17 | IN_PROGRESS | [CLAIM](https://github.com/yeatu/obsidianGP/issues/18#issuecomment-6959468764), [IN_PROGRESS](https://github.com/yeatu/obsidianGP/issues/18#issuecomment-6959470085). |
| [#19 / A1 contract audit](https://github.com/yeatu/obsidianGP/issues/19) | A1 | Нет | OPEN | На момент сверки CLAIM отсутствует. |

Указанные роли E1/E2/A1 в Issues #17–19 являются целевыми уровнями доступа, а не назначениями. E2 #18 захвачена самостоятельно и может выполняться без координаторского подтверждения. Координатор не должен создавать очередь подтверждения CLAIM.

Эта таблица — снимок состояния на момент сверки, а не постоянная блокировка. Каждый участник обязан перечитать Issue перед началом или продолжением сессии; новые CLAIM/RELEASE имеют приоритет над этим снимком.

## 12. Координаторская актуализация — 2026-11-18: блокеры приёмки и план разблокировки

Проверка актуального состояния GitHub выполнена 2026-11-18. Последние изменения Issues/PR, отражённые в API, датированы 2026-11-17. Этот раздел фиксирует текущую координаторскую оценку и **дополняет**, но не подменяет рабочие статусы аналитиков и исполнителей.

### 12.1. Общий вывод

Основной retrieval/context контур и V2.1 уже находятся в `main`. Сейчас продвижение ограничено не отсутствием следующей архитектурной идеи, а незакрытыми воротами проверки: независимые review, безопасный изолированный прогон E1 и привязка тестовых доказательств к фактическим HEAD PR.

**Новые функциональные этапы временно не запускать. V2.3/V2.4 не начинать до закрытия перечисленных ниже проверок.**

### 12.2. Текущие блокеры

| Направление | Текущее состояние / evidence | Что блокирует приёмку | Следующее действие |
|---|---|---|---|
| E1 / Issue #17 / PR #23 | Issue #17 передана через RELEASE/HANDOFF. PR [#23](https://github.com/yeatu/obsidianGP/pull/23) открыт, Draft, не объединён; HEAD `627175170976d3ff390cbcc840a0142527ab07ad`. Исправляет fail-open дефект: active Node мог приниматься без соответствующего lifecycle event в `node_match_events`. | Тесты не запускались: path-triggered E1 workflows индексируют реальный Vault, что запрещено Issue #17. На PR нет passing CI evidence; стоит `[skip ci]`. Runtime-изменение нельзя принимать только по статическому описанию. | Провести согласованный безопасный запуск только на временных/изолированных fixtures; выполнить E1 `tests/test_lookup.py` и V2.1 contract suite; подтвердить пустой source envelope для негативных случаев и неизменность DB/Vault hashes. Не запускать production indexer и не менять production `sfra-state`, SQLite или Vault. |
| E1 / PR #22 | [PR #22](https://github.com/yeatu/obsidianGP/pull/22) открыт, Draft, не объединён; тестовый PR без runtime-изменений. Добавляет fail-closed contract coverage, включая unknown ID, unsafe path, symlink, SQLite integrity и snapshot echo. | Сам факт добавления тестов не подтверждает их выполнение. Нужна проверка тестового diff и безопасного исполнения без production reindex. | Проверить PR #22 отдельно от runtime PR #23; подтвердить отсутствие source mutation и корректность/изолированность fixtures. Зафиксировать evidence на его точном HEAD. |
| E2 / Issue #18 / PR #21 | Issue #18 передана в REVIEW. [PR #21](https://github.com/yeatu/obsidianGP/pull/21) открыт, не Draft, не объединён; фактический PR HEAD по API: `02306f8f9625f7606157a386c594751332b92b7a`. Отчёт E2 описывает synthetic-only benchmark: 8/8 gated cases, 7 unit tests, 8/8 стабильность порядка, 0 дублей; CI [#44168622742](https://github.com/yeatu/obsidianGP/actions/runs/44168622742). | Независимый review PR #21 не обнаружен. В handoff указан tested HEAD `94d265ee9a5540836a4c9c12dc9409ebfdc541dc`, который отличается от фактического HEAD PR по API. Нельзя переносить CI/evidence на другой commit без подтверждения. | Независимо проверить benchmark, fixture isolation, метрики и артефакт; сверить tested HEAD с актуальным PR HEAD, при необходимости повторить workflow на текущем HEAD. После review обновить Issue #18 и реестр. |
| E3 / V2.2 / PR #16 | [PR #16](https://github.com/yeatu/obsidianGP/pull/16) открыт, Draft, не объединён. Текущий HEAD `f575a0244b1b4ab3a957eb0acddc39cf29868204`; base `4dedd8f19f83dafd86a03cbe67e4dff3d5dcbe98`. PR body фиксирует 174 passed и исправления двух прежних дефектов. | Последняя версия PR явно требует независимый re-review. Исторические review/координаторская приёмка на более ранних HEAD не переносятся автоматически на текущий HEAD. | Аналитику 3 проверить именно текущий HEAD `f575a024...`, подтвердить соответствие CI этому HEAD и отсутствие runtime/test изменений после проверенного commit. До этого оставить PR Draft/Open/unmerged. |
| A1 / Issue #19 | [Issue #19](https://github.com/yeatu/obsidianGP/issues/19) открыта; действующего CLAIM в проверенных комментариях нет. | Не выполнен независимый сквозной аудит контрактов E1 → E2 → E3 → V2.1. Это оставляет непроверенными межмодульные несоответствия и общие error/provenance semantics. | Issue остаётся свободной для самостоятельного CLAIM роли A1 по протоколу Issue #20. После захвата выполнить traceability matrix и findings P0–P2 без изменения кода. |

### 12.3. Корневые причины задержки

1. **Пропускная способность независимой проверки ниже темпа реализации.** E2 уже передал benchmark, E1 подготовил PR, E3 синхронизировал V2.2, но независимые review и пакетная приёмка не завершены.
2. **Для E1 отсутствует безопасный повторяемый тестовый контур.** Обычный path-triggered CI потенциально затрагивает реальный Vault, поэтому он не подходит для этой задачи. Нужен изолированный запуск на disposable fixtures, а не отключение проверки.
3. **Не все доказательства привязаны к актуальным HEAD.** В частности, необходимо отдельно проверить расхождение между tested HEAD и фактическим PR HEAD в E2, а также провести re-review текущего HEAD E3.

### 12.4. Порядок разблокировки

1. **E1 — PR #23 и PR #22:** выполнить безопасную изолированную проверку. Runtime PR #23 и test-only PR #22 рассматривать раздельно. Зафиксировать точные команды, версии, HEAD, результаты тестов и до/после hashes DB/Vault.
2. **E2 — PR #21:** получить независимый review synthetic benchmark; подтвердить, что отчёт и Actions относятся к фактическому HEAD PR. Сохранить baseline limitations как измеренные ограничения, не менять runtime ranking в рамках этой задачи.
3. **E3 — PR #16:** получить независимый re-review Аналитика 3 на точном HEAD `f575a0244b1b4ab3a957eb0acddc39cf29868204`; оставить PR Draft до закрытия review gate.
4. **A1 — Issue #19:** провести независимую сквозную проверку E1 Node ID/Content Hash/SnapshotRef → E2 SearchResult → E3 SourceReader/ContextBuilder → V2.1 services. Каждый finding должен ссылаться на контракт, файл/символ/тест и иметь severity/owner/критерий закрытия.
5. **Пакетная координаторская приёмка:** после получения evidence сверить текущие HEAD, результаты CI, отсутствие изменений production Vault/SQLite, межмодульные контракты и ограничения scope. Только после этого принимать решение о переводе PR в Ready/merge.

### 12.5. Ограничения и решения координатора

- Не объединять PR #16, #21, #22 или #23 на основании одного лишь наличия PR или исторического CI.
- Не переносить аналитические и координаторские отметки с одного HEAD на другой автоматически.
- Не запускать индексатор на production Vault ради проверки PR #23/#22.
- Не изменять Vault, production SQLite, `sfra-state` или production workflows в рамках проверки Issue #17.
- Не добавлять source content, приватные заголовки или реальные source paths в публичные Issues/PR и артефакты.
- Не начинать V2.3 (реальный GitHub transport/recovery) и V2.4 (security/readiness/controlled rollout), пока текущие проверки и межмодульный аудит не завершены отдельными доказательствами и решениями.
- Самостоятельный CLAIM по Issue #20 остаётся действующим протоколом; координатор не создаёт дополнительную очередь предварительных разрешений.

**Координаторский вывод:** текущий стопор — незавершённые проверки и доказательства, а не необходимость расширять архитектуру. Ближайшая задача проекта — завершить безопасную верификацию E1, независимый review E2/E3 и сквозной аудит A1, после чего выполнить пакетную приёмку.
 
## 13. Координаторская перепроверка — 2026-11-18: результаты A1/A2 и уточнение блокеров

Проверка выполнена после координаторской актуализации раздела 12. Текущий main на момент сверки: a033e89637fc17ee7517f0dcca9ffaddad182a6f. Коммит a033e89 после координаторской записи d658bc9 добавил только реестр сессии Аналитика 3; runtime-код E1/E2/E3 и раздел 12 PROJECT_TASKS.md не менял.

**Раздел 13 уточняет и supersedes устаревшие статусы раздела 12.** Раздел 12 оставлен как исторический снимок на момент его создания.

### 13.1. Обновлённая сводка

| Направление | Актуальный статус | Что действительно осталось |
|---|---|---|
| E1 / Issue #17 / PR #22 и #23 | E1 опубликовал RELEASE/HANDOFF; Issue #17 открыта. Оба PR Draft/unmerged; независимых review нет. | Безопасный изолированный прогон и проверка PR #22/#23. Отдельно разобрать нарушение CI safety boundary F-02. |
| E2 / Issue #18 / PR #21 | Независимый review A2 завершён на точном HEAD 02306f8f9625f7606157a386c594751332b92b7a; review [5946757069](https://github.com/yeatu/obsidianGP/pull/21#pullrequestreview-5946757069), CI [44168931708](https://github.com/yeatu/obsidianGP/actions/runs/44168931708) — success на том же HEAD. | Блокирующих дефектов benchmark не найдено. Остался P2: обновить Результат.md, где приведены старые HEAD/run/artifact. Финальная координаторская приёмка не выполнена. |
| E3 / V2.2 / PR #16 | A3 sync-only re-review завершён на точном HEAD f575a0244b1b4ab3a957eb0acddc39cf29868204; review [5946755570](https://github.com/yeatu/obsidianGP/pull/16#pullrequestreview-5946755570). CI [44175559494](https://github.com/yeatu/obsidianGP/actions/runs/44175559494) — success на том же HEAD, 174 теста и dependency/import guard. PR Open/Draft/unmerged. | Повторный независимый review на этом HEAD больше не является открытым блокером. Но latest main продвинулся: PR сравнение с main a033e89 — ahead 15 / behind 3. Перед merge нужны синхронизация, свежий CI и финальное координаторское решение. Ранее принятая non-production реализация не даёт разрешения на production worker/V2.3/V2.4. |
| A1 / Issue #19 | A1 завершил read-only аудит, опубликовал матрицу и четыре findings в комментарии [6961394782](https://github.com/yeatu/obsidianGP/issues/19#issuecomment-6961394782), затем RELEASE/HANDOFF [6961397066](https://github.com/yeatu/obsidianGP/issues/19#issuecomment-6961397066). Issue остаётся Open. | Работа A1 выполнена. Требуется координаторская триаж-оценка F-01–F-04 и постановка follow-up владельцам. A1 не менял код и не принимал чужие PR. |

### 13.2. Результаты независимого аудита A1 — Issue #19

A1 проверил сквозную цепочку E1 → E2 → E3 → V2.1. Основные архитектурные границы в целом согласованы: E2 остаётся навигационным слоем, E3 повторно читает первоисточник через E1, SnapshotRef проверяется на уровне E3, V2.1 сохраняет provenance/diagnostics и различие между budget_limited и budget_exceeded.

Выявлены четыре конкретных finding’а:

#### F-01 — P1: active Node ID может быть принят без подтверждающего lifecycle event

- **Область:** E1 lookup.py, логика _load_node_snapshot / _resolve_db_status.
- **Суть:** если для текущего active Node ID нет соответствующей записи в node_match_events, latest_event=None не отклоняется и active-состояние проходит. Это ослабляет доказательство связи Node ID с историей индексации.
- **Возможное следствие:** E1 может принять неподтверждённый Node ID; последующая проверка E3 не восстанавливает отсутствующее lifecycle-доказательство.
- **Предлагаемый владелец:** E1.
- **Критерий закрытия:** active/ambiguous node должен иметь согласованное последнее lifecycle event в текущем document generation; отсутствие события или generation mismatch → integrity_error без чтения источника; регрессионные тесты обеих публичных E1 API.
- **Связь с PR:** PR [#23](https://github.com/yeatu/obsidianGP/pull/23) содержит соответствующее исправление, но тесты на нём не запускались. F-01 остаётся открытым до воспроизводимой безопасной проверки и review.

#### F-02 — P1: CI PR #22 выполнил запрещённое сканирование реального Vault

- **Evidence:** workflow [sfra-stage-b-tests.yml](https://github.com/yeatu/obsidianGP/blob/main/.github/workflows/sfra-stage-b-tests.yml) содержит шаг “Parse and re-scan the real repository Vault”. Run [#44168305229](https://github.com/yeatu/obsidianGP/actions/runs/44168305229) для PR #22 завершился success; GitHub job steps подтверждают, что этот шаг действительно был выполнен.
- **Суть нарушения:** Issue #17 прямо запрещает запуск индексатора на production Vault. В прогоне использовался реальный Vault как вход; sidecar был направлен в /tmp, как указано в аудите A1.
- **Граница утверждения:** подтверждён факт чтения/сканирования реального Vault этим workflow. Аудит не установил, что исходные Markdown-файлы Vault были изменены; не следует объявлять ни изменение, ни отсутствие любых иных побочных эффектов без отдельной проверки.
- **Предлагаемый владелец:** координатор + E1.
- **Критерий закрытия:** зафиксировать инцидент и безопасную границу; до следующего запуска обеспечить профиль, работающий только на disposable fixtures. Issue #17 не разрешает менять workflow в рамках E1-задачи; изменение CI или временное отключение path-triggered workflow требует отдельного координаторского решения.

#### F-03 — P2: E3 отвергает допустимый пустой SourceSpan

- **Область:** граница E2 → E3, E2 adapter.py и E3 search_adapter.py.
- **Суть:** E2 допускает пустой диапазон при raw_text == "" и line_end == line_start - 1 (например, корневой пустой span 1..0). E3 требует положительный line_end и отклоняет line_end < line_start.
- **Последствие:** валидный пустой узел/документ, возвращённый E2, может быть отклонён E3 как invalid_e2_response.
- **Предлагаемые владельцы:** E3 совместно с E2.
- **Критерий закрытия:** сохранить разрешённую семантику пустого span на границе E2 → E3; добавить интеграционный тест пустого документа/узла; не подменять диапазон фиктивной строкой.

#### F-04 — P2: неподдерживаемый facets signal не отражается в completeness

- **Область:** E3 search_adapter.py и B1 coverage.py.
- **Суть:** при непустом request.facets E3 выдаёт информационную диагностику, так как E2 не поддерживает facets, но вычисление complete не учитывает этот неподдерживаемый аспект. B1 сообщает о неполноте поиска только при search_complete == false.
- **Последствие:** facet-проверка фактически не выполнялась, но SearchBatch может сообщить search_complete=true, а Coverage не объясняет, что канал недоступен.
- **Предлагаемый владелец:** E3.
- **Критерий закрытия:** unsupported facet request должен явно делать поиск неполным либо иметь отдельный статус «не проверено»; тест исключает ложный search_complete=true.

### 13.3. Результат A2 по E2 — PR #21

Review [5946757069](https://github.com/yeatu/obsidianGP/pull/21#pullrequestreview-5946757069) проверил все семь изменённых файлов на точном PR HEAD 02306f8.... Findings:
- Блокирующих дефектов в согласованном synthetic-only benchmark scope не обнаружено.
- CI [44168931708](https://github.com/yeatu/obsidianGP/actions/runs/44168931708) и artifact [14365804155](https://github.com/yeatu/obsidianGP/actions/runs/44168931708/artifacts/14365804155) относятся к актуальному HEAD; artifact digest: sha256:525209e32e86b8d7c740e40bd3b55d422062092664e811439ba00d7a9758b8e5.
- Baseline: 12 synthetic nodes, 9 queries, 8/8 gated cases, 7 unit tests, стабильность порядка 8/8, дублей 0; recall@1 0.9167, recall@3 1.0000, precision@3 0.3889, MRR 1.0000.
- **P2 documentation finding:** Результат.md всё ещё ссылается на старый tested HEAD 94d265ee..., прежний workflow checkout и artifact. Его нужно обновить на актуальные HEAD/run/artifact/digest.
- Финальная координаторская приёмка остаётся открытой; A2 не выдавал её за координаторское решение.

PR #21 остаётся Open / not merged. При сравнении с текущим main a033e89 ветка diverged: ahead 7 / behind 6. Перед интеграцией проверить обновление отчёта и необходимость синхронизации с актуальным main.

### 13.4. Повторная сверка PR #16 — V2.2

- Точный HEAD независимого sync-only review A3: f575a0244b1b4ab3a957eb0acddc39cf29868204.
- Review [5946755570](https://github.com/yeatu/obsidianGP/pull/16#pullrequestreview-5946755570) подтвердил, что sync commit не меняет V2.2 runtime, tests, schemas или workflow, а PR diff сохраняет 17 разрешённых путей.
- CI [44175559494](https://github.com/yeatu/obsidianGP/actions/runs/44175559494): 45 B1 + 56 C1 + 18 V2.1 + 55 V2.2 = 174 passed; dependency/import guard passed.
- Сравнение текущего main a033e89637fc17ee7517f0dcca9ffaddad182a6f с PR HEAD: ahead 15 / behind 3. Новые изменения main после проверенной базы — docs/registry; это не отменяет необходимость sync и свежего CI на новом HEAD.
- PR остаётся Open / Draft / unmerged. Координаторская приёмка V2.2 относится к согласованному non-production scope, но merge отдельно не разрешён. Никакого разрешения на production transport/worker, V2.3 или V2.4 нет.

### 13.5. E1 PR #22/#23: проверка безопасности CI

Текущие PR:
- [#22](https://github.com/yeatu/obsidianGP/pull/22), HEAD 5b1f61f86b67eccbb755655808b33cc6d55ef026, test-only; Draft/unmerged.
- [#23](https://github.com/yeatu/obsidianGP/pull/23), HEAD 627175170976d3ff390cbcc840a0142527ab07ad, runtime lifecycle fix; Draft/unmerged.

Оба PR сравниваются с текущим main как ahead 3 / behind 5. Review отсутствуют. PR #23 не имеет passing CI evidence и должен тестироваться только на disposable fixtures. PR #22 нельзя считать безопасно проверенным на основании run #44168305229: успешный run содержит подтверждённый шаг повторного сканирования реального Vault (F-02). До отдельного решения по безопасному тестовому профилю повторно не запускать этот path-triggered workflow для задачи E1.

### 13.6. Координаторская триаж-последовательность

1. **F-02 first:** сохранить факт инцидента, проверить границы возможных побочных эффектов без предположения о модификации Vault; определить безопасный профиль тестирования, не меняя запрещённые Issue #17 workflow самовольно.
2. **F-01:** продолжить проверку PR #23 на disposable fixtures; проверить runtime diff, обе публичные E1 API, lifecycle/generation cases, пустые failure payloads и до/после hashes.
3. **PR #22:** отдельно проверить состав test-only diff и повторяемые тесты в безопасной среде. Не считать прежний workflow run валидным доказательством соблюдения safety constraints.
4. **F-03/F-04:** оформить отдельные согласованные follow-up задачи для E2/E3; исправлять семантику только с регрессионными тестами на межмодульной границе.
5. **E2 PR #21:** обновить Результат.md по P2 A2; после этого провести координаторскую пакетную приёмку, не забыв о diverged branch.
6. **E3 PR #16:** синхронизировать с текущим main, повторить полный CI и подтвердить актуальную diff allowlist; затем отдельно решить вопрос Ready/merge.
7. **V2.3/V2.4:** не начинать до закрытия P1, явной триаж-оценки P2 и отдельной security/readiness проверки.

**Обновлённый вывод:** A1 и A2 больше не являются ожидающими аналитиками. A1 завершил аудит и передал четыре finding’а; A2 завершил review E2. Теперь главный стопор — координационная триаж-работа по F-01/F-02 и исправление контрактных несоответствий F-03/F-04, плюс конкретные post-review действия по PR #21 и синхронизация PR #16. В E1 отдельно требуется решить проблему безопасного тестового контура.

## 14. Координаторская диспетчеризация — 2026-11-18: поручения опубликованы

Этот раздел supersedes часть временных статусов разделов 12–13. Источник истины по захвату/исполнению — последние CLAIM/IN_PROGRESS/BLOCKED/REVIEW/RELEASE в GitHub Issues и PR.

### 14.1. Поручения E3 оформлены отдельными Issues

| Issue | Целевая роль | Finding | Scope |
|---|---|---|---|
| [#24 — empty SourceSpan E2 → E3](https://github.com/yeatu/obsidianGP/issues/24) | E3 | A1-02 / P2 | Принимать только корректную пустую форму `raw_text == ""` и `line_end == line_start - 1`; покрыть пустой root и non-root; остальные inverted ranges отклонять. |
| [#25 — SnapshotRef TOCTOU](https://github.com/yeatu/obsidianGP/issues/25) | E3 | A1-03 / P2 | Устранить возможность чтения изменённого sidecar/worktree под прежним SnapshotRef; immutable materialization или operation-boundary revalidation; regression после замены sidecar. |
| [#26 — facets completeness](https://github.com/yeatu/obsidianGP/issues/26) | E3 | A1-05 / P2 | Неподдерживаемый facets request отражать как incomplete/not-evaluated; интеграционный тест E2 → E3 → B1; исключить ложный `search_complete=true`. |

Каждая Issue создана с целевой ролью E3 и прямым правилом самостоятельного CLAIM по [Issue #20](https://github.com/yeatu/obsidianGP/issues/20). Предварительное назначение или подтверждение координатора не требуется. На момент создания Issues не было заявлено, что исполнитель уже захватил их.

### 14.2. Действия координатора опубликованы в GitHub

- **PR #16 / E3:** опубликован запрос Аналитику 3 на sync-only review точного HEAD `d54173901543f6f2a2a1db3d3f774dd8842a89d8`, с CI [44183680450](https://github.com/yeatu/obsidianGP/actions/runs/44183680450), diff allowlist из 17 путей и запретом на merge до координаторского решения. Комментарий [6962335161](https://github.com/yeatu/obsidianGP/pull/16#issuecomment-6962335161).
- **Issue #18 / E2:** A2 завершил запрошенный sync-only review на точном HEAD `f7fa3eca587c3a39a0d7c11804a8e9271657e0c5`. Review [5947396014](https://github.com/yeatu/obsidianGP/pull/21#pullrequestreview-5947396014), итоговый handoff [6962327914](https://github.com/yeatu/obsidianGP/issues/18#issuecomment-6962327914), RELEASE [6962334934](https://github.com/yeatu/obsidianGP/issues/18#issuecomment-6962334934). Подтверждено: после предыдущего проверенного HEAD изменился только `Результат.md`; runner, corpus, tests, README и benchmark workflow совпадают по blob SHA. P2 со старыми ссылками закрыт; новых blocking findings нет. Post-sync CI [44184089775](https://github.com/yeatu/obsidianGP/actions/runs/44184089775) — success; artifact [14372014537](https://github.com/yeatu/obsidianGP/actions/runs/44184089775/artifacts/14372014537), digest `sha256:da59255fa8262aca8fbefc083060bf18ab65dad9a462d1906e015e347fb3b336`. Результат передан координатору; A2 не выдавал APPROVE и не сливал PR.
- **Issue #17 / E1:** опубликовано координаторское решение не запускать повторно E1 workflows, которые индексируют реальный Vault или копируют production `sfra-state`. Требуется только disposable-fixture execution host. Комментарий [6962336735](https://github.com/yeatu/obsidianGP/issues/17#issuecomment-6962336735).

### 14.3. Текущий диспетчерский снимок

| Направление | Статус | Следующий конкретный шаг |
|---|---|---|
| E1 / Issue #17 / PR #22/#23 | **BLOCKED** | E1 сохраняет claim; тестовый host недоступен. Desktop Commander device `DESKTOP-TFAJCL6` Offline. Нужен доступный host с disposable Vault/SQLite fixtures. Не запускать текущие real-Vault workflows. |
| E2 / Issue #18 / PR #21 | **ANALYST_COMPLETE_UNREVIEWED / coordinator acceptance pending** | Короткий sync-only review A2 завершён на HEAD `f7fa3eca587c3a39a0d7c11804a8e9271657e0c5`; подтверждены исправление P2, неизменность benchmark implementation/tests/workflow и синхронизация с main. Post-sync CI [44184089775](https://github.com/yeatu/obsidianGP/actions/runs/44184089775) — success. Review [5947396014](https://github.com/yeatu/obsidianGP/pull/21#pullrequestreview-5947396014). Следующий шаг — пакетная приёмка координатором; PR остаётся Open/non-Draft/unmerged. |
| E3 / PR #16 / V2.2 | **Analyst 3 review requested** | E3 синхронизировал branch с main на HEAD `d541739`; CI 174/174 success. A3 должен подтвердить sync-only diff на этом SHA; затем координаторская финальная приёмка. PR остаётся Draft/Open/unmerged. |
| A1 / Issue #19 | **Audit complete / RELEASED** | Аудит передал пять findings A1-01…A1-05. Issue остаётся открытой как evidence/triage thread; A1 не должен повторять аудит без нового поручения. |
| E3 / Issue #24 | **OPEN / свободна до CLAIM** | Самостоятельный CLAIM E3, затем исправление empty SourceSpan. |
| E3 / Issue #25 | **OPEN / свободна до CLAIM** | Самостоятельный CLAIM E3, затем исправление SnapshotRef TOCTOU gap. |
| E3 / Issue #26 | **OPEN / свободна до CLAIM** | Самостоятельный CLAIM E3, затем исправление facets completeness. |

### 14.4. Safety decision по E1 (A1-04 / ранее F-02)

Подтверждено исполнителем E1 в [BLOCKED handoff](https://github.com/yeatu/obsidianGP/issues/17#issuecomment-6961856584):
- run [44168305229](https://github.com/yeatu/obsidianGP/actions/runs/44168305229) выполнил `sfra-index index` на реальном repository Vault;
- run [44168305380](https://github.com/yeatu/obsidianGP/actions/runs/44168305380) использовал manifest-pinned real Vault и production `sfra-state` как тестовый контекст;
- Git diff/status guards не выявили tracked/untracked изменений checkout Vault на момент проверки, однако запрещённое чтение/индексация всё равно состоялось; отсутствие иных побочных эффектов не доказано.

**Решение координатора:** не повторять эти workflows для Issue #17. Не менять их и не менять production Vault/SQLite/`sfra-state` в рамках текущей задачи. E1 остаётся BLOCKED до появления execution host, который работает только с disposable fixtures. Это единственный текущий инфраструктурный стопор E1; доступный Desktop Commander device на момент проверки Offline.

### 14.5. Что остаётся у координатора

1. **A2 sync-only confirmation получено** на HEAD `f7fa3eca587c3a39a0d7c11804a8e9271657e0c5`; провести пакетную приёмку E2 benchmark PR #21 в согласованном synthetic-only scope.
2. После A3 sync-only review провести финальную проверку PR #16. Ни review, ни CI не дают автоматического разрешения на merge.
3. Разобрать A1-01 и safety boundary A1-04 совместно с E1; не обходить BLOCKED запуском прежних workflows.
4. Контролировать три новых E3 Issues #24–#26 через самостоятельные CLAIM и фактические доказательства.
5. V2.3/V2.4 не запускать до закрытия P1, принятия решения по P2 и отдельного security/readiness gate.

**Принцип работы:** исполнители начинают свободные задачи по CLAIM без ожидания координатора; аналитики проверяют точные HEAD и evidence; координатор принимает решения только там, где есть архитектурная зависимость, safety boundary или финальная приёмка.



## 15. Координаторская приёмка E2 — 2026-11-18

### 15.1. PR #21 принят и объединён

Координаторская проверка завершена после A2 sync-only review.

- PR [#21](https://github.com/yeatu/obsidianGP/pull/21) успешно объединён в `main`.
- Merge commit: `2bb84ea536e60605c33be3bb03f5a4da7dee30af`.
- Проверенный PR HEAD: `f7fa3eca587c3a39a0d7c11804a8e9271657e0c5`.
- Post-sync CI: [44184089775](https://github.com/yeatu/obsidianGP/actions/runs/44184089775) — success.
- Artifact: [14372014537](https://github.com/yeatu/obsidianGP/actions/runs/44184089775/artifacts/14372014537), digest `sha256:da59255fa8262aca8fbefc083060bf18ab65dad9a462d1906e015e347fb3b336`.
- A2 review [5947396014](https://github.com/yeatu/obsidianGP/pull/21#pullrequestreview-5947396014) подтвердил исправление P2, неизменность benchmark runner/corpus/tests/workflow после предыдущего review и отсутствие новых blocking findings.
- Benchmark: 12 synthetic nodes, 9 queries, 8/8 gated cases, 7 unit tests; recall@1 0.9167, recall@3 1.0000, precision@3 0.3889, MRR 1.0000; стабильность порядка 8/8, дубликатов 0.
- [Issue #18](https://github.com/yeatu/obsidianGP/issues/18) закрыта как completed.

Решение: **COORDINATOR_ACCEPTED_AND_MERGED** в пределах synthetic-only benchmark scope. Это не меняет runtime semantics lexical search и не разрешает расширять retrieval scope.

### 15.2. Остальные потоки

| Направление | Текущее состояние | Следующий координаторский шаг |
|---|---|---|
| E1 / Issue #17 / PR #22/#23 | BLOCKED: требуется execution host с disposable Vault/SQLite fixtures. | Не запускать real-Vault workflows. Проверять только после появления изолированного хоста. |
| E3 / PR #16 / V2.2 | Предыдущая приёмка non-production scope действительна; последний известный HEAD `d54173901543f6f2a2a1db3d3f774dd8842a89d8`, CI [44183680450](https://github.com/yeatu/obsidianGP/actions/runs/44183680450) успешен, A3 sync-only review [5947349629](https://github.com/yeatu/obsidianGP/pull/16#pullrequestreview-5947349629) завершён. | Повторно сверить текущий PR/base после merge E2. Не объединять автоматически: проверить актуальный diff allowlist и CI. |
| E3 / Issue #24 | OPEN | Проверить CLAIM и затем фактический PR по empty SourceSpan. |
| E3 / Issue #25 | OPEN | Проверить CLAIM и затем фактический PR по SnapshotRef TOCTOU. |
| E3 / Issue #26 | OPEN | Проверить CLAIM и затем фактический PR по facets completeness. |
| A1 / Issue #19 | RELEASED | Повторный аудит не нужен; findings остаются на координаторском контроле. |

### 15.3. Изменение приоритетов координатора

1. E2 benchmark больше не является открытым блокером: PR #21 merged, Issue #18 completed.
2. После merge PR #21 повторно проверить актуальный base PR #16; старое утверждение о синхронизации на `d541739` не считать автоматически актуальным.
3. Проверить открытые E3 Issues #24–#26 по реальному коду и PR evidence; не подменять реализацию повторным описанием задач.
4. E1 остаётся заблокированным на безопасном тестовом хосте. Никакие реальные данные не публиковать в публичных артефактах или комментариях.

**Последняя координаторская операция:** merge PR #21, commit `2bb84ea536e60605c33be3bb03f5a4da7dee30af`.

## 16. Кризисная координаторская стабилизация — 2026-11-18

Этот раздел supersedes устаревшие статусы раздела 15 и предыдущие упоминания PR #16 / #24–#29.

### 16.1. Завершённые приёмки и merge

| Область | Результат | Доказательства |
|---|---|---|
| E2 synthetic lexical benchmark | **MERGED** | PR [#21](https://github.com/yeatu/obsidianGP/pull/21), merge 2bb84ea536e60605c33be3bb03f5a4da7dee30af; Issue #18 completed; CI 44184089775 success. |
| E3 empty SourceSpan | **MERGED** | PR [#27](https://github.com/yeatu/obsidianGP/pull/27), merge 4b71425f093a99882f08738e6d6243228d98416b; Issue #24 completed; C1/V2.1 fixture tests passed and manifest-pinned E1→E2→E3 integration run 44192658977 success. |
| E3 SnapshotRef TOCTOU | **MERGED** | Включено в PR [#30](https://github.com/yeatu/obsidianGP/pull/30); Issue #25 completed. Operation-boundary verification before/after E1/E2 calls, path/HEAD/branch/clean-tree/manifest/SQLite digest revalidation, fail-closed snapshot_changed. |
| E3 facets completeness | **MERGED** | Включено в PR [#30](https://github.com/yeatu/obsidianGP/pull/30); Issue #26 completed. Unsupported facets теперь not_evaluated, warning diagnostic и SearchBatch.complete=false, с E2→E3→B1 regression. |
| E3 contract integration | **MERGED** | PR [#30](https://github.com/yeatu/obsidianGP/pull/30), merge 1712ef3347c3c577dd4c2c2218c277a2b75bad1b. CI on exact HEAD dc01d2cc4b1a7e89b993ea3ad1be3dc6c3c0f5f9: B1 45, C1 66, V2.1 18 passed; dependency/import guard passed; real manifest-pinned integration 44193376053 success. Artifact 14377518167 contains aggregate report only; no source text. |
| E3 V2.2 non-production Issue core | **MERGED** | PR [#16](https://github.com/yeatu/obsidianGP/pull/16), merge 05a067e1348b2871e403159f060d49b61d4fef7d; Issue #15 completed. Independent Analyst 3 review and coordinator acceptance; CI 44183680450: 45 B1 + 56 C1 + 18 V2.1 + 55 V2.2 = 174 tests; dependency/import guard passed. |

PR #28 and PR #29 were closed as superseded after their changes were consolidated into PR #30. No code from those stale branches was merged. Current main HEAD after the above merges: 05a067e1348b2871e403159f060d49b61d4fef7d.

### 16.2. Remaining blockers

| Направление | Статус | Решение |
|---|---|---|
| E1 / Issue #17 / PR #22/#23 | **BLOCKED** | Existing E1 workflows index the real Vault / production sidecar. No rerun of those workflows until disposable Vault + SQLite execution host or an approved fixture-only test route exists. PR #22/#23 remain open; tests have not been accepted. |
| E3 V2.3/V2.4 | **NOT STARTED / FROZEN** | Do not begin transport, event triggers, recovery, GitHub writes, credentials, MCP/HTTP or deployment until a separate readiness review and explicit scope approval. |
| E3 PR #12 | **PROPOSAL ONLY** | GitHub Issue Worker and Recovery proposal remains unimplemented; do not treat it as a running agent. |
| A1 / Issue #19 | **RELEASED** | Audit completed; findings A1-01…A1-05 triaged into accepted fixes or E1 blocker. No repeat audit needed. |

### 16.3. Coordinator's operational decision

1. E2 benchmark and E3 V2.2 are now in main; do not reopen them absent a regression.
2. Issues #24, #25, #26 and #15 are closed as completed.
3. PR #28/#29 are closed as superseded; use PR #30 as the canonical implementation history for #25/#26.
4. E1 is the only remaining implementation blocker in the current approved scope. It is an environment/evidence blocker, not a lack of assigned work.
5. Do not mistake the successful read-only manifest-pinned integration run for permission to run the E1 indexer against the production Vault. The former validated E3 reads; the latter mutates/indexes production state and remains blocked.
6. V2.3/V2.4 remain frozen. The V2.2 merge does not authorize production GitHub transport or source-content publication.

**Координаторская точка восстановления:** main HEAD 05a067e1348b2871e403159f060d49b61d4fef7d; E2 benchmark, E3 contract fixes and V2.2 non-production core accepted and merged. Единственный текущий стопор — E1 fixture-only execution environment.
