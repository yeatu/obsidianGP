# E1 Source Scope API — contract audit (Issue #17)

**Дата:** 2026-11-17  
**Основа аудита:** `main` `cb86417e1b8f2870b7e71c1ae5dbb1e3eea1b8b2`  
**Результат:** обнаружен дефект проверки Node ID provenance; добавлено fail-closed исправление и регрессионные тесты. Runtime PR передаётся координатору, merge не выполняется.

## Область и ограничения

Проверены публичные `read_source_scope()` и `resolve_current_node()`, модели результатов, SQLite snapshot preflight, lifecycle resolver, event validation, безопасное открытие source path и текущие тесты E1/V2.1.

Не менялись SQLite schema v2, storage/persistence workflow, GitHub workflows, `sfra-state`, production SQLite и файлы Vault. Индексатор не запускался на production Vault. Тестовые фикстуры используют временные Vault/SQLite.

## Матрица контрактов

| Инвариант | Существующее покрытие / результат аудита | Дополнение в этом PR |
|---|---|---|
| Opaque `snapshot_id` echo в каждом scope и resolver result | `test_read_source_scope_supports_all_four_modes_with_one_snapshot`, `test_resolve_current_node_returns_current_address_and_echoes_snapshot_id` | Контракт оставлен неизменным; E1 не валидирует Git/manifest SnapshotRef |
| Snapshot echo mismatch отвергается consumer layer | V2.1 содержит `test_read_source_service_rejects_snapshot_echo_mismatch`; ответственность не переносится в E1 | V2.1 тест не запускался в этом прогоне |
| Ambiguous anchor не возвращает source text | `test_source_scope_rejects_ambiguous_anchor_without_partial_data` параметризован по четырём scope | Добавлен отдельный тест ambiguous-ветви `resolve_current_node()` |
| Deleted/stale node/document не возвращает partial content | `test_stale_node_is_reported_as_deleted_address`, `test_deleted_document_is_reported_without_opening_markdown`, `test_source_scope_rejects_deleted_document_without_partial_data` | Добавлены проверки provenance/generation для event lifecycle |
| Expected Content Hash mismatch | `test_wrong_expected_hash_is_stale_and_does_not_return_node`, `test_source_scope_wrong_expected_hash_returns_no_partial_fragments` | Без изменения публичного контракта |
| Stored raw_text / version hash integrity | `test_tampered_sqlite_raw_text_is_integrity_error`, DB-only deleted-state hash tests | Без изменения публичного контракта |
| Node ID связан с событием актуального поколения | **Найден дефект:** активная строка с валидным, но подменённым Node ID могла пройти preflight без соответствующей event history | Добавлена обязательная связь current Node ID ↔ latest lifecycle event и точное generation match |
| Unsafe source path и symlink traversal | `test_path_escape_in_database_is_integrity_error`, `test_symlink_source_is_rejected`, race/replacement test | Добавлены формы absolute/drive/backslash/repeated separator/dot/NUL и symlinked parent directory |
| SQLite integrity / foreign keys | Полный `PRAGMA integrity_check` и `foreign_key_check` выполнялись в preflight; отдельного FK regression не было | Добавлен fail-closed тест foreign-key violation |
| Одна read transaction и один source-file read | `test_each_source_scope_uses_one_connection_transaction_and_one_file_read` | Без изменения |
| Нет partial source text в error envelope | `_assert_empty_scope_failure` используется для существующих negative scope tests | Новые negative tests проверяют пустые fragments и отсутствие raw text |
| SQLite/Vault read-only | `test_source_scope_and_resolver_do_not_modify_sqlite_or_vault` и legacy read-only test | Production storage не использовался |

## Найденный дефект и исправление

`_check_db_snapshot()` ранее допускал `latest_event is None` для активного узла. При изменении `structural_nodes.node_id` на другой синтаксически валидный UUID история `node_match_events` могла остаться привязана к старому ID. Текущий node row и его node_versions при этом не содержат независимого сравнения node_id; resolver мог вернуть новую адресацию как `ok`.

Исправление:
- активный/ambiguous узел обязан иметь matching event в текущем document generation;
- тип события должен согласовываться с lifecycle status;
- stale/deleted узел обязан иметь последнее событие в `stale_generation` и допустимого lifecycle type;
- нарушение приводит к `INTEGRITY_ERROR`, без source read и без partial address/content.

Публичные сигнатуры, поля result types, opaque snapshot semantics и schema v2 не изменялись.

## Добавленные регрессионные тесты

В `tests/test_lookup.py` добавлены проверки:
- Node ID подменён, event history осталась на старом ID: Source Scope и resolver fail closed;
- current event generation не соответствует документу;
- resolver отвергает ambiguous exact ID;
- семь небезопасных форм source_path;
- symlink на родительский каталог;
- SQLite foreign-key violation выявляется до открытия source.

## Запуск тестов и ограничения воспроизводимости

**В этом аудиторском прогоне новые и полные E1/V2.1 тесты не запускались.** Причина намеренная: существующие PR workflows, срабатывающие на изменения в E1 implementation tree, запускают индексатор на реальном Vault; Issue #17 прямо запрещает такой запуск. GitHub integration в текущем окружении не предоставляет безопасный workflow_dispatch для E1 test job, а менять workflows запрещено задачей.

Команды для воспроизведения в изолированном окружении без production Vault:
```bash
cd "GPT/Нейросеть/Проекты/Исполнитель 1/Сессия 1/Реализация"
python -m pip install -e . -r requirements-dev.txt
python -m pytest -q tests/test_lookup.py
```

V2.1 consumer contract suite:
```bash
python -m pytest -q "GPT/Нейросеть/Проекты/Исполнитель 3/Сессия 1/Реализация/Этап В2.1/tests"
```

Предыдущие результаты E1 CI на уже принятом коде не считаются результатом запуска этих новых тестов. Утверждение о passing для текущего PR не делается.

## Изменённые файлы

- `sfra_indexer/lookup.py` — fail-closed lifecycle event binding.
- `tests/test_lookup.py` — изолированные regression/contract tests.
- `09_Аудит_Source_Scope_API_Issue_17.md` — этот отчёт.

**Текущее решение:** runtime contract patch подготовлен в отдельной ветке и Draft PR. Остановка до координаторской проверки и организации безопасного прогона тестов. PR не объединён.
