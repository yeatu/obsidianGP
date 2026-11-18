# SFRA — оперативная панель проекта

> Точка входа для участников проекта. Нормативный протокол — [Issue #20, Governance Protocol v2.4](https://github.com/yeatu/obsidianGP/issues/20).
> Источник истины по статусу — соответствующая GitHub Issue и её последние CLAIM / RELEASE / BLOCKED / review-события. Панель не заменяет Issues и точные evidence.

**Снимок:** 2026-11-18  
**Текущий main HEAD:** `553392dbbe9d3782683593bb92b88ac3ad6d9721`  
**Последний кодовый baseline:** `bc36bfdeceb34447f0cb8e1ae7978ecfe12de9c1`  
**Разница после code baseline:** четыре commit только с session-registry Markdown: E1 Session 6, E2 Session 4, E3 Session 6, Coordinator 1 Session 12. Код SFRA в этих изменениях не менялся.

## 1. Целевая архитектура и действующие решения

**ChatGPT Web / mobile → GitHub Issues → GitHub Actions → GitHub-hosted Runner → SFRA shared core/services → ответ в исходном Issue → ChatGPT читает ответ.**

- Личный компьютер владельца не является runtime-зависимостью. GitHub-hosted Runner — эфемерная среда исполнения, не постоянное хранилище Vault / SQLite / sidecar.
- Долговременный data plane проектируется через provider-neutral immutable snapshot bundles, versioned catalogue и read-only exact-version resolver/materializer.
- Существующие E1 indexing/source API, E2 retrieval, E3/B1 Context Builder, V2.1 SearchVaultService/ReadSourceService и V2.2 non-production Issue Worker Core переиспользуются. Не дублировать их бизнес-логику в адаптерах.
- Содержимое Vault и производные source metadata владелец разрешил публиковать; blanket redaction не вводить. Credentials, tokens, keys, provenance и integrity checks сохраняются.
- Публикация данных не равна разрешению на production import/read/index/write, provider provisioning, workflow dispatch или snapshot activation.
- Web worker остаётся выключенным для реального round-trip до независимого review точного финального стека и отдельного C-разрешения на один помеченный synthetic Issue round-trip.

**Исторические наработки сохраняются.** Ранее созданные реализации, адаптеры, тесты, схемы, docs, ветки, PR, commits и review trail не удалять и не переписывать из-за изменения приоритета. Повторное использование возможно в отдельной согласованной границе; сохранённые экспериментальные адаптеры не становятся обязательной runtime-зависимостью Web.

## 2. Активная очередь и владельцы

Статус в таблице сверяется с последним событием соответствующей Issue. «Свободна» означает, что действующего CLAIM нет и указанные зависимости выполнены; «заблокирована» — что захват сейчас преждевременен.

| Issue | Роль / статус | Следующий результат | Зависимости и границы |
|---|---|---|---|
| [#194](https://github.com/yeatu/obsidianGP/issues/194) | E — свободная P1 INTEGRATION | Синхронизировать объединённый W1 PR #92 stack с current main, fixture CI и новый A review | PR #92 HEAD `d57f576...`; main `553392...`; exact diff 14 W1 files; prior A #187 — только исторический target |
| [#193](https://github.com/yeatu/obsidianGP/issues/193) | E — свободная P1 INTEGRATION | Синхронизировать bundle PR #162 и correction PR #184 с current main | Parent #162 HEAD `c9ab808...`, child #184 HEAD `df37678...`; main `553392...`; four bundle-owned files; combined A review #190 идёт по старому точному target |
| [#195](https://github.com/yeatu/obsidianGP/issues/195) | E — свободная P2 INTEGRATION | Синхронизировать benchmark PR #84 с current main и повторить два полных exact-head прогона | PR #84 HEAD `c05f622...`; base review #189 — `94bd689...`; main `553392...`; не менять corpus/метрики/quality gates |
| [#196](https://github.com/yeatu/obsidianGP/issues/196) | E — заблокирована зависимостью | Синхронизировать writer PR #170 и correction PR #179 после bundle sync | **Только после RELEASE #193**; сохранить parent/child branch stack и четыре writer-owned files |
| [#197](https://github.com/yeatu/obsidianGP/issues/197) | E2 RELEASED / ждёт A #199 | Исправить пример indexer identity в CLOUD_SNAPSHOT_V2.md | PR #198, one-file docs-only diff; exact HEAD `fc9f1b3...` / base `553392...` |
| [#190](https://github.com/yeatu/obsidianGP/issues/190) | A — A1 CLAIMED | Интегрированный audit полного bundle builder + key correction | Exact historical parent #162 `c9ab808...`, child #184 `df37678...`, base `bc36bf...`; verdict не переносится на synced HEAD |
| [#77](https://github.com/yeatu/obsidianGP/issues/77) | P1 — W1 stack на A/C gate | #194 sync → fresh A review → отдельное C-решение | PR #92 остаётся open/unmerged; synthetic worker/round-trip не запускать до отдельного разрешения |
| [#119](https://github.com/yeatu/obsidianGP/issues/119) | E3 RELEASED / parent review & C gate | Принять immutable bundle builder/verifier | PR #162 + correction #184; #193 — current-main sync; #190 — интегрированный review исторической версии |
| [#125](https://github.com/yeatu/obsidianGP/issues/125) | E3 RELEASED / stack refresh pending | Принять immutable writer | PR #170 + correction #179; A1 принял correction #180 только для старого exact target; #196 после #193 |
| [#156](https://github.com/yeatu/obsidianGP/issues/156) | E1 RELEASED / A accepted historical target | Сохранить воспроизводимый benchmark evidence | PR #84, A1 accepted #189 для HEAD `c05f622...` / base `94bd689...`; #195 обновляет base и создаёт новый review |
| [#120](https://github.com/yeatu/obsidianGP/issues/120) | E — gated / пока не захватывать | Read-only exact-version resolver/materializer | После принятия #117/#118/#119 |
| [#124](https://github.com/yeatu/obsidianGP/issues/124) | E — gated / пока не захватывать | Synthetic lifecycle conformance | После принятия #117–#120 и #125; C3 добавил обязательный trust-order тест из #175 |
| [#134](https://github.com/yeatu/obsidianGP/issues/134) | E — gated | B1 SnapshotIdentity seam | Требует #120 и отдельный принятый E1 cloud verifier |
| [#136](https://github.com/yeatu/obsidianGP/issues/136) | E — gated | E3 factory-verified materialized snapshot handle | Требует #120, #134 и E1 cloud verifier |
| [#137](https://github.com/yeatu/obsidianGP/issues/137) | E — gated | Additive V2.2 cloud request/status protocol | Требует #134/#136; не менять v1 |
| [#138](https://github.com/yeatu/obsidianGP/issues/138) | E — gated | Synthetic V2.2 → B1 query-path conformance | Требует #134/#136/#137 и E1 verifier |

### Приоритет конфликтов и интеграции

1. Сначала current-main sync и propagation через stacked PRs: W1 #194, bundle #193, benchmark #195.
2. Writer stack #196 не менять до нового parent HEAD из #193.
3. Не создавать параллельные синхронизации одной ветки. W1 #178 завершён; дубликат #181 закрыт. C2 decision #191 разрешила только branch-only integration #186 → #92, не main merge.
4. Один точный HEAD/base — один действующий review target. Исторический verdict полезен как evidence, но не переносится на изменённую ветку.
5. Не запускать реальный worker, production read, provider action или activation ради снятия очередного review gate.

## 3. Принятые решения, review и CI evidence

- [#117 / PR #127](https://github.com/yeatu/obsidianGP/pull/127): CloudSnapshotRef v2 принят и merged.
- [#118 / PR #159](https://github.com/yeatu/obsidianGP/pull/159): in-memory SnapshotCataloguePort принят C3 после A2 REVIEW_ACCEPTED #160; merge commit `bc36bf...`. `mark_verified(snapshot_id)` остаётся caller-enforced boundary.
- [#175](https://github.com/yeatu/obsidianGP/issues/175): A1 analysis accepted C3. Orchestrator не вызывает `mark_verified()` до успешной public bundle verification и отдельного E1 cloud-index verifier. Для `immutable_import` нельзя использовать Git-shaped v1 verifier; пока additive E1 verifier не реализован и не принят, snapshot остаётся STAGED и не может стать VERIFIED/ACTIVE.
- [#173 / PR #184](https://github.com/yeatu/obsidianGP/pull/184): A1 REVIEW_ACCEPTED #185 для object-key correction (exact old HEAD only). PR #184 остаётся stacked на #162.
- [#172 / PR #179](https://github.com/yeatu/obsidianGP/pull/179): A1 REVIEW_ACCEPTED #180 для writer integrity correction (exact old HEAD only). PR #179 остаётся stacked на #170.
- [#183 / PR #186](https://github.com/yeatu/obsidianGP/pull/186): A1 REVIEW_ACCEPTED #187 для W1 digest conversion. C2 decision #191 разрешила branch-only merge PR #186 в W1 feature branch; итоговый parent PR #92 HEAD стал `d57f576...`. PR #186 не вливался в main.
- [#156 / PR #84](https://github.com/yeatu/obsidianGP/pull/84): две независимые полные попытки дали byte-identical JSON/Markdown отчёты. Gold corpus v1.0.0 остаётся 42 cases / 32 docs / 69 nodes. Результат 40/42; gq-010 и gq-036 остаются реальными failed gates, 14 status diagnostics видимы, 0 explicit SourceRead mismatches. A1 принял handoff #189 только для HEAD `c05f622...` / base `94bd689...`; #195 обновляет базу.
- [#132 / #142](https://github.com/yeatu/obsidianGP/issues/142): additive E1 verifier design accepted. E1 должен проверять внутреннюю consistency материализованного source/SQLite/index snapshot через read-only SQLite. Legacy manifest v1 и workflow не менять.
- [#124](https://github.com/yeatu/obsidianGP/issues/124): trust-order addendum зафиксирован. Upload/read-back и `stage()` не доказывают E1 verification; без E1 verifier — no `mark_verified`, no activation.
- [#197](https://github.com/yeatu/obsidianGP/issues/197): documentation correction завершена E2; PR #198 открыт, независимое A-review #199 ожидает CLAIM.
- [#188](https://github.com/yeatu/obsidianGP/issues/188): закрыта после снятия ложной E1 CLAIM строки и path-filter correction; benchmark review handoff #189 принят.

## 4. PR state и merge boundaries

| PR | Состояние | Текущий смысл |
|---|---|---|
| [#92 — W1](https://github.com/yeatu/obsidianGP/pull/92) | Open / unmerged | Feature branch HEAD `d57f576...`; correction #186 уже включена в feature branch; #194 sync с main `553392...`, exact 14 W1 files |
| [#84 — benchmark](https://github.com/yeatu/obsidianGP/pull/84) | Open / Draft / unmerged | HEAD `c05f622...`; 2 main-only commits позади; #195 sync + два полных прогона; 40/42 result, не green |
| [#162 — bundle](https://github.com/yeatu/obsidianGP/pull/162) | Open / unmerged | HEAD `c9ab808...`; #184 child correction `df37678...`; #193 sync |
| [#184 — bundle key correction](https://github.com/yeatu/obsidianGP/pull/184) | Open / Draft / unmerged | A1 accepted #185 для correction delta; parent + child integrated exact review #190 идёт на старой базе |
| [#170 — writer](https://github.com/yeatu/obsidianGP/pull/170) | Open / unmerged / stacked | HEAD `8c957c9...`; child correction #179 |
| [#179 — writer correction](https://github.com/yeatu/obsidianGP/pull/179) | Open / unmerged / stacked | A1 accepted #180 для correction delta; #196 ожидает #193 и должен обновить обе ветки |
| [#198 — CloudSnapshotRef v2 documentation example](https://github.com/yeatu/obsidianGP/pull/198) | Open / unmerged | Exact HEAD `fc9f1b3...`; one documentation file; fresh A review #199 |
| [#186 — W1 digest correction](https://github.com/yeatu/obsidianGP/pull/186) | Closed / merged into feature branch only | Merge commit `d57f576...` в PR #92 branch; не в main |
| [#159 — catalogue](https://github.com/yeatu/obsidianGP/pull/159) | Merged | C3 accepted #118; merge commit `bc36bf...` |
| [#127 — CloudSnapshotRef v2](https://github.com/yeatu/obsidianGP/pull/127) | Merged | Contract accepted |

Устаревшие панели #153 и #176 закрыты как superseded; их branches, commits и review records сохраняются. Текущая панельная ревизия основана на main `553392...`.

## 5. Зависимости и ограничения

1. **Cloud execution:** GitHub-hosted runners; личный компьютер не нужен для runtime. Runner workspace эфемерен.
2. **Source authority:** canonical Vault, completeness локальной/offline копии, sync, freshness, workload/SLO, retention, RPO/RTO и budget остаются UNDECIDED в #145. Metadata-only #154 не доказывает canonical authority или локальную полноту.
3. **E1 cloud verifier:** separate E1-owned typed inner attestation + read-only verifier. Не менять manifest v1, `verify_state_directory()`, `create_state_snapshot()` или legacy workflow. Git revision и immutable import ID — разные tagged variants. Verifier доказывает consistency материала, не происхождение источника или историческое назначение Node ID.
4. **Trust order:** prepare/public bundle verification → immutable write/read-back → stage (STAGED) → E1 cloud verifier → mark VERIFIED → activation through CAS. При любой ошибке — без VERIFIED/ACTIVE; прежний ACTIVE pointer не меняется.
5. **Quality:** не редактировать gold corpus, ranking, normalization, token budget или метрики для скрытия gq-010/gq-036.
6. **Worker:** PR fixture workflow может проверить тесты; `synthetic-issue-worker` на pull_request остаётся skipped. Ни синтетический Issue write/round-trip, ни production worker не запускается без отдельного C-разрешения.
7. **Provider:** не выбирать и не подключать provider, не создавать credentials/OIDC/KMS, не делать upload/download или production source operations в этих задачах.
8. **История:** no deletion, force-push, reset/rebase или branch rewrite. Синхронизации только обычными history-preserving merges.

## 6. Правило ведения панели

- Для каждой активной задачи — Issue, тип, роль, следующий результат, прямые зависимости и действующий CLAIM.
- Действующий владелец определяется последним CLAIM / RELEASE / BLOCKED событием в самой Issue; отсутствие assignee не заменяет проверку комментариев.
- Review verdict всегда привязан к exact HEAD/base; любой sync требует нового exact-head review.
- Параллельные задачи разделяются по файлам/API и не меняют общий стек одновременно.
- Если панель расходится с Issues/PR/Actions, приоритет имеет live GitHub state; панель обновляется отдельным PR.

---

**Рабочее правило:** панель помогает найти следующую безопасную задачу. Точные права, claims, review, зависимости и merge authority проверяются в GitHub Issue/PR, не выводятся из этой сводки.
