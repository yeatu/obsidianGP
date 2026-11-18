# SFRA: cloud data plane без зависимости от личного компьютера

**Тип:** ANALYSIS, Issue #86  
**Автор:** A1  
**Проверенная база:** main, commit 2051d0ce6cdbceab1fc825c617708f8255266476  
**Дата:** 2026-11-18  
**Режим:** read-only. Production Vault, SQLite, sfra-state и реальные workflows не открывались и не запускались.

## 1. Итоговая рекомендация

Целевой runtime должен разделять три слоя:

1. **GitHub Issues** — приём структурированного запроса и канал ответа в исходном Issue.
2. **GitHub Actions на GitHub-hosted runners** — временное исполнение worker и SFRA application services. Runner не является хранилищем.
3. **Постоянный cloud data plane** — долговременное хранение исходного snapshot, индекса E1 и manifest с точной неизменяемой идентичностью.

Для первого безопасного cloud-only этапа можно использовать уже существующую remote Git source branch и sfra-state как источник данных, потому что E1 persistence workflow умеет получать удалённый Vault ref и восстанавливать индексную базу на hosted runner. Это даёт computer-independent execution, если все изменения Vault сначала опубликованы в remote source ref. Однако это следует считать **совместимым bootstrap**, а не окончательной масштабируемой архитектурой: SQLite хранится как Git blob в истории отдельной ветки, а текущий E3 verifier жёстко связан с локальными Git checkout и файловыми путями.

Рекомендуемое целевое направление — **immutable snapshot bundles в provider-neutral object storage + небольшой versioned snapshot catalogue + узкий read-only snapshot resolver/materializer**. GitHub остаётся control plane для запросов и ответов; Actions runner остаётся ephemeral executor; object storage хранит source package, SQLite sidecar и manifest дольше жизни runner. Managed application service с тёплым cache можно добавить позже, если измерения покажут, что клонирование/скачивание и холодный запуск на каждый запрос слишком дороги или медленны.

Ни AWS, ни Google Cloud, ни Azure на этом этапе не выбирается. Сначала нужно определить фактический размер Vault/SQLite, частоту синхронизации, запросную нагрузку, требования к latency и бюджет. Режимы object lock/retention не включать по умолчанию: некоторые варианты блокировки необратимы или требуют отдельной административной политики.

**Решение по безопасности:** не запускать production indexing, source reads, state publication или миграцию данных на основании этого анализа. Они требуют отдельного C/owner approval. Особенно важно получить явную disposition по существующему .github/workflows/sfra-state-persistence.yml: файл на main содержит push/workflow_dispatch триггеры и contents:write, но анализ не проверял repository settings, фактическую enablement и историю недавних запусков.

## 2. Подтверждённое текущее состояние

### 2.1. Где находятся исходные данные и индекс

| Слой | Фактическая реализация в main | Что это означает для cloud runtime |
|---|---|---|
| Source Vault | Дерево ГП/ находится в Git-репозитории, а существующий E1 workflow checkout-ит явно указанный Vault ref в vault/ с sparse-checkout ГП/. | Источник уже может быть получен на удалённом runner по конкретному commit SHA. Если изменения остались только на отключённом личном компьютере и не попали в remote source, cloud worker их прочитать не сможет. |
| Structural index E1 | SQLite state/structure.sqlite3; manifest state/manifest.json; orphan branch sfra-state. В README E1 перечислены текущие и stale узлы, версии, события сопоставления и полный raw Markdown в истории SQLite. | Это производный, но source-bearing артефакт. sfra-state хранит Git-историю manifest и DB, а не просто временный файл runner. |
| E2 search | GPT/Нейросеть/Проекты/Исполнитель 2/Сессия 1/Реализация/source/src/sfra_search/runtime.py. Открывает E1 DB read-only, импортирует текущие узлы в in-memory SQLite FTS5, выполняет один поиск и закрывает память. | Поисковый индекс не является постоянным хранилищем. Для каждого холодного процесса его нужно строить заново из E1 snapshot. |
| E3 snapshot/source | Этап В1/src/sfra_context_integrations/snapshot.py, source_reader.py, search_adapter.py. | Текущая реализация не transport-independent на уровне хранения: verifier требует локальные абсолютные paths, Git HEAD/branch/status, manifest-файл и SQLite-файл. |
| B1 Context Builder | Этап Б1/src/sfra_context_builder/. Пакет не импортирует GitHub Actions, E1/E2 runtime или SQLite. | Уже достаточно отделён от транспорта. Принимает SearchRequest/SearchBatch/resolver/SnapshotRef, сохраняет provenance и атомарно укладывает целые узлы/группы в бюджет. |
| V2.1 application services | Этап В2.1/ и Этап В1/src/sfra_context_integrations/application.py. SearchVaultService и ReadSourceService вызывают существующие E3/B1 сервисы. | Это подходящая граница между worker transport и SFRA Core. Новая облачная реализация не должна дублировать E1/E2/E3 логику. |
| V2.2 Issue Worker Core | Этап В2.2/src/sfra_issue_core/worker.py, projector.py. Core принимает IssueReaderPort, TransportStatusStorePort, application services и SnapshotRef. | Транспортные порты позволяют подключить облачное чтение и сохранение request status без переписывания retrieval. SafeResultProjector намеренно формирует только агрегаты. |
| W1 Web adapter | PR #92, synthetic-only Web adapter; hosted workflow и отдельная synthetic response projection. | Это доказательство транспортного механизма, а не production data plane. Он не должен ждать #86 и не должен получить доступ к реальному Vault. |

### 2.2. Что делает существующий E1 persistence workflow

Файл .github/workflows/sfra-state-persistence.yml на проверенной main содержит следующий поток:

1. Запуск по push на executor-1/sfra-indexer-session-1 при изменениях ГП/**, E1 реализации или самого workflow, а также ручной workflow_dispatch.
2. Checkout E1 implementation и отдельно выбранного Vault ref в два каталога. Vault commit фиксируется через git rev-parse HEAD.
3. Checkout orphan branch sfra-state, проверка её root history и allowlist файлов README.md, state/structure.sqlite3, state/manifest.json.
4. Restore ранее сохранённой SQLite в $RUNNER_TEMP, если база и manifest существуют. Иначе инициализация разрешается только явно.
5. E1 индексирует исходную папку в staging directory вне Vault.
6. Создаёт SQLite Backup API snapshot и manifest, проверяет integrity, проверяет allowlist state tree, сравнивает remote HEAD с базовым HEAD и выполняет fast-forward push в sfra-state.
7. Использует GitHub-hosted ubuntu-latest, concurrency group sfra-state-production, cancel-in-progress: false и workflow permission contents: write.

Это уже cloud-side ingestion/snapshot pipeline, но с ограничениями:
- Ветка состояния доступна по правам чтения репозитория; README E1 прямо отмечает, что SQLite содержит source text и исторические версии.
- Обновления DB записываются в Git history. Это удобно для текущего прототипа, но крупные SQLite snapshots со временем увеличивают .git, время clone/fetch и стоимость хранения. Реальное поведение дельта-сжатия Git зависит от структуры и изменений DB; размер репозитория и объём новых pack objects в рамках этого анализа не измерялись.
- SQLite — один большой бинарный файл. GitHub рекомендует держать репозиторий не более 10 GB, рекомендуемый предел одиночного файла — 1 MB, жёсткий лимит — 100 MB, push ограничен 2 GB. См. [GitHub repository limits](https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits).
- На каждого нового runner выполняется checkout и восстановление state. sfra-state не является быстрым read API или managed cache.

**Отдельная граница:** .github/workflows/sfra-e3-real-e1-integration.yml на main отключён fail-closed сообщением и exit 1 из-за исторического раскрытия source-derived metadata в публичных Actions logs (#53). Это не тот же workflow, что E1 state persistence. Файл persistence присутствует на main и его разрешённое состояние/операционная политика не установлены этим анализом. Нельзя автоматически делать вывод «real data уже запрещена в любом Actions workflow» только из отключения E3 integration workflow, но и нельзя считать persistence workflow одобренным для нового production data plane. Требуется решение C.

### 2.3. Локальные предположения E3

Текущая PinnedSnapshot содержит пути к:
- sidecar Git checkout;
- state/structure.sqlite3;
- state/manifest.json;
- Vault Git checkout;
- Vault root.

Её binder запускает Git subprocess, читает реальный HEAD обоих checkout, проверяет ветку sidecar sfra-state, clean status, вызывает E1 verify_state_directory, сверяет manifest и hash SQLite. Операционная проверка повторяет проверки путей, HEAD, branch, status, manifest digest и DB digest до/после операций.

E1 SourceReader далее получает локальные db_path и vault_root; E2SearchAdapter — путь к той же SQLite DB. Это хорошие integrity boundaries, но они пока выражены как локальная файловая модель. Сам по себе перенос worker на GitHub-hosted runner не делает snapshot verifier облачным: ему всё ещё нужны оба checkout и файловые пути.

## 3. Целевая модель и data-flow

### 3.1. Рекомендуемое разделение

- **Source authority:** remote Git source revision или отдельно согласованный browser-uploaded source package. У каждого импорта есть точная версия, а не плавающая ветка.
- **Ingestion:** hosted runner или управляемый cloud job строит E1 state в staging и публикует проверенный snapshot bundle.
- **Durable snapshot store:** object storage, включённое versioning, immutable keys, контроль манифеста и checksum.
- **Snapshot catalogue:** небольшой атомарно обновляемый индекс доступных snapshots. Содержит статус staged/verified/active/retired, schema/indexer version, revision identity, object version IDs, byte sizes и hashes.
- **Request control plane:** GitHub Issue с неизменяемой привязкой к request body digest, request ID и принятому SnapshotRef.
- **Execution:** GitHub-hosted runner или позже managed service materializes exact snapshot, затем запускает существующие application services.
- **Response:** ответ в originating Issue comment. Публикация контента разрешена владельцем, если это полезно запросу. Credentials и operational secrets не попадают в Issue.

### 3.2. Ingestion flow

~~~mermaid
flowchart TD
    A["Remote Vault Git ref or owner browser upload"] --> B["Ingestion event with exact source revision"]
    B --> C["GitHub-hosted runner / managed cloud job"]
    C --> D["E1 index_vault in isolated staging"]
    D --> E["Verify E1 DB, exact source hashes and manifest"]
    E --> F["Build immutable snapshot bundle"]
    F --> G["Object storage: versioned objects"]
    G --> H["Verify object version IDs and SHA-256"]
    H --> I["Atomic catalogue publish: snapshot = VERIFIED"]
    I --> J["New snapshot becomes eligible for requests"]
~~~

Порядок важен: catalogue/pointer нельзя переключать на новый snapshot, пока source bundle, DB, manifest и object versions не загружены и не проверены. При любой ошибке остаётся предыдущий active snapshot. Upload должен быть idempotent по source revision + indexer/schema version + deterministic manifest.

### 3.3. Query flow

~~~mermaid
sequenceDiagram
    participant U as ChatGPT Web/mobile
    participant GH as GitHub Issue
    participant A as GitHub-hosted Actions
    participant C as Snapshot catalogue
    participant O as Object storage
    participant S as SFRA Core/services
    U->>GH: Create marked request Issue
    GH->>A: issues.opened
    A->>A: Validate actor, title, body digest, request ID
    A->>C: Resolve one eligible snapshot once
    C-->>A: Exact immutable SnapshotRef + object version refs
    A->>O: Download exact object versions
    O-->>A: Source bundle + SQLite + manifest
    A->>A: Verify signatures, hashes and exact SnapshotRef
    A->>S: Run existing E1/E2/E3/B1/V2.1 services
    S-->>A: Context Pack / typed source result
    A->>GH: Post bounded response to originating Issue
    U->>GH: Read result comment
~~~

Участок от catalogue resolution до завершения source read должен работать с одной фиксированной идентичностью. Если object version отсутствует, manifest не совпадает, DB hash неверен или source version недоступен, worker возвращает typed stale/unavailable/integrity outcome. Он не перечитывает latest и не молча подменяет snapshot.

### 3.4. Что происходит с личным компьютером

Требование «компьютер выключен» достижимо только при условии, что **актуальный source revision уже опубликован в облачный источник**. Cloud runtime не может увидеть новые файлы, которые остались исключительно на отключённом устройстве. Это физическое ограничение, не особенность SFRA.

По текущему репозиторию исходный путь уже remote: executor-1/sfra-indexer-session-1 содержит Vault directory ГП/, а E1 workflow умеет checkout-ить удалённый ref. Если эта ветка является принятой source authority, initial import можно построить из уже опубликованного remote commit без подключения личного компьютера.

Если актуальный Vault ещё хранится только локально, потребуется одна начальная публикация:
- либо загрузка source archive через браузер/mobile UI в cloud intake;
- либо загрузка archive напрямую в object storage через короткоживущий presigned/resumable upload URL;
- либо публикация исходного содержимого в remote Git source repository, если размер/частота изменений укладывается в ограничения GitHub.

После начальной загрузки дальнейшая синхронизация должна запускаться от remote commit/event или от upload завершённого пакета. Ни один шаг не должен ждать или опрашивать домашний компьютер.

### 3.5. Incremental sync

Для каждого обновления:
1. Зафиксировать новую source revision: git commit SHA или immutable upload ID + SHA-256 exact package.
2. Вычислить idempotency key из source revision, E1 indexer version, SQLite schema version, manifest format version и index configuration.
3. Сравнить с последним verified catalogue entry. Не переиндексировать тот же source revision и ту же конфигурацию без причины.
4. E1 выполняет incremental indexing в отдельной staging DB. Изменённые/удалённые documents обрабатываются существующими E1 lifecycle semantics; история версий не подменяется полным snapshot из случайной копии.
5. Создать manifest с source revision, E1 schema/indexer version, source document count/bytes, DB bytes, exact DB SHA-256, source archive SHA-256, creation time и schema version.
6. Записать snapshot objects под уникальными immutable keys. Сразу получить storage object version IDs / generation numbers.
7. Повторно скачать или прочитать metadata конкретных versions и пересчитать SHA-256, чтобы убедиться, что опубликован именно тот payload.
8. Запустить E1 verifier на staging copy; только затем отметить snapshot VERIFIED.
9. Сменить активный catalogue pointer через compare-and-swap против ожидаемого предыдущего generation. При гонке проигравший job не перезаписывает winner: он сверяет опубликованный target и либо заканчивается как duplicate, либо повторяет выбор active snapshot.
10. Старые snapshots остаются доступными до истечения отдельно утверждённого retention window; не удалять их из-за одной неудачной синхронизации.

## 4. SnapshotRef, provenance и verifier continuity

### 4.1. Непреложные invariants

Существующая семантика должна сохраниться:
- Node ID — адрес структурного узла; не заменять поиск по Node ID на fuzzy lookup.
- Content Hash — SHA-256 точных UTF-8 байтов raw_text узла, без нормализации и усечения.
- Document Hash — SHA-256 целого исходного Markdown документа.
- Index generation — поколение соответствующего документа в E1.
- SnapshotRef — идентичность согласованной версии source + sidecar + manifest.
- Все операции поиска, resolve и чтения в одном запросе должны принадлежать одному SnapshotRef.
- Ошибка hash, manifest, storage generation, source revision или отсутствующий object version приводит к fail-closed результату; никаких fallback на текущий snapshot.

### 4.2. Два этапа эволюции SnapshotRef

**Bootstrap / совместимый режим:** пока durable source и E1 sidecar остаются в GitHub Git refs, можно сохранить текущую тройку SnapshotRef:
- vault_commit_sha — точный commit источника;
- sidecar_commit_sha — точный commit ветки sidecar;
- manifest_sha256 — SHA-256 точных UTF-8 bytes manifest.

Object store на первом шаге может выступать mirror/cache этих exact Git-backed snapshots, а не подменять идентичность. В таком режиме нельзя заменять sidecar commit произвольным storage version ID.

**Cloud-native режим:** если Git перестанет быть фактическим носителем sidecar/source snapshot, одной старой тройки уже недостаточно, чтобы честно описать provider object version. Тогда нужен новый версионированный SnapshotRef contract, например:
- source_revision — точный Git commit или immutable import revision;
- index_bundle_sha256 — digest SQLite sidecar bundle;
- manifest_sha256 — digest canonical manifest;
- source_object_version и index_object_version — opaque immutable object IDs/generation numbers;
- snapshot_id — детерминированный digest canonical identity tuple.

Это пример направления, не принятая схема. Имя, формат, миграция и совместимость должны быть утверждены C до реализации. **Нельзя выдавать object generation за Git SHA** или подменять semantics существующего sidecar_commit_sha.

### 4.3. Manifest и trust chain

Рекомендованный canonical manifest (схема подлежит C approval):
- manifest schema version;
- source repository/ref и exact source commit/import revision;
- E1 indexer version и SQLite schema version;
- object key + immutable version ID/generation для source bundle и SQLite DB;
- SHA-256 и byte size каждого полного object payload;
- source document count, node count и index generation counters;
- timestamp ingestion, workflow run ID, worker commit SHA;
- E1 verifier result/version;
- подписываемый digest canonical manifest и key ID подписи.

Manifest должен сериализоваться канонически до вычисления digest/signature. Подпись манифеста через управляемый KMS key — рекомендация для cloud-native trust boundary, не текущая функция main. Важно, чтобы signer имел отдельное narrowly scoped право публикации, а reader не мог менять ни manifest, ни objects.

### 4.4. Materialization и compatibility

Краткосрочно можно скачивать immutable source package и SQLite в новый $RUNNER_TEMP каталог, проверять их и затем использовать существующие E1/E2/E3 APIs. Но текущий E3 binder дополнительно требует Git checkout metadata и Git commands. Есть два варианта дальнейшей реализации:

A. **Git-compatible snapshot bundle:** object store сохраняет точные Git bundles/repositories плюс E1 state files. Runner воссоздаёт локальные Git checkouts точных commits, затем текущий binder работает без смены semantics. Это снижает изменение E3, но сохраняет Git complexity и может увеличить bundle size.

B. **Cloud snapshot provider:** новый E3 adapter/binder получает verified manifest + immutable object versions, проверяет signature/digests и создаёт доверенную PinnedSnapshot capability без Git command assumption. Это архитектурно чище для managed service/object storage, но требует отдельного пересмотра SnapshotRef и operation-boundary verifier.

Моя рекомендация: начать с A как bridge, если remote Git остаётся source authority. До перехода B зафиксировать отдельный C decision и contract. Не добавлять fallback-путь к latest в обеих схемах.

## 5. Варианты data plane

| Вариант | Достоинства | Слабые места / стоимость | Вывод |
|---|---|---|---|
| 1. GitHub source branch + sfra-state | Уже частично реализован; точный Git commit; manifests и DB в одном версионируемом workflow; минимальная новая инфраструктура; runner может всё checkout-ить без личного PC. | SQLite как бинарный blob в Git history; растущий .git; каждый запрос/ingestion клонирует или скачивает состояние; repo/file/push limits; доступ к branch связан с repo permissions; нет узкого data API. | Лучший bootstrap и переходный режим, если measured dataset size остаётся в GitHub supportable range. |
| 2. Versioned object storage + catalogue | Отделяет data lifecycle от кода/Issues; естественная модель immutable object versions; крупные архивы и SQLite не раздувают Git history; можно назначать отдельные IAM roles; lifecycle/replication/restore управляются отдельно. | Появляется новый storage adapter, OIDC trust policy, publisher/reader roles, catalogue, signing, monitoring; цена зависит от storage class, request count и egress; провайдер lock-in в object version API. | Рекомендуемый target durable data plane; начать с provider-neutral interface и не выбирать provider до измерений/решения C. |
| 3. Managed application/data service | Может держать warmed snapshot cache, уменьшить повторную загрузку DB и startup; дать narrow read-only API; скрыть storage provider за service boundary. | Дополнительная постоянно работающая cloud service/конфигурация, доступность, auth, deployment, monitoring и расход; риск случайно превратить сервис в новый retrieval implementation; нужно проектировать cache invalidation по SnapshotRef. | Опция Phase 2, если cold start/p95 latency/traffic обоснуют её. Не обязательна для первого cloud-only пилота. |
| 4. GitHub Actions artifacts/cache | Простая передача между job steps/runs; удобно для тестовых промежуточных файлов и отчётов. | Artifact/log retention настраивается и по умолчанию ограничена; runner эфемерен; storage quota зависит от GitHub plan; cache допускает замену/eviction и не является authoritative source. | Не использовать как durable Vault/SQLite store. Только temporary CI intermediate. |
| 5. GitHub Issues/comments как data store | Уже выбранный ChatGPT Web control/response channel; удобная адресация request ID, marker history и round-trip. | Comments предназначены для коммуникации, создают notifications, rate-limited; длинный полный документ раздувает Issue и историю; listing требует pagination; hard size limit в endpoint docs явно не опубликован. | Использовать как request/status/response channel, а не основное хранилище или постоянную базу исходных данных. |
| 6. Git LFS | Сохраняет большие бинарные blobs вне обычного Git object store, оставляя pointer в repository. | Отдельные quota и file-size limits; не решает catalogue, transactional publish, snapshot verifier и object retention. Для GitHub Free/Pro включённые LFS storage/bandwidth лимиты ограничены 10 GiB. | Возможный временный обход для крупных файлов в GitHub-центристском режиме, но не предпочитаемый конечный data plane. |

### 5.1. GitHub limits, которые влияют на выбор

Текущая документация GitHub рекомендует on-disk repository size не более 10 GB; одиночный Git object рекомендован до 1 MB, жёсткий предел — 100 MB; push size ограничен 2 GB. Большой бинарный SQLite snapshot в Git истории — следовательно, осознанный компромисс, не бесконечно масштабируемое решение. [Repository limits](https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits).

Git LFS использует pointer в Git repository, а actual large object хранит отдельно; per-file max зависит от плана (2 GB для Free/Pro, 4 GB Team, 5 GB Enterprise Cloud), включённые storage/bandwidth quotas также ограничены. Это может отодвинуть проблему размера файла, но не создаёт snapshot catalogue и verification semantics. [About Git LFS](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage), [Git LFS billing](https://docs.github.com/en/billing/concepts/product-billing/git-lfs).

GitHub-hosted runner получает новую VM на job; после завершения job VM decommissioned. Это отлично подходит для временного materialization и выполнения, но исключает runner filesystem как durable state. [GitHub-hosted runners](https://docs.github.com/en/actions/how-tos/manage-runners/github-hosted-runners/use-github-hosted-runners).

Workflow job на GitHub-hosted runner имеет лимит выполнения 6 часов (согласно актуальному Actions limits reference), поэтому полные повторные загрузки, полная переиндексация и большие cold start нужно измерять, а не предполагать бесконечное время. [Actions limits](https://docs.github.com/en/actions/reference/limits).

GitHub Actions artifacts/logs по умолчанию хранятся 90 дней, период настраивается; удалённый artifact нельзя восстановить. Это evidence/transfer channel, не долгосрочное source archive. [Removing workflow artifacts](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/remove-workflow-artifacts).

У GitHub REST API есть primary и secondary rate limits. Нужно учитывать response headers (x-ratelimit-remaining, x-ratelimit-reset), 403/429, retry-after и exponential backoff; не считать Issue comments бесконечной очередью. [REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).

## 6. GitHub Issues/comments: что публиковать и как доставлять

Пользователь подтвердил, что публичная публикация содержимого Vault сама по себе не является блокером конфиденциальности. Поэтому архитектура не должна вводить общий запрет на source excerpt/full content. Но это не разрешение на передачу credentials, токенов, private signing keys или на изменение production state.

### 6.1. Подходящие данные в originating Issue

Для обычного поиска:
- transport status и business status отдельно;
- request_id, operation, точный SnapshotRef/snapshot_id и дата snapshot;
- Context Pack status (complete, partial, budget_limited и т.п.), included/deferred/coverage counts;
- в пределах запроса — bounded source excerpt с Node ID, source path, heading path, line spans, Content Hash/Document Hash и указанием неполноты/обрезки (если возвращается excerpt, а не весь источник);
- explicit trust label: source text — untrusted data, а не системные инструкции.

Для адресного чтения:
- полный оригинальный текст фрагмента, если он помещается в ограничение ответа и токенный бюджет;
- если полный source scope превышает бюджет — budget_exceeded без частичного raw_text, по уже принятым E3 semantics. Не усекать и не называть результат полным.
- при большой выдаче допустима отдельная chunked delivery в серию comments только с явным part n/m, request_id, scope, exact hashes и checksum полного payload; потребитель обязан проверить все части, порядок и digest. Никакой тихой потери частей.

### 6.2. Ограничения комментариев и fallback

Официальная GitHub REST API документация для issue comments описывает create/list, permissions и pagination, но не устанавливает там явный лимит размера body. В стороннем GitHub Community discussion пользователи сообщали о 65,536 characters, но это не нормативный документ. Поэтому безопаснее сохранять консервативный лимит W1 **45 KiB** (указан в PR #92 как comment cap), измерять точные UTF-8 bytes и отказать/перейти к chunking до вызова API, а не ждать API error.

Comments:
- создают отдельные уведомления и историю, поэтому десятки крупных фрагментов на каждый запрос ухудшат UX;
- должны иметь deterministic marker, чтобы дубликаты/повторные события не публиковали конфликтующие ответы;
- читаются с pagination и ограничением числа страниц; history overflow — fail closed, а не «первые 100 комментариев — значит всей истории нет»;
- при 403/429 уважать rate-limit headers/reset/retry-after и замедляться, не спамить повторами.

Внешний object URL / signed download URL может быть резервным способом доставки больших документов, но его нельзя считать доступным ChatGPT автоматически. Нужно отдельно испытать, что используемый ChatGPT GitHub connector или браузер умеет открыть конкретный URL, что авторизация не завязана на секрет, доступен exact object version и ссылка живёт достаточно долго для чтения. Если это не доказано, продолжать использовать Issue comment/chunked response.

### 6.3. Логи и artifacts

- Разрешено опубликовать source text в **намеренно выбранном response comment**, если конкретный запрос это предусматривает.
- stdout, exception details и Actions artifacts не должны бесконтрольно дублировать полный ответ. По умолчанию — aggregate counters, duration, status code, workflow/worker SHA, request ID и snapshot digest.
- Не выводить credentials, JWT, signed URLs, KMS tokens, environment values, сырые Issue body, stack traces с env values.
- Это operational separation и least-exposure практика, а не заявление, что пользователь запрещает публикацию самих заметок.

## 7. Security / access design

### 7.1. Trust boundaries

1. **Issue body — untrusted input.** Только validated event metadata + request protocol allowlist определяют доступные операции. Body не должен выбирать storage bucket/key, cloud project, arbitrary object URL или snapshot из непроверенного namespace.
2. **GitHub event identity** — проверить exact repository, action issues.opened, owner-authored Issue, sender identity, issue author, [SFRA] marker/title, Issue number и event/body digest race. Не доверять только username полю из body.
3. **Cloud identity** — не хранить долгоживущий cloud key в GitHub Secrets, если можно использовать OIDC federation. GitHub документирует, что OIDC выдаёт JWT, который cloud provider обменивает на access token; provider должен иметь trust condition, чтобы untrusted repo/workflow не получил роль. [OIDC in cloud providers](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-cloud-providers), [OIDC token claims](https://docs.github.com/en/actions/reference/security/oidc).
4. **Object storage** — immutable versions; request runner получает read-only permission к точным snapshot objects. Он не может их перезаписать или удалить.
5. **Ingestion publisher** — отдельная идентичность, которая может записывать новые snapshot objects и обновлять catalogue pointer через narrowly scoped CAS, но не удалять старые snapshots и не менять уже опубликованные versions.
6. **Retention operator** — отдельно защищённая human/admin role для destructive deletion/retention operations; не доступна обычному query worker.
7. **Response publisher** — минимальный GitHub token только для чтения нужного Issue, чтения marker comments и создания comments; без contents:write, actions:write и cloud snapshot write.

### 7.2. OIDC / short-lived credentials

Для GitHub Actions рекомендован OIDC federation вместо long-lived cloud access keys:
- job получает permission id-token: write только в шагах, которым нужен cloud token;
- cloud provider проверяет issuer, audience, subject, repository/repository_id, owner/owner_id, workflow reference, branch/ref, event name и environment;
- query role ограничивается read-only exact snapshot namespace;
- ingestion role допускает только write immutable snapshot path и compare-and-swap catalogue update;
- delete/retention rights вынесены отдельно;
- access token короткоживущий, не логируется, не сохраняется в artifacts, не передаётся в Issue payload.

Точная доступность и формат OIDC immutable subject claims следует подтвердить на конкретном репозитории во время настройки. Trust policy не должна разрешать любой workflow в любом branch/PR автоматически.

### 7.3. Secrets vs source content

Владелец разрешает публичную публикацию источников. Это не снижает требования к:
- GitHub token, OIDC JWT, KMS signing keys, storage credentials, API keys;
- key rotation, permission scopes, expiry;
- audit records, integrity verification и approvals;
- предотвращению произвольной записи/удаления snapshots.

Encryption in transit (TLS) и at-rest encryption должны быть включены на уровне выбранного cloud provider; ключи управляются отдельной identity/KMS. Это защита cloud credentials и целостности инфраструктуры, а не попытка ввести скрытую приватность заметок вопреки предпочтению владельца.

### 7.4. Immutability and retention

Начать с object versioning + checksum-verified immutable object key, без необратимого WORM lock. После определения retention policy C может выбрать retention lock:
- S3 Object Lock работает на object versions и поддерживает Governance/Compliance; Compliance retention нельзя сократить или удалить до expiry. [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html).
- Google Cloud Storage Object Versioning сохраняет noncurrent versions и допускает управление lifecycle; storage cost учитывает все версии. [GCS Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning).
- Google Bucket Lock делает bucket retention policy неизменяемой и это irreversible action. [GCS Bucket Lock](https://docs.cloud.google.com/storage/docs/bucket-lock).
- Azure Blob immutable storage поддерживает time-based retention и legal hold. [Azure immutable storage](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-storage-overview).

Не включать compliance-grade lock только ради слова immutable. Сначала согласовать retention window, удаление по запросу владельца, litigation/hold needs и стоимость исторических versions.

## 8. Options / provider choice — без преждевременного выбора

### 8.1. Object storage providers

| Provider family | Доступные возможности, которые подходят | Риски / что проверить до выбора |
|---|---|---|
| AWS S3 | Versioning, Object Lock per version, Governance/Compliance retention, lifecycle; подходит под immutable bundle + manifest. | Нужны bucket/IAM/KMS policy, costs by region/storage class/requests/egress, role trust conditions, restore tests. Compliance mode может запрещать удаление даже root. |
| Google Cloud Storage | Object Versioning, generation IDs, Object Retention Lock и Bucket Lock; version ID подходит для exact locator. | Bucket Lock irreversible; lifecycle/version costs; verify service identity and access scope. |
| Azure Blob Storage | Blob versioning, immutable WORM policies, legal hold/time-based retention, soft delete. | Region/account configuration, version-level retention semantics, lifecycle and role scope. |

Выбор зависит не только от unit price. По официальной Google Cloud pricing page основные cost drivers включают storage class/region, data processing/operations, retrieval fees, inter-region replication и network egress. Это общие факторы для оценки object-store economics; точный estimate потребует real dataset size and access pattern, которых этот анализ не измерял. [Cloud Storage pricing](https://cloud.google.com/storage/pricing).

### 8.2. Какие измерения нужны до C provider choice

| Метрика | Зачем нужна |
|---|---|
| Полный размер ГП/ archive (bytes) | Стоимость одного initial transfer и cold materialization. |
| SQLite DB size и годовой рост | Ограничение Git single blob и object storage growth. |
| Размер изменения на одну source revision | Выбор full snapshots vs delta packages / document-level blobs. |
| Сколько source docs и nodes | Время E1 indexing и verification. |
| Частота updates per day/week | Ingestion runtime/compute and storage churn. |
| Queries per day/week и read scopes | Download/egress/GET cost, managed cache justification. |
| Cold/warm p50/p95 | Нужно ли постоянно прогретое API. |
| Snapshot retention policy | Object version lifecycle, backup cost, deletion semantics. |
| Region/data residency | Выбор region, latency и regulatory constraints. |
| Budget ceiling | Условие C provider and architecture approval. |

Не выдавать ценовую оценку в USD до получения этих показателей. Считать ежемесячную стоимость как: active+retained snapshot bytes × storage rates + upload/download/GET/PUT/list calls + network transfer + indexing/verification compute + optional managed API uptime/cache + backup/replication + observability/KMS. Для full-version storage учитывать, что versions хранят целые objects, а не всегда diffs.

## 9. Надёжность, recovery и failure modes

| Failure mode | Требуемое поведение |
|---|---|
| Upload завершился не полностью | Snapshot остаётся STAGED; active catalogue pointer не меняется; cleanup только после согласованного TTL. |
| Manifest/DB/source hash mismatch | integrity_error; object bundle не публикуется как VERIFIED; текущий active snapshot остаётся прежним. |
| Object version missing/deleted | Не подбирать latest; fail closed и operational alert. |
| Два ingestion jobs одновременно | CAS на active pointer; один winner; второй повторно сверяет expected current generation, не перезаписывает. |
| Source commit переписан/удалён из Git | Immutable imported source bundle сохраняет содержимое exact source revision независимо от branch movement. |
| Workflow runner умер | Повторный job использует тот же idempotency key; незавершённая staged upload не становится активной. |
| GitHub API 403/429 | Retry-after/rate-limit reset, exponential backoff, bounded attempts, safe status. |
| Comment post упал после service execution | At-least-once service execution с deduped terminal markers, не заявлять exactly-once. Recovery — отдельный request ID/новый Issue, либо явно утверждённый retry marker без удаления истории. |
| Snapshot истёк из retention до запроса | Request получает typed expired/stale result; не rebinding на latest. Каталог должен учитывать pending requests/pins. |
| Provider outage | Fail closed с retriable unavailable; не переключаться на другую версию или provider без явно идентичного verified bundle. |
| Secret/token compromise | Revoke/rotate identity, audit role usage, disable workflow environment; source data checksum не заменяет credential rotation. |

### 9.1. Backup/restore

- Основной snapshot storage должен иметь versioning и регулярную проверку восстанавливаемости.
- Backup может быть второй copy/region, но на первом этапе достаточно сначала доказать exact same-region restore и hash verification.
- Отдельно сохранять signed manifest/catalogue metadata; данные без доступного manifest не являются валидным snapshot.
- Retention policy должна покрывать все snapshots, на которые ещё ссылаются незавершённые/повторно читаемые Issues; удалять только когда ссылки истекли и owner retention policy это разрешает.
- Restore test обязан материализовать конкретную версию и снова прогнать E1 verifier/digest validation, а не просто проверить наличие object key.

## 10. Стоимость и latency: trade-offs

### 10.1. GitHub-only bootstrap

Плюсы:
- Уже есть workflow и manifest contract;
- нет новой cloud provider subscription/configuration;
- exact source commit and sidecar commit легко выразить existing SnapshotRef;
- E1/E2/E3 можно materialize без большой архитектурной переделки.

Минусы:
- каждый холодный job скачивает source/sidecar;
- E2 строит in-memory FTS index на каждый новый процесс;
- SQLite version в Git history и repository growth;
- branch write credential и query read credential смешаны в одном Actions/workflow design, если не разделить workflow identity;
- hard limits GitHub single file/pack/push.

Годится для bootstrap, пока фактический размер и частота обновлений невелики. Не надо мигрировать данные только ради моды на облака; но и не надо считать Git blob долгосрочным object store.

### 10.2. Object store + ephemeral runner

Плюсы:
- durable snapshot вне runner;
- exact object version download по request snapshot;
- разделение publisher vs reader roles;
- GitHub repository хранит код/manifest schema/request control, а не весь data history;
- scale storage/retention отдельно от CI compute.

Минусы:
- query job всё равно может скачивать полный source+DB;
- добавляет provider-specific IAM/OIDC, catalogue and new E3 snapshot provider;
- cold-start download and E2 index rebuild can dominate latency.

Это лучший компромисс для первой target архитектуры, если size metrics подтверждают, что Git history уже становится неудобным.

### 10.3. Managed service with warm snapshot cache

Плюсы:
- read API сразу получает cached E1 DB/source, не скачивает весь пакет на каждый request;
- можно держать ограниченный набор immutable snapshots warm;
- меньше cold-start latency и меньший Actions job payload.

Минусы:
- постоянно работающий cloud service либо managed container warm pool;
- дополнительная auth/network/API availability boundary;
- нужно инвалидировать cache по exact SnapshotRef, а не по mutable latest;
- ещё один production service требует отдельного deployment, monitoring, scaling and cost budget.

Только Phase 2, если p95 latency или query volume делают runner-per-request непривлекательным. Не нужно одновременно строить object store, managed API и новый DB schema на первом шаге.

## 11. Этапы реализации и approval gates

| Stage | Содержание | Кто решает / acceptance gate |
|---|---|---|
| 0. Data inventory | Измерить source archive size, SQLite bytes, file count, growth, update frequency, expected requests, latency target and budget. | Owner/C подтверждает цифры и предел затрат. Не читать production data автоматически ради измерения; использовать уже доступные manifest/metadata или отдельно разрешённую процедуру. |
| 1. Bootstrap cloud-only | Подтвердить, что source revision уже опубликована в remote branch; построить synthetic E1/E2/E3 materialization tests на hosted runner; проверить no-PC flow. | C отдельно определяет disposition текущего sfra-state persistence workflow и разрешает controlled synthetic tests. |
| 2. Snapshot storage adapter design | Provider-neutral ObjectStorePort, SnapshotCataloguePort, immutable version identity, manifest format, staging/verified/active state. | C approve architecture + SnapshotRef v2 compatibility decision before implementation. |
| 3. Synthetic object-store proof | Only synthetic archive/SQLite fixture; upload, version, download exact version, tamper/partial upload, CAS concurrency and restore. | A review + C acceptance. No production credentials/source. |
| 4. Initial cloud import | Browser/mobile/remote source import to staging, full hash verification, initial source+DB snapshot. | Owner explicitly approves source of truth and import path; one-time upload action if source is not already remote. |
| 5. Incremental synchronization | Remote source commit → hosted ingestion → immutable new snapshot → verify → atomic catalogue switch. | Separate E implementation issue + A review + C release/merge gate. |
| 6. Read-only production pilot | One marked request, pinned snapshot, read-only E1/E2/E3/V2.1, bounded originating Issue response; rollback and audit. | Explicit C/owner production pilot approval, plus the separately reviewed cloud SnapshotRef provider/materializer and Web response-worker path, each with its own exact-head A review and C acceptance; any production source-read activation still requires a separate explicit C/owner decision. Historical local-adapter work is not a prerequisite for the cloud-only Web route. |
| 7. Managed data service (optional) | Warm cache/service, read-only API, scaling/monitoring. | Only if measured latency/traffic requires it; separate C decision and issues. |

### 11.1. Нужные engineering streams после C approval (не создаются этим анализом)

1. **Snapshot storage contract** — provider-neutral immutable object references, manifest v2, signature/digest validation and catalogue state transitions.
2. **Cloud ingestion adapter** — initial import, incremental source revision ingestion, E1 staging, verify-before-publish and CAS pointer.
3. **Cloud snapshot materializer** — fetch exact object versions to ephemeral runner or managed service; fail closed on mismatch.
4. **E3 cloud snapshot provider** — adapt SnapshotRef/verifier semantics without Git checkout assumption, or implement Git-compatible object bundles as bridge.
5. **Query worker adapter** — bind issue request to one snapshot, use current V2.1/V2.2 ports, bounded result response. W1 remains synthetic until all explicit gates are passed.
6. **Operational/retention layer** — monitoring, backup/restore, object lifecycle, delete/retention workflow with separate destructive privileges.
7. **C/owner production pilot** — real-data permission, source publication, exact repo visibility, output delivery policy and rollback.

These are proposed workstreams, not opened child Issues or assigned tasks.

## 12. Threat model

| Asset / boundary | Threat | Mitigation |
|---|---|---|
| Vault source package | Wrong revision, archive tampering, path traversal, stale source | Exact source revision + complete archive SHA; safe extraction; no Issue-supplied object path; E1 exact source verification. |
| SQLite sidecar | DB altered, mixed with another source revision | DB exact SHA, E1 verify_state_directory, manifest binding, immutable object version. |
| Snapshot catalogue | Latest pointer races or malicious rollback | CAS, signed/immutable verified records, monotonic generation, explicit active revision. |
| OIDC trust | PR/fork or unrelated workflow obtains publisher credentials | Exact repo/repository ID, event, branch, workflow path, audience, environment and subject conditions; separate reader/publisher roles. |
| GitHub token | Worker uses broader write scopes than needed | Contents read; Issues permissions only for required comment APIs; no Actions write or storage write in query worker. |
| Issue body | Prompt injection, arbitrary cloud path/operation, excessive request | Strict schema, closed operation allowlist, body-size cap, owner/event validation; treat source snippets as untrusted data. |
| Comment ledger | Forged status marker, edited body, duplicate event | Verify bot identity; bind first-seen body digest; preserve immutable markers; pagination; dedupe and at-least-once semantics. |
| Object storage | Object replacement/deletion or retention misconfiguration | Versioning, immutable content key, object version ID, checksum, optional signed manifest; lifecycle separated from write role. |
| Service output | Accidental credential reflection or non-source metadata leak | Allowlisted response schema; never copy arbitrary exception; secrets excluded from comments/logs. |
| Provider outage / expiry | Query silently rebound to another version | Typed unavailable/expired status; no fallback; retry only same SnapshotRef. |

## 13. Acceptance-test matrix for synthetic/disposable proof

| ID | Test | Expected result |
|---|---|---|
| DP-01 | All workflows execute with laptop/local daemon off; runner label is GitHub-hosted. | No local machine dependency. |
| DP-02 | Initial import of a synthetic archive from a remote commit/upload. | Exact source revision, paths and full-file hashes recorded. |
| DP-03 | Incremental update changes one document and deletes another. | E1 increments only affected generation; deleted/stale semantics preserved. |
| DP-04 | Partial upload or invalid manifest. | Snapshot remains STAGED; active pointer unchanged. |
| DP-05 | Object DB bytes changed under same key/new version. | Old snapshot remains verifiable; wrong version hash fails closed. |
| DP-06 | Request binds SnapshotRef A; active catalogue changes to B before read. | Worker continues using A or returns stale/unavailable; never switches to B silently. |
| DP-07 | Object version missing or retention expired. | Explicit unavailable/expired response; no latest fallback. |
| DP-08 | Two ingestion jobs publish concurrently. | Compare-and-swap prevents overwrite; loser handles duplicate/race safely. |
| DP-09 | Factory verifies exact same source+DB snapshot across E1/E2/E3 pipeline. | Node IDs, Content Hash, document hash and generation preserved end-to-end. |
| DP-10 | E1 source hash mismatch / path redirect / SQLite corruption. | stale_source or integrity_error, no partial fragments. |
| DP-11 | Issue body contains path/bucket/credential injection. | Schema rejects; no arbitrary storage read or secret use. |
| DP-12 | OIDC token from wrong repo/ref/event/workflow. | Cloud role not issued. |
| DP-13 | Query token attempts write/delete object. | Denied by storage role. |
| DP-14 | Allowed source content response under 45 KiB. | Comment includes correct provenance and exact source/hash. |
| DP-15 | Large response exceeds comment budget. | Explicit chunking or bounded budget_exceeded; no hidden truncation. |
| DP-16 | GitHub REST API 403/429/secondary throttle. | Backoff; terminal status avoids duplicate/conflicting comments. |
| DP-17 | Runner crashes after service call before terminal comment. | At-least-once execution and deterministic recovery; no exactly-once claim. |
| DP-18 | Restore a retained previous snapshot. | Exact same SnapshotRef/object versions and hashes verify; no reindex drift. |
| DP-19 | Audit log inspected. | Contains request ID, worker/SnapshotRef identity and aggregate status; no credentials. Intended response comment may contain approved source payload. |
| DP-20 | Real-data path test attempted before C approval. | Fail closed / not available; no production checkout or mutation. |

## 14. C / owner decisions needed before real-data implementation

1. **Source authority:** is the existing remote branch executor-1/sfra-indexer-session-1 with ГП/ the canonical Vault source, or should initial import land in another remote repository/object store?
2. **Current persistence workflow:** is .github/workflows/sfra-state-persistence.yml still an approved production ingestion path, or must C explicitly suspend/rework its contents:write state publication before any new rollout? The workflow file is present; this analysis did not execute it or inspect repository-side workflow settings.
3. **Durable store choice:** retain GitHub Git state as bootstrap, move to object storage, or choose provider after size/cost measurements?
4. **Snapshot contract:** approve bridge using Git commit identities or a new versioned SnapshotRef including cloud object version identities?
5. **Provider and region:** AWS S3, Google Cloud Storage, Azure Blob, or other; region, encryption/KMS key ownership, IAM, OIDC trust policy.
6. **Retention/deletion:** how many versions or days; whether user can request immediate removal; backup/replication requirements; no irreversible WORM retention until C explicitly approves.
7. **Output scope:** allowed source content per operation (node/parent/neighbors/document), max inline response bytes/tokens, when to chunk, and whether any cloud object download link is supported by the actual ChatGPT Web GitHub connector.
8. **Real-data pilot:** exact named owner, target snapshot, workflow permissions, rollout window, monitoring and rollback procedure.
9. **Prerequisites:** verifier chain #36/#51/#67/#79 is accepted via C decision #96; independently review and C-accept the Web response path and cloud SnapshotRef provider/materializer at their own exact-head gates. Any production source-read capability requires a separate explicit C/owner activation decision. Historical held local-adapter tasks #38 and #40 are not prerequisites for the Web/cloud-only architecture. A positive cloud design analysis is not authorization to bypass any production gate.

## 15. Conclusion

SFRA can run without the owner's computer being online. The current repository already contains a partial cloud execution/ingestion path, but the E3 snapshot boundary is still local-file/Git-checkout-shaped and the durable E1 sidecar lives in Git history. The first safe step is to use the existing remote source revision and hosted runners as a controlled bootstrap, with a clear C decision on current persistence workflow permissions. The sustainable target is versioned immutable snapshot storage and a small cloud snapshot provider, with GitHub Issues/Actions remaining the user-facing control/response path.

The invariant is not «always use the newest data». It is **use exactly the snapshot that the request was bound to, or fail closed**. Cloud storage, runners, managed service and GitHub comments are replaceable infrastructure around that invariant; none may weaken Node ID, Content Hash, document provenance, or snapshot verification.

**No production migration, real-data execution, workflow run, cloud provisioning, credential change or implementation issue was created as part of this analysis.**

## References

### Repository evidence
- [E1 persistence workflow](https://github.com/yeatu/obsidianGP/blob/2051d0ce6cdbceab1fc825c617708f8255266476/.github/workflows/sfra-state-persistence.yml)
- [Disabled E3 real integration workflow](https://github.com/yeatu/obsidianGP/blob/2051d0ce6cdbceab1fc825c617708f8255266476/.github/workflows/sfra-e3-real-e1-integration.yml)
- [E1 structural indexer README](https://github.com/yeatu/obsidianGP/blob/2051d0ce6cdbceab1fc825c617708f8255266476/GPT/Нейросеть/Проекты/Исполнитель%201/Сессия%201/Реализация/README.md)
- [E1 state verifier](https://github.com/yeatu/obsidianGP/blob/2051d0ce6cdbceab1fc825c617708f8255266476/GPT/Нейросеть/Проекты/Исполнитель%201/Сессия%201/Реализация/sfra_indexer/state.py)
- [E1 incremental indexer](https://github.com/yeatu/obsidianGP/blob/2051d0ce6cdbceab1fc825c617708f8255266476/GPT/Нейросеть/Проекты/Исполнитель%201/Сессия%201/Реализация/sfra_indexer/indexer.py)
- [E2 one-shot runtime](https://github.com/yeatu/obsidianGP/blob/2051d0ce6cdbceab1fc825c617708f8255266476/GPT/Нейросеть/Проекты/Исполнитель%202/Сессия%201/Реализация/source/src/sfra_search/runtime.py)
- [E3 snapshot binder](https://github.com/yeatu/obsidianGP/blob/2051d0ce6cdbceab1fc825c617708f8255266476/GPT/Нейросеть/Проекты/Исполнитель%203/Сессия%201/Реализация/Этап%20В1/src/sfra_context_integrations/snapshot.py)
- [E3 source reader](https://github.com/yeatu/obsidianGP/blob/2051d0ce6cdbceab1fc825c617708f8255266476/GPT/Нейросеть/Проекты/Исполнитель%203/Сессия%201/Реализация/Этап%20В1/src/sfra_context_integrations/source_reader.py)
- [B1 Context Builder README](https://github.com/yeatu/obsidianGP/blob/2051d0ce6cdbceab1fc825c617708f8255266476/GPT/Нейросеть/Проекты/Исполнитель%203/Сессия%201/Реализация/Этап%20Б1/README.md)
- [V2.1 application services README](https://github.com/yeatu/obsidianGP/blob/2051d0ce6cdbceab1fc825c617708f8255266476/GPT/Нейросеть/Проекты/Исполнитель%203/Сессия%201/Реализация/Этап%20В2.1/README.md)
- [V2.2 Issue Worker Core](https://github.com/yeatu/obsidianGP/blob/2051d0ce6cdbceab1fc825c617708f8255266476/GPT/Нейросеть/Проекты/Исполнитель%203/Сессия%201/Реализация/Этап%20В2.2/src/sfra_issue_core/worker.py)
- [Coordinator cloud-only direction and owner approvals, #75](https://github.com/yeatu/obsidianGP/issues/75)
- [Owner-approved security disposition #53](https://github.com/yeatu/obsidianGP/issues/53)
- [Synthetic Web adapter #77](https://github.com/yeatu/obsidianGP/issues/77)

### Platform documentation (checked 2026-11-18)
- [GitHub-hosted runners: a new VM per job, decommissioned after completion](https://docs.github.com/en/actions/how-tos/manage-runners/github-hosted-runners/use-github-hosted-runners)
- [GitHub Actions OIDC with cloud providers](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-cloud-providers)
- [GitHub OIDC claims and immutable subject claims](https://docs.github.com/en/actions/reference/security/oidc)
- [GitHub repository and file/push limits](https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits)
- [GitHub Actions execution limits](https://docs.github.com/en/actions/reference/limits)
- [GitHub Actions artifact retention](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/remove-workflow-artifacts)
- [GitHub LFS file limits](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage)
- [GitHub REST comments API](https://docs.github.com/en/rest/issues/comments?apiVersion=2022-11-28)
- [GitHub REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- [Amazon S3 versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html)
- [Amazon S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [Google Cloud Storage Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
- [Google Cloud Storage Bucket Lock](https://docs.cloud.google.com/storage/docs/bucket-lock)
- [Azure Blob immutable storage](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-storage-overview)
- [Google Cloud Storage pricing components](https://cloud.google.com/storage/pricing)
