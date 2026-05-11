---
phase: 5
title: "Positions Tab"
status: pending
priority: P2
effort: "1d"
dependencies: [3]
---

# Phase 5: Positions Tab

## Overview

Table list backtest positions với sort/filter. Click row → zoom chart vào range của position + highlight position box trên chart. Footer aggregate count/sum PnL cho filter hiện tại.

## Requirements

- Functional:
  - Columns: `#`, `Entry Time`, `Direction` (LONG/SHORT badge), `Entry`, `Exit`, `Qty`, `Duration`, `PnL`, `Fee`, `Status` (Open/Closed).
  - Sort: click header → toggle asc/desc, persist trong-session.
  - Filter chips: `All | Wins | Losses | Open`. Multi-select không cần — single filter.
  - Click row → `chart.timeScale().setVisibleRange()` zoom đến position + outline highlight box.
  - Footer: count + sum PnL theo filter.
- Non-functional: virtualize nếu > 200 rows (TanStack Virtual already trong deps?).

## Architecture

### Position highlight communication

Vấn đề: tab tự render bảng, chart ở scope khác. Need shared state cho highlight.

Solution: lift state qua `routes/index.tsx` (hoặc context).

```typescript
// routes/index.tsx
const [highlightedPos, setHighlightedPos] = useState<number | null>(null) // index trong positions array

<TradingChart
  ...
  positions={positions}
  highlightedPositionIdx={highlightedPos}
/>

<BacktestPanel
  backtest={backtestDoc}
  onPositionClick={(idx, pos) => {
    setHighlightedPos(idx)
    chartRef.current?.timeScale().setVisibleRange({
      from: toUTCTimestamp(pos.entry_time) - pad,
      to: (pos.exit_time ? toUTCTimestamp(pos.exit_time) : lastBarTime) + pad,
    })
  }}
/>
```

Chart ref expose qua callback `onChartReady` từ `TradingChart`.

### `PositionBoxPrimitive` highlight

Thêm `highlightIdx?: number` vào constructor. Renderer: nếu position idx match → vẽ outline border 2px màu vàng/cam.

### Sort + filter state

`useState` trong tab — non-persisted (KISS).

```typescript
const [sortBy, setSortBy] = useState<SortKey>('entry_time')
const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
const [filter, setFilter] = useState<FilterKey>('all')

const filtered = useMemo(() => applyFilter(positions, filter), [positions, filter])
const sorted = useMemo(() => sortPositions(filtered, sortBy, sortDir), [filtered, sortBy, sortDir])
```

### Virtualization

TanStack Virtual khi rows > 200. Else plain render.

## Related Code Files

### Create
- `packages/pocketquant-web/src/components/strategy/backtest-panel/positions-tab.tsx`
- `packages/pocketquant-web/src/components/strategy/backtest-panel/positions-table.tsx` — table component
- `packages/pocketquant-web/src/components/strategy/backtest-panel/positions-filter.tsx` — filter chips
- `packages/pocketquant-web/src/components/strategy/backtest-panel/positions-utils.ts` — sort/filter/format helpers

### Modify
- `packages/pocketquant-web/src/components/chart/position-box-primitive.ts` — accept `highlightIdx`, render outline khi match
- `packages/pocketquant-web/src/components/chart/trading-chart.tsx` — accept `highlightedPositionIdx`, expose chart ref qua `onChartReady` callback, pass idx vào primitive
- `packages/pocketquant-web/src/routes/index.tsx` — lift highlight state, wire callback

## Implementation Steps

1. **`positions-utils.ts`**:
   - `applyFilter(positions, filter)` — all/wins (pnl>0)/losses (pnl<0)/open (exit_time === null).
   - `sortPositions(positions, key, dir)`.
   - `formatDuration(entry, exit)` — entry-to-exit, "—" nếu open.
   - `formatPnl(n)` — signed number.
2. **`positions-filter.tsx`** — render 4 chips, active highlighting.
3. **`positions-table.tsx`** — render header (clickable sort) + rows. Row props: `position`, `index`, `isHighlighted`, `onClick`. Row hover effect.
4. **`positions-tab.tsx`** — orchestrate filter + sort + table. Footer aggregate `<div>{filtered.length} positions · Total PnL: {sum}</div>`.
5. **Update `PositionBoxPrimitive`** — store `highlightIdx`, renderer check `for (let i = 0; i < positions.length; i++) { if (i === highlightIdx) ctx.strokeStyle = '#FFD600'; ctx.strokeRect(...) }`.
6. **Update `TradingChart`** — prop `highlightedPositionIdx`, recreate primitive khi change. Add `onChartReady?: (chart) => void` callback.
7. **Update `routes/index.tsx`** — lift `highlightedPositionIdx` state, ref to chart instance via callback, wire `onPositionClick` to BacktestPanel → forward to PositionsTab.
8. **Virtualization** — nếu rows > 200, dùng TanStack Virtual `useVirtualizer`. Check `package.json` xem có `@tanstack/react-virtual` không, install nếu thiếu.
9. **Test** — backtest có 20+ positions, sort tất cả columns, filter chips, click row → zoom + highlight.

## Success Criteria

- [ ] Table render đủ 10 columns
- [ ] Sort hoạt động trên all columns
- [ ] Filter chips: all/wins/losses/open
- [ ] Click row → chart zoom đúng range + highlight box outline vàng
- [ ] Footer aggregate chính xác
- [ ] Direction badge LONG xanh, SHORT đỏ
- [ ] Open positions hiển thị "Open" status + exit "—"
- [ ] Performance OK với 500+ rows (virtualize nếu cần)

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Highlight + zoom đồng thời gây race với primitive re-attach | Memo primitive recreation; debounce zoom |
| Click row nhanh nhiều lần re-create primitive lag | useMemo posData, chỉ recreate primitive khi `highlightIdx` change (KHÔNG khi positions data unchanged) |
| Virtual + filter combo edge cases | Test thoroughly with edge filter states |

## Notes

- TimeScale `pad`: `(exit_time - entry_time) * 0.2` mỗi side, min 5 bars.
- Direction badge style: pill rounded với màu fill nhạt.
