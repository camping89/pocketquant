---
name: gold-window-round-trip-and-timeframe-edge
description: XAUUSD:EXNESS 2025-11-09..2026-11-08 is a round trip (+1.26% net, +39% then -30%), random-walk stats at 1m-1d; generic trend rules lose on 1m after cost and mostly survive on 5m-1h
metadata:
  type: project
---

Measured 2026-11-10 from prod `bars` (bid): the 12-month backtest window opens 4004.90 and closes 4055.47 (+1.26%). High 5595 on 2026-01-29, low 3870 on 2026-10-30, drawdown -30.3% not recovered. Annualized vol 26.6%. Lag-1 autocorrelation is within ~2 SE of zero at 1m, 5m, 15m, 1h, 4h, 1d; variance ratios 0.95-1.02 up to 1h.

**Why:** The owner and a brief both assumed "gold rose strongly over the window", and read long PF = short PF as a strategy flaw. It is a property of the window. Seven generic always-in trend rules (Donchian 20/55/200, SMA 50/200, TSMOM 20/100) at 0.238 USD round trip: net positive 1 of 7 on 1m, 5 of 7 on 5m and 15m, 7 of 7 on 1h; 4h/1d have too few positions to rank. Long and short gross are near equal for every rule.

**How to apply:** Check the window's net change before reasoning about trend capture. Judge a strategy's horizon by median hold and stop distance, not its top interval (Triple Screen 1m sets hold 1-5 min; `15m,1h,4h` holds 60 min). Carver speed limit at these costs is about 650 round trips a year. The only run near the gate was `15m,1h,4h` stop/strategy, PF 1.118 at 0.5 bp slippage (2026-11-07 "raw-spread costs" run); `1h,4h,1d` was the worst older set. The plan dir `261101-0843-stf-to-mtf-foundation` is under `plans/`, not `plans/archive/`. Triple Screen has `stop_lookback` and `risk_reward` parameters. Report: `plans/reports/kongming-261110-1218-gold-timeframe-edge.md`. Related: [[exit-reason-never-persisted-trades-route-reads-positions]].
