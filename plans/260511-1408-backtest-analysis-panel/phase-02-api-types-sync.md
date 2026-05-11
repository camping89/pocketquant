---
phase: 2
title: "API Types Sync"
status: pending
priority: P1
effort: "0.5d"
dependencies: [1]
---

# Phase 2: API Types Sync

## Overview

Đồng bộ TS types với backend shape sau Phase 1. Verify `GET /api/v1/strategies/{sid}/symbols/{subId}/backtest` trả đủ `positions + equity_curve + metrics + config_snapshot`. Add `direction` field vào `BacktestPosition`. Loại bỏ duplicate type giữa `backtest-api.ts` và `strategy-api.ts`.

## Requirements

- Functional:
  - TS `SubscriptionBacktest` type khớp với `BacktestResult.to_dict()` shape.
  - `BacktestPosition.direction: 'LONG' | 'SHORT'` available.
  - `equity_curve: EquityPoint[]` available.
  - `metrics: BacktestMetrics` available.
- Non-functional: no duplicate types, tsc compiles clean.

## Architecture

### Single source of truth

```typescript
// api/backtest-api.ts (canonical types)
export interface BacktestPosition {
  direction: 'LONG' | 'SHORT'      // NEW
  entry_price: number
  entry_time: string
  exit_price: number | null
  exit_time: string | null
  quantity: number
  sl_price: number | null
  tp_price: number | null
  pnl: number
  commission: number
}

export interface BacktestMetrics {
  total_return: number
  cagr: number
  sharpe_ratio: number
  sortino_ratio: number              // ADD
  max_drawdown: number
  win_rate: number
  profit_factor: number              // ADD
  total_trades: number
  winning_trades: number
  losing_trades: number
  avg_win: number                    // ADD
  avg_loss: number                   // ADD
  avg_trade_duration_seconds: number | null  // ADD
  total_commission: number
}

export interface EquityPoint {
  timestamp: string
  equity: number
  drawdown: number
}

export interface SubscriptionBacktest {
  run_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  metrics: BacktestMetrics | null
  positions: BacktestPosition[]
  equity_curve: EquityPoint[]        // ADD
  config_snapshot?: Record<string, unknown>
  started_at?: string
  completed_at?: string
  error_message?: string | null
}
```

`strategy-api.ts` import `SubscriptionBacktest` từ `backtest-api.ts` (no redefine).

## Related Code Files

### Modify
- `packages/pocketquant-web/src/api/backtest-api.ts` — extend types
- `packages/pocketquant-web/src/api/strategy-api.ts` — import `SubscriptionBacktest` từ backtest-api, bỏ redefine local
- `packages/pocketquant-web/src/components/chart/position-box-primitive.ts` — `PositionData` thêm `direction` field, box color theo direction (đã có pnl-based, giữ logic, thêm visual cue cho SHORT vd diagonal stripe pattern hoặc icon)

## Implementation Steps

1. **Verify backend response** — manual `curl` hoặc `/health` smoke test sau Phase 1 redeploy. Check fields: `positions[].direction`, `equity_curve[]`, `metrics.sortino_ratio`, etc.
2. **Update `backtest-api.ts`** — extend interfaces theo Architecture block.
3. **Update `strategy-api.ts`** — remove local `SubscriptionBacktest` definition (nếu có), import từ `backtest-api.ts`.
4. **Update `position-box-primitive.ts`** — `PositionData` thêm `direction`. Khi SHORT, render box pattern khác (vd `ctx.fillStyle` semi-transparent với pattern hoặc bóng đậm hơn). KISS: tạm thời thêm 1 dòng text `[SHORT]` vào info block là đủ.
5. **Update `trading-chart.tsx`** — map `direction` từ position vào `PositionData`.
6. **tsc check** — `cd packages/pocketquant-web && pnpm tsc --noEmit`.

## Success Criteria

- [ ] `SubscriptionBacktest` chứa đủ `equity_curve` + `metrics` fields
- [ ] `BacktestPosition.direction` tồn tại
- [ ] No duplicate type definitions giữa 2 api files
- [ ] `pnpm tsc --noEmit` passes
- [ ] Position box hiển thị direction label trong info block

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Backend response shape khác (camelCase vs snake_case) | Inspect response trước khi viết types — backend dùng snake_case từ `to_mongo()` |
| `direction` missing trên doc cũ → FE crash | Fallback `direction ?? 'LONG'` trong consumer code |

## Notes

- Backend đã serialize `avg_trade_duration_seconds` (xem `BacktestMetrics.to_mongo:161`).
- Không tạo new endpoint — KISS, reuse `getSubscriptionBacktest`.
