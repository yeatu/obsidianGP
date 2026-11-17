# SFRA Search: локальный поисковый индекс

Автономный поисковый модуль для этапа 2 SFRA. Хранит производный индекс отдельно от Vault, использует SQLite FTS5 и возвращает оригинальный `raw_text` вместе с адресом и версией источника. Модуль не разбирает Markdown, не создаёт Node ID, не строит граф знаний и не формирует Context Pack.

## Требования

- Python 3.11 или новее.
- SQLite с поддержкой FTS5 (проверяется командой `sfra init`).
- `pymorphy3` и русский словарь `pymorphy3-dicts-ru` — основной морфологический механизм.
- NLTK — локальный резервный Snowball stemmer, если `pymorphy3` недоступен. При создании индекса выбранный движок записывается в `index_meta`; нельзя незаметно открыть БД другим нормализатором.

## Установка

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Либо:

```bash
python -m pip install -r requirements-dev.txt
python -m pip install -e . --no-deps
```

## Быстрый запуск

Все команды ниже выполняются из каталога `Реализация`. По умолчанию БД находится в `.ai-index/sfra-search.sqlite3`; этот каталог не должен находиться внутри сканируемого набора Markdown-файлов. Путь можно изменить через глобальный параметр `--db`, который указывается **до подкоманды**.

```bash
sfra init
sfra import-nodes --jsonl fixtures/nodes.sample.jsonl --manifest fixtures/import-manifest.json
sfra search "18 518"
sfra search "Генрих Фауст"
sfra show node_00421
sfra check
```

Эквивалентно запуску через модуль: `python -m sfra_search --db PATH ...`.

## Импортный контракт

JSONL: одна запись Node v1 на строку. Обязательные поля:

```json
{
  "node_id": "node_00421",
  "source_path": "персонажи/Генрих Фауст.md",
  "node_type": "section",
  "parent_node_id": "node_00012",
  "heading_path": ["Поведение", "Конфликтное поведение"],
  "line_start": 310,
  "line_end": 337,
  "content_hash": "sha256:<64 lowercase hex characters>",
  "raw_text": "Оригинальный текст структурного узла"
}
```

`content_hash` обязан быть SHA-256 по точным UTF-8 байтам `raw_text`, без нормализации и обрезки. Опциональный `document_hash` — SHA-256 полного Markdown-файла; его нельзя вычислить из одного структурного узла, поэтому при отсутствии поле хранится и возвращается как `null`. Координаты строк начинаются с 1, `line_end` включителен. `source_path` — нормализованный относительный POSIX-путь от корня Vault с `/`.

Если нужен импорт с удалением, передайте отдельный manifest:

```json
{
  "schema": "sfra-node-batch/v1",
  "mode": "replace_documents",
  "replace_source_paths": ["персонажи/Генрих Фауст.md"],
  "deleted_node_ids": []
}
```

Режимы:

- `delta`: только upsert и явные `deleted_node_ids`; отсутствие узла в пакете ничего не удаляет.
- `replace_documents`: пакет содержит полный набор узлов для `replace_source_paths`; отсутствующие в нём узлы перечисленных документов помечаются удалёнными.
- `full_snapshot`: аналогичная замена для явно перечисленного `managed_source_paths`.

Входные узлы и manifest полностью валидируются до транзакции. Любая ошибка во время записи откатывает весь пакет.

## CLI

| Команда | Назначение |
|---|---|
| `sfra init` | Создать схему и проверить поддержку FTS5. |
| `sfra import-nodes --jsonl FILE [--manifest FILE]` | Импорт Node v1 JSONL. |
| `sfra update --jsonl FILE [--manifest FILE]` | Инкрементальное обновление. |
| `sfra search "запрос" [--entity NAME] [--limit N]` | Лексический, морфологический, числовой и опциональный entity search. |
| `sfra search-entity "имя" [--limit N]` | Поиск по подтверждённой сущности/алиасу. |
| `sfra show NODE_ID [--hash CONTENT_HASH]` | Текущая или конкретная историческая версия. |
| `sfra load-entities --config FILE` | Загрузить явный реестр сущностей из JSON. |
| `sfra confirm-alias --entity-id ID --alias TEXT` | Подтвердить алиас и перестроить текущие упоминания. |
| `sfra reject-alias --entity-id ID --alias TEXT` | Отклонить алиас и удалить его текущие упоминания. |
| `sfra list-aliases --entity-id ID` | Показать статусы алиасов. |
| `sfra list-candidates [--limit N]` | Показать неподтверждённые кандидаты из имён файлов, заголовков и повторяющихся именных последовательностей. |
| `sfra check` | Проверить целостность SQLite, текущие FTS-записи и ссылки на версии. |

## Одноразовый запуск в GitHub Actions с индексом Исполнителя 1

Для штатного сценария не требуется постоянная поисковая БД или сервер. Команда `run-once`:

1. открывает структурную БД Исполнителя 1 в режиме SQLite `mode=ro`;
2. читает только текущие узлы активных документов со статусом `active` и без `stale_generation`; узлы `ambiguous`, `stale`, `deleted` и узлы удалённых документов не импортируются;
3. проверяет сохранённые Исполнителем 1 `node_id`, `content_hash` и SHA-256 точного UTF-8 `raw_text`; отсутствующие идентификаторы не генерирует;
4. создаёт производный FTS5/Entity Registry индекс в общей in-memory SQLite базе;
5. выполняет поиск и печатает JSON-результат; при завершении процесса временная поисковая БД исчезает.

Пример локального вызова, эквивалентного шагу GitHub Actions:

```bash
python -m pip install -e ".[dev]"
sfra run-once \
  --source-db "$RUNNER_TEMP/sfra-search-index/structure.sqlite3" \
  --query "остановка кровообращения" \
  --limit 20
```

Поиск по сущности и подключение конфигурации Entity Registry:

```bash
sfra run-once \
  --source-db "$RUNNER_TEMP/sfra-search-index/structure.sqlite3" \
  --query "" --entity "Генрих Фауст" \
  --entity-config config/entities.example.json
```

Каждый hit сохраняет `node_id` и `content_hash` исходного структурного индекса. Следующий одноразовый шаг может адресно получить точный `raw_text`, координаты и `document_hash` из той же БД:

```bash
sfra get-source \
  --source-db "$RUNNER_TEMP/sfra-search-index/structure.sqlite3" \
  --node-id "node_..." \
  --content-hash "sha256:..."
```

Тот же интерфейс доступен как Python API: `search_structural_database(...)`, `load_current_nodes(...)` и `get_source_node(database_path, node_id, content_hash)`. Исходная структурная БД не изменяется; FTS5 не дописывается в неё и не сохраняется между запусками. Аргумент `--db` глобальной CLI-конфигурации для `run-once` не используется, отдельный файл поисковой БД не создаётся.

В интеграционном workflow Исполнителя 2 структурную БД **не следует создавать заново**. Workflow получает `state/structure.sqlite3` и `state/manifest.json` из ветки `sfra-state`, сверяет SHA-256, версию схемы и соответствие исходному commit, после чего передаёт существующую БД команде `run-once`. Исполнитель 2 не запускает `index_vault` и не изменяет ветку состояния. Для автономных тестов можно использовать искусственную SQLite-фикстуру. Фактическая проверка этого сценария: [успешный Actions run](https://github.com/yeatu/obsidianGP/actions/runs/43997334585).

## Сущности и алиасы

Пример конфигурации находится в `config/entities.example.json`. Каноническое имя автоматически становится подтверждённым алиасом. Алиасы из списка строк загружаются со статусом `candidate`; они **не** участвуют в `search_entity` до явного подтверждения.

```bash
sfra load-entities --config config/entities.example.json
sfra list-aliases --entity-id character_daphne
sfra confirm-alias --entity-id character_daphne --alias "Дафна"
sfra search-entity "Дафна"
sfra reject-alias --entity-id character_daphne --alias "ошибочный вариант"
```

Один алиас может быть подтверждён для нескольких Entity ID. В таком случае `search_entity` возвращает все ID и `ambiguous: true`, а не выбирает сущность за пользователя. Таблица `entity_sources` — единственное место хранения роли `primary_document`; отдельной копии `primary_source_path` в `entities` нет.

Кандидаты автоматически собираются как подсказки из basename документа, заголовков и повторяющихся фрагментов из 2–3 слов с заглавными буквами. Это исключительно неподтверждённые кандидаты. Автоматического объединения или подтверждения сущностей нет.

## Поиск и ранжирование

1. FTS5 exact-channel ищет оригинальные формы только в оригинальных полях имени документа, пути, заголовков и текста.
2. Morph-channel ищет леммы/основы только в отдельных производных полях. Каналы FTS разделены, поэтому морфологическое совпадение не маскируется под точное. При установленном `pymorphy3` используется его русский словарь; при недоступности — NLTK Snowball Russian stemmer как резерв.
3. Числа изымаются из обычного FTS-выражения и ищутся по точным ключам в исходном тексте, имени документа, пути и заголовках. `18 518`, `18 518`, `18 518` и `18518` дают одинаковый ключ `18518`; `118518` и `185180` — другие значения. Десятичные значения хранятся строковым точным представлением `Decimal`, не binary float.
4. Пользовательский текст никогда напрямую не передаётся в грамматику FTS5. Запрос разбирается на токены, каждый токен заключён в кавычки; служебные операторы пользователя остаются обычными словами.
5. Ранжирование: entity exact → document title → heading → exact word/number/phrase → morphology → неполное OR-совпадение. BM25 используется только как вторичный порядок внутри tier. В SQLite FTS5 меньшее значение BM25 лучше; сортировка по BM25 выполняется по возрастанию. При равенстве применяются `source_path`, `line_start`, `node_id` по возрастанию.
6. Зоны Vault и авторские заметки не меняют релевантность.

Обычный поиск соединяет FTS/числовые результаты только с `nodes.current_version_id`, поэтому устаревшие версии не возвращаются. `show --hash` позволяет получить конкретную историю. Выдача содержит оригинальный текст узла, а не лемматизированное поле.

## Программный интерфейс

```python
from sfra_search import SFRAIndex, calculate_content_hash

index = SFRAIndex(".ai-index/sfra-search.sqlite3")
index.import_nodes(nodes, manifest={"mode": "delta"})
response = index.search("Особенности речи Генриха Фауста", entities=["Генрих Фауст"], limit=20)
entity_response = index.search_entity("Дафна Гринграсс", limit=20)
node = index.get_node("node_00421")
index.confirm_alias("character_daphne", "Дафна")
index.reject_alias("character_daphne", "сомнительный алиас")
index.close()
```

Метод `update_index(...)` является алиасом `import_nodes(...)`. `get_node(node_id, content_hash)` возвращает полный `raw_text` выбранной версии, `index_generation` и `document_hash`; он не возвращает поисковый `excerpt`. Дополнительный метод `mentions_for_entity(...)` возвращает карту подтверждённых упоминаний. В `search_entity` явно назначенный документ роли `primary_document` возвращается первым; это навигационная настройка, а не оценка каноничности.

## Тесты

```bash
python -m pytest
```

Тестовый набор не зависит от Исполнителя 1 и использует искусственные Node v1-данные. Он покрывает импорт/повторный импорт/версии, текущие и исторические версии, точные слова и числа, словоформы и глаголы, имена и заголовки, алиасы/неоднозначность, несколько путей с одинаковым basename, delta/replace/delete, rollback, безопасность FTS-запроса и сохранение оригинального текста.

## Контракт для следующего компонента

Формат поискового попадания включает `node_id`, `source_path`, `heading_path`, координаты, `content_hash`, `excerpt`, `match_type`, `match_reasons` и `relevance` с `tier` 1–6 и числовым `bm25`. `excerpt` является только подсказкой поиска. Для постоянной локальной БД следующий компонент вызывает `get_node(node_id, content_hash)`. В одноразовом Actions runtime временная БД закрывается после получения результата, поэтому исходник извлекается по той же паре из сохраняемой SQLite Исполнителя 1 через `get_source_node(...)` / `sfra get-source`. В обоих случаях возвращается полный `raw_text`, а не `excerpt`. Значения `bm25` сортируются по возрастанию внутри одного tier.

**Интеграционный блокер:** текущий Node v1 от Исполнителя 1 не содержит обязательного для схемы Исполнителя 3 `document_hash`. Модуль принимает его как опциональное расширение и честно возвращает `null`, если поле не передано. Нельзя подделывать хеш полного документа по одному узлу. До интеграции Исполнители 1 и 3 должны согласовать передачу/nullable-правило для этого поля.

## Статусы источников и фактическая интеграционная проверка

Structural adapter соблюдает принцип active-only:

- load_current_nodes() импортирует только строки, у которых документ active, узел active и stale_generation IS NULL.
- get_source_node() применяет тот же фильтр при адресном получении по node_id + content_hash.
- ambiguous, stale, deleted и узлы удалённых документов не попадают в FTS и не возвращаются как оригинальные источники.
- Если active-узел ссылается на ambiguous или stale родителя, parent_node_id возвращается как null; это не блокирует получение самого active-узла.
- Отсутствующий document_hash остаётся null. Хеш узла content_hash не используется вместо SHA полного документа.
- E2 не разрешает неоднозначность и не изменяет статусы или идентификаторы в SQLite E1.

## Fixture-тесты и интеграция E2

Итоговый PR run: https://github.com/yeatu/obsidianGP/actions/runs/44010014722

На Python 3.13 в пересобранном архивном пакете выполнено **64 passed, 0 failed, 0 errors, 0 skipped**. Искусственные SQLite fixtures проверяют active / ambiguous / stale / deleted, stale_generation, удалённый документ, пустую выдачу, отсутствие ID у ambiguous-узла, null document_hash, скрытие ambiguous parent_node_id, read-only получение источников и CLI parser.

Отдельно выполнен real-Vault сценарий на актуальном manifest E1; workflow предварительно пересобрал архивный пакет и наложил канонический active-only structural.py:

- E2 tested commit: 78466b6dc400f96f2821391434553bc1e3a2326b.
- E1 state branch SHA: fb0b45ae0e5043e342c790d43e2b341ca65d7f2b.
- SHA-256 manifest: sha256:3d5eacf5fc2f7f927af8f591f317ea95d56d0c0f53de1bc61cb54d23677fd072.
- SHA-256 SQLite: sha256:2a6d792d5e5c458ffa87df32a082229fc548c42dab2d91a5cc8fa1195bcf6674.
- SQLite PRAGMA integrity_check: ok; schema 2.
- 66 документов, 9 080 active-узлов; в этом снимке E1 ambiguous/stale/deleted узлов и удалённых документов не было.
- pymorphy3 2.0.6: формы «реанимации» и «реанимацию» нормализованы к «реанимация»; оба запроса вернули три одинаковые пары node_id + content_hash.
- Три источника получены через get-source; SHA-256 каждого raw_text совпал с content_hash.
- SHA набора файлов Vault до и после совпал; структурная SQLite и HEAD sfra-state не изменились.
- Дополнительный постоянный файл поисковой SQLite не создавался.

**Разделение доказательств:** сценарии с реальными ambiguous/stale/deleted записями покрыты только fixtures, потому что актуальный E1 snapshot не содержит таких строк. Real-Vault тест подтверждает active-only выдачу фактических результатов и успешное получение оригинальных активных источников. Он не утверждает, что в production snapshot были реальные ambiguous-узлы, которые удалось отбросить.

PR для независимой проверки: https://github.com/yeatu/obsidianGP/pull/7. В main изменения не влиты.

### API for Executor 3

The search adapter contract deliberately separates search hints from source retrieval:

- search() returns a bounded excerpt with node_id, source_path, heading_path, line coordinates, content_hash, match_type, match_reasons, and relevance with tier and bm25.
- get_node(node_id, content_hash) returns the complete, exact-version raw_text, plus index_generation and document_hash. It never returns excerpt in place of source text.
- document_hash is null when absent from the importer payload. It is not fabricated from one structural node. The E1 structural index supplies the whole-document SHA-256 as documents.source_sha256 in the tested integration snapshot.

