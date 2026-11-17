# Proposal: E1 Source Scope API v1

**Статус:** предложение на согласование. Это не утверждение, что API уже реализован.

## 1. Предлагаемый интерфейс

```python
read_source_scope(
    db_path, node_id, expected_hash, vault_root,
    *, scope,  # node | parent | neighbors | document
) -> SourceScopeResult
```

Вход адресует точную текущую пару `Node ID + Content Hash`. Fuzzy lookup, похожий узел, подстановка новой версии и чтение исторической версии под текущим адресом запрещены.

`vault_root` должен указывать на immutable checkout, чей Git commit равен manifest `source_commit`. До вызова E3 строит `SnapshotRef`:
- `vault_commit_sha = manifest.source_commit`;
- `sidecar_commit_sha = git rev-parse HEAD` checkout ветки `sfra-state`;
- `manifest_sha256 = SHA-256` точных байтов `state/manifest.json`.

E1 API не делает checkout/fetch и не разрешает moving branch ref.

## 2. Семантика scope

| Scope | Результат |
|---|---|
| `node` | точный текущий target node |
| `parent` | target и непосредственный parent из того же структурного snapshot |
| `neighbors` | target и непосредственные previous/next siblings под тем же parent, упорядоченные по source coordinates |
| `document` | полный исходный Markdown-файл, содержащий target |

Определение neighbors как immediate siblings является предложением для аналитика. Не включать descendants, узлы других родителей или документы.

Document scope возвращает исходный полный файл из checkout, не реконструкцию из `node_versions`.

## 3. Provenance и integrity

Каждый fragment возвращает:
- `node_id`, `source_path`, `node_type`, `parent_node_id`, `heading_path`, координаты;
- `content_hash` — SHA-256 точного UTF-8 фрагмента;
- `raw_text` — точный исходный текст;
- `document_hash` — E1 `documents.source_sha256` полного Markdown;
- `index_generation` — E1 `documents.generation` данного source_path.

E1 выполняет DB-only integrity preflight, безопасное разрешение пути внутри vault_root, проверку полного hash файла, координат и exact slice. Для всех fragments scope требуется одна read transaction и один document generation. При несовпадении hash/snapshot/generation/координат вернуть ошибку и пустой fragments.

Рекомендуемые статусы: `ok`, `stale_source`, `not_found`, `ambiguous`, `deleted`, `invalid_request`, `source_unavailable`, `budget_exceeded`, `integrity_error`. Исходный текст не усекать. `source_unavailable` не превращать в частичный успешный scope.

## 4. Metadata зависимостей

B1 использует `preservation`, `required_with` и `parent_context_required`. Текущий E1 parser/API contract не подтверждает, что эти значения формируются. Просьба указать их источник. Если они существуют, Source API возвращает их verbatim в metadata; если нет, источник согласуется отдельно. E3 не выводит обязательность из Markdown.

## 5. Вопросы на согласование

1. Принимается ли определение neighbors как immediate previous/next siblings одного parent?
2. Подтверждается ли полный document read как capability E1?
3. Может ли E1 гарантировать одну read transaction для target + parent + siblings?
4. Откуда поступают preservation/required_with/parent_context_required?
5. Где применяется scope budget и какой TokenCounter используется? В любом варианте текст нельзя усекать.

До согласования E1 API E3 не делает прямой SQL к E1 schema и не реализует эти scopes через внутреннюю логику индексатора.
