---
phase: 2
title: "Backtest replays 1m bars for fills"
status: pending
priority: P1
effort: "1d"
dependencies: []
---

# Phase 2: Backtest replays 1m bars for fills

## Goal
When 1m bars cover the window, a backtest publishes them with the entry-interval bars in true time order. The paper broker's finest-interval rule then fills stops and checks SL and TP on 1m bars, as live paper does.

## Facts (verified 2026-11-12)
- `PaperBrokerAdapter._is_finest` lets only the finest interval seen for a symbol fill or exit. `fill_resting_stops` runs on every `BarCompletedEvent` before strategies decide (`engine/strategy/strategy_app_service.py`, `_on_bar_completed`). Strategies receive only their own interval (`_find_strategies`).
- `BacktestAppService.run` streams only `config.intervals[0]`. It sets the simulation time to the bar start (`set_simulation_time(bar.datetime)`) and publishes with `occurred_at=bar.datetime`. A stop rests from `placed_at` and fills only on a bar with `occurred_at > placed_at`.
- The equity curve is marked on every published bar (`_mtm_on_bar`) and downsampled at persist time.

## Files to Create / Modify
- Modify: `src/pocketquant/engine/backtest/backtest_app_service.py` (replay loop).
- Modify: `src/pocketquant/engine/backtest/backtest_report_app_service.py`, only if the run snapshot needs the fill interval.
- Modify tests: `tests/backtest_test/engine/` and `tests/core_test/infra/brokers/test_paper_broker_stop_entry.py`.

## Tasks & Steps
1. **Live parity.** Confirm the live trader publishes XAUUSD 1m `BarCompletedEvent`s next to 15m. Read `engine/market_data/app_services/bar_app_service.py` and the tracked intervals, and check a prod log or snapshot. If live paper does not see 1m bars, stop and report: the premise of this design is wrong.
2. **Merge the streams.** In the replay loop, when the entry interval is coarser than 1m and the first 1m bar is at or before `start_date`, stream the 1m bars for the same window too. Merge by bar end (start + interval). On a tie, publish the 1m bar first, so the 1m bars inside a 15m bucket go out before the 15m bar that closes it.
3. **Simulation time.** Give the simulation clock and `occurred_at` a meaning that stays monotonic across both streams, without changing the result of a single-interval run. Every stop placed on a 15m signal bar must fill only on 1m bars that start at or after that bar's close. Write down the chosen rule in a `#` comment at the loop.
4. **Equity curve.** Mark to market only on entry-interval bars, so the equity curve and its memory size stay as they are today.
5. **Fallback.** Without 1m coverage from `start_date`, keep the single-stream replay unchanged. Record which fill interval the run used in the run snapshot, so a report can tell the two apart.
6. **Gaps.** A 15m bucket with no 1m bar inside only delays fills to the next 1m bar. Note this in the comment. Phase 1 measures how often it happens.
7. **Tests**, named by the rule they prove:
   - A stop entry whose fill bucket touched the SL in a 1m bar before the entry is not stopped out on the fill.
   - A stop entry whose SL is touched in a 1m bar after the fill is stopped out at the SL.
   - A TP is checked from the 1m bar after the fill, not on the fill bar.
   - No stop fills on a 1m bar that starts before its signal bar closed (no look-ahead).
   - Without 1m bars, the trades equal the single-stream result.
   - The equity curve has one point per entry-interval bar.
8. Read `docs/governance/no-look-ahead-rules.md` and confirm that the higher-timeframe context rules still hold with the mixed stream.

## Verification
- `uv run pytest tests/backtest_test tests/core_test/infra/brokers -q`, then the full suite: `just test` with Docker running. The 4 known Windows tz failures are expected.
- `uv run pyright src/pocketquant/engine/backtest` and the import linter.
- **Golden check:** replay run `01a1c41f`'s config locally on a window with no 1m bars, and get the same 489 trades.

## Risk and rollback
- **Speed:** about 15 times more events per run. Measure the run time of one year in phase 4 before any long run.
- **Wrong clock semantics:** this would create look-ahead. The no-look-ahead test is the gate.
- **Rollback:** revert the commit. Stored runs are not affected.
