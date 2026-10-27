## Fix plan — candidate #3: finest interval + occurred_at freshness guard (replay-stamped) + open-first gap rule

### 1. Chosen repair

The broker acts only on the finest bar stream seen per symbol and ignores coarser bars entirely, which removes Defect 1's cause (a coarse bar whose range starts before the entry). A second guard: a bar may act only on positions and orders that existed before the bar was published (`event.occurred_at`). Replay stamps `occurred_at = bar_time`, so the guard behaves the same live and in backtests. For Defect 2, `_check_sl_tp` reads `event.open`; a level the bar opens past fills at the open (ask open for SHORT). No new order/position field, no schema change.

### 2. Answers

**Q1:** Option (c), `self._finest_interval_s: dict[str, int]`. (a) fails live: `opened_at` is wall-clock and the feed lags ~10 min, so ~10 min of real 1m bars would be skipped. (b) needs interval plumbing through `OrderAggregate`, persistence and the strategy service. Live 1m is published first on a tick, so 1m drives every symbol in a pooled broker; backtest has one interval, filter does nothing.

**Q2:** Yes, live and backtest. Positions with `opened_at >= event.occurred_at` are snapshotted before pending fills and skipped for this bar. Live: 50 ms fill delay makes opened time later than publish time. Backtest: replay sets `occurred_at = bar_time = opened_at`. A position opened by a pending LIMIT on this bar is still checked, as today.

**Q3:** Same finest rule, plus `pending.submitted_at >= event.occurred_at → skip`. No LIMIT gap rule: filling at the limit is conservative.

**Q4:** `o = event.open`, `s = self._spread`, slippage afterwards in `_fire_synthetic_exit`. Open decides first; intrabar SL still wins.
```
LONG:  tp and o >= tp        -> (o, SELL, TP)
       sl and low <= sl      -> (min(o, sl), SELL, SL)
       tp and high >= tp     -> (tp, SELL, TP)
SHORT: a = o + s
       tp and a <= tp        -> (a, BUY, TP)
       sl and high + s >= sl -> (max(a, sl), BUY, SL)
       tp and low + s <= tp  -> (tp, BUY, TP)
```

### 3. Changes

`paper_broker_adapter.py`:
1. Import `Interval`, `INTERVAL_SECONDS` from `core.domain.shared`.
2. `__init__`: `self._finest_interval_s = {}`; clear in `reset()` (`BacktestAppService.run` calls it).
3. Top of `_on_bar_completed`: `secs = INTERVAL_SECONDS[Interval(event.interval)]`; `finest = min(secs, self._finest_interval_s.get(event.symbol, secs))`; store; `if secs > finest: return`; then `fresh = {p.id for p in self._positions.values() if p.opened_at >= event.occurred_at}` before `_fill_pending_on_bar`.
4. SL/TP loop: add `or pos.id in fresh` to the skip; call `_check_sl_tp(pos, event)`.
5. `_fill_pending_on_bar`: add `or pending.submitted_at >= event.occurred_at` to the skip.
6. Rewrite `_check_sl_tp(pos, bar)` per Q4; update the class docstring.

`historical_replay_app_service.py`: `occurred_at=bar_time` on `BarCompletedEvent` (the only other producer).

Size: ~+18 / −6 src — more code than it replaces (CLAUDE.md stop-and-ask point).

### 4. Behaviour changes

Live paper: coarser bars no longer close, fill LIMITs, or mark prices; a 1m strategy's own signal bar no longer closes its entry; gap exits fill at the open (prod SL 7690 × 1.00005 = 7690.38, not 7681.31).

Backtests: identical for in-range-open, non-signal bars. Deliberate: (1) a signal bar no longer closes its own entry; (2) a LIMIT submitted on bar N fills at earliest on N+1; (3) gap bars fill at the open. hitnrun2 most affected: its LONG SL can sit above entry (`max(min(prev_lows), …)`), so today it "exits" at a profit on the signal bar; now at the next bar's open. Traced: `test_backtest_long_round_trip_on_downtrend`, `_short_round_trip_on_uptrend`, `_multi_trade_after_fill_reset`, `_sharpe_bounded…` still pass (flat curve guarded by `std == 0`). Expect hitnrun2 P&L in real backtests to fall — the bias removed. Engulfing and pullback30 unchanged (SL/TP outside the signal bar).

Unchanged: Exness, persistence, current broker unit expectations (mid-range opens; orders placed before the event is created).

### 5. Risks

Feed delay: no feed-vs-wall comparison. Pooled: per symbol; a 15m-only symbol still served. Startup: if the first event is coarse (race during `load_strategy`), that bar is checked once; self-corrects on the next 1m. Weekend: reopen 1m fills at open. Both levels past: impossible; open past TP → TP wins even if low later reaches SL. SHORT spread: gap uses ask open; intrabar stays at level. Slippage once, adverse, incl. favourable TP gaps. Manual orders between bars: checked on the next bar. Unit-test microsecond tie between submit and event creation could flake (unlikely). Unknown interval: `Interval(...)` raises.

### 6. Verification

`test_paper_broker_sl_tp_fill.py` (`_bar_event` gets `open=None`, `interval="1m"`):
- `test_coarser_bar_does_not_close_but_next_1m_does` (AC1): 1m (100.2/99.8), BUY sl 98/tp 104; 4h (105/97) → open; 1m (100.5/97.5) → 98.
- `test_coarser_bar_does_not_fill_pending_limit` (BUY LIMIT 90; 4h low 89, then 1m low 89.5 → 90).
- `test_finest_interval_is_per_symbol`; `test_signal_bar_does_not_close_entry_made_by_its_handler` (handler subscribed before `connect` submits on bar 1 97–101 sl 98; bar 2 closes).
- `test_limit_filled_on_bar_is_still_checked_same_bar` (LIMIT 90 sl 85, bar o92/h95/l84 → fill 90 then SL 85).
- `test_long_sl_gap_fills_at_open` (o96/h97/l95, slip 0.001 → 96×0.999); `test_long_tp_gap_fills_at_open` (o106); `test_open_past_tp_beats_intrabar_sl` (o105/l97 → 105); `test_long_sl_inside_range_fills_at_level` (o99/l97 → 98); `test_short_sl_reopen_gap_matches_prod` (→ 7690.38).
`test_paper_broker_spread.py` (spread 0.4): `test_short_sl_gap_fills_at_ask_open` (o103 → 103.4), `test_short_tp_gap_fills_at_ask_open` (o94 → 94.4).
New `tests/backtest_test/engine/test_paper_broker_signal_bar.py`: `test_replay_signal_bar_does_not_close_its_entry` (replay 2 bars; entry bar 1, exit bar 2).
Commands: broker suite, `tests/backtest_test`, `just test`, ruff check + format on touched files, `uv run pyright src`, `uv run lint-imports`, `uv run python scripts/code_metrics.py --ratchet`.

Status: DONE_WITH_CONCERNS — src grows ~12 net lines; hitnrun2 backtest P&L drops because a signal-bar exit bias is removed.
