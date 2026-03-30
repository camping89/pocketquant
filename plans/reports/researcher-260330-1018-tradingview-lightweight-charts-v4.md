# TradingView Lightweight Charts v4 Integration Research
**Date:** 2026-03-30 | **Status:** Complete | **Focus:** React + TypeScript Integration

---

## Executive Summary

TradingView Lightweight Charts v5.1.0 (Dec 2024) is production-ready with native pane support—**v4 is legacy and not recommended**. For new projects, adopt v5. Core findings: no official React wrapper exists; community wrappers available but lightweight library works directly with hooks; full TypeScript support; all requested features (multiple series, real-time updates, panes, theming, resize) native to library; React strict mode requires careful cleanup.

---

## 1. Latest Version & Package

| Aspect | Details |
|--------|---------|
| **Current Version** | v5.1.0 (Dec 16, 2024) |
| **npm Package** | `lightweight-charts` |
| **npm Install** | `npm install lightweight-charts` |
| **Bundle Size** | ~35kB (gzipped, down from 50kB in v4) |
| **TypeScript** | Full support—declarations bundled |
| **v4 Status** | Legacy; v5 added panes, yield curve, options charts, conflation |

**Recommendation:** Use v5.1.0. v4 reached EOL; v5 solves the pane problem (your RSI/MACD use case).

---

## 2. React Wrapper Ecosystem

| Wrapper | Status | TypeScript | Notes |
|---------|--------|-----------|-------|
| **Direct Library + Hooks** | ✅ Recommended | Native | TradingView's tutorial pattern; minimal overhead |
| **lightweight-charts-react-components** | ⚠️ Community | ✅ Yes | Declarative API; active maintenance |
| **kaktana-react-lightweight-charts** | ⚠️ Community | Partial | Simple ref-based wrapper |
| **trash-and-fire/lightweight-charts-react-wrapper** | ⚠️ Community | Unknown | Component-based abstraction |
| **Official React Wrapper** | ❌ No | — | TradingView did not ship official wrapper |

**Verdict:** No official React wrapper. Direct library + `useRef` + `useEffect` is production pattern shown in TradingView docs. If team prefers declarative API, `lightweight-charts-react-components` is most active community choice.

---

## 3. Core API Signatures

### 3.1 Chart Creation
```typescript
const chart = createChart(container: HTMLElement, options?: ChartOptions): IChartApi;
```

**Typical options:**
```typescript
createChart(containerRef.current, {
  width: 800,
  height: 600,
  layout: {
    background: { color: '#ffffff' },
    textColor: '#666',
  },
  timeScale: {
    timeVisible: true,
    secondsVisible: false,
  },
  rightPriceScale: {
    autoScale: true,
  },
})
```

### 3.2 Series Types & Creation
```typescript
// All addSeries methods return ISeriesApi<TData, HorzScaleItem, TData, TOptions>
chart.addCandlestickSeries(options?: SeriesOptions): ISeriesApi;
chart.addHistogramSeries(options?: SeriesOptions): ISeriesApi;   // Volume
chart.addLineSeries(options?: SeriesOptions): ISeriesApi;        // Indicators
chart.addAreaSeries(options?: SeriesOptions): ISeriesApi;
chart.addBarSeries(options?: SeriesOptions): ISeriesApi;
chart.addBaselineSeries(options?: SeriesOptions): ISeriesApi;
```

**CandlestickSeries data format:**
```typescript
type CandlestickData = {
  time: UTCTimestamp | BusinessDay;
  open: number;
  high: number;
  low: number;
  close: number;
};
```

**HistogramSeries (volume) data format:**
```typescript
type HistogramData = {
  time: UTCTimestamp | BusinessDay;
  value: number;
  color?: string; // Optional: color per bar
};
```

**LineSeries & AreaSeries data format:**
```typescript
type LineSeriesData = {
  time: UTCTimestamp | BusinessDay;
  value: number;
};
```

### 3.3 Real-Time Updates
```typescript
series.setData(data: TData[]): void;
series.update(bar: TData, historicalUpdate?: boolean): void;
```

**Behavior:**
- `setData()`: Replaces entire dataset. Use once on load. **Slow if called repeatedly.**
- `update()`: Adds new bar or updates last bar (if time matches). Typical usage: tick updates.
  - `historicalUpdate=true`: Updates any non-latest bar (slower, useful for corrections).
  - Default `historicalUpdate=false`: Only updates most recent bar.

**Pattern:**
```typescript
// Load initial data
series.setData(historicalBars);

// Real-time: update last bar or append new one
series.update({ time, open, high, low, close });
```

---

## 4. Multiple Series on Single Chart

**All series share same time scale by default. Add series before populating data.**

```typescript
const chart = createChart(container);

// Primary candlestick
const candleSeries = chart.addCandlestickSeries();

// Volume (same pane, right axis)
const volumeSeries = chart.addHistogramSeries({
  priceFormat: { type: 'volume' },
  color: '#26a69a',
});

// Both use same timeScale
candleSeries.setData(ohlcData);
volumeSeries.setData(volumeData);

// Update in real-time
candleSeries.update(latestCandle);
volumeSeries.update({ time: latestCandle.time, value: latestVolume });
```

**Key constraint:** Without panes, all series overlay on same grid. Use `paneIndex` (v5+) to separate.

---

## 5. Multiple Panes (v5+ Only)

**v5.1.0 natively supports panes. RSI/MACD use case solved.**

### Add Series to Specific Pane
```typescript
// Pane 0: Price (default)
const candleSeries = chart.addCandlestickSeries();

// Pane 1: RSI
const rsiSeries = chart.addLineSeries({
  paneIndex: 1,
  color: '#ff0000',
  lineWidth: 2,
});

// Pane 2: MACD
const macdSeries = chart.addLineSeries({
  paneIndex: 2,
  color: '#0000ff',
});

// Access pane API to resize
const pane1 = chart.pane(1);
pane1.setHeight(100); // 100px
```

### Pane Configuration
```typescript
createChart(container, {
  layout: {
    panes: {
      separatorColor: '#cccccc',
      separatorHoverColor: '#999999',
      enableResize: true, // Users can drag separators
    },
  },
});
```

### Pane API Methods
- `chart.pane(index: number): IPaneApi`
- `pane.getHeight(): number`
- `pane.setHeight(height: number): void` (min 30px)
- `pane.getSeries(): ISeriesApi[]`
- `chart.removePane(index: number): void`

**Design note:** If pane height < 30px, request ignored. Plan pane layout with minimum 30px per pane + separators.

---

## 6. TypeScript Type Safety

**Fully typed. All interfaces exported from `lightweight-charts`:**

```typescript
import {
  createChart,
  CandlestickData,
  HistogramData,
  LineSeriesData,
  IChartApi,
  ISeriesApi,
  IPaneApi,
  SeriesOptions,
  ChartOptions,
  UTCTimestamp,
  BusinessDay,
} from 'lightweight-charts';

const chart: IChartApi = createChart(container);
const series: ISeriesApi<CandlestickData> = chart.addCandlestickSeries();
```

No type guard needed; library provides generics for data shape and series options.

---

## 7. Chart Resize Handling

**Manual resize listener required (library doesn't auto-resize to container).**

### Direct Pattern (No Wrapper)
```typescript
useEffect(() => {
  const container = containerRef.current;
  if (!container || !chart) return;

  const handleResize = () => {
    chart.applyOptions({
      width: container.clientWidth,
      height: container.clientHeight,
    });
  };

  window.addEventListener('resize', handleResize);
  return () => window.removeEventListener('resize', handleResize);
}, [chart]);
```

### Gotcha: React Strict Mode
In Strict Mode dev mode, useEffect runs twice (setup → cleanup → setup). If cleanup calls `chart.remove()` and setup recreates, ensure:
1. No stale refs post-unmount
2. Set `_api = null` in wrapper cleanup (if wrapping)
3. Guard chart operations with nullcheck

---

## 8. Dark/Light Theme Support

**No built-in theme toggle. Manual color config via `applyOptions()`.**

### Light Theme
```typescript
chart.applyOptions({
  layout: {
    background: { color: '#ffffff' },
    textColor: '#000000',
  },
  grid: {
    vertLines: { color: '#e0e0e0' },
    horzLines: { color: '#e0e0e0' },
  },
});
```

### Dark Theme
```typescript
chart.applyOptions({
  layout: {
    background: { color: '#1a1a1a' },
    textColor: '#ffffff' },
  grid: {
    vertLines: { color: '#333333' },
    horzLines: { color: '#333333' },
  },
});
```

### Series Colors Per-Theme
```typescript
const colors = theme === 'dark'
  ? { line: '#ffffff', area: '#00ff00' }
  : { line: '#000000', area: '#00cc00' };

series.applyOptions(colors);
```

**Pattern:** Theme state → listen for changes → call `chart.applyOptions()` + `series.applyOptions()` for each series.

---

## 9. React Strict Mode & Cleanup Gotchas

### Issue 1: Double-Mount in Development
React 18+ Strict Mode intentionally runs setup+cleanup twice in dev to catch missing cleanup.

**Symptom:** Chart created, then immediately destroyed and recreated.

**Fix:**
```typescript
useEffect(() => {
  const chart = createChart(containerRef.current!);
  // ... setup series

  return () => {
    chart.remove(); // Critical: must call remove()
  };
}, []);
```

### Issue 2: Cleanup Order with Resize Listener
If resize listener cleanup runs before chart cleanup, unmounting during resize can crash.

**Fix (guaranteed cleanup order):**
```typescript
useEffect(() => {
  const chart = createChart(containerRef.current!);

  const handleResize = () => {
    if (!chart) return; // Guard against stale closure
    chart.applyOptions({ width: w, height: h });
  };

  window.addEventListener('resize', handleResize);

  return () => {
    window.removeEventListener('resize', handleResize);
    chart.remove(); // Always remove last
  };
}, []);
```

### Issue 3: Wrapper Cleanup in Subcomponents
If wrapping chart in a custom component and using `useRef` internally, store null check:

```typescript
// Inside wrapper component
const chartRef = useRef<IChartApi | null>(null);

useEffect(() => {
  chartRef.current = createChart(...);
  return () => {
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null; // Prevent stale refs
    }
  };
}, []);
```

### Issue 4: Data Updates During Cleanup
If real-time data arrives during unmount, it may attempt `series.update()` on deleted chart.

**Fix:** Unsubscribe from data source **before** calling `chart.remove()`:
```typescript
useEffect(() => {
  const chart = createChart(container);
  const series = chart.addCandlestickSeries();

  // Subscribe to data stream
  const unsubscribe = dataStream.subscribe(bar => series.update(bar));

  return () => {
    unsubscribe(); // Stop updates FIRST
    chart.remove(); // Then destroy
  };
}, []);
```

---

## 10. Performance & Known Limitations

### v5.1.0 Enhancements
- **Conflation:** Auto-merge data points when zoomed out. Enable via `enableConflation: true` in chart options. Huge win for large datasets.
- **rightOffsetPixels:** Pixel-based right margin (replaces v4's percent-based).
- **pop() method:** Remove latest data point without full redraw.

### Known Issues
- **No multi-timeframe natively:** Must manage separate chart instances or series for different timeframes.
- **Pane minimum height 30px:** Design layouts with this constraint.
- **Custom indicators:** RSI, MACD, Bollinger Bands not included—must calculate client-side.
- **No candle color conditional logic:** Cannot auto-color candles based on condition without custom drawing (use HistogramSeries overlay as workaround).

---

## 11. Integration Checklist for PocketQuant

### Must-Have
- [x] CandlestickSeries for price OHLC
- [x] HistogramSeries for volume
- [x] LineSeries for RSI/MACD/indicators
- [x] Multiple panes via `paneIndex`
- [x] Real-time `series.update()` for live trading
- [x] TypeScript full coverage
- [x] Dark/light theme via `applyOptions()`
- [x] Resize listener for responsive layout

### Nice-to-Have
- [x] Conflation for large historical datasets
- [x] Crosshair & hover interactions (native)
- [x] Time scale formatting (native)
- [x] Price scale auto-scale (native)

### Out-of-Scope (Requires Custom Logic)
- [ ] Indicator calculations (RSI, MACD, Bollinger) — use `ta-lib` or TA.js for compute
- [ ] Alerts/annotations on chart — use overlays + custom event handlers
- [ ] Advanced heatmaps/clustering — beyond library scope

---

## 12. Recommended Integration Pattern (for PocketQuant)

### Component Structure
```typescript
// hooks/useChart.ts
export function useChart(containerId: string) {
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<Map<string, ISeriesApi>>(new Map());

  useEffect(() => {
    const container = document.getElementById(containerId);
    if (!container) return;

    chartRef.current = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight,
      layout: { background: { color: '#fff' }, textColor: '#000' },
    });

    const handleResize = () => {
      chartRef.current?.applyOptions({
        width: container.clientWidth,
        height: container.clientHeight,
      });
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chartRef.current?.remove();
      chartRef.current = null;
    };
  }, [containerId]);

  const addSeries = (type: string, key: string, options = {}) => {
    if (!chartRef.current) return null;
    const series = chartRef.current[`add${type}Series`](options);
    seriesRef.current.set(key, series);
    return series;
  };

  const updateSeries = (key: string, data: any) => {
    seriesRef.current.get(key)?.update(data);
  };

  return { chart: chartRef.current, addSeries, updateSeries };
}
```

### Usage in Trading Dashboard
```typescript
export function TradingChart() {
  const { chart, addSeries } = useChart('chart-container');

  useEffect(() => {
    if (!chart) return;

    // Pane 0: Price + Volume
    const candleKey = addSeries('Candlestick', 'candles', { paneIndex: 0 });
    const volKey = addSeries('Histogram', 'volume', {
      paneIndex: 0,
      priceFormat: { type: 'volume' },
    });

    // Pane 1: RSI
    const rsiKey = addSeries('Line', 'rsi', { paneIndex: 1, color: '#ff0000' });

    // Load historical
    const [candles, volumes, rsis] = await loadData();
    chart.addSeries(candleKey).setData(candles);
    // ... etc

    // Real-time updates
    const unsubscribe = ws.onTick(bar => {
      series.get(candleKey).update(bar);
      series.get(volKey).update({ time: bar.time, value: bar.volume });
      // Calculate and update RSI
      const rsi = calculateRSI(recentBars);
      series.get(rsiKey).update({ time: bar.time, value: rsi });
    });

    return () => unsubscribe();
  }, [chart]);

  return <div id="chart-container" style={{ width: '100%', height: '600px' }} />;
}
```

---

## 13. Adoption Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| v4 → v5 breaking changes | Medium | v5 adds features; v4 code mostly works. Test pane APIs if upgrading. |
| No custom indicators bundled | Medium | Pre-compute RSI/MACD server-side or use TA.js client-side. |
| Strict Mode cleanup | Low | Follow cleanup pattern above; add null guards. |
| Bundle size impact | Low | 35kB gzipped; negligible for trading app. |
| Real-time performance at scale | Low | Conflation helps; library tested at 10k+ candles. |

**Verdict:** Low adoption risk. v5 is production-grade. Main effort is indicator calculation, not charting library.

---

## 14. Sources & References

- [TradingView Lightweight Charts Official Docs](https://tradingview.github.io/lightweight-charts/)
- [Getting Started Tutorial](https://tradingview.github.io/lightweight-charts/docs)
- [React Integration Pattern](https://tradingview.github.io/lightweight-charts/tutorials/react/simple)
- [ISeriesApi Interface](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/ISeriesApi)
- [Panes API Documentation](https://tradingview.github.io/lightweight-charts/tutorials/how_to/panes)
- [Release Notes v5.1.0](https://github.com/tradingview/lightweight-charts/releases)
- [npm Package Page](https://www.npmjs.com/package/lightweight-charts)
- [Chart Colors Customization](https://tradingview.github.io/lightweight-charts/tutorials/customization/chart-colors)
- [Community React Wrapper: lightweight-charts-react-components](https://github.com/ukorvl/lightweight-charts-react-components)

---

## Unresolved Questions

1. **Indicator library choice:** Should PocketQuant compute RSI/MACD server-side (in Python backtest engine) or client-side (TA.js)? Client-side reduces latency but adds bundle; server-side increases API calls.
2. **Conflation tuning:** At what zoom level should conflation activate? Library default or custom threshold?
3. **Custom candle colors:** Need conditional coloring (e.g., bullish green, bearish red)? This requires custom drawing or series-per-condition workaround.

