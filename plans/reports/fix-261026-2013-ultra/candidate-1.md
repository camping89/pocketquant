## Fix plan — candidate #1: finest interval + skip each order's own bar (broker-clock cutoff) + open-first gap rule

**1. Chosen repair**

Per symbol, the broker remembers the smallest interval received. A coarser bar does nothing in the broker (no SL/TP, no pending LIMIT fill, no MTM). The broker also stamps the time it finishes each bar for a symbol; an order or position created after that stamp is not checked on the next bar, because that bar's range is older than it. SL/TP reads the bar `open`: if already past a level, the exit fills at the open. Neither rule compares feed time with wall-clock, so the ~10-minute TradingView delay does not matter. Defect 2 comes from never reading `open`; the new rule reads it.

**2. Answers**

- **Q1:** A bar is used only if `INTERVAL_SECONDS[event.interval] == _finest_secs[symbol]`; both new dicts keyed by symbol (pooled broker OK). Live: 1m published first and the bus awaits handlers in order, so finest is 1m. Backtest: one interval, nothing changes. A position is also skipped while `pos.opened_at > _last_bar_at[symbol]` (no skip if no stamp yet). Both sides from `get_current_time()` (wall-clock live, sim time backtest).
- **Q2:** Yes, live and backtest, same rule. Backtest: `opened_at` on the signal bar is `bar_start N` > stamp from bar N−1, so the signal bar is skipped; bar N+1 checks. Live 15m: the coarse 15m handler still stamps, so the next 1m checks. Live 1m: opened after the previous stamp → signal bar skipped. Deliberate backtest changes: SL/TP no longer fires on the signal bar; a pending LIMIT no longer fills on its submit bar; a position opened by a LIMIT fill is not SL/TP-checked on its fill bar.
- **Q3:** Same finest rule plus freshness `pending.submitted_at > cutoff`. No LIMIT gap rule: filling at the limit when the open is past it is pessimistic, never flatters.
- **Q4:** Open before intrabar range. LONG (SELL at bid): `open <= sl` → open (SL); elif `open >= tp` → open (TP); elif `low <= sl` → `sl`; elif `high >= tp` → `tp`. SHORT (BUY at ask): `ask_open = open + spread`; `ask_open >= sl` → ask_open (SL); elif `ask_open <= tp` → ask_open (TP); else existing intrabar checks at the level. A level the open already passed wins; only intrabar keeps SL-first. Slippage stays in `_fire_synthetic_exit`.

**3. Changes** (`paper_broker_adapter.py`)

1. Import `INTERVAL_SECONDS` from `pocketquant.core.common.constants`.
2. `__init__`: `self._finest_secs: dict[str, int] = {}`, `self._last_bar_at: dict[str, datetime] = {}`; clear both in `reset()`.
3. `_on_bar_completed`, after the current-price line:
   ```python
   sym = event.symbol
   secs = INTERVAL_SECONDS[event.interval]
   finest = self._finest_secs[sym] = min(secs, self._finest_secs.get(sym, secs))
   if secs > finest:  # coarser range includes pre-entry prices
       self._last_bar_at[sym] = get_current_time()
       return
   cutoff = self._last_bar_at.get(sym)
   ```
   SL/TP loop: `if cutoff is not None and pos.opened_at > cutoff: continue`; call `self._check_sl_tp(pos, event)`. Last line of handler: `self._last_bar_at[sym] = get_current_time()` (after fills, so a position filled inside this handler is checked on the next bar).
4. `_fill_pending_on_bar`: `cutoff = self._last_bar_at.get(event.symbol)`; skip when `cutoff is not None and pending.submitted_at > cutoff`.
5. `_check_sl_tp(self, pos, bar: BarCompletedEvent)` per Q4.
6. Update class and handler docstrings; drop "entries may open the very position that the same bar's SL/TP would then close".

Size: ~+24 / −6 src, ~+120 tests.

**4. Behaviour changes**

- Live paper: 5m–1w bars never fill or close anything; signal bar never checked; a manual order placed between bars skips the next bar; gap opens fill at the open (ES reopen → 7690 × 1.00005 = 7690.38).
- Backtests: the three Q2 changes plus gap fills at open. No existing unit test changes expectation (each opens before any bar → cutoff None; `open=(h+l)/2` inside range or equal to the level, e.g. SL 98 with 99/97 → open 98). `test_hitnrun2_backtest` may move a TP exit from the signal bar to the recovery bar; its assertions (>1 trades, flat at end) hold.
- Unchanged: intrabar level fills, SL-first intrabar, MARKET fills, entry spread, commission, Exness, schemas.

**5. Risks**

Feed delay: none. Pooled broker: per symbol. Startup: first bar no cutoff; live paper positions in memory. Weekend: Friday bar stamped; Sunday first bar gap-fills at open. Both levels past: impossible from the open. SHORT spread on open in gap fills only. Unknown interval → `KeyError` (replay validates via `Interval(config.interval)`). Open concern: skipping SL/TP on a LIMIT fill bar is slightly optimistic for SL.

**6. Verification**

`test_paper_broker_sl_tp_fill.py`; `_bar_event` gets optional `interval`, `bar_start`, `open`; tests pin the clock with `set_simulation_time`, autouse fixture clears it.
- `test_coarser_bar_never_closes_position_opened_inside_it`: 1m neutral T0, BUY sl 98/tp 104 at T1, 4h (97–105) → open; 1m T2 (low 97.5, open 99) → closes at 98. (AC1)
- `test_signal_bar_skipped_then_next_bar_closes`; `test_finest_interval_is_per_symbol` (only 15m still gets SL); `test_pending_limit_ignores_coarser_bar_and_own_bar`.
- `test_gap_past_sl_fills_at_open` (LONG/SHORT, spread 0.5, slip 0.001; SHORT sl 102 open 103 → 103.5×1.001); `test_gap_past_tp_fills_at_open` incl. open past TP with low crossing SL → TP at open; `test_es_reopen_gap_short_sl`; `test_open_inside_range_fills_at_level`. (AC2)
Run broker suite and `tests/backtest_test` with no edits to existing tests (AC3); ruff + quality gate (AC4).

Status: DONE_WITH_CONCERNS — could not run tests read-only; "no existing test changes" is from reading fixtures. Backtests change on purpose in three named ways; the user should accept them, especially skipping SL/TP on a LIMIT fill bar.
