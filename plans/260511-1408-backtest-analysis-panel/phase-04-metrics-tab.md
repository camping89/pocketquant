---
phase: 4
title: "Metrics Tab"
status: pending
priority: P2
effort: "0.5d"
dependencies: [3]
---

# Phase 4: Metrics Tab

## Overview

Grid cards hiển thị toàn bộ performance metrics: return, CAGR, Sharpe, Sortino, max drawdown, win rate, profit factor, trade counts, avg win/loss, avg duration, total commission. Color-coded by sign (green/red), tooltip giải thích mỗi metric.

## Requirements

- Functional:
  - 12+ metric cards.
  - Negative-is-good metrics (max_drawdown) → red khi giá trị nhỏ hơn 0 (đúng theo direction).
  - `null` / missing → "—" hoặc "N/A".
  - Tooltip hiển thị mô tả + formula.
- Non-functional: responsive grid, < 100 LOC tab file.

## Architecture

### Card data model

```typescript
interface MetricCard {
  label: string
  value: string         // pre-formatted
  raw: number | null
  tone: 'positive' | 'negative' | 'neutral'
  tooltip: string
}
```

`metric-cards.ts` exports `buildMetricCards(metrics: BacktestMetrics): MetricCard[]`:

| Card | Format | Tone rule |
|------|--------|-----------|
| Total Return | `+12.34%` | `raw > 0 ? positive : negative` |
| CAGR | `+8.50%` | same |
| Sharpe Ratio | `1.85` | `>=1 positive, <0 negative, else neutral` |
| Sortino Ratio | `2.10` | same |
| Max Drawdown | `-15.20%` | `negative` (always loss) |
| Win Rate | `55.0%` | `>=0.5 positive, <0.4 negative, else neutral` |
| Profit Factor | `1.42` | `>=1.5 positive, <1 negative, else neutral` |
| Total Trades | `124` | `neutral` |
| Winning | `68` | `positive` |
| Losing | `56` | `negative` |
| Avg Win | `+125.4` | `positive` |
| Avg Loss | `-89.2` | `negative` |
| Avg Duration | `2h 34m` | `neutral` (format from `avg_trade_duration_seconds`) |
| Total Commission | `12.45` | `neutral` |

### Layout

CSS grid `auto-fill` `minmax(140px, 1fr)`. Card: label + value + small tone bar.

## Related Code Files

### Create
- `packages/pocketquant-web/src/components/strategy/backtest-panel/metrics-tab.tsx`
- `packages/pocketquant-web/src/components/strategy/backtest-panel/metric-cards.ts` — `buildMetricCards` builder + formatters
- `packages/pocketquant-web/src/components/strategy/backtest-panel/metric-card.tsx` — single card component

### Modify
- `packages/pocketquant-web/src/index.css` — `.metric-card` styles

## Implementation Steps

1. **Create `metric-cards.ts`** — builder + format helpers (percent, signed number, duration).
2. **Create `metric-card.tsx`** — render label + value + tone class. Tooltip via title attribute hoặc lightweight tooltip lib (KISS: dùng `title`).
3. **Create `metrics-tab.tsx`** — accept `metrics: BacktestMetrics`, call builder, render grid.
4. **Handle null metrics** — nếu `backtest.metrics === null` (failed) → render error state.
5. **CSS grid + card styling** — match dark theme.
6. **Replace stub** trong Phase 3 với real component.

## Success Criteria

- [ ] All 14 metric cards render
- [ ] Tone colors đúng cho mỗi metric
- [ ] Avg duration format human-readable (`2h 34m`, `1d 5h`, `45m`)
- [ ] Tooltips hiển thị on hover
- [ ] Failed backtest case render error state
- [ ] Responsive (3-4 columns desktop, 2 mobile)

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Duration formatter edge cases (0s, NaN) | Unit test format helper |
| Color tones không đủ contrast | Reuse existing theme color tokens |

## Notes

- Skip charting libraries — pure HTML/CSS cards.
- Avg duration computed from `avg_trade_duration_seconds` (number | null).
