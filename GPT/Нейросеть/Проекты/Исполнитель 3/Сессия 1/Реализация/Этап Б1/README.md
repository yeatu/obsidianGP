# SFRA Context Builder — Этап Б1

Независимое ядро сборки Context Pack. Пакет не импортирует GitHub Actions, MCP SDK, E1/E2 runtime или SQLite.

## Состав

- нормализация и валидация SearchRequest / SearchBatch;
- SHA-256 точных UTF-8 байтов каждого raw_text;
- дедупликация только по Node ID + Content Hash;
- обнаружение конфликтующих версий одного Node ID;
- детерминированное ранжирование;
- разрешение required_with / parent_context_required через узкий DependencyResolver;
- SCC для циклов и неделимые dependency groups;
- Known, Version Changes, Coverage и Parallel Sources;
- атомарное бюджетирование целых узлов/групп без усечения;
- Context Pack по контракту Этапа А.

## Установка и тесты

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

Для подсчёта используется только `tiktoken==0.14.0`, encoding по умолчанию `o200k_base`. Если пакет/кодировка недоступны, инициализация TokenCounter завершается явной ошибкой. Молчаливого fallback на длину строки нет.

## API

```python
from sfra_context_builder import ContextBuilder, TiktokenCounter

builder = ContextBuilder(token_counter=TiktokenCounter("o200k_base"))
pack = builder.build(request_json, search_batch_json)
```

Для разрешения отсутствующих обязательных узлов передаётся объект с методом:

```python
resolve_node(node_id: str, snapshot: SnapshotRef) -> Mapping | None
```

При использовании resolver параметр `snapshot` обязателен. Resolver должен читать только закреплённую пару source/sidecar commit. Ядро не открывает SQLite и не выбирает ветки само.

## Границы Б1

В этом этапе нет SearchAdapter к E2, SourceReader/read_source, GitHub Issue worker, recovery workflow и end-to-end. Эти компоненты подключаются отдельно после приёмки ядра.
