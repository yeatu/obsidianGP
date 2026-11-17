# Этап 1: сохранение и восстановление SQLite через sfra-state

## Назначение

Этап реализует только постоянное состояние production-индекса между GitHub Actions runner. API адресного чтения узла и межзапусковой тест с отдельной sfra-state-test веткой являются следующими отдельными этапами.

## Архитектура

- Production-состояние хранится в настоящей orphan-ветке sfra-state.
- Ветка имеет независимый root commit без родителей.
- Допустимое дерево: README.md, state/structure.sqlite3 и state/manifest.json.
- Исходный Vault, исходный код и прочие файлы в state branch не публикуются.
- SQLite восстанавливается только после проверки manifest SHA-256, PRAGMA integrity_check, foreign_key_check и schema version.
- Создание снимка выполняется через sqlite3.Connection.backup(), после чего готовый файл повторно проверяется и хешируется.
- Manifest записывается атомарно и содержит формат, путь базы, SHA-256, версию схемы, source repository/branch/commit, workflow run ID и время снимка.
- Публикация использует workflow concurrency, проверку ожидаемого remote HEAD и обычный fast-forward push. Ветка не перезаписывается force push.

## Первичная инициализация

База не создаётся автоматически при отсутствующем состоянии. Первый запуск должен быть явно вызван через workflow_dispatch с initialize_state=true. Обычный push при ещё неинициализированном состоянии пропускает индексацию.

## Граница доступа

Отдельная orphan-ветка физически отделяет состояние от дерева Vault, но не ограничивает права чтения для пользователей с доступом к репозиторию. SQLite содержит raw_text и историю текста заметок.

## Проверки

Автоматические тесты в tests/test_state.py проверяют:
- создание и полную проверку manifest+SQLite snapshot;
- отказ при несовпадении SHA-256 manifest;
- отказ при повреждённой SQLite даже при обновлённом manifest hash;
- наличие committed WAL data в Backup API snapshot;
- fail-closed при отсутствии persisted state.

Межзапусковой A/B тест не входит в этот этап. Его тестовые база, fixture Vault и state branch должны быть изолированы от production sfra-state.

## Ограничения этапа

- Реализация API get_node_by_id(..., expected_hash) не входит в этот этап.
- Интеграционный тест двух независимых runner не входит в этот этап.
- Схема SQLite v2 и код этапов B/C не изменяются.


## Фактический результат реализации

**Коммит реализации:** \`d20c87ccf38981cff1388e002af0a6bcce06f477\`.

**Созданная production state-ветка:** \`sfra-state\`, root commit \`927e340b7ba2c60bab0edc2c6cfe15afbe138202\`. Git Data API подтвердил \`parents: []\`. Полное дерево root commit содержит только \`README.md\`. Workflow дополнительно повторно проверил orphan-root и allowlist на GitHub Actions.

### CI

- [Run 43980073213 — SFRA structural indexer stages B and C](https://github.com/yeatu/obsidianGP/actions/runs/43980073213): success; **28 passed in 1.55s**; CLI help прошёл; реальный Vault — 66 Markdown, 9 080 узлов, 21 Passage, 2 пустых документа; второй проход пропустил все 66 неизменённых документов; Git-проверка исходной папки Vault успешна.
- [Run 43980073444 — SFRA persistent SQLite state](https://github.com/yeatu/obsidianGP/actions/runs/43980073444): success; проверка checkout orphan-ветки и allowlist прошла; workflow корректно пропустил restore/index/snapshot/push, поскольку production state branch пока содержит только README и запуск не имел флага первичной инициализации.

### Промежуточный статус до production-проверки

На момент подготовки первоначальной версии этого отчёта рабочая SQLite ещё не была опубликована в `sfra-state`, а production restore/snapshot/push не выполнялся. Предыдущий запуск `43980073444` корректно пропустил эти шаги, поскольку не был вызван с `initialize_state=true`.

Этот раздел фиксирует историческое состояние. Неопределённость снята последующими production-запусками №4 и №5, результаты которых приведены ниже. Локальные тесты по-прежнему являются отдельным уровнем проверки и не подменяют фактический межзапусковой round-trip.

API `get_node_by_id(..., expected_hash)`, ветка `sfra-state-test` и отдельный интеграционный A/B-тест остаются вне границ этапа 1 Persistence и относятся к следующим отдельным этапам.

## Итоговая production-проверка между независимыми GitHub Actions runner

**Вердикт аналитика: этап 1 Persistence принят.** Полный production round-trip подтверждён двумя последовательными ручными запусками workflow `SFRA persistent SQLite state` на ветке `executor-1/sfra-indexer-session-1`. Оба запуска завершились со статусом `success`; все рабочие шаги workflow выполнены.

### Запуск №4 — первичная инициализация

[GitHub Actions run 43988013903](https://github.com/yeatu/obsidianGP/actions/runs/43988013903)

- Событие: `workflow_dispatch`; параметр `initialize_state=true`.
- Рабочая ветка: `executor-1/sfra-indexer-session-1`, исходный commit `4edb7707bee02604aa68066ca0e1ce1030f8ebfd`.
- Проверка настоящей orphan-истории `sfra-state` и allowlist завершилась успешно.
- Рабочая SQLite создана вне Vault, в каталоге runner temp.
- Проиндексировано 66 документов: 66 обработано, 0 пропущено; сохранено 9 080 структурных узлов и 21 Passage. В наборе 2 пустых документа.
- Создан снимок SQLite через Backup API, сформирован manifest, проверка состояния прошла успешно.
- SQLite и manifest опубликованы в `sfra-state`. Коммит публикации: [`a64b9039818f6cf7da2a42fbb339491a19ae626d`](https://github.com/yeatu/obsidianGP/commit/a64b9039818f6cf7da2a42fbb339491a19ae626d).

### Запуск №5 — восстановление сохранённого состояния

[GitHub Actions run 43988325234](https://github.com/yeatu/obsidianGP/actions/runs/43988325234)

- Событие: `workflow_dispatch`; параметр `initialize_state=false`.
- Запуск выполнен на новом независимом runner.
- Сохранённая SQLite восстановлена из `sfra-state`; проверка manifest и целостности завершилась успешно.
- Повторно проверено 66 документов: 0 переиндексировано, все 66 пропущены как неизменившиеся.
- После восстановления в индексе осталось 9 080 активных узлов, 21 Passage, 9 080 версий узлов и 9 080 событий сопоставления; статусы stale и ambiguous — 0.
- Повторный снимок и публикация manifest завершились успешно. Итоговый commit ветки состояния: [`8cb649e507d20ff39ef387402a1c97e642b14136`](https://github.com/yeatu/obsidianGP/commit/8cb649e507d20ff39ef387402a1c97e642b14136).

### Сверка состояния и неизменность Vault

| Проверка | Запуск №4 | Запуск №5 |
|---|---|---|
| SHA-256 `state/structure.sqlite3` | `2a6d792d5e5c458ffa87df32a082229fc548c42dab2d91a5cc8fa1195bcf6674` | `2a6d792d5e5c458ffa87df32a082229fc548c42dab2d91a5cc8fa1195bcf6674` |
| SQLite integrity / проверка состояния | Успешно | Успешно |
| Документы | 66 проиндексировано | 66 пропущено |
| Узлы | 9 080 | 9 080 сохранено |
| Passage | 21 | 21 |
| Изменения в исходной папке `ГП` | Не обнаружены | Не обнаружены |

Контрольная сумма SQLite совпала в manifest обоих запусков. Ветка `sfra-state` содержит `README.md`, `state/structure.sqlite3` и `state/manifest.json`; бинарная база и manifest присутствуют в опубликованном дереве. Исходные материалы Vault не изменялись.

**Итог:** сохранение production SQLite, восстановление на независимом runner и повторное использование прежнего состояния доказаны фактическими запусками №4 и №5. Этап 1 Persistence принят аналитиком. API адресного чтения и изолированная тестовая ветка `sfra-state-test` в этот этап не включались.


## Дополнение E1: явная фиксация источника Vault

Для последующих запусков источник заметок выбирается отдельно от ветки реализации. Workflow принимает параметр `vault_ref` (по умолчанию `executor-1/sfra-indexer-session-1`; переключения на `main` по умолчанию нет), делает отдельный checkout `vault/ГП` и фиксирует фактический SHA через `git rev-parse HEAD`.

Новые manifest сохраняют `vault_ref` и `vault_commit_sha`. Ключи `source_branch` и `source_commit` оставлены в качестве совместимых алиасов; чтение ранее созданных manifest, где присутствуют только старые ключи, поддерживается. Это дополнение не меняет SQLite schema v2 и не переписывает исторические результаты production round-trip выше.
