---
phase: 5
title: "Frontend single-run UI"
status: done
effort: ""
---

# Phase 5: Frontend single-run UI

## Overview

Thêm UI single-run backtest (route `/backtest`): form trigger (strategy/symbol/interval/dates/params) → `POST /backtest/run` → poll `GET /backtest/{run_id}` → trang kết quả (metrics + equity + trades/positions). Resolve red-team H5 (single-run giờ có FE consumer). Tái dùng backtest-panel components giữ lại từ phase 4.

## Requirements

- Functional: trang `/backtest` — form chọn strategy (từ `GET /backtest/strategies`), symbol, interval, start/end date, optional params → submit.
- Functional: submit → `POST /backtest/run` → nhận `run_id` → poll `GET /backtest/{run_id}` mỗi ~1.5-2s tới `finished`/`failed`.
- Functional: hiển thị kết quả — metrics cards, equity curve (chart), trades/positions table. Reuse `backtest-panel/*` (MetricsTab, PositionsTab, equity) giữ từ phase 4.
- Functional: badge `started`(spinner)/`finished`/`failed` + error_message khi failed.
- Non-functional: `npm run lint` + `npm run build` xanh; TanStack Router file-based route.
- Constraint (C6): status literal mới CHỈ trong backtest scope; KHÔNG đụng forward/job/sync.

## Architecture

FE dùng TanStack Router file-based (`web/src/routes/`: `index`, `monitor`, `strategies`). Thêm `routes/backtest.tsx` → route `/backtest`. Nav link trong layout.

```
/backtest route:
  <BacktestForm> → useRunBacktest() mutation → POST /backtest/run → {run_id}
       ↓ setActiveRunId
  useBacktestRun(run_id) query (refetchInterval: status==='started' ? 1500 : false)
       ↓ status
  started → <RunningState spinner>
  finished → <BacktestResultView metrics + equity + trades>   (reuse backtest-panel/*)
  failed → <ErrorState error_message>
```

### API client (backtest-api.ts)
- `BacktestStatus = 'started' | 'finished' | 'failed'` (đổi từ pending/running/completed).
- `runBacktest(body): Promise<{run_id}>` → POST /backtest/run.
- `fetchBacktestRun(runId): Promise<BacktestRunResult>` → GET /backtest/{run_id}.
- `fetchBacktestEquity(runId)` → GET /backtest/{run_id}/equity (đã có endpoint).
- Type `BacktestRunResult`: status, metrics, equity_curve, config_snapshot, error_message, open_positions/trades.

### Trades/positions display (VALIDATED — endpoint riêng)
Run doc có `open_positions`. Closed trades ở `backtest_trades` collection. QUYẾT ĐỊNH (validated): endpoint riêng `GET /backtest/{run_id}/trades` (query service join `trade_repo.list_by_run`) song song `/equity` (đã có pattern). KHÔNG nhúng vào run doc (tránh phình). Backend endpoint này có thể làm ở phase 2 hoặc đầu phase 5. <!-- Updated: Validation Session 1 - trades endpoint riêng bắt buộc -->

## Related Code Files

- Create: `web/src/routes/backtest.tsx` — route `/backtest` (form + result orchestration).
- Create: `web/src/components/backtest/backtest-form.tsx` — form trigger.
- Create: `web/src/components/backtest/backtest-result-view.tsx` — kết quả (reuse panel tabs).
- Create: `web/src/hooks/use-backtest-run.ts` — mutation + poll query.
- Modify: `web/src/api/backtest-api.ts` — `BacktestStatus` mới, `runBacktest`, `fetchBacktestRun`, `BacktestRunResult` type.
- Modify: `web/src/components/strategy/backtest-status-badge.tsx` — keys `started`(spinner)/`finished`/`failed`.
- Reuse (từ phase 4, không xóa): `web/src/components/strategy/backtest-panel/metrics-tab.tsx`, `positions-tab.tsx`, equity tab, `equity-sparkline.tsx`.
- Modify: `web/src/components/layout/*` (nav) — thêm link `/backtest`.
- Maybe-modify (backend, nếu chọn trades endpoint): `app/routes/backtest.py` + `backtest_query_service.py` — `GET /backtest/{run_id}/trades`.
- Modify: `web/src/routeTree.gen.ts` — regenerate (TanStack codegen).

## Implementation Steps

1. Trades display (VALIDATED): endpoint `/backtest/{run_id}/trades` — nếu chưa làm ở phase 2, thêm backend nhỏ (route + query join `trade_repo.list_by_run`).
2. `backtest-api.ts`: `BacktestStatus` mới + `runBacktest` + `fetchBacktestRun` (+ trades fetch).
3. `backtest-status-badge.tsx`: keys started/finished/failed (C6 — chỉ backtest).
4. `use-backtest-run.ts`: mutation POST + poll query (refetchInterval khi `started`).
5. `backtest-form.tsx`: strategy dropdown (fetchStrategies), symbol/interval/date/params inputs.
6. `backtest-result-view.tsx`: metrics + equity + trades (reuse panel tabs).
7. `routes/backtest.tsx`: orchestrate form → poll → result. Regen routeTree.
8. Nav link `/backtest`.
9. `npm run lint` + `npm run build` → xanh.
10. Manual: trigger backtest từ UI → started spinner → finished → metrics/equity/trades hiển thị; failed → error.

## Success Criteria

- [x] Route `/backtest` (TanStack file route, routeTree regen): form → `POST /backtest/run` → poll `GET /backtest/{run_id}` → result.
- [x] Kết quả hiển thị metrics (MetricsTab) + equity (EquitySparkline) + trades/positions (PositionsTab) — reuse panel tabs, adapt type `BacktestRunResult`.
- [x] Badge started(spinner)/finished/failed + error_message (`backtest-status-badge` keys mới).
- [x] Poll dừng ở terminal: `useBacktestRun` refetchInterval=false khi status≠'started'.
- [x] Trades qua endpoint riêng `GET /backtest/{run_id}/trades` (join client-side trong `fetchBacktestRun`).
- [x] C6: không phá forward/job/sync badge.
- [x] `npm run lint`(0 errors) + `npm run build`(tsc + vite) xanh.

## Notes — implementation

- Orphaned BacktestPanel wrapper (`index.tsx`, `backtest-panel-header`, `use-panel-layout`, `backtest-panel-tabs`, `equity-tab`, `use-equity-pane`) xóa — chỉ phục vụ subscription chart sub-pane (đã decouple). Result view dùng `EquitySparkline` thay equity-tab.
- New files: `routes/backtest.tsx`, `components/backtest/backtest-form.tsx`, `components/backtest/backtest-result-view.tsx`, `hooks/use-backtest-run.ts`.

## Risk Assessment

- **Risk (H5)**: single-run path giờ có FE — phải test end-to-end thật. Mitigation: manual smoke + verify poll terminal.
- **Risk**: trades không có trong run doc → result thiếu trades. Mitigation: quyết endpoint `/trades` ở step 1, không để mơ hồ.
- **Risk**: reuse backtest-panel tabs vốn nhận shape SubscriptionBacktest (xóa ở phase 4) → type mismatch. Mitigation: panel tabs nhận props generic (metrics/positions/equity), adapt type cho BacktestRunResult.
- **Risk**: TanStack routeTree codegen quên regen → route 404. Mitigation: chạy dev/codegen, verify route load.
