# Slice 2 — Ad-hoc Backtest Run — Brainstorm Report

## Metadata

| Field | Value |
|---|---|
| Priority | 2/5 |
| Scope | FE + BE |
| Depends on | **Slice 1** (history store + Backtest tab shell + deep-link select) |
| Unblocks | Hoàn thiện Backtest tab (trader chạy run mới rồi xem ngay trong history) |
| Date | 2026-06-28 |
| Constraints | import-linter (`fastapi` only in `app`; `core ◁ engine ◁ backtest ◁ app`), PK uuid7 only, single uvicorn worker |

---

## 1. Problem Statement

- Trong Backtest tab (do Slice 1 dựng), trader **chưa** có cách chạy backtest mới on-demand cho subscription đang chọn.
- Hiện chỉ có 2 đường chạy backtest:
  - `run-all-backtests` fan-out per subscription (`kind="subscription"`, không chọn date/params) — `backtest_command_service.py:139-169`.
  - `POST /backtest/run` (`kind="single"`, đủ date/capital/bps/params) — **nhưng kết quả KHÔNG gắn `sub_id`** ⇒ không vào history của subscription.
- Cần: form input (date range, capital, slippage_bps, commission_bps, strategy params động) → enqueue → poll → kết quả mới xuất hiện trong history table của Slice 1 → auto-select xem detail.

---

## 2. Current State (evidence)

### 2.1 Backend — đã có sẵn enqueue→worker→poll cho `kind="single"`

| Thành phần | File:line | Ghi chú |
|---|---|---|
| Route enqueue | `app/routes/backtest.py:41-51` | `POST /backtest/run` → `cmd_svc.run(cmd)`, trả `{request_id}`, status 202 |
| Route poll | `app/routes/backtest.py:54-59` | `GET /backtest/requests/{request_id}` → status/result/error |
| Command DTO | `backtest/backtest_command_service.py:37-51` | `RunBacktestCommand`: strategy_id/symbol/interval/start_date/end_date/initial_capital/slippage_bps/commission_bps/parameters. **Không có `sub_id`** |
| Enqueue logic | `backtest/backtest_command_service.py:94-115` | Build `config` dict, INSERT `BacktestRequest(kind="single", sub_id=None)` — `sub_id` để trống |
| Request domain | `core/domain/backtest/request.py:13-58` | `BacktestRequest` đã có field `sub_id: str \| None`; docstring nói rõ "single kind: no subscription to key on → embed result" |
| Worker dispatch | `backtest/workers/backtest_request_worker.py:103-119` | `kind=="single"` → `run_single` → `_assemble_single_response` → `mark_done(result=...)`. `kind=="subscription"` → `run_subscription` ghi `backtest_runs` keyed `sub_id` |
| Single dispatch | `backtest/workers/backtest_dispatch.py:92-139` | Chạy isolated sandbox, persist vào `backtest_*` collections (`persist_results` mặc định True) |
| Poll response | `backtest/backtest_query_service.py:44-55,101-110` | `BacktestRequestStatusResponse`: request_id/status/result/error |

### 2.2 Backend — strategy param schema CHƯA expose

| Thành phần | File:line | Ghi chú |
|---|---|---|
| Strategy registry | `core/domain/strategy/services/__init__.py:4-7` | Chỉ 2 strategies: `hitnrun2`, `engulfing` |
| Param defaults | `core/domain/strategy/services/hitnrun2.py:31-54` | `_DEFAULTS` dict (entry_lookback_bars, sl/tp_lookback_bars, max_loss_pct, min_profit_pct, direction) — **chỉ trong code**, đọc qua `config.parameters.get(...)` |
| Strategy detail route | `app/routes/strategy.py:59-67` → `engine/strategy_query_service.py:69-76` | `GET /strategies/{code}` trả `class_name` + `description` (docstring dòng đầu). **KHÔNG có param schema** |

### 2.3 Backend — tín hiệu data availability (cho "disable submit")

| Thành phần | File:line | Ghi chú |
|---|---|---|
| Date range từ bars | `backtest/jobs/backtest_strategy_loader.py:17-38` | `resolve_date_range` đọc `bar_repo.find_datetimes` → (first, last); fallback 365d |
| Sync status route | `app/routes/market_data_status.py:38-58` | `GET /sync-status/{symbol}?interval=` trả `bar_count` + `last_bar_at` + `status` — FE dùng được để gate submit |

### 2.4 Frontend — CHƯA có form ad-hoc run

| Thành phần | File:line | Ghi chú |
|---|---|---|
| backtest-api | `web/src/api/backtest-api.ts:60-62` | Chỉ `fetchStrategies()`. **Không có `runBacktest` / `pollRequest`** |
| strategy-api | `web/src/api/strategy-api.ts:53-64` | `runAllBacktests` (fan-out) + `getSubscriptionBacktest`. Không có ad-hoc run |
| hooks | `web/src/hooks/use-subscriptions.ts:79-85` | `useRunAllBacktests` chỉ invalidate. Không có poll-by-request-id |
| dashboard-column | `web/src/components/strategies/dashboard-column.tsx:110-114` | Empty state "No backtest data. Run a backtest first." — chưa có nút run |
| Form pattern tham khảo | `web/src/components/strategies/new-subscription-dialog.tsx:36-186` | Modal + `useState` per field + `handleSubmit` + error branch theo HTTP status — pattern tái dùng cho run form |
| datetime helper | `web/src/lib/datetime.ts:6-23` | `dayjs` + `utc` plugin có sẵn; `parseIso` xử lý naive-UTC. **Không có date-picker lib** trong `package.json:14-22` (dayjs có; echarts/lightweight-charts; không date picker) |

### 2.5 Diagram — luồng enqueue→worker→poll (hiện có cho `kind="single"`)

```
FE run form                BE app                     BacktestRequestWorker (in-proc, single)
   |                          |                                  |
   | POST /backtest/run ----> | cmd_svc.run()                    |
   |   (RunBacktestCommand)   |   INSERT BacktestRequest          |
   |                          |   kind="single" status=pending   |
   | <--- 202 {request_id} ---|   (sub_id=None  <-- GAP)          |
   |                          |                                  | claim_next() (poll 2s)
   |                          |                                  | run_single(config)
   |                          |                                  |   sandbox engine → backtest_* collections
   | GET /backtest/requests/{id} (poll 1-2s)                     | _assemble_single_response()
   | ---------------------->  | query_svc.get_request_status() ->| mark_done(result=fe_payload)
   | <-- {status, result} ----|                                  |
   |                          |                                  |
 status=done → render detail; (GAP: result không tự vào history store keyed sub_id)
```

---

## 3. Requirements

| # | Requirement (verify được) |
|---|---|
| R1 | Backtest tab hiển thị form với: start_date, end_date (range), initial_capital, slippage_bps, commission_bps, và params động theo strategy của subscription đang chọn. |
| R2 | Submit gọi enqueue trả `request_id`, FE poll status mỗi 1-2s cho tới terminal (`done`/`failed`). |
| R3 | Khi `done`, run mới phải xuất hiện trong history table (Slice 1) **và** được auto-select để xem detail — không cần reload trang. |
| R4 | Form có preset date ranges: last 30d / 90d / 1y / YTD / all (= toàn bộ bar coverage). |
| R5 | Submit bị disable khi data chưa sync đủ cho range (dựa `bar_count`/`last_bar_at` từ `GET /sync-status/{symbol}`). |
| R6 | Validate client-side: `start_date < end_date`, `initial_capital >= 100`, `slippage_bps >= 0`, `commission_bps >= 0` (khớp ràng buộc `RunBacktestCommand` BE). |
| R7 | Hiển thị progress khi `pending`/`running` (spinner + trạng thái). |
| **Scope boundary** | Slice 2 KHÔNG làm: live equity/KPI (S3), orders (S4), explain trade (S5), grid optimization UI (đã có `POST /backtest/optimize`, ngoài scope). |
| **Constraint** | Giữ import-linter (run logic ở `backtest`, route ở `app`), uuid7 cho `request_id`, single worker (không thêm worker process). |
| **Touchpoints** | BE: `RunBacktestCommand` + `BacktestCommandService.run` + worker `_dispatch`; FE: `backtest-api.ts` + hooks + Backtest tab component (Slice 1 shell). |

---

## 4. Approaches Evaluated

### 4.1 Gắn ad-hoc run vào subscription

| Approach | Pros | Cons |
|---|---|---|
| **A. Thêm `sub_id` optional vào `RunBacktestCommand` + worker ghi history store** | Run mới vào đúng history của sub; auto-select dễ; tái dùng path `kind="single"` (đã embed config + params đầy đủ) | Phụ thuộc storage choice của Slice 1 (history table key gì); cần worker ghi thêm 1 nơi |
| B. Để run rời rạc (`sub_id=None`), FE poll `/backtest/requests/{id}` rồi link sau | Zero BE đổi DTO | Run không nằm trong history Slice 1 → R3 không đạt nếu Slice 1 query theo `sub_id`; trader phải nhớ request_id |
| C. Reuse `kind="subscription"` (`run_subscription`) với params override | Đã ghi `backtest_runs` keyed `sub_id` | `run_subscription` KHÔNG nhận date/capital/bps/params từ FE — `resolve_date_range` tự suy từ bars (`backtest_dispatch.py:186`); phải đại tu signature → vi phạm KISS |

### 4.2 Param schema source (render dynamic form)

| Approach | Pros | Cons |
|---|---|---|
| **(a) BE endpoint `GET /strategies/{code}/parameters` trả JSON schema từ strategy class** | Single source of truth; FE generic; thêm strategy mới không đụng FE | Cần strategy expose schema (hiện chỉ có `_DEFAULTS` dict trong code, không typed schema) → phải thêm contract `parameters_schema()` cho mỗi `IStrategy` |
| (b) Hardcode FE form per known strategy | Nhanh nhất; chỉ 2 strategies | Drift khi đổi defaults; trùng kiến thức code↔FE; vi phạm DRY |
| (c) Generic key-value JSON editor (textarea / rows) | Zero BE đổi; chạy được mọi strategy | UX kém (trader gõ JSON thô); không validate type/range; dễ sai key |

### 4.3 Date picker

| Approach | Pros | Cons |
|---|---|---|
| **Native `input[type=date]` + dayjs** | 0 dep mới (KISS); dayjs đã có (`package.json:18`); đủ cho date-only | UI mộc, tùy theo browser |
| Thêm lib (react-day-picker / mui) | UX đẹp hơn | Thêm bundle + dep; thừa cho date-only range |

---

## 5. Recommended Solution

- **4.1 → Approach A**: thêm `sub_id: str | None` vào `RunBacktestCommand`; `BacktestCommandService.run` set `bt_request.sub_id = cmd.sub_id` (giữ `kind="single"` vì cần config-driven date/params). Worker `_dispatch` nhánh single, **sau** `mark_done`, nếu `request.sub_id` not None thì ghi result vào history store của Slice 1 (`backtest_repo.save_for_subscription` hoặc store mới Slice 1 chọn).
  - Rationale: path `kind="single"` đã carry đủ config (`backtest_command_service.py:94-104`) + đã assemble FE payload (`backtest_request_worker.py:121-167`). Chỉ cần "rót" thêm vào history khi có `sub_id`. Không đụng `run_subscription`.
- **4.2 → Approach (a) nếu rẻ, fallback (c)**: thêm classmethod `parameters_schema() -> list[ParamSpec]` cho `IStrategy`, `HitNRun2Strategy`/`EngulfingStrategy` trả spec từ `_DEFAULTS` (name/type/default/min/max). Route `GET /strategies/{code}/parameters` ở `app` (giữ import-linter). Nếu schema contract đắt → tạm fallback (c) generic JSON editor, để trống `parameters` ⇒ BE dùng strategy defaults (đã có `p.get(..., _DEFAULTS[...])`).
- **4.3 → Native `input[type=date]` + dayjs**. Preset ranges compute bằng dayjs; "all" = lấy từ `/sync-status` first/last hoặc để BE `resolve_date_range`.
- **Giữ invariants**: `request_id` = uuid7 (đã `generate_id()` ở `backtest_command_service.py:107`); single worker không đổi; run logic ở layer `backtest`, route ở `app`.
- **Phụ thuộc storage Slice 1 (nêu rõ)**: nơi worker ghi history (`save_for_subscription` keyed `sub_id` vs một collection runs mới có nhiều rows/sub) **do Slice 1 quyết**. Slice 2 chỉ cần "khi `sub_id` set, ghi vào store đó". Nếu Slice 1 chọn 1-row-per-sub cache (`backtest_runs`), ad-hoc run sẽ **ghi đè** cache → cân nhắc với Slice 1 (xem Open Questions).

---

## 6. Vertical Slice Breakdown

### 6.1 Backend

- `RunBacktestCommand` (`backtest_command_service.py:37-51`): thêm `sub_id: str | None = Field(default=None)`.
- `BacktestCommandService.run` (`:94-115`): `BacktestRequest(..., sub_id=cmd.sub_id)`. Giữ `kind="single"`.
- Worker `_dispatch` single nhánh (`backtest_request_worker.py:111-117`): sau `mark_done(result=fe_result)`, nếu `request.sub_id`: ghi history store (gọi method Slice 1 cung cấp). Giữ per-request isolation.
- (Optional, approach a) `IStrategy.parameters_schema()` + 2 implementations + route `GET /strategies/{code}/parameters` ở `app/routes/strategy.py` (query svc ở `engine`).

### 6.2 Frontend

- `backtest-api.ts`: thêm `runBacktest(body): Promise<{request_id}>` (`POST /api/v1/backtest/run`) + `pollBacktestRequest(id): Promise<{status, result, error}>` (`GET /api/v1/backtest/requests/{id}`); (optional) `fetchStrategyParams(code)`.
- Hook `useRunBacktest`: mutation enqueue → lưu `request_id` → `useQuery` poll với `refetchInterval` dừng khi terminal (pattern giống `use-subscriptions.ts:21-24` đang poll `running`).
- Run form component (trong Backtest tab shell Slice 1): date range native inputs + preset buttons + capital/bps inputs + params editor (schema-driven hoặc JSON fallback) + submit disabled theo `/sync-status` gate. Pattern form theo `new-subscription-dialog.tsx`.
- On `done`: invalidate history query (Slice 1 key) + auto-select run mới (qua deep-link state Slice 1).

### 6.3 API Contract

| Method | Path | Body / Params | Response |
|---|---|---|---|
| POST | `/api/v1/backtest/run` | `RunBacktestCommand` + `sub_id?` | 202 `{ request_id }` |
| GET | `/api/v1/backtest/requests/{id}` | — | `{ request_id, status, result?, error? }` |
| GET | `/api/v1/sync-status/{symbol}?interval=` | symbol composite, interval | `{ bar_count, last_bar_at, status, ... }` (gate submit) |
| GET *(optional a)* | `/api/v1/strategies/{code}/parameters` | — | `[ { name, type, default, min?, max?, enum? } ]` |

---

## 7. Decomposition into Sub-tasks (ordered, shippable)

1. **BE-1** — `RunBacktestCommand.sub_id` + `run()` set `sub_id`; worker single ghi history khi `sub_id` set. (depends Slice 1 store API)
2. **FE-1** — `backtest-api.ts`: `runBacktest` + `pollBacktestRequest`. Shippable standalone (poll `/backtest/requests` đã có).
3. **FE-2** — `useRunBacktest` hook (enqueue + poll + terminal stop).
4. **FE-3** — Run form: date range + presets + capital/bps inputs + client validate (R4/R6/R7).
5. **FE-4** — Submit gate qua `/sync-status` (R5).
6. **FE-5** — On-done: invalidate + auto-select history row (R3, qua Slice 1 deep-link).
7. **BE-2 / FE-6** *(optional)* — param schema endpoint (a) + schema-driven params editor; fallback (c) JSON editor nếu (a) đắt.

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Data chưa sync đủ cho range chọn → run rỗng/lỗi warmup (hitnrun2 cần `sl_lookback_bars` bars, `hitnrun2.py:90`) | Gate submit qua `/sync-status` `bar_count`; preset "all" clamp theo `last_bar_at`; show warning khi range vượt coverage |
| Param validation: type/range sai (vd `direction` phải long\|short\|both, `hitnrun2.py:53`) | Approach (a) emit min/max/enum cho client validate; BE vẫn raise `ValueError` → worker `mark_failed`, FE show error |
| **Coupling storage Slice 1**: nếu Slice 1 = 1-row-per-sub cache thì ad-hoc run đè cache, mất history nhiều run | Chốt với Slice 1: ad-hoc run cần many-rows-per-sub (history) hay đè cache (xem OQ-1) |
| Poll không bao terminal `failed` → spinner treo | `refetchInterval` dừng khi `status ∈ {done, failed}`; render `error` field |
| Run đè backtest cache đang dùng cho dashboard hiện tại (`/subscriptions/{id}/backtest`, `strategy.py:148-154`) | Nếu store riêng cho history thì không đè; nếu đè thì invalidate `['subscription-backtest', subId]` (đã có pattern `use-subscriptions.ts:36-38`) |

---

## 9. Success Metrics & Validation

- BE: `pytest` cho `backtest_command_service` (sub_id propagate) + worker dispatch (ghi history khi sub_id set). `import-linter` pass (không thêm import lệch layer).
- FE: `cd web && npm run lint && npm run build` (tsc-b + vite) pass; `npm run test` nếu thêm hook test.
- Manual: chọn sub → mở Backtest tab → submit run với preset 90d → thấy spinner → done → row mới trong history → auto-select detail render metrics.

---

## 10. Dependencies & Open Questions

**Cross-ref**: Slice 1 report (history store + Backtest tab shell + deep-link) — file `slice-1-*-report.md` cùng thư mục `plans/reports/` (đặt tên theo Slice 1 khi có).

**Quyết định cần chốt:**

- **OQ-1 (BLOCKING, với Slice 1)**: history store là **many-rows-per-sub** (mỗi ad-hoc run 1 row) hay **1-row-per-sub cache** (`backtest_runs`, `save_for_subscription`)? Slice 2 R3 (run mới xuất hiện + giữ các run cũ) cần many-rows. Nếu Slice 1 chọn cache → cần thống nhất schema bổ sung.
- **OQ-2**: Param schema dùng approach (a) hay fallback (c) cho v1? Phụ thuộc chi phí thêm `IStrategy.parameters_schema()` contract (verify độ phức tạp `EngulfingStrategy` defaults trước khi cam kết).
- **OQ-3**: Worker ghi history bằng method nào của Slice 1 (tên + signature)? Slice 2 BE-1 chờ contract này.
- **OQ-4**: "all" preset lấy range từ FE (`/sync-status`) hay để BE auto (`resolve_date_range`) khi FE gửi date trống? (KISS: FE compute từ sync-status).

---

Status: DONE
Summary: Slice 2 ad-hoc backtest run — BE đã có sẵn enqueue→worker→poll cho `kind="single"`; gap chính là `RunBacktestCommand` không carry `sub_id` (kết quả không vào history sub) và FE chưa có form/api/hook nào. Recommend: thêm `sub_id` optional + worker ghi history store của Slice 1, param schema endpoint (a) fallback JSON editor (c), date picker native + dayjs.
Concerns: Coupling chặt với storage choice của Slice 1 (OQ-1/OQ-3 blocking) — nếu Slice 1 chọn 1-row-per-sub cache thì R3 (giữ nhiều run trong history) không đạt; cần chốt many-rows-per-sub trước khi implement BE-1.
