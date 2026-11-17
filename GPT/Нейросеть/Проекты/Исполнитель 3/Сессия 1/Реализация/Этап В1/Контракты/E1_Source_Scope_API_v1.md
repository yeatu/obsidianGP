# E1 Source Scope API v1 — интеграционный контракт E1/E3

**Статус:** согласованный consumer contract для публичных экспортов \`sfra_indexer.read_source_scope\` и \`sfra_indexer.resolve_current_node\`. Реальную E1/Vault интеграцию доказывает только отдельный сквозной прогон на согласованном snapshot, не fixtures.

## 1. Публичные сигнатуры

\`\`\`python
read_source_scope(
    db_path, vault_root, node_id, expected_hash,
    *, scope, snapshot_id,
) -> SourceScopeResult

resolve_current_node(
    db_path, node_id, *, snapshot_id,
) -> CurrentNodeAddress
\`\`\`

Scopes: \`node\`, \`parent\`, \`neighbors\`, \`document\`.

E1 не принимает token budget. E1 возвращает полный verified source text. E3 создаёт SnapshotRef, закрепляет checkout refs, проверяет manifest/SQLite и передаёт opaque \`snapshot_id\` в каждый E1 call. E1 echo-ит этот token, не выполняя Git fetch/checkout/branch resolution.

\`resolve_current_node\` возвращает только актуальный адрес и Content Hash, не raw_text. E3 затем делает exact node scope read по полученному hash. Запрещены fuzzy matching и historical fallback.

## 2. Native result shapes

### SourceScopeResult

\`to_dict()\` содержит:
- \`snapshot_id\`, \`scope\`, \`status\`;
- \`fragments\` — exact NodeRecord dictionaries для node/parent/neighbors; для document scope пустой список;
- \`anchor\` — verified target NodeRecord;
- \`parent\`, \`previous\`, \`next\` — verified relation records или null;
- \`document\` — полный DocumentRecord для document scope либо null;
- \`error\` — безопасная диагностика отказа.

Для любого non-ok result source records не возвращаются: \`fragments=[]\`, anchor/relation/document fields null.

### NodeRecord

Содержит producer Node ID, Content Hash, source path, node type, parent Node ID, heading path, raw_text, line/char/byte coordinates, source/document hash, document-local index generation и metadata.

Node Content Hash = SHA-256 точных UTF-8 байтов raw_text. \`document_hash\`/\`source_sha256\` соответствуют полному исходному документу; \`index_generation\` локален для конкретного source_path.

### DocumentRecord

Содержит полный Markdown raw_text, source_path, source/document hash, document-local generation, UTF-8 size_bytes и anchor identity. Документ не реконструируется из node versions и не обрезается.

### CurrentNodeAddress

Содержит snapshot_id, status, node_id, content_hash, source_path, document_hash, index_generation и error. Не содержит raw_text. При non-ok все address поля пусты.

## 3. Семантика

| Scope | Records | Условие |
|---|---|---|
| node | anchor + [anchor] | exact current target |
| parent | anchor + optional parent, fragments target + parent | immediate parent того же документа/generation; root возвращает только target |
| neighbors | anchor + optional previous/next immediate siblings | тот же parent, source order, не descendants |
| document | anchor + full document, fragments=[] | исходный Markdown целиком |

E3 сопоставляет named relation fields с fragments и независимо проверяет target/parent/sibling IDs, общий parent, source order, уникальность Node IDs и provenance всех fragments.

## 4. Snapshot binding

E3 проверяет:
- actual Vault HEAD == manifest \`source_commit\` (или \`vault_commit_sha\`);
- actual sidecar HEAD относится к branch \`sfra-state\`;
- manifest bytes hash рассчитан по точным байтам;
- E1 public \`verify_state_directory()\` успешно проверил sidecar state;
- SQLite hash совпадает с manifest;
- checkout чистые, Vault root лежит внутри pinned Vault checkout.

Один SnapshotRef проходит через SearchAdapter, DependencyResolver и все SourceReader calls. Document-local E1 generation не используется вместо Vault snapshot identity и не сравнивается между разными source_path.

## 5. Budget и policy metadata

Token budget полностью принадлежит E3:
- E1 возвращает полный текст;
- E3 считает его через B1 TokenCounterProtocol;
- превышение бюджета означает defer/reject целого контекста, без truncation и partial source fragment.

E1 возвращает только реально существующие NodeRecord.metadata. При отсутствии \`preservation\`, \`required_with\`, \`parent_context_required\` E3 применяет B1 defaults \`normal / () / False\`, маркирует их как policy defaults и не выдаёт за source annotations.

## 6. Ошибки и границы

E1 fail-closed для stale, ambiguous, deleted, not_found, invalid_request, integrity_error и не возвращает partial fragments. E3 дополнительно fail-closed для snapshot mismatch, malformed/missing provenance, wrong relation identity/order, content/document hash mismatch, budget_exceeded и E1 transport errors.

E1: SQLite read transaction + source verification + structural relations.  
E2: retrieval/ranking only.  
E3: Git/manifest/SnapshotRef binding + dependency policy + token budget + Context Pack.
