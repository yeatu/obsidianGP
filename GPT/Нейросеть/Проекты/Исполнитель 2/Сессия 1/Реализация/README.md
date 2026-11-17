# SFRA Search — Исполнитель 2

**Текущий статус:** E2 active-only исправление и повторная интеграция завершены на PR-ветке. PR №7 подготовлен для независимой проверки Аналитиком 2. В main не влито.

## Контрольные ссылки

- [PR №7: исправление ambiguous-статусов и повторная интеграция](https://github.com/yeatu/obsidianGP/pull/7)
- [Итоговый GitHub Actions run](https://github.com/yeatu/obsidianGP/actions/runs/44007319361)
- [Actions artifact: JSON, JUnit XML и отчёт](https://github.com/yeatu/obsidianGP/actions/runs/44007319361/artifacts/14295396277)
- [Подробный отчёт с SHA и результатами](./Результат.md)
- [Исходный пакет sfra_search](./source/)
- [Fixture-тесты адаптера](./source/tests/test_structural_runtime.py)
- [Read-only структурный адаптер](./source/src/sfra_search/structural.py)
- [Интеграционный workflow в PR-ветке](https://github.com/yeatu/obsidianGP/blob/e2/active-node-source-filter/.github/workflows/sfra-search-integration.yml)

## Что изменено в E2

Оба метода — load_current_nodes() и get_source_node() — допускают только узлы со статусом active и stale_generation IS NULL, принадлежащие active-документам. Ambiguous, stale и deleted записи не импортируются в FTS и не возвращаются как оригинальные источники.

Отдельно защищён parent_node_id: активный узел не раскрывает ID родителя, если родитель ambiguous или stale. При этом сам активный дочерний источник остаётся доступным.

E2 не пытается разрешать неоднозначность и не меняет статус или идентификатор узла в E1. Если у активного узла отсутствуют node_id или content_hash, импорт завершается ошибкой. Если document_hash отсутствует, он остаётся null, а не подменяется хешем узла.

## Проверки

Итоговый Actions run на commit 6e5a1cca0bfacbcb610bb394cc8080fba960c324 завершился success по всем шагам.

- 64 fixture-теста прошли; 0 failures, 0 errors, 0 skipped.
- CLI smoke checks для sfra run-once --help и sfra get-source --help успешны.
- Реальный Vault: 66 документов, 9 080 активных узлов.
- SHA manifest: sha256:3d5eacf5fc2f7f927af8f591f317ea95d56d0c0f53de1bc61cb54d23677fd072.
- SHA структурной SQLite: sha256:2a6d792d5e5c458ffa87df32a082229fc548c42dab2d91a5cc8fa1195bcf6674.
- SQLite quick_check: ok; schema 2.
- Morphology: pymorphy3 2.0.6; обе формы реанимации / реанимацию нормализованы к реанимация.
- Оба запроса вернули по три active-результата; три пары node_id + content_hash совпали.
- Три оригинальных источника получены отдельно; SHA-256 каждого raw_text совпал с content_hash.
- Vault, структурная SQLite и ветка sfra-state после запуска не изменились.
- Постоянный файл поисковой FTS5-базы не создавался.

## Что проверялось где

**Искусственные SQLite fixtures:** active / ambiguous / stale / deleted, stale_generation, удалённый документ, пустая выдача, null document_hash, недоступность неоднозначного источника, скрытие parent_node_id неоднозначного родителя и CLI parser.

**Реальный Vault и текущий E1 manifest:** проверка SHA/manifest, SQLite integrity/schema, поиск двух словоформ, active-only проверка фактических поисковых адресов, получение трёх оригинальных источников и проверка неизменности источников.

В текущем снимке E1 нет ни ambiguous, ни stale, ни deleted строк. Поэтому fixture-тесты подтверждают поведение фильтра для этих статусов; реальная интеграция подтверждает, что поиск в текущем снимке возвращает только допустимые active-адреса. Эти виды доказательств не смешиваются.

## Результат

Подробные версии SHA, запросов, адресов и проверок находятся в [Результат.md](./Результат.md). Машинные результаты и отчёт приложены к Actions artifact.

**Следующий шаг:** независимое ревью Аналитика 2 по PR №7. Автоматическая успешная проверка не является автоматической приёмкой. Слияние в main не выполнялось.
