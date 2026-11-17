# SFRA-E3-V2.1 — Application Services

**Владелец:** Исполнитель 3  
**Статус:** реализация в отдельной ветке, передача аналитику после CI  
**Issue:** [#13 — transport-independent application services](https://github.com/yeatu/obsidianGP/issues/13)

## Назначение

V2.1 добавляет transport-independent application API поверх принятого контура E1/E2/E3. Эти сервисы предназначены для последующего использования CLI, GitHub Issue worker или MCP adapter, но сами не зависят от транспорта.

## Реализация

Пакет: `sfra_context_integrations`.

### SearchVaultService

Создаётся поверх уже сконфигурированного `ContextIntegrationPipeline`:

```python
from sfra_context_builder.models import SearchRequest
from sfra_context_integrations import (
    ContextIntegrationPipeline,
    SearchVaultService,
)

service = SearchVaultService(pipeline)
result = service.search(
    SearchRequest(query="...", task="...", budget_tokens=3000),
    source_reads=(),
)
```

- Принимает B1 `SearchRequest` и необязательную последовательность E3 `SourceReadRequest`.
- Передаёт их существующему pipeline; не создаёт новые adapters, builder, resolver или snapshot.
- Возвращает исходный `ContextIntegrationResult` без пересборки и потери diagnostics, coverage, Included/Deferred или budget status.
- Не переименовывает `budget_limited` в `complete`.

### ReadSourceService

Создаётся поверх уже созданного и закреплённого `E1SourceReader`:

```python
from sfra_context_integrations import ReadSourceRequest, ReadSourceService

service = ReadSourceService(source_reader)
result = service.read(
    ReadSourceRequest(
        node_id="node_...",
        expected_hash="sha256:<64 lowercase hex>",
        scope="node",  # node | parent | neighbors | document
        snapshot=pinned_snapshot.ref,
        budget_tokens=3000,
    )
)
```

- Запрос включает неизменяемый `SnapshotRef`; сервис отвергает несовпадение с snapshot reader.
- Передаёт scope и бюджет существующему E3 SourceReader.
- Возвращает typed `ReadSourceResult`, типизированные source fragments, diagnostics, token accounting и business error.
- Сохраняет exact identity/provenance и полный raw text из результата E3 SourceReader; не пересчитывает хеши и не считает токены повторно.
- Любой non-ok статус обязан иметь пустой `fragments`; частичные тексты отвергаются как нарушение контракта.
- `budget_exceeded` возвращается как business status, без усечения текста.

## Типизированные контракты

Экспортируются:
- `ReadSourceRequest`, `ReadSourceResult`, `SourceFragment`;
- `ServiceDiagnostic`, `TokenAccounting`, `ServiceError`;
- `ApplicationServiceError`, `ApplicationServiceContractError`;
- `ContextIntegrationPipelinePort`, `SearchVaultApplication`, `ReadSourceApplication`.

Для поиска переиспользуются B1 `SearchRequest`, E3 `SourceReadRequest` и `ContextIntegrationResult`. Новый parallel request/result model не вводится, чтобы не создавать вторую интерпретацию уже принятого результата.

## Архитектурные границы

- Constructor injection; одна реализация каждого port на snapshot.
- Один pinned SnapshotRef на всю операцию.
- E2 остаётся владельцем retrieval/search.
- E1 public API остаётся единственным source boundary.
- E3 SourceReader остаётся владельцем source validation и token budget.
- В V2.1 нет GitHub SDK/API, Issues/comments, HTTP server, webhooks, MCP, retries, leases или recovery.
- В V2.1 нет сериализатора или renderer для raw source text. Source text остаётся результатом внутреннего application call.
- Никакой записи в Vault, sfra-state или E1 SQLite.

## Проверки

Локальная команда из корня репозитория после установки B1/E3/E2 packages:

```bash
python -m pytest -q "GPT/Нейросеть/Проекты/Исполнитель 3/Сессия 1/Реализация/Этап Б1/tests"
python -m pytest -q "GPT/Нейросеть/Проекты/Исполнитель 3/Сессия 1/Реализация/Этап В1/tests"
python -m pytest -q "GPT/Нейросеть/Проекты/Исполнитель 3/Сессия 1/Реализация/Этап В2.1/tests"
```

CI workflow: `.github/workflows/sfra-e3-v2-1-application-tests.yml`. Он запускает B1, C1 и V2.1 contract suites и проверяет, что E3 package не объявляет GitHub/HTTP/MCP зависимости.

Реальная E1/E2 интеграция остаётся отдельным read-only gate и запускается существующим workflow `.github/workflows/sfra-e3-real-e1-integration.yml` на том же PR HEAD.

## Security

Репозиторий и GitHub Issues/comments публичные. Публикация raw_text, excerpts, quotes, titles, paths и source fragments запрещена по умолчанию. V2.1 не содержит механизма сериализации или внешней публикации содержимого Vault.


## Фактические результаты проверки — 2026-11-17

Проверенный implementation HEAD: `9b57c68a4d74240432a530f941f38e06c1100d3b`.

- [V2.1 application service CI 44047430145](https://github.com/yeatu/obsidianGP/actions/runs/44047430145): success — B1 **45 passed**, C1 **56 passed**, V2.1 **18 passed**; transport dependency guard passed.
- [C1 regression CI 44047430129](https://github.com/yeatu/obsidianGP/actions/runs/44047430129): success — B1 **45 passed**, C1 **56 passed**.
- [Real E1/E2/E3 + V2.1 integration 44047430210](https://github.com/yeatu/obsidianGP/actions/runs/44047430210): success.
- Machine-readable artifact: [ID 14311932536](https://github.com/yeatu/obsidianGP/actions/runs/44047430210), ZIP SHA-256 `sha256:804d99db6b9fb447bc8b854e10fb8d9aa9a86ffaeedcdf0676596c22b341419e`.

### Real application-service exercise

The real runner now invokes `SearchVaultService.search()` over the actual `ContextIntegrationPipeline` and `ReadSourceService.read()` over the actual E1 SourceReader. The results recorded in artifact 14311932536:

| Scope | Status | Typed fragments |
|---|---|---|
| node | ok | 1 target |
| parent | ok | 1 target + 1 parent_context |
| neighbors | ok | 1 target + 1 next_neighbor |
| document | ok | 1 document |

All four ReadSourceResult values echo the same SnapshotRef. SearchVaultService returns the existing ContextIntegrationResult and preserves Context Pack status `budget_limited`. ReadSourceService document budget test returns `budget_exceeded`, no fragments, budget owner E3.

### Pinned snapshot and read-only guards

- E3 implementation: `9b57c68a4d74240432a530f941f38e06c1100d3b`.
- E1 API: `a9ba3445d4a7bd4b6e6a9806770b75b4f16640ef`.
- Vault commit: `2a3c54fa7a9e910f4c9621c8fe00f41a061fc158`.
- sidecar commit: `fb0b45ae0e5043e342c790d43e2b341ca65d7f2b`.
- manifest SHA-256: `sha256:3d5eacf5fc2f7f927af8f591f317ea95d56d0c0f53de1bc61cb54d23677fd072`.
- SQLite SHA-256: `sha256:2a6d792d5e5c458ffa87df32a082229fc548c42dab2d91a5cc8fa1195bcf6674`.

The original E3 real negative matrix also remained green: stale hash, not_found, corrupt source, ambiguous/deleted disposable lifecycle, snapshot echo/request mismatch, document hash mismatch and generation mismatch all fail closed. Production SQLite, manifest, sidecar tree and Vault tree remained unchanged; HEADs and clean checkout guards passed.

**Interpretation:** technical and CI gates for V2.1 are demonstrated on the above HEAD. This is an implementation handoff, not Analyst 3 acceptance. PR #14 remains Draft and unmerged.
