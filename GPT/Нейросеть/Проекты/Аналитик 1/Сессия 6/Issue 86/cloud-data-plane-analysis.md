# SFRA: cloud data plane и компьютер-независимая синхронизация

**Task:** Issue #86  
**Agent:** A1 / Role A  
**Analysis baseline:** main 9ba9d0403de0683c97938d0d323d96799157fc57  
**Date:** 2026-11-18  
**Mode:** read-only architecture analysis  
**Status:** proposed for C/owner decision; no provider selected and no production rollout authorized

## 1. Executive summary

SFRA уже отделяет бизнес-логику от транспортов, а GitHub Actions может выполнять W1 на GitHub-hosted runner без включённого личного компьютера. Но ephemeral runner не является источником долговременного состояния. Для полноценного computer-independent режима отдельно нужны:

1. **Durable source and snapshot storage** с неизменяемой идентичностью версий.
2. **Computer-independent ingestion/sync**, доступный через браузер/mobile или cloud-to-cloud.
3. **Ephemeral execution** на GitHub-hosted runners или другом управляемом compute.
4. **Narrow request/response transport** через GitHub Issues, не превращающий Issue history в базу данных.
5. **Snapshot materialization and verification**, сохраняющие существующие E1/E2/E3 guarantees.

Рекомендованная целевая схема: **Git как источник версий исходного Vault; object storage как долговременное хранилище immutable snapshots и SQLite sidecar; GitHub Actions как эфемерный executor; существующие SFRA application services как единственный слой retrieval/read logic; GitHub Issue как control plane и основной канал ответа**.

Это не требует выбора конкретного cloud provider сейчас. Для первой итерации можно сохранить GitHub как source-of-truth и использовать текущий SnapshotRef/Git checkout pipeline, а sidecar постепенно вынести в object storage. При миграции нельзя просто заменить Git paths на object keys: текущий E3 binder проверяет реальные Git HEADs, ветку sidecar, чистоту checkout, manifest bytes и SQLite digest. Для сохранения совместимости потребуется либо materializer, восстанавливающий точные Git snapshots во временных каталогах, либо отдельная версия snapshot-storage contract и C approval.

**Не запускались** workflow #53, реальные E1/Vault операции, production SQLite/sidecar, cloud provisioning, upload, migration или sync. В ходе анализа читались только код, контракты, workflows и Issue/PR metadata.

## 2. Цели, ограничения и утверждённые решения

### 2.1. Целевая пользовательская цепочка

ChatGPT Web/mobile → GitHub Issue → GitHub Actions on GitHub-hosted runner → SFRA Core/services → response в исходном Issue → ChatGPT читает response.

Личный компьютер владельца не является runtime-компонентом. Запрещённые зависимости: self-hosted runner, постоянно работающий домашний компьютер, локальный daemon/tunnel, локальный MCP endpoint.

### 2.2. Что уже утверждено

- Issue #75 выбирает GitHub Issues + GitHub Actions как первый Web-facing transport поверх существующих V2.1/V2.2 services. W1 разрешён только synthetic-only; production Vault, production SQLite/sidecar и read_source runtime не разрешены этим решением.
- Issue #81 задаёт trusted-process threat model для PinnedSnapshot. Arbitrary hostile code в том же Python process не является защитной целью, но invalid construction, subclass substitution, stale/mismatched snapshots и fail-closed operation boundaries остаются обязательными.
- C1 принял verifier chain #36/#51/#67/#79 после независимого A1 review; PR #87 merged в main на 9ba9d0403de0683c97938d0d323d96799157fc57. Это не включает production read_source.
- В Issue #75 владелец прямо разрешил публикацию содержимого Vault и source-derived metadata как таковую. Нельзя вводить blanket content redaction. Credentials/secrets, provenance, integrity, authorisation и production-operation gates остаются защищёнными.
- Issue #53 / #75 запрещают повторно включать или запускать прежний real-Vault persistence workflow без отдельного C/owner approval.
- W1 в PR #92 остаётся synthetic-only. На момент анализа его base — старый 2051d0ce6cdbceab1fc825c617708f8255266476, тогда как current main уже 9ba9d0403de0683c97938d0d323d96799157fc57. Это самостоятельное rebase/review/acceptance действие W1 lane, не prerequisite для этого анализа.

### 2.3. Важное разграничение

Публичность контента не равна разрешению на production ingestion или operations. Публикация может быть допустима по предпочтению владельца, но чтение/индексация реального Vault, запуск workflow, изменение sidecar и production state всё равно требуют отдельного согласования.

## 3. Текущее состояние по репозиторию

Факты ниже выведены из tracked source, contracts и workflow definitions на указанном main baseline. Реальное содержимое Vault и sidecar не читалось.

### 3.1. Source corpus и E1

E1 package находится в следующих путях:

- GPT/Нейросеть/Проекты/Исполнитель 1/Сессия 1/Реализация/sfra_indexer/indexer.py
- GPT/Нейросеть/Проекты/Исполнитель 1/Сессия 1/Реализация/sfra_indexer/storage.py
- GPT/Нейросеть/Проекты/Исполнитель 1/Сессия 1/Реализация/sfra_indexer/state.py
- GPT/Нейросеть/Проекты/Исполнитель 1/Сессия 1/Реализация/README.md

Факты:
- index_vault(vault_path, index_dir) принимает локальный filesystem path к Vault и отдельный index directory. E1 отклоняет размещение index directory внутри source Vault.
- E1 рекурсивно находит Markdown .md, читает UTF-8 с сохранением исходных LF/CRLF, считает SHA-256 полного файла и инкрементально индексирует изменённые документы.
- SQLite хранит source path, raw_text, структурные node records, passages, metadata, node lifecycle и node_versions. В node_versions сохраняется raw Markdown каждого snapshot узла, а не только locator.
- E1 state manifest связывает database SHA-256 с конкретным Vault source commit/ref. Workflow сохраняет structure.sqlite3 и manifest.json отдельно от source tree.
- Удалённые source files не удаляют историю: document/node lifecycle помечается deleted/stale; предыдущие node versions остаются.

Следствие: sidecar — это не только индекс метаданных. Он содержит исходный текст и исторические версии. Для cloud data plane нужно учитывать размер всей SQLite базы и историю, а не считать её лёгким производным cache.

### 3.2. Текущий GitHub persistence workflow

Файл: .github/workflows/sfra-state-persistence.yml.

Его YAML описывает следующую схему:
- implementation branch и Vault source ref checkout выполняются в разные каталоги;
- source checkout использует явно заданный vault_ref и sparse checkout ГП;
- отдельный sfra-state orphan branch восстанавливается как state repository;
- разрешены только README.md, state/structure.sqlite3, state/manifest.json;
- index build идёт во временный каталог runner;
- SQLite snapshot формируется через SQLite Backup API;
- manifest сохраняет source repository, Vault ref/commit, database path/hash и workflow metadata;
- публикация выполняется обычным fast-forward push после проверки, что remote branch не сдвинулся; workflow concurrency сериализует writes;
- workflow-level contents: write используется для обновления state branch.

Это уже показывает cloud-to-cloud путь для source, который уже находится в GitHub. Однако workflow работает с реальным source checkout и sidecar write, поэтому его наличие в Git не означает разрешение запускать его сейчас. #53/#75 запрещают re-enable/real-data execution без отдельного C/owner approval.

**Публичность:** GitHub API сейчас сообщает, что yeatu/obsidianGP имеет visibility=public. E1 README прямо описывает sfra-state как содержащую SQLite с current и historical source text и указывает, что читатель репозитория может читать этот текст. Следовательно, любой source content, закоммиченный в эту ветку публичного репозитория, становится публично доступным. Это не конфликтует с заявленным предпочтением владельца, но это реальная характеристика канала, а не условная настройка секретности. Сама ветка и данные из неё в рамках анализа не открывались.

### 3.3. Snapshot identity и E3

Основные контракты/реализация:
- Этап В1/src/sfra_context_integrations/snapshot.py
- Этап В1/src/sfra_context_integrations/source_reader.py
- Этап В1/src/sfra_context_integrations/search_adapter.py
- Этап В1/src/sfra_context_integrations/pipeline.py
- Этап В1/src/sfra_context_integrations/application.py

Текущий SnapshotRef состоит из:
- vault_commit_sha;
- sidecar_commit_sha;
- manifest_sha256.

E3 binder:
1. принимает filesystem roots для sidecar Git checkout, Vault Git checkout и Vault subdirectory;
2. получает реальные Git HEADs обоих checkout;
3. требует ожидаемую sidecar branch sfra-state и чистые worktrees;
4. вызывает публичный E1 verify_state_directory;
5. сверяет проверенный manifest с точными manifest bytes, source repository, Vault commit и SQLite SHA-256;
6. строит SnapshotRef по фактическим Git/manifest identities;
7. повторно проверяет paths, Git heads, branch, cleanliness, manifest digest и database digest вокруг source/search operations.

E1 Source Scope API открывает SQLite read-only/query-only и оригинальный Markdown под Vault root; он проверяет целостность source/hash/coordinates и не делает fuzzy/historical fallback. E1 сам не проверяет Git/manifest relationship; эту задачу выполняет E3.

Ключевое архитектурное следствие: **object-store key/version не является прямой заменой Git commit SHA в текущем контракте**. Пока действует существующий binder, cloud materializer должен предоставить два чистых Git worktrees с ожидаемыми HEADs и веткой sidecar. Альтернатива — новая versioned SnapshotRef/storage contract с эквивалентными доказательствами целостности, но это отдельное C-решение и migration work, а не скрытая переинтерпретация трёх текущих полей.

### 3.4. Shared core и transport boundary

- B1 Context Builder (Этап Б1) — pure package. Валидирует SearchRequest/SearchBatch, hashes, deduplicates, resolves dependency groups, ranks, budgets complete nodes atomically and creates Context Pack. Он не открывает SQLite, не знает GitHub/MCP.
- E3 integrations связывают E2 retrieval, E1 source reads и B1 builder; они несут SnapshotRef и source provenance.
- V2.1 SearchVaultService и ReadSourceService — transport-independent application facades. Они возвращают typed results, не реализуют свой поиск и не открывают SQLite самостоятельно.
- V2.2 Issue Worker Core — transport-independent обработчик request/status/idempotency, использующий injected application ports.
- W1 в PR #92 — GitHub Issues event adapter. Сейчас он использует synthetic-only corpus/gold case и injected V2.1-shaped fake ports. У него нет реального E1 source reader, production SQLite или Vault доступа.

Это правильное разделение для cloud-only target: GitHub workflow должен оставаться transport glue, а не копировать retrieval, provenance, snapshot или budget logic.

## 4. Целевая архитектура

### 4.1. Рекомендованный вариант: Git source + immutable object snapshot store + ephemeral GitHub Actions

~~~mermaid
flowchart TD
    U[ChatGPT Web / mobile] -->|owner-authored SFRA request| I[GitHub Issue]
    I --> E[issues.opened event]
    E --> W[GitHub Actions hosted VM]
    W -->|short-lived OIDC credential| A[Snapshot access API]
    A --> O[(Immutable object storage)]
    O -->|exact snapshot bundle| W
    W --> M[Snapshot materializer]
    M --> P[PinnedSnapshot / E1 verifier]
    P --> C[Existing E1 / E2 / E3 / B1 / V2.1 services]
    C --> R[Allowlisted response projection]
    R -->|bounded result comment| I
    I -->|read response| U

    G[GitHub source commit] --> S[Cloud sync / ingestion]
    S --> V[Validate + hash + index]
    V --> O
    V --> Q[Immutable manifest + snapshot pointer]
~~~

Границы:
- GitHub Issues — request/control plane и пользовательский response channel.
- GitHub Actions — короткоживущий compute. VM/filesystem не является durable store.
- Git/GitHub — source version identity и кодовая история.
- Object storage — durable immutable payloads: source bundle/objects, sidecar DB bundle/snapshot, manifest.
- SFRA core — единое место business logic.
- Snapshot pointer — только указатель для выбора нового snapshot; request execution закрепляется за конкретным SnapshotRef.

### 4.2. Почему рекомендован hybrid, а не один GitHub branch для всего

Текущий GitHub persistence flow технически доказывает, что source уже в GitHub можно индексировать на hosted runner без личного компьютера. Но SQLite — изменяемый бинарный snapshot с полным и историческим raw text. GitHub прямо указывает, что Git не предназначен для крупных SQL database files и рекомендует file-sharing/storage service для таких файлов. GitHub рекомендует держать repository ideally below 1 GB, strongly below 5 GB; documented on-disk recommendation is 10 GB. Также указаны single-object hard limit 100 MiB, push limit 2 GB и operational recommendations для read/push rates. Эти ограничения делают Git branch удобным compatibility path, но слабым кандидатом на бессрочное snapshot archive для растущей SQLite базы.

Git остаётся полезен для исходного Markdown и commit identity. Object storage лучше подходит для больших immutable snapshots, versioned blobs, resumable uploads и retention policies.

### 4.3. Snapshot compatibility: не ломать текущий контракт

Рекомендуемый переходный механизм:

1. В момент indexing создаётся immutable sidecar snapshot, связанный с одним exact Vault commit.
2. Snapshot metadata содержит фактические Vault commit SHA, sidecar commit SHA, manifest SHA-256 и SHA-256 database blob.
3. Sidecar snapshot экспортируется как Git bundle/pack или другой артефакт, из которого materializer восстанавливает checkout с тем же sidecar commit SHA.
4. GitHub runner downloads snapshot envelope/bundles в RUNNER_TEMP, восстанавливает чистый Vault checkout и sidecar checkout на точных commit IDs, sidecar branch — sfra-state.
5. Только после проверки hashes и manifest запускается существующий E3 binder.
6. PinnedSnapshot продолжает производить и проверять тот же SnapshotRef tuple. Если exact Git commit невозможно сохранить в object-store representation, нужен новый versioned contract и отдельное согласование C; нельзя подменять commit SHA произвольным object version ID.

Это сохраняет действующие E1/E2/E3 contracts на первом шаге. Позже возможен отдельный object-store-backed snapshot port, но он должен доказывать те же source/sidecar identity, immutable manifest и database/source hashes.

## 5. Варианты durable data plane

| Вариант | Плюсы | Минусы / риски | Роль в целевой схеме |
|---|---|---|---|
| GitHub repo + sfra-state Git branch | Уже существует; Git commit SHA естественно подходит под SnapshotRef; no extra vendor; direct GitHub browser/mobile commits | SQLite/raw text history увеличивает Git repo; большие binary snapshots неудобны; contents:write workflow credential; Git checkout cost; source import из браузера ограничен | Transitional path и source version control; не рекомендован как единственное долгосрочное хранилище sidecar |
| Object storage с versioning/immutability | Большие объекты и blobs; content-addressed keys; resumable multipart; lifecycle/retention; direct browser upload через short-lived signed URL; compute читает по exact key/version | Нужен upload API/control plane, materializer и OIDC policy; текущий E3 Git binder не читает object IDs напрямую; стоимость version retention/egress | **Рекомендуемый durable snapshot layer** |
| Managed application/data service + managed DB | Query API без materialize/cold download; central auth/audit; удобнее для высокого concurrency/latency | Самый большой operational footprint; E1/E2 сейчас tightly связаны с SQLite/local files; миграция E1/E2/schema/transactions; persistent service not required by current W1 target | Future option, если Actions latency, cold downloads или concurrency станут bottleneck |
| GitHub Issues/comments как source store | Простой пользовательский интерфейс, уже используется как request/response channel | Комментарии — журнал диалога, не версионируемая база; неудобно для полного corpus; API rate limits; лимиты размера/шум; плохой вариант для больших/многих бинарных snapshots | Control plane + response channel; не primary source/index store |
| GitHub Actions artifacts/cache | Удобно передавать job outputs и test reports | Job/VM ephemeral; artifact retention is configurable, default 90 days; cache has quota/eviction; artifacts не immutable source database | CI/test outputs only; не durable source store |

### 5.1. Provider-neutral evaluation

Provider выбирать после synthetic POC по критериям:
- immutable object versions / generation IDs / retention lock;
- resumable multipart upload from browser/mobile;
- short-lived scoped signed GET/PUT access;
- GitHub Actions OIDC/workload identity federation;
- checksum validation and conditional writes;
- lifecycle, soft delete, backup/restore;
- region/data residency, egress and request costs;
- API/S3 compatibility, tooling and exit/migration path.

Технологические примеры, не выбор поставщика:
- Amazon S3: presigned URLs дают ограниченный по времени upload/download доступ без выдачи пользователю cloud credentials; SigV4 presigned upload supports integrity checksums. GitHub Actions can exchange OIDC for short-lived cloud credentials.
- Google Cloud Storage: Object Versioning keeps noncurrent versions addressable by generation; lifecycle/soft-delete settings affect recovery and cost. Workload Identity Federation can exchange GitHub OIDC for short-lived credentials.
- Cloudflare R2: presigned URLs can be used from browsers/mobile; multipart supports resumable/parallel large uploads; incomplete multipart uploads have lifecycle cleanup; bucket locks support time-based retention rules.
- Azure Blob: version-level or container-level immutable storage supports time-based retention/legal hold (WORM); user delegation SAS allows delegated, scoped access.

No account, bucket, cloud provider, credentials or infrastructure were created or configured during this analysis.

## 6. Computer-independent import and synchronization

### 6.1. Existing Git-first case

If the canonical Vault is already fully represented in the GitHub source branch, a user can update it through a GitHub browser/mobile commit or another cloud-to-cloud source workflow. Once the commit exists remotely, GitHub Actions can checkout that exact commit and index it without the user's computer being online.

Advantages:
- exact source commit identity is native;
- no extra file transfer is needed after the source commit;
- existing E1 path and manifest contracts stay close to current design.

Limitations:
- editing/uploading many files in browser is cumbersome;
- GitHub browser file upload is documented at 25 MiB per file; regular Git blocks files over 100 MiB and warns above 50 MiB;
- large full-Vault imports and binary SQLite sidecars are not a good fit for regular Git;
- this is only computer-independent if the source is already synced to GitHub or can be committed via mobile/browser/cloud-to-cloud.

### 6.2. Recommended import portal flow

For a larger Vault or non-Git client, use a thin cloud upload control plane and direct-to-object-store data transfer:

1. User signs in through an owner-controlled identity/session; import API authorizes one repository/namespace and creates an import ID.
2. API returns a short-lived upload manifest with per-object signed upload URLs and an allowlisted object prefix. URL is scoped to method, object key and expiration; it is a bearer capability and must not be posted in Issues or logs.
3. Browser/mobile uploads one archive or batches of changed Markdown files. Large archive uses resumable multipart upload; small delta can be uploaded as individual blobs. The browser never receives a long-lived cloud account key.
4. Upload finalization endpoint verifies object exists, exact byte length, SHA-256 checksum, expected file count, duplicate/path collisions and import ID. ZIP/tar extraction rejects absolute paths, .., symlink escapes, duplicate paths and unexpected file types.
5. Import is first written to a staging namespace. It does not become a current snapshot until all validation/index steps pass.
6. The indexer creates a new sidecar snapshot using the exact immutable source version. Manifest records source commit/ref or content-manifest digest, parser/indexer/schema version, SQLite SHA-256 and snapshot identity.
7. Snapshot bundle and manifest are committed immutably. Only then is current_snapshot updated with compare-and-swap / generation precondition. Failed or interrupted uploads never become current.
8. Previous snapshots remain available according to an explicit retention policy. The new pointer does not delete old objects.

Initial full import is necessarily a one-time explicit user action unless the Vault already exists in a cloud source repository/provider with an authorized cloud-to-cloud API. Subsequent incremental sync can upload changed files only, keyed by path + content hash, or import a new exact Git commit. No background home daemon is required.

### 6.3. Incremental sync model

Each sync event should produce:
- import_id and request/actor ID;
- source origin and exact source version/ref;
- sorted file manifest: relative path, byte size, SHA-256, file type;
- parser/indexer version and SQLite schema version;
- previous snapshot ID and proposed new snapshot ID;
- counts only for operational logs; no content is required in logs.

Indexing rules:
- unchanged files retain current E1 generation/Node IDs/history;
- changed files follow existing E1 matching/versioning logic;
- deleted files become tombstones/stale records under current E1 semantics;
- ambiguous remapping remains ambiguous, never fuzzy-forced;
- complete database/index is built in staging and validated before immutable publication;
- no partial sync becomes visible.

A delta bundle must be bound to a specific parent snapshot. Applying a delta to the wrong base fails closed. If the parent changed during indexing, discard the candidate or rebase explicitly; never publish it as a descendant of an unverified parent.

## 7. Request execution, SnapshotRef and response delivery

### 7.1. Request binding

A stateless W1 request must resolve to one snapshot exactly once:
- either the request explicitly carries the desired SnapshotRef/snapshot ID;
- or the first accepted event atomically resolves the approved current-snapshot pointer and records that immutable identity in the request ledger.

Retries/reruns reuse the already-recorded SnapshotRef. They must not silently switch to the newest snapshot because the current pointer advanced. Existing W1 body-digest binding is a useful pattern for freezing request payload; snapshot binding needs the same immutability rule.

### 7.2. Worker sequence

1. Validate exact repository, issue author, sender, issues.opened, [SFRA] title gate and request body schema.
2. Bind immutable request-body hash and deduplicate by Issue/request ID.
3. Resolve and persist one immutable SnapshotRef.
4. Acquire short-lived read credentials using GitHub OIDC; download only that snapshot's required objects/bundles.
5. Materialize clean source/sidecar Git checkouts in runner temp storage; verify exact Git commits, manifest and SQLite hashes.
6. Build PinnedSnapshot and invoke existing V2.1/V2.2 service ports. Transport code does not call SQLite directly, does not recreate retrieval or content budgeting and does not invent another source reader.
7. Recheck operation-boundary verifier before/after E1/E2 calls as already implemented.
8. Project typed result through an explicit allowlist.
9. Post bounded result comment to the originating Issue and persist terminal worker status.
10. Destroy runner temp snapshot data when the hosted runner VM is decommissioned.

### 7.3. Delivery channel suitability

**GitHub Issue comment is the primary response channel** for status, a concise Context Pack, bounded excerpts, provenance, SnapshotRef and diagnostics. This matches the approved Web workflow and user's publication preference.

Current W1 PR #92 caps request body at 32 KiB and response comments at 45 KiB. Those are application-level safeguards, not a rule that Vault content must be redacted. For outputs larger than a comment:
- split into ordered, clearly labelled comments only if the result remains readable and within GitHub API limits; or
- store the full text/result as an immutable object and post a stable public link or short-lived signed GET link, depending on the intended retention/access policy.

Do not use Actions logs as the response store. They are noisy operational records and default retention is 90 days; on public repositories the documented maximum is 90 days, while private repositories can configure up to 400 days. Artifacts likewise have storage caps and expiry. They are not long-term Vault storage.

GitHub REST API has primary and secondary rate limits. Published secondary controls include limits on concurrent requests, points per endpoint/minute and content-generating requests; repeated comment creation is therefore not an unlimited streaming mechanism. W1 should keep bounded pagination, exponential backoff and a small deterministic response count.

## 8. Security, integrity and trust boundaries

The data-plane threat model should distinguish publication preference from credentials, integrity and execution authority.

### 8.1. Identity and authorization

- Only approved owner/repository/Issue event combinations can execute. W1 currently gates repository, owner-authored Issue, matching sender, non-PR Issue, title prefix and exact issues.opened action.
- Issue body is untrusted data, not code or a shell script. Strict versioned schema, duplicate-key rejection, body-size limit, operation allowlist and immutable body digest remain mandatory.
- A GitHub comment is not an upload credential. Never place a presigned URL, token, PAT, cloud key or service credential in an Issue body/comment.
- W1's least-privilege worker permissions (contents: read, issues: write only in the worker job) are a baseline. Future cloud access adds id-token: write only to the job that needs federation.
- OIDC trust must filter repository, owner, ref/branch, workflow identity and environment where supported. Cloud IAM role should only read the approved snapshot prefix for request jobs; publishing/index jobs get separate write permissions.

### 8.2. Upload endpoint

- Short expiry; single object/key/method; one import namespace; maximum size and object count.
- For multipart, bind the upload ID, part list and final checksum; abort incomplete uploads with lifecycle rules.
- Verify file paths and content after upload; never trust browser filename or object metadata alone.
- Preserve source bytes and SHA-256; decode Markdown with strict UTF-8 and existing E1 behavior.
- Use encryption at rest and TLS in transit; consider customer-managed keys if required by chosen provider, but do not make content confidentiality the product driver absent a user requirement.
- Credentials remain secret even when source note text is allowed to be public.

### 8.3. Snapshot integrity and rollback

- Immutable snapshot objects; no in-place overwrite of an existing snapshot ID.
- Manifest hash computed from exact bytes, database SHA-256 verified, source commit and sidecar commit pinned.
- Snapshot pointer updated only after all assets verify and with CAS/generation match to prevent lost update races.
- Worker never trusts the newest pointer after a request has already been bound.
- E1/E2 outputs remain bound to one SnapshotRef. Any stale/mismatched commit, manifest, DB, file hash or source coordinate fails closed with no partial result.
- Keep a recoverable previous snapshot and test rollback by updating the pointer to an earlier immutable snapshot; never edit an existing snapshot.

### 8.4. Process isolation and runner hygiene

- Hosted runner VM is created per job and decommissioned after the job; local filesystem is temporary.
- Use RUNNER_TEMP for materialized source, SQLite and transient bundles. Avoid artifacts/caches for durable snapshot data.
- No source bodies, raw_text, source path, node IDs, hashes or exception text in stdout/stderr. The user's publication permission allows intentional response content, not accidental diagnostic leakage.
- Keep third-party Actions pinned to full commit SHAs/approved lockfile for production execution.
- Separate job permissions and concurrency; do not put contents: write into a request execution job unless it has a specific approved publication purpose.

### 8.5. Retention and deletion

Define explicit policies for:
- active snapshots;
- rollback snapshots;
- import staging uploads and failed multipart uploads;
- response exports/result blobs;
- worker status/idempotency records;
- operational logs.

Use storage-native object versioning/retention/soft delete or WORM features where useful. Separate retention from publication: a public source snapshot can still require immutability and recovery. Pruning is a separate privileged operation with preview, retention window and audit record; a request worker must never delete source snapshots.

## 9. Options, operational trade-offs and recommendation

### Recommended staged target

**Keep source commit identity in Git; place generated immutable index snapshots in object storage; execute on GitHub-hosted runners; preserve GitHub Issues as request/response channel.**

Why:
- source Git commits already provide an exact, stable identity;
- object storage is better suited to versioned large blobs and resumable uploads than Git history;
- GitHub Actions remains the computer-independent executor;
- current shared core and application-service contracts can remain the sole business-logic layer;
- GitHub Issues keeps the ChatGPT-facing interaction simple;
- provider choice can remain open until a synthetic POC measures total size, upload/download time, storage cost and runner time.

### Staged compatibility choices

1. **Now / synthetic stage:** W1 continues against the accepted synthetic gold corpus. Keep production data disconnected. Rebase the stale PR #92 before new W1 A review and separate C acceptance.
2. **First approved real-data-capable design, before real-data execution:** prototype SnapshotMaterializer and immutable snapshot envelope using synthetic Vault/SQLite only. Test Git bundle materialization and object storage using a provider-neutral interface.
3. **Small corpus interim:** direct GitHub source checkout may remain the source snapshot mechanism if repository health and SQLite size remain acceptable. Keep sidecar writes disabled until C/owner explicitly approves; do not reuse #53 workflow by implication.
4. **Target storage:** move immutable sidecar DB/bundles and manifests to object storage with versioning/retention, keeping the exact Git commit identities needed by the current binder.
5. **Later scale path:** consider a managed application/data service only if Actions cold-start/download latency, concurrency or SQLite snapshot size makes per-job materialization inefficient. That path likely requires E1/E2 storage-port work or DB migration and a new C architecture decision.

### Why not a managed SQL database immediately

E1/E2 currently depend on local SQLite APIs and E1's single-transaction source scope. E3 pins local Git directories and a database file. Moving to a managed Postgres/API service is a valid future route, but it is not a simple storage configuration change: it alters E1 storage, query semantics, transaction consistency, snapshot materialization, failure modes and possibly index schema. It creates an always-on service and provider operations before evidence requires them.

## 10. Cost, reliability and lock-in

Primary cost drivers:
- retained source versions and sidecar snapshot bytes;
- duplicate versions and retention duration;
- object PUT/GET/list requests and multipart parts;
- egress from object store to GitHub-hosted runners;
- GitHub Actions compute minutes and concurrency;
- GitHub API reads/comments and retry rates;
- KMS/encryption request cost if customer-managed keys are chosen;
- backup and restore testing.

Reliability controls:
- immutable snapshot IDs and exact manifest/database checksums;
- CAS on current pointer and state generation;
- staging/validation before publish;
- bounded retries with jitter for transient storage/GitHub failures;
- idempotent request ledger and stable response markers;
- no dependency on a single runner's local filesystem;
- tested restore from a previous snapshot and from a clean runner;
- metrics on snapshot download time, indexing time, run duration, bytes transferred, failures and storage growth.

Lock-in controls:
- object store interface exposes only get/put/head/list version operations and checksums; core logic does not import provider SDKs;
- export a documented snapshot envelope and portable archive format;
- keep source commit and manifest format provider-neutral;
- ensure all snapshots can be downloaded and verified outside the provider;
- document lifecycle/retention semantics rather than depending on undocumented provider behavior.

## 11. Proposed implementation breakdown after C approval

No child implementation Issues are opened by this analysis. The following packages should be separately scoped and assigned only after C chooses the target:

| Package | Deliverable | Likely owner role | Dependency |
|---|---|---|---|
| Snapshot envelope/materializer | Versioned manifest; Git bundle materializer; verify exact Vault/sidecar commits; reuse PinnedSnapshot | E | C approves storage representation and SnapshotRef compatibility |
| Object-store adapter | Provider-neutral immutable object API; checksum/version/conditional operations; synthetic integration tests | E | Provider selection; IAM boundary |
| Browser/mobile ingestion control plane | Authenticated import session, short-lived upload URLs, resumable multipart, staging/finalization | E | Owner approves import UX and cloud provider |
| Index publish job | Run E1 on staged source, generate SQLite+manifest snapshot, validate, publish immutable object and CAS pointer | E | Snapshot materializer and object adapter |
| W1 snapshot access | Resolve pinned snapshot once per Issue request, use OIDC read-only access, materialize and call existing V2.1/V2.2 services | E | C acceptance of W1 and real-data gate |
| Operations and recovery | Retention/pruning, backup/restore, audit, retry/recovery, cost dashboards | E | Operational SLO and retention policy |
| Independent reviews | Exact-head, fixture-only tests, synthetic import/restore, security/data-flow acceptance | A then C | Every security boundary change |

## 12. Acceptance test plan

### Synthetic-only contract tests

- Full initial archive import; same archive re-import is idempotent.
- Delta import succeeds only against its declared parent snapshot.
- Wrong parent snapshot, missing object, changed object generation or checksum mismatch fails closed.
- Archive traversal, absolute paths, symlinks, duplicate paths, invalid UTF-8, duplicate normalized paths and over-limit uploads are rejected.
- Interrupted multipart upload can resume; abandoned upload is cleaned by lifecycle.
- Failed indexing does not advance the current snapshot pointer.
- Two concurrent publishers cannot overwrite a newer pointer; loser must rebase/retry.
- Manifest is canonical/byte-stable and database digest matches exact SQLite bytes.
- Snapshot materializer reconstructs both exact Git commit SHAs and the expected sfra-state branch in clean temporary directories.
- Existing PinnedSnapshot constructor/verifier gates and E1/E2 pre/post operation-boundary checks remain intact.
- A request retry after current pointer advances reuses its originally bound SnapshotRef.
- Wrong/stale SnapshotRef never falls forward to current snapshot.
- No result fragments are returned on stale, integrity_error, unavailable or budget_exceeded outcomes.

### Computer-independent tests

- User can begin and complete an import from a browser/mobile session without an always-on user device.
- Hosted runner obtains short-lived OIDC credentials only for the approved repository/ref/workflow.
- Runner reads only the requested immutable snapshot prefix; cannot list/delete/publish snapshots from request job.
- New runner can reproduce the same output from the same SnapshotRef.
- Runner decommission/retry does not lose source data or change the SnapshotRef.
- GitHub Issue opened event results in one terminal comment under duplicate delivery, within response-size bound.
- A non-owner, edited issue, pull request, comment event, invalid title, oversized body and invalid request body do not invoke application services.

### Publication/response tests

- Bounded comment includes status, operation, snapshot identity, provenance and result.
- Large result is split/linked through an explicit allowed mechanism; no silent truncation.
- Signed URLs expire, are scoped and never written into diagnostics.
- Content can be included in the user-approved public response, while credentials and cloud tokens never appear in response/logs.
- Issue comments and response objects are not treated as the canonical source database.

## 13. C/owner decisions required before real-data implementation

1. Approve the hybrid Git + object snapshot architecture as the target, or retain Git-only persistence with an explicit size/retention ceiling.
2. Select provider only after a synthetic POC measures upload, download, exact snapshot materialization, monthly storage, egress and operational friction.
3. Approve the browser/mobile initial import UX and identify where the initial exported Vault archive can be obtained if it is not already available in GitHub.
4. Approve immutable snapshot retention, rollback window, archival and permanent deletion procedure.
5. Decide whether the existing 3-field SnapshotRef plus Git materialization remains the contract, or commission a new versioned object-native SnapshotRef/storage port.
6. Approve any real Vault ingestion or read_source activation through a separate production rollout decision after fresh A review and security acceptance. This analysis itself does not grant that permission.
7. Decide where full result payloads above the W1 45 KiB comment cap should live: multiple bounded Issue comments, public object URL, or a different response channel.

## 14. Limitations and evidence quality

- The analysis maps the repository's tracked source, contracts and workflow YAML at main commit 9ba9d0403de0683c97938d0d323d96799157fc57. It did not inspect production source content, production SQLite, sfra-state branch contents or actual cloud account configuration.
- The current repository reports private=false / visibility=public; the report therefore treats tracked Git/state content as publicly readable where committed.
- The persistence workflow is described from its YAML and E1 README, not from an execution. It was not triggered or re-enabled.
- Provider examples are technical capability references, not procurement/plan confirmation. No price forecast is claimed because vault size, update rate, region, retention and traffic are not measured.
- PR #92 W1 remains synthetic-only and has a stale base after the verifier merge. Its current test evidence must not be represented as current-main acceptance.

## 15. References

### Repository evidence
- E1 README and source-scope/state model: GPT/Нейросеть/Проекты/Исполнитель 1/Сессия 1/Реализация/README.md.
- E1 index/storage/state: sfra_indexer/indexer.py, storage.py, state.py.
- E1 persistence workflow: .github/workflows/sfra-state-persistence.yml.
- E3 snapshot binding and operation guards: Этап В1/src/sfra_context_integrations/snapshot.py, source_reader.py, search_adapter.py, pipeline.py.
- Application services: Этап В1/src/sfra_context_integrations/application.py.
- B1 Context Builder: Этап Б1/README.md.
- W1 synthetic adapter design: PR #92 / Этап W1/README.md and .github/workflows/sfra-web-adapter-w1-tests.yml.
- Coordinator constraints: Issues #53, #75, #81; active design request #86.

### External technical documentation (checked 2026-11-18)
- [GitHub repository limits](https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits)
- [GitHub large files and SQL database guidance](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)
- [GitHub-hosted runner lifecycle](https://docs.github.com/en/actions/how-tos/manage-runners/github-hosted-runners/use-github-hosted-runners)
- [GitHub Actions runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [GitHub Actions artifact/log retention](https://docs.github.com/en/organizations/managing-organization-settings/configuring-the-retention-period-for-github-actions-artifacts-and-logs-in-your-organization)
- [GitHub REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- [GitHub Actions OIDC with cloud providers](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-cloud-providers)
- [Amazon S3 presigned upload/download URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)
- [Google Cloud Storage object versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
- [Google Workload Identity Federation for deployment pipelines](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
- [Cloudflare R2 presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/)
- [Cloudflare R2 multipart uploads](https://developers.cloudflare.com/r2/objects/upload-objects/)
- [Cloudflare R2 bucket locks](https://developers.cloudflare.com/r2/buckets/bucket-locks/)
- [Azure Blob version-level immutability](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-policy-configure-version-scope)

**Final recommendation:** proceed with a provider-neutral synthetic POC for an immutable object snapshot store plus exact Git snapshot materialization. Keep W1 execution on ephemeral GitHub-hosted runners, keep GitHub Issues as bounded request/response, and keep all real Vault ingestion/source reads disabled until a separate C/owner rollout decision.
