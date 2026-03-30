---
phase: 4
priority: P1
effort: M
status: complete
depends_on: [3]
---

# Phase 4: Technical Indicators

## Overview

Client-side indicator computation + rendering as additional series/panes on the chart. 4 indicators: MA/EMA, RSI, MACD, Bollinger Bands.

## Context

- [plan.md](plan.md)
- LC v5 panes: `paneIndex: N` when adding series; `chart.pane(N).setHeight(px)`
- Indicators computed from OHLCV close prices (+ high/low for Bollinger)
- No external lib — math is simple enough to implement directly

## Requirements

### Functional
- **Moving Averages**: SMA(20), EMA(50) — overlay on candlestick pane
- **RSI(14)**: Separate pane below chart, 0-100 scale, overbought/oversold lines at 70/30
- **MACD(12,26,9)**: Separate pane — MACD line, signal line, histogram
- **Bollinger Bands(20,2)**: Overlay on candlestick pane — upper, middle, lower bands
- User can toggle each indicator on/off

### Non-Functional
- Compute <50ms for 5000 bars
- No external math library

## Architecture

```
src/
├── lib/
│   └── indicators/
│       ├── moving-average.ts   # SMA, EMA
│       ├── rsi.ts              # RSI
│       ├── macd.ts             # MACD
│       └── bollinger-bands.ts  # Bollinger Bands
├── hooks/
│   └── use-indicators.ts       # Compute + memoize indicators from OHLCV
└── components/
    └── chart/
        └── indicator-series.ts  # Add/remove indicator series on chart
```

## Indicator Math

### SMA(period)
```typescript
function sma(closes: number[], period: number): (number | null)[] {
  return closes.map((_, i) => {
    if (i < period - 1) return null;
    const slice = closes.slice(i - period + 1, i + 1);
    return slice.reduce((a, b) => a + b, 0) / period;
  });
}
```

### EMA(period)
```typescript
function ema(closes: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1);
  const result: (number | null)[] = new Array(closes.length).fill(null);
  result[period - 1] = closes.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < closes.length; i++) {
    result[i] = closes[i] * k + (result[i - 1] as number) * (1 - k);
  }
  return result;
}
```

### RSI(period=14)
Uses Wilder's smoothing (exponential moving average of gains/losses).

### MACD(fast=12, slow=26, signal=9)
- MACD line = EMA(12) - EMA(26)
- Signal line = EMA(9) of MACD line
- Histogram = MACD - Signal

### Bollinger Bands(period=20, stdDev=2)
- Middle = SMA(20)
- Upper = Middle + 2 * stddev(20)
- Lower = Middle - 2 * stddev(20)

## Pane Layout

```
┌──────────────────────────┐
│  Pane 0: Candlestick     │  ← MA, EMA, Bollinger overlay here
│  + Volume overlay         │
├──────────────────────────┤
│  Pane 1: RSI (height 100) │
├──────────────────────────┤
│  Pane 2: MACD (height 120)│
└──────────────────────────┘
```

## Implementation Steps

1. Create `src/lib/indicators/moving-average.ts` — `sma()`, `ema()`
2. Create `src/lib/indicators/rsi.ts` — `rsi()`
3. Create `src/lib/indicators/macd.ts` — `macd()` returning { macdLine, signalLine, histogram }
4. Create `src/lib/indicators/bollinger-bands.ts` — `bollingerBands()` returning { upper, middle, lower }
5. Create `src/hooks/use-indicators.ts`:
   - Takes OHLCV data + active indicator config
   - Returns memoized (`useMemo`) computed indicator data arrays
6. Create `src/components/chart/indicator-series.ts`:
   - `addIndicatorSeries(chart, type, data)` — adds appropriate series to correct pane
   - `removeIndicatorSeries(chart, seriesRef)` — cleanup
7. Integrate into `TradingChart` — add/remove indicator series based on active config
8. Add indicator toggle state (simple boolean map, lifted to parent)

## Series Config

```typescript
const INDICATOR_COLORS = {
  sma20: '#2196F3',       // blue
  ema50: '#FF9800',       // orange
  rsi: '#AB47BC',         // purple
  macdLine: '#26C6DA',    // cyan
  macdSignal: '#FF7043',  // deep orange
  macdHist: '#66BB6A',    // green (positive) / '#EF5350' (negative)
  bbUpper: 'rgba(33, 150, 243, 0.3)',
  bbMiddle: '#2196F3',
  bbLower: 'rgba(33, 150, 243, 0.3)',
};
```

## Related Code Files

- **Create:** `src/lib/indicators/*.ts`, `src/hooks/use-indicators.ts`, `src/components/chart/indicator-series.ts`
- **Modify:** `src/components/chart/trading-chart.tsx` (integrate indicators)

## Todo

- [x] Implement SMA + EMA
- [x] Implement RSI
- [x] Implement MACD
- [x] Implement Bollinger Bands
- [x] useIndicators hook with memoization
- [x] Indicator series add/remove on chart
- [x] Pane layout (RSI pane 1, MACD pane 2)
- [x] Toggle on/off state

## Success Criteria

- All 4 indicator types render correctly
- Pane heights: RSI ~100px, MACD ~120px
- Overlay indicators (MA, BB) align with candlesticks
- Toggle removes/adds series without chart flicker
- Compute time <50ms for 5000 bars
