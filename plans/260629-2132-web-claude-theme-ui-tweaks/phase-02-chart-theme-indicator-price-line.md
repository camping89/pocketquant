---
phase: 2
title: "Chart theme & indicator price-line"
status: done
priority: P1
dependencies: [1]
effort: "M"
---

# Phase 2: Chart theme & indicator price-line

<!-- Updated: Validation Session 1 - candle colors lấy từ token --up-color/--down-color (hex chốt ở Phase 1), không literal -->

## Overview

Hai việc trên lightweight-charts:
1. **Theme-aware chart** — chart background/grid/border/candle đọc màu từ CSS token (Phase 1) qua `getComputedStyle`, và re-apply khi theme đổi (tái dùng đúng cơ chế `mode` effect đã có cho timezone).
2. **Task 2** — bỏ đường price line ngang nét đứt của indicator series (`priceLineVisible:false`).

## Requirements

- Functional: đổi theme → chart bg/grid/candle đổi theo không cần reload; EMA/SMA/BB không còn đường ngang nét đứt ở giá trị cuối.
- Non-functional: chart đọc lại chính CSS token (DRY, không hard-code màu lần 2); không churn series khi đổi theme (chỉ `applyOptions`, không re-create).

## Architecture

### Đọc token cho chart

lightweight-charts nhận giá trị màu JS, không nhận `var(--…)`. Tạo helper đọc token:

```ts
// web/src/lib/theme-colors.ts (mới)
export interface ChartColors {
  background: string; text: string; grid: string; border: string;
  up: string; down: string;
}
export function readChartColors(): ChartColors {
  const s = getComputedStyle(document.documentElement)
  const v = (n: string) => s.getPropertyValue(n).trim()
  return {
    background: v('--bg-primary'),
    text: v('--text-primary'),
    grid: v('--border-color'),
    border: v('--border-color'),
    up: v('--up-color'),
    down: v('--down-color'),
  }
}
```

### `use-chart.ts`

- Bỏ literal trong `DEFAULT_OPTIONS` (`#1a1a2e`, `#d1d4dc`, `#2B2B43`); thay bằng `readChartColors()` lúc `createChart`.
- Thêm param `themeMode: 'dark'|'light'` (giống `mode` cho tz). Effect mới: khi `themeMode` đổi → `chart.applyOptions({ layout, grid, rightPriceScale, timeScale })` với màu mới. Chart instance giữ nguyên (zoom/series intact) — y như effect timezone hiện có.
- Caller (`trading-chart.tsx`, `strategy-chart.tsx`) lấy `themeMode` từ `useTheme()` và truyền vào `useChart`.

### Candle colors

`trading-chart.tsx` (dòng ~94) và `strategy-chart.tsx` (dòng ~68) hard-code `upColor/downColor/wickUp/wickDown = '#26a69a'/'#ef5350'`. Đổi sang `readChartColors().up/.down`. Vì candle series tạo trong effect `[data]` (re-create khi data đổi), nó tự lấy màu mới sau toggle nếu data reload — NHƯNG để đổi tức thì không cần data reload, thêm vào effect `themeMode`: `candleRef.current?.applyOptions({ upColor, downColor, wickUpColor, wickDownColor })` và `volumeRef` nếu cần. Đặt logic này trong `use-chart` không được (nó không giữ series refs) → đặt một effect nhỏ ở mỗi chart component, hoặc expose 1 callback. KISS: thêm `useEffect([themeMode])` trong `trading-chart.tsx` + `strategy-chart.tsx` apply lại candle colors.

### Task 2 — price line

`indicator-series.ts` `addIndicatorSeries`: mọi `chart.addSeries(LineSeries, {...})` thêm `priceLineVisible: false, lastValueVisible: false`. Áp cho sma20, ema9, ema21, bbUpper, bbMiddle, bbLower, rsi, macdLine, macdSignal. (Histogram MACD không có price line line-style nhưng set `priceLineVisible:false` vẫn an toàn.)

> Chỉ bỏ price line (đường ngang giá trị cuối). KHÔNG đổi `lineStyle` của bbMiddle (giữ dashed như cũ — user chỉ yêu cầu bỏ price line, theo quyết định brainstorm "Price line ngang nét đứt").

## Related Code Files

- Create: `web/src/lib/theme-colors.ts`
- Modify: `web/src/components/chart/use-chart.ts` (token colors + themeMode effect)
- Modify: `web/src/components/chart/trading-chart.tsx` (candle colors token + themeMode apply)
- Modify: `web/src/components/chart/strategy-chart.tsx` (candle colors token + themeMode apply)
- Modify: `web/src/components/chart/indicator-series.ts` (priceLineVisible:false)
- Reference: `web/src/lib/use-theme.ts` (Phase 1)

## Implementation Steps

1. Tạo `theme-colors.ts` với `readChartColors()`.
2. `use-chart.ts`: thay `DEFAULT_OPTIONS` literal bằng `readChartColors()`; thêm param `themeMode`; thêm effect re-apply layout/grid/scale colors khi `themeMode` đổi.
3. `trading-chart.tsx`: `const { mode: themeMode } = useTheme()`; truyền vào `useChart`; candle/wick colors từ `readChartColors()`; thêm effect `[themeMode]` apply lại candle+volume colors.
4. `strategy-chart.tsx`: tương tự (candle colors + themeMode). (Chart này đã sẽ nhận indicator ở Phase 3 — chỉ chạm candle/theme ở đây.)
5. `indicator-series.ts`: thêm `priceLineVisible:false, lastValueVisible:false` vào mọi LineSeries option object.
6. `npm run lint` + `npm run build`; kiểm: toggle theme khi đang xem chart → bg/grid/candle đổi tức thì, zoom giữ nguyên; bật EMA/SMA/BB → không còn đường ngang nét đứt; line vẫn vẽ.

## Success Criteria

- [ ] Toggle theme → chart background/grid/border/candle đổi tức thì, không reload, zoom/series giữ nguyên.
- [ ] Chart không còn literal màu — đọc từ CSS token.
- [ ] EMA/SMA/BB không còn đường ngang nét đứt (price line); đường indicator vẫn vẽ bình thường.
- [ ] bbMiddle vẫn dashed như cũ; markers (engulf/backtest) không bị ảnh hưởng.
- [ ] `npm run lint` + `npm run build` pass.

## Risk Assessment

- **`getComputedStyle` trả rỗng** nếu `data-theme` chưa set. Mitigation: Phase 1 set attribute trước React mount; fallback giá trị mặc định trong `readChartColors` nếu `v()` rỗng.
- **Candle không đổi màu khi toggle** vì series tạo trong effect `[data]`. Mitigation: effect `[themeMode]` apply lại candle colors (step 3/4).
- **Đụng `strategy-chart.tsx` cùng Phase 3.** Mitigation: Phase 3 `blockedBy` [2]; làm tuần tự.
