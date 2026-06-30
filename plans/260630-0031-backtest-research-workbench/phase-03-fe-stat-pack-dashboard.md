---
phase: 3
title: "FE Stat Pack dashboard"
status: completed
priority: P2
dependencies: [2]
---

# Phase 3: FE Stat Pack dashboard

<!-- Updated: Validation Session 1 - KPI hero 5 metric, metrics 3 nhóm, drawdown top-5 + recovery def -->

## Overview

Nâng `BacktestResultView` từ 3 tab phẳng thành **single-run stat dashboard 4 tab**: Overview (KPI hero + metrics phân nhóm + equity+underwater), Trades (PnL/duration histogram + streak + profit factor LONG/SHORT split), Risk&Time (drawdown table — **monthly heatmap hoãn iter 2**), Orders (stub → P4). Dùng **lib charting đã cài** (lightweight-charts `HistogramSeries` + echarts), KHÔNG uPlot.

## Requirements

- Functional:
  - **Overview:** KPI hero 5 card tone-màu = **Total Return / CAGR / Sharpe / Max DD / Win Rate** (validation Q1); metrics phân 3 nhóm (validation): **Returns** {total_return, cagr, avg_win, avg_loss} · **Risk** {sharpe_ratio, sortino_ratio, max_drawdown, profit_factor} · **Trade Stats** {total_trades, winning_trades, losing_trades, win_rate, avg_trade_duration_seconds, total_commission}; equity+underwater full-width (lightweight-charts, drawdown đã có mỗi điểm).
  - **Trades:** PnL/duration histogram (lightweight-charts `HistogramSeries`); win/loss streak; **profit factor LONG/SHORT split** (FE chỉ tính split; aggregate lấy từ `metrics` BE — red-team M7); bảng trades (tái dùng `PositionsTable`). *(Cột MAE/MFE thuộc plan mae-mfe-excursion, không ở đây.)*
  - **Risk&Time:** `DrawdownTable` **top 5** (validation Q3) — mỗi dòng: depth %, start→trough date, recovery date (equity chạm lại peak trước drawdown), duration; tính từ `equity_curve.drawdown` (quét peak→trough→recovery). **KHÔNG monthly heatmap** (red-team H3 — hoãn iter 2; equity+underwater ở Overview đã cho cái nhìn drawdown chính xác).
  - **Orders:** stub (P4).
- Non-functional: charting dùng lib sẵn có; màu qua CSS variables (`readChartColors()` pattern); component mới co-locate `components/backtest/` (gần `backtest-result-view.tsx`), KHÔNG rải sang `strategy/backtest-panel/`; module API `web/src/api/backtest-api.ts`.

## Architecture

**Charting (red-team C3 — không uPlot):**
- Histogram PnL/duration + equity+underwater → **lightweight-charts** (`HistogramSeries`/`LineSeries`/area; theme đã wired `use-chart.ts` + `readChartColors()`).
- (Scatter/heatmap khi cần ở plan khác → echarts, đã cài.)

**Component (red-team F6/F8 — bớt premature abstraction):** KpiHero/MetricGroup/StreakBadges render INLINE trong tab dùng `MetricCard` (`components/strategy/backtest-panel/metric-card.tsx`) + regroup `metric-cards.ts` (chỉ đổi data, không đẻ component xuất khẩu). Component mới chỉ cho boundary thật: `equity-drawdown-chart`, `pnl-histogram`, `duration-histogram`, `drawdown-table`, `stats-utils`.

**Client stats (`stats-utils.ts`):** histogram bin, streak, **profit factor split theo direction** (aggregate KHÔNG tính lại — đọc `metrics.profit_factor` BE), drawdown top-N từ `equity_curve.drawdown`. *(Monthly resample bỏ — hoãn cùng heatmap.)*

```
BacktestResultView (4 tab)
├─ Overview:  KpiHero(inline) · MetricGroup×3(inline) · EquityDrawdownChart
├─ Trades:    PnlHistogram · DurationHistogram · streak/PF-split(inline) · PositionsTable
├─ Risk&Time: DrawdownTable
└─ Orders:    (stub → P4)
```

## Related Code Files

- Modify: `web/src/components/backtest/backtest-result-view.tsx` — 4 tab.
- Create: `web/src/components/backtest/equity-drawdown-chart.tsx`, `pnl-histogram.tsx`, `duration-histogram.tsx`, `drawdown-table.tsx`, `stats-utils.ts`.
- Modify: `web/src/components/strategy/backtest-panel/metric-cards.ts` — regroup 14 metric thành 3 nhóm (data, không đẻ component).
- Reference: `web/src/components/chart/trading-chart.tsx`, `use-chart.ts`, `readChartColors()` (pattern theme-aware lightweight-charts + `HistogramSeries`); `metric-card.tsx`; `web/src/index.css` (CSS variables).
- Reference: `web/src/api/backtest-api.ts` (module đúng).

## Implementation Steps

1. `stats-utils.ts`: histogram bin, streak, profit-factor-split, drawdown top-N (unit-testable thuần hàm).
2. Overview: KpiHero + MetricGroup inline (dùng `MetricCard` + regroup `metric-cards.ts`) + `EquityDrawdownChart` (lightweight-charts equity line + underwater area pane).
3. Trades: `PnlHistogram` + `DurationHistogram` (`HistogramSeries`) + streak/PF-split inline + `PositionsTable`.
4. Risk&Time: `DrawdownTable`.
5. `BacktestResultView`: ráp 4 tab; Orders stub.
6. `npm run lint && npm run build`.

## Success Criteria

- [x] Overview: KPI hero + 3 nhóm metric + equity+underwater render đúng theme dark/light.
- [x] Trades: 2 histogram + streak + profit factor split LONG/SHORT (aggregate khớp `metrics` BE).
- [x] Risk&Time: drawdown table top-N render.
- [x] Histogram/chart đổi màu khi toggle theme.
- [x] KHÔNG thêm uPlot/visx vào `package.json`.
- [x] `npm run lint && npm run build` pass.

## Risk Assessment

- **profit_factor 2 nguồn (red-team M7):** FE chỉ tính split LONG/SHORT; aggregate đọc `metrics.profit_factor` BE — không 2 định nghĩa lệch.
- **component scatter (red-team F6):** KpiHero/MetricGroup/StreakBadges inline, không đẻ file riêng → giảm surface.
- **heatmap đã hoãn (red-team H3):** không hiển thị số tài chính xấp xỉ; equity+underwater (chính xác) thay thế nhu cầu nhìn drawdown.
- **lightweight-charts histogram:** dùng `HistogramSeries` (đã dùng ở `trading-chart.tsx:108`) — không cần lib mới.
