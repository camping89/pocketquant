## Fix plan — candidate #4: finest-interval gate + same-bar skip + open-aware fills

**1. Chosen repair**

The broker fills/exits only on bars of the finest interval it has seen per symbol (a tiny per-symbol map `_finest_interval_s`), which removes the 4h/15m ranges that contain pre-entry prices without any clock comparison, so feed delay is irrelevant. A second rule skips any position opened (or LIMIT submitted) during the dispatch of the current bar (`opened_at >= event.occurred_at`), and replay stamps `occurred_at=bar_time` so live and backtest share one rule. Exits and LIMIT fills price from the bar `open` when it is already past the level. Each piece maps one-to-one to a named cause in the packet; nothing new reaches persistence, orders or Exness.

**2. Answers**

- **Q1:** (c) + the `occurred_at` rule. (a) fails: live `opened_at` is wall-clock ~10 min ahead of `bar_start`, so it would skip real post-entry bars. (b) needs plumbing through orders/positions and still checks at strategy resolution. (c) keeps backtests identical (one interval) and works for the pooled broker because it is keyed by symbol.
- **Q2:** Yes, live and backtest. Rule: `pos.opened_at >= event.occurred_at` → skip that position for that bar. Live: covers a 1m strategy's signal bar (15m is already covered by Q1). Backtest: changes only trades whose own signal bar touched SL/TP; that exit moves to a later bar (today it is look-ahead bias).
- **Q3:** Yes, same finest gate, plus skip `pending.submitted_at >= event.occurred_at`. Gap: BUY LIMIT fills at `min(limit, open)`, SELL LIMIT at `max(limit, open)`, then slippage. LIMIT spread handling unchanged.
- **Q4:** Exit-side prices: `off = spread if SHORT else 0`; `o=open+off, hi=high+off, lo=low+off`.
  - LONG: `o >= tp` → TP at `o`; elif `lo <= sl` → SL at `min(sl, o)`; elif `hi >= tp` → TP at `tp`.
  - SHORT: `o <= tp` → TP at `o`; elif `hi >= sl` → SL at `max(sl, o)`; elif `lo <= tp` → TP at `tp`.
  Open can be past only one level, so the favourable-gap check goes first; intra-bar, SL still wins. `_fire_synthetic_exit` applies slippage as today.

**3. Changes** (`paper_broker_adapter.py` unless noted)

1. Import `INTERVAL_SECONDS` from `core.domain.shared.value_objects`. `__init__`: `self._finest_interval_s: dict[str, int] = {}`; `reset()` clears it.
2. `_on_bar_completed`, after the `_current_prices` update:
   ```python
   secs = INTERVAL_SECONDS[event.interval]
   finest = min(secs, self._finest_interval_s.get(event.symbol, secs))
   self._finest_interval_s[event.symbol] = finest
   if secs > finest:
       return  # coarser bar spans pre-entry prices
   ```
   In the scan add `if pos.opened_at >= event.occurred_at: continue`; call `self._check_sl_tp(pos, event)`. Update docstring and the comment in `connect`.
3. `_fill_pending_on_bar`: skip `pending.submitted_at >= event.occurred_at`; store `(pending, base)` with `base = min(limit, event.open)` for BUY / `max(...)` for SELL; `_apply_slippage(base, side)`.
4. `_check_sl_tp(self, pos, bar: BarCompletedEvent)` rewritten per Q4 (single caller).
5. `historical_replay_app_service.py`: `BarCompletedEvent(..., occurred_at=bar_time)`.

Size: ~+22 / −12 src, ~110 test lines.

**4. Behaviour changes**

- Live paper: SL/TP and LIMIT fills on 1m only; signal bar never closes its own position; gaps fill at open (CME reopen ≈ 7690.4 not 7681.31). MTM still runs on every finest bar (coarse closes on the same tick are equal).
- Backtests: identical for non-gap, non-signal-bar bars. Changed: gap-open exits, signal-bar exits, and LIMITs that filled against their own submit bar (only `entry_type="limit"`; default market). Possible expectation changes: `test_engulfing_backtest.py`, `test_engulfing_pullback30_touch_backtest.py`, `test_hitnrun2_backtest.py`, `test_r7_worked_example_defaults.py` — diffs must be traced to one of the three rules.
- Unit broker tests: expected unchanged (helper bars open at mid or exactly at SL; orders are submitted before their bar event is built).

**5. Risks**

Feed delay: no time comparison in Q1; Q2 compares two wall-clock stamps (live) or two sim stamps (backtest). Pooled broker: per-symbol map; every symbol gets 1m (1m published first on any closing tick). Startup: first bar coarse → self-heals at first 1m (≤1 min). Weekend gap: reopen 1m fills at open. Both levels past: impossible at open; intra-bar SL wins. SHORT spread: gap fill `open+spread`; intra-bar SL fill stays at the level (as today). Slippage once. `>=` tie: Python 3.13+ clocks precise; new tests set `occurred_at` explicitly. LIMIT entries: no longer closed by their own fill bar. Unknown interval → `KeyError`; all 10 producers use valid values.

**6. Verification**

New tests in `test_paper_broker_sl_tp_fill.py` (`_bar_event` gains `interval`, `open`, `bar_start` kwargs):
- `test_coarse_bar_predating_entry_does_not_close`: 1m (99/97), LONG SL 98 at 100, 4h bar low 95, 1m low 97.5 → stays open, closes on the 1m.
- `test_signal_bar_does_not_close_own_position`: a handler subscribed before the broker opens during a 1m bar with low < SL → stays open; next bar closes.
- `test_long_sl_gap_fills_at_open` (open 96, SL 98); `test_short_sl_gap_fills_at_open_plus_spread` (spread 0.4, open 103, SL 102 → 103.4×(1+slip)).
- `test_long_tp_gap_fills_at_open`, `test_short_tp_gap_fills_at_open`.
- `test_open_inside_range_fills_at_level` (open 99, low 97, SL 98 → 98).
- `test_limit_gap_fills_at_open`, `test_limit_not_filled_by_submit_bar`.
Run `uv run pytest -q tests/core_test/infra/brokers`, `uv run pytest -q tests/backtest_test`, `uv run ruff check src tests scripts`, repo quality gate. AC1 coarse test; AC2 gap tests; AC3 suites with justified diffs; AC4 ruff/gate.

Status: DONE_WITH_CONCERNS — could not run suites read-only; which backtest strategy tests shift under the signal-bar and LIMIT rules is unknown.
