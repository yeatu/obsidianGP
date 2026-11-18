# SFRA — оперативная панель

> Точка входа для AI-участников и снимок активной работы. Нормативные правила — [Issue #20, Governance Protocol v2.4](https://github.com/yeatu/obsidianGP/issues/20).
> GitHub Issue — источник истины по задаче. Эта панель показывает только активные задачи и не дублирует CLAIM, review, CI или evidence.

**Снимок:** 2026-11-18 (C1 post-verifier refresh)  
**main base for this dashboard update:** `9ba9d0403de0683c97938d0d323d96799157fc57`  
**Базовая версия кода:** `bb2275ece19f3d7cf1aa655b89d8d037803976c6`

## 0. Начало работы

Пользователь и координатор не назначают обычные задачи вручную. Участник сам выбирает свободную задачу своей роли, публикует CLAIM и начинает работу.

| Роль | Ответственность | Допустимые типы |
|---|---|---|
| **E — исполнитель** | Код, тесты, исправления, техническая документация и интеграция в утверждённом scope | `IMPLEMENTATION`, `INTEGRATION` |
| **A — аналитик** | Исследование, диагностика, требования, аудит и независимая проверка | `ANALYSIS`, `REVIEW_REQUEST` |
| **C — координатор** | Приоритеты, scope, архитектура, зависимости, блокировки, перераспределение, кризисы, общая панель и merge | `COORDINATOR_DECISION`; управление задачами всех ролей |

Буква Agent ID задаёт роль; цифра только различает участников: E1/E2/... имеют равные права внутри E, A1/A2/... — внутри A. Цифра не даёт старшинства или исключительных прав. Идентификатор C и полномочия выдаёт только владелец проекта; самоназначение запрещено.

**Если Agent ID ещё нет:** сохрани уже выданный ID. Иначе выбери E или A по типу задачи и следующий номер выше максимального использованного в этой категории. Проверь CLAIM во всех известных Issues, включая закрытые; номера не переиспользуются, нумерация E и A независимая. При совпадении первый CLAIM по GitHub comment ID сохраняет ID, второй публикует `AGENT_ID_REASSIGN` в своей Issue и выбирает следующий номер.

### Самостоятельный CLAIM

1. Выбери активную задачу своей роли. Не бери задачу другой роли, BLOCKED-задачу или задачу с невыполненными зависимостями.
2. Проверь Issue: статус, scope, критерии, зависимости, последние CLAIM/RELEASE/BLOCKED/REVIEW-события, пересекающиеся Issues/PR, требования к компетенциям, доступу и независимости.
3. Опубликуй комментарий:

   ```
   CLAIM
   Task: #<issue>
   Agent: <E<n>|A<n>|C<n>>
   Role: <E|A|C>
   Scope: <что именно беру>
   Started: <UTC timestamp>
   ```

4. Повторно прочитай комментарии. При гонке действует корректный CLAIM с наименьшим GitHub comment ID. Проигравший прекращает пересекающуюся работу и публикует `CLAIM_CONFLICT_YIELD`.
5. После подтверждения CLAIM начинай работу без дополнительного разрешения C для обычных задач E/A. Публикуй `PROGRESS`, а результаты и доказательства сохраняй в Issue/PR/commit/Actions.

Исключение из границ ролей возможно только при явном делегировании C с записанным scope и сроком/условием окончания.

## 1. Текущий курс

**Целевая архитектура — cloud-only:** ChatGPT Web / mobile → GitHub Issues → GitHub Actions → GitHub-hosted runner → SFRA shared core/services → ответ в исходном Issue → ChatGPT читает результат. Личный компьютер владельца может быть выключен и не является runtime-зависимостью. Не использовать self-hosted runner, локальный daemon или tunnel.

**Облачные данные:** облачная доступность исходного Vault, индекса, snapshot/manifest и sidecar, а также компьютер-независимые import/sync ещё анализируются в [#86](https://github.com/yeatu/obsidianGP/issues/86) (A1 CLAIM). Никакой production data access или migration не разрешается до отдельного C/owner decision по результатам анализа.

**Публикация содержимого:** владелец прямо подтвердил, что публичное распространение Vault content и source-derived metadata само по себе не является препятствием. Не вводить blanket confidentiality/redaction policy для текста заметок. Защищать credentials/tokens/signing keys и сохранять целостность, provenance, контроль операций и стоимость/лимиты каналов.

**Web adapter W1:** реализация [#77](https://github.com/yeatu/obsidianGP/issues/77) завершена E2 и передана на независимую проверку [#97](https://github.com/yeatu/obsidianGP/issues/97). [PR #92](https://github.com/yeatu/obsidianGP/pull/92), HEAD `e78576f483c688aa01f633e9293257416bc0778f`, имеет 44 успешных fixture tests в run `44240799599` на merge-ref с прежней базой `2051d0ce...`. После этого main продвинулся слиянием verifier PR #87; перед A/C acceptance нужно подтвердить актуальную интеграцию относительно текущего main. W1 остаётся synthetic-only; реальный Vault и production worker не подключены.

**Общее SFRA Core:** E1 structural indexer / Node identity / source API; E2 SQLite/FTS retrieval; E3/B1 Context Builder; V2.1 SearchVaultService / ReadSourceService; V2.2 non-production Issue Worker Core. Новые адаптеры должны использовать эти сервисы, а не копировать их бизнес-логику.

**PinnedSnapshot security:** cumulative correction #36/#51/#67/#79 принята A1 в [#88](https://github.com/yeatu/obsidianGP/issues/88), отдельно принята C1 в [#96](https://github.com/yeatu/obsidianGP/issues/96) и объединена из [PR #87](https://github.com/yeatu/obsidianGP/pull/87) в main commit `9ba9d0403de0683c97938d0d323d96799157fc57`. Issues #36/#51/#67/#79 закрыты. Принятый threat model #81 предполагает доверенный код внутри Python процесса и не обещает защиту от hostile same-process introspection. Это принятие verifier foundation **не включает** production `read_source`.

**Качество:** synthetic gold corpus v1.0.0 принят: 42 cases, 32 synthetic docs, 69 nodes. Benchmark #42 у E1; PR #84 Draft. Run `44237776930` показал 40/42 gates passed и выявил forbidden-node failures plus source-budget completeness-honesty gap. Не ослаблять критерии; исправить runner и повторить все cases.

**Сохранённая локальная линия:** ранее созданные adapter source, tests, schemas, docs, branches, PRs и evidence сохраняются. Локальные adapter-only задачи #38/#39/#40/#43/#72 и связанные PR остаются на owner hold; они не являются целевой Web архитектурой и не блокируют cloud-only направление. Общие компоненты SFRA переиспользуются там, где это оправдано.

## 2. Активные задачи

Перед любым CLAIM повторно проверить Issue, актуальные комментарии и зависимости. Эта таблица — краткий снимок, а не замена источнику истины.

| Issue | Приоритет | Тип | Роль | Следующий результат | Зависимости / владелец |
|---|---:|---|:---:|---|---|
| [#42](https://github.com/yeatu/obsidianGP/issues/42) | P1 | `IMPLEMENTATION` | **E** | Исправить benchmark integrity/completeness failures, повторить 42 synthetic cases и приложить exact-head reports | E1 CLAIM; PR #84 Draft; run #44237776930: 40/42 gates; forbidden-node и source-budget completeness findings обязательны |
| [#86](https://github.com/yeatu/obsidianGP/issues/86) | P1 | `ANALYSIS` | **A** | Спроектировать cloud data plane, computer-independent import/sync и варианты каналов публикации | A1 CLAIM; анализ-only; no real Vault access/migration |
| [#97](https://github.com/yeatu/obsidianGP/issues/97) | P1 | `REVIEW_REQUEST` | **A** | Независимая exact-head проверка W1 #77 / PR #92 | PR #92 HEAD `e78576f483c688aa01f633e9293257416bc0778f`; 44 fixture tests passed on merge-ref `18f8e586...`; recheck integration against current main after PR #87 merge |
| [#91](https://github.com/yeatu/obsidianGP/issues/91) | P2 | `COORDINATOR_DECISION` | **C** | Exact-head fixture CI bootstrap disposition | C2 claimed; C2 reports completion in comment #6969671557; Issue remains open pending its owner-side closure/reconciliation |

**Временно приостановленная линия:** Local adapter-only Issues #38/#39/#40/#43/#72 не брать в работу и не продолжать их merge/review без нового прямого решения владельца. Их код и история сохранены; shared-core результаты остаются пригодными для переиспользования.

**Завершено / принято:** #36/#51/#67/#79 — verifier chain accepted by A1 and C1, PR #87 merged; #88 — REVIEW_ACCEPTED; #96 — C1 decision completed. #53 закрыта после waiver владельца по удалению исторического run/artifact; старый real-Vault workflow остаётся disabled. #80 — завершённый A1 preflight, findings включены в #77. #93 — завершённая C3 coordination refresh; #95 закрыта как not planned из-за owner hold; #89 — duplicate #88. #34 завершена с CHANGES_REQUESTED по предыдущему dashboard HEAD. #37, #41, #49, #63, #69, #75, #81 завершены/приняты.

## 2.1. Новое правило декомпозиции: parallel-first

По Governance Protocol v2.4 (§5) каждую новую крупную задачу сначала разбиваем на минимальные самостоятельно полезные и проверяемые результаты. Для каждого пакета фиксируются один владелец, целевая роль, deliverable, затрагиваемые компоненты/файлы, прямые блокирующие зависимости, конфликты и интеграционная граница. Родительская связь не считается зависимостью автоматически. Независимые анализ, контракты, компоненты, тестовые наборы, fixtures, документация и conformance-проверки открываются отдельными Issues, когда их можно завершать параллельно. Не создаём микрозадачи без собственного результата и не расширяем scope ради занятости.

## 3. Открытые PR

| PR | Состояние | Трактовка |
|---|---|---|
| [#92 — synthetic Web adapter W1](https://github.com/yeatu/obsidianGP/pull/92) | Открыт / Ready for review | HEAD `e78576f483c688aa01f633e9293257416bc0778f`; run #44240799599 — 44 fixture tests passed on base `2051d0ce...`; A review #97. Current main advanced through #87; verify updated integration/base before acceptance |
| [#84 — synthetic gold benchmark runner](https://github.com/yeatu/obsidianGP/pull/84) | Открыт / Draft | HEAD `a16698266f5ceafa27ef4174a067517ca346663e`; run #44237776930: 40/42 gates; E1 corrections pending; do not weaken failed gates |
| [#47 — preserved local adapter bootstrap](https://github.com/yeatu/obsidianGP/pull/47) | Открыт / Draft / HOLD | Preserved history and code; no target path; no merge without explicit owner re-scope |
| [#57 — preserved local search adapter](https://github.com/yeatu/obsidianGP/pull/57) | Открыт / Draft / HOLD | Preserved; no local adapter work/merge under current scope |
| [#66 — preserved read-source parser preparation](https://github.com/yeatu/obsidianGP/pull/66) | Открыт / Draft / HOLD | Parser-only result preserved; no runtime wiring |
| [#94 — preserved generated-schema correction](https://github.com/yeatu/obsidianGP/pull/94) | Открыт / Draft / HOLD | Code/tests/exact-head CI preserved; review #95 closed as not planned under current target |
| [#54 / #70 — prior verifier attempts](https://github.com/yeatu/obsidianGP/pulls) | Открыты / historical | Superseded by merged PR #87; preserve review history; do not merge old attempts |
| [#12, #1, #2 — historical prototypes](https://github.com/yeatu/obsidianGP/pulls) | Открыты / historical | Preserve unchanged; no merge absent separate C/owner decision |

## 4. Действующие ограничения и решения

- **Cloud-only runtime:** ChatGPT Web/mobile → GitHub Issues → Actions → GitHub-hosted runners → SFRA → response in originating Issue. The owner's personal computer, self-hosted runner, local daemon/tunnel and local execution are not runtime dependencies.
- **Durable source availability:** cloud source/index/snapshot/manifest/sidecar and computer-independent import/sync are still under analysis in #86. Runner workspace is ephemeral. No real-data migration, cloud provisioning, production checkout/read/index or mutation before separate C/owner approval.
- **Publication preference:** public source-content/source-derived metadata publication is allowed where useful. Do not impose blanket note-content secrecy/redaction. Protect credentials/secrets and preserve integrity/provenance; select Issue/comment/log/artifact/object-store channels according to payload size, cost, retention and reliability.
- **W1 #77 / PR #92:** synthetic-only. A review #97 and C acceptance/merge remain required. Exact PR head passed 44 fixture tests on merge-ref #18f8 with prior main base 2051; after verifier merge PR #87, current-main integration must be revalidated. No synthetic Issue write/worker round-trip until A acceptance and explicit C authorization. No production runtime follows automatically.
- **PinnedSnapshot:** verifier chain is accepted and merged (#87 / merge commit `9ba9d040...`). This protects the shared read boundary under trusted-process assumption #81. It does not enable `read_source`; any future real-data Web composition requires approved cloud data plane #86, its own independent review and separate C/owner activation.
- **Local adapter preservation:** all legacy local adapter code, schemas, tests, docs, branches, PRs and CI evidence remain. Local-only tasks and PRs are held, not deleted/reverted; no reactivation or merge without explicit owner re-scope.
- **Historical #53:** the owner waived artifact/run deletion; historical run `44222117959` and artifact `14391137054` were not deleted and may remain public. The old real-Vault workflow remains disabled. No rerun or production execution is authorized.
- **Benchmark #42:** synthetic-only. Keep exact corpus digest, reference/span/hash checks, forbidden-node gates, source fidelity, completeness honesty and determinism. Fix the implementation; do not dilute criteria.
- Do not add embeddings/vector search, change ranking/normalization or token-budget ownership without benchmark evidence. Never label truncated source text as complete.
- Normative governance: [#20](https://github.com/yeatu/obsidianGP/issues/20). Cloud-only Web decision: [#75](https://github.com/yeatu/obsidianGP/issues/75). Cloud data plane: [#86](https://github.com/yeatu/obsidianGP/issues/86). PinnedSnapshot threat model: [#81](https://github.com/yeatu/obsidianGP/issues/81).

## 5. Передача E → A → E и обновление панели

Нормативные правила находятся в [Issue #20](https://github.com/yeatu/obsidianGP/issues/20). После каждого перехода исполнитель или аналитик обновляет свою строку через PR. Координатор вправе обновлять весь active register и архитектурные указания. Панель остаётся кратким снимком: Issue, PR, commit и Actions — источники истины.

C принимает архитектурные, security, cross-module, milestone и integration результаты только после проверки точного HEAD и evidence. Обычные leaf-задачи внутри утверждённого scope принимает независимый A. Никакой CLAIM или merge не отменяет ограничений #53, #75, #81 либо иных актуальных C/owner decisions.


Из панели удаляются только строки. GitHub Issues, комментарии, PR, commits и evidence сохраняются. Issue/PR/commit/Actions остаются источниками истины; панель — только краткий список следующего действия.
