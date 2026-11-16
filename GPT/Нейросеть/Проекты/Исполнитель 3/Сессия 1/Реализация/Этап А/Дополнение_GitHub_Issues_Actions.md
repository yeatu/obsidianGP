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

В комментариях используется marker:

    <!-- sfra:request:<request_id>:status -->

Комментарии с результатом используют:

    <!-- sfra:request:<request_id>:attempt:<attempt_no>:part:<index>/<total> -->

Status comment содержит:
- protocol_version;
- request_id;
- issue_number и operation;
- транспортный status;
- attempt_no и max_attempts=3;
- lease_expires_at (не null только в RUNNING);
- source snapshot (commit SHA, index_generation, document/index manifest);
- result_manifest или error;
- workflow run id и время обновления.

Result manifest дополнительно содержит attempt_no. Каждая часть результата публикуется как JSON-объект по схеме `sfra.issue.result-part.schema.json`: protocol_version, request_id, attempt_no, part_index, parts_total, encoding, marker и content. Поле content — очередная UTF-8-safe строка компактного JSON-результата; отдельная часть сама по себе не обязана быть валидным JSON. Сборка выполняется только после соединения content по порядку и проверки длины и SHA-256.

Payload comments содержат сериализованный результат. Для небольшого ответа весь компактный JSON помещается в одну часть. Для большого ответа:
- компактный JSON сериализуется в UTF-8 без форматирующих переносов;
- строка делится на части не более 45 KiB, только по границам UTF-8 code points;
- каждая часть публикуется отдельным комментарием с marker и порядковым номером;
- status comment содержит число частей, общий размер и SHA-256 всей сериализованной последовательности;
- клиент соединяет части строго по индексу, проверяет общий размер и hash, затем разбирает JSON.

Такой механизм не обрезает исходный raw_text и не меняет контракт Context Pack/SourceReadResult. Если часть комментариев не опубликована, запрос не переводится в DONE.

При повторе статусный комментарий с тем же request_id обновляется. Маркеры частей включают attempt_no, поэтому старые части другой попытки не могут попасть в сборку нового результата. DONE и FAILED с retryable=false являются терминальными и дают no-op. FAILED с retryable=true может быть повторён recovery workflow с тем же request_id после retry_after и только пока не исчерпан max_attempts. Для повторной попытки создаётся новая группа result-part comments с новым attempt_no; status comment указывает только на manifest текущей попытки.

## 5. Идемпотентность и защита от потери запросов

### 5.1. Источник истины

GitHub Issue — долговременная запись запроса и очередь PENDING. Комментарии с marker — журнал исполнения и результата. Внешняя серверная память диалога не требуется.

- request_id генерируется клиентом как UUID v4.
- При повторе обработки используется тот же Issue и тот же request_id.
- Для нового read_source создаётся новое Issue и новый request_id.
- Дубликат workflow run сначала ищет marker status. При terminal DONE/FAILED бизнес-функция повторно не запускается.
- Все результаты связаны с исходным issue_number + request_id.

Клиенту нельзя отправлять один и тот же request_id как две разные команды в разных Issues. Для нового запроса генерируется новый ID.

### 5.2. Concurrency

Issue-запросы читают неизменяемый snapshot sidecar. Разные Issues можно обрабатывать параллельно: каждый runner имеет собственную рабочую копию SQLite, открывает её read-only и создаёт временные поисковые структуры в своём RUNNER_TEMP.

Повторная обработка одного Issue сериализуется по ключу Issue:

    concurrency:
      group: sfra-issue-${{ github.event.issue.number }}
      queue: max

cancel-in-progress не включается.

GitHub поддерживает queue: max для сохранения до 100 ожидающих запусков в concurrency group. При достижении лимита новые запуски всё ещё могут быть отклонены, поэтому одной настройки concurrency недостаточно для абсолютной гарантии. Источник: https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency

Для защиты от пропуска при перегрузке предусматривается recovery sweep (например, каждые 5 минут):
- находит открытые Issues с префиксом [SFRA] от разрешённых авторов;
- выделяет Issues без terminal status marker, со статусом PENDING или с устаревшим RUNNING;
- направляет их через тот же валидатор и тот же per-Issue concurrency group;
- перед выполнением повторно проверяет status marker, чтобы DONE/FAILED не запускались повторно.

Recovery sweep — страховка от задержанных/пропущенных событий и отменённых запусков; Issue остаётся долговременной записью запроса. Комментарии не запускают workflow, так как issue_comment отсутствует в триггерах.

## 6. Постоянное sidecar-хранилище

### 6.1. Наблюдаемое состояние текущей реализации

В ветке executor-1/sfra-indexer-session-1 README Исполнителя 1 указывает SQLite sidecar structure.sqlite3 во внешнем каталоге индекса. Workflow Stage B/C создаёт его в /tmp/sfra-vault-sidecar. Файл SQLite исключён через .gitignore (*.sqlite3, *.db).

Следовательно, действующий workflow подтверждает корректность индексации, но не сохраняет SQLite sidecar между независимыми GitHub Actions runs. Это необходимо устранить до полноценного Issue MVP. Стабильные Node ID и история версий существуют в SQLite, но исчезают вместе с временным runner, если база не переносится в постоянное хранилище.

### 6.2. Предлагаемое хранилище MVP

Предлагается отдельная ветка:

    sfra-index-state

Структура:

    .sfra-state/
      manifest.json
      structure.sqlite3
      search-state.sqlite3       # если E2 хранит отдельное постоянное состояние сущностей/алиасов

Ветка содержит только служебное состояние, не меняет ГП/ и не вливается в main.

manifest.json должен включать:
- protocol/state schema version;
- commit SHA Vault, для которого sidecar актуален;
- commit SHA версии индексатора;
- generation/manifest version;
- SQLite schema versions;
- количество активных документов/узлов;
- дату последней синхронизации;
- SHA-256 каждого SQLite файла.

structure.sqlite3 сохраняет Node ID, структурные узлы, node_versions, stale/ambiguous состояния и match events Исполнителя 1. Если E2 хранит собственный реестр сущностей/алиасов и подтверждённые аннотации, они должны находиться в постоянном search-state.sqlite3 либо в согласованной постоянной таблице, но не в ephemeral FTS.

FTS5 и Context Pack могут пересобираться/создаваться во временном каталоге на каждый запрос. Постоянная часть — идентичность Node ID, Content Hash, история версий и подтверждённые поисковые аннотации.

Конкретное разбиение DB-файлов требует согласования с Исполнителями 1 и 2. Главный инвариант — база с Node ID/историей не является временным артефактом runner.

### 6.3. Отдельный workflow синхронизации sidecar

Предусмотреть отдельный workflow, который обновляет sfra-index-state при изменении ГП/** или версии индексатора/поискового слоя:

1. Получить точный commit SHA Vault.
2. Получить текущую ветку sidecar.
3. Загрузить постоянные SQLite базы и manifest.
4. Запустить инкрементальную синхронизацию из текущего структурного индексатора.
5. Обновить согласованный поисковый state.
6. Выполнить checkpoint/close SQLite и проверить integrity.
7. Сформировать manifest с SHA-256 и source commit SHA.
8. Опубликовать новый commit только в sfra-index-state.

Этот workflow сериализуется общей группой:

    concurrency:
      group: sfra-index-state
      queue: max

cancel-in-progress не используется. Для защиты от пропущенного события отдельный scheduled catch-up сравнивает manifest с текущим default branch и обновляет sidecar до актуального состояния. История версий сохраняется в постоянной SQLite базе; каждое обработанное состояние не должно сбрасывать Node ID.

### 6.4. Issue worker — только чтение

Issue workflow:
- checkout Vault на конкретный commit SHA;
- checkout sfra-index-state на конкретный commit SHA;
- проверяет manifest.vault_commit_sha == checked_out_vault_sha;
- сверяет SHA-256 SQLite файла с manifest;
- открывает постоянную БД read-only;
- строит FTS5/временные структуры в RUNNER_TEMP;
- выполняет запрос;
- не записывает изменения в sfra-index-state, main или ГП/.

Если manifest не соответствует Vault snapshot, запрос остаётся PENDING с диагностикой INDEX_NOT_READY. Он не должен выполнять поиск по несогласованным данным. Recovery sweep повторит запрос после синхронизации sidecar.

Все фрагменты одного read_source читаются из одного закреплённого snapshot. Node ID + expected_hash проверяется до выдачи, а SHA-256 считается повторно от точного UTF-8 raw_text.

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

## 12. Что подтвердить с координатором/предыдущими исполнителями

1. Допускается ли отдельная публичная ветка sfra-index-state для постоянного хранения SQLite. Поскольку репозиторий публичный, ветка будет публичной.
2. Где хранится постоянная часть реестра сущностей/алиасов E2: в отдельном search-state DB или в общей базе. FTS5 при этом может быть временной.
3. Какой точный workflow/branch является источником актуального кода E1/E2 при sidecar refresh.
4. Требуется ли разрешать несколько авторов в SFRA_ALLOWED_ISSUE_AUTHORS, кроме текущего владельца репозитория.
5. Какой максимальный размер result comments считать операционным порогом. Проектное предложение — 45 KiB UTF-8 на одну часть.

---

**Статус:** транспортная архитектура GitHub Issues + Actions описана. Она не требует реализации MCP SDK для MVP. До повторной проверки аналитика workflow, приложение и постоянная ветка sidecar не создаются.
