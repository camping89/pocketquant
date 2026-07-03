# Phase 02 — Chart behavior: box theo lựa chọn + auto-scroll

## Context links
- Parent: [plan.md](plan.md)
- Depends on: [phase-01](phase-01-data-and-anchor-ohlcv.md) (chart anchored render đúng nến + positions trong viewport)
- Docs: `docs/code-standards.md`

## Overview
- Date: 2026-07-01
- Description: Trong `TradingChart`, đổi `PositionBoxPrimitive` từ vẽ box TOÀN BỘ positions → chỉ vẽ box cho {lệnh highlight, lệnh hover}; mặc định chỉ markers. Thêm auto-scroll: khi `highlightedPositionIndex` đổi → `setVisibleRange` quanh lệnh.
- Priority: P2
- Implementation status: completed
- Review status: completed (controller self-review — reviewer subagent stalled)

## Key Insights
- `TradingChart` hiện build `posData` từ TOÀN BỘ `positions` (line ~333) rồi tạo 1 `PositionBoxPrimitive`. Markers thì build riêng (line ~246) — giữ nguyên (vẽ hết, đã dedup).
- `onChartReady(chart)` đã tồn tại → parent giữ `IChartApi` ref; nhưng auto-scroll nên làm **bên trong** `TradingChart` (theo `highlightedPositionIndex`) để không rò chart API ra ngoài + tránh lệch lifecycle.
- `setVisibleRange` cần `Time` (unix giây). `positions[i].entry_time`/`exit_time` là ISO → dùng `toUTCTimestamp` (đã import).
- Clamp: range phải nằm trong `[data.candles[0].time, data.candles.at(-1).time]` để không scroll ra vùng trống → lightweight-charts sẽ ignore range ngoài data nhưng clamp cho UX mượt.
- **Pad chốt: `PAD_BARS = 50`** nến mỗi bên (tổng ngữ cảnh ~100 nến + độ rộng lệnh).

## Requirements
1. Box chỉ vẽ cho positions có `index ∈ {highlightedPositionIndex, hoveredPositionIndex}` (bỏ qua null). Mặc định (cả hai null) → `posData` rỗng → primitive không vẽ box (markers vẫn còn).
2. Markers giữ nguyên: build từ toàn bộ `positions`.
3. Auto-scroll: effect theo `[highlightedPositionIndex, data]` → nếu index hợp lệ + position có entry_time → tính `[entryT - pad, exitT + pad]` với `pad = barDur * 50` (50 nến mỗi bên), clamp, `chart.timeScale().setVisibleRange(...)`.
4. Hover (chỉ đổi `hoveredPositionIndex`) → KHÔNG auto-scroll (tránh giật khi rê chuột qua bảng).

## Architecture
```
positions (all) ──► markers (vẽ hết, dedup)        [giữ nguyên]
positions filtered by {highlight, hover} ──► PositionBoxPrimitive posData
highlightedPositionIndex change ──► effect ──► setVisibleRange(entry..exit ± pad, clamped)
```
Pad nến: lấy 2 candle time liền nhau từ `data.candles` để suy ra bar duration; pad = `barDur * 50`. Nếu chỉ 1 nến → fallback pad cố định.

## Related code files
- `web/src/components/chart/trading-chart.tsx` (sửa — filter posData, effect auto-scroll)
- `web/src/components/chart/position-box-primitive.ts` (đọc — không đổi; nó vẽ mọi pos được truyền)

## Implementation Steps
1. Trong effect tạo `PositionBoxPrimitive` (hiện ~line 320-367): trước khi `.map`, lọc `positions` theo index ∈ {highlight, hover}. Giữ `index: idx` đúng theo vị trí GỐC trong mảng positions (để highlight match). → map qua `positions.entries()`, filter theo idx, rồi build `PositionData`.
   - Deps effect đã gồm `[positions, data, highlightedPositionIndex, hoveredPositionIndex]` (đã có) → primitive rebuild khi selection đổi. OK.
2. Thêm effect auto-scroll:
   - Deps `[highlightedPositionIndex, data]`.
   - Guard: `chartRef.current`, `data`, index hợp lệ, `positions[index]` tồn tại.
   - `entryT = toUTCTimestamp(p.entry_time)`, `exitT = p.exit_time ? toUTCTimestamp(p.exit_time) : lastCandleTime`.
   - barDur từ 2 nến đầu; pad = `barDur * 50` (50 nến mỗi bên).
   - `from = clamp(entryT - pad, firstT, lastT)`, `to = clamp(exitT + pad, firstT, lastT)`.
   - `chart.timeScale().setVisibleRange({ from, to })` (try/catch — range invalid khi data rỗng).
3. Comment 1 dòng WHY tại auto-scroll (vì sao chỉ theo highlight, không theo hover).

## Todo list
- [ ] Filter posData theo {highlight, hover}, giữ index gốc
- [ ] Markers vẫn build từ toàn bộ positions (xác nhận không đổi)
- [ ] Effect auto-scroll theo highlightedPositionIndex (clamp range)
- [ ] Hover không trigger scroll

## Success Criteria
- Mặc định: chart chỉ có markers, không box.
- Set highlight 1 index → box hiện cho đúng lệnh đó + chart cuộn tới nó.
- Set hover → box (nét đứt) hiện, chart KHÔNG cuộn.
- Highlight + hover khác index → 2 box hiện.
- Không lỗi console khi index = null hoặc data chưa load.

## Risk Assessment
- **TB**: tính bar duration sai khi data có gap → pad lệch. Mitigation: pad chỉ để ngữ cảnh, lightweight-charts clamp; chấp nhận sai số nhỏ.
- **Thấp**: `setVisibleRange` trước khi candle series sẵn sàng → try/catch + guard `data`.

## Security Considerations
Không.

## Next steps
→ Phase 03: mount chart + nối highlight/hover từ bảng (state ở `BacktestResultView`).
