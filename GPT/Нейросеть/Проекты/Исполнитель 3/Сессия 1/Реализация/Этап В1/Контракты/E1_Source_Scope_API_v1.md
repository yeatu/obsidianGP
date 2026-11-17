# Proposal: E1 Source Scope API v1 для Executor 3

**Статус:** предложение E3 для согласования с E1 и аналитиком. Ветка E1 PR #11 сейчас реализует точное чтение одного узла; остальные scope в production E1 пока отсутствуют.

## 1. Публичные операции

Предлагается единая операция scope read:

    read_source_scope(
        db_path,
        vault_root,
        node_id: str,
        expected_hash: str,
        *,
        scope: str,  # node | parent | neighbors | document
        budget_tokens: int | None,
        snapshot_id: str,
    ) -> SourceScopeResult

Вход адресует точную текущую пару Node ID + Content Hash. Fuzzy lookup, поиск похожего узла, выбор исторической версии вместо текущей и автоматическая подмена новым hash запрещены.

Для B1 dependency edges, в которых известен только Node ID, необходима отдельная операция:

    resolve_current_node(
        db_path,
        node_id: str,
        *,
        snapshot_id: str,
    ) -> CurrentNodeAddress

Она возвращает только current locator: Node ID, Content Hash, source_path, parent, coordinates, document_hash, document-local index_generation и explicit metadata. После этого E3 обязан запросить полный текст отдельным exact read_source_scope(scope="node", expected_hash=...). Нельзя возвращать похожий/исторический узел под другим ID.

## 2. Snapshot pinning

E3 создаёт B1 SnapshotRef до первого вызова:
- vault_commit_sha — фактический HEAD immutable Vault checkout;
- sidecar_commit_sha — фактический HEAD immutable sfra-state checkout;
- manifest_sha256 — SHA-256 точных байтов state/manifest.json.

Обязательное равенство:
SnapshotRef.vault_commit_sha == manifest.source_commit == pinned Vault HEAD.

E1 получает snapshot_id как непрозрачный correlation token и возвращает тот же snapshot_id в каждом ответе. E1 не должен повторно разрешать branch name, делать checkout/fetch или переключать SQLite/Vault path в рамках операции. E3 проверяет SHA и checkout identity до вызова.

Для одной операции scope E1 выполняет чтение из одной SQLite read transaction и одного pinned Vault checkout. Для полного pipeline E3 повторно передаёт тот же SnapshotRef всем операциям.

## 3. Семантика scope

| Scope | Fragments | Правило |
|---|---|---|
| node | target | Только текущий exact Structural Node |
| parent | target + parent_context | Непосредственный parent из того же structural tree и document generation; если parent отсутствует — target + diagnostic |
| neighbors | target + optional previous_neighbor / next_neighbor | Immediate siblings под тем же parent, в порядке source coordinates; не descendants |
| document | один document | Полный оригинальный Markdown-файл, содержащий target; не reconstruction из node_versions |

Если запрошенный scope не реализован, вернуть source_unavailable, а не частичный успешный ответ.

## 4. Response envelope

Каждый ответ обязан включать:
- status;
- snapshot_id;
- target_source (для успешных ответов);
- fragments;
- diagnostics;
- token_accounting для budgeted request.

Для каждого node fragment:
- role, node_id, source_path, node_type, parent_node_id;
- heading_path, line coordinates;
- content_hash — SHA-256 точных UTF-8 байтов raw_text;
- raw_text — дословный проверенный исходный срез;
- document_hash — E1 documents.source_sha256;
- index_generation — E1 documents.generation данного source_path.

Для document fragment:
- role="document";
- полный оригинальный Markdown в raw_text;
- content_hash == document_hash == SHA-256(full raw_text UTF-8);
- тот же source_path и document-local generation target.

Для scope node document_hash=null допускается, если E1 не располагает whole-document hash. Для parent/neighbors/document null запрещён и приводит к integrity_error + пустому fragments.

## 5. Проверки целостности

1. Validate Node ID, expected hash и scope.
2. E1 DB-only integrity preflight из PR #11.
3. Текущий active/unambiguous Node ID; no historical fallback.
4. Безопасный canonical path/symlink check внутри pinned vault_root.
5. Полный файл SHA-256 против documents.source_sha256.
6. Координаты и exact source slice.
7. SHA-256 каждого fragment exact UTF-8.
8. Для parent/neighbors/document — общий source_path, document_hash и E1 document-local generation.
9. Все fragments одной scope операции получены в одной read transaction.
10. Error response всегда содержит fragments=[]; никакого partial raw_text.

E1 document generation — локален для source_path, его нельзя сравнивать между разными документами или использовать как глобальный Vault snapshot ID.

## 6. Статусы и бюджет

Рекомендуемые статусы:
ok, stale_source, not_found, ambiguous, deleted, invalid_request, source_unavailable, budget_exceeded, integrity_error.

Budget:
- применяется к полной запрошенной scope;
- raw_text никогда не обрезается;
- если полный scope превышает budget — budget_exceeded, fragments=[];
- TokenCounter/encoding должны быть зафиксированы и согласованы.

## 7. Dependency metadata

B1 использует:
- preservation;
- required_with;
- parent_context_required.

E1 должен явно подтвердить источник этих полей и вернуть их verbatim. Если они хранятся в metadata, указать таблицу/поле и гарантии экспорта. Если не существуют, координатор должен определить другой explicit source. E3 не выводит обязательность из Markdown текста, E2 excerpt или поисковых причин.

## 8. Вопросы для согласования

1. Принимается ли neighbors как immediate siblings одного parent?
2. Может ли E1 гарантировать atomic read transaction для target + parent + siblings?
3. Подтверждается ли полный Markdown document read?
4. Как E1 принимает/echo-ит snapshot_id, а E3 проверяет три component hashes?
5. Как E1 предоставляет current-node lookup по Node ID для B1 dependency resolver?
6. Как передаются preservation/required_with/parent_context_required?
7. Какой TokenCounter и scope budget поддерживаются?

До согласования и реализации этого API E3 использует fake E1 Scope API только в тестах и не делает SQL к внутренней схеме E1.
