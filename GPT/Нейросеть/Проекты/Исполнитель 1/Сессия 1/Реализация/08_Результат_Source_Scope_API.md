# E1 — единый Source Scope API и Snapshot binding

Статус: реализация подготовлена в PR #11; ожидает CI и повторной независимой приёмки.

## Публичные методы

\`\`\`python
read_source_scope(
    db_path,
    vault_root,
    node_id,
    expected_hash,
    *,
    scope,
    snapshot_id,
) -> SourceScopeResult

resolve_current_node(
    db_path,
    node_id,
    *,
    snapshot_id,
) -> CurrentNodeAddress
\`\`\`

\`scope\`: \`node\`, \`parent\`, \`neighbors\`, \`document\`.

Публичные типы и обе функции экспортированы из \`sfra_indexer\`.

## Структура результата

\`SourceScopeResult\` возвращает:
- исходный \`snapshot_id\` без изменения;
- \`scope\` и общий \`status\`;
- \`fragments\` — кортеж в Python и список при сериализации;
- \`anchor\`, \`parent\`, \`previous\`, \`next\`;
- \`document\` для полного документа;
- безопасные \`error_code/message\`.

Каждый NodeRecord несёт \`node_id\`, \`content_hash\`, \`source_path\`, \`document_hash\`, \`index_generation\`, исходный \`raw_text\`, координаты и ровно существующий \`metadata_json\`. \`document_hash\` соответствует \`documents.source_sha256\`; \`index_generation\` соответствует \`documents.generation\`.

Документная область не реконструируется: \`document.raw_text\` — полный оригинальный Markdown, прочитанный из Vault checkout и проверенный по полному SHA-256. У документа также есть \`document_hash\`, \`index_generation\`, размер, ID и Hash anchor.

## Атомарность

Каждый scope использует один read-only SQLite connection и одну read-транзакцию. Все SQL-запросы для anchor, parent, siblings, document, versions и match events исполняются через неё. Дополнительные публичные методы изнутри не вызываются. В исходный Markdown файл выполняется один безопасный descriptor-relative read; хеш документа проверяется один раз, а все фрагменты строятся из одних и тех же байтов.

Связанные узлы должны иметь тот же \`document_pk\`, \`source_path\`, \`source_sha256\` и текущую \`documents.generation\`, что и anchor. Каждый связанный узел дополнительно проходит собственный latest-version/event/status/hash/coordinate preflight и source slice verification.

Любая ошибка даёт пустой \`fragments\` (и пустые/null content fields), без частичных parent/neighbors/document. Неактивные, stale, deleted и ambiguous записи не выдаются.

## Snapshot responsibility boundary

E1 трактует \`snapshot_id\` как непрозрачную строку. Она сохраняется без нормализации в каждом \`SourceScopeResult\` и \`CurrentNodeAddress\`.

E1 не проверяет Git ref, commit SHA, manifest SHA, SnapshotRef, sidecar provenance и checkout identity. Это обязанность E3. E3 передаёт:
- изолированный, проверенный \`db_path\`;
- соответствующий manifest commit \`vault_root\`;
- вычисленный E3 \`snapshot_id\`.

E1 не выполняет git fetch/checkout и не выбирает актуальный snapshot.

\`resolve_current_node\` использует одну DB read-транзакцию и возвращает актуальные \`node_id\`, \`content_hash\`, \`source_path\`, \`document_hash\`, \`index_generation\`, \`snapshot_id\`. Это DB-only resolution; проверка текущих байтов делается последующим \`read_source_scope\`.

## Compatibility

Существующие функции сохранены как обёртки над единым core:
- \`get_node_by_id\` → \`scope="node"\`;
- \`get_parent_by_id\` → \`scope="parent"\`;
- \`get_neighbors_by_id\` → \`scope="neighbors"\`;
- \`get_document_by_id\` → \`scope="document"\`.

Независимые многосоединительные implementations удалены.

## Проверки

В \`tests/test_lookup.py\` добавлены сценарии:
- четыре scope;
- один connection + одна read-транзакция + один file read на каждый scope;
- совместимость прежних функций с единым core;
- общие \`document_hash/index_generation/source_path\` для всех NodeRecord;
- opaque Snapshot ID echo;
- пустой список фрагментов для stale/ambiguous/deleted/hash/source/path/generation/coordinate/cross-document failures;
- разрешение current node и отказ от stale ID;
- неизменность тестовой SQLite и тестового Vault.

CI дополнительно делает read-only checkout ветки \`sfra-state\`, копирует manifest и SQLite во временный каталог, проверяет копию через \`sfra-index state-verify\`, извлекает из manifest точный Vault commit SHA, checkout-ит этот SHA и проверяет все четыре scope против production snapshot copy. Ни checkout, ни tests не содержат команд публикации/записи в \`sfra-state\`. Проверка текущего Vault завершается Git diff/status guard.

## Границы

- SQLite schema v2 сохранена.
- Parser, identity, storage, indexer и production workflow не переписывались.
- E1 не добавляет токенный бюджет и не обрезает текст.
- E1 не создаёт policy metadata \`preservation\`, \`required_with\`, \`parent_context_required\`.
- Никаких самостоятельных операций Git/Snapshot selection внутри Python API нет.
