---
phase: 3
title: "FE MAE-MFE scatter + columns"
status: pending
priority: P2
dependencies: [2]
---

# Phase 3: FE MAE-MFE scatter + columns

## Overview

Hiển thị MAE/MFE/R-multiple trên workbench: thêm cột vào `PositionsTable` (Trades tab) + `MaeMfeScatter` (echarts) vào Risk&Time tab. Guard null cho run cũ (toàn bộ run hiện có = null cho tới khi chạy run mới sau khi Phase 2 deploy).

## Requirements

- Functional: cột MAE/MFE/R-multiple trong bảng trades ("—" khi null); scatter mfe-vs-mae màu theo win/loss; run cũ (null) → scatter rỗng, không crash.
- Non-functional: scatter dùng **echarts** (`^6.0.0` đã cài, dùng ở `job-timeline-chart.tsx`); màu theo CSS variables theme; KHÔNG thêm uPlot/visx.

## Architecture

- `MaeMfeScatter`: echarts scatter, x=mae, y=mfe, màu điểm theo `pnl>0` (`--up-color`/`--down-color`). Filter bỏ điểm null trước khi vẽ. Empty state khi 0 điểm hợp lệ.
- `PositionsTable`: thêm 3 cột; formatter null → "—" (KHÔNG `.toFixed()` trên null).
- Theme: echarts re-apply option màu khi theme đổi (đọc CSS variables), pattern theo `job-timeline-chart.tsx`.

## Related Code Files

- Modify: `web/src/api/backtest-api.ts` (**đường đúng — KHÔNG phải `lib/`**) — type `BacktestTrade` thêm `mae?: number | null` / `mfe?` / `r_multiple?`.
- Modify: `web/src/components/strategy/backtest-panel/positions-table.tsx` — 3 cột + null formatter.
- Create: `web/src/components/strategy/backtest-panel/mae-mfe-scatter.tsx` (echarts).
- Modify: `web/src/components/backtest/backtest-result-view.tsx` — mount scatter vào Risk&Time tab.
- Reference: `web/src/components/monitor/job-timeline-chart.tsx` (pattern echarts init + theme).

## Implementation Steps

1. `backtest-api.ts`: thêm 3 field optional vào `BacktestTrade`.
2. `positions-table.tsx`: 3 cột + formatter null→"—".
3. `mae-mfe-scatter.tsx`: echarts scatter, filter null, empty state, theme-aware màu.
4. Mount vào Risk&Time tab.
5. `npm run lint && npm run build`.

## Success Criteria

- [ ] Run mới: cột MAE/MFE/R-multiple hiện số; scatter có điểm màu win/loss.
- [ ] Run cũ (null): cột "—", scatter rỗng, KHÔNG crash.
- [ ] Test render với fixture trade null → không throw.
- [ ] Scatter đổi màu khi toggle theme.
- [ ] `npm run lint && npm run build` pass.

## Risk Assessment

- **null crash (run cũ = 100% data hiện có)**: formatter + filter null bắt buộc; test fixture null khóa acceptance.
- **echarts theme**: re-apply option khi theme đổi (pattern job-timeline-chart đã có).
- **Phụ thuộc Phase 2 + workbench**: cần `list_trades` trả field (P2) + Trades/Risk&Time tab tồn tại (workbench P4). blockedBy workbench plan.
