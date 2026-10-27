## Fix plan — candidate #2: per-symbol "fresh bar" gate on bar_start + open-first gap rule

**1. Chosen repair**

The broker acts only on new price ranges. It keeps one value per symbol: the `bar_start` of the last bar it acted on. A bar whose `bar_start` is not later than that only re-covers prices already read, so it cannot fill a pending LIMIT or trigger SL/TP (a coarser interval closing on the same tick, the Friday 4h/1d bars arriving at the Sunday reopen, duplicate deliveries). This targets Defect 1's cause: mixing intervals means reading the same prices twice. No interval on orders, no wall clock, no per-position state; immune to feed delay, per symbol in a pooled broker, and backtests unchanged because replay starts strictly increase. For Defect 2, the bar `open` is checked before the levels, so a gap fills at the first traded price.

**2. Answers**

- **Q1:** `fresh = event.bar_start is None or last is None or event.bar_start > last`, `last = self._last_bar_start.get(event.symbol)`; store the start when fresh. Option (c) derived from timestamps. Live: 1m is processed first on every tick, so every coarser bar is stale. Backtest: every bar fresh. MTM still runs on every bar.
- **Q2:** Partly. Live 15m+ strategies: signal bar is stale, cannot close the position (the prod case). Live 1m strategies and every backtest: signal bar still checked, as today. The broker cannot tell "opened while this bar was dispatched" from "opened between bars" without an order field; backtests stay identical; known gap.
- **Q3:** Yes, `_fill_pending_on_bar` uses the same `fresh` gate. Gap rule: BUY fills at `min(open, limit)`, SELL at `max(open, limit)`, then slippage. LIMIT fills still ignore spread.
- **Q4:** Open first, then levels; SL beats TP at each step. `base` is the pre-slippage price.
  - LONG: `open <= sl` → (open, SL); elif `open >= tp` → (open, TP); elif `low <= sl` → (sl, SL); elif `high >= tp` → (tp, TP).
  - SHORT: `ask_open = open + spread`; `ask_open >= sl` → (ask_open, SL); elif `ask_open <= tp` → (ask_open, TP); then the two existing `high/low + spread` checks fill at the level.
  - Fill `_apply_slippage(base, exit_side)`; synthetic order `price` is `base`.

**3. Changes** (`paper_broker_adapter.py`)

1. `__init__`: `self._last_bar_start: dict[str, datetime] = {}` ("a bar starting at or before this only re-covers prices already acted on"); clear in `reset()` (called by `BacktestAppService` `:109`).
2. `_on_bar_completed`: compute `fresh`, store when fresh; wrap `_fill_pending_on_bar(event)`, the SL/TP scan and synthetic exits in `if fresh:`. `_current_prices` update and MTM loop stay unconditional.
3. `_check_sl_tp(self, pos, bar: BarCompletedEvent)`: four ordered checks per side (one caller).
4. `_fill_pending_on_bar`: `base = min(event.open, limit)` for BUY else `max(...)`; `_apply_slippage(base, side)`.
5. Docstrings: open first, then SL before TP; stale bars ignored.

Estimate: ~+22 / −6 src, ~130 test lines.

**4. Behaviour changes**

- Live paper: SL/TP and LIMIT fills react only to the first (finest) stream per symbol, in practice 1m. 4h/1d/1w bars, the 15m signal bar and Friday bars delivered at the reopen are ignored. Gapped stops fill near the open (prod ≈ 7690 not 7681.31). Favourable gaps fill at the better open.
- Backtests: identical except bars that open past SL, TP or a pending limit. Checked every existing bar-feeding test: helpers use `open=(high+low)/2` and no case opens past a level (e.g. SHORT sl=101, spread 0.4, high 100.7 → ask_open 100.5 inside). Repeated `_T0` bars only in `test_fill_clears_state...` where the second bar should do nothing. Persistence test uses increasing starts. Expect no expectation change.
- Unchanged: MARKET and immediate-LIMIT fills, commission, futures accounting, MTM, Exness, schemas.

**5. Risks**

Feed delay: none (bar timestamps only). Pooled broker: per symbol, interval-agnostic. Startup: no value → first bar acts; live 1m first. Weekend: Friday 4h starts before the last 1m start → stale; Sunday first 1m acts, gap handled. SL and TP both past at open: not with sane levels; SL wins. Assumes nested minute-aligned grids (holds 1m..1w). Remaining gaps: live 1m strategies and backtests still check the signal bar; a pyramided add can be closed by the bar being dispatched; an event with default `open=0.0` would fill at 0 (every producer sets `open`).

**6. Verification**

`test_paper_broker_sl_tp_fill.py` (`_bar_event` gets `open`, `bar_start`, `interval` kwargs):
- `test_coarser_bar_covering_entry_does_not_close_position`: 1m at T0+239m, BUY 100 SL 98, 4h start T0 low 97 → open; 1m at T0+240m open 99 low 97.5 → closes at 98. (AC1)
- `test_pending_limit_ignores_coarser_bar`: same with BUY LIMIT 90; fills on the later 1m.
- `test_gap_past_level_fills_at_open` parametrized (slip 0.001, spread 0.4): LONG SL open 96 → 96(1−s); LONG TP open 106 → 106(1−s); SHORT SL open 103 → 103.4(1+s); SHORT TP open 95 → 95.4(1+s).
- `test_open_inside_range_fills_at_level`: open 99, low 97 → 98.
- `test_gap_past_tp_beats_intrabar_sl`: open 106, low 97 → TP 106.
- `test_pending_limit_gap_fills_at_open`: BUY LIMIT 90, open 88 → 88. (AC2)
Run broker suite + `tests/backtest_test` with no assertion edits (AC3); full `uv run pytest -q`; ruff check, `ruff format --check`, quality gate (AC4).

Status: DONE_WITH_CONCERNS — live 1m strategies and every backtest still check the signal bar (Q2); fixing it needs to know at order time which bar is being dispatched.
