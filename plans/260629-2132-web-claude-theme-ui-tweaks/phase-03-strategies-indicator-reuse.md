---
phase: 3
title: "Strategies indicator reuse"
status: done
priority: P2
dependencies: [2]
effort: "M"
---

# Phase 3: Strategies indicator reuse

<!-- Updated: Validation Session 1 - chốt render đầy đủ RSI/MACD panes (không cắt scope dù chart 400px) -->

## Overview

Thêm bộ indicator toggles + render đầy đủ vào strategies page, **tái dùng** đúng module charts page dùng (`IndicatorToggles`, `useIndicators`, `addIndicatorSeries`/`removeIndicatorSeries`, `engulfingMarkers`) — zero copy logic. Persist lựa chọn vào localStorage (key riêng `strategies.indicators`).

## Requirements

- Functional: strategies page có cùng 6 toggle (SMA/EMA/RSI/MACD/BB/Engulf) như charts; bật/tắt render/gỡ series tương ứng; gồm panes phụ RSI/MACD; persist qua reload.
- Non-functional: KHÔNG copy logic indicator — import lại module hiện có. Giữ ranh giới: `StrategyChart` chỉ thêm indicator series, KHÔNG kéo `PositionBoxPrimitive`.

## Architecture

### `StrategyChart` nhận `indicators`

`strategy-chart.tsx` hiện cố ý không có indicator (comment đầu file). Thêm:
- Prop `indicators: IndicatorConfig`.
- `const indicatorData = useIndicators(data?.candles, indicators)` (tái dùng hook).
- Effect quản lý indicator series: mirror `trading-chart.tsx` dòng 172-189 — `addIndicatorSeries(chart, indicatorData, indicators)` + cleanup `removeIndicatorSeries`. Lưu `indicatorRefs = useRef<IndicatorSeriesRefs|null>`.
- Engulf markers: hiện `StrategyChart` đã có markers từ trades (effect dòng 105-123). Phải **merge** engulf markers với trade markers vào 1 set (createSeriesMarkers chỉ 1 instance/series — gọi lần 2 sẽ replace). Theo pattern `trading-chart.tsx` `mergedMarkers` (dòng 240-253): gộp `tradesToMarkers(trades)` + `engulfingMarkers(data.candles)` (khi `indicators.engulfing`), sort theo time, `setMarkers` 1 lần.

> ⚠️ Đây là thay đổi logic markers tinh tế. Trade markers hiện set qua `markersRef` riêng. Refactor để 1 `markersRef` nhận mảng merge. Test kỹ: chọn sub có trades + bật Engulf → cả 2 loại marker hiện; tắt Engulf → chỉ trade markers còn.

### Toggles + persist

- Component tái dùng `IndicatorToggles` (`controls/indicator-toggles.tsx`) — không sửa file đó.
- State + persist ở `strategies-page-layout.tsx` (hoặc tách hook nhỏ `use-persisted-indicators.ts` dùng chung nếu muốn DRY với charts page sau — nhưng charts page hiện KHÔNG persist indicators, nên giữ KISS: persist cục bộ trong strategies layout, key `strategies.indicators`).
- Render thanh toggles ngay trên `StrategyChart` (cả desktop pane lẫn mobile config tab). Strategies main pane: chart cao 400px (desktop) / 300px (mobile) — RSI/MACD panes sẽ chia nhỏ chiều cao. Chấp nhận (quyết định brainstorm: render đầy đủ). Nếu chật, lightweight-charts tự co panes.

### Persist helper

```ts
// đọc: localStorage 'strategies.indicators' → IndicatorConfig (default tất cả false, hoặc ema:true theo charts default)
// ghi: onChange → setState + localStorage.setItem
```
Default: theo charts page (`ema:true, engulfing:true`, còn lại false) cho nhất quán.

## Related Code Files

- Modify: `web/src/components/strategies/strategy-chart.tsx` (indicators prop + series + merged markers + theme từ Phase 2)
- Modify: `web/src/components/strategies/strategies-page-layout.tsx` (toggles UI + persist state, truyền `indicators` xuống chart — desktop + mobile)
- Reference (reuse, KHÔNG sửa): `web/src/components/controls/indicator-toggles.tsx`, `web/src/hooks/use-indicators.ts`, `web/src/components/chart/indicator-series.ts`, `web/src/lib/indicators/engulfing.ts`, `web/src/lib/trades-to-markers.ts`
- Optional create: `web/src/hooks/use-persisted-indicators.ts` (chỉ nếu tách hook gọn hơn)

## Implementation Steps

1. `strategy-chart.tsx`: thêm prop `indicators`; `useIndicators(data?.candles, indicators)`; effect add/remove indicator series (mirror trading-chart).
2. Refactor markers trong `strategy-chart.tsx`: gộp trade markers + engulf markers (khi bật) thành `mergedMarkers`, set 1 lần qua `markersRef`. Đảm bảo cleanup/detach đúng (chỉ detach on unmount, setMarkers([]) khi rỗng — theo trading-chart pattern).
3. `strategies-page-layout.tsx`: thêm state `indicators` + đọc/ghi localStorage `strategies.indicators` (default ema+engulfing). Render `<IndicatorToggles>` trên cả 2 chỗ chart (desktop pane + mobile config). Truyền `indicators` vào cả 2 `<StrategyChart>`.
4. (Optional) tách `use-persisted-indicators.ts` nếu thấy lặp đọc/ghi.
5. `npm run lint` + `npm run build`; kiểm: chọn sub → toggles hiện; bật từng indicator (gồm RSI/MACD pane) → render; bật Engulf + có trades → cả 2 marker; reload → state giữ.

## Success Criteria

- [ ] Strategies page có 6 toggle giống charts; bật/tắt render đúng series (gồm panes RSI/MACD).
- [ ] Engulf markers + trade markers cùng hiện khi cùng bật; tắt Engulf chỉ còn trade markers.
- [ ] Indicator logic dùng chung module charts (zero duplicate) — verify bằng grep không có hàm compute mới.
- [ ] Persist `strategies.indicators` qua reload; default ema+engulfing.
- [ ] `PositionBoxPrimitive` KHÔNG bị kéo vào strategy chart (ranh giới giữ nguyên).
- [ ] `npm run lint` + `npm run build` pass.

## Risk Assessment

- **Marker merge regression** — gộp 2 nguồn markers dễ sai (mất trade markers, hoặc duplicate). Mitigation: theo sát pattern `trading-chart.tsx` `mergedMarkers`; test 4 tổ hợp (trades±, engulf±).
- **Chart 400px chật với panes phụ.** Quyết định (validation 1): **render đầy đủ RSI/MACD** giống charts page — lightweight-charts tự co panes. KHÔNG cắt scope, KHÔNG tự bỏ RSI/MACD. Chấp nhận panes hẹp khi cùng bật nhiều indicator.
- **Đụng `strategy-chart.tsx` cùng Phase 2.** Mitigation: `blockedBy` [2]; tuần tự.
