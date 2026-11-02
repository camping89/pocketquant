# Phase 09 report: stop entries and strategy exits in paper

Paper now rests a stop entry in the broker, fills it before strategies decide on a bar, and goes flat on `Direction.EXIT`. Orders persist SL/TP, a takeover restores every paper position and cancels stored pending stops, and both docs changed in the same commit.

## Commits

- `e5475a19e9c6b6d523b4c1fdf6848312dd566cea` `feat(execution): stop entries and strategy exits`: code, tests, `docs/system-architecture.md`, `docs/deployment.md` (25 files).
- No metric ceiling change: the ratchet exited 0.

## Entry gate

All six lines passed: `0`, `synced`, `Result: PASS`, `0`, `2`, `docker-ok`.

## Tests

New files:
- `tests/core_test/unit/domain/strategy/test_signal.py`: 3 passed.
- `tests/core_test/infra/brokers/test_paper_broker_stop_entry.py`: 16 passed. These are the twelve planned tests (the sell-stop test runs two parametrized cases), plus `test_a_stop_fill_bar_never_takes_the_tp`, `test_an_sl_already_past_the_fill_exits_at_the_fill` and `test_a_failing_subscriber_does_not_stop_the_other_fills`.
- `tests/engine_test/test_paper_capabilities.py`: 17 passed. These are the thirteen planned tests, plus `test_a_stop_with_new_exits_is_replaced`, `test_a_stop_entry_is_rejected_while_a_position_is_open`, `test_a_stop_placed_while_its_strategy_stops_is_cancelled` and `test_a_reload_after_an_unload_mid_submit_still_trades`.

Replaced, renamed and inverted:
- `test_risk_check.py`: `test_exit_and_flat_signals_are_rejected` became `test_an_exit_with_an_open_position_passes`, `test_an_exit_without_a_position_is_rejected`, `test_an_exit_passes_with_zero_balance` and `test_a_flat_signal_is_rejected`. Also added `test_a_stop_entry_against_an_open_position_is_rejected`.
- `test_paper_restore.py`: `test_a_paper_row_without_exits_is_dropped` became `test_a_paper_row_without_exits_is_restored` (inverted). Added `test_a_takeover_cancels_stored_pending_stops`.
- `test_async_broker_fill_wiring.py`: `test_paper_broker_is_not_subscribed_to_order_updates` became `test_a_paper_broker_is_subscribed_to_order_updates_once`, and the file header was rewritten.
- `test_order_aggregate_uuid_id.py`: added `test_mongo_round_trip_keeps_sl_and_tp`.
- `test_order_app_service_immediate_fill.py`: added `test_a_wired_paper_fill_publishes_one_fill_event` and `test_pending_stop_and_cancel`.

Red before green:
- Tasks 09.1 to 09.3 ran red first: 09.1 had `6 failed`, 09.2 had `3 failed`, and 09.3 hit an import error.
- For Task 09.4 the engine code was written before its tests. The tests were then run against the HEAD engine and failed there: `16 failed, 4 passed`.
- A mutation check confirmed the two race tests. Removing the post-submit cancel and the non-resting `True` makes both fail.

## Verify results

- 09.1: `14 passed`.
- 09.2: `11 passed`.
- 09.3: `160 passed`.
- 09.4: `303 passed, 3 warnings`. The `paper_position_dropped_no_exits` grep prints `0`.
- 09.5 (A13): the stale-claim grep prints `0`, the `never outlives its strategy` count is `1`, and the symbol grep prints `5`. The docs are 50 and 230 lines long.

## Pass order and stop lifetime

The engine runs `PaperBrokerAdapter.fill_resting_stops` before any strategy decides on a bar, and only while it holds the lease (`trading_until` set and in the future). In that pass, resting stops fill first and SL/TP exits run after.

A resting stop is cancelled in four cases:
- stop (`stop_strategy`);
- unload, which goes through `stop_strategy`;
- handover (`stop()`);
- takeover, which cancels the stored pending stop of every loaded subscription.

## GATES and FULLSUITE

- `Contracts: 6 kept, 0 broken.`
- Ratchet `exit=0`.
- Ruff `All checks passed!`.
- FULLSUITE: `4 failed, 1258 passed, 1 skipped, 55 warnings, 4 errors in 124.71s (0:02:04)`. The unexpected-failure count is `0`.

## CI

Run `41383851965` on `e5475a19`: `completed success`.

## Deviations from the phase text

The independent review and kongming counsel led to these changes beyond the phase text. Each one was confirmed by a probe or a test.
- **Paper `cancel_order` returns True for an id that is not resting.** It means no fill can follow. Without this, a stop dropped on unload stayed SUBMITTED in the order service, and after a reload every entry was refused with "pending cancel failed". The second assert of `test_a_cancelled_stop_never_fills` is now `True`.
- **Post-submit cancel.** If the strategy was stopped or unloaded while its stop was in flight (Mongo save plus the paper fill delay), `_process_signal` cancels that stop after `submit` returns.
- **Every fill-pass outcome is dispatched.** `fill_resting_stops` delivers every fill, refusal and exit even when a subscriber raises, then raises the first error.
- **Fill-bar SL clamp.** An SL already past the fill exits at the fill price, never at a price the bar did not trade.
- **A kept stop also needs the same SL and TP.** The phase text said "same side and price". A re-sent stop with new exits now replaces the old one.
- **The risk check rejects a stop entry while a position is open**, with the reason `position open`. Before this, a same-side stop was placed every bar and refused, with a WARNING, at every touch. Same-side market adds are unchanged.
  - As a result, a position and its own pending stop can only co-exist out of band. The two EXIT-with-pending tests therefore place the stop directly through `OrderAppService.submit`.
- **Test doubles updated to the new engine contract:** `strategy_injection_roundtrip_characterization_test.py`, `test_order_filled_event_routing.py`, `test_contract_spec_wiring.py`, `test_subscription_broker_selection.py` and `test_strategy_reject_delivery.py`. The last one passed for the wrong reason before the fix. None of these files is in the phase's Files list.
- **Doc wording kept to the code as it is now:**
  - Dropped "or on a manual close", because manual close does not exist yet.
  - Stated that the Exness `close_position` is not built and returns False.
  - The risk sentence names opposite and stop entries.
  - The takeover wording says "of every loaded subscription".
  - The table row says "a second market fill merges into it".
  - The fill-bar sentence says "at the SL, or at the fill when the SL is already past it".

## Follow-ups (not in this phase)

- **Backtest stub orders.** Every cancelled stop becomes a placeholder `OrderRecord` (MARKET, quantity 0) in backtest results, through `BacktestReportAppService.on_event`, and is saved. A strategy that moves its stop every bar writes one row per bar. The fix belongs in the collector.
- **A stored stop of a subscription loaded after takeover** is cancelled on its first moved signal. If that first signal is the identical stop, it is kept, but nothing rests until the strategy moves it.
- **A stop and a restart inside one in-flight submit** keep the old stop until the next signal.
- **Exness EXIT logs a WARNING and an INFO every bar** while `close_position` returns False. No strategy emits EXIT today; Phase 10 builds the close.
- **Backtest behaviour change.** Backtests take SL/TP before strategies on every bar, as the design verdict requires, so existing backtest numbers can change. An engine error in the pass is logged at ERROR and does not fail the run.

## Advisory record

kongming gave counsel at five points:
- the Task 09.4 test-double failures;
- the ruff E501;
- the review fix set;
- the M1 and EXIT test conflict;
- the pre-commit go/no-go, which was GO.

Result: PASS
