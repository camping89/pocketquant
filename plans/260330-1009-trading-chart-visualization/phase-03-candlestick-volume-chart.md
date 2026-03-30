---
phase: 3
priority: P0
effort: M
status: complete
depends_on: [2]
---

# Phase 3: Candlestick + Volume Chart

## Overview

Core chart component using Lightweight Charts v5 — candlestick series (pane 0) + volume histogram (pane 0, overlay). Handles create/destroy lifecycle, resize, and dark theme.

## Context

- [plan.md](plan.md)
- [LC v5 research](../reports/researcher-260330-1018-tradingview-lightweight-charts-v4.md)
- LC v5 API: `createChart()`, `chart.addCandlestickSeries()`, `chart.addHistogramSeries()`, `series.setData()`, `series.update()`
- React strict mode: must handle double mount — `chart.remove()` in cleanup

## Requirements

### Functional
- Render candlestick chart from OHLCV data
- Volume bars below candlesticks (same pane, overlay at bottom)
- Crosshair with OHLCV tooltip
- Time scale auto-fits data, scrollable
- Chart resizes with container

### Non-Functional
- Smooth render for up to 5000 bars
- Dark theme by default
- Clean chart lifecycle (no memory leaks)

## Architecture

```
src/components/chart/
├── trading-chart.tsx          # Main chart container — owns IChartApi lifecycle
└── use-chart.ts               # Hook: createChart, resize observer, cleanup
```

## Key Implementation

### Chart Hook (`use-chart.ts`)

```typescript
function useChart(containerRef: RefObject<HTMLDivElement>, options?: DeepPartial<ChartOptions>) {
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#1a1a2e' },
        textColor: '#d1d4dc',
      },
      grid: {
        vertLines: { color: '#2B2B43' },
        horzLines: { color: '#2B2B43' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#2B2B43' },
      timeScale: { borderColor: '#2B2B43', timeVisible: true },
      ...options,
    });
    chartRef.current = chart;

    // Resize observer
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      chart.applyOptions({ width, height });
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  return chartRef;
}
```

### TradingChart Component (`trading-chart.tsx`)

```typescript
function TradingChart({ exchange, symbol, interval }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useChart(containerRef);
  const { data } = useOHLCV(exchange, symbol, interval);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !data) return;

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    });
    candleSeries.setData(data.candles);

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: '',  // overlay
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    volumeSeries.setData(data.volumes);

    chart.timeScale().fitContent();

    return () => {
      chart.removeSeries(candleSeries);
      chart.removeSeries(volumeSeries);
    };
  }, [data]);

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />;
}
```

## Dark Theme Colors

```typescript
const CHART_COLORS = {
  background: '#1a1a2e',
  text: '#d1d4dc',
  grid: '#2B2B43',
  border: '#2B2B43',
  upColor: '#26a69a',
  downColor: '#ef5350',
  volumeUp: 'rgba(38, 166, 154, 0.3)',
  volumeDown: 'rgba(239, 83, 80, 0.3)',
};
```

## Implementation Steps

1. Create `src/components/chart/use-chart.ts` — chart lifecycle hook with ResizeObserver
2. Create `src/components/chart/trading-chart.tsx` — candlestick + volume rendering
3. Define chart color constants (dark theme)
4. Wire `TradingChart` into `App.tsx` with hardcoded symbol for testing
5. Test with live API data — verify candles render, volume overlay works
6. Verify resize behavior (fullscreen, window resize)
7. Verify cleanup — no console warnings about disposed chart on HMR

## Related Code Files

- **Create:** `src/components/chart/use-chart.ts`, `src/components/chart/trading-chart.tsx`
- **Modify:** `src/App.tsx` (add TradingChart)
- **Depends on:** `src/hooks/use-ohlcv.ts` (Phase 2)

## Todo

- [x] Create useChart hook with lifecycle + resize
- [x] Create TradingChart component
- [x] Candlestick series with up/down colors
- [x] Volume histogram overlay
- [x] Dark theme colors
- [x] Wire into App, test with real data
- [x] Verify cleanup on unmount/HMR

## Success Criteria

- Candlestick chart renders 1000+ bars without lag
- Volume bars visible below candles (same pane)
- Crosshair shows OHLCV values
- Chart resizes with window
- No memory leaks on component unmount

## Risk Assessment

- **React strict mode double mount**: Mitigated by `chart.remove()` in cleanup + null guard
- **Large datasets**: LC v5 handles 10K+ bars natively; no virtualization needed
