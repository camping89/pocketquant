# Slice 1 — Backtest History & Comparison + UI Foundation — Brainstorm Report

## Metadata

Priority 1/5 · Vertical slice FE+BE · Depends on: none · Unblocks: Slice 2 (ad-hoc run dùng history store + tab shell), Slice 3/4/5 (dùng deep-link 2-tab shell) · Date 2026-06-28

---

## 1. Problem Statement

- Một `Subscription` = `(strategy_code, symbol, interval)` immutable uuid7. Phục vụ CẢ backtest (historical replay) lẫn forward (live từ `start`).
- Hiện BE chỉ giữ **đúng 1 backtest cache-slot mỗi subscription** → không có history. Mỗi lần `run-all-backtests` ghi đè slot cũ; người dùng không xem lại được run trước, không so sánh 2 run (đổi date-range / params), không thấy run nào sinh ra metrics đang hiển thị.
- UI hiện trộn backtest + forward trong 1 cột `DashboardColumn` 360px (3 tab Metrics/Positions/Trades), không deep-link được tới 1 subscription, không có tab tách bạch Backtest vs Forward.
- Slice 1 phải: (a) dựng **UI foundation** dùng chung cho 4 slice sau — deep-link route subscription detail + shell 2-tab (Backtest | Forward); (b) ship **Backtest tab** đầu tiên — history table nhiều run/sub + run-detail (metrics + positions overlay + equity) + compare 2 run.

---

## 2. Current State (evidence)

### 2.1 Storage — cache-slot, KHÔNG history

- `COLLECTION_BACKTEST_RUNS = "backtest_runs"` (`core/common/constants.py:15`) là collection chung cho cả: full run docs (keyed `strategy_code`) lẫn subscription cache-slot (keyed field `subscription_id`).
- **Unique sparse index** `ix_backtests_subscription_id_unique` trên field `subscription_id` (`backtest_repository.py:15-37`, mint trong `ensure_indexes` `:299`) → **tối đa 1 doc/subscription**. Sparse để full-run docs (không có field này) không vào index.
- `save_for_subscription` (`:152-179`) upsert ghi đè slot theo `subscription_id`; pop `_id`, slot `_id` cố định 1 lần qua `_upsert_cache_slot` (`:104-124`). `upsert_status` (`:126-150`) ghi status-only doc ('running'/'failed') cùng slot.
- Worker `run_subscription` (`backtest_dispatch.py:166,219,236`) gọi `upsert_status` → run → `save_for_subscription` → ghi đè. Mỗi run mất run trước.

### 2.2 Read paths

| Endpoint | Service → repo | Scope | Evidence |
|---|---|---|---|
| `GET /subscriptions/{id}/backtest` | `StrategyQueryService.get_subscription_backtest` → `find_doc_by_subscription` | latest cache-slot, 404 nếu chưa chạy | `strategy.py:148-154`, `strategy_query_service.py:155-168`, `backtest_repository.py:238-254` |
| `GET /backtest/strategy/{code}` | `BacktestQueryService.list_results` → `list_by_strategy_code` | list theo **strategy_code only**, KHÔNG filter symbol+interval | `backtest.py:110-136`, `backtest_query_service.py:88-93`, `backtest_repository.py:58-72` |
| `GET /backtest/{run_id}` | `get_result` → `get(_id)` | 1 run by uuid | `backtest.py:86-92` |
| sidebar enrich | `list_symbols` → `get_subscription_statuses` (`$in` sub_ids) | status-only/run projection mỗi sub | `strategy_query_service.py:98`, `backtest_repository.py:216-236` |

### 2.3 `positions` không nằm trong cache-slot doc

- `BacktestResult.to_mongo` (`entities.py:42-55`) ghi `open_positions[]` (still-open lots), **KHÔNG có `positions[]`**.
- Round-trip closed trades nằm collection riêng `backtest_trades` (`constants.py:17`), scoped theo `run_id` (`backtest_trade_repository.py:35 list_by_run`).
- FE-facing `positions[]` (closed Trades + open lots) được **assemble runtime** chỉ trong path single-run worker `_assemble_single_response` (`backtest_request_worker.py:121-167`). Cache-slot path KHÔNG assemble → `GET /subscriptions/{id}/backtest` trả doc **thiếu `positions`**; FE `DashboardColumn` cứu bằng `backtest?.positions ?? []` (`dashboard-column.tsx:43-55`). → Run-detail slice 1 PHẢI build `positions` từ `backtest_trades(run_id)` + `open_positions`, không đọc thẳng doc.

### 2.4 Frontend

- Routes: chỉ `/` (charts), `/strategies`, `/monitor` (`__root.tsx:13-26`). `/strategies` = `StrategiesPageLayout` (`strategies.tsx`), KHÔNG có param route per-subscription.
- `StrategiesPageLayout` (`strategies-page-layout.tsx`): 3-pane grid `240px | 1fr | 360px`, state `selectedSub` cục bộ (`useState`, `:26`) — **không URL-driven**, không shareable, back/forward không hoạt động.
- `DashboardColumn` (`dashboard-column.tsx`): 3 tab Metrics/Positions/Trades, đọc `useSubscriptionBacktest(sub.id)` (latest slot). `MetricsTab`/`PositionsTab` consume `SubscriptionBacktest` (`backtest-api.ts:42-58`); `EquityTab` render equity_curve lên sub-pane chart (`equity-tab.tsx`).
- `BacktestPanel` (`backtest-panel/index.tsx`) là 1 component đầy đủ hơn (collapsible, drag, 3 tab metrics/positions/equity) nhưng hiện không gắn vào `/strategies` layout — tái dùng tốt cho run-detail.
- API client: `getSubscriptionBacktest` (`strategy-api.ts:60-64`) chỉ có latest. KHÔNG có client list-runs-by-sub / get-run / compare. `backtest-api.ts` chỉ export `fetchStrategies`.
- Hook: `useSubscriptionBacktest` (`use-subscriptions.ts:46-57`) query `['subscription-backtest', subId]`.

### 2.5 Luồng dữ liệu backtest hiện tại (overwrite)

```mermaid
flowchart LR
  FE["FE Sidebar select sub<br/>(local useState)"] -->|GET /subscriptions/{id}/backtest| QS[StrategyQueryService]
  QS --> FD["find_doc_by_subscription<br/>(latest slot)"]
  RUN["POST /strategies/{code}/run-all-backtests"] --> W[run_subscription worker]
  W -->|upsert_status running| SLOT[("backtest_runs<br/>1 cache-slot / sub<br/>UNIQUE sparse idx")]
  W -->|save_for_subscription OVERWRITE| SLOT
  FD --> SLOT
  W -.->|trades scoped run_id| TR[("backtest_trades")]
  classDef bad fill:#fdd,stroke:#c00;
  class SLOT bad;
```

Slot là điểm nghẽn: ghi đè ⇒ mất history; doc thiếu `positions` ⇒ detail phải join `backtest_trades`.

---

## 3. Requirements

- **Expected output**: 1 deep-link route `/strategies/$subId` mở subscription detail với chart + shell 2 tab; Backtest tab hiển thị bảng N run (date range/params/total_return/CAGR/Sharpe/Sortino/max_drawdown/win_rate/profit_factor/#trades), chọn 1 run xem metrics + positions overlay + equity, chọn 2 run xem cạnh nhau.
- **Acceptance criteria**: từ sidebar click sub → URL đổi sang `/strategies/{id}` (reload giữ state, back/forward chạy); chạy backtest 2 lần với date-range khác nhau → history table hiển thị 2 dòng phân biệt; mở 1 run cũ render đúng metrics + positions + equity của chính run đó; chọn 2 run → 2 cột metric so sánh.
- **Scope boundary**: chỉ Backtest tab + history store + deep-link shell. Forward tab = shell trống/placeholder (slice 3+). KHÔNG đụng ad-hoc run form (slice 2), orders detail (slice 4), explain-trade (slice 5).
- **Non-negotiable constraints**: giữ 7 import-linter contracts (`pyproject.toml:78-137`) — repo mới/sửa chỉ ở `core.infra.persistence.repositories`, service ở `engine`/`backtest`, route ở `app`, fastapi chỉ ở `app`; PK uuid7 (`generate_id`), không bson/ObjectId; single uvicorn worker (không thêm process/scheduler mới).
- **Touchpoints**: BE `backtest_repository.py`, `backtest_query_service.py`, `backtest_dispatch.py`, route `backtest.py`/`strategy.py`; FE route mới `strategies.$subId`, shell 2-tab, history/run-detail/compare components, `backtest-api.ts` + hooks.

---

## 4. Approaches Evaluated

### 4.1 Storage — A1 / A2 / A3

Vấn đề cốt lõi: sidebar enrich (`get_subscription_statuses`, `list_symbols:98`) phụ thuộc **đúng 1 doc/sub** keyed `subscription_id`. Mọi phương án phải giữ invariant này hoặc thay nguồn status.

| | Cơ chế | Pros | Cons |
|---|---|---|---|
| **A1** | Bỏ unique index, mỗi run 1 doc có `subscription_id` | Đơn giản nhất về ghi; mọi run cùng 1 collection | **Phá `get_subscription_statuses`**: `$in` trả nhiều doc/sub → `out[doc["subscription_id"]]` ghi đè ngẫu nhiên (`:230-235`) ⇒ sidebar hiện status sai. Phá luôn `find_doc_by_subscription` (trả tuỳ ý). Phải viết lại 2 read path = rủi ro cao. `upsert_status` mất nơi neo (không còn slot duy nhất). |
| **A2** | Giữ cache-slot 'latest' cho sidebar status (như cũ) **+** historical runs scoped `sub_id` tách bằng `kind` field (vd `kind:"history"`) hoặc collection riêng; index unique chỉ áp doc slot | Rủi ro thấp nhất — read path status & latest **không đổi**; tách rõ "scheduled-latest slot" vs "manual/historical runs"; index partial dễ giới hạn unique cho slot | Hai khái niệm doc trong cùng collection (nếu dùng `kind`) → query cần filter `kind`; cần đổi unique index từ `sparse` sang `partialFilterExpression` để chỉ slot vào index |
| **A3** | Collection mới `backtest_history` — **mọi** run append (full doc, có `subscription_id`); cache-slot `backtest_runs` chỉ trỏ run mới nhất (giữ nguyên) | Tách sạch concern: slot = status/latest cho sidebar (zero đổi read path cũ), history = nguồn cho table/detail/compare; append-only đơn giản, không unique-index gymnastics; index `(subscription_id, started_at desc)` cho list nhanh | Thêm 1 collection + repo; worker ghi 2 nơi (slot + history) trong cùng `run_subscription`; cần backfill nhận thức "run cũ trước slice này không có history" (chấp nhận: history bắt đầu từ slice 1) |

**Recommend: A3** (fallback A2 nếu muốn 1 collection). A3 giữ `backtest_runs` slot **bất biến** → `get_subscription_statuses`/`find_doc_by_subscription`/sidebar không đổi 1 dòng (giảm regression). History là collection append-only thuần đọc cho table/detail/compare. A2 đạt cùng mục tiêu nhưng trộn 2 loại doc trong 1 collection + đổi index spec, nhiều bề mặt lỗi hơn. A1 loại — phá đúng read path đang chạy.

### 4.2 Navigation — C1 / C2 / C3

| | Cơ chế | Pros | Cons |
|---|---|---|---|
| **C1** | Deep-link route `/strategies/$subId` (TanStack file route), detail page = chart + shell 2-tab; sidebar `Link` thay `onSelect` | URL shareable, back/forward, reload giữ state; detail có không gian rộng cho history table + compare; foundation tái dùng cho slice 3/4/5 | Refactor `StrategiesPageLayout`: bỏ `selectedSub` useState, chuyển sang route param + `Outlet`; phải xử lý layout list+detail (master-detail qua nested route) |
| **C2** | Giữ 3-pane, đổi `DashboardColumn` thành 2 tab Backtest/Forward | Refactor ít nhất; không đụng routing | Cột 360px quá chật cho history table + compare 2 run; vẫn không deep-link/shareable; slice sau (orders/explain) càng chật ⇒ nợ kỹ thuật dồn |
| **C3** | Lai: giữ sidebar, main area rộng chứa shell 2-tab (không param route, chọn bằng state) | Rộng hơn C2; refactor vừa | Vẫn không URL-driven (mất shareable/back-forward — yêu cầu chính của "deep-link"); nửa vời, slice sau vẫn phải lên C1 |

**Recommend: C1**. Đây là "UI foundation" mà 4 slice sau dựa vào; chỉ C1 cho URL-driven shareable + đủ không gian. C2/C3 tiết kiệm trước-mắt nhưng dồn nợ.

---

## 5. Recommended Solution

**Storage A3 + Navigation C1.**

- **A3**: thêm collection `backtest_history` (append-only, full BacktestResult doc + `subscription_id` + `run_kind` để phân biệt scheduled vs manual về sau). Worker `run_subscription` sau khi `save_for_subscription` (slot, giữ nguyên) thì **append 1 history doc**. `backtest_runs` slot không đổi ⇒ sidebar/status path zero-regression. List/detail/compare đọc từ `backtest_history`.
- **C1**: route `/strategies/$subId` master-detail; sidebar dùng `Link` deep-link; detail = `StrategyChart` (locked symbol+interval) + shell 2-tab (`Backtest` active, `Forward` placeholder). Backtest tab = history table → chọn run → run-detail (tái dùng `BacktestPanel`) / chọn 2 → compare.

**Invariant giữ nguyên**:
- import-linter: history collection repo nằm `core.infra.persistence.repositories` (cùng `backtest_repository.py` hoặc file mới `backtest_history_repository.py`); query service ở `backtest`/`engine`; route ở `app`; không import fastapi ngoài app.
- uuid7 PK: history doc `_id` = `generate_id_str()` (`core.common.uuid`), không bson/ObjectId.
- single uvicorn worker: append history chạy trong worker `run_subscription` hiện có, không thêm process/scheduler/connection mới.

---

## 6. Vertical Slice Breakdown

### 6.1 Backend

| Layer | File | Change |
|---|---|---|
| constants | `core/common/constants.py` | thêm `COLLECTION_BACKTEST_HISTORY = "backtest_history"` |
| repo | `core/infra/.../backtest_history_repository.py` (mới) hoặc method trong `backtest_repository.py` | `append_run(sub_id, result)` (uuid7 `_id`, set `subscription_id`, `run_kind`, copy metrics/equity_curve/open_positions/config_snapshot/started_at/completed_at); `list_by_subscription(sub_id, limit)`; `get_run(run_id)`; `ensure_indexes` → index `[(subscription_id,1),(started_at,-1)]` |
| worker | `backtest/workers/backtest_dispatch.py` | sau `save_for_subscription` (`:219`) gọi `history_repo.append_run(sub_id, result)` (chỉ khi `status=="completed"`/`"failed"` theo policy); inject `history_repo` vào `BacktestDispatchDeps` |
| query svc | `backtest/backtest_query_service.py` | `list_subscription_runs(ListSubRunsQuery)`; `get_subscription_run(GetSubRunQuery)` build `positions[]` từ `backtest_trades.list_by_run(run_id)` + `open_positions` (port logic `_assemble_single_response:121-167`, tách thành helper dùng chung để DRY); `compare_runs(CompareRunsQuery: run_id_a, run_id_b)` |
| route | `app/routes/backtest.py` | thêm dưới `subscription_router` (strategy.py) hoặc `backtest_router`: `GET /subscriptions/{sub_id}/backtest/runs`, `GET /subscriptions/{sub_id}/backtest/runs/{run_id}`, `GET /subscriptions/{sub_id}/backtest/compare?a=&b=`; dùng `FromDishka[BacktestQueryService]`, `DishkaRoute` |
| DI | provider của BacktestDispatchDeps + worker | wire `BacktestHistoryRepository` |

**DTO shapes (BE)**:
- History row: `{ run_id, run_kind, started_at, completed_at, status, date_range:{start,end}, parameters, metrics: BacktestMetrics.to_dict() }` (date_range lấy từ `config_snapshot`).
- Run detail: tái dùng shape `SubscriptionBacktest` hiện có — `{ run_id, status, metrics, positions[], equity_curve[], config_snapshot, started_at, completed_at }` (FE component tái dùng ngay).
- Compare: `{ a: <row+metrics>, b: <row+metrics> }` (FE diff 2 cột; equity overlay tuỳ chọn).

**Import-linter compliance**: tất cả repo ở `core.infra`; service ở `backtest`; route ở `app`; helper assemble-positions đặt ở `backtest` (đang import `core.domain` + repos — hợp lệ). Không thêm import fastapi vào core/engine/backtest.

### 6.2 Frontend

| Item | File | Change |
|---|---|---|
| route | `web/src/routes/strategies.$subId.tsx` (mới) | file route param `$subId`; loader/`useParams`; render detail; `strategies.tsx` thành layout có `Outlet` (master-detail) hoặc index = empty-state |
| sidebar | `strategy-list-sidebar.tsx` | `onSelect` → `<Link to="/strategies/$subId" params>`; highlight theo route param thay `selectedSubId` prop |
| shell | `components/strategy/subscription-detail/index.tsx` (mới) | chart locked symbol+interval + tab bar `Backtest`/`Forward` (Forward = placeholder); Backtest tab mount history view |
| history table | `.../backtest-history-table.tsx` (mới) | cột date-range/params/8 metric; row click → select run; multiselect ≤2 → compare |
| run detail | tái dùng `backtest-panel/index.tsx` `BacktestPanel` | feed run-detail DTO (đã đúng `SubscriptionBacktest` shape) |
| compare | `.../backtest-compare-view.tsx` (mới) | 2 cột metric cạnh nhau + delta |
| api | `backtest-api.ts` | `listSubscriptionRuns(subId)`, `getSubscriptionRun(subId, runId)`, `compareRuns(subId, a, b)` + types `BacktestRunRow`, reuse `SubscriptionBacktest`, `BacktestCompare` |
| hooks | `hooks/use-backtest-history.ts` (mới) | `useSubscriptionRuns(subId)`, `useSubscriptionRun(subId, runId)`, `useCompareRuns(...)`; query keys `['sub-runs',subId]`, `['sub-run',subId,runId]` |

### 6.3 API Contract

```
GET /api/v1/subscriptions/{sub_id}/backtest/runs?limit=50
→ 200 [ { run_id, run_kind, status, started_at, completed_at,
          date_range:{start,end}, parameters, metrics:{...8+ fields} } ]   // [] nếu chưa run

GET /api/v1/subscriptions/{sub_id}/backtest/runs/{run_id}
→ 200 { run_id, status, metrics, positions:[{entry_price,entry_time,exit_price,
        exit_time,quantity,sl_price,tp_price,pnl,commission}],
        equity_curve:[{timestamp,equity,drawdown}], config_snapshot,
        started_at, completed_at }
→ 404 nếu run_id không thuộc sub

GET /api/v1/subscriptions/{sub_id}/backtest/compare?a={run_id}&b={run_id}
→ 200 { a:{...run row+metrics}, b:{...run row+metrics} }
→ 404 nếu a hoặc b không thuộc sub
```

---

## 7. Decomposition into Sub-tasks (ordered, mỗi task shippable)

1. **BE storage**: thêm `COLLECTION_BACKTEST_HISTORY`, `BacktestHistoryRepository` (`append_run`/`list_by_subscription`/`get_run`/`ensure_indexes`), DI wire. Test: append + list trả đúng N run.
2. **BE worker append**: `run_subscription` append history sau slot save; inject vào deps. Test: chạy 2 lần → history có 2 doc, slot vẫn 1.
3. **BE assemble helper + query svc**: tách positions-assembly thành helper dùng chung (`_assemble_single_response` + run-detail); `list_subscription_runs`/`get_subscription_run`/`compare_runs`. Test: run-detail build positions từ `backtest_trades`.
4. **BE routes**: 3 endpoints mới + response_model. Test: 404 path, list shape, compare shape.
5. **FE deep-link route**: `strategies.$subId.tsx` + sidebar `Link` + master-detail layout. Ship: URL đổi, back/forward chạy, reload giữ sub.
6. **FE shell 2-tab**: subscription-detail chart + Backtest/Forward (Forward placeholder).
7. **FE history table + api/hooks**: list runs, render 8 metric/dòng.
8. **FE run-detail**: chọn run → `BacktestPanel` render run đó.
9. **FE compare**: chọn 2 run → compare view.

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **A1 phá `get_subscription_statuses`** (nếu lỡ chọn A1): `$in` nhiều doc/sub → status sidebar sai (`:230-235`) | Chọn A3 — slot `backtest_runs` bất biến; history tách collection riêng |
| Refactor routing C1 vỡ state cũ (selectedSub) | Master-detail nested route + `Outlet`; index route giữ empty-state; sidebar highlight theo `useParams` |
| Run-detail thiếu `positions` (cache-slot doc không có field này, `entities.py:42-55`) | get_subscription_run build positions từ `backtest_trades(run_id)` + `open_positions` (helper dùng chung, KHÔNG đọc doc.positions) |
| Worker ghi 2 nơi (slot + history) → partial write nếu crash giữa chừng | Append history sau slot save; history là phụ trợ — slot vẫn nhất quán; append idempotent theo run uuid (skip nếu `_id` đã tồn tại) |
| History phình to (mỗi run full equity_curve) | `list_by_subscription` projection bỏ `equity_curve`/`positions` (chỉ metrics + meta); detail mới load đầy đủ; index `(subscription_id, started_at desc)` + `limit` |
| Run cũ trước slice 1 không có history | Chấp nhận: history bắt đầu từ slice 1 (table trống cho sub chưa chạy lại); không backfill |
| `list_by_strategy_code` (`/backtest/strategy/{code}`) vẫn không filter symbol+interval | Ngoài scope slice 1 (history theo sub_id thay thế); để nguyên, không đụng |

---

## 9. Success Metrics & Validation

- BE: `just test` (unit repo + query svc + worker append), `just lint`, `just types` (mypy), import-linter pass 7 contracts.
- FE: `cd web && npm run lint && npm run build`.
- Chức năng: 2 run khác date-range → 2 dòng history phân biệt; mở run cũ → metrics/positions/equity của chính run đó; compare 2 run → 2 cột metric + delta; sidebar status (latest) không đổi hành vi (regression check trên `list_symbols`).
- Deep-link: `/strategies/{id}` reload giữ state; back/forward chạy; copy URL mở đúng sub.

---

## 10. Dependencies & Open Questions

**Cross-ref reports sibling** (cùng `plans/reports/`):
- `slice-2-*-adhoc-run-*-report.md` — ad-hoc run form ghi vào history store (A3) của slice này; dùng lại shell 2-tab.
- `slice-3-*-live-equity-kpi-*-report.md`, `slice-4-*-orders-*-report.md`, `slice-5-*-explain-trade-*-report.md` — đều dùng deep-link 2-tab shell (C1) của slice này; Forward tab placeholder mở rộng từ slice 3.

**Quyết định cần user chốt ở plan phase**:
- **A?** — Storage: A3 (collection `backtest_history` riêng, recommend) vs A2 (1 collection + `kind` field + partial unique index). Cả hai giữ slot bất biến; A3 tách sạch hơn, A2 ít collection hơn.
- **C?** — Navigation: C1 (deep-link `/strategies/$subId`, recommend) đã coi như chốt vì là foundation; xác nhận chấp nhận refactor `StrategiesPageLayout` sang master-detail.
- `run_kind` policy: history có lưu run `failed` không, hay chỉ `completed`? (đề xuất: lưu cả hai, table filter mặc định `completed`).
- Compare view: chỉ diff metrics (đề xuất slice 1) hay overlay 2 equity curve trên 1 chart (có thể hoãn)?

---

Status: DONE
