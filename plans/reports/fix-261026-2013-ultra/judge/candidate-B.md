## Fix plan — finest-interval gate + open-price gap rule (signal bar deferred)

**1. Chosen repair**

Option (c) plus an open-price gap rule. The broker remembers, per symbol, the shortest interval it has seen, and any bar of a longer interval returns at the top of `_on_bar_completed` before it can trigger anything, so SL/TP exits and pending LIMIT fills both run only on the finest interval. This targets cause 1 directly: higher-interval bars start before entries made inside them. Live publishes 1m first on every tick, so a 15m entry is next checked against the 1m bar that starts at its close; backtests replay one interval, so they are unchanged; no clock is read, so feed delay cannot affect it. For cause 2, `_check_sl_tp` also receives `event.open` and, when the open is already past a level, fills at the open.

**2. Answers**

- **Q1:** a bar may fill/trigger only if `INTERVAL_SECONDS[event.interval] <= self._finest_secs.get(event.symbol, secs)`, then store it. Per-symbol entry, so pooled BTC 1m and ETH 15m don't interfere. No clock. No-op in backtests.
- **Q2:** Not in this change. Live strategies coarser than 1m are already protected (the last 1m bar of the tick is processed before the signal bar is published). Only 1m strategies and all backtests still check the signal bar. Closing that needs to know which bar is being dispatched — a new order field or event-bus ordering change — more code than it replaces, so ask first. Backtest results unchanged.
- **Q3:** Yes, same guard (it sits above `_fill_pending_on_bar`). No gap rule: gapping through a limit can only improve the price, so filling at the limit stays conservative. STOP_* orders share this path and still need real stop logic (existing TODO).
- **Q4:** LONG (bid bars), `o = open`: if `tp` and `o >= tp` → exit at `o` (TP); elif `sl` and `low <= sl` → exit at `min(sl, o)` (SL); elif `tp` and `high >= tp` → `tp`. SHORT, `o = open + spread` (ask): if `tp` and `o <= tp` → `o`; elif `sl` and `high + spread >= sl` → `max(sl, o)`; elif `tp` and `low + spread <= tp` → `tp`. A TP already passed at the open wins (open is the first price); intra-bar SL still beats TP; open cannot be past both. Slippage applied last, always adverse.

**3. Changes** (`paper_broker_adapter.py`)

1. Import `INTERVAL_SECONDS` from `pocketquant.core.common.constants` (string-keyed, matches `event.interval`).
2. `__init__`: `self._finest_secs: dict[str, int] = {}` with a one-line comment.
3. Top of `_on_bar_completed`, before `_current_prices`:
   ```python
   # Only the finest interval seen fills or exits: coarser bars start before entries inside them.
   secs = INTERVAL_SECONDS[event.interval]
   if secs > self._finest_secs.get(event.symbol, secs):
       return
   self._finest_secs[event.symbol] = secs
   ```
4. `_check_sl_tp(self, pos, bar_open, bar_high, bar_low)` per Q4; caller passes `event.open, event.high, event.low`.
5. `reset()` adds `self._finest_secs.clear()` (real caller `backtest_app_service.py:109`; without it a 1m run then a 4h run on one broker skips every bar).
6. Update the class docstring "SL fires first" line for the gap rule; one line on finest interval in the `_on_bar_completed` docstring.

Estimate: ~+16 / −5 src, ~+120 tests.

**4. Behaviour changes**

- Live paper: exits and LIMIT fills only on 1m; gap exits fill at open (2026-10-25 ES stop ≈ 7690 × 1.00005 instead of 7681.31).
- Backtests: interval rule changes nothing; bars that open past a level fill at the open (intended). Existing fixtures build `open` at midpoint or inside the range (e.g. `test_long_sl_fills_when_bar_low_below_sl` open 98 == SL → same price). Expect no existing expectation to change.
- Unchanged: intra-bar fills at the level, SL beats TP intra-bar, entries, commission, MTM, Exness.

**5. Risks**

Startup: a position exists only after a signal, and the tick's 1m is published first; paper positions are in-memory. Coarse first: treated as finest until a finer bar arrives, harmless. Weekend: reopen 1m fills at open; 1d/1w on the same tick skipped. Unknown interval → `KeyError` (enum keeps 7 keys). 1m signal bar still checked (Q2).

**6. Verification**

`test_paper_broker_sl_tp_fill.py` (`_bar_event` gains `interval=`, `open=`):
- `test_coarser_bar_ignored_after_finer_seen`: 1m (100.5/99.5), LONG SL 98/TP 104, 4h (h103 l97) → open; 1m l97.5 → closes at 98. (AC1)
- `test_coarser_bar_does_not_fill_pending_limit`: 1m seed, BUY LIMIT 95, 4h l94 → pending; 1m l94.5 → fills 95.
- `test_single_coarse_interval_still_triggers`: only 4h bars, SL fires (backtests at 4h unaffected).
- `test_long_sl_gap_fills_at_open` (o96 h97 l95, slip 0.001 → 96×0.999), `test_long_tp_gap_fills_at_open` (o106), `test_tp_gap_beats_sl_in_same_bar` (o105 h105 l97 → TP 105).
- `test_es_short_sl_gap_reopen`: SHORT SL 7680.92, slip 0.00005, o7690 h7698.5 → ≈7690.3845.
`test_paper_broker_spread.py` (`_bar` gains `open=`): `test_short_sl_gap_fills_at_ask_open` (spread 0.4, SL 101, o101.2 → 101.6), `test_short_tp_gap_fills_at_ask_open` (TP 99, o98.2 → 98.6). Existing level-fill tests cover open-inside-range. (AC2)
Run broker suite (113 + new), `tests/backtest_test` with no expectation edited (AC3), ruff + quality gate from `docs/code-standards.md` (AC4).

Status: DONE_WITH_CONCERNS
