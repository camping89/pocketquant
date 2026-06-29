# Slice 1 — Backtest History & Comparison + UI Foundation — Brainstorm Report

## Metadata

Priority 1/5 · Vertical slice FE+BE · Depends on: none · Unblocks: Slice 2 (ad-hoc run dùng history store + tab shell), Slice 3/4/5 (dùng deep-link 2-tab shell) · Date 2026-06-29

> **RE-SCOUT NOTE (2026-06-29):** codebase đã refactor lớn kể từ bản brainstorm đầu. **Backtest đã được tách HOÀN TOÀN khỏi subscription** — có trang riêng `/backtest` (ad-hoc form + poll), `StrategyQueryService` không còn `_bt_repo`, cache-slot per-subscription + unique sparse index + worker `run_subscription` đã **bị gỡ**. Premise "1 Subscription phục vụ cả backtest+forward, detail 2-tab" KHÔNG còn khớp AS-IS. Report cập nhật theo thực tế; các quyết định A/B/C được re-frame và cần user chốt lại (xem §4, §10).

---

## 1. Problem Statement

- Premise dùng chung của 5 slice: 1 `Subscription` = `(strategy_code, symbol, interval)` immutable uuid7, phục vụ cả backtest (historical replay) lẫn forward (live), detail có chart + 2 tab Backtest|Forward.
- **AS-IS xung đột premise**: backtest hiện đã decoupled khỏi subscription, sống ở `/backtest` page riêng (`web/src/routes/backtest.tsx`). `DashboardColumn` (cột phải `/strategies`) giờ **forward-only** (docstring `dashboard-column.tsx:1-6`). Subscription list không còn enrich backtest status (`strategy_query_service.py:87-99`).
- Backtest run hiện: `POST /backtest/run` cấp uuid7 `run_id`, lưu doc `started`, spawn `asyncio` task, FE poll `GET /backtest/{run_id}` (`backtest.py:35-54`). Run keyed theo `strategy_code` (KHÔNG `subscription_id`).
- **Gap còn lại cho Slice 1**:
  - Không có **history view có cấu trúc**: `GET /backtest/strategy/{code}` list theo `strategy_code` only, KHÔNG filter symbol+interval, KHÔNG link subscription (`backtest.py:91-117`). FE `/backtest` page chỉ hiển thị **1 run đang chạy** (`activeRunId` state, `backtest.tsx:14`) — không có bảng N run, không compare.
  - Không có **deep-link** tới 1 run hay 1 subscription detail: `/strategies` dùng `selectedSub` local state (`strategies-page-layout.tsx:26`), `/backtest` dùng `activeRunId` local state — cả hai không URL-driven, không shareable, back/forward không chạy.
  - Không có **compare** 2 run cạnh nhau.
- Slice 1 phải quyết: history + compare gắn vào **subscription detail** (tái-coupling theo premise) hay vào **`/backtest` page** (theo AS-IS đã decoupled) — đây là quyết định kiến trúc lớn nhất, xem §4.

---

## 2. Current State (evidence)

### 2.1 Storage — per-run doc keyed `strategy_code`, KHÔNG cache-slot, KHÔNG subscription

- `COLLECTION_BACKTEST_RUNS = "backtest_runs"`, `COLLECTION_BACKTEST_ORDERS`, `COLLECTION_BACKTEST_TRADES` (`core/common/constants.py:15-17`). **KHÔNG còn** `COLLECTION_BACKTEST_OPTIMIZATION_RUNS`/`_REQUESTS`.
- `BacktestRepository` (`backtest_repository.py`) đã viết lại slim: `save`/`get`/`list_by_strategy_code`/`get_best_by_metric`/`mark_failed`/`mark_orphaned_started_as_failed`/`delete`/`delete_by_strategy_code`/`ensure_indexes`. **KHÔNG còn** `save_for_subscription`, `upsert_status`, `find_by_subscription`, `find_doc_by_subscription`, `get_subscription_statuses`, `_upsert_cache_slot`, `mark_stale_running_as_failed`, `ensure_subscription_cache_unique_index`.
- **KHÔNG còn unique sparse index** `ix_backtests_subscription_id_unique`. `ensure_indexes` (`:111-132`) chỉ tạo index theo `strategy_code`/`started_at`/`status`/`metrics.*`. KHÔNG có index nào theo `subscription_id`.
- Mỗi `POST /backtest/run` cấp `run_id` mới (`backtest_command_service.py:49`), lưu doc `started` (`BacktestResult.started`, `entities.py:38-58`); engine overwrite **cùng** run_id khi xong → **mỗi run là 1 doc riêng, không overwrite chéo** ⇒ history "thô" đã tồn tại trong `backtest_runs` keyed `strategy_code`, chỉ thiếu scoping symbol+interval + UI.
- Status vocab MỚI: `"started"` → `"finished"` | `"failed"` (`entities.py:33`, `backtest_repository.py:38,53`). (Bản cũ là `"completed"`.)

### 2.2 Read / Write paths (AS-IS)

| Endpoint | Service → repo | Scope | Evidence |
|---|---|---|---|
| `POST /backtest/run` (202) | `BacktestCommandService.run` → `save(started)` + route spawn `BacktestExecutionService.execute_and_persist` | cấp run_id, async | `backtest.py:35-54`, `backtest_command_service.py:42-62`, `backtest_execution_service.py:26-45` |
| `GET /backtest/{run_id}` | `get_result` → `get(_id)` | 1 run by uuid (poll) | `backtest.py:57-63`, `backtest_query_service.py:48-52` |
| `GET /backtest/{run_id}/equity` | `get_result` | equity curve của run | `backtest.py:66-78` |
| `GET /backtest/{run_id}/trades` | `list_trades` → `BacktestTradeRepository.list_by_run` | closed trades của run | `backtest.py:81-88`, `backtest_query_service.py:54-73` |
| `GET /backtest/strategy/{code}` | `list_results` → `list_by_strategy_code` | list theo **strategy_code only**, KHÔNG symbol+interval, KHÔNG sub | `backtest.py:91-117`, `backtest_query_service.py:75-80`, `backtest_repository.py:31-45` |
| `GET /backtest/strategies` | route inline `STRATEGY_REGISTRY.keys()` | list template names | `backtest.py:30-32` |

- **KHÔNG còn** `GET /subscriptions/{id}/backtest`, `POST /strategies/{code}/run-all-backtests`, `run_all_backtests_router`, `/backtest/requests/{id}`, `/backtest/optimize`, `/backtest/optimization/{id}`.
- `subscription_router` (`strategy.py:99-153`): chỉ start/stop/positions/trades/delete. Không backtest.
- Route mount (`app/main_extensions.py:401-404`): `strategy_router` → `subscription_router` → `trading_router` → `backtest_router`.

### 2.3 `positions` được assemble CLIENT-SIDE từ trades + open_positions

- `BacktestResult.to_mongo` (`entities.py:63-76`) ghi `open_positions[]` (still-open lots), **KHÔNG có `positions[]`**. Closed round-trip Trades nằm collection riêng `backtest_trades` scoped `run_id` (`backtest_trade_repository.py:35 list_by_run`).
- FE `fetchBacktestRun` (`backtest-api.ts:117-166`) tự join: fetch run doc → nếu `finished` thì fetch `/{runId}/trades` → ghép closed trades + `open_positions` thành `positions[]`. **Logic assemble đã chuyển sang FE** (bản cũ assemble ở BE worker). Run-detail của slice 1 tái dùng được hàm này.

### 2.4 Frontend

- Routes (`web/src/routes/`): `__root.tsx`, `index.tsx` (Charts), `strategies.tsx`, `backtest.tsx` (MỚI), `monitor.tsx`, `monitor_.jobs.$jobId.tsx`. Nav có link `/backtest` (`__root.tsx:24-26`). **KHÔNG có** param route per-subscription / per-run.
- `/backtest` page (`backtest.tsx`): `BacktestForm` + `BacktestResultView`, state `activeRunId` local (`:14`), poll qua `useBacktestRun` (`use-backtest-run.ts:24-31`, refetch 1500ms khi `started`). Chỉ 1 run hiển thị, không history table, không compare.
- `BacktestResultView` (`components/backtest/backtest-result-view.tsx`): 3 tab Metrics/Equity/Trades, tái dùng `MetricsTab`/`PositionsTab` (`backtest-panel/`) + `EquitySparkline`.
- `MetricsTab`/`PositionsTab` (`backtest-panel/metrics-tab.tsx:6-8`, `positions-tab.tsx:2,17`) giờ nhận prop `backtest: BacktestRunResult` (KHÔNG còn `SubscriptionBacktest`). **`backtest-panel/index.tsx` và `equity-tab.tsx` đã bị XOÁ**; thư mục còn metric-card/metric-cards/metrics-tab/positions-{filter,tab,table,utils}.
- `/strategies` (`strategies-page-layout.tsx`): 3-pane `selectedSub` local state (`:26`), cột phải `DashboardColumn` giờ **forward-only** (PnlBadge + RecentTradesTable live, `dashboard-column.tsx:17-57`). Sidebar `StrategyListSidebar` dùng `onSelect` callback + `selectedSubId` prop (`strategy-list-sidebar.tsx:13-17,113-114`) — không Link/deep-link.
- API client: `backtest-api.ts` — `BacktestStatus = 'started'|'finished'|'failed'` (`:40`), `BacktestRunResult` (`:44-57`), `runBacktest` (`:111`), `fetchBacktestRun` (`:117`). `strategy-api.ts` — `listSubscriptions`/`addSymbol`/`removeSubscription`/`deleteStrategy`; **KHÔNG còn** `runAllBacktests`, `getSubscriptionBacktest`, `SubscriptionBacktest`, `SubscriptionBacktestStatus`.
- Hooks: `use-backtest-run.ts` — `useStrategyList`/`useRunBacktest`/`useBacktestRun`. `use-subscriptions.ts` — `useSubscriptions` (poll khi `desired_state !== actual_state`, `:17-21`)/`useAddSymbol`/`useRemoveSymbol`/`useDeleteStrategy`. **KHÔNG còn** `useSubscriptionBacktest`/`useRunAllBacktests`.

### 2.5 Luồng dữ liệu backtest hiện tại (ad-hoc, decoupled)

```mermaid
flowchart LR
  FORM["/backtest page<br/>BacktestForm (activeRunId local)"] -->|POST /backtest/run| CMD[BacktestCommandService.run]
  CMD -->|save started| RUNS[("backtest_runs<br/>1 doc / run_id<br/>keyed strategy_code")]
  CMD -.->|return run_id| ROUTE[route spawns asyncio task]
  ROUTE --> EXEC[BacktestExecutionService.execute_and_persist]
  EXEC --> RS[run_single sandbox]
  RS -->|overwrite same run_id| RUNS
  RS -->|orders/trades scoped run_id| TR[("backtest_trades / backtest_orders")]
  POLL["useBacktestRun poll GET /backtest/{run_id}"] --> RUNS
  POLL -->|finished → GET /{id}/trades| TR
  classDef new fill:#dfd,stroke:#0a0;
  class RUNS,TR new;
```

`backtest_runs` đã append-per-run (không cache-slot). Thiếu: scoping symbol+interval (history bảng), deep-link, compare.

---

## 3. Requirements

- **Expected output**: 1 history view liệt kê N backtest run cho 1 phạm vi (subscription HOẶC strategy_code+symbol+interval, tuỳ quyết định §4) với date-range/params/8 metric (total_return/CAGR/Sharpe/Sortino/max_drawdown/win_rate/profit_factor/#trades); chọn 1 run → detail (metrics + positions overlay trên chart + equity); chọn 2 run → compare cạnh nhau; deep-link URL tới history/run.
- **Acceptance criteria**: chạy backtest 2 lần (date-range/params khác) → history table hiện 2 dòng phân biệt; mở 1 run cũ render đúng metrics/positions/equity của chính run đó; chọn 2 run → 2 cột metric + delta; URL deep-link reload giữ state + back/forward chạy + copy link mở đúng.
- **Scope boundary**: chỉ history + compare + deep-link foundation. KHÔNG đụng ad-hoc run form logic (đã có, slice 2 mở rộng), orders detail (slice 4), explain-trade (slice 5). Forward tab/view ngoài scope nếu chọn tách (xem §4).
- **Non-negotiable constraints**: giữ 7 import-linter contracts (`pyproject.toml:79,89,95,105,114,120,133`) — repo chỉ ở `core.infra.persistence.repositories`, service ở `engine`/`backtest`, route ở `app`, fastapi chỉ ở `app`; PK uuid7 (`generate_id_str`), không bson/ObjectId; single uvicorn worker (không thêm process/scheduler — ad-hoc run dùng `asyncio.create_task` in-process hiện có).
- **Touchpoints**: BE `backtest_repository.py`, `backtest_query_service.py`, route `backtest.py`; FE route mới (per-run hoặc per-sub), history table + compare components, `backtest-api.ts` + `use-backtest-run.ts`.

---

## 4. Approaches Evaluated

> Vì cache-slot + subscription-scoped backtest đã bị gỡ, nhóm A (storage) và C (navigation) được re-frame so với bản brainstorm đầu.

### 4.0 Coupling — B1 / B2 (quyết định nền, ảnh hưởng A & C)

| | History/compare gắn vào | Pros | Cons |
|---|---|---|---|
| **B1** | `/backtest` page (giữ AS-IS đã decoupled) | Khớp kiến trúc hiện tại (backtest standalone); không tái-couple; ít refactor `/strategies`; backtest cross-symbol/strategy tự nhiên | Lệch premise dùng chung "subscription detail 2-tab"; slice 3/4/5 (forward) vẫn ở `/strategies` → 2 nơi xem |
| **B2** | Subscription detail 2-tab (tái-couple theo premise) | Khớp premise 5-slice; 1 nơi xem cả backtest+forward 1 sub | **Đi ngược refactor vừa làm** (vừa decouple xong); cần re-add `subscription_id` vào run doc + endpoint scoped sub; nhiều rework, rủi ro tái lập đúng thứ vừa gỡ |

**Recommend: cần user chốt.** AS-IS nghiêng B1 (tôn trọng refactor mới). Nếu giữ premise 5-slice thì B2 — nhưng phải xác nhận user muốn đảo chiều refactor decouple. Phần A/C dưới giả định **B1** (mặc định AS-IS); nếu B2, xem note cuối mỗi mục.

### 4.1 Storage — A1 / A2 / A3 (re-framed)

Cache-slot đã không còn → "phá `get_subscription_statuses`" (rủi ro của A1 bản cũ) **không còn áp dụng** (hàm đó đã bị xoá). Vấn đề mới: **scoping history theo (strategy_code, symbol, interval)** để bảng không trộn run của symbol khác.

| | Cơ chế | Pros | Cons |
|---|---|---|---|
| **A1** | Dùng nguyên `backtest_runs` hiện tại, thêm query `list_by_scope(strategy_code, symbol, interval)` đọc `config_snapshot.symbol`/`.interval` | Không đổi schema; data đã có (`config_snapshot` chứa symbol/interval, `command_service.py:50-60`); chỉ thêm 1 repo method + index | Query trên field lồng `config_snapshot.*` cần index riêng; doc cũ trước refactor có thể thiếu field (tolerate) |
| **A2** | Promote `symbol`+`interval` thành **top-level field** của run doc (denormalize khỏi `config_snapshot`) + index `(strategy_code, symbol, interval, started_at desc)` | Query/sort/index sạch, nhanh; bảng history filter chuẩn | Đổi `to_mongo`/`from_mongo` + backfill nhận thức (run cũ thiếu field → tolerate hoặc migrate) |
| **A3** | Collection `backtest_history` riêng append-only (như bản cũ) | Tách concern | **Thừa**: `backtest_runs` đã append-per-run, không còn overwrite ⇒ không cần collection thứ 2; tăng chi phí ghi 2 nơi vô ích |

**Recommend: A2** (promote symbol+interval top-level + composite index). Đơn giản, query/sort sạch, không cần collection mới. A1 chấp nhận nếu muốn zero schema-change (đọc `config_snapshot.*`). A3 loại — append-per-run đã có sẵn, thêm collection là thừa (vi phạm YAGNI). *Nếu B2:* thêm `subscription_id` top-level thay/để cùng symbol+interval, index theo `subscription_id`.

### 4.2 Navigation — C1 / C2 / C3 (re-framed)

| | Cơ chế | Pros | Cons |
|---|---|---|---|
| **C1** | Deep-link route per-run trên `/backtest`: `/backtest/$runId` (history list = `/backtest`, detail = param route); compare qua search param `?compare=runA,runB` | URL shareable, back/forward, reload giữ run; khớp B1; tận dụng `/backtest` đã có | Refactor `backtest.tsx` từ `activeRunId` local sang route param + master-detail (list+detail) |
| **C2** | Giữ `/backtest` single-page, thêm history table + compare bằng local state (không route param) | Refactor ít nhất | Không deep-link/shareable (mất yêu cầu chính "deep-link"); không back/forward |
| **C3** | (chỉ khi B2) `/strategies/$subId` 2-tab Backtest|Forward | Khớp premise | Phụ thuộc B2; refactor `/strategies` master-detail lớn |

**Recommend: C1** (giả định B1). URL-driven foundation cho slice sau. C2 loại — không đạt deep-link. C3 chỉ hợp lệ nếu user chọn B2.

---

## 5. Recommended Solution

**Coupling B1 (giữ decoupled, chờ user xác nhận) + Storage A2 + Navigation C1.**

- **B1**: history + compare sống trên `/backtest`, tôn trọng refactor decouple vừa làm. (Nếu user muốn premise 5-slice → B2 + C3, cần xác nhận đảo chiều.)
- **A2**: promote `symbol`+`interval` lên top-level field của `backtest_runs` doc + composite index `(strategy_code, symbol, interval, started_at desc)`; thêm `list_by_scope`. Không thêm collection.
- **C1**: route `/backtest` = history list; `/backtest/$runId` = run detail (tái dùng `BacktestResultView`); compare qua search param. Scope picker chọn (strategy_code, symbol, interval).

**Invariant giữ nguyên**:
- import-linter: repo ở `core.infra.persistence.repositories`; query/command service ở `backtest`; route ở `app`; không import fastapi ngoài app (`backtest_execution_service.py` đã ở `backtest`, không fastapi — đúng).
- uuid7 PK: run_id = `generate_id_str()` (`command_service.py:49`), không bson/ObjectId.
- single uvicorn worker: ad-hoc run giữ `asyncio.create_task` in-process (`backtest.py:51`), không thêm process/scheduler.

---

## 6. Vertical Slice Breakdown

### 6.1 Backend

| Layer | File | Change |
|---|---|---|
| domain | `core/domain/backtest/entities.py` | thêm `symbol`/`interval` top-level vào `BacktestResult` + `to_mongo`/`from_mongo`/`started` (lấy từ `config_snapshot`) — A2 |
| repo | `backtest_repository.py` | `list_by_scope(strategy_code, symbol, interval, limit, include_failed)`; `get` đã có; `ensure_indexes` thêm `(strategy_code, symbol, interval, started_at desc)` |
| query svc | `backtest_query_service.py` | `ListScopedRunsQuery`; `list_scoped_runs`; `compare_runs(run_id_a, run_id_b)` (đọc 2 doc + assemble metrics rows); reuse `list_trades` cho detail |
| route | `app/routes/backtest.py` | `GET /backtest/runs?strategy_code=&symbol=&interval=&limit=` (history); `GET /backtest/compare?a=&b=`; giữ `GET /backtest/{run_id}` + `/{run_id}/trades` + `/{run_id}/equity` cho detail; dùng `FromDishka[BacktestQueryService]`, `DishkaRoute` |

**DTO shapes (BE)**:
- History row: `{ run_id, status, started_at, completed_at, symbol, interval, date_range:{start,end}, parameters, metrics: BacktestMetrics.to_mongo() }` (date_range từ `config_snapshot.start_date/end_date`).
- Run detail: dùng nguyên doc `GET /backtest/{run_id}` + `/{run_id}/trades` (FE `fetchBacktestRun` đã assemble `positions[]`).
- Compare: `{ a: <row+metrics>, b: <row+metrics> }`.

**Import-linter compliance**: tất cả repo ở `core.infra`; service ở `backtest`; route ở `app`. Không thêm import fastapi vào core/engine/backtest. (Note: `dishka.integrations.fastapi` chỉ ở route — đúng pattern, contract "fastapi only in app" grep-based ở test, không kẹt route.)

### 6.2 Frontend

| Item | File | Change |
|---|---|---|
| route list | `web/src/routes/backtest.tsx` | refactor: top = scope picker + `BacktestForm`; dưới = history table; bỏ `activeRunId` local → route nav |
| route detail | `web/src/routes/backtest.$runId.tsx` (mới) | param `$runId`; `useBacktestRun(runId)` → `BacktestResultView`; compare qua `?compare=` search |
| history table | `components/backtest/backtest-history-table.tsx` (mới) | cột symbol/interval/date-range/params/8 metric; row click → nav `/backtest/$runId`; multiselect ≤2 → compare |
| compare | `components/backtest/backtest-compare-view.tsx` (mới) | 2 cột metric + delta |
| result view | `backtest-result-view.tsx` (tái dùng) | feed `BacktestRunResult` (đã đúng shape) |
| api | `backtest-api.ts` | `listBacktestRuns({strategy_code,symbol,interval})`, `compareRuns(a,b)` + types `BacktestRunRow`, `BacktestCompare` |
| hooks | `use-backtest-run.ts` (mở rộng) | `useBacktestRuns(scope)`, `useCompareRuns(a,b)`; query keys `['backtest-runs',scope]`, `['backtest-compare',a,b]` |

*(Nếu B2: route `/strategies/$subId` + shell 2-tab; sidebar đổi `onSelect`→`Link`; re-add subscription-scoped endpoints.)*

### 6.3 API Contract

```
GET /api/v1/backtest/runs?strategy_code={c}&symbol={s}&interval={i}&limit=50
→ 200 [ { run_id, status, started_at, completed_at, symbol, interval,
          date_range:{start,end}, parameters, metrics:{...8+ fields} } ]   // [] nếu chưa run

GET /api/v1/backtest/{run_id}            (đã có)
→ 200 slim run doc { _id, strategy_code, status, metrics, equity_curve, open_positions, config_snapshot, ... }
GET /api/v1/backtest/{run_id}/trades     (đã có)
→ 200 { run_id, trades:[{direction,entry_price,entry_time,exit_price,exit_time,quantity,sl_price,tp_price,pnl,commission,duration_seconds}] }

GET /api/v1/backtest/compare?a={run_id}&b={run_id}
→ 200 { a:{...row+metrics}, b:{...row+metrics} }
→ 404 nếu a hoặc b không tồn tại
```

FE assemble `positions[]` client-side qua `fetchBacktestRun` (`backtest-api.ts:117-166`) — giữ nguyên.

---

## 7. Decomposition into Sub-tasks (ordered, mỗi task shippable)

1. **BE schema A2**: promote `symbol`+`interval` top-level vào `BacktestResult` + `to/from_mongo` + `started`. Test: round-trip giữ field; doc thiếu field tolerate.
2. **BE repo + index**: `list_by_scope` + composite index. Test: 2 run cùng scope vs khác symbol → filter đúng.
3. **BE query svc + route**: `list_scoped_runs`, `compare_runs`, `GET /backtest/runs`, `GET /backtest/compare`. Test: shape list/compare, 404 compare.
4. **FE deep-link**: `backtest.$runId.tsx` + refactor `backtest.tsx` bỏ `activeRunId` local → route nav. Ship: URL đổi, back/forward, reload giữ run.
5. **FE history table + api/hooks**: scope picker + `listBacktestRuns` + table 8 metric/dòng.
6. **FE run-detail**: route detail render `BacktestResultView` cho run param.
7. **FE compare**: multiselect 2 run → compare view + delta.

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **Premise vs AS-IS lệch** (subscription 2-tab vs `/backtest` decoupled) | Đưa quyết định B1/B2 cho user chốt TRƯỚC khi plan; mặc định B1 tôn trọng refactor mới |
| Doc cũ trước refactor thiếu `symbol`/`interval` top-level (A2) | `from_mongo` tolerate (fallback đọc `config_snapshot`); không hard-fail; history bắt đầu data sạch từ slice 1 |
| `config_snapshot.symbol`/`interval` key drift giữa command vs engine config | Verify `_config_from_dict` (`backtest_dispatch.py:43-54`) đọc `payload["symbol"]/["interval"]` — khớp `command_service.py:51-52`; A2 denormalize 1 lần lúc `started` |
| Refactor `backtest.tsx` (C1) vỡ poll-while-started | Giữ `useBacktestRun` refetchInterval logic (`use-backtest-run.ts:29`); detail route poll cùng hook |
| FE assemble positions chỉ khi `finished` (`backtest-api.ts:120`) | Đúng AS-IS — compare/detail chỉ hiển thị positions cho run terminal; run `started` chỉ metrics rỗng |
| `GET /backtest/strategy/{code}` cũ vẫn không scope symbol+interval | Bổ sung `GET /backtest/runs` (scoped) thay thế cho history; route cũ giữ nguyên (back-compat, không đụng) |
| B2 đảo chiều refactor decouple | Chỉ làm B2 nếu user xác nhận; cảnh báo rework lớn (re-add subscription_id + endpoints vừa gỡ) |

---

## 9. Success Metrics & Validation

- BE: `just test` (repo `list_by_scope` + query svc compare + entities round-trip), `just lint`, `just types` (mypy), import-linter pass 7 contracts.
- FE: `cd web && npm run lint && npm run build`.
- Chức năng: 2 run khác date-range cùng scope → 2 dòng history; run symbol khác KHÔNG lẫn vào bảng; mở run cũ → đúng metrics/positions/equity; compare 2 run → 2 cột + delta.
- Deep-link: `/backtest/{run_id}` reload giữ; back/forward chạy; copy URL mở đúng run.

---

## 10. Dependencies & Open Questions

**Cross-ref reports sibling** (cùng `plans/reports/`):
- `slice-2-*-adhoc-run-*-report.md` — ad-hoc run form đã tồn tại (`backtest.tsx` + `BacktestForm`); slice 2 mở rộng (params nâng cao, ghi vào history scope A2 của slice này).
- `slice-3-*-live-equity-kpi-*-report.md`, `slice-4-*-orders-*-report.md`, `slice-5-*-explain-trade-*-report.md` — forward/live hiện ở `/strategies` `DashboardColumn` (forward-only). Nếu B1, các slice này tách khỏi backtest navigation của slice 1; nếu B2 thì dùng chung shell 2-tab.

**Quyết định cần user chốt ở plan phase**:
- **B?** (MỚI, quan trọng nhất) — Coupling: B1 (history/compare trên `/backtest`, giữ AS-IS decoupled, recommend) vs B2 (tái-couple vào subscription detail 2-tab theo premise 5-slice). B2 đảo chiều refactor vừa làm → cần xác nhận rõ.
- **A?** — Storage: A2 (promote symbol+interval top-level + index, recommend) vs A1 (query `config_snapshot.*`, zero schema-change). A3 (collection riêng) đã loại vì `backtest_runs` đã append-per-run.
- **C?** — Navigation: C1 (`/backtest/$runId` deep-link, recommend với B1) vs C3 (`/strategies/$subId` 2-tab, chỉ hợp lệ nếu B2). C2 (no route param) loại.
- Compare scope: cho phép compare 2 run **khác scope** (cross-symbol/strategy) hay chỉ trong cùng scope? (đề xuất: cùng scope ở slice 1).
- `GET /backtest/strategy/{code}` cũ: deprecate hay giữ song song với `GET /backtest/runs`? (đề xuất: giữ, không đụng).

---

## Unresolved Questions

1. B1 vs B2 — user có muốn giữ backtest decoupled (vừa refactor) hay tái-couple vào subscription theo premise 5-slice? (block toàn bộ hướng slice 1).
2. Premise gốc của 5-slice (subscription detail 2-tab) còn hiệu lực không, hay đã bị thay bằng kiến trúc `/backtest` standalone + `/strategies` forward-only?
3. Các report sibling (slice 2-5) đã được re-scout theo kiến trúc mới chưa, hay vẫn dựa premise cũ?

---

Status: DONE_WITH_CONCERNS
