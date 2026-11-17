# E1 Source Scope API v1 — интеграционный контракт E1/E3

**Статус:** описание синхронизировано с публичным API, реализованным в ветке E1 PR #11. E3 потребляет только публичные экспорты \`sfra_indexer.read_source_scope\` и \`sfra_indexer.resolve_current_node\`. Production end-to-end считается неподтверждённым до отдельного прогона на согласованном snapshot.

## 1. Публичные операции

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

Разрешённые \`scope\`: \`node\`, \`parent\`, \`neighbors\`, \`document\`.

У \`read_source_scope\` нет \`budget_tokens\`. E1 возвращает полный проверенный текст; токенный бюджет рассчитывает и применяет E3. E1 не выполняет Git fetch/checkout, не разрешает branch names и не переключает состояние.

\`resolve_current_node\` возвращает текущий однозначный адрес и producer Content Hash без \`raw_text\`. E3 после этого обязан выполнить exact \`read_source_scope(scope="node", expected_hash=...)\`. Fuzzy matching и historical fallback запрещены.

## 2. Snapshot binding

E3 до первого E1 вызова формирует \`SnapshotRef\`:

- \`vault_commit_sha\` — фактический HEAD чистого immutable Vault checkout;
- \`sidecar_commit_sha\` — фактический HEAD чистого checkout ветки \`sfra-state\`;
- \`manifest_sha256\` — SHA-256 точных байтов \`state/manifest.json\`.

Проверки E3:
- \`SnapshotRef.vault_commit_sha == manifest.source_commit\` (либо согласованный \`vault_commit_sha\`) == actual Vault HEAD;
- sidecar checkout действительно находится на ветке \`sfra-state\`; recorded sidecar SHA равен его HEAD;
- E1 \`verify_state_directory()\` успешно проверяет manifest/SQLite/schema/FK/integrity;
- SHA SQLite равен \`manifest.database_sha256\`;
- SHA manifest считается по raw bytes, а не по повторно сериализованному JSON;
- оба checkout чистые; Vault root лежит внутри pinned Vault repository.

\`snapshot_id\` — \`SnapshotRef.snapshot_id\`. E3 передаёт его в каждый \`read_source_scope()\` и \`resolve_current_node()\`. E1 возвращает его без изменений в каждом success/error result. Echo подтверждает корреляцию запроса, но не заменяет проверки Git/manifest, которые выполняет E3.

## 3. Нативный response shape E1

### SourceScopeResult

Результат имеет публичный \`to_dict()\` shape:

- \`snapshot_id\`;
- \`scope\`;
- \`status\`;
- \`fragments\`: список \`NodeRecord.to_dict()\` для scope \`node\`, \`parent\`, \`neighbors\`; для \`document\` пустой список;
- \`anchor\`: exact target \`NodeRecord\` при success;
- \`parent\`, \`previous\`, \`next\`: соответствующий current relation record или \`null\`;
- \`document\`: полный \`DocumentRecord.to_dict()\` для scope \`document\`, иначе \`null\`;
- \`error\`: код и безопасное сообщение при отказе.

На любом non-ok статусе \`fragments\` пуст, \`anchor/parent/previous/next/document\` равны \`null\`. Частичный source payload запрещён.

### NodeRecord

Включает как минимум:
- \`node_id\`, \`content_hash\`, \`source_path\`;
- \`node_type\`, \`parent_node_id\`, \`heading_path\`;
- \`raw_text\`, \`line_start\`, \`line_end\`;
- \`char_start\`, \`char_end\`, \`byte_start\`, \`byte_end\`;
- \`source_sha256\`, \`document_hash\`, \`index_generation\`;
- \`metadata\`.

\`document_hash\` и \`source_sha256\` соответствуют \`documents.source_sha256\`; \`index_generation\` — \`documents.generation\` этого \`source_path\`. Node content hash — SHA-256 точных UTF-8 байтов \`raw_text\`.

### DocumentRecord

Включает:
- \`source_path\`, \`source_sha256\`, \`document_hash\`, \`index_generation\`;
- \`size_bytes\`, полный \`raw_text\`;
- \`anchor_node_id\`, \`anchor_content_hash\`.

Для \`document\` scope E1 возвращает полный оригинальный Markdown. \`document_hash == source_sha256 == SHA-256(raw_text UTF-8)\`. Документ не реконструируется из node versions и не обрезается.

### CurrentNodeAddress

Публичный \`to_dict()\` shape плоский:
- \`snapshot_id\`, \`status\`;
- \`node_id\`, \`content_hash\`, \`source_path\`;
- \`document_hash\`, \`index_generation\`;
- \`error\` при отказе.

Все address-поля \`null\` при non-ok. \`raw_text\` не возвращается.

## 4. Семантика scope

| Scope | Публичные поля | Семантика |
|---|---|---|
| \`node\` | \`anchor\`, \`fragments=[anchor]\` | Текущий exact structural node |
| \`parent\` | \`anchor\`, optional \`parent\`, fragments target + parent | Непосредственный parent того же документа и поколения; root node возвращает только anchor |
| \`neighbors\` | \`anchor\`, optional \`previous\`, \`next\`, fragments target + immediate siblings | Соседи под тем же parent, упорядочены по source coordinates; не descendants |
| \`document\` | \`anchor\`, \`document\`, \`fragments=[]\` | Полный исходный Markdown, содержащий target |

E3 нормализует named relations в роли \`target\`, \`parent_context\`, \`previous_neighbor\`, \`next_neighbor\`, \`document\`. Он проверяет, что native \`fragments\` содержат те же Node IDs/hashes, что и named relation fields; отдельно сверяет parent identity, общий parent у siblings, source order и уникальность Node IDs.

## 5. Целостность и статусы

E1 отвечает за:
- один SQLite connection и одну read transaction на scope;
- DB-only integrity preflight;
- current active/unambiguous records;
- безопасность source path и чтения Vault;
- document SHA и точные source slices/coordinates;
- связи parent/siblings внутри одного документа и поколения;
- no partial fragments при отказе.

E3 дополнительно сверяет:
- expected target node + content hash;
- echo snapshot_id и scope;
- \`source_path\`, \`source_sha256/document_hash\`, \`index_generation\` между native results;
- SHA-256 raw text фрагмента и полного документа;
- relation identity/order в нормализованном ответе.

Текущие E1 status values: \`ok\`, \`stale_source\`, \`deleted\`, \`ambiguous\`, \`not_found\`, \`invalid_request\`, \`integrity_error\`. E3 сохраняет эти отказы как явные статусы; ошибки контракта и snapshot mismatch также fail closed.

## 6. Token budget — только E3

- E1 никогда не принимает и не применяет token budget.
- E1 возвращает полный точный текст каждого fragment/document.
- E3 вызывает существующий \`TokenCounterProtocol\` на полном результате.
- При превышении бюджета E3 возвращает \`budget_exceeded\` с пустыми fragments либо откладывает atomic group в Context Builder.
- E3 не обрезает \`raw_text\` и не выдаёт partial excerpt за полный источник.

## 7. Dependency metadata

E1 может передавать значения из реально существующего \`NodeRecord.metadata\`. Не следует требовать от структурного индексатора специальных policy-полей, если их источник не определён отдельным контрактом.

Если реальные значения присутствуют, E3 может использовать:
- \`preservation\`;
- \`required_with\`;
- \`parent_context_required\`.

При отсутствии E3 применяет B1 defaults:
- \`preservation = "normal"\`;
- \`required_with = ()\`;
- \`parent_context_required = False\`.

E3 помечает defaults как policy defaults, а не source annotations. Поиск, excerpt и текст узла не являются источниками этих значений.

## 8. Разделение ответственности

- E1: текущая структурная идентичность, атомарное source read, проверка текста/хешей/путей/координат/relations, echo \`snapshot_id\`.
- E3: закрепление Git HEADs, проверка \`sfra-state\` ref и Vault commit against manifest, raw manifest digest, SnapshotRef, token counter/budget, dependency policy defaults, Context Pack.
- E2: только поиск и ranking через существующий SearchAdapter boundary.

Ни одна из сторон не изменяет SQLite schema v2 в рамках этого интеграционного контракта.
