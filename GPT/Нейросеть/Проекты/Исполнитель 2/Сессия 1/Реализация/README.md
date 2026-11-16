# SFRA Search — Исполнитель 2

**Контрольная точка:** этап 1 дополнения координатора опубликован для проверки аналитиком. Одноразовый GitHub Actions workflow и полный прогон нового runtime на Vault относятся к этапу 2 и пока не заявляются выполненными.

## Состав

- `Проектное решение.md` — исходная архитектура.
- `sfra-search-prototype.tar.xz.part00` … `part06` — семь частей архива с исходным кодом и тестами.
- `README.md` — эта инструкция.
- `Результат.md` — подробный отчёт о текущем этапе, проверках и ограничениях.
- `Уточнения после аналитической проверки.md` — исторические заметки по предыдущему аудиту и API Executor 3.

## Сборка архива

Скачайте все семь частей в одну папку, сохранив имена и порядок.

Linux / macOS:

```bash
cat sfra-search-prototype.tar.xz.part00 sfra-search-prototype.tar.xz.part01 sfra-search-prototype.tar.xz.part02 sfra-search-prototype.tar.xz.part03 sfra-search-prototype.tar.xz.part04 sfra-search-prototype.tar.xz.part05 sfra-search-prototype.tar.xz.part06 > sfra-search-prototype.tar.xz
tar -xJf sfra-search-prototype.tar.xz
```

Windows CMD:

```bat
copy /b sfra-search-prototype.tar.xz.part00+sfra-search-prototype.tar.xz.part01+sfra-search-prototype.tar.xz.part02+sfra-search-prototype.tar.xz.part03+sfra-search-prototype.tar.xz.part04+sfra-search-prototype.tar.xz.part05+sfra-search-prototype.tar.xz.part06 sfra-search-prototype.tar.xz
tar -xJf sfra-search-prototype.tar.xz
```

## Этап 1: что добавлено

Отдельный пакет `sfra_search` получил read-only адаптер к SQLite Исполнителя 1 и одноразовый runtime. Команда `sfra run-once --source-db PATH --query QUERY` читает текущие структурные узлы из существующей БД, строит FTS5 в памяти, выполняет поиск и выводит JSON с исходными `node_id` и `content_hash`.

Идентификаторы не генерируются и не переписываются. Исходная БД открывается с `mode=ro` и `PRAGMA query_only=ON`. Для получения первоисточника предусмотрена команда `sfra get-source --source-db PATH --node-id ID --content-hash HASH`, возвращающая полный точный `raw_text` и координаты. Постоянный поисковый сервер и файл поисковой БД не создаются.

В модуле также реализованы русский морфологический поиск, Entity Registry и алиасы, числовая нормализация через `Decimal`, ранжирование и API предыдущего прототипа.

## Проверки этапа 1

- `python -m pytest -q`: **56 passed**.
- `python -m compileall -q src tests`: успешно.
- Проверены read-only поведение, неизменность входной БД, поиск и извлечение исходного узла по паре ID/hash, отсутствие файла постоянной поисковой БД.
- Архив ZIP и TAR.XZ проверен локально; SHA-256 TAR.XZ: `cadc03980b8685a22d85fc55270ccd23f892dc66983e4027a1ebb0b231f8c4b5`.

Тесты интеграционного адаптера используют SQLite с опубликованной схемой Исполнителя 1, но не саму полную БД Vault. В Issue №4 отдельно зафиксирован более ранний эксперимент на реальном Vault (66 документов, 9 080 узлов); он проверял прежний smoke harness, а не новый модуль.

## Ограничения и следующий этап

В изолированной локальной среде не удалось установить `pymorphy3` из PyPI; 56 тестов проходили с резервным NLTK Snowball. Основной путь `pymorphy3` должен быть дополнительно проверен в Actions с доступом к зависимостям.

На этапе 2 будет добавлен отдельный workflow, который запускает индексатор Исполнителя 1 в `$RUNNER_TEMP`, устанавливает поисковый пакет и вызывает `sfra run-once`. Затем новый runtime будет проверен на полном Vault с контролем SHA-256 и отсутствия изменений исходников. До этого этап 1 считается только промежуточной точкой, а задача в целом не объявляется принятой.
