# Дополнение к архитектуре SFRA: GitHub Issues + Actions

**Исполнитель:** 3  
**Область:** транспорт и эксплуатация Context Builder  
**Статус:** проектное дополнение к Этапу А, передаётся аналитику  
**Программная реализация:** не начата  
**Версия протокола:** sfra.issue.v1

---

## 1. Решение координатора

Основной MVP-транспорт — GitHub Issue → GitHub Actions → Issue Comment.

Это изменение касается транспорта, но не меняет контракты и ответственность бизнес-логики:
- search_vault остаётся операцией формирования Context Pack;
- read_source остаётся операцией адресного чтения;
- Context Builder, Coverage, Deferred, Parallel Sources, Statistics, бюджет, known и SourceReader не зависят от GitHub Actions;
- MCP не является обязательным условием работоспособности MVP.

MCP, если будет реализован позднее или уже появится в ходе разработки, остаётся отдельным необязательным адаптером. Удалять существующий MCP-код или его спецификацию не требуется. Но MCP SDK не должен быть обязательной зависимостью ядра.

## 2. Транспорт-независимое ядро

Внутренние сервисы:

    application/
      search_vault.py       # SearchRequest -> ContextPack
      read_source.py        # ReadSourceRequest -> SourceReadResult
      request_dispatch.py   # строгая маршрутизация operation -> сервис
    context/
      builder.py
      coverage.py
      budget.py
      dependency_graph.py
    adapters/
      executor2_search.py
      source_reader.py
    transports/
      github_issue/
        parser.py
        renderer.py
        status_store.py
      mcp_optional/
        server.py            # только необязательный адаптер, если нужен

Операции ядра не принимают типы SDK GitHub или MCP. Они получают обычные Python-модели/JSON-совместимые структуры и возвращают ContextPack/SourceReadResult.

GitHub transport:
1. получает Issue event;
2. разбирает JSON envelope;
3. проверяет протокол, автора, заголовок и payload schema;
4. вызывает один из двух application services;
5. превращает результат в комментарий или последовательность комментариев.

MCP transport, если появится, вызывает те же application services. Ни один транспорт не содержит бизнес-алгоритмы.

## 3. Issue-протокол

### 3.1. Заголовок и тело Issue

Заголовок должен начинаться с точного префикса:

    [SFRA]

Рекомендуемый заголовок:

    [SFRA] search_vault <request_id>

или:

    [SFRA] read_source <request_id>

Одно Issue — один запрос и одна операция. Для повторного read_source создаётся новое Issue с новым request_id.

Тело содержит один JSON envelope из sfra.issue.v1. Допускаются:
- чистый JSON без дополнительного текста;
- один fenced-блок json без текста до/после.

Любой произвольный текст, несколько JSON-блоков, комментарии вокруг JSON или невалидный JSON приводят к FAILED / INVALID_REQUEST. Issue body не является кодом и не передаётся в shell.

### 3.2. Envelope

Обязательные поля:
- protocol_version: строго sfra.issue.v1;
- request_id: уникальный UUID v4;
- operation: строго search_vault или read_source;
- payload: вход соответствующей операции.

Пример search_vault:

    {
      "protocol_version": "sfra.issue.v1",
      "request_id": "6f2f5b1e-6ab7-4a9e-9c2b-c0c9846c7d14",
      "operation": "search_vault",
      "payload": {
        "query": "Особенности речи Генриха Фауста",
        "entities": ["Генрих Фауст"],
        "facets": ["VOICE"],
        "budget_tokens": 3000,
        "known": [],
        "focus": [
          {
            "id": "voice_style",
            "label": "Общий стиль речи",
            "entities": ["Генрих Фауст"],
            "facets": ["VOICE"],
            "terms": ["общий стиль речи"],
            "match_mode": "any"
          }
        ]
      }
    }

Пример read_source:

    {
      "protocol_version": "sfra.issue.v1",
      "request_id": "c5ca2fca-68cc-4fda-8a6e-276d2fd176a2",
      "operation": "read_source",
      "payload": {
        "node_id": "node_00421",
        "expected_hash": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "scope": "parent",
        "budget_tokens": 2500
      }
    }

Payload проходит отдельную валидацию существующей схемой:
- search_vault.request.schema.json;
- read_source.request.schema.json.

Envelope schema не заменяет валидацию payload. Версия схемы payload и версия транспортного envelope независимы: это позволяет обновлять поля Context Builder с сохранением однозначного Issue-протокола.

### 3.3. Валидация и отказ

До вызова бизнес-логики выполняется:

1. Проверка, что событие относится к Issue, а не Pull Request.
2. Проверка полного repository name.
3. Проверка, что issue.title начинается с [SFRA].
4. Проверка issue.user.login по allowlist SFRA_ALLOWED_ISSUE_AUTHORS.
5. Проверка, что allowlist задан; пустая конфигурация означает fail closed.
6. Строгий разбор envelope и проверка protocol_version.
7. Проверка UUID v4 и разрешённой операции.
8. Проверка payload соответствующей JSON Schema.
9. Ограничение размера входного Issue body (предлагаемый предел MVP: 32 KiB UTF-8).
10. Только после всех проверок — вызов application service.

Allowlist задаётся в GitHub Actions Variables, например SFRA_ALLOWED_ISSUE_AUTHORS=yeatu. Это конфигурация имён GitHub-аккаунтов, не секрет. Не следует полагаться только на author_association: проверяется точный login из allowlist.

Неавторизованные запросы не получают содержимое Vault в комментарии. Невалидные запросы не направляются в произвольные команды, динамические импорты, shell-команды или файловые пути.

## 4. Обработка GitHub Actions

### 4.1. Триггер

Основной триггер:

    on:
      issues:
        types: [opened]

Не подключать issue_comment, pull_request и issues.edited как командные триггеры MVP.

Комментарии Actions являются только результатом. Они не должны запускать новые запросы. Редактирование Issue не изменяет исходную команду: для нового запроса создаётся новое Issue.

GitHub указывает для события issues, что оно имеет activity type opened и что GITHUB_SHA/ref относятся к последнему commit default branch. В обработчике необходимо явно закрепить конкретный SHA, который фактически использован для checkout, и указать его в результате. Источник: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows

### 4.2. Последовательность обработки

1. Получить Issue event.
2. Проверить автора, префикс заголовка и тип события.
3. Разобрать JSON envelope без выполнения содержимого.
4. Проверить версию протокола, UUID, operation и payload schema.
5. Получить commit SHA текущего Vault snapshot.
6. Получить согласованное состояние sidecar и проверить manifest.
7. Запустить нужный application service.
8. Для search_vault — вернуть полный Context Pack.
9. Для read_source — вернуть SourceReadResult с проверкой Node ID + expected_hash и snapshot.
10. Опубликовать/обновить комментарии с request_id и статусом.
11. При ошибке зафиксировать FAILED с машинно-читаемым кодом, безопасным сообщением и диагностикой без секретов/stack trace.

Ни один шаг не интерпретирует тело Issue как Python, shell, YAML, шаблон workflow или импортируемый модуль.

### 4.3. Статусы

Статус транспортной обработки:
- PENDING — Issue зарегистрировано, запрос ожидает обработки или sidecar пока не синхронизирован;
- RUNNING — запрос проверен, snapshot закреплён, операция выполняется;
- DONE — операция выполнена и результат опубликован;
- FAILED — запрос не может быть выполнен из-за невалидного запроса или инфраструктурной/интеграционной ошибки.

Статус операции не смешивается со статусом транспорта. Например:
- Issue transport status = DONE;
- read_source result status = stale.

Это успешная обработка запроса, которая корректно сообщает, что версия источника устарела. Аналогично пустой поиск — DONE с Context Pack status empty, а не FAILED.

### 4.4. Комментарии и machine-readable markers

Один Issue хранит один запрос. Идентификатор обработки:

    repository_full_name + issue_number + request_id

Status comment использует marker:

    <!-- sfra:request:<request_id>:status -->

Комментарии с результатом используют JSON-объект по схеме `sfra.issue.result-part.schema.json`. **Полное тело каждого result-комментария — ровно один JSON-объект**, без отдельной строки marker до/после объекта, без Markdown fence и без произвольного текста вокруг JSON.

Пример структуры тела (это именно тело комментария, а не JSON-фрагмент внутри другого формата):

    {
      "protocol_version": "sfra.issue.v1",
      "request_id": "<uuid-v4>",
      "attempt_no": 1,
      "part_index": 1,
      "parts_total": 1,
      "encoding": "utf-8-json-compact",
      "marker": "<!-- sfra:request:<request_id>:attempt:1:part:1/1 -->",
      "content": "<часть компактного JSON-результата>"
    }

HTML marker является значением JSON-поля `marker`; он **не** публикуется отдельной строкой и не извлекается из тела до JSON-разбора. Клиент сначала разбирает полное тело как строгий JSON, проверяет его по result-part schema, затем проверяет точное соответствие marker полям request_id, attempt_no, part_index и parts_total. Не допускаются префиксы/суффиксы, fenced-блоки или fallback-разбор marker из произвольного текста.

Status comment содержит:
- protocol_version;
- request_id;
- issue_number и operation;
- транспортный status;
- attempt_no и max_attempts=3;
- lease_expires_at (не null только в RUNNING);
- source snapshot (закреплённые source/sidecar commit SHA, manifest digest и версия SQLite/indexer);
- result_manifest или error;
- workflow run id и время обновления.

Result manifest дополнительно содержит attempt_no, который обязан совпадать с top-level attempt_no в status comment. Worker сверяет это равенство. Поле `content` result-part объекта — очередная UTF-8-safe строка компактного JSON-результата; отдельная часть сама по себе не обязана быть валидным JSON. Сборка выполняется только после соединения content по порядку и проверки длины и SHA-256.

Для небольшого ответа используется одна часть. Для большого ответа:
- компактный JSON результата сериализуется в UTF-8 без форматирующих переносов;
- content делится на части не более 45 KiB UTF-8, только по границам code points;
- каждая часть публикуется отдельным комментарием, полное тело которого является JSON-объектом по result-part schema;
- worker проверяет, что request_id/attempt_no/index/total в marker совпадают с полями объекта, индексы идут подряд от 1 до parts_total, а число частей равно result_manifest.parts;
- status comment содержит attempt_no, число частей, общий размер и SHA-256 всей последовательности content;
- клиент соединяет content строго по part_index, проверяет общий размер и hash, затем разбирает единый JSON.

45 KiB — лимит только для content; полный JSON body должен оставаться внутри лимита GitHub Issue Comment. Лимит content проверяется по UTF-8 байтам, а не по числу Unicode-символов.

Такой механизм не обрезает исходный raw_text и не меняет контракт Context Pack/SourceReadResult. Если часть комментариев не опубликована, запрос не переводится в DONE.

При повторе статусный комментарий с тем же request_id обновляется. Маркеры частей включают attempt_no, поэтому старые части другой попытки не могут попасть в сборку нового результата. DONE и FAILED с retryable=false являются терминальными и дают no-op. FAILED с retryable=true может быть повторён recovery workflow с тем же request_id после retry_after и только пока не исчерпан max_attempts. Для повторной попытки создаётся новая группа result-part comments с новым attempt_no; status comment указывает только на manifest текущей попытки.
## 5. Идемпотентность и защита от потери запросов

### 5.1. Источник истины

GitHub Issue — долговременная запись запроса. Исходный Issue и request_id идентифицируют запрос; comments с status/part markers хранят состояние попыток и результат. Внешняя серверная память диалога не требуется.

- request_id генерируется клиентом как UUID v4.
- При recovery используется то же Issue и тот же request_id.
- Для нового read_source создаётся новое Issue и новый request_id.
- Любой запуск сначала повторно получает Issue и comments через GitHub API, затем проверяет автора, заголовок, envelope, schema и status state.
- DONE — терминальный no-op.
- FAILED с retryable=false — терминальный no-op.
- FAILED с retryable=true может быть повторён только по правилам §5.4.
- RUNNING с действующим lease не запускается повторно.
- PENDING выполняется один раз после получения per-Issue concurrency lock.

Клиенту нельзя отправлять один и тот же request_id как две разные команды в разных Issues. Для нового запроса генерируется новый ID.

### 5.2. Concurrency

Issue-запросы читают неизменяемый snapshot sidecar. Разные Issues можно обрабатывать параллельно: каждый runner имеет собственную рабочую копию SQLite, открывает её read-only и создаёт временные поисковые структуры в своём RUNNER_TEMP.

Все пути запуска (событие issues.opened и плановый recovery) используют один reusable workflow и одну per-Issue concurrency group:

    concurrency:
      group: sfra-issue-${{ inputs.issue_number || github.event.issue.number }}
      queue: max

Не включать cancel-in-progress=true. Повторные запуски одного Issue сериализуются; recovery run, ожидающий активный run, после освобождения группы перечитывает статус и становится no-op, если первый run завершился DONE.

GitHub поддерживает queue: max для сохранения до 100 ожидающих запусков в concurrency group. При достижении лимита новые запуски всё ещё могут быть отклонены, поэтому одной настройки concurrency недостаточно для абсолютной гарантии. Источник: https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency

### 5.3. Конкретный recovery sweep через reusable workflow

Используются два workflow файла:

1. `.github/workflows/sfra-issue-worker.yml` — общий worker. Он принимает:
   - обычный триггер `issues: types: [opened]`;
   - повторный вызов через `workflow_call` с обязательным input `issue_number: number`.

   В обоих режимах worker получает актуальный Issue через GitHub API по issue_number и запускает один и тот же обработчик: проверка автора, префикса [SFRA], версии протокола, UUID, operation, payload schema и идемпотентности. Для прямого события issue_number берётся из `github.event.issue.number`, для reusable-вызова — из `inputs.issue_number`.

2. `.github/workflows/sfra-issue-recovery.yml` — scheduled dispatcher:
   - запускается каждые 5 минут через `schedule` и вручную через `workflow_dispatch`;
   - с `issues: read` постранично получает открытые Issues, исключает Pull Requests и отбирает заголовки с точным префиксом [SFRA];
   - просматривает status marker и включает в recovery matrix только Issues без status, с PENDING, с истёкшим lease у RUNNING либо с FAILED/retryable=true, у которого retry_after наступил и attempt_no < max_attempts;
   - status comment и тело Issue при отборе используются только как подсказка для планирования, а не как граница доверия или разрешение выполнить операцию;
   - создаёт matrix по issue_number (fail-fast=false, max-parallel=5) и для каждого элемента вызывает `sfra-issue-worker.yml` через `uses: ./.github/workflows/sfra-issue-worker.yml` и `with: issue_number: ${{ matrix.issue_number }}`;
   - job обнаружения кандидатов имеет только `issues: read`; отдельный matrix job, вызывающий reusable worker, получает `contents: read` и `issues: write`.

Scheduled workflow не пытается искусственно генерировать событие `issues.opened`. Он вызывает тот же reusable worker напрямую. Внутри worker повторно выполняются все проверки; автор вне allowlist или невалидный payload не получает доступа к Vault. Per-Issue concurrency находится в общем reusable worker, поэтому обычное событие и recovery не могут параллельно обработать один Issue.

Recovery scan только выбирает кандидатов. Окончательное решение о повторе всегда принимает worker после повторного чтения Issue и comments. Если status comment отсутствует или повреждён, worker не трактует это как DONE: он проводит обычную авторизацию и валидацию envelope, затем безопасно восстанавливает PENDING либо формирует диагностический FAILED.

### 5.4. Единая семантика повторных попыток

Transport status transitions:

    PENDING -> RUNNING -> DONE
                         -> FAILED

- Первичная попытка начинается с `attempt_no=1`; `max_attempts=3`.
- `DONE` терминален. Повторная доставка события или запуск workflow не вызывает application service повторно.
- `FAILED` с `error.retryable=false` терминален. Для исправленного запроса или ручного повторения после постоянной ошибки создаётся новое Issue и новый request_id.
- `FAILED` с `error.retryable=true` допускает повтор через recovery workflow с тем же Issue и request_id, не раньше `error.retry_after`, пока `attempt_no < max_attempts`.
- При допуске повтора worker меняет status на PENDING, увеличивает attempt_no на 1, очищает error и затем переводит запрос в RUNNING. Верхний предел — три фактические попытки.
- Предлагаемый backoff: 5 минут после первой неудачи, 15 минут после второй. Значение retry_after записывается в status comment и используется recovery scan.
- Если третья попытка завершается transient error, worker публикует FAILED с retryable=false и code=RETRY_EXHAUSTED; исходный код сохраняется в details.last_error_code.
- RUNNING содержит lease_expires_at (MVP: now + 20 минут). Если runner завершился/отменён до terminal status, recovery workflow после истечения lease и освобождения per-Issue concurrency переводит запрос в следующую попытку. Лимит max_attempts применяется и к такому восстановлению.
- Коды авторизации, JSON/protocol/schema validation и другие постоянные ошибки всегда retryable=false. Временные ошибки GitHub API, кратковременная недоступность sidecar и прерывание runner могут быть retryable=true.

`PENDING` и `RUNNING` всегда имеют `error=null`; `DONE` имеет `error=null` и result_manifest; `FAILED` имеет error и не имеет result_manifest. У FAILED/retryable=true поле retry_after обязательно; у retryable=false оно null. У lease_expires_at значение не null только для RUNNING.

Recovery sweep — страховка от задержанных/пропущенных событий и отменённых запусков; Issue остаётся долговременной записью запроса. Комментарии не запускают workflow, так как issue_comment отсутствует в триггерах.

## 6. Постоянное sidecar-хранилище

### 6.1. Актуальное состояние E1 на 17 ноября 2026 года

Постоянное хранилище уже реализовано в E1 и не должно проектироваться заново под прежнее имя:

- ветка: `sfra-state` (orphan branch с отдельным root commit);
- SQLite: `state/structure.sqlite3`;
- manifest: `state/manifest.json`;
- разрешённое дерево ветки: `README.md`, `state/structure.sqlite3`, `state/manifest.json`;
- workflow: `.github/workflows/sfra-state-persistence.yml`.

Старая схема `sfra-index-state/.sfra-state/` не существует и не должна использоваться worker. Ветка `sfra-state` публичная, поскольку репозиторий публичный. Опубликованная SQLite содержит `raw_text` и историю версий; после инициализации эти данные будут доступны читателям репозитория.

На момент последней проверки ветка `sfra-state` ещё содержит только `README.md`: production DB и manifest не опубликованы. Persistence workflow имеет явный fail-closed режим: первый запуск должен быть вручную вызван через workflow_dispatch с `initialize_state=true`. Обычный запуск без базы пропускает restore/index/snapshot/push. Зелёный статус такого пропуска не подтверждает persistence.

### 6.2. Реальная структура и manifest E1

Worker использует только следующую структуру:

    sfra-state/
      README.md
      state/
        structure.sqlite3
        manifest.json

Фактический manifest E1 (format_version=1, SQLite schema v2) содержит следующие поля:

    {
      "format_version": 1,
      "database": "state/structure.sqlite3",
      "database_sha256": "sha256:<64 lowercase hex>",
      "sqlite_schema_version": 2,
      "source_repository": "yeatu/obsidianGP",
      "source_branch": "executor-1/sfra-indexer-session-1",
      "source_commit": "<40-char commit SHA>",
      "indexer_version": "0.2.0",
      "workflow_run_id": "<GitHub Actions run id>",
      "updated_at": "<UTC ISO-8601 timestamp>"
    }

Соответствие manifest E1 и canonical source_snapshot E3:

| Поле E1 manifest | Поле E3 | Правило |
|---|---|---|
| `source_repository` | `source_repository` | Должно совпасть с разрешённым репозиторием |
| `source_branch` | `source_branch` | Проверяется по allowlist; сейчас E1 использует `executor-1/sfra-indexer-session-1` |
| `source_commit` | `vault_commit_sha` | Это commit, из которого E1 индексировал Vault; worker checkout-ит ровно этот SHA, не текущий `main` |
| `database` | `database_path` | Сейчас строго `state/structure.sqlite3` |
| `database_sha256` | `database_sha256` | Сравнивается с SHA-256 скачанного SQLite-файла |
| `format_version` | `manifest_format_version` | Сейчас 1 |
| `sqlite_schema_version` | `sqlite_schema_version` | Проверяется с фактической SQLite schema |
| `indexer_version` | `indexer_version` | Сейчас 0.2.0 |
| `workflow_run_id`, `updated_at` | те же диагностические поля | Сохраняются в source_snapshot |

Дополнительные метаданные, которых **нет** в E1 manifest:
- `sidecar_branch` — фиксированное имя `sfra-state`;
- `sidecar_commit_sha` — SHA commit ветки `sfra-state`, полученный Git checkout/ref;
- `manifest_sha256` — worker вычисляет SHA-256 точных байтов `state/manifest.json`; E1 не хранит hash самого manifest внутри manifest;
- `index_generation` верхнего транспортного snapshot — `null`, потому что E1 SQLite v2 имеет generation на уровне документа, а не единый глобальный generation. Для конкретного source_path E2 получает `documents.generation`; это значение передаётся в get_node/SourceReadResult и сравнивается внутри одного документа, но не между разными документами.

Нельзя ожидать от E1 manifest полей `vault_commit_sha`, `manifest_sha256` или глобального `index_generation`. Нельзя переименовывать `database_sha256` в hash manifest: это hash самого SQLite файла.

### 6.3. Источник whole-document hash и generation

В SQLite E1 v2 таблица `documents` содержит:
- `source_sha256` — SHA-256 всего исходного Markdown-документа в точном UTF-8 представлении;
- `generation` — номер версии именно этого документа, увеличиваемый при его обновлении.

E2 должен получать `document_hash` из `documents.source_sha256` по тому же document/source_path, из которого получен узел. Это предпочтительный путь, а не попытка вывести hash документа из Content Hash отдельного узла. Если поле отсутствует в старой/неполной записи или не может быть однозначно сопоставлено, E2 возвращает `document_hash: null`; подставлять туда `content_hash` запрещено.

`index_generation` в ответе get_node означает документный `documents.generation`, а не глобальный номер всего Vault. Узлы одного source_path должны иметь одинаковые document_hash и index_generation в одном закреплённом snapshot. Для разных source_path эти generation могут различаться; общая идентичность snapshot определяется парой source commit + sidecar commit (и manifest digest).

### 6.4. Реальный persistence workflow E1

Workflow `.github/workflows/sfra-state-persistence.yml`:
1. Checkout кода и Vault из `executor-1/sfra-indexer-session-1`.
2. Checkout отдельной orphan-ветки `sfra-state`.
3. Проверяет root commit без родителей и allowlist файлов.
4. При уже существующих DB+manifest проверяет состояние и восстанавливает SQLite; при первичной инициализации требует `initialize_state=true`.
5. Выполняет инкрементальную индексацию в RUNNER_TEMP, не меняя `ГП/`.
6. Создаёт согласованный SQLite snapshot через Backup API, пишет manifest с точными полями §6.2 и проверяет его.
7. Публикует обычным fast-forward push с проверкой remote HEAD и без force push.

Этот workflow сериализован concurrency group `sfra-state-production`. Он обновляет только `sfra-state`; E3 worker не публикует и не изменяет sidecar.

### 6.5. Issue worker — только чтение

До вызова application service worker обязан:
1. Checkout-ить `sfra-state` и зафиксировать его фактический HEAD как `sidecar_commit_sha`.
2. Прочитать `state/manifest.json`, строго проверить обязательные поля/версии и `database == state/structure.sqlite3`.
3. Проверить `source_repository` и allowlist `source_branch`; checkout-ить исходный репозиторий на точном `source_commit` из manifest. Значение `source_commit` становится E3 `vault_commit_sha`. Worker не подменяет его SHA текущего `main` или SHA из Issue body.
4. Скачать `state/structure.sqlite3`, сверить SHA-256 с `database_sha256`, выполнить SQLite integrity/schema checks.
5. Вычислить SHA-256 точных байтов manifest и записать его как E3 `manifest_sha256`.
6. Открыть SQLite read-only; FTS5 и временные поисковые структуры строить в RUNNER_TEMP.

Проверка snapshot:
- E3 `vault_commit_sha` равен manifest `source_commit` и SHA checkout исходного кода/Vault;
- `sidecar_branch == "sfra-state"`, `sidecar_commit_sha` является commit, из которого прочитаны manifest и DB;
- hash скачанной DB равен manifest `database_sha256`;
- `manifest_sha256` вычислен из тех же байтов manifest, по которым worker выполнил JSON parsing.

Если одна из проверок не проходит, sidecar не используется, результат не выдаётся; запрос остаётся PENDING с диагностикой `INDEX_NOT_READY` или завершается соответствующим integrity error по правилам transport. Worker никогда не записывает в `sfra-state`, `main` или `ГП/`.


## 7. Права GitHub Actions

Минимальная матрица:

| Workflow / Job | permissions | Обоснование |
|---|---|---|
| Issue request worker | contents: read, issues: write | Читать Vault и sidecar; создать/обновить Issue Comments |
| Issue recovery sweep | contents: read, issues: write | Найти ожидающие Issues и восстановить их обработку |
| Sidecar build job | contents: read | Читать Vault, исходники компонентов и текущий sidecar |
| Sidecar publish job | contents: write | Записать SQLite и manifest только в ветку sfra-index-state |
| Unit tests | минимум contents: read или без дополнительных write scopes | Читать исходники и запускать тесты |

Issue worker никогда не получает contents: write. Публикация результата требует только issues: write. contents: write выделяется отдельному workflow/job обслуживания sidecar.

В workflow задаётся permissions: {} на верхнем уровне и только необходимые permissions на соответствующем job. Не применять write-all. Не передавать GITHUB_TOKEN в shell-команды, которые могут получить значения из Issue body. Для API-комментариев использовать штатный GitHub API клиент/экшен, а данные Issue читать как JSON из event payload.

Официальная документация GitHub описывает permissions contents и issues, в том числе то, что write включает чтение: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions

## 8. Безопасность

- Issue body — недоверенные данные. Только strict JSON parser и JSON Schema; никакого eval/exec, shell interpolation, dynamic import или шаблонной генерации кода.
- Передавать поля в Python через JSON-файл/event payload, а не вставлять ${{ github.event.issue.body }} в исполняемый shell script.
- Использовать exact allowlist GitHub authors.
- Проверять [SFRA], operation enum, protocol version и request_id.
- Исключать pull request events и комментарии как источники команд.
- Checkout только известных refs и путей, не использовать путь/branch из Issue body.
- GitHub Actions dependencies лучше закреплять на commit SHA; не использовать динамически выбранные action refs.
- Исходный Markdown из Vault передавать без изменения как untrusted_source_data; его содержимое не исполнять.
- Не включать в comments токены, секреты, абсолютные runner paths или полные stack traces.
- Поскольку текущий репозиторий yeatu/obsidianGP публичный, отдельная ветка sidecar также будет доступна читателям репозитория. Она содержит только производное содержимое уже публичного Vault и метаданные индекса; секреты и приватные данные туда не помещаются.

## 9. Результат через Issue Comment

Для успешной операции:
- status comment = DONE;
- в нём есть request_id, issue_number, operation, source snapshot и result manifest;
- result JSON содержит Context Pack или SourceReadResult;
- при большом ответе несколько payload comments образуют одну проверяемую UTF-8 JSON-последовательность.

Для ошибки обработки:
- status comment = FAILED;
- error.code, безопасное сообщение, retryable и диагностические данные;
- исходный запрос и его request_id остаются в Issue.

Примеры кодов:
- INVALID_REQUEST;
- UNAUTHORIZED_AUTHOR;
- UNSUPPORTED_PROTOCOL_VERSION;
- UNSUPPORTED_OPERATION;
- PAYLOAD_SCHEMA_INVALID;
- INDEX_NOT_READY (оставить PENDING, retryable);
- SIDECAR_CHECKSUM_MISMATCH;
- SIDECAR_DATABASE_UNAVAILABLE;
- SOURCE_SNAPSHOT_MISMATCH;
- INTERNAL_ERROR.

Бизнес-ответы empty, stale, not_found, budget_exceeded и integrity_error не следует автоматически превращать в FAILED transport: если operation штатно сформировала диагностический SourceReadResult/ContextPack, transport status остаётся DONE.

## 10. Сквозной сценарий

1. ChatGPT создаёт Issue [SFRA] search_vault <request_id> с sfra.issue.v1.
2. Actions проверяет автора, заголовок, JSON envelope, версию и payload schema.
3. Worker закрепляет Vault commit, получает согласованный sidecar manifest и выполняет search_vault.
4. Issue Comment возвращает полный Context Pack, включая Node ID и Content Hash.
5. ChatGPT выбирает адресный узел и создаёт отдельное Issue [SFRA] read_source <new_request_id>.
6. Actions вызывает read_source с Node ID + expected_hash + scope.
7. Возвращается точный оригинальный фрагмент с hash/path/version.
8. Если версия изменилась, операция возвращает SourceReadResult.status=stale с current hash/locator и пустыми fragments. Похожий узел не подставляется.

## 11. Проверочные сценарии до реализации

| ID | Сценарий | Ожидаемое поведение |
|---|---|---|
| I-01 | Разрешённый автор + [SFRA] + корректный search_vault JSON | PENDING → RUNNING → DONE; comment содержит Context Pack |
| I-02 | Корректный read_source в новом Issue | DONE; comment содержит исходный текст и версию |
| I-03 | Запрос от автора вне allowlist | Нет доступа к operation result; UNAUTHORIZED_AUTHOR в безопасной диагностике |
| I-04 | Issue title без [SFRA] | Workflow не выполняет запрос |
| I-05 | Невалидный JSON/лишний текст вокруг JSON | FAILED / INVALID_REQUEST |
| I-06 | Неизвестная protocol_version | FAILED / UNSUPPORTED_PROTOCOL_VERSION |
| I-07 | Operation не входит в разрешённый список | FAILED / UNSUPPORTED_OPERATION |
| I-08 | Payload не проходит schema | FAILED / PAYLOAD_SCHEMA_INVALID |
| I-09 | Комментарий Actions к исходному Issue | Не запускает workflow |
| I-10 | Повторный запуск того же Issue/request_id после DONE | No-op; второй несовместимый ответ не создаётся |
| I-11 | Два разных Issue одновременно | Независимые read-only snapshots; запросы не перезаписывают sidecar |
| I-12 | Sidecar refresh одновременно с Issue worker | Worker читает закреплённый branch commit или PENDING INDEX_NOT_READY |
| I-13 | SQLite checksum не совпадает с manifest | Нет чтения как trusted sidecar; ошибка/повтор после исправления |
| I-14 | Runner прервался после RUNNING | Recovery sweep обнаруживает незавершённый Issue и повторяет |
| I-15 | Очередь Actions concurrency перегружена | Долговременный Issue остаётся PENDING и подбирается recovery sweep |
| I-16 | Ответ превышает размер одного комментария | JSON разбит на UTF-8-safe части; общий SHA-256 проверяется; raw_text не теряется |
| I-17 | Source snapshot изменился после search_vault | Новый read_source проверяет expected_hash и возвращает stale при несовпадении |
| I-18 | Содержимое Issue содержит shell/python инструкции | Инструкции остаются строковыми данными; не исполняются |
| I-19 | Pull Request с заголовком [SFRA] | Исключён, никакой операции не выполняется |
| I-20 | В Issue передан абсолютный path/branch/command | Поля отвергаются схемой или игнорируются; checkout использует только заданные workflow refs |
| I-21 | Scheduled sweep находит PENDING Issue | Matrix вызывает тот же reusable worker; автор, title, envelope и payload schema проверяются повторно |
| I-22 | FAILED с retryable=true и наступившим retry_after | Тот же Issue/request_id переходит в PENDING и запускается следующая попытка; старые parts не смешиваются |
| I-23 | FAILED с retryable=false либо DONE | Recovery вызывает worker или пропускает Issue; operation не запускается повторно |
| I-24 | FAILED retryable=true после третьей попытки | Состояние становится terminal FAILED / RETRY_EXHAUSTED |
| I-25 | RUNNING lease истёк после прерывания runner | После освобождения concurrency group recovery запускает следующую попытку, если лимит не исчерпан |

## 12. Что подтвердить с координатором/предыдущими исполнителями

1. Допускается ли отдельная публичная ветка sfra-index-state для постоянного хранения SQLite. Поскольку репозиторий публичный, ветка будет публичной.
2. Где хранится постоянная часть реестра сущностей/алиасов E2: в отдельном search-state DB или в общей базе. FTS5 при этом может быть временной.
3. Какой точный workflow/branch является источником актуального кода E1/E2 при sidecar refresh.
4. Требуется ли разрешать несколько авторов в SFRA_ALLOWED_ISSUE_AUTHORS, кроме текущего владельца репозитория.
5. Какой максимальный размер result comments считать операционным порогом. Проектное предложение — 45 KiB UTF-8 на одну часть.

---

**Статус:** транспортная архитектура GitHub Issues + Actions описана. Она не требует реализации MCP SDK для MVP. До повторной проверки аналитика workflow, приложение и постоянная ветка sidecar не создаются.
