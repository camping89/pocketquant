# Code Review: pocketquant-web

**Date:** 2026-03-30 | **Reviewer:** code-reviewer | **Package:** packages/pocketquant-web

## Scope

- **Files:** 23 (4 lib/indicators, 4 hooks, 3 chart components, 3 controls, 2 api, 4 config/entry, 1 types, 1 css, 1 layout)
- **LOC:** ~680 (excluding CSS)
- **Focus:** Correctness, race conditions, LC v5 API, React lifecycle, security, performance

## Overall Assessment

Clean, well-structured SPA. LC v5 API usage is correct (SeriesDefinition pattern, pane indexes). Types are strict with no `any`. Two critical issues found: a race condition between symbol switching and realtime polling, and a StrictMode double-mount that destroys the chart. Several high-priority items around error handling and memoization.

---

## Critical Issues

### C1. Race condition: realtime poll updates stale series after symbol switch

**File:** `src/hooks/use-realtime-bar.ts` + `src/components/chart/trading-chart.tsx`

`useRealtimeBar` receives `candleSeries` and `volumeSeries` as hook args (line 90 of trading-chart.tsx). These are **ref values snapshotted at render time**, not the ref objects themselves. When the user switches symbols:

1. React Query starts fetching new OHLCV data
2. The existing `useEffect` in `useRealtimeBar` is still polling with the **old** series refs
3. The cleanup runs only when the new `candleRef.current` / `volumeRef.current` propagate through a re-render
4. Between fetch-start and data-arrival, the poll can call `.update()` on a series that has been removed from the chart, throwing a runtime error

**Fix:** Pass the ref objects (`candleRef`, `volumeRef`) to `useRealtimeBar` instead of `.current` values, and read `.current` inside the poll callback. Additionally, gate the poll on `data` being loaded (add `data` as a dependency or a separate `enabled` flag):

```ts
// use-realtime-bar.ts
export function useRealtimeBar(
  exchange: string, symbol: string, interval: Interval,
  candleRef: React.RefObject<ISeriesApi<'Candlestick'> | null>,
  volumeRef: React.RefObject<ISeriesApi<'Histogram'> | null>,
) {
  useEffect(() => {
    const poll = async () => {
      const cs = candleRef.current
      const vs = volumeRef.current
      if (!cs || !vs) return
      // ... rest of poll logic
    }
    // ...
  }, [exchange, symbol, interval]) // refs are stable, not deps
}
```

### C2. StrictMode double-mount destroys chart, second mount creates on removed DOM

**File:** `src/components/chart/use-chart.ts`

`useChart` has an empty dependency array `[]` and calls `chart.remove()` in cleanup. In React 18+/19 StrictMode, effects run -> cleanup -> run again. The second mount calls `createChart(el, ...)` on the same DOM element, which should work. However, there is a subtler issue: the `chartRef` is shared across both mounts. The first cleanup sets `chartRef.current = null`, but the second mount writes a new chart. The problem arises when other effects (candle/volume setup in `trading-chart.tsx`) read `chartRef.current` during the first mount's lifecycle -- they get a chart instance that will be destroyed moments later, creating series on a doomed chart.

This is partially mitigated by `data` being the dependency of the series effect (data won't be ready during the initial double-mount cycle). But if data is cached by React Query (e.g., user switches back to a previously-viewed symbol), the series effect fires immediately on the first mount, attaching to a chart that gets destroyed.

**Fix:** Add a mounted guard or use `useSyncExternalStore` for the chart lifecycle. Simpler approach: make the chart effect depend on a stable key that changes on symbol switch, so chart creation is tied to data lifecycle:

```ts
// Alternatively, key the chart div to force fresh DOM:
<div key={`${exchange}-${symbol}-${interval}`} ref={containerRef} ... />
```

This ensures a fresh chart per symbol/interval combo and sidesteps the StrictMode issue entirely.

---

## High Priority

### H1. `useIndicators` memoization depends on entire `config` object -- rerenders on every toggle

**File:** `src/hooks/use-indicators.ts` (line 83)

`useMemo` depends on `[candles, config]`. `config` is a new object reference on every state update in `App.tsx` (line 29: `useState<IndicatorConfig>`). When any indicator is toggled, `config` changes (correct), but the memo also recomputes when **unrelated** parent state changes cause `ChartApp` to re-render, because `config` is created fresh each time.

Currently `ChartApp` has no other state that would trigger spurious re-renders, so this is low-impact today. But it will become a problem when additional state is added. Consider wrapping with `useCallback`/`useMemo` for the `onChange` handler or using `React.memo` on `TradingChart`.

**Impact:** Indicator recomputation is O(n) over candle data. For 1000 bars, this is cheap. For larger datasets, could cause jank.

### H2. No error UI -- failed API calls silently show empty chart

**Files:** `src/hooks/use-ohlcv.ts`, `src/components/chart/trading-chart.tsx`

`useOHLCV` returns `{ data, error, isLoading }` but `TradingChart` only destructures `{ data }`. If the API is down or returns 500, the user sees a blank chart with no feedback. The `useRealtimeBar` hook also silently swallows errors (line 39: empty `catch {}`).

**Fix:** Destructure `error` and `isLoading` from `useOHLCV`, render appropriate states:

```tsx
const { data, error, isLoading } = useOHLCV(exchange, symbol, interval)
if (isLoading) return <div className="chart-loading">Loading...</div>
if (error) return <div className="chart-error">Failed to load data</div>
```

### H3. `apiFetch` returns `res.json()` without validation -- trusts server shape blindly

**File:** `src/api/api-client.ts` (line 10)

`return res.json()` is cast to `T` via the generic. If the API returns an unexpected shape (e.g., error envelope `{ detail: "..." }`), callers will destructure undefined properties and crash at runtime.

**Fix:** Consider a lightweight runtime check or use a schema validator like `zod` for critical API boundaries. At minimum, check that `res.json()` has expected top-level keys before returning.

### H4. `useChart` ignores `options` changes after mount

**File:** `src/components/chart/use-chart.ts` (line 49)

The `useEffect` has `// eslint-disable-line react-hooks/exhaustive-deps` suppressing the warning that `options` is not in the dep array. If a parent ever passes different `options` (e.g., theme switching), the chart won't update. The suppression comment should at minimum document **why** this is intentional.

Currently no caller passes `options`, so not a live bug. But the function signature advertises it as a parameter.

---

## Medium Priority

### M1. `ema()` crashes if `closes.length < period`

**File:** `src/lib/indicators/moving-average.ts` (line 10-19)

If `closes` has fewer elements than `period`, the initial SMA loop at line 14 reads beyond array bounds (returns `NaN`), and `result[period - 1]` writes to an out-of-bounds index. The `sma` function handles this correctly (returns null for short arrays), but `ema` does not guard.

This propagates to MACD (which calls `ema(closes, 26)`) and would crash/produce NaN for datasets under 26 bars.

**Fix:**
```ts
export function ema(closes: number[], period: number): (number | null)[] {
  const result: (number | null)[] = new Array(closes.length).fill(null)
  if (closes.length < period) return result
  // ... rest
}
```

### M2. `removeIndicatorSeries` can throw if chart was already removed

**File:** `src/components/chart/indicator-series.ts` (line 94-101)

The cleanup in `trading-chart.tsx` line 104-109 checks `chartRef.current` but if the chart was `.remove()`'d (from `use-chart.ts` cleanup running first), calling `chart.removeSeries(s)` on a destroyed chart throws. Effect cleanup order is not guaranteed to match creation order.

**Fix:** Wrap in try-catch:
```ts
export function removeIndicatorSeries(chart: IChartApi, refs: IndicatorSeriesRefs): void {
  for (const s of refs.all) {
    try { chart.removeSeries(s) } catch { /* chart already disposed */ }
  }
}
```

### M3. `toUTCTimestamp` does not validate input

**File:** `src/api/market-data-api.ts` (line 14-16)

`new Date(iso).getTime()` returns `NaN` for invalid strings. `NaN / 1000` stays `NaN`, which gets cast to `UTCTimestamp`. LC will either crash or render garbage.

**Fix:** Add a guard: `const ts = new Date(iso).getTime(); if (isNaN(ts)) throw new Error('Invalid datetime: ' + iso)`

### M4. Symbol selector XSS surface is safe (React escaping) but filter is uncontrolled for large lists

**File:** `src/components/controls/symbol-selector.tsx`

The filter runs on every keystroke against the full symbol list with two `toLowerCase().includes()` calls per item. For a few hundred symbols this is fine. If the symbol list grows to thousands, this will jank. Consider debouncing the filter or virtualizing the list.

No XSS risk -- React's JSX escaping handles the `s.name` and `s.symbol` values correctly.

### M5. Polling interval is hardcoded to 2s regardless of bar interval

**File:** `src/hooks/use-realtime-bar.ts` (line 6)

Polling every 2s for a 1-week bar is wasteful. For 1-minute bars, 2s is reasonable. Consider scaling `POLL_MS` based on `interval`:

```ts
const POLL_MAP: Record<Interval, number> = { '1m': 2000, '5m': 5000, '1h': 30000, '1d': 60000, ... }
```

---

## Low Priority

### L1. Duplicate color constants

Volume colors defined in both `market-data-api.ts` (lines 11-12) and `use-realtime-bar.ts` (lines 33-34) as inline strings. Extract to a shared `CHART_COLORS` constant.

### L2. `queryClient` created at module scope

**File:** `src/App.tsx` (line 7)

Module-scope `QueryClient` means it survives HMR in dev, potentially serving stale cache. Not a production issue but can confuse during development. Standard pattern is to create inside the component or use `useState(() => new QueryClient(...))`.

### L3. MACD pane index calculation is fragile

**File:** `src/components/chart/indicator-series.ts` (line 73)

`const pane = config.rsi ? 2 : 1` assumes RSI is always pane 1. If RSI data is empty (insufficient bars), RSI series won't be created, but MACD still goes to pane 2, leaving an empty pane 1. Consider tracking the actual next-pane index dynamically.

---

## Positive Observations

- LC v5 `addSeries(SeriesDefinition, options, paneIndex)` pattern used correctly throughout
- Clean separation: hooks handle data, chart components handle rendering, lib handles computation
- All indicator math is pure functions with null-propagation for insufficient data
- `ResizeObserver` cleanup is properly handled
- TypeScript strict mode enabled with no `any` types
- `enabled: !!exchange && !!symbol` guard on OHLCV query prevents empty fetches
- Polling cleanup with `active` flag + `clearInterval` prevents updates after unmount

---

## Recommended Actions (Priority Order)

1. **[C1]** Pass refs (not `.current`) to `useRealtimeBar` to prevent stale series updates on symbol switch
2. **[C2]** Add `key` prop to chart container div to force clean remount per symbol/interval
3. **[H2]** Add loading/error states to `TradingChart`
4. **[M1]** Guard `ema()` against `closes.length < period`
5. **[H3]** Add minimal runtime validation in `apiFetch` or at API boundary
6. **[M2]** Try-catch in `removeIndicatorSeries` for disposed chart
7. **[M3]** Validate `toUTCTimestamp` input
8. **[H4]** Either remove `options` param from `useChart` or make it reactive
9. **[M5]** Scale polling interval based on bar interval
10. **[L3]** Dynamic pane index for MACD

---

## Unresolved Questions

1. Are the backend API routes (`/api/v1/market-data/ohlcv/...`, `/api/v1/market-data/symbols`, `/api/v1/market-data/current-bar/...`) already implemented and matching these exact paths/response shapes?
2. Is there a plan for WebSocket-based realtime updates to replace HTTP polling?
3. Should indicator parameters (SMA period, EMA period, etc.) be user-configurable, or are the current hardcoded values (20, 50, 14) final?
