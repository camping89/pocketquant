---
title: "Backtest UI — chart nến + trực quan hóa entry/exit từng order"
description: "Wiring TradingChart vào backtest detail tab Trades: markers, box theo lựa chọn, auto-scroll, anchor OHLCV theo backtest window"
status: completed
priority: P2
effort: 6h
branch: develop
tags: [web, backtest, chart, frontend, wiring]
created: 2026-07-01
---

# Backtest UI — chart nến + trực quan hóa entry/exit từng order

## Mục tiêu
Trong backtest detail (tab Trades), hiển thị chart nến với mũi tên BUY/SELL mọi lệnh + box chi tiết (Entry/Exit/SL/TP/PnL/Qty) cho lệnh đang click/hover, chart auto-scroll tới lệnh khi click dòng bảng. Bản chất là **wiring** component đã có (`TradingChart`, `PositionBoxPrimitive`, `PositionsTab` callbacks) — không xây mới.

## Brainstorm nguồn
`plans/reports/brainstorm-260701-0044-backtest-chart-orders-visualization-report.md`

## Phát hiện bổ sung (ngoài brainstorm — rủi ro ẩn, đã verify code)
- **Query key collision**: `ohlcvQueryKey = ['ohlcv', symbol, interval]` không gồm `end_date`. Backtest chart (anchored quá khứ) + live chart cùng symbol/interval sẽ share cache → ghi đè nhau. → cần query key riêng khi anchored.
- **Realtime push nến lạc**: `TradingChart` gọi `useRealtimeBar` vô điều kiện; SSE push nến hiện tại vào series. Chart anchor quá khứ sẽ bị chèn nến tương lai + mở EventSource thừa. → cần gate `useRealtimeBar` khi anchored.

## Phases

| # | Phase | Status | Effort | Depends |
|---|---|---|---|---|
| 01 | [Data + anchor OHLCV theo backtest window](phase-01-data-and-anchor-ohlcv.md) | completed | 2.5h | — |
| 02 | [Chart behavior: box theo lựa chọn + auto-scroll](phase-02-chart-box-selection-and-autoscroll.md) | completed | 1.5h | 01 |
| 03 | [Layout tab Trades + wiring highlight/hover 2 chiều](phase-03-trades-tab-layout-and-wiring.md) | completed | 1.5h | 01, 02 |
| 04 | [CSS: chart wrapper height + responsive mobile](phase-04-css-chart-height-responsive.md) | completed | 0.5h | 03 |

## Dependency
`01 (data + anchor, query-key fix, realtime gate)` → `02 (chart behavior)` → `03 (layout + wiring)` → `04 (CSS polish)`.
Phase 01 rủi ro cao nhất (chạm shared hook `useOhlcvHistory` + `TradingChart` mà live chart dùng) — làm trước, verify không regression live trước khi sang 02.

## Acceptance criteria (toàn plan)
1. Run finished → tab Trades → chart nến đúng khoảng backtest + mũi tên BUY/SELL mọi lệnh.
2. Click dòng bảng → chart cuộn tới lệnh, box Entry/Exit/SL/TP/PnL/Qty + viền vàng.
3. Hover dòng → box viền nét đứt.
4. Run cũ (vài năm trước) vẫn thấy đúng nến + box (không trống).
5. Chart trang chính (live, `routes/index.tsx`) + `strategy-chart.tsx` không đổi hành vi.

## Scope OUT
- Backend (không sửa Python).
- Live chart `routes/index.tsx` + `strategy-chart.tsx` — giữ nguyên hành vi.
- Replay/animation theo thời gian.
- Equity/drawdown/histogram giữ nguyên.

## Validation strategy
Manual verify trên UI (ít test infra cho React component). Mỗi phase nêu bước verify cụ thể. Bắt buộc cross-check live chart sau Phase 01.
