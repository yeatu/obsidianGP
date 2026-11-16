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

### Что ещё не подтверждено Actions

Рабочая SQLite ещё не опубликована в \`sfra-state\`, а production restore/snapshot/push пока не выполнялся. Это сознательное fail-closed поведение: первый запуск необходимо явно выполнить через GitHub Actions → **SFRA persistent SQLite state** → **Run workflow** с \`initialize_state=true\`. После этого обычные push запускают режим восстановления существующей базы.

Локальные тесты проверили backup из SQLite WAL, manifest hash, отказ при несовпадении контрольной суммы и отказ при повреждённой базе. Они не заменяют подтверждение полного production round-trip через GitHub branch.

API \`get_node_by_id(..., expected_hash)\`, ветка \`sfra-state-test\` и два независимых тестовых runner остаются следующими отдельными этапами.
