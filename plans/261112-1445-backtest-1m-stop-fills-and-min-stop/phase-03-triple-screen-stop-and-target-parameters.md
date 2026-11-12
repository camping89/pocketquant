---
phase: 3
title: "Triple Screen stop and target parameters"
status: done
priority: P1
effort: "5h"
dependencies: [2]
---

# Phase 3: Triple Screen stop and target parameters

## Goal
- **Rename:** `stop_lookback` becomes `stoploss_lookback`, counted in bars of the next higher timeframe.
- **Add:** `takeprofit_lookback`, `entry_buffer_atr`, `stoploss_buffer_atr` and `min_stop_atr`.
- **Defaults:** the new parameters default to off. Golden check G-b proves that the rename keeps the stored run's trades.

## Facts (verified 2026-11-12)
- `TripleScreenStrategyService` is in `src/pocketquant/core/domain/strategy/services/triple_screen_strategy_service.py`.
  - `DEFAULTS` is at `:25-34`, with `"stop_lookback": 5`.
  - The constructor reads parameters with `p.get(...)` (`:36-47`).
  - Today `stop_lookback` must be at least 1 (`:54-62`).
  - The window is `self._recent = deque(maxlen=self.stop_lookback)` (`:67`), appended once per entry bar (`on_bar_completed`, `:99`).
  - The swing stop is `min` or `max` over `self._recent` (`:121-128`), and the TP is `price ± risk_reward x risk`.
- **Context timing:** the strategy reads higher-timeframe bars that closed before the start of the entry bar (`strategy_app_service.py`, `_context_at`). `bar["context"][top]` is the list of closed top-interval bars.
- **Parameter checks:**
  - An unknown parameter key is rejected on submit (`core/domain/strategy/services/__init__.py:50-52`).
  - A default typed `int` rejects a float value, and a default typed `float` accepts an int or a float (`_type_matches`, `:19-24`). NaN and inf pass that check.
- **Ratio:** `INTERVAL_SECONDS` is in `src/pocketquant/core/common/constants.py:45`. The ratio of middle to entry seconds is always a whole number (`services/__init__.py:44`).
- **Live warm-up** replays 500 entry bars (`_WARMUP_BARS`, `engine/strategy/strategy_app_service.py:55`). The domain package may not import from `engine` (import linter).
- **Tests:** `tests/core_test/unit/domain/strategy/test_triple_screen.py` (unit) and `tests/backtest_test/engine/test_triple_screen_backtest.py` (engine). No test mentions `stop_lookback`.
- **Stored data:** 47 stored backtest runs carry `stop_lookback`; they stay as records and are never re-validated (`backtest_execution_service.py:104`). At 14:32 on 2026-11-12, no subscription carried it.

## Definitions
`ratio` = seconds(middle) / seconds(entry), which is 4 for `15m,1h,4h`. `ATR` = Wilder ATR(14) on the closed top-interval context bars (`bar["context"][top]`). `high` and `low` are those of the entry bar that just closed.

| Step | Long | Short |
|---|---|---|
| 1. Entry, stop order | `high + entry_buffer_atr x ATR` | `low - entry_buffer_atr x ATR` |
| 2. Swing stop | lowest low of the last `stoploss_lookback x ratio` closed entry bars, minus `stoploss_buffer_atr x ATR` | highest high of those bars, plus `stoploss_buffer_atr x ATR` |
| 3. Minimum stop | `sl = min(step 2, entry - min_stop_atr x ATR)` | `sl = max(step 2, entry + min_stop_atr x ATR)` |
| 4. Risk | `entry - sl` | `sl - entry` |
| 5. TP, `exit_mode=sl_tp` only | `max(highest high of the last takeprofit_lookback x ratio entry bars, entry + risk_reward x risk)` | `min(lowest low of those bars, entry - risk_reward x risk)` |

- The windows include the signal bar, as today.
- **Market entry:** the entry is the close. The entry offset does not apply.
- **`exit_mode=strategy`:** no TP. The tide flip exits, and `takeprofit_lookback` is ignored.
- **`takeprofit_lookback=0`:** gives today's TP exactly.
- **ATR warm-up:** while ATR is undefined (fewer than 15 top bars) and any ATR parameter is non-zero, the decision is `skip` with reason `top interval warming up`.

## Files to Create / Modify
- Modify: `src/pocketquant/core/domain/strategy/services/triple_screen_strategy_service.py`.
- Modify: `tests/core_test/unit/domain/strategy/test_triple_screen.py`.
- Modify: `docs/governance/strategy-assessment-rubric.md` (the G2 row and its decision text, and the trial count).

## Tasks

### Task 3.1 — Parameters and validation
- **Goal:** the new parameter set exists, with exact bounds, and `stop_lookback` is gone.
- **Target files:** `triple_screen_strategy_service.py`: `DEFAULTS` and `__init__`.
- **Steps:**
  1. In `DEFAULTS`, replace `"stop_lookback": 5` with `"stoploss_lookback": 2`. Add `"takeprofit_lookback": 0`, `"entry_buffer_atr": 0.0`, `"stoploss_buffer_atr": 0.0` and `"min_stop_atr": 0.0`. The floats must be written `0.0`.
  2. In `__init__`, read the five values with `p.get`. Cast the three ATR values with `float(...)`.
  3. Validate:
     - `stoploss_lookback >= 1`; put it in the existing `counts` tuple and update that error message;
     - `takeprofit_lookback >= 0`;
     - each ATR value satisfies `math.isfinite(v) and v >= 0`;
     - compute `ratio = INTERVAL_SECONDS[middle] // INTERVAL_SECONDS[entry]` from `config.intervals`, and require `max(stoploss_lookback, takeprofit_lookback) * ratio <= 500`.
     Raise `ValueError` with a message naming the parameter. Put a `#` comment above the 500 cap: live warm-up replays 500 entry bars (`_WARMUP_BARS` in `engine/strategy/strategy_app_service.py`).
  4. Size the window `deque(maxlen=max(stoploss_lookback, takeprofit_lookback) * ratio)`. Keep the attribute name `self._recent`.
  5. Search `grep -rn "stop_lookback" src tests web/src docs`. The only remaining hits must be in plan or report files.
- **Success criteria:** the code holds no `stop_lookback`, and the bounds are as listed.
- **Verify:** `grep -rn "stop_lookback" src tests web/src` prints nothing (exit code 1).

### Task 3.2 — The five steps
- **Goal:** entries, stops and TPs follow the Definitions table.
- **Target files:** `triple_screen_strategy_service.py`: `on_bar_completed` and one new private method `_atr(self, top_bars) -> float | None` (Wilder ATR(14)).
- **Steps:**
  1. Add `_atr` (Wilder smoothing, period 14). It returns `None` when there are fewer than 15 bars.
  2. In `on_bar_completed`, after the existing warm-up checks, compute `atr = self._atr(bar["context"][top])` once. If `atr is None` and any of the three ATR parameters is non-zero, the decision is `skip`, `top interval warming up`.
  3. Use `sl_bars = list(self._recent)[-stoploss_lookback * ratio:]` for step 2 and `tp_bars = list(self._recent)[-takeprofit_lookback * ratio:]` for step 5, the latter only when `takeprofit_lookback > 0`. Treat `atr` as `0.0` when every ATR parameter is 0.
  4. Implement steps 1 to 5 exactly as in the table, for long and short. Keep the existing `risk <= 0` skip.
  5. Add `atr`, `swing_stop`, `sl` and `tp` to the snapshot readings, next to the existing ones (see `test_the_snapshot_reports_three_readings_and_a_decision`).
- **Success criteria:** the table is implemented. With every new parameter at its default and `stoploss_lookback x ratio` equal to the old `stop_lookback`, the result equals today's.
- **Verify:** `uv run pytest tests/core_test/unit/domain/strategy/test_triple_screen.py -q` exits 0. The existing tests must still pass. Change a test only to rename `stop_lookback`; never change an expected value.
- **Deviation 2026-11-12 (kongming counsel):** step 5 conflicts with `test_the_snapshot_reports_three_readings_and_a_decision`, which pins exactly three readings, and the engine stores only `readings` and `decision`. The four new rows are appended with `ok: None`, and that test's two list assertions are scoped to `readings[:3]` with their literals unchanged. The new rows are checked inside the task 3.3 tests, so the count stays at +13. The long name of test 1 carries `# noqa: E501`.

### Task 3.3 — Tests
- **Goal:** each rule is pinned by a test named after it.
- **Target files:** `tests/core_test/unit/domain/strategy/test_triple_screen.py`.
- **Steps:** add these tests, in the file's existing style:
  1. `test_the_stoploss_window_spans_lookback_times_ratio_entry_bars_including_the_signal_bar`
  2. `test_the_entry_buffer_moves_the_stop_order_by_x_atr_on_both_sides`
  3. `test_the_stoploss_buffer_moves_the_swing_stop_outward_by_x_atr_on_both_sides`
  4. `test_the_minimum_stop_widens_a_closer_stop_and_keeps_a_farther_one`
  5. `test_the_take_profit_is_the_farther_of_the_swing_level_and_the_risk_reward_floor`
  6. `test_takeprofit_lookback_is_ignored_in_strategy_exit_mode`
  7. `test_atr_uses_only_closed_top_interval_bars`
  8. `test_atr_parameters_skip_while_atr_is_warming_up`
  9. `test_the_old_stop_lookback_key_is_rejected_on_submit`, through `check_strategy_inputs`
  10. `test_a_negative_nan_or_infinite_atr_parameter_is_rejected`
  11. `test_stoploss_lookback_zero_is_rejected`
  12. `test_a_lookback_beyond_the_500_bar_warm_up_is_rejected`
  13. `test_a_float_value_is_accepted_for_each_atr_parameter`
- **Success criteria:** all new tests pass.
- **Verify:** `uv run pytest tests/core_test/unit/domain/strategy/test_triple_screen.py tests/backtest_test/engine/test_triple_screen_backtest.py -q` exits 0. The new test count is 13 more than before task 3.3.

### Task 3.4 — Rubric G2 and trial count
- **Goal:** the rubric matches owner decisions 4, 8 and 9.
- **Target files:** `docs/governance/strategy-assessment-rubric.md`.
- **Steps:**
  1. Change the G2 row so that it passes on in-sample t >= 3.0. The Deflated Sharpe Ratio is reported and does not gate.
  2. In the G2 decision text, add one sentence: in-sample is the whole window that informed the configuration's selection.
  3. Set the recorded trial count to 224 if the rubric records one. If it does not, change nothing for this step.
- **Success criteria:** the G2 row and text say exactly that.
- **Verify:** `grep -n "3.0" docs/governance/strategy-assessment-rubric.md` shows the G2 row.

### Task 3.5 — Stored subscriptions (read-only)
- **Goal:** know whether any stored subscription still carries the old key.
- **Target files:** none.
- **Steps:**
  1. On prod, read-only: `db.subscriptions.countDocuments({"parameters.stop_lookback": {$exists: true}})` in database `pocketquant`.
- **Success criteria:** the count is 0.
- **Verify:** the printed count is `0`. If it is not 0, stop and ask the owner which integer `stoploss_lookback` each listed subscription should get. List the subscription ids, broker and state, never secret fields. Do not write a migration.

### Task 3.6 — Golden check G-b and quality gates
- **Goal:** the rename keeps `01a1c980`'s trades, and nothing else broke.
- **Target files:** `.cache/golden/config.json`, `.cache/golden/gb.csv`.
- **Steps:**
  1. Repeat phase 1 task 1.1 (target guard).
  2. Copy `.cache/golden/config.json` to `.cache/golden/config-gb.json`. Replace `"stop_lookback": 80` with `"stoploss_lookback": 20`.
  3. Run `.cache/golden/b0.py` with that config and output `.cache/golden/gb.csv`.
  4. Compare `gb.csv` with `b0.csv` on all columns, in order.
  5. Run `uv run pytest tests/ -q`, `uv run lint-imports`, `uv run python scripts/code_metrics.py --ratchet` and `uv run pyright src/pocketquant/core/domain/strategy`.
- **Success criteria:** identical trade lists, and every gate passes.
- **Verify:**
  - The comparison prints `0` differing rows, and both files have 1 991 rows.
  - pytest has no failures other than the known Windows tz tests (4 failed plus 4 errors in `test_utc_runtime_guard.py` and `test_cron_trigger_timezone.py`).
  - `lint-imports` and the ratchet exit 0, and pyright reports `0 errors`.

### Task 3.7 — Commit
- **Goal:** one focused commit on `develop`.
- **Steps:**
  1. `git add` the three files of this phase only.
  2. Commit `feat(strategy): triple screen higher-timeframe stop and target lookbacks, atr offsets and minimum stop`.
- **Success criteria:** the commit holds only those files.
- **Verify:** `git log -1 --stat` lists exactly those three files.

## Risk and rollback
- This changes strategy logic, which the owner approved on 2026-11-12.
- The default `stoploss_lookback=2` changes running Triple Screen subscriptions, paper and Exness broker alike, from 5 to 8 entry bars of lookback (owner decision 3). Phase 5 tells the owner.
- `stoploss_buffer_atr` is used only by the informational trials of phase 4 (owner decision 8).
- Rollback: revert the commit. No stored data is changed in this phase.

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
