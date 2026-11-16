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
