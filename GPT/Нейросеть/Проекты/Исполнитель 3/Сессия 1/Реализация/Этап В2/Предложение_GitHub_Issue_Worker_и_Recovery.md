# Техническое предложение: GitHub Issue Worker и Recovery для SFRA

**Исполнитель:** 3  
**Версия:** 0.1  
**Основа протокола:** sfra.issue.v1  
**Статус:** предложение для аналитика и координатора  
**Реализация worker/recovery:** не входит в эту ветку и PR

---

## 1. Цель и предпосылки

Предложение описывает безопасный transport layer для двух операций:

- search_vault: SearchRequest → E2 SearchAdapter → E3 Context Builder → ContextPack;
- read_source: точный node_id + expected_hash + scope → E1 Source Scope API → E3 budget policy → SourceReadResult.

Предложение следует за подтверждённым real integration run 44026131789: E2, E3 и E1 работали на одном SnapshotRef; все четыре scope и parent dependency прошли; read-only guards подтвердили неизменность production SQLite, manifest, Vault и sidecar. Context Pack был budget_limited (1 included / 2 deferred), что отражено как фактический результат, не как complete.

Текущий smoke workflow .github/workflows/sfra-issue-bridge-smoke.yml доказывает только доставку Issue event и публикацию комментария с issues:write. Он не является worker, не валидирует sfra.issue.v1, не закрепляет SnapshotRef, не вызывает E2/E3/E1 и не обеспечивает идемпотентность или recovery.

### В scope будущей реализации

- Issue request parser и строгая валидация;
- единый Issue worker для событий и повторной обработки;
- application services поверх уже принятого E3 ядра;
- status/result comments;
- per-Issue concurrency и идемпотентность;
- leases, retry policy и scheduled recovery sweep;
- проверки public sidecar/Vault snapshot и безопасная публикация результатов.

### За пределами текущего предложения

- реализация worker/recovery кода;
- MCP adapter/server;
- новые поисковые алгоритмы или SQL-доступ E3 к SQLite E1;
- запись E3 в Vault, main или sfra-state;
- изменение Context Builder B1;
- обработка команд через issue_comment или issues.edited;
- несколько операций в одном Issue.

PR #10 остаётся ограниченным C1. Это предложение предназначено для отдельной постановки V2.

---

## 2. Архитектура и границы ответственности

GitHub Issue — долговременная запись запроса. GitHub Actions — временный исполнитель. Исходное Issue и его комментарии позволяют новому runner восстановить состояние без памяти предыдущего процесса.

Рекомендуемая структура:

    application/
      search_vault.py
      read_source.py
      dispatch.py

    transports/
      github_issue/
        event_parser.py
        request_validator.py
        status_store.py
        result_renderer.py
        worker.py
        recovery.py

### Application services

**SearchVaultService**
- принимает типизированный SearchRequest;
- вызывает существующий E2 SearchAdapter и E3 ContextIntegrationPipeline/ContextBuilder;
- возвращает ContextPack с provenance, diagnostics, Included/Deferred и budget status;
- не знает о GitHub Issues, comments, workflow run или GitHub SDK.

**ReadSourceService**
- принимает ReadSourceRequest;
- вызывает только E1 public read_source_scope() и, когда необходимо, resolve_current_node();
- передаёт SnapshotRef и применяет бюджет через E3 TokenCounterProtocol;
- возвращает SourceReadResult с точной идентичностью фрагментов;
- не обращается напрямую к SQLite E1.

**IssueWorker**
- повторно получает Issue и comments через GitHub API;
- валидирует автора, заголовок, envelope, schema и request identity;
- сериализует обработку одного Issue;
- закрепляет SnapshotRef до запуска application service;
- публикует status и result comments;
- сам не реализует retrieval, dependency resolution, parsing Markdown или бюджетирование.

**RecoveryDispatcher**
- только ищет Issues-кандидаты на восстановление;
- вызывает тот же reusable worker по issue_number;
- не выполняет application service самостоятельно;
- не считает status comment доверенным без повторной валидации worker.

**StatusStore**
- читает/обновляет один status comment;
- валидирует request_id, attempt_no, lease и result manifest;
- не допускает перехода в DONE до проверки всей последовательности result parts.

Transport status не смешивается с business result status. Например, transport DONE + business stale_source означает, что операция успешно обработана и вернула корректный отказ по устаревшему адресу. Аналогично empty и budget_limited не являются transport failure.

---

## 3. Входной Issue и строгая валидация

Сохраняется envelope sfra.issue.v1:

    {
      "protocol_version": "sfra.issue.v1",
      "request_id": "6f2f5b1e-6ab7-4a9e-9c2b-c0c9846c7d14",
      "operation": "search_vault",
      "payload": {
        "query": "пример поискового запроса",
        "budget_tokens": 3000
      }
    }

Разрешённые операции:
- search_vault — payload валидируется отдельно по search_vault.request.schema.json;
- read_source — payload валидируется отдельно по read_source.request.schema.json.

Один Issue = один request_id = одна операция. Повторный read_source создаётся как новое Issue с новым UUID v4.

### Порядок проверок

1. Событие — именно Issue, не Pull Request.
2. Repository full name строго равен разрешённому repository.
3. Заголовок начинается с точного префикса [SFRA].
4. issue.user.login входит в непустой allowlist SFRA_ALLOWED_ISSUE_AUTHORS.
5. Тело Issue содержит ровно один JSON envelope: чистый JSON или один fenced json block, без окружающего текста.
6. protocol_version, UUID v4 и operation допустимы.
7. payload проходит соответствующую JSON Schema с additionalProperties=false.
8. Размер body не превышает 32 KiB UTF-8 (предлагаемый предел, требует утверждения).
9. Запрос не конфликтует с уже известными request_id/issue_number/body hash.
10. Только после успешного завершения проверок вызывается application service.

Авторизация выполняется по точному login из allowlist; одного author_association недостаточно. Если allowlist отсутствует или пуст, worker действует fail closed.

Issue body — недоверенные данные. Запрещены eval/exec, shell interpolation, динамические imports, генерация workflow YAML, произвольные команды и пути из payload. Не вставлять github.event.issue.body внутрь исполняемого shell script. Передавать данные как event JSON или получать Issue через GitHub API.

### Неизменность принятого запроса

Issue можно отредактировать после открытия. Для защиты от изменения команды worker вычисляет SHA-256 точных UTF-8 bytes принятого body и сохраняет его в status comment как request_body_sha256.

Recovery повторно получает body и требует совпадения hash. При mismatch worker не исполняет изменённый payload, выдаёт permanent INVALID_REQUEST_BODY_CHANGED и предлагает создать новое Issue.

Текущая status schema не содержит request_body_sha256. До реализации требуется согласовать additive schema change либо sfra.issue.v1.1. Не помещать обязательный идентификатор в произвольный details object и не менять request envelope без необходимости.

---

## 4. GitHub Actions workflows

### 4.1. Общий worker

Предлагаемый файл:

    .github/workflows/sfra-issue-worker.yml

Поддерживаемые входы:
- issues: types: [opened];
- workflow_call с обязательным issue_number: number.

Оба пути используют один и тот же worker. При workflow_call он получает исходное Issue по номеру через GitHub API и выполняет полную повторную авторизацию и валидацию. Не пытаться искусственно генерировать событие issues.opened.

Прямой production trigger:

    on:
      issues:
        types: [opened]

Не включать issues.edited, issue_comment и pull_request как источники команд. Комментарии являются только результатом. Для изменённой команды создаётся новое Issue.

GitHub требует, чтобы workflow file для события issues уже находился в default branch. Для event issues GITHUB_SHA соответствует последнему commit default branch. Worker должен сохранить фактический checkout SHA и не брать branch/ref/commit из Issue body.

Источник: GitHub Docs, Events that trigger workflows:
https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows

### 4.2. Recovery dispatcher

Предлагаемый файл:

    .github/workflows/sfra-issue-recovery.yml

Триггеры:
- schedule: каждые 5 минут;
- workflow_dispatch: ручная проверка.

Порядок:
1. Постранично получить открытые Issues целевого репозитория.
2. Исключить Pull Requests и заголовки без точного [SFRA].
3. Прочитать status marker и отобрать кандидатов: status отсутствует, PENDING, RUNNING с истёкшим lease, либо FAILED/retryable=true с наступившим retry_after и не исчерпанными попытками.
4. Сформировать matrix по issue_number, fail-fast=false, max-parallel=5.
5. Для каждого Issue вызвать локальный reusable workflow sfra-issue-worker.yml.
6. Не выполнять retrieval/reading в recovery dispatcher.

Выбор кандидатов по comments — только эвристика. Worker повторно читает Issue и все relevant comments, проверяет status schema, request_id, body hash, авторизацию и lease. Повреждённый status comment не трактуется как DONE.

### 4.3. Per-Issue concurrency

Прямой worker и recovery должны разделять один concurrency group на каждый Issue. Ключ должен содержать repository full name и issue_number, чтобы идентификатор не пересекался между репозиториями.

Предлагается concurrency queue: max без cancel-in-progress. При одном active run запросы одного Issue ждут; новый запуск не должен прерывать текущий.

Актуальные ограничения GitHub Actions:
- queue: max допускает до 100 pending jobs/workflow runs в одном concurrency group;
- при заполненной очереди дополнительные запуски отклоняются;
- queue: max несовместим с cancel-in-progress: true;
- порядок FIFO определяется временем попадания в ожидание, а не датой создания Issue.

Поэтому concurrency не даёт абсолютной гарантии доставки. Recovery sweep обязателен и должен повторно обнаруживать не обработанные Issues после переполнения очереди.

Источники:
https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
https://docs.github.com/en/actions/reference/limits

---

## 5. Snapshot binding и работа с E1/E2

Worker использует существующие E3 Snapshot binder, SearchAdapter и SourceReader. Не создавать транспортные аналоги этих компонентов.

До запуска application service:
1. Checkout sfra-state в отдельную рабочую копию и фиксировать фактический sidecar HEAD.
2. Прочитать точные байты state/manifest.json и вычислить manifest SHA-256.
3. Вызвать E1 public verify_state_directory() и сверить SQLite SHA-256 с manifest.database_sha256.
4. Проверить manifest format/schema, source_repository, allowlist source_branch и database path state/structure.sqlite3.
5. Checkout Vault на точный manifest.source_commit, не на текущий main и не на commit из Issue.
6. Проверить фактический Vault HEAD и clean checkout.
7. Создать один SnapshotRef: vault_commit_sha, sidecar_commit_sha, manifest_sha256.

SnapshotRef записывается в RUNNING status до запуска application service. Один snapshot_id передаётся в E2/E3/E1 путь. E1 получает opaque snapshot_id и возвращает его без изменений; Git/manifest binding остаётся ответственностью E3.

Worker и application services работают read-only. Временные поисковые структуры допускаются только в RUNNER_TEMP. У worker нет contents:write. Публикация sidecar остаётся в отдельном E1 persistence workflow.

### Snapshot consistency при recovery

Повтор одного request_id не переключается молча на более новый Vault или sfra-state snapshot.

- Если первая попытка уже закрепила SnapshotRef, следующие attempts обязаны использовать те же commits и manifest hash.
- Если pinned commits недоступны или не проходят проверку, вернуть явную ошибку snapshot unavailable/integrity error. Не выбирать текущий HEAD автоматически.
- Если первая попытка завершилась до snapshot pinning, первая успешная попытка может закрепить SnapshotRef.
- После закрепления snapshot менять его нельзя.

---

## 6. Status lifecycle, идемпотентность и retry

Transport statuses:
- PENDING — запрос принят и ждёт обработки;
- RUNNING — запрос валиден, snapshot и lease закреплены, операция выполняется;
- DONE — business result полностью опубликован и проверен;
- FAILED — transport/validation/infrastructure failure.

Business statuses остаются в ContextPack/SourceReadResult: empty, stale_source, budget_limited, not_found, budget_exceeded, integrity_error и т.п.

### Idempotency key

repository_full_name + issue_number + request_id.

Правила:
- DONE — терминальный no-op;
- FAILED с retryable=false — терминальный no-op;
- RUNNING с актуальным lease — no-op;
- RUNNING с истёкшим lease — recovery candidate;
- PENDING — можно выполнять после получения concurrency slot;
- FAILED с retryable=true — повтор только после retry_after и пока attempt_no меньше max_attempts.

Повторный запуск всегда перечитывает status и Issue до application service.

### Retry policy

Основа Stage A:
- max_attempts = 3;
- backoff после первой retryable failure: 5 минут;
- backoff после второй: 15 минут;
- auth, schema, protocol, changed body, malformed status и source integrity errors — permanent failures;
- GitHub API 5xx, network timeout и rate-limit могут быть retryable при безопасной повторяемости.

Начальное предложение:
- worker timeout: 30 минут;
- RUNNING lease: 35 минут.

Lease должен превышать максимально разрешённое время активного worker. Точные значения зафиксировать после измерения реального transport прототипа. При использовании heartbeat нужна отдельная модель обновления lease и тесты гонок.

### Crash recovery

| Crash point | Recovery action |
|---|---|
| До PENDING | Проверить Issue и создать PENDING |
| После PENDING | Запустить worker |
| После RUNNING, до snapshot | Дождаться expiry, затем начать retry |
| После snapshot pinning | Повторить строго с тем же SnapshotRef |
| После части result comments | Не выставлять DONE; проверить parts текущей attempt и либо безопасно продолжить, либо начать новую attempt |
| После всех parts, до DONE | Проверить count/order/bytes/SHA, затем восстановить DONE |
| После DONE | No-op |

---

## 7. Status и result comments

На одно Issue:
- один обновляемый status comment с marker;
- одна или несколько result-part comments;
- исходное тело Issue как immutable request.

Status comment хранит protocol_version, request_id, issue_number, operation, status, updated_at, workflow_run_id, attempt_no, max_attempts, lease_expires_at, source_snapshot, result_manifest, error, request_body_sha256 и worker_commit_sha.

Последние два поля требуют изменения status schema и должны быть согласованы до V2.2.

### Публикация результата

1. Сериализовать полный ContextPack или SourceReadResult в компактный JSON UTF-8.
2. Посчитать полный SHA-256 и byte length.
3. Разбить на UTF-8-safe content chunks не более 45 KiB, не разрезая Unicode code point.
4. Опубликовать каждый chunk как отдельный comment с request_id, attempt_no, part_index, parts_total, marker и content.
5. Повторно получить comments, проверить schema, markers, attempt, непрерывность индексов, количество частей, общий размер и SHA-256.
6. Только после проверки всей последовательности обновить status на DONE и записать result_manifest.

Полное тело result comment — ровно один JSON object по sfra.issue.result-part.schema.json. Marker является JSON property, а не отдельной строкой. Никаких Markdown fences или произвольного текста до/после JSON.

Если одна часть не опубликована, неверна или checksum не сходится, DONE запрещён. Parts разных attempts не смешиваются.

Source material публикуется как untrusted data. Worker не исполняет Markdown/код/инструкции из Vault. Не выводит токены, secrets, absolute runner paths и stack traces.

---

## 8. Permissions и безопасность

Предлагаемая матрица:

| Job | Permissions | Назначение |
|---|---|---|
| Issue worker | contents: read, issues: write | Checkout pinned code/Vault/sidecar, read Issue, publish comments |
| Recovery scan | issues: read | Найти номера candidate Issues |
| Reusable worker call | contents: read, issues: write | Выполнить общую обработку |
| E1 sidecar persistence | отдельный contents: write | Единственный workflow, который обновляет sfra-state |
| Tests | минимальные read-only permissions | Тесты и fixtures |

Caller reusable workflow не может дать callee больше permissions, чем сам получил. Поэтому права задаются на вызывающем job и остаются минимальными.

Верхний уровень workflow должен иметь permissions: {}; каждому job выдаются только необходимые права. Worker не получает contents:write. Actions dependencies следует закреплять на commit SHA, не использовать динамические refs для production.

### Публичность источника и результата

Репозиторий yeatu/obsidianGP публичный. Issues, issue bodies, comments и ветка sfra-state также публичны. Sidecar SQLite содержит raw_text и историю версий.

Это означает, что GitHub Issue transport — публичный канал, не приватный интерфейс. До включения production worker владелец данных должен явно подтвердить допустимость публикации точных Vault fragments в публичных comments. Allowlist автора не делает результат приватным. Запросы с конфиденциальными данными запрещены.

---

## 9. План отдельной реализации

| PR | Объём | Выход |
|---|---|---|
| V2.1 Application services | Явные SearchVaultService и ReadSourceService поверх E3 pipeline; unit/contract tests | Транспорт-независимые application services |
| V2.2 Safe worker core | Strict Issue parser/schema, non-empty allowlist, body hash, status schema v2, snapshot binding, safe aggregate projector, worker core over fake/in-memory ports | Testable non-production core; no GitHub API, write calls or active workflows |
| V2.3 GitHub transport + recovery | Separately approved GitHub API adapter, status persistence, per-Issue idempotency/concurrency, leases/retries, dispatcher and recovery sweep; fault injection | Non-production transport adapter and recovery evidence, still disabled pending V2.4 |
| V2.4 Controlled rollout | Allowlist, ограниченный budget, audit, secrets review, permission review, эксплуатационные инструкции | Production readiness review |

V2.1 должен быть принят до V2.2. V2.2 не должен включать реальные GitHub API/write calls или активный issues.opened/workflow_call/schedule trigger. V2.2 проверяется только fake/in-memory ports. V2.3 не включается на production Issues до завершения fault injection и отдельного разрешения; V2.4 отдельно принимает controlled rollout.

MCP может рассматриваться позднее как отдельный optional adapter к application services. Для GitHub Issue MVP он не является обязательной зависимостью.

---

## 10. План тестирования и приёмки

### Request parser and schema
- чистый JSON, один fenced JSON, лишний текст, multiple blocks, invalid UTF-8, malformed JSON;
- неизвестная protocol version/operation, UUID, missing/extra fields;
- обе payload schemas;
- input byte limit;
- exact body hash и body modification after acceptance;
- пустой allowlist, authorised и unauthorised author;
- одинаковый request_id в том же и другом Issue.

### Idempotency and fault injection
- параллельные opened/recovery запуск одного Issue;
- recovery при действующем lease;
- повтор DONE и FAILED permanent;
- retry до/после retry_after;
- attempt limit 3;
- crash после каждого перехода PENDING/RUNNING/snapshot/result-part/DONE;
- incomplete/duplicated/reordered/corrupt result comments;
- API 5xx, 429/rate limit и timeout;
- переполнение concurrency queue и восстановление следующим sweep.

### Real data checks
- pinned sidecar/Vault checkout и immutable SnapshotRef;
- search_vault, read_source по четырём scopes;
- stale/unknown/budget results остаются успешными business outcomes;
- raw_text/hash/path/generation provenance сохранены;
- production sfra-state и исходный Vault сравниваются до/после;
- worker не имеет write permissions к contents.

### Приёмка transport MVP
- корректный authorised Issue проходит PENDING → RUNNING → DONE;
- unauthorized/invalid Issue не получает source content;
- DONE повторно не вызывает application service;
- result manifest сходится с собранными chunks;
- transport FAILED чётко различает retryable/permanent;
- recovery подбирает пропущенный, expired и retryable Issue;
- logs/comments не содержат секретов;
- snapshot не меняется между attempts.

---

## 11. Решения, требующие аналитика/координатора

До реализации worker нужно зафиксировать:

1. **Публичность данных:** разрешена ли публикация точных Vault fragments в публичные Issue comments? Это обязательный release gate.
2. **Allowlist:** предлагаю начать только с yeatu; подтвердить владельца и правила добавления авторов.
3. **Schema evolution:** добавить request_body_sha256 и worker_commit_sha в status schema или ввести sfra.issue.v1.1?
4. **Лимиты:** утвердить 32 KiB request body, 45 KiB result content, worker timeout 30 минут и lease 35 минут.
5. **Recovery:** утвердить interval 5 минут и max-parallel 5.
6. **Retries:** max_attempts 3, backoff 5/15 минут и retryable error codes.
7. **Budget/publication:** подтверждается ли публикация всех Included fragments без усечения с опорой на hard token budget E3?
8. **Операционное владение:** кто отключает worker/удаляет ошибочные публичные comments при инциденте?

Пункты 1, 3 и 4 являются blockers. Пока они не согласованы, production worker не включать.

---

## 12. Итог

Рекомендуемая модель:
- Issue — долговременная запись запроса;
- reusable GitHub Actions worker — единственный обработчик;
- recovery workflow — обнаружитель и dispatcher, не второй worker;
- E2/E3/E1 — существующие transport-independent search/context/source components;
- SnapshotRef — закреплённая идентичность всего запроса и всех retry;
- comments — проверяемый status/result store.

Предложение не включает транспортный код, не изменяет C1 PR #10 и не даёт оснований считать smoke workflow готовым worker. Следующий этап после независимой проверки документа — отдельная постановка V2.1 на application services.

---

## 13. Координаторское решение — 2026-11-17

### Статус и scope

Основной E1/E2/E3 retrieval/context контур уже объединён в main. Следующая разрешённая задача — **SFRA-E3-V2.1: transport-independent application services**.

- Реализовать SearchVaultService поверх существующих E2 SearchAdapter и E3 ContextIntegrationPipeline/ContextBuilder.
- Реализовать ReadSourceService поверх публичных E1 read_source_scope() и resolve_current_node().
- Ввести typed request/result contracts и unit/contract tests для обоих сервисов.
- Сохранить единственный SnapshotRef, exact provenance, fail-closed semantics и E3-owned budget policy.
- Не добавлять GitHub SDK, Issue parsing, comments, status store, recovery, Actions workflow или прямой SQL к E1 в V2.1.
- Сервисы должны вызываться из тестов/CLI harness как обычные application API; транспорт будет отдельным адаптером следующего этапа.

### Data publication decision

**DENY BY DEFAULT для публикации source content в публичных GitHub Issues/comments.** Репозиторий публичный, поэтому Issue и все comments рассматриваются как публичный канал.

- Запрещено публиковать raw_text, excerpts, цитаты, заголовки исходных документов, source paths и иные содержательные фрагменты Vault.
- До отдельного разрешения worker может публиковать только транспортный статус и безопасные агрегированные метаданные, не раскрывающие текст и расположение источника.
- Исключение возможно только после corpus-level public-export allowlist, проверенного владельцем данных, и отдельного maintainer approval на конкретный Issue. Без обоих условий source publication disabled.
- Allowlist Issue authors по умолчанию содержит только точный GitHub login yeatu. Пустой или отсутствующий allowlist означает fail-closed.

### Protocol and transport status

- Request envelope сохраняется как sfra.issue.v1; transport-specific fields не добавляются в request payload.
- Status record получает status_schema_version=2, request_body_sha256 и worker_commit_sha.
- Body hash рассчитывается по точным UTF-8 bytes первоначального Issue body; любое последующее изменение блокирует исполнение изменённого запроса.
- Retry обязан сохранять первоначальный SnapshotRef; запрещено молча переключаться на новую версию Vault или sfra-state.

### Initial limits and operations

- Issue request body: максимум 32 KiB UTF-8.
- Result chunk: максимум 45 KiB UTF-8; aggregate serialized result: максимум 256 KiB.
- Worker timeout: 30 минут; RUNNING lease: 35 минут.
- Recovery interval: 5 минут; max-parallel: 5.
- Retry: максимум 3 attempts; backoff 5 минут, затем 15 минут.
- Per-Issue concurrency: без cancel-in-progress; повторная проверка автора, body hash, status, attempt и SnapshotRef перед каждым исполнением.
- Единственный владелец первичного rollout и incident response: repository owner/admin yeatu.
- Budget остаётся под контролем E3. Транспорт не может повышать token budget, обрезать source text или менять business status budget_limited на complete.

### Release gates

V2.1 разрешён к реализации. Production Issue worker, recovery scheduler и любые операции публикации SourceReadResult/ContextPack в GitHub остаются disabled до отдельной V2.2–V2.4 security/readiness acceptance. Требуются тестовый Issue, review permissions, author allowlist, status schema, body hash, snapshot pinning, fault-injection recovery и подтверждение безопасного результата.

MCP остаётся optional и не является зависимостью GitHub Issue MVP.


---

## 14. Координаторское обновление после завершения V2.1 — 2026-11-17

### Фактическое состояние foundation

SFRA-E3-V2.1 завершена и объединена:
- PR [#14](https://github.com/yeatu/obsidianGP/pull/14) merged в `main`, merge commit `9a0bfa012269590466a3b314770425a2a97dfe7f`.
- `SearchVaultService` и `ReadSourceService` входят в main.
- Issue [#13](https://github.com/yeatu/obsidianGP/issues/13) закрыт как completed.
- Pre-merge C1/V2.1/real integration evidence зафиксированы в PR #14 и рабочих реестрах.

Исторические формулировки в разделах 12–13, где следующим шагом называется V2.1, superseded этим обновлением.

### Следующая разрешённая задача: V2.2 non-production safe worker core

Создан отдельный Issue [#15](https://github.com/yeatu/obsidianGP/issues/15): **SFRA-E3-V2.2 non-production Issue validation and safe worker core**.

V2.2 ограничена:
- строгий parser/validator для `sfra.issue.v1`, title/repository/author allowlist и 32 KiB UTF-8 body limit;
- UUID/operation/payload schemas с `additionalProperties=false`;
- `request_body_sha256` по точным UTF-8 bytes и fail-closed при изменении body;
- transport status schema v2 с обязательными `status_schema_version`, `request_body_sha256`, `worker_commit_sha`;
- safe result projection только с allowlisted operational status и безопасными aggregate metadata;
- testable IssueWorkerCore over fake/in-memory ports с использованием V2.1 application services;
- adversarial tests, доказывающие, что reject не вызывает application services и что никакой source content не попадает в публичный projection.

**Жёсткие запреты для V2.2:**
- no GitHub API/SDK client, network calls, credentials or write permissions;
- no active `issues.opened`, `workflow_call` or schedule workflow;
- no real Issue/comment writes;
- no source-text serialization, excerpts, paths, titles or result chunks;
- no lease/retry/recovery, MCP, HTTP/webhooks or deployment;
- no writes to Vault, `sfra-state` or E1 production SQLite.

Владелец реализации по проектной роли — Исполнитель 3; независимая проверка — Аналитик 3; затем пакетная координаторская приёмка. Issue не назначен на GitHub login: проектная роль не сопоставлена с аккаунтом, login не выдумывается.

### Последующие стадии

- V2.3: GitHub API adapter, status persistence, idempotency, lease/retry/concurrency и recovery; отдельный issue/approval и fault injection.
- V2.4: security/readiness audit и controlled rollout. Только отдельная координаторская release acceptance может разрешить production event workflow.
- MCP optional, не входит в GitHub Issue MVP.

**PR #12 остаётся Draft и proposal-only.** Он не включает worker/recovery implementation и не является разрешением на production transport. Public Vault source-content publication остаётся `DENY BY DEFAULT`.
