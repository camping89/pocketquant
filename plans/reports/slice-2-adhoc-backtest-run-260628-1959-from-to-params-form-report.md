# Slice 2 — Ad-hoc Backtest Run — Brainstorm Report

> **Re-scout 2026-06-29**: codebase đã đổi căn bản kể từ bản report đầu. Toàn bộ citations đã được verify lại bằng Read/Grep. Các thay đổi lớn (architecture, premise) được note tại §0 và rải trong từng section.

## Metadata

| Field | Value |
|---|---|
| Priority | 2/5 |
| Scope | FE + BE |
| Depends on | **Slice 1** (premise: history store + Backtest tab shell + deep-link) — **xem §0: premise này KHÔNG còn khớp code AS-IS** |
| Unblocks | Hoàn thiện trải nghiệm ad-hoc backtest |
| Date | 2026-06-29 |
| Constraints | import-linter (`fastapi` only in `app`; `core ◁ engine ◁ backtest ◁ app`), PK uuid7 only, single uvicorn worker |

---

## 0. Đổi căn bản so với bản report đầu (PHẢI đọc trước)

| # | Bản cũ giả định | Code AS-IS (verified) |
|---|---|---|
| C1 | Backtest nằm trong "Backtest tab của subscription" (1 sub → chart + 2 tab Backtest\|Forward) | Backtest **đã decoupled khỏi subscription**. Có route riêng `/backtest` (`web/src/routes/backtest.tsx`). `DashboardColumn` giờ là **forward-testing only** — docstring `dashboard-column.tsx:1-6` ghi rõ "Backtest now lives on its own /backtest page, decoupled from subscriptions" |
| C2 | Enqueue → `BacktestRequestWorker` poll-loop → `kind="single/subscription"` | **Không còn queue/worker**. `POST /backtest/run` spawn `asyncio.create_task(execution_svc.execute_and_persist(...))` in-process (`backtest.py:49-54`). `BacktestRequest` domain + `backtest_request_worker.py` đã bị **gỡ** |
| C3 | Poll `GET /backtest/requests/{request_id}` trả `{status,result,error}` | Poll `GET /backtest/{run_id}` trả full `BacktestResult.to_dict()` (`backtest.py:57-63`) |
| C4 | `RunBacktestCommand` cần thêm `sub_id` để vào history sub | Không có `sub_id` ở đâu cả; subscription↔backtest link đã bị gỡ luôn (endpoint `GET /subscriptions/{id}/backtest` + `getSubscriptionBacktest` FE đều **biến mất**) |
| C5 | FE "chưa có form ad-hoc run nào" | FE **đã có**: `backtest-form.tsx`, `use-backtest-run.ts` (`useRunBacktest`+`useBacktestRun`), `backtest-result-view.tsx`, route `/backtest`. runBacktest + poll đã hoạt động |
| C6 | Status `pending/running/done/failed` | Status `started / finished / failed` (`entities.py:33`, FE `BacktestStatus` `backtest-api.ts:40`) |

⇒ **Slice 2 phần lớn đã được implement** dưới dạng standalone page. Gap còn lại nhỏ hơn nhiều, và **mâu thuẫn premise** (decoupled vs "vào history của sub") là quyết định cần chốt lại — xem §10.

---

## 1. Problem Statement

- Trader cần chạy backtest mới on-demand với: date range, initial_capital, slippage_bps, commission_bps, strategy parameters động → submit → poll → xem kết quả.
- **AS-IS**: luồng này đã chạy được ở `/backtest` page (form → `runBacktest` → poll `useBacktestRun` → `BacktestResultView`).
- Gap thực tế còn lại:
  - Form **chưa** có preset date ranges (30d/90d/1y/YTD/all) — `backtest-form.tsx:108-114` chỉ có 2 native `input[type=date]` rỗng.
  - **Chưa** disable submit theo data availability (`use-sync-status.ts` tồn tại nhưng form không dùng).
  - Params là **JSON textarea thô** (`backtest-form.tsx:117-125`), không phải dynamic form theo schema; không validate `initial_capital`/`bps` (FE không expose 2 field này — chỉ dựa BE default).
  - **Không có** history table/list các run trước (cả BE lẫn FE) — mỗi lần chỉ giữ `activeRunId` hiện tại trong `useState` (`backtest.tsx:14`).
  - Mâu thuẫn premise: nếu vẫn muốn "run gắn vào subscription đang chọn" thì link sub↔backtest đã bị gỡ, phải dựng lại.

---

## 2. Current State (evidence — verified 2026-06-29)

### 2.1 Backend — luồng ad-hoc run (no queue, in-process task)

| Thành phần | File:line | Ghi chú |
|---|---|---|
| Route enqueue | `app/routes/backtest.py:35-54` | `POST /backtest/run` → `cmd_svc.run(cmd)` trả `(run_id, config)`; spawn `asyncio.create_task(execution_svc.execute_and_persist(run_id, config))`; giữ strong-ref trong `request.app.state.backtest_tasks`; trả `{request_id: run_id}` status 202 |
| Route poll | `app/routes/backtest.py:57-63` | `GET /backtest/{run_id}` → `BacktestResult.to_dict()` (full doc, không phải `{status,result,error}`) |
| Route trades | `app/routes/backtest.py:81-88` | `GET /backtest/{run_id}/trades` → `{run_id, trades}` (joined `backtest_trades`) |
| Route equity | `app/routes/backtest.py:66-78` | `GET /backtest/{run_id}/equity` |
| Route list | `app/routes/backtest.py:91-117` | `GET /backtest/strategy/{strategy_id}` — list runs theo **strategy_code** (không phải sub_id), limit + include_failed |
| Command DTO | `backtest/backtest_command_service.py:21-35` | `RunBacktestCommand`: strategy_id/symbol/interval/start_date/end_date/initial_capital(ge=100)/slippage_bps(ge=0)/commission_bps(ge=0)/parameters. **Không có `sub_id`** |
| Command run | `backtest/backtest_command_service.py:42-62` | `run_id = generate_id_str()` (uuid7); build `config` dict; `save(BacktestResult.started(run_id, config))`; return `(run_id, config)`. Không enqueue, không `sub_id` |
| Execution svc | `backtest/backtest_execution_service.py:21-46` | `execute_and_persist(run_id, config)` → `run_single(deps, config, run_id=run_id)`; engine tự catch lỗi và **return** `failed` (không raise); `except` ngoài flip started doc → `mark_failed` |
| Dispatch | `backtest/workers/backtest_dispatch.py:57-111` | `run_single(deps, config_payload, run_id=None)` — isolated sandbox, inject strategy, `BacktestAppService.run(config, run_id=run_id)`, teardown finally. Chỉ còn **single** path (đã gỡ `run_subscription`) |
| Result entity | `core/domain/backtest/entities.py:33,38-58,60-76` | `status: "started"\|"finished"\|"failed"`; `BacktestResult.started(run_id, config)` zeroed metrics; `to_dict()`=`to_mongo()` |
| Query svc | `backtest/backtest_query_service.py:23-30,48-80` | `GetBacktestQuery`/`ListBacktestsQuery`/`EnqueueBacktestResponse(request_id)`; `get_result`/`list_trades`/`list_results`. **KHÔNG còn** `get_request_status`, `BacktestRequestStatusResponse` |
| Repo | `core/infra/persistence/repositories/backtest_repository.py:15,24,31,63` | `save`/`get`/`list_by_strategy_code`/`mark_failed`. **KHÔNG còn** `save_for_subscription`/`upsert_status` |

### 2.2 Backend — KHÔNG còn link subscription ↔ backtest

- `app/routes/strategy.py` (verified full): `subscription_router` chỉ còn start/stop/positions/trades/delete. **Không còn** `GET /subscriptions/{sub_id}/backtest`, không `GetSubscriptionBacktestQuery`.
- Grep `get_subscription_backtest|save_for_subscription|GetSubscriptionBacktestQuery` trong `src/` → 0 hit (chỉ comment/constant `COLLECTION_BACKTEST_RUNS` còn).

### 2.3 Backend — strategy param schema vẫn CHƯA expose

| Thành phần | File:line | Ghi chú |
|---|---|---|
| Registry | `core/domain/strategy/services/__init__.py:4-7` | `{"hitnrun2": HitNRun2Strategy, "engulfing": EngulfingStrategy}` — 2 strategies |
| Param defaults | `core/domain/strategy/services/hitnrun2.py:31-37` | `_DEFAULTS`: entry_lookback_bars=240, sl_lookback_bars=480, tp_lookback_bars=60, max_loss_pct=0.01, min_profit_pct=0.02, direction="both". Đọc qua `p.get(...)` (`:45-52`); `direction` validate long\|short\|both (`:53`) |
| Strategy detail route | `app/routes/strategy.py:58-66` → `engine/strategy_query_service.py` `get_one` | Trả `strategy_code` + `class_name` + `description` (docstring dòng đầu). **KHÔNG có param schema** |

### 2.4 Backend — tín hiệu data availability (cho "disable submit")

| Thành phần | File:line | Ghi chú |
|---|---|---|
| Sync status route | `app/routes/market_data_status.py:15-35,38-56` | `GET /sync-status` (list) + `GET /sync-status/{symbol}?interval=` trả `bar_count`+`last_bar_at`+`status` |
| Date range từ bars | `backtest/jobs/backtest_strategy_loader.py:17-38` | `resolve_date_range` đọc `bar_repo.find_datetimes` → (first,last); fallback 365d. **Lưu ý**: chỉ dùng nội bộ — route `/backtest/run` KHÔNG auto-resolve, FE phải gửi start/end |

### 2.5 Frontend — ad-hoc run ĐÃ implement (standalone `/backtest`)

| Thành phần | File:line | Ghi chú |
|---|---|---|
| API run | `web/src/api/backtest-api.ts:111-113` | `runBacktest(body: RunBacktestBody)` → `POST /api/v1/backtest/run` → `{request_id}` |
| API poll+join | `web/src/api/backtest-api.ts:117-166` | `fetchBacktestRun(runId)` → `GET /backtest/{runId}`; khi `finished` join `GET /backtest/{runId}/trades` + open_positions → unified `positions[]` |
| Types | `web/src/api/backtest-api.ts:40,44-69` | `BacktestStatus='started'\|'finished'\|'failed'`; `BacktestRunResult`; `RunBacktestBody` |
| Hooks | `web/src/hooks/use-backtest-run.ts:9-31` | `useStrategyList`, `useRunBacktest` (mutation), `useBacktestRun` (poll `refetchInterval` dừng khi status≠'started') |
| Page | `web/src/routes/backtest.tsx:13-68` | `activeRunId` trong `useState`; form → mutate → `onSuccess` set activeRunId; render spinner(started)/error(failed)/`BacktestResultView`(finished) |
| Form | `web/src/components/backtest/backtest-form.tsx:30-138` | strategy select + symbol text + interval select + 2 native `input[type=date]` + **JSON textarea** cho params. Validate: strategy, symbol có `:`, start≤end, JSON parse. **Không** có capital/bps input, **không** presets, **không** sync gate |
| Result view | `web/src/components/backtest/backtest-result-view.tsx` | render `BacktestRunResult` |
| datetime helper | `web/src/lib/datetime.ts:6-23,69-74` | `dayjs`+`utc` plugin; `parseIso`; `INTERVAL_MS`. Không date-picker lib |
| sync-status hook | `web/src/hooks/use-sync-status.ts:4-10` | `useSyncStatus()` poll 30s — **tồn tại nhưng form chưa dùng để gate** |
| Form pattern tham khảo | `web/src/components/strategies/new-subscription-dialog.tsx:11,55,148` | INTERVALS const + handleSubmit + error branch theo HTTP status |
| package.json deps | `web/package.json:14-22` | dayjs có; echarts/lightweight-charts; **không** date-picker lib |

### 2.6 Frontend — KHÔNG có backtest history table

- Mỗi lần chỉ giữ 1 `activeRunId` (`backtest.tsx:14`). Không list run cũ.
- `web/src/types/job-history.ts` là **data-sync scheduler job history** (`JobRun`/`JobRunDetail`/`JobStats`), KHÔNG phải backtest run history — không liên quan Slice 1 premise.
- `useSubscriptionBacktest`/`useRunAllBacktests` đã **bị gỡ** khỏi `use-subscriptions.ts` (verified: chỉ còn `useSubscriptions`/`useAddSymbol`/`useRemoveSymbol`/`useDeleteStrategy`).

### 2.7 Diagram — luồng run→task→poll (AS-IS, no queue)

```
FE /backtest page         BE app (single uvicorn)          asyncio task (in-process)
   |                          |                                  |
   | POST /backtest/run ----> | cmd_svc.run(cmd)                 |
   |  (RunBacktestBody)       |   run_id=generate_id_str (uuid7) |
   |                          |   save(BacktestResult.started)   |
   |                          |   create_task(execute_and_persist)----> run_single(deps,config,run_id)
   | <-- 202 {request_id} ----|   (held in app.state.backtest_tasks)    sandbox engine
   |                          |                                  |       → backtest_*  (overwrite run_id)
   | GET /backtest/{run_id}   |                                  |       → mark_failed nếu fault ngoài engine
   |   (poll 1.5s khi started)| query_svc.get_result() ---------|
   | <-- BacktestResult doc --|  (status started→finished/failed)|
   |  khi finished: + GET /backtest/{run_id}/trades  (join positions)
   |                          |                                  |
 status=finished → BacktestResultView;  (KHÔNG tự vào history list keyed sub — không có store đó)
```

---

## 3. Requirements

| # | Requirement (verify được) | AS-IS |
|---|---|---|
| R1 | Form có start/end date, initial_capital, slippage_bps, commission_bps, params động theo strategy | Một phần: date + JSON params có; **thiếu** capital/bps input + dynamic schema |
| R2 | Submit → run_id → poll tới terminal (`finished`/`failed`) | **Đạt** (`use-backtest-run.ts:24-30`) |
| R3 | Run mới xuất hiện trong history table → auto-select detail | **Chưa**: không có history table; chỉ giữ activeRunId |
| R4 | Preset date ranges 30d/90d/1y/YTD/all | **Chưa** |
| R5 | Disable submit khi data chưa sync đủ (dùng `/sync-status`) | **Chưa** (hook có sẵn, form chưa wire) |
| R6 | Client validate start≤end, capital≥100, bps≥0 | Một phần: start≤end + JSON parse; thiếu capital/bps (chưa expose field) |
| R7 | Hiển thị progress khi `started` | **Đạt** (`backtest.tsx:49-54`) |
| **Scope boundary** | KHÔNG làm: live equity/KPI (S3), orders (S4), explain trade (S5), grid optimization (đã gỡ khỏi BE — không có route optimize nữa) |
| **Constraint** | Giữ import-linter (run logic ở `backtest`, route ở `app`), uuid7 (`generate_id_str`), single worker (task in-process, không thêm process) |
| **Touchpoints** | BE (optional): param-schema endpoint. FE: `backtest-form.tsx` (presets/capital/bps/sync gate/schema), `backtest.tsx` (history list), (nếu re-link sub) BE `RunBacktestCommand`+repo |

---

## 4. Approaches Evaluated

### 4.1 Gắn ad-hoc run vào subscription (premise C1/C4 — quyết định lại)

| Approach | Pros | Cons |
|---|---|---|
| **A. Giữ decoupled (AS-IS)** — backtest là page riêng, không gắn sub_id | Khớp hướng refactor đang có; zero BE đổi; KISS | Trader không xem được "lịch sử backtest của sub đang chọn" như premise Slice 1 |
| B. Re-link: thêm `sub_id` optional vào `RunBacktestCommand` + `BacktestResult` + `list_by_sub` query | Đúng premise gốc | Đảo ngược refactor vừa làm; phải dựng lại endpoint/store đã gỡ; rủi ro cao, cần user chốt |
| C. FE-only link: list run theo `strategy_code` (đã có `GET /backtest/strategy/{id}`) + filter symbol/interval client-side để xấp xỉ "của sub" | Không đụng BE schema; tái dùng route sẵn có | Lọc client thô; nhiều sub cùng strategy_code+symbol+interval sẽ lẫn |

### 4.2 Param schema source (R1 dynamic form)

| Approach | Pros | Cons |
|---|---|---|
| **(a) BE `GET /strategies/{code}/parameters` trả schema từ class** | Single source of truth; FE generic | Cần thêm contract `parameters_schema()` cho `IStrategy` (chỉ có `_DEFAULTS` dict) |
| (b) Hardcode FE per strategy | Nhanh; chỉ 2 strategies | Drift; DRY vi phạm |
| **(c) Generic JSON editor (AS-IS)** | Đã chạy (`backtest-form.tsx:117-125`); zero BE | UX thô; không validate type/range; dễ sai key |

### 4.3 Date picker + presets

| Approach | Pros | Cons |
|---|---|---|
| **Native `input[type=date]` + dayjs presets (AS-IS + thêm preset buttons)** | 0 dep mới (KISS); date input đã có; dayjs sẵn (`package.json:18`) | UI mộc |
| Thêm lib | UX đẹp | Thêm bundle thừa cho date-only |

---

## 5. Recommended Solution

- **4.1 → Approach A (giữ decoupled) cho v1**, vì code đã đi hướng này và đảo ngược (B) là user-decision đắt. Nếu cần "history của sub", dùng **C** (list theo `strategy_code` + filter) như bước nhẹ. **B chỉ làm khi user xác nhận muốn quay lại premise sub-coupled** (xem OQ-1).
- **4.2 → giữ (c) JSON editor cho v1**, nâng cấp **(a)** khi rẻ. (a) thêm `IStrategy.parameters_schema()` + 2 implementations + route ở `app` (giữ import-linter). Để trống params ⇒ BE dùng strategy defaults (`hitnrun2.py:45-52`).
- **4.3 → Native + dayjs presets**: thêm preset buttons compute start/end bằng dayjs; "all" = lấy `last_bar_at` (và sớm nhất nếu cần) từ `/sync-status`.
- **Wire sync gate (R5)**: dùng `useSyncStatus` (đã có) → tra `bar_count`/`last_bar_at` cho `symbol`+`interval` đang chọn → disable submit + cảnh báo khi range vượt coverage.
- **Expose capital/bps (R1/R6)**: thêm 2 input vào `backtest-form.tsx`, validate `>=100`/`>=0` khớp BE (`RunBacktestCommand` ge constraints).
- **History (R3)**: thêm list dùng `GET /backtest/strategy/{strategy_id}` + auto-select row mới sau khi `finished`. (Không cần BE mới.)
- **Giữ invariants**: uuid7 (`generate_id_str`), single worker (task in-process — KHÔNG thêm worker process), run logic ở `backtest`, route ở `app`.

---

## 6. Vertical Slice Breakdown

### 6.1 Backend

- **Không bắt buộc đổi** cho v1 (luồng run/poll đã đủ).
- (Optional, approach a) `IStrategy.parameters_schema()` + `HitNRun2Strategy`/`EngulfingStrategy` impl + route `GET /strategies/{code}/parameters` ở `app/routes/strategy.py`.
- (Chỉ nếu chọn 4.1-B) thêm `sub_id` vào `RunBacktestCommand` (`backtest_command_service.py:21-35`) + `BacktestResult` + query `list_by_sub` + dựng lại endpoint sub backtest — **cần user chốt**.

### 6.2 Frontend

- `backtest-form.tsx`: thêm preset buttons (30d/90d/1y/YTD/all via dayjs); thêm `initial_capital`/`slippage_bps`/`commission_bps` inputs + validate; wire `useSyncStatus` để gate submit (R5); (nếu a) đổi JSON textarea → schema-driven fields.
- `backtest.tsx`: thêm history list (`GET /backtest/strategy/{strategy_id}`) + auto-select run mới khi `finished` (invalidate list).
- (nếu cần "all" preset) FE đọc `/sync-status/{symbol}?interval=` cho first/last.

### 6.3 API Contract (AS-IS)

| Method | Path | Body / Params | Response |
|---|---|---|---|
| POST | `/api/v1/backtest/run` | `RunBacktestBody` (strategy_id/symbol/interval/start_date/end_date/initial_capital?/slippage_bps?/commission_bps?/parameters?) | 202 `{ request_id }` |
| GET | `/api/v1/backtest/{run_id}` | — | full `BacktestResult` doc (`status: started\|finished\|failed`) |
| GET | `/api/v1/backtest/{run_id}/trades` | — | `{ run_id, trades[] }` |
| GET | `/api/v1/backtest/strategy/{strategy_id}` | `limit`, `include_failed` | list run docs (theo strategy_code) |
| GET | `/api/v1/sync-status/{symbol}?interval=` | — | `{ bar_count, last_bar_at, status, ... }` (gate submit) |
| GET *(optional a)* | `/api/v1/strategies/{code}/parameters` | — | `[ { name, type, default, min?, max?, enum? } ]` |

---

## 7. Decomposition into Sub-tasks (ordered, shippable)

1. **FE-1** — `backtest-form.tsx`: thêm preset date buttons (R4) + `initial_capital`/`bps` inputs với validate (R1/R6). Shippable standalone.
2. **FE-2** — Wire `useSyncStatus` gate submit (R5) + warning khi range vượt coverage.
3. **FE-3** — `backtest.tsx`: history list via `GET /backtest/strategy/{id}` + auto-select run mới khi `finished` (R3).
4. **BE-1 / FE-4** *(optional)* — param schema endpoint (a) + schema-driven params editor; fallback giữ JSON (c).
5. **(blocked, cần user chốt)** — re-link sub_id (4.1-B) nếu user muốn quay lại premise sub-coupled.

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Data chưa sync đủ → run rỗng/lỗi warmup (hitnrun2 cần `sl_lookback_bars`=480 bars, `hitnrun2.py:34,90` context) | Gate submit qua `useSyncStatus` `bar_count`; "all" preset clamp theo `last_bar_at` |
| Param JSON sai key/range (vd `direction` phải long\|short\|both, `hitnrun2.py:53`) | (a) emit min/max/enum cho client validate; BE engine return `failed` (không raise, `backtest_execution_service.py:35-42`) → FE show `error_message` |
| FE `BacktestRunResult.error_msg` field thừa | `error_msg` không tồn tại trong BE doc (`to_mongo` chỉ có `error_message`); FE fallback `error_message ?? error_msg` (`backtest.tsx:19`) — vô hại, có thể dọn |
| Concurrent runs starve live Mongo pool (no cap, `backtest.py:44-47` ghi rõ accepted) | Trade-off đã chấp nhận; không guard ở Slice 2 |
| Premise mismatch (decoupled vs sub-history) gây hiểu nhầm scope | Chốt OQ-1 trước khi làm bất kỳ BE re-link |

---

## 9. Success Metrics & Validation

- BE (nếu đụng): `pytest` cho `backtest_command_service`/`backtest_query_service`; `import-linter` pass.
- FE: `cd web && npm run lint && npm run build` (tsc-b + vite) pass; `npm run test` nếu thêm hook test.
- Manual: `/backtest` → chọn strategy + preset 90d → (gate cho phép) → submit → spinner(started) → finished → result render; history list hiện run mới + auto-select.

---

## 10. Dependencies & Open Questions

**Cross-ref**: Slice 1 report (history store + Backtest tab shell + deep-link) — `slice-1-*-report.md` cùng `plans/reports/`. **Lưu ý premise Slice 1 (sub → 2 tab Backtest|Forward) không còn khớp code AS-IS** (backtest đã tách page riêng) — Slice 1 cần re-scout tương tự.

**Quyết định cần chốt:**

- **OQ-1 (BLOCKING, user-decision)**: Giữ backtest **decoupled** (AS-IS, hướng refactor đang đi) hay **re-link vào subscription** theo premise gốc? Ảnh hưởng toàn bộ scope BE. Code đã gỡ link sub↔backtest ⇒ quay lại là đảo ngược user-decision, cần xác nhận.
- **OQ-2**: Param editor giữ JSON (c) hay nâng schema (a) cho v1?
- **OQ-3**: History list theo `strategy_code` (route sẵn có) có đủ không, hay cần key chặt hơn (symbol+interval, hoặc sub_id nếu OQ-1=re-link)?
- **OQ-4**: "all" preset lấy range từ `/sync-status` (FE) — đủ chưa, hay cần thêm "first_bar_at" (route hiện chỉ trả `last_bar_at`, không có first)?

---

Status: DONE_WITH_CONCERNS
Summary: Re-scout phát hiện codebase đã đổi căn bản — backtest đã decoupled khỏi subscription, bỏ queue/worker (dùng asyncio.create_task in-process), và FE đã implement phần lớn Slice 2 (form+poll+result ở route /backtest). Report viết lại toàn bộ theo AS-IS; gap còn lại: presets, capital/bps inputs, sync gate, dynamic param schema, history list.
Changes:
- Citations sửa: POST /backtest/run giờ spawn asyncio task (backtest.py:35-54, KHÔNG còn enqueue); poll = GET /backtest/{run_id} (KHÔNG còn /backtest/requests/{id}); RunBacktestCommand KHÔNG có sub_id (backtest_command_service.py:21-35, run() trả tuple, save started doc); status started/finished/failed (entities.py:33).
- File mới phát hiện: backtest_execution_service.py, web/src/routes/backtest.tsx, web/src/components/backtest/backtest-form.tsx + backtest-result-view.tsx, web/src/hooks/use-backtest-run.ts, web/src/hooks/use-sync-status.ts.
- File đã GỠ (sửa citation cũ): backtest_request_worker.py, BacktestRequest domain (request.py), run_subscription trong dispatch, GET /subscriptions/{id}/backtest, getSubscriptionBacktest/runAllBacktests/useSubscriptionBacktest/useRunAllBacktests (FE), RunOptimizationCommand/RunAllBacktestsCommand.
- Premise mismatch ghi rõ tại §0 (C1: backtest decoupled khỏi sub) và OQ-1.
Concerns: Premise gốc (run gắn vào subscription, vào history của sub) MÂU THUẪN với code AS-IS (đã decoupled). OQ-1 là user-decision blocking — không tự ý re-link. Slice 1 premise cũng cần re-scout vì cùng giả định sub→2-tab không còn khớp.
