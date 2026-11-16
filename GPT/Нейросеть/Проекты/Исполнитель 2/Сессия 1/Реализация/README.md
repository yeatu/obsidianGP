# SFRA Search — функциональный прототип Исполнителя 2

В этой папке находятся архитектурная основа, архив исходного кода, инструкции и фактический отчёт о проверке.

## Состав публикации

- `Проектное решение.md` — архитектурное решение Этапа А.
- `sfra-search-prototype.tar.xz.part00` … `part05` — шесть частей одного архива с исходниками и тестами.
- `README.md` — этот файл.
- `Результат.md` — сводка реализации, тестов и ограничений.
- `Уточнения после аналитической проверки.md` — решения по замечаниям аналитика и совместимости с Executor 3.

Архив содержит Python-пакет `sfra_search`, зависимости, миграции/схему SQLite, Node v1 JSON Schema, JSONL фикстуры, конфигурацию сущностей, CLI, README, отчёт и pytest-тесты. Рабочая SQLite-база и кэши Python в архив не включены.

## Сборка архива из частей

Части — бинарные фрагменты одного файла. Скачайте все шесть файлов в одну папку, не меняя имена и порядок.

Linux / macOS:

```bash
cat sfra-search-prototype.tar.xz.part00 sfra-search-prototype.tar.xz.part01 sfra-search-prototype.tar.xz.part02 sfra-search-prototype.tar.xz.part03 sfra-search-prototype.tar.xz.part04 sfra-search-prototype.tar.xz.part05 > sfra-search-prototype.tar.xz
tar -xJf sfra-search-prototype.tar.xz
```

Windows CMD:

```bat
copy /b sfra-search-prototype.tar.xz.part00+sfra-search-prototype.tar.xz.part01+sfra-search-prototype.tar.xz.part02+sfra-search-prototype.tar.xz.part03+sfra-search-prototype.tar.xz.part04+sfra-search-prototype.tar.xz.part05 sfra-search-prototype.tar.xz
tar -xJf sfra-search-prototype.tar.xz
```

## Установка и первый запуск

После распаковки перейдите в корень распакованного проекта:

```bash
python -m pip install -e ".[dev]"
sfra init
sfra import-nodes --jsonl fixtures/nodes.sample.jsonl --manifest fixtures/import-manifest.json
sfra search "18 518"
sfra search "Генрих Фауст"
sfra show node_00421
sfra check
python -m pytest -q
```

Требуется Python 3.11+ и SQLite с FTS5. Инициализация проверяет FTS5 явно. Основной морфологический путь — pymorphy3 с русским словарём. Если pymorphy3 недоступен при установке, пакет использует резервный NLTK Snowball и записывает выбранный движок в метаданные базы.

## Результаты локальной проверки

- `python -m pytest -q`: **47 passed**.
- `python -m compileall -q src tests`: успешно.
- CLI smoke test: init → импорт трёх искусственных Node v1 узлов → поиск `18 518` → `sfra check`; проверка БД сообщает `integrity=ok`, отсутствующих FTS-записей — 0, потерянных ссылок на текущую версию — 0.
- Фактический прогон использовал NLTK Snowball fallback: среда не имела доступа к PyPI и не смогла установить pymorphy3.
- Тестовые данные искусственные. Реальный экспорт Исполнителя 1 и полный Vault не импортировались.

## Интерфейс для Executor 3

`search()` возвращает поисковый hit с ограниченным `excerpt`. Это не первоисточник. Для получения точной версии следующий компонент вызывает `get_node(node_id, content_hash)`, который возвращает полный `raw_text`, координаты, `index_generation` и `document_hash`.

Если источник не передал SHA-256 всего Markdown-документа, `document_hash` будет `null`. Хеш структурного узла нельзя выдавать за хеш всего документа. Контракт Executor 1 / Executor 3 требует согласовать передачу этого поля либо разрешить null до появления экспорта целого документа.

**Статус:** функциональный автономный прототип опубликован для независимой проверки аналитиком. Задание не объявляется окончательно принятым до проверки аналитиком, теста штатного пути pymorphy3 и интеграции с реальным экспортом структурного индексатора.
