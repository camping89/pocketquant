---
phase: 2
title: "Backtest replays 1m bars for fills"
status: done
priority: P1
effort: "1d"
dependencies: [1]
---

# Phase 2: Backtest replays 1m bars for fills

## Goal
When the symbol has a 1m bar at or before `start_date` and the entry interval is coarser than 1m, a backtest publishes 1m bars together with the entry-interval bars, in true time order. The paper broker's finest-interval rule then fills stops and checks SL and TP on 1m bars, as live paper does. A run without 1m coverage is unchanged.

## Facts (verified 2026-11-12 by the red team)
- `PaperBrokerAdapter._is_finest` (`paper_broker_adapter.py:524-529`) lets only the finest interval seen for a symbol fill or exit. It is checked in `fill_resting_stops` (`:554`) and in the broker's own `_on_bar_completed` (`:678`). `reset()` clears it (`:794`), and each backtest gets its own broker.
- A resting stop fills only on an event with `occurred_at > placed_at` (`:565`). `placed_at`, `opened_at` and `exit_time` come from `get_current_time()` (`:139`, `:438`, `:463`), which returns the simulation clock in a backtest.
- Only the SL is checked on the fill bar; the TP waits one bar (`:532-541`).
- `fill_resting_stops` runs on every `BarCompletedEvent` before strategies decide (`engine/strategy/strategy_app_service.py`, `_on_bar_completed`). Strategies receive only their own interval (`_find_strategies`).
- `BacktestAppService.run` (`engine/backtest/backtest_app_service.py:101-125`) streams only `config.intervals[0]`. It sets `set_simulation_time(bar.datetime)` and publishes with `occurred_at=bar.datetime` and `bar_start=bar.datetime`.
- `_mtm_on_bar` (`backtest_app_service.py:80-84`) marks equity on every published bar.
- `BarRepository.stream` (`bar_repository.py:130-151`) is `find(query).sort("datetime", 1)` with no `batch_size`. `BarRepository.find(symbol, interval, end_date=..., limit=1)` returns the newest bar at or before `end_date` (it sorts descending, `:100-128`).
- `INTERVAL_SECONDS` is in `src/pocketquant/core/common/constants.py:45`.
- `config_snapshot` is built in `backtest_report_app_service.py:334-348`. `BacktestReportAppService` is constructed in `backtest_app_service.py` and in two tests: `tests/backtest_test/engine/test_report_annualization_source.py` and `tests/backtest_test/engine/test_result_collector_mark_to_market.py`.

## The rule this phase implements
- **Clock.** For every published bar, `clock = bar.datetime + step(bar interval) - step(finest)`.
  - `finest` is 1m in a merged run, and the entry interval in a single-stream run.
  - Call `set_simulation_time(clock)` and publish with `occurred_at=clock`. `bar_start` stays `bar.datetime`. Do not set `bar_end`; it turns on live-only stale checks.
  - In a single-stream run, `clock = bar.datetime`, which is exactly today's value.
- **Publish order, merged run.** For each entry bar E (start `T`, end `T + step`), in time order:
  1. Publish every not-yet-published 1m bar whose start is before `T + step`, oldest first.
  2. If none of the 1m bars published in step 1 starts at or after `T`, publish one stand-in event first. It has `interval="1m"`, `bar_start=T`, clock `T`, and E's open, high, low, close and volume.
  3. Publish E.
  After the last entry bar, publish the 1m bars left in the window.
- **Mark to market** only on events whose `interval` equals `config.intervals[0]`.
- **Gate.** The merged run is used only when `config.intervals[0] != "1m"` and `await self._bar_repo.find(config.symbol, Interval("1m"), end_date=config.start_date, limit=1)` is non-empty. Otherwise the run is single-stream.
- **Meaning of stored times, merged run.** `placed_at` is the signal bar's end minus 60 s. `opened_at` is the start of the 1m bar that filled. An SL or TP `exit_time` is the start of the 1m bar that hit. A strategy exit's `exit_time` is the deciding bar's end minus 60 s.
- **Why there is no look-ahead.** A stop exists only after its signal bar is published, which happens after every 1m bar of that bucket. The first 1m bar after it has clock `T + step`, which is greater than `placed_at = T + step - 60 s`.

## Files to Create / Modify
- Modify: `src/pocketquant/engine/backtest/backtest_app_service.py` (the `run` method's replay loop and `_mtm_on_bar`).
- Modify: `src/pocketquant/engine/backtest/backtest_report_app_service.py` (`__init__` gets a keyword `fill_interval: str`; `config_snapshot` gets `"fill_interval"`).
- Modify: `src/pocketquant/core/infra/persistence/repositories/bar_repository.py` (`stream`: add `.batch_size(1000)` to the cursor).
- Modify: `tests/backtest_test/engine/test_report_annualization_source.py` and `tests/backtest_test/engine/test_result_collector_mark_to_market.py` (pass `fill_interval`).
- Create: `tests/backtest_test/engine/test_backtest_1m_fill_replay.py`.

## Tasks

### Task 2.1 — Live parity
- **Goal:** confirm that live paper sees XAUUSD 1m bars, which is this design's premise.
- **Target files:** `src/pocketquant/engine/market_data/app_services/bar_app_service.py` (read only).
- **Steps:**
  1. Read `bar_app_service.py:30-60` and find where 1m `BarCompletedEvent`s are published.
  2. On prod, read-only: `db.bars.find({symbol:"XAUUSD:EXNESS",interval:"1m"}).sort({datetime:-1}).limit(1)`.
- **Success criteria:** the code publishes 1m events, and the newest prod 1m bar is less than 10 minutes old during market hours.
- **Verify:** both hold. If live does not publish 1m events, stop and report: the design premise is wrong.

### Task 2.2 — Cursor batch size
- **Goal:** neither cursor sits idle long enough to time out during a merged replay.
- **Target files:** `bar_repository.py`, method `stream`.
- **Steps:**
  1. Change the cursor line to `collection.find(query).sort("datetime", 1).batch_size(1000)`.
- **Success criteria:** the cursor is created with batch size 1000.
- **Verify:** no verification needed; task 2.6 runs the existing backtest tests.

### Task 2.3 — Merged replay loop
- **Goal:** the replay implements the rule above.
- **Target files:** `backtest_app_service.py`, method `run`, the `async for bar in self._bar_repo.stream(...)` block and `_mtm_on_bar`.
- **Steps:**
  1. Before the collector is built, compute `entry = config.intervals[0]` and `merged = entry != "1m" and bool(await self._bar_repo.find(config.symbol, Interval("1m"), end_date=config.start_date, limit=1))`. Set `fill_interval = "1m" if merged else entry`, and pass `fill_interval=fill_interval` to `BacktestReportAppService(...)`.
  2. Write one local `async def _publish(bar, interval: str, finest_s: int)` inside `run`:
     - compute the clock;
     - call `self._broker.set_current_price`;
     - call `set_simulation_time(clock)`;
     - publish the `BarCompletedEvent` with `interval=interval`, `bar_start=bar.datetime` and `occurred_at=clock`;
     - count `bars_processed` and yield every `_YIELD_EVERY`, as today.
     Skip bars whose `datetime` is `None`, as today.
  3. Single stream (`merged` is false): keep the current loop and call `_publish(bar, entry, INTERVAL_SECONDS[entry])`.
  4. Merged:
     - open `ones = self._bar_repo.stream(config.symbol, Interval("1m"), config.start_date, config.end_date)` as an async iterator and keep one look-ahead bar `pending`;
     - for each entry bar E from the entry `stream`, run the three publish steps of the rule, with `finest_s = 60`;
     - after the loop, publish the remaining 1m bars.
     The stand-in event is `await _publish(E, "1m", 60)`. Its clock is `T + 60 - 60 = T`, because `_publish` takes the step from the `interval` argument (`INTERVAL_SECONDS[interval]`), not from the bar.
  5. In `_mtm_on_bar`, return early when `event.interval != entry`.
  6. Put one `#` comment above the merged branch with three facts: the clock formula, why it has no look-ahead, and that a bucket with no 1m bar is filled by the coarse rule through the stand-in.
- **Success criteria:** the code follows the rule. The single-stream path computes the same clock as today.
- **Verify:** `uv run pyright src/pocketquant/engine/backtest` reports `0 errors`.

### Task 2.4 — Fill interval in the snapshot
- **Goal:** every stored run says which interval filled it.
- **Target files:** `backtest_report_app_service.py` (`__init__`, `config_snapshot`); the two test files listed above.
- **Steps:**
  1. Add a required keyword `fill_interval: str` to `BacktestReportAppService.__init__` and store it.
  2. Add `"fill_interval": self._fill_interval` to `config_snapshot`.
  3. In both test files, pass `fill_interval="15m"`, or the test's entry interval, where they construct `BacktestReportAppService`.
- **Success criteria:** the snapshot has `fill_interval`.
- **Verify:** `uv run pytest tests/backtest_test/engine/test_report_annualization_source.py tests/backtest_test/engine/test_result_collector_mark_to_market.py -q` exits 0.

### Task 2.5 — Tests for the rule
- **Goal:** each rule is pinned by a test named after it.
- **Target files:** `tests/backtest_test/engine/test_backtest_1m_fill_replay.py` (new). Copy the fixture style of `tests/backtest_test/engine/test_paper_broker_signal_bar.py` and `tests/backtest_test/engine/test_triple_screen_backtest.py`.
- **Steps:** write these tests, using hand-built 15m and 1m bars:
  1. `test_stop_whose_bucket_touched_sl_before_entry_is_not_stopped_out`
  2. `test_stop_whose_sl_is_touched_after_entry_is_stopped_out_at_sl`
  3. `test_tp_is_checked_from_the_1m_bar_after_the_fill`
  4. `test_no_stop_fills_on_a_1m_bar_starting_before_signal_bar_close`
  5. `test_bucket_without_1m_bars_fills_by_the_coarse_rule`
  6. `test_without_1m_coverage_trades_equal_the_single_stream_run`, with trades compared on side, entry time, exit time, prices, quantity and pnl.
  7. `test_simulation_clock_never_decreases_in_a_merged_run`, by subscribing to `BarCompletedEvent` and recording `occurred_at`.
  8. `test_every_trade_exits_at_or_after_its_entry`
  9. `test_equity_curve_has_one_point_per_entry_bar`
  10. `test_snapshot_records_the_fill_interval`, for both `1m` and `15m`.
- **Success criteria:** all ten tests pass.
- **Verify:** `uv run pytest tests/backtest_test/engine/test_backtest_1m_fill_replay.py -q` exits 0 and reports `10 passed`.

### Task 2.6 — Suite, linters and no-look-ahead rules
- **Goal:** nothing else broke, and the governance rules still hold.
- **Target files:** `docs/governance/no-look-ahead-rules.md` (read only).
- **Steps:**
  1. Read `docs/governance/no-look-ahead-rules.md`. For each rule, write one line in the commit message body saying how the merged stream keeps it. If a rule is broken, the Verify step fails.
  2. Start Docker Desktop if `docker ps` fails.
  3. Run `uv run pytest tests/ -q`, `uv run lint-imports`, `uv run python scripts/code_metrics.py --ratchet` and `uv run pyright src/pocketquant/engine/backtest src/pocketquant/core/infra/persistence/repositories`.
- **Success criteria:** every gate passes, apart from the known Windows tz tests.
- **Verify:**
  - pytest has no failures other than those in `test_utc_runtime_guard.py` and `test_cron_trigger_timezone.py` (4 failed plus 4 errors are expected).
  - `lint-imports` exits 0.
  - The ratchet exits 0. If it fails only on a ceiling, raising the ceiling in `[tool.code-metrics]` is allowed; padding code is not.
  - pyright reports `0 errors`.
  - Every no-look-ahead rule has a line.

### Task 2.7 — Golden check G-a
- **Goal:** the new code reproduces B0 exactly on a run without 1m coverage.
- **Target files:** `.cache/golden/b0.py` (from phase 1), `.cache/golden/ga.csv`.
- **Steps:**
  1. Repeat phase 1 task 1.1 (target guard).
  2. Run `.cache/golden/b0.py` with its output path set to `.cache/golden/ga.csv`.
  3. Compare `ga.csv` with `b0.csv` on all columns, in order. Read the new run's `config_snapshot.fill_interval`.
- **Success criteria:** identical lists, and `fill_interval` is `15m`.
- **Verify:** the comparison prints `0` differing rows and both files have 1 991 rows. `fill_interval == "15m"`.

### Task 2.8 — Commit
- **Goal:** one focused commit on `develop`.
- **Steps:**
  1. `git add` the files listed under "Files to Create / Modify" only.
  2. Commit `feat(backtest): fill stops and exits on 1m bars when the window has 1m coverage`, with the no-look-ahead lines in the body.
- **Success criteria:** `git status --short` shows no staged or modified source files after the commit.
- **Verify:** `git log -1 --stat` lists only the files above.

## Risk and rollback
- **Speed:** about 16 times more events per merged run. Phase 4 task 4.4 measures it before any long run.
- **Wrong clock:** this would create look-ahead. Tests 4, 7 and 8 of task 2.5 are the gate.
- **Global effect:** after release, every backtest of any symbol whose window starts after the symbol's first 1m bar fills on 1m bars. Phase 5 tells the owner.
- **Rollback:** revert the commit. Stored runs are not affected.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.
