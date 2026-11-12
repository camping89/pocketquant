---
phase: 4
title: "Re-run and rubric score"
status: pending
priority: P2
effort: "3h"
dependencies: [1, 2, 3]
---

# Phase 4: Re-run and rubric score

## Goal
Measure the 1m fill, the minimum stop and candidate C with the engine. Score them with `docs/governance/strategy-assessment-rubric.md` at 2% risk.

## Runs (pre-registered; nothing else runs)
- **Shared settings:**
  - Triple Screen `15m,1h,4h`, `entry_type=stop`, spread 0.08, commission 3 bp, slippage 0.1 bp, 10 000 USD.
  - Window: 2024-05-01, or the first full 1m day from phase 1, to 2026-11-10 23:59 UTC. 1m fills on.
- **A, frozen config:** `exit_mode=strategy`, `stoploss_lookback=20`.
- **B:** A plus `min_stop_atr=0.5`.
- **C, the walk-forward candidate** (kongming report, section 5.3): `stoploss_lookback=10`, `takeprofit_lookback=10`, `entry_offset_atr=0.1`, `stoploss_offset_atr=0.0`, `min_stop_atr=0.5`, `exit_mode=sl_tp`, `risk_reward=1.0`.
- **Trial count:** about 221 configurations so far. A, B and C were already counted in the sweep, so they add none.

## Tasks & Steps
1. **Local data.** Copy the prod XAUUSD:EXNESS bars for 1m, 15m, 1h, 4h and 1d, plus the `symbols` doc, into a local Mongo (Docker, `README.md`). Use `mongodump --query` on the VPS and `mongorestore` locally. This is read-only on prod.
2. **Replica check, before any profit is read.** Run C locally on a window without 1m bars (2023-01..2024-04). Its trades must match `.cache/km3/candidate_trades.csv` for that window.
   - If they do not match, stop. Ask kongming to redo its report, section 5, with the engine's exit path.
3. **Runs.** Point a local `.env` at that Mongo. Run A, B and C in parallel as separate processes, through `BacktestCommandService.run` and `BacktestExecutionService.execute_and_persist`.
4. **Timing.** Time one month of A first. Stop and report if a full run would take over 2 hours.
5. **Compare A** trade by trade with run `01a1c980` on the same window: fill-bar stops removed, R changed, total R.
6. **Rescale** each run to 2% compounding over each trade's stop, as in `.cache/oos/an.py`. Report:
   - final equity and max drawdown;
   - worst day and worst streak;
   - P(drawdown of 50% or more), by bootstrap;
   - the Kelly fraction;
   - the largest position as a multiple of equity;
   - the worst gap loss.
7. **Score** A, B and C with the rubric, gates G1 to G5 and S1 to S10. Show the out-of-sample segment (2024-05-01..2025-11-08) and the in-sample year (2025-11-09..2026-11-08) separately.
8. **Decision rule for C, fixed now.** Drop C if the engine's mean R on 2024-05..2026-11 is at or below 0, or its t is below 1.5. If it survives, phase 5 asks the owner about a paper subscription for C.
9. Write `plans/reports/backtest-<date>-triple-screen-1m-fills-stop-target-rubric.md`, with the verdict and the next step.

## Verification
- Every number in the report is reproducible from a script under `.cache/` and the run ids.
- The run snapshot shows the 1m fill interval for every run.

## Risk
- **Small sample:** about 18 months of out-of-sample trades. The test can reject C but may be too small to confirm it (the rubric's power check). About 320 new trades are needed to confirm +0.15 R.
- **Not modelled:** swap. C holds for 38 hours on average, so the report must state swap as an unmodelled cost.
