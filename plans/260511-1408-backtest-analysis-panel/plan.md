---
title: "Backtest Analysis Panel - FIFO lot tracking + bottom panel"
description: "End-to-end backtest analysis: refactor backend to FIFO lot tracking (long/short/partial fills) + FE bottom panel with Metrics/Positions/Equity tabs"
status: pending
priority: P2
effort: "5-7d"
branch: "develop"
tags: [backtest, frontend, backend, refactor]
blockedBy: [260523-1850-backtest-storage-refactor]
blocks: []
created: "2026-05-11T07:12:09.818Z"
createdBy: "ck:plan"
source: skill
brainstorm: plans/reports/brainstorm-260511-1408-backtest-analysis-panel.md
related:
  - plans/260523-1850-backtest-storage-refactor/  # upstream: schema refactor (Fill/Trade/Order/OrderEvent + 4-collection split) must land first
---

> **⚠️ Schema migration pending (2026-05-23):** Phase 2-7 of this plan consume the embedded-array schema (`BacktestResult.trades[]`/`positions[]`) being refactored in `260523-1850-backtest-storage-refactor`. After that plan ships, Phase 2 (API Types) must be rewritten to consume `backtest_orders`+`backtest_trades` collections and slimmed `backtest_runs`. Phase 1 (Backend FIFO) is already complete in current codebase. Hold further work on this plan until upstream merges.

# Backtest Analysis Panel - FIFO lot tracking + bottom panel

**Brainstorm:** [`brainstorm-260511-1408-backtest-analysis-panel.md`](../reports/brainstorm-260511-1408-backtest-analysis-panel.md)

## Goal

User chọn 1 subscription → bottom collapsible panel hiển thị Metrics + Positions table + Equity/DD subchart. Backend refactor `result_collector` sang FIFO open-lots queue để hỗ trợ long/short/partial-fills/flip đúng convention Backtrader/QuantConnect. Reuse `getSubscriptionBacktest` API (đã trả full doc).

## Phases

| Phase | Name | Status | Blocks | Effort |
|-------|------|--------|--------|--------|
| 1 | [Backend FIFO Lot Tracking](./phase-01-backend-fifo-lot-tracking.md) | Pending | 2 | 1.5d |
| 2 | [API Types Sync](./phase-02-api-types-sync.md) | Pending | 3 | 0.5d |
| 3 | [Bottom Panel Skeleton](./phase-03-bottom-panel-skeleton.md) | Pending | 4,5,6 | 0.5d |
| 4 | [Metrics Tab](./phase-04-metrics-tab.md) | Pending | 7 | 0.5d |
| 5 | [Positions Tab](./phase-05-positions-tab.md) | Pending | 7 | 1d |
| 6 | [Equity Tab Pane](./phase-06-equity-tab-pane.md) | Pending | 7 | 1d |
| 7 | [Polish](./phase-07-polish.md) | Pending | — | 0.5d |

## Key Decisions (validated in brainstorm)

- Entry: bottom collapsible panel dưới `TradingChart`, mount khi `selectedSubId && backtestDoc.status === 'completed'`
- Tabs: Metrics | Positions | Equity (persist trong `localStorage`)
- Backend: FIFO open-lots queue thay sequential `_position_qty` state
- Short flip: 2 PositionRecord (close LONG + open SHORT), KHÔNG hybrid
- Equity render: `chart.addPane()` v5 — share timeScale main chart
- API: reuse `GET /api/v1/strategies/{sid}/symbols/{subId}/backtest`
- Out of scope: run history compare, multi-strategy overlay, CSV export, ad-hoc trigger

## Out of Scope

- Multi-run compare / history list
- Cross-strategy overlay
- Trigger new backtest từ panel
- CSV export

## Dependencies

None — single-repo, develop branch.

## Unresolved Questions

1. `OrderResult.side` default khi đọc fills cũ trong DB → default `LONG` cho backward compat?
2. Hide panel khi user xem chart symbol khác sub.symbol — hide hoặc warning tooltip?
