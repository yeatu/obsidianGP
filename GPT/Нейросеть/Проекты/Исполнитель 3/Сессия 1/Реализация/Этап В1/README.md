# Этап В1 — интеграция Context Builder: C1

**Статус:** пакет C1 подготовлен к независимой проверке.  
**Объём:** E2 SearchAdapter, snapshot binding, E1 source-read port, fixtures и unit-тесты.  
**Не входит:** реализация E1 SourceReader, Issue worker, recovery, MCP.

## Фактическая исходная точка

- B1 Context Builder принят и находится в `main`.
- E2 предоставляет `search_structural_database(source_database, query, entities=..., limit=..., entity_config=...)`.
- Search hit содержит locator, excerpt, `match_type`, `match_reasons` и `relevance.tier/bm25`.
- E2 `excerpt` — поисковая подсказка, не первоисточник.
- E2 `index_generation` создаётся производным поисковым индексом и не равен E1 `documents.generation`.
- E1 публикует проект `get_node_by_id` только для scope `node`. В документе E1 прямо указано, что реализация API не начиналась; `parent`, `neighbors` и `document` не входят в текущий контракт.

Последний E2 real-Vault report: [run 43997334585](https://github.com/yeatu/obsidianGP/actions/runs/43997334585). Он подтверждает существующий поиск и получение узлов из E1 SQLite, но не новый E1 Source API и не четыре scope-read.

## Реализовано в C1

1. `E2SearchAdapter` вызывает существующий E2 runtime или injected callable.
2. E2 hit используется только как locator/ranking record.
3. Полный `raw_text` поступает только через injected `E1NodeReader` по `node_id + content_hash` и тому же `SnapshotRef`.
4. E2 `excerpt` сохраняется только как `signals.match_excerpt`.
5. Tier/BM25 сохраняются без инверсии; BM25 — ascending.
6. `match_reasons` сохраняются в `unmapped_match_reasons`: неизвестным кодам не приписываются новые значения или веса.
7. E2 generation не используется как E1 document generation.
8. Пустой успешный поиск отличается от ошибки; E2 exception не маскируется под empty result.
9. Ровно `limit` результатов считаются потенциально усечёнными: E2 не возвращает `total_count` или `cursor`.
10. Snapshot binder проверяет `manifest.source_commit` против реального pinned Vault commit, DB SHA-256 и SHA-256 точных байтов manifest. E1 integrity verifier вызывается через официальный `verify_state_directory` callback.

## Открытая зависимость E1

До C2 E1 должен согласовать и реализовать контракт из `Контракты/E1_Source_Scope_API_v1.md`: `node`, `parent`, `neighbors`, `document`.

Для parent/neighbors/document нужны E1 `document_hash` и document-local `index_generation`. E3 не подменяет hash документа хешем узла.

Источник `preservation`, `required_with` и `parent_context_required` пока не подтверждён. E3 не выводит эти флаги из текста, excerpt или match reasons.

## Следующие gates

| Gate | Условие |
|---|---|
| C1 | Аналитик принимает E2 mapping, Snapshot binder, fixtures и запрос к E1 |
| C2 | E1 реализует node / parent / neighbors / document API |
| C3 | E3 подключает SourceReader и DependencyResolver через публичный E1 API; fixtures пройдены |
| C4 | Real-Vault search → Context Pack → все read scopes на одном pinned snapshot, Vault/sidecar read-only |

CI на fixtures не является real-Vault integration test. Следующий gate не начинается автоматически после публикации PR.
