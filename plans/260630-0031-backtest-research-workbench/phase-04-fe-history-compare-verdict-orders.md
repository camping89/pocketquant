---
phase: 4
title: "FE history compare verdict orders"
status: completed
priority: P2
dependencies: [3]
---

# Phase 4: FE history compare verdict orders

<!-- Updated: Validation Session 1 - compare cross-scope, default scope rỗng, verdict optimistic-revert, diff direction map -->

## Overview

Hoàn thiện workbench: **history rail** (list run scoped, từ `GET /backtest/strategy/{id}?symbol=&interval=` mở rộng ở P1), **compare view** (2–3 run: equity overlay + metrics diff table), **verdict panel** (đọc/sửa qua `PATCH` đã có), **Orders tab** (bảng lazy-load + drawer fills/events từ `GET /{run_id}/orders` ở P1). Khép luồng "chạy nhiều → so sánh → annotate → chốt".

## Requirements

- Functional:
  - **History rail:** bảng run (started_at, status, return/sharpe/win_rate/max_dd/#trades, verdict snippet), scope theo (strategy_code, **symbol composite**, interval), sort client-side, row click → `/backtest/$runId`, checkbox 2–3 → Compare. **Default scope (validation Q5): rỗng đến khi chọn strategy** — chưa chọn → empty state "chọn strategy để xem lịch sử"; chọn strategy (dropdown từ `GET /backtest/strategies` registry) → load run gần nhất; symbol/interval = optional filter thu hẹp.
  - **Compare** (`/backtest/compare?runs=`): **cross-scope** (validation Q2 — cho compare run khác strategy/symbol/interval); equity overlay **bắt buộc normalize %** từ initial_capital (lightweight-charts multi-series); metrics diff table (cột=run, highlight ô best mỗi hàng theo direction map).
  - **Verdict panel:** card header dashboard, đọc `verdict`, textarea edit, Save → `PATCH /{run_id}/verdict`. **Optimistic + revert on fail (validation Q6):** set ngay; fail (404/500) → revert verdict cũ trong cache nhưng **GIỮ text textarea** + toast lỗi + cho retry.
  - **Orders tab:** bảng orders lazy-load (fetch khi mở tab), row → drawer `fills[]`+`events[]`+link `resulting_trade_id`. DTO key `order_id` (P1).
- Non-functional: history scope **gửi symbol composite `CODE:EXCHANGE`** (red-team H1 — không bare code); orders virtualize nếu >200 dòng; thuần CSS variables; module API `web/src/api/backtest-api.ts`; component co-locate `components/backtest/`.

## Architecture

```
/backtest index:  <BacktestForm> + <RunHistoryRail scope={strategy,symbol,interval}>  ──row──► /backtest/$runId
                                          └─ checkbox 2–3 ──► /backtest/compare?runs=a,b,c
/backtest/$runId: <VerdictPanel>(header) + <BacktestResultView> ─ Orders tab: <OrdersTable> ─row─► <OrderDetailDrawer>
/backtest/compare: <RunCompareView> = <EquityOverlay> + <MetricsDiffTable>
```

- History: `useBacktestRuns(scope)` query `['backtest-runs', scope]` → `GET /backtest/strategy/{strategy}?symbol={composite}&interval={i}` (endpoint mở rộng P1, **KHÔNG `/runs`** — red-team H4). Scope picker reuse giá trị run form (symbol composite).
- Compare: parse `?runs=` → fetch mỗi run (reuse `useBacktestRun`) → overlay normalize % từ initial_capital + diff. **Direction map** highlight ô best (validation Q4): cao=tốt {total_return, cagr, sharpe_ratio, sortino_ratio, win_rate, profit_factor, avg_win}; gần-0/cao=tốt (ít âm) {max_drawdown, avg_loss}; thấp=tốt {total_commission, avg_trade_duration_seconds}; trung tính không highlight {total_trades, winning_trades, losing_trades}.
- Verdict: `useSetVerdict` → `PATCH`; invalidate run query; 404 → revert + toast.
- Orders: `useBacktestOrders(runId, {enabled: tabActive})` lazy → `GET /{run_id}/orders`. Drawer reuse `.drawer-in`.

## Related Code Files

- Create (co-locate `components/backtest/`): `run-history-rail.tsx`, `backtest-history-table.tsx`, `run-compare-view.tsx`, `equity-overlay.tsx`, `metrics-diff-table.tsx`, `verdict-panel.tsx`, `orders-table.tsx`, `order-detail-drawer.tsx`.
- Modify: `web/src/api/backtest-api.ts` (**module đúng**) — `listBacktestRuns(scope)`, `fetchBacktestOrders(runId)`, `setVerdict(runId, verdict)` + types `BacktestRunRow`, `BacktestOrder`, `OrderFill`, `OrderEvent`.
- Modify: `web/src/hooks/use-backtest-run.ts` — `useBacktestRuns(scope)`, `useBacktestOrders(runId, enabled)`, `useSetVerdict()`.
- Modify: `web/src/routes/backtest.tsx` — mount `<RunHistoryRail>` vào slot (P2).
- Modify: `web/src/routes/backtest.compare.tsx` — fill `<RunCompareView>`.
- Modify: `web/src/components/backtest/backtest-result-view.tsx` — Orders tab + VerdictPanel header.

## Implementation Steps

1. `backtest-api.ts` + types: `listBacktestRuns` (gửi symbol composite), `fetchBacktestOrders`, `setVerdict`.
2. `use-backtest-run.ts`: 3 hook (runs scoped, orders lazy, verdict mutation).
3. `RunHistoryRail` + `backtest-history-table`: scope picker (symbol composite) + bảng + sort + multiselect → nav compare.
4. `VerdictPanel`: textarea + Save (optimistic + invalidate + 404 revert).
5. Orders tab: `OrdersTable` (lazy, virtualize >200) + `OrderDetailDrawer` (fills/events, key order_id).
6. `RunCompareView`: `EquityOverlay` (normalize %) + `MetricsDiffTable` (highlight best).
7. Ráp routes (index rail, compare, $runId orders+verdict).
8. `npm run lint && npm run build`.

## Success Criteria

- [x] History rail: 2 run khác date-range cùng scope → 2 dòng; run symbol khác KHÔNG lẫn (gửi composite khớp).
- [x] Row click → `/backtest/$runId`; checkbox 2–3 → `/backtest/compare?runs=`.
- [x] Compare: equity overlay + diff table highlight ô best.
- [x] Verdict: sửa + Save → persist (reload giữ); clear (null) OK; 404 revert.
- [x] Orders tab: lazy-load khi mở; drawer fills+events; key `order_id`; link resulting_trade_id.
- [x] `npm run lint && npm run build` pass.

## Risk Assessment

- **History trộn symbol (red-team H1):** scope picker gửi symbol composite khớp doc; dùng `/strategy/{id}` mở rộng (KHÔNG `/strategy/{id}` cũ không filter, KHÔNG `/runs`).
- **Orders nhiều dòng:** lazy-load (chỉ khi mở tab) + virtualize >200.
- **Compare cross-scope (validation Q2):** cho phép compare run khác strategy/symbol/interval; equity overlay BẮT BUỘC normalize % từ initial_capital (trục giá khác nhau không so trực tiếp được).
- **Verdict optimistic:** invalidate sau PATCH; 404 → revert + toast.
- **Phụ thuộc P1+P2+P3:** endpoint (P1), routing (P2), dashboard tabs (P3) xong trước.
