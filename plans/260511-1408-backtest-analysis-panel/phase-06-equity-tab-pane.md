---
phase: 6
title: "Equity Tab Pane"
status: pending
priority: P2
effort: "1d"
dependencies: [3]
---

# Phase 6: Equity Tab Pane

## Overview

Equity curve + drawdown subchart hiển thị qua Lightweight-charts v5 **pane API** (`chart.addPane()`) trên main chart instance — KHÔNG tạo chart riêng. Mount khi user mở tab Equity, unmount khi switch tab khác (giảm GPU). Sync timeScale tự động với main candle pane.

## Requirements

- Functional:
  - Pane index 1 chứa LineSeries `equity` (xanh) + AreaSeries `drawdown` (đỏ, scale phải).
  - TimeScale auto-sync với main chart (built-in).
  - Stretch factor: main pane 3, equity pane 1.
  - Mount/unmount theo tab active.
- Non-functional: không flicker khi switch tabs, < 150 LOC.

## Architecture

### Pane lifecycle

```typescript
// equity-tab.tsx
useEffect(() => {
  const chart = chartRef.current
  if (!chart) return

  const equityPane = chart.addPane()
  const equityPaneIdx = chart.panes().length - 1

  const equitySeries = chart.addSeries(LineSeries, {
    color: '#26a69a',
    lineWidth: 2,
    priceLineVisible: false,
  }, equityPaneIdx)

  const ddSeries = chart.addSeries(AreaSeries, {
    topColor: 'rgba(239,83,80,0.4)',
    bottomColor: 'rgba(239,83,80,0.0)',
    lineColor: '#ef5350',
    priceScaleId: 'drawdown',  // separate scale right side
  }, equityPaneIdx)

  equitySeries.setData(equity_curve.map(p => ({
    time: toUTCTimestamp(p.timestamp) as UTCTimestamp,
    value: p.equity,
  })))

  ddSeries.setData(equity_curve.map(p => ({
    time: toUTCTimestamp(p.timestamp) as UTCTimestamp,
    value: p.drawdown,
  })))

  // Set stretch factors
  const panes = chart.panes()
  panes[0].setStretchFactor(3)
  panes[equityPaneIdx].setStretchFactor(1)

  return () => {
    chart.removePane(equityPaneIdx)
  }
}, [equity_curve, chartRef])
```

### Chart ref injection

`TradingChart` expose chart instance qua `onChartReady` callback (added trong Phase 5). `EquityTab` receive ref via prop từ panel parent.

### Data source

`backtest.equity_curve: EquityPoint[]` từ Phase 2 types. Available after backtest completed.

## Related Code Files

### Create
- `packages/pocketquant-web/src/components/strategy/backtest-panel/equity-tab.tsx`
- `packages/pocketquant-web/src/components/strategy/backtest-panel/use-equity-pane.ts` — hook encapsulate pane lifecycle

### Modify
- `packages/pocketquant-web/src/components/strategy/backtest-panel/index.tsx` — accept + forward chart ref
- `packages/pocketquant-web/src/routes/index.tsx` — pass chart ref to BacktestPanel
- `packages/pocketquant-web/src/components/chart/trading-chart.tsx` — `onChartReady` callback (already added Phase 5 — confirm)

## Implementation Steps

1. **Verify lightweight-charts version** — `cat packages/pocketquant-web/package.json | grep lightweight`. Must be ≥5.0.8 cho pane API. Upgrade nếu < 5.0.8.
2. **Create `use-equity-pane.ts`** — hook params: `chart`, `equity_curve`. Encapsulate addPane + addSeries + setData + cleanup.
3. **Create `equity-tab.tsx`** — receive `equity_curve` + `chart` ref qua props. Call hook. Render empty (pane is rendered by chart itself).
4. **Wire chart ref** — `TradingChart` `onChartReady(chart)` → routes/index.tsx state → pass to `<BacktestPanel chartRef={chartRef}>` → forward to `<EquityTab chart={chart}>`.
5. **Tab unmount cleanup** — Phase 3 lazy tab render means tab component unmount on switch → hook cleanup remove pane automatically. Verify no flicker.
6. **Drawdown scale** — separate `priceScaleId: 'drawdown'`, configure right side scale, scale range fit drawdown values (negative).
7. **Hover tooltip** — optional: show equity + drawdown value tại crosshair time. Reuse existing OHLCV legend pattern nếu khả thi. KISS: skip cho v1, add nếu user request.
8. **Smoke test** — chọn sub, mở tab Equity → pane xuất hiện dưới candle, zoom/pan sync; switch sang Metrics → pane biến mất; switch lại → pane re-appear.

## Success Criteria

- [ ] Lightweight-charts version ≥5.0.8 confirmed
- [ ] Equity pane render khi tab Equity active
- [ ] Pane unmount khi switch tab khác (no leak)
- [ ] TimeScale sync với main chart (zoom main → equity zoom theo)
- [ ] Drawdown area visible với scale riêng bên phải
- [ ] Stretch factor 3:1 main:equity
- [ ] No flicker khi rapid tab switch

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| lightweight-charts < 5.0.8 (no addPane API) | Phase 0 step: upgrade nếu cần. Major version v5 should already be in deps |
| Pane index conflict với indicator panes (RSI etc) | Use `chart.panes().length - 1` thay vì hardcode idx 1 |
| Equity data scale rất khác candle scale | Tự động — separate pane = separate price scales |
| Drawdown 0-only (no losses) → area invisible | Acceptable; means strategy never drawdown |

## Notes

- Pane API v5 docs: `chart.addPane()`, `chart.removePane(idx)`, `paneIndex` parameter on `addSeries`.
- KHÔNG dùng separate chart instance — sync logic complex, theming duplicate.
- Equity points đã sparse (chỉ trên close, sau Phase 1 refactor) → render fast.
