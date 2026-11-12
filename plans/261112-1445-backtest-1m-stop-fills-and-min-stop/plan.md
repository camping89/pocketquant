---
title: "Backtest fills on 1m bars and Triple Screen stop and target parameters"
description: "Backfill 1m gold bars, make backtests replay 1m bars so stop entries, SL and TP fill in true order as in live paper, give Triple Screen higher-timeframe stop-loss and take-profit lookbacks, entry and stop offsets and a minimum stop, then run three pre-registered configs and score them with the strategy assessment rubric at 2% risk."
status: pending
priority: P2
effort: 2.5d
branch: develop
tags: [backend, backtest, experimental]
blockedBy: []
blocks: []
created: 2026-11-12
---

# Backtest fills on 1m bars and Triple Screen stop and target parameters

## Outcome

- **1m fills:** a backtest whose entry interval is 15m or longer fills resting stops, and checks SL and TP, on the 1m bars inside each entry bar, in time order. Today it counts a stop as stopped out whenever the fill bar's range also touches the SL. In the 2025-11..2026-11 replay, about 18 of 32 such stops were false.
- **New Triple Screen parameters:**
  - `stoploss_lookback` (the renamed `stop_lookback`) and a new `takeprofit_lookback`, both counted in bars of the next higher timeframe;
  - an entry offset and a stop-loss offset against fakeouts;
  - a minimum stop distance.
- **Measurement:** three pre-registered configurations run on 2024-05..2026-11 and are scored with `docs/governance/strategy-assessment-rubric.md` at the owner's fixed 2% risk.

## Why

- **Evidence:**
  - `plans/reports/kongming-261112-1356-triple-screen-diagnosis-and-assessment-rubric.md`, sections 5.3 and 5.6;
  - `plans/reports/kongming-261112-1527-mtf-lookback-takeprofit-and-entry-offset.md`, the parameter design, the pre-registered sweep and candidate C;
  - `plans/reports/backtest-261111-1432-triple-screen-2023-2026-out-of-sample-2pct.md`.
- **Fill rule:** the stop-on-fill-bar rule (`fill_resting_stops` in `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py`) moves the out-of-sample total between -11 R and +84 R.
- **Stop size:** stops as close as 0.5 USD make positions up to 87x equity at 2% risk. A minimum stop of 0.5 x ATR(4h) caps them at about 18x and cuts undecidable fill-bar trades from 4.7% to 1.1%.

## Design decisions

- **1m fills:**
  - The paper broker already acts only on the finest interval it sees for a symbol (`_is_finest`), and live paper sees the finer bars; phase 2 verifies this.
  - The backtest replays only the entry interval (`backtest_app_service.py`, the `self._bar_repo.stream(...)` loop).
  - So the backtest also streams 1m bars, merged in time order, and the broker's existing rules run at 1m resolution, as in live.
  - Rejected: a lazy resolver inside the broker, which would add a second fill path that live never uses.
- **Backfill:** run locally in remote-db mode (`README.md`, `just tunnel`), not on the 3.9 GB VPS. `scripts/backfill/provider_bars.py` holds every fetched bar in memory.
- **Parameters:** the definitions in the kongming report, section 3.2, plus the owner's stop-loss offset (phase 3).
- **Offsets as two parameters:** the owner wants X on both the entry and the stop loss. They are two parameters, `entry_buffer_atr` and `stoploss_buffer_atr`, so candidate C keeps its pre-registered values (entry offset 0.1, stop-loss offset 0). Any non-zero stop-loss offset is a new trial.

## Phases

| # | Phase | Status | Depends on |
|---|---|---|---|
| 1 | [Backfill 1m gold bars](./phase-01-backfill-1m-gold-bars.md) | pending | - |
| 2 | [Backtest replays 1m bars for fills](./phase-02-backtest-replays-1m-fills.md) | pending | 1 for the real-data check only |
| 3 | [Triple Screen stop and target parameters](./phase-03-triple-screen-stop-and-target-parameters.md) | pending | - |
| 4 | [Re-run and rubric score](./phase-04-rerun-and-rubric-score.md) | pending | 1, 2, 3 |
| 5 | [Ship](./phase-05-ship.md) | pending | 4 |

## Acceptance criteria

- **Coverage:** XAUUSD:EXNESS 1m bars cover 2024-05-01..now on prod, with the coverage and gaps recorded. The pre-write backup exists on the VPS.
- **No look-ahead:** a backtest with 1m coverage never fills a stop on a 1m bar that starts before its signal bar closed. A test proves this, together with `docs/governance/no-look-ahead-rules.md`.
- **Fill order:** a stop whose fill bar touched the SL only before the entry is not stopped out. One whose SL was touched after the entry is. Without 1m coverage, the result equals today's rule.
- **Unchanged trades:** a backtest whose window has no 1m bars, run with the old lookback converted (80 entry bars become `stoploss_lookback=20`), gives the same trades as stored run `01a1c41f`.
- **Parameters:**
  - Triple Screen has `stoploss_lookback` (default 2), `takeprofit_lookback`, `entry_buffer_atr`, `stoploss_buffer_atr` and `min_stop_atr`.
  - The new ones default to off; the float ones default to `0.0`.
  - `stop_lookback` is gone from the code, with no alias.
- **Replica check:** the engine's trades for candidate C, on a window without 1m bars, match `.cache/km3/candidate_trades.csv`. Do this before reading any profit.
- **Report:** a report scores A, B and C with the rubric at 2% risk, with the out-of-sample and in-sample segments shown separately and the trial count updated.
- **Quality gates:** the full test suite, pyright and the import linter pass.

## Constraints

- `CLAUDE.md` rules: KISS; at most two hops; repositories in core; no docstrings; delete dead code; never deprecate and keep.
- **Prod data:** back up before any write; live trading stays disarmed.
- **Release:** a `develop` to `master` release needs the owner's explicit yes.
- **Pre-registration:** the phase-4 values are fixed below. Nothing else runs, and no neighbour of C is tried.

## Non-goals

- A monthly loss brake, other strategies, other symbols, and the Exness account terms.
- Changing live paper or Exness order handling.
- Spending the 2022-05..2022-12 holdout. The owner keeps it for a later strategy.

## Owner decisions (2026-11-12)

1. **Minimum stop:** a closer swing stop is widened to `min_stop_atr` x ATR(14) on the top interval, and the trade is kept. The value is 0.5, chosen by the pre-registered rule.
2. **X:** it applies to both the entry (long = level + X, short = level - X) and the stop loss (long = swing - X, short = swing + X).
3. **Default:** `stoploss_lookback` defaults to 2, Elder's two bars of the trading timeframe.
4. **Rubric G2:** in-sample t >= 3.0 is the binding test. The Deflated Sharpe Ratio is reported but does not decide. Update `docs/governance/strategy-assessment-rubric.md` to match.
5. **Holdout:** keep the 2022 holdout untouched.
6. **Paper:** open a paper subscription for C only if C survives the phase-4 engine run.
7. **Where:** backtests run locally against a local Mongo copy, several in parallel.
