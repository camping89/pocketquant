# Engulfing key level and chart markers

The take-profit formula is the code in `engulfing_strategy_service.py`. This file holds what the code cannot say: one decision and two traps that span the strategy and the chart.

## The key level is a proxy, not a swing pivot

- The key level is the extreme of a plain window of recent bars, held by the engulfing strategy itself.
- The engine has no swing-pivot detection. Detecting a peak or trough against the bars on both sides was considered and left out.
- A one-bar spike in the window sets the key level as firmly as a real reversal does. Do not read the key level as a confirmed swing high or low.

## A chart marker is not a strategy entry

- The chart's Engulfing toggle marks every pattern the detector finds. The strategy enters only the patterns that pass its own gates in `EngulfingStrategyService.on_bar_completed`.
- A marker with no trade is expected, not a bug. A marker does not mean the strategy did or will enter there.
- The strong/weak colour uses a fixed chart constant (`STRONG_THRESHOLD` in `web/src/lib/indicators/engulfing.ts`). It does not read the strategy's `max_rejection_wick_pct`.
- When a backtest tunes `max_rejection_wick_pct`, the colours no longer show which patterns that backtest enters. No test ties the two values together.
