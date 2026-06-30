---
phase: 3
title: "Compact list + form drawer"
status: completed
priority: P2
dependencies: [1, 2]
---

# Phase 3: Compact list + form drawer

## Overview

Thay history table 9 cột bằng compact card/row hợp cột list hẹp; nút "+ New run" mở form trong drawer; áp `formatQty`/`formatPrice` (P1) vào orders/trades/drawer/history để hết tràn cột.

## Requirements

- Functional:
  - `RunHistoryRail` nhận `selectedRun`/`onSelect`, render compact row thay table. Row active có viền trái accent. Checkbox compare (≤3) + nút "Compare N" giữ.
  - Mỗi row: dòng 1 `ngày · strategy · symbol·interval`; dòng 2 `Return%`(màu up/down) + `Sharpe` + `#trades` + verdict dot/ellipsis.
  - **Dropdown sort** (validation Q2) trên đỉnh list: Newest (started_at desc, default) / Return / Sharpe / Win% / Max DD / #trades. Tái dùng logic `metricVal` + sort của `BacktestHistoryTable` cũ (di chuyển sang rail trước khi xóa table) — KHÔNG mất power sort.
  - Nút "+ New run" trên đỉnh list → mở `BacktestForm` trong drawer; submit chạy run + điều hướng `?run=<newId>` (giữ `useRunBacktest` nhưng đổi `onSuccess` navigate sang search param).
  - Format số: `orders-table` (qty), `positions-table` (qty), `order-detail-drawer` (qty + SL/TP + fills), `backtest-history-table` nếu còn dùng (qty/price).
- Non-functional: compact list không tràn ngang ở 400px; filter strategy/symbol/interval giữ logic cũ.

## Architecture

- **Compact row** component mới `components/backtest/run-list-item.tsx` — 1 run, props: `row: BacktestRunRow`, `active`, `selected`, `onSelect`, `onToggleSelect`, `disableSelect`. Style class `.backtest-run-item` (clone cảm giác `strategy-card`).
- **`RunHistoryRail`** sửa: bỏ `useNavigate` row→detail (giờ `onSelect` prop từ workbench), render `RunListItem` thay `BacktestHistoryTable`. Filter pickers (strategy/symbol/interval) + Compare button giữ. Default "all strategies" theo code hiện tại (commit `76768d0`), KHÔNG theo plan Q5 cũ.
  - Thêm dropdown sort (Q2): di chuyển `SortKey` + `metricVal` + logic sort từ `backtest-history-table.tsx` vào rail (hoặc helper nhỏ), expose qua dropdown. Sort áp lên `rows` trước khi map `RunListItem`.
  - `BacktestHistoryTable` → **XÓA** (validation Q4: chỉ 1 callsite ở rail — VERIFIED `run-history-rail.tsx:79`). Sau khi di chuyển sort logic sang rail, xóa file.
- **Form drawer**: nút "+ New run" trong rail → state mở drawer. Tái dùng pattern `order-detail-drawer` (backdrop + aside + Esc close). `BacktestForm` render trong drawer, `useRunBacktest.onSuccess` đổi: `navigate({ to: '/backtest', search: { run: request_id } })` + đóng drawer.
- **Format số áp dụng:**
  - `orders-table.tsx:48` `{o.quantity}` → `formatQty(o.quantity)`.
  - `positions-table.tsx:92` `{p.quantity}` → `formatQty(p.quantity)`.
  - `order-detail-drawer.tsx`: qty (`order.quantity`), SL/TP (`formatPrice`), fills qty (`formatQty`) + price (`formatPrice`).
  - `backtest-history-table.tsx`: nếu giữ, price/qty qua format. (Compact row dùng `formatPrice` cho return%? — return là % nên giữ `pct()`; chỉ qty/price thô mới cần format.)

## Related Code Files

- Create: `web/src/components/backtest/run-list-item.tsx`
- Modify: `web/src/components/backtest/run-history-rail.tsx` (compact render + selectedRun/onSelect + "New run" drawer)
- Modify: `web/src/components/backtest/backtest-form.tsx` (render trong drawer — có thể chỉ wrap ở rail, form giữ nguyên)
- Modify: `web/src/hooks/use-backtest-run.ts` (`useRunBacktest.onSuccess` → navigate search param thay `/backtest/$runId`)
- Modify: `web/src/components/backtest/orders-table.tsx` (formatQty)
- Modify: `web/src/components/strategy/backtest-panel/positions-table.tsx` (formatQty)
- Modify: `web/src/components/backtest/order-detail-drawer.tsx` (formatQty/formatPrice)
- Modify: `web/src/index.css` (`.backtest-run-item`, drawer reuse nếu cần)
- Delete: `web/src/components/backtest/backtest-history-table.tsx` (validation Q4 — sau khi di chuyển sort logic sang rail)

## Implementation Steps

1. `use-backtest-run.ts`: đổi `useRunBacktest.onSuccess` → `navigate({ to: '/backtest', search: { run: request_id } })`.
2. Tạo `run-list-item.tsx` — compact 2 dòng + checkbox + active border. Import `formatQty`/`pct` cho số.
3. Sửa `run-history-rail.tsx`: props `selectedRun`/`onSelect`; di chuyển `SortKey`+`metricVal`+sort từ `backtest-history-table.tsx` vào rail + dropdown sort (default Newest); map `rows` đã sort → `RunListItem`; thêm nút "+ New run" + drawer state bọc `BacktestForm`; bỏ `useNavigate` row click (dùng `onSelect`). Giữ filter + Compare button (Compare vẫn `navigate({ to: '/backtest/compare', ... })`).
4. CSS `.backtest-run-item` (padding, 2 dòng, active `border-left: 3px accent`, hover bg).
5. Áp format số: orders-table, positions-table, order-detail-drawer (import từ `lib/number-format`).
6. XÓA `backtest-history-table.tsx` (sort logic đã chuyển sang rail ở bước 3) — verify không còn import.
7. `npm run lint && npm run build && npx vitest run` pass.
8. Test thủ công (agent-browser): list compact không tràn 400px, chọn run active highlight, "+ New run" mở drawer chạy được, qty/price gọn ở mọi bảng.

## Success Criteria

- [ ] Compact list không tràn ngang ở cột 400px; row active highlight; checkbox compare ≤3 + "Compare N" hoạt động.
- [ ] Dropdown sort hoạt động (Newest default + Return/Sharpe/Win%/Max DD/#trades).
- [ ] "+ New run" mở drawer, submit chạy run + điều hướng `?run=<newId>`, đóng drawer.
- [ ] qty/price gọn (không số dài `0.009343299644197806`) ở orders, trades, drawer.
- [ ] Filter strategy/symbol/interval giữ nguyên hành vi (default all strategies).
- [ ] `backtest-history-table.tsx` đã xóa, không còn import; `npm run lint && npm run build && vitest run` pass.

## Risk Assessment

- **Xóa `BacktestHistoryTable`:** verified chỉ 1 callsite (`run-history-rail.tsx:79`). Di chuyển sort logic sang rail TRƯỚC khi xóa, rồi grep verify không còn import.
- **Form drawer + run navigate:** đảm bảo đóng drawer sau navigate; mobile drawer full-width không che mất.
- **Compare flow:** checkbox select + "Compare N" vẫn trỏ `/backtest/compare?runs=` — không đổi.
- **Compact row mất thông tin so với table:** chấp nhận (user chốt compact); giữ đủ KPI quan trọng (return/sharpe/#trades/verdict). Sort GIỮ qua dropdown (validation Q2) — không mất power.
