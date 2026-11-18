# Локальный SFRA MCP server

Статус: локальная композиция E1/E2/B1/E3 и stdio tool interfaces по Issue #38. Процесс read-only; единственный транспорт stdio.

## Требования и установка

Требуется Python 3.11 или новее. Пакеты проекта устанавливаются из соответствующих каталогов монорепозитория:

~~~bash
E1_DIR="GPT/Нейросеть/Проекты/Исполнитель 1/Сессия 1/Реализация"
E2_DIR="GPT/Нейросеть/Проекты/Исполнитель 2/Сессия 1/Реализация/source"
B1_DIR="GPT/Нейросеть/Проекты/Исполнитель 3/Сессия 1/Реализация/Этап Б1"
INTEGRATION_DIR="GPT/Нейросеть/Проекты/Исполнитель 3/Сессия 1/Реализация/Этап В1"
MCP_DIR="GPT/Нейросеть/Проекты/Исполнитель 3/Сессия 1/Реализация/Локальный MCP"

python -m pip install -e "$E1_DIR"
python -m pip install -e "$E2_DIR"
python -m pip install -e "$B1_DIR"
python -m pip install -e "$INTEGRATION_DIR"
python -m pip install -e "$MCP_DIR"
~~~

Для запуска тестов установите последнюю зависимость через "$MCP_DIR[test]" вместо "$MCP_DIR". MCP SDK закреплён как mcp==2.3.0; typing-extensions объявлен явно для Python 3.11 TypedDict schemas. E1/E2/B1/integration imports берутся из локальных package roots, а не копируются в MCP package.

## Конфигурация

До запуска задаются три обязательные переменные окружения:

- SFRA_SIDECAR_ROOT: абсолютный путь к корню локального sidecar Git checkout, содержащему state/manifest.json и state/structure.sqlite3.
- SFRA_VAULT_GIT_ROOT: абсолютный путь к корню локального Git checkout Vault.
- SFRA_VAULT_SUBDIR: непустой относительный путь к каталогу Vault внутри SFRA_VAULT_GIT_ROOT (например, ГП).

Сначала проверяется форма путей. Затем composition root вызывает E1 verify_state_directory через E3 bind_pinned_snapshot, который проверяет Git checkouts, branch, manifest и SQLite digest, и создаёт один активный PinnedSnapshot. На любой ошибке composition запуск завершается fail-closed. Путь к SQLite открывается только уже существующими E1/E2/E3 services; MCP не выполняет собственные SQL-запросы.

## Состав сервисов и SnapshotRef

Composition root связывает E1 read_source_scope / resolve_current_node через их публичный Python API, E3 E1SourceReader, E2 E2SearchAdapter, B1 ContextBuilder, E3 ContextIntegrationPipeline и SearchVaultService. Все компоненты используют один и тот же pinned snapshot.

Публичная identity состоит из vault_commit_sha, sidecar_commit_sha и manifest_sha256; snapshot_id является их производным значением. MCP caller переносит identity из ответа поиска в запрос чтения, а сервер не подменяет старый snapshot текущим.

ReadSourceService намеренно не создаётся в runtime composition. Подключение read_source заблокировано координатором до независимой проверки и C acceptance для #36/#51. Сам зарегистрированный tool slot пока возвращает явную ошибку и не вызывает E1.

## MCP tools и граница child issues

Регистрируются ровно две согласованные схемы: search_vault и read_source. Их регистрации являются закрытыми handler slots, которые явно отказывают в вызове до установки реализаций из child Issues #39 и #40. Неизвестные поля исключаются SDK schema, а child handlers обязаны выполнять дополнительную строгую проверку через application contracts.

Эта поставка не включает HTTP/SSE/WebSocket, GitHub API, credentials, worker/recovery, произвольный файловый доступ, write tools или source text в логах. stdout зарезервирован под MCP protocol; startup diagnostics пишутся в stderr.

## Запуск

После установки пакетов и задания переменных окружения:

~~~bash
sfra-mcp
# или
python -m sfra_mcp_server
~~~

CLI строит verified search service graph до запуска stdio server. Ошибка конфигурации или composition завершает процесс с кодом 2; удалённый transport API не предоставляется.
