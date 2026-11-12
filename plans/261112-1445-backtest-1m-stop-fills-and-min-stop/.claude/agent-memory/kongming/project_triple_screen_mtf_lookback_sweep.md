---
name: triple-screen-mtf-lookback-sweep
description: 2026-11-12 pre-registered 77-config replica sweep of Triple Screen gold (min stop, 1h-unit SL/TP lookbacks, ATR entry offset); one sl_tp candidate passes walk-forward but fails the deflated-Sharpe gate; trial count 221
metadata:
  type: project
---

Sweep of 2026-11-12 on the offline replica (`.cache/km3/`, gitignored scratch, may be gone; report `plans/reports/kongming-261112-1527-mtf-lookback-takeprofit-and-entry-offset.md`).

- Owner asked for `stoploss_lookback` (rename of `stop_lookback`), `takeprofit_lookback`, both in middle-interval bars, and an entry offset X (long = level + X). Advised name: `entry_offset_atr`; X read as the stop-entry offset, not an SL buffer.
- `min_stop_atr` chosen by a non-profit rule (smallest multiple with at most 2% undecidable fill-bar trades): 0.5 x ATR(14, 4h). It cuts undecidable trades from 4.7% to 1.1% and the largest 2% position from 87x to 17.9x equity. 1.0 gives 9x.
- Candidate: stoploss_lookback 10, takeprofit_lookback 10, entry offset 0.10 ATR, min stop 0.5 ATR, `exit_mode=sl_tp`, TP = farther of the swing level and 1 R. Walk-forward test folds 2024-01..2026-11: 570 trades, +0.148 R, t 2.77 (both fill bounds agree). Deflated Sharpe 0.71-0.88 at N = 219, so the trials gate fails. No single parameter passed its own fold test.
- The swing TP is under 1 R on 68% of trades, so the 1 R floor sets most targets.
- The replica's SL/TP path was never checked against the engine; swap is not modelled and sl_tp trades last 38 h on average.
- Trials on gold: about 221. The 15m holdout 2022-05..2022-12 is still untouched.

**Why:** the owner wants parameters tuned by backtest; this is the first config with an out-of-sample t above 2, which is when selection bias matters most.

**How to apply:** treat the candidate as one frozen config for an engine run and paper incubation, never as proof. Do not widen the grid around it. Keep counting trials from 221. Related: [[triple-screen-oos-diagnosis-and-rubric]] (lives in the repo-root kongming memory).
