---
phase: 9
title: "Capabilities in paper: stop entry, EXIT, risk, order SL/TP persistence, restore; architecture doc"
status: completed
priority: P1
effort: 1.5d
dependencies: [8]
---

# Phase 09: Capabilities in paper: stop entry, EXIT, risk, order SL/TP persistence, restore; architecture doc

<!-- Red team 2026-11-01: #15 -->
No open issue: plan.md "Design verdicts" settles the trigger order, `close_position(..., *, reason, deadline)`, the stop lifetime and the test double.

## Goal

Paper supports `entry_type=stop` as a broker-held resting order and `Direction.EXIT` as "go flat". Every new signal cancels the subscription's resting stop before it places anything, except that an unchanged stop is kept. A resting stop never outlives a stop, unload, edit or handover. Orders persist SL/TP; a takeover restores paper positions and cancels every stored pending stop. The architecture doc says so in the same commit.

## Context

- Design verdicts (plan.md): the pending stop rests in the broker; `on_order_update` is subscribed for every broker and returns early for `OrderStatus.PENDING`; the engine calls `PaperBrokerAdapter.fill_resting_stops(event, running)` before any strategy decides on a bar, and the same pass runs the SL/TP check; EXIT cancels the pending stop, then sends `close_position` even when the cancel fails; `close_position` is a no-op by state; EXIT is exempt from the stale and gap skips. Orders persist `sl_price`/`tp_price`. <!-- Red team 2026-11-01: #1 #2 #4 #5 #12 -->
- Why the engine calls the trigger: strategies subscribe to `BarCompletedEvent` before the paper broker (`src/pocketquant/engine/strategy/strategy_app_service.py:108-117`, `core/infra/brokers/paper/paper_broker_adapter.py:106-111`), and a backtest streams only the entry interval. A stop re-placed every bar would be cancelled before the broker's own handler saw a touching bar.
- Signal (`core/domain/strategy/value_objects.py:9-23`) has `entry_price` that the engine never reads. `Direction.EXIT` exists (`core/domain/strategy/enums.py:4-8`). The risk check rejects every non-entry direction and says "exits are SL/TP only" (`engine/execution/risk_check.py:12-26`); its test is `tests/engine_test/test_risk_check.py:40`.
- Orders: `to_mongo`/`from_mongo` drop `sl_price` and `tp_price` (`core/domain/order/entities.py:173-208`). `OrderAppService.submit` saves before the broker call (`engine/execution/order_app_service.py:33-36`) and logs INFO `order_submitted` (`:89-94`). `on_order_update` handles FILLED and CANCELLED for orders in `_pending` (`:129-165`); `load_pending_orders` restores `find_pending` rows (status pending, submitted, partially filled; `core/infra/persistence/repositories/order_repository.py:20-25`). Paper calls `_notify_callbacks` inside `submit_order` (`paper_broker_adapter.py:136`) while the order is still PENDING.
- Paper broker: market-only (`:146-165`); `cancel_order` is a no-op (`:224-226`); `_on_bar_completed` (`:472-503`) acts only on the finest interval, sets `_current_prices` (`:478`) and skips positions with `opened_at >= event.occurred_at` (`:479`). `_fire_synthetic_exit` (`:528-586`) checks only object identity (`:547-551`), and a closed position lingers in `_positions`, so a second exit of the same closed object opens a reverse position (`_execute_fill`, `:335-339`). `restore`/`drop_positions`/`reset` are at `:230-246,588-593`. Reasons live in `core/domain/brokers/events.py:14-20`. <!-- Red team 2026-11-01: #4 -->
- Paper has no entries pause and no daily loss cap: both exist only in the Exness adapter (`core/infra/brokers/exness/exness_broker_adapter.py:219-252,300-319`). The paper placement checks are the lease (`trading_until`), the risk check (one position per subscription) and `_can_afford`, so the trigger re-runs those. <!-- Red team 2026-11-01: #6 -->
- Engine: `stop()` calls `stop_strategy` for every instance (`strategy_app_service.py:134-135`) before it disconnects the brokers; `stop_strategy` calls `on_stop()` only when running (`:297-298`); `unload_strategy` calls `stop_strategy` (`:306`), so the Phase 06 edit reload goes through it too. The takeover drops a paper row with no SL and no TP (`:157-165`), inverted here; its test is `tests/engine_test/test_paper_restore.py:198`. The entry guards (`:401-421`) apply to every signal. `_process_signal` is at `:505-631` (INFO `live.signal_latency` at `:605-626`), `_create_order` at `:633-651`. `on_order_update` is wired only when `fills_async` (`:676-677`) and never in `inject_prepared_strategy` (`:334-347`). <!-- Red team 2026-11-01: #1 #2 -->
- Broker port implementers: `PaperBrokerAdapter`, `ExnessBrokerAdapter` (`exness_broker_adapter.py:85`), and two test fakes: `tests/engine_test/test_async_broker_fill_wiring.py:50`, `tests/engine_test/test_concurrent_opens.py:41`. Phase 10 implements the Exness close; here it returns `False` with a WARNING, as its `cancel_order` does (`:750-752`). `test_paper_broker_is_not_subscribed_to_order_updates` (`test_async_broker_fill_wiring.py:167-179`) and the file header (`:1-2`) assert the `fills_async` gate this phase removes. <!-- Red team 2026-11-01: #9 -->
- Test double: the one `ScriptedStrategy` in `tests/strategy_doubles.py` (created in Phase 05; Phase 08 added its per-bar script mode: class-level `SCRIPT`, instance `script`, each item a dict of field overrides applied with `dataclasses.replace` to the fixed-rule LONG signal of that bar, or `None`). This phase only writes script items, for example `{"entry_type": "stop", "entry_price": 101.0}` or `{"direction": Direction.EXIT}`; it adds no second double and no second script form. <!-- Red team 2026-11-01: #15 -->
- Paper fill rules (advice A-3, optimistic): BUY when `high + spread >= stop`, filled at `max(open + spread, stop)`; SELL when `low <= stop`, filled at `min(open, stop)`; slippage applies; never on the bar where the stop was placed (`placed_at >= event.occurred_at`). On a stop-fill bar only the SL is checked, against that bar's range, filled at the SL (worst case); the TP waits for the next bar. <!-- Red team 2026-11-01: #12 -->
- Logs: a stop moved every bar is a per-bar event, so its cancel and re-submit log at DEBUG; the business INFO lines are the fill, `strategy.position_close_sent` and the manual action. <!-- Red team 2026-11-01: #14 -->
- Docs C6, in the same commit: `docs/system-architecture.md` "Exits are SL/TP only" (HEAD `:12`), the takeover sentence (HEAD `:22`), the "One take-profit per entry, closed in full" section (HEAD `:37-48`); `docs/deployment.md:124`. Locate each by its text.

## Entry gate

Run from `D:/w/_me/algotrading/pocketquant`:
1. `git status --porcelain -- src web deploy tests scripts docs .github | wc -l` prints `0`.
2. `git fetch -q origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo synced` prints `synced`.
3. `tail -1 plans/261101-0843-stf-to-mtf-foundation/reports/phase-08-backtest-intervals-backend.md` prints `Result: PASS`.
4. `git grep -n "def close_position" -- src | wc -l` prints `0` (on a resume, skip each task whose Verify already passes).
5. `git grep -n -E "^class ScriptedStrategy|SCRIPT: ClassVar" -- tests/strategy_doubles.py | wc -l` prints `2`. <!-- Red team 2026-11-01: #15 -->
6. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok`.

A resumed phase may show its own task files as uncommitted (line 1), and line 2 may fail only when `git rev-list --count HEAD..origin/develop` prints `0` (local is ahead by this phase's own unpushed commits). <!-- Consistency sweep 2026-11-01 --> On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 09 after <UTC time>
```

## Files

- Modify (src): `src/pocketquant/core/domain/strategy/value_objects.py`, `src/pocketquant/engine/execution/risk_check.py`, `src/pocketquant/core/domain/order/entities.py`, `src/pocketquant/engine/execution/order_app_service.py`, `src/pocketquant/core/domain/brokers/broker_port.py`, `src/pocketquant/core/domain/brokers/events.py`, `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py`, `src/pocketquant/core/infra/brokers/exness/exness_broker_adapter.py` (temporary `close_position` only), `src/pocketquant/engine/strategy/strategy_app_service.py`.
- Modify (tests): `tests/engine_test/test_risk_check.py`, `tests/core_test/unit/domain/order/test_order_aggregate_uuid_id.py`, `tests/engine_test/test_order_app_service_immediate_fill.py`, `tests/engine_test/test_paper_restore.py`, `tests/engine_test/test_async_broker_fill_wiring.py` (fake `close_position`, the inverted paper wiring test, the header), `tests/engine_test/test_concurrent_opens.py`. `tests/strategy_doubles.py` is not changed: the Phase 08 script mode covers every test here. <!-- Red team 2026-11-01: #9 #15 -->
- Create (tests): `tests/core_test/unit/domain/strategy/test_signal.py`, `tests/core_test/infra/brokers/test_paper_broker_stop_entry.py`, `tests/engine_test/test_paper_capabilities.py`.
- Modify (docs): `docs/system-architecture.md`, `docs/deployment.md`.

## Tasks

### Task 09.1 — Signal entry type and the EXIT risk branch

**Goal:** a stop entry is a valid signal only with a price and a side; EXIT passes risk only with an open position.

**Target files and symbols:** `Signal` (`value_objects.py:9-23`); `RiskCheckHandler.validate` and its comment (`risk_check.py:11-46`).

**Steps:**
1. Tests first. `test_signal.py`: `test_a_stop_entry_needs_an_entry_price` (raises `ValueError`); `test_a_stop_entry_needs_a_long_or_short_side` (EXIT with `entry_type="stop"` raises); `test_a_market_signal_defaults_to_market`. In `test_risk_check.py`, replace `test_exit_and_flat_signals_are_rejected` (`:39-44`) with `test_an_exit_with_an_open_position_passes`, `test_an_exit_without_a_position_is_rejected` (reason `no open position`), `test_an_exit_passes_with_zero_balance` and `test_a_flat_signal_is_rejected`.
2. Run `uv run python -m pytest tests/core_test/unit/domain/strategy/test_signal.py tests/engine_test/test_risk_check.py -q 2>&1 | tail -1`. Expected red: `failed`.
3. Add `entry_type: Literal["market", "stop"] = "market"` as the last `Signal` field. `__post_init__` raises `ValueError("a stop entry needs entry_price and a LONG or SHORT direction")` when `entry_type == "stop"` and (`entry_price is None` or the direction is not LONG/SHORT).
4. In `validate`, add a first branch: EXIT returns `(False, "no open position")` when the position is `None` or closed, else `(True, "")`. Replace the comment `:12-14` with: "EXIT passes only with an open position; the engine closes it through the broker, never through an order. FLAT and other non-entry directions are rejected because the order path maps them to SELL. An entry against an open position is rejected: a subscription holds one position."

**Success criteria:** the seven tests pass.

**Verify:** `uv run python -m pytest tests/core_test/unit/domain/strategy/test_signal.py tests/engine_test/test_risk_check.py -q 2>&1 | tail -1` contains `passed` and no `failed`.

### Task 09.2 — Order store: SL/TP persistence, pending stop, cancel, PENDING guard

**Goal:** a stored stop keeps its exits; the order service finds and cancels a subscription's resting stop; an immediate paper fill is processed once when paper is wired to `on_order_update`.

**Target files and symbols:** `OrderAggregate.to_mongo`/`from_mongo`; `OrderAppService.submit` (the `order_submitted` log), `on_order_update`, new `pending_stop`, new `cancel`.

**Steps:**
1. Tests first. `test_order_aggregate_uuid_id.py`: `test_mongo_round_trip_keeps_sl_and_tp`. `test_order_app_service_immediate_fill.py`: `test_a_wired_paper_fill_publishes_one_fill_event` (`await broker.subscribe_order_updates(svc.on_order_update)`, then a MARKET BUY: exactly one `OrderFilledEvent`, result FILLED); `test_pending_stop_and_cancel` (a STOP_MARKET order moved to SUBMITTED in `_pending`: `pending_stop("s1")` returns it; after `await svc.cancel(order)` it is CANCELLED and saved, and `pending_stop("s1") is None`).
2. Run `uv run python -m pytest tests/core_test/unit/domain/order tests/engine_test/test_order_app_service_immediate_fill.py -q 2>&1 | tail -1`. Expected red: `failed`.
3. `to_mongo` writes `"sl_price"` and `"tp_price"`; `from_mongo` reads `doc.get("sl_price")` and `doc.get("tp_price")`.
4. At the top of `on_order_update`, inside the lock after the lookup: `if order.status is OrderStatus.PENDING: return`, with the comment "submit() owns an order until the broker call returns; a paper broker notifies inside that call."
5. `def pending_stop(self, subscription_id) -> OrderAggregate | None` returns the first `_pending` order with that subscription id, `order_type is OrderType.STOP_MARKET` and `status is OrderStatus.SUBMITTED`. `async def cancel(self, order) -> None`: under the lock, return if `self._pending.pop(str(order.id), None) is None`; otherwise `order.cancel()` and `await self._order_repo.save(order)`; after the lock, log DEBUG `order_cancelled` (order_id, subscription_id). It publishes no `OrderCancelledEvent`: the engine asked for the cancel. <!-- Red team 2026-11-01: #14 -->
6. In `submit`, log `order_submitted` at DEBUG for a STOP_MARKET order and at INFO otherwise, with the comment "A stop may be moved every bar; its fill is the per-trade event." <!-- Red team 2026-11-01: #14 -->

**Success criteria:** the three tests pass.

**Verify:** `uv run python -m pytest tests/core_test/unit/domain/order tests/engine_test/test_order_app_service_immediate_fill.py -q 2>&1 | tail -1` contains `passed` and no `failed`.

### Task 09.3 — Paper resting stop, pre-strategy pass, and `close_position` on the port

**Goal:** paper holds one resting STOP_MARKET per placement, fills it in a pass the engine runs before strategies (stops, then SL/TP), refuses a fill the placement checks would refuse, cancels it, drops it, and closes a whole open position exactly once.

**Target files and symbols:** `IBrokerPort` (new abstract `close_position`); `events.py` (`REASON_STOP_FILL`, `REASON_STRATEGY_EXIT = "strategy_exit"`, `REASON_CANCELLED`; the `strategy_exit` value is read by Phase 10's tests and Phase 17's log grep) <!-- Consistency sweep 2026-11-01 -->; `PaperBrokerAdapter.__init__` (`self._resting`), `submit_order`, `cancel_order`, `drop_positions`, `restore`, `reset`, `_on_bar_completed`, new `_is_finest`, new `_sl_tp_hits`, new `fill_resting_stops`, new `close_position`, `_fire_synthetic_exit` (returns `bool`); `ExnessBrokerAdapter.close_position` (temporary); `_AsyncFillBroker`, `_VenueBroker`.

**Steps:**
1. Tests first in `test_paper_broker_stop_entry.py` (broker with `slippage_percent=0.0`, `fill_delay_ms=0`, an `EventBus`, `set_simulation_time` for `placed_at`, events with an explicit `occurred_at`; `fill_resting_stops(event, {"s1"})` unless stated):
   - `test_a_buy_stop_fills_on_a_later_bar_that_touches_it` (stop 101, bar O100 H101.5 → filled at 101.0, one FILLED order callback with the order's id and SL); `test_a_buy_stop_gapped_over_fills_at_the_open` (O102 → 102.0); `test_a_sell_stop_fills_at_the_stop_or_the_open_below_it`; `test_a_stop_never_fills_on_the_bar_it_was_placed`; `test_a_cancelled_stop_never_fills` (`cancel_order` True, then False).
   - <!-- Red team 2026-11-01: #1 #6 --> `test_a_stop_of_a_subscription_not_running_is_skipped` (`running=set()`: no callback, the stop still rests); `test_a_stop_is_refused_while_the_subscription_holds_a_position` (one CANCELLED callback, nothing rests).
   - <!-- Red team 2026-11-01: #12 --> `test_a_stop_fill_bar_checks_only_the_sl_against_that_bar` (stop 101, SL 99, TP 103, bar O100 H103.5 L98.5 → fill at 101, then an SL exit at 99 on the same bar; no TP exit); `test_the_pass_takes_the_sl_of_an_open_position` (a position with SL 99, a bar with L98 → one SL exit in the pass; the broker's own handler on the same event adds nothing).
   - <!-- Red team 2026-11-01: #4 --> `test_close_position_fills_the_whole_position` (True; one `OrderFilledEvent` on the bus, one trade callback, `get_positions() == []`; a second call returns False); `test_an_exit_of_an_already_closed_position_does_nothing` (close, then `_fire_synthetic_exit` on the same position object returns False; no new position, one fill in total).
   - `test_drop_reset_and_restore_clear_resting_stops`.
2. Run `uv run python -m pytest tests/core_test/infra/brokers/test_paper_broker_stop_entry.py -q 2>&1 | tail -1`. Expected red: `failed`.
3. Port: `async def close_position(self, subscription_id: str, symbol: str, *, reason: str, deadline: datetime | None = None) -> bool`, abstract, with the comment "Closes the subscription's whole open position at market; False when none is open. It never opens or reverses a position." In Exness, a temporary body logs WARNING `exness.close_unsupported` and returns False. In both test fakes, a body that returns False.
4. Paper:
   - `self._resting: dict[str, tuple[OrderAggregate, datetime]] = {}`, keyed by broker order id.
   - `submit_order`: a STOP_MARKET goes under the lock into `_resting[broker_order_id] = (order, now)`; the result is `OrderResult(status=SUBMITTED, sl_price, tp_price, side, submitted_at=now)`; other non-market types keep the existing rejection.
   - `cancel_order` pops the order, emits `SUBMITTED→CANCELLED` with `REASON_CANCELLED` as an order event (no order callback), and returns whether it was found.
   - `_is_finest(event) -> bool` holds `:473-477`. `_sl_tp_hits(event, skip) -> list[...]` holds the collection loop `:479-490` (positions with `opened_at >= event.occurred_at` or in `skip` are left out). `_on_bar_completed` uses both and keeps its SL/TP check, with the WHY comment "After the engine's pre-strategy pass this finds nothing new on the bar; it still runs in standby, where the engine skips that pass."
   - `fill_resting_stops(event, running: set[str])`: return unless `_is_finest`. Set `self._current_prices[symbol] = event.close` first, so an EXIT on this bar closes at its close. Under the lock, for each resting order on the symbol with `placed_at < event.occurred_at` that the bar touches (fill rules in Context): skip it when its subscription is not in `running`; refuse it when the subscription holds an open position or `_can_afford` fails; otherwise apply `_apply_slippage`, pop it and `_execute_fill_with_commission`. For each filled position, check only its SL against this bar (`low <= sl` for LONG, `high + spread >= sl` for SHORT, exit at `sl`). Then collect `_sl_tp_hits(event, skip=<filled ids>)`. After the lock: per fill, emit `SUBMITTED→FILLED` with `REASON_STOP_FILL`, `_notify_callbacks(FILLED result)`, then the trade callbacks; a refused order is popped and gets `REASON_CANCELLED` plus `_notify_callbacks(CANCELLED, error_message=<"position open" | "Insufficient balance">)` and one WARNING `paper.stop_refused`; then fire the SL/TP exits through `_fire_synthetic_exit`. No `OrderFilledEvent` for a stop fill: `OrderAppService.on_order_update` publishes it. <!-- Red team 2026-11-01: #1 #6 #12 -->
   - `close_position`: the position under `f"{subscription_id}:{symbol}"`, or return False when it is absent or `is_closed`. The exit side is the opposite side; the trigger is `self._current_prices.get(symbol.upper(), pos.current_price)`, plus spread for a BUY. Return `await self._fire_synthetic_exit(pos, trigger, side, reason)`.
   - `_fire_synthetic_exit` returns False, without a fill, when the position under the key is not `pos`, or `pos.is_closed`, or `pos.quantity <= 0`; True after a fill. Update its comment: "A second exit of one position must never reverse it; closed is decided by state, not by identity." <!-- Red team 2026-11-01: #4 -->
   - `drop_positions` also drops the subscription's resting orders; `reset` and `restore` clear `_resting`. `restore(positions, realized_net)` keeps its signature: a takeover restores no stop. <!-- Red team 2026-11-01: #1 -->

**Success criteria:** the twelve tests and the existing broker tests pass.

**Verify:** `uv run python -m pytest tests/core_test/infra/brokers tests/backtest_test/engine -q 2>&1 | tail -1` contains `passed` and no `failed`.

### Task 09.4 — Engine: pass order, cancel-then-place, kept stop, EXIT, stop lifetime, takeover

**Goal:** the engine runs the paper pass before strategies only while it may trade, places and moves stops, keeps an unchanged stop, goes flat on EXIT even on a gapped or stale bar and even when the cancel fails, cancels a stop on every stop, unload and handover, and cancels stored stops at takeover.

**Target files and symbols:** `StrategyAppService.take_over`, `stop_strategy`, `inject_prepared_strategy`, `_on_bar_completed` (and its comment `:360-362`), `_process_signal`, `_create_order`, `_get_or_create_broker`, new `_cancel_stop`.

**Steps:**
1. <!-- Red team 2026-11-01: #15 --> Test setup: load `ScriptedStrategy` and set `script` on the loaded instance (Phase 08 mode). "Stop LONG 101" below means the item `{"entry_type": "stop", "entry_price": 101.0}` (plus `stop_loss_price`/`take_profit_price` overrides where a test names them); "market LONG" means `{}`; "EXIT" means `{"direction": Direction.EXIT}`; a bar with no signal is `None`.
2. Tests first in `test_paper_capabilities.py` (a paper engine as in `tests/engine_test/test_paper_position_lifecycle.py`, `ScriptedStrategy`, 1m live events):
   - `test_a_stop_replaced_every_bar_still_fills_on_the_bar_that_touches_it`: bar 1 stop LONG 101; bar 2 (H101.5) stop LONG 105. Exactly one BUY fill at 101.0; the tracker holds the position.
   - `test_a_new_signal_cancels_the_resting_stop_then_places`: bar 1 stop 105; bar 2 (H102) stop 104. The first order is CANCELLED, the second SUBMITTED; `pending_stop` is the second.
   - <!-- Red team 2026-11-01: #14 --> `test_an_unchanged_stop_is_kept`: bar 1 stop LONG 105; bar 2 (H102) stop LONG 105. One order, still SUBMITTED, one `submit_order` call; `structlog.testing.capture_logs` shows DEBUG `strategy.stop_kept` and no INFO line from bar 2.
   - `test_exit_cancels_the_pending_stop_and_closes_the_position`: market LONG (SL 50), then stop LONG 200, then EXIT. One SELL fill, one `TradeClosedEvent`, no pending, no open position.
   - <!-- Red team 2026-11-01: #5 --> `test_exit_closes_even_when_the_cancel_fails` (the broker's `cancel_order` patched to return False): one SELL fill, one WARNING `strategy.pending_cancel_failed`.
   - <!-- Red team 2026-11-01: #2 --> `test_an_exit_on_a_gapped_bar_still_closes` (`gap=True`) and `test_an_exit_on_a_stale_bar_still_closes` (bar end older than `_STALE_AFTER_S`): one SELL fill each; an entry on the same bar kind is still skipped.
   - <!-- Red team 2026-11-01: #12 --> `test_an_exit_bar_takes_the_sl_first`: a LONG with SL 99, then a bar with L98 on which the script says EXIT. One exit at 99 with `REASON_AUTO_SL`; the EXIT finds nothing open and logs DEBUG `strategy.exit_ignored`.
   - `test_exit_with_nothing_open_is_ignored`: no order; one DEBUG `strategy.exit_ignored`.
   - <!-- Red team 2026-11-01: #1 --> `test_stopping_a_subscription_cancels_its_pending_stop`; `test_unloading_a_stopped_subscription_cancels_its_pending_stop` (stop, then unload: the cancel runs although the instance is not running); `test_a_handover_stop_cancels_the_pending_stop` (`await engine.stop(timeout_s=0)`: the order is CANCELLED and saved); `test_no_stop_fills_without_the_lease` (`trading_until = None`, a touching bar: no fill, the order stays SUBMITTED).
   - In `test_paper_restore.py`, rename `test_a_paper_row_without_exits_is_dropped` (`:198`) to `test_a_paper_row_without_exits_is_restored` and invert its asserts (the row is open in the broker; no `paper_position_dropped_no_exits`). <!-- Red team 2026-11-01: #1 --> Add `test_a_takeover_cancels_stored_pending_stops`: `find_pending` returns a SUBMITTED STOP_MARKET with SL; after `take_over` it is CANCELLED and saved, `pending_stop(sid) is None`, and a touching bar opens no position.
   - <!-- Red team 2026-11-01: #9 --> In `test_async_broker_fill_wiring.py`, replace `test_paper_broker_is_not_subscribed_to_order_updates` (`:167-179`) with `test_a_paper_broker_is_subscribed_to_order_updates_once` (two subscriptions on one pooled paper broker: `len(broker._order_callbacks) == 1`), and rewrite the header `:1-2` as "# Every broker is subscribed to order updates once, when it is created; a paper broker / # notifies inside submit_order, and the order service ignores an order still PENDING."
3. Run `uv run python -m pytest tests/engine_test/test_paper_capabilities.py tests/engine_test/test_paper_restore.py tests/engine_test/test_async_broker_fill_wiring.py -q 2>&1 | tail -1`. Expected red: `failed`.
4. `_cancel_stop(order, broker) -> bool`: if `await broker.cancel_order(order.broker_order_id or "")` is True, `await self._order_app_service.cancel(order)` and return True; otherwise log WARNING `strategy.pending_cancel_failed` (subscription_id, order_id) and return False.
5. `_on_bar_completed`:
   - At the top of the `try`: when `self.trading_until is not None and get_current_time() < self.trading_until`, build `running = {sid for sid, s in self._strategies.items() if s.is_running}` and call `await broker.fill_resting_stops(event, running)` for each distinct connected `PaperBrokerAdapter` in `self._brokers.values()` (an exception logs ERROR `paper.stop_fill_failed` with `exc_info=True`). WHY comment: "Stops resting from earlier bars fill, and SL/TP exits run, before any strategy decides on this bar. A fill is an entry, so it needs the lease like any other." <!-- Red team 2026-11-01: #1 #12 -->
   - The stale and gap checks run only when `signal.direction is not Direction.EXIT`; the in-flight check runs for every signal, so an EXIT behind an in-flight entry is skipped as `inflight` and the strategy sends it again on the next bar (Phase 14). Rewrite the comment `:360-362` to say so: "An exit is never stale: going flat is not a look-ahead risk." <!-- Red team 2026-11-01: #2 -->
6. `_process_signal`, after the broker lookup:
   - `pending = self._order_app_service.pending_stop(strategy.id)`.
   - <!-- Red team 2026-11-01: #14 --> A stop entry whose `pending` has the same side and `stop_price == signal.entry_price` logs DEBUG `strategy.stop_kept` and returns.
   - If `pending` is set and `_cancel_stop` fails: an entry calls `on_order_rejected("pending cancel failed")` and returns; an EXIT goes on. <!-- Red team 2026-11-01: #5 -->
   - `current_price = signal.entry_price if signal.entry_type == "stop" else event.close` (sizing and fallback SL).
   - After risk validation: an invalid EXIT logs DEBUG `strategy.exit_ignored` when `pending is None` and returns either way, with no `on_order_rejected`.
   - A valid EXIT calls `await broker.close_position(strategy.id, position.symbol, reason=REASON_STRATEGY_EXIT, deadline=deadline)`, logs INFO `strategy.position_close_sent` (subscription_id, reason, closed) and returns before sizing.
   - `live.signal_latency` logs at DEBUG when `pending` was set (a moved stop), else at INFO. <!-- Red team 2026-11-01: #14 -->
7. `_create_order`: a stop builds `OrderType.STOP_MARKET` with `stop_price=signal.entry_price` and `price=None`; a market signal builds as today.
8. Wire `on_order_update` for every broker: drop the `fills_async` condition at `:676-677` (keep the WHY of a one-time wiring), and in `inject_prepared_strategy` subscribe it before `connect()` only when the broker is not already in `self._brokers.values()`.
9. <!-- Red team 2026-11-01: #1 --> `stop_strategy` keeps `on_stop()` inside its `is_running` check, and after that check cancels `pending_stop(strategy_id)` through `_cancel_stop` whenever one exists and a broker is bound. `stop()` keeps its `stop_strategy` loop, so a handover cancels every resting stop before the brokers disconnect. Comment: "A resting stop never outlives its strategy: stop, unload, edit and handover all cancel it, and the strategy re-places it on its next bar."
10. <!-- Red team 2026-11-01: #1 --> `take_over`: delete `:157-165` and the `dropped` counter; `broker.restore(rows, realized)` is unchanged. Then, for each `sid` in `self._strategies` with `order := pending_stop(sid)`: `await broker.cancel_order(order.broker_order_id or "")` when a broker is bound (its result is only logged), then `await self._order_app_service.cancel(order)`, and log INFO `strategy.pending_stop_dropped` (subscription_id, order_id, broker_cancelled). Log `paper_stops_dropped=` in place of `paper_dropped=`.

**Success criteria:** the new and changed tests pass; `git grep -n "paper_position_dropped_no_exits" -- src tests | wc -l` prints `0`.

**Verify:** `uv run python -m pytest tests/engine_test tests/backtest_test -q 2>&1 | tail -1` contains `passed` and no `failed`.

### Task 09.5 — Architecture and deployment docs (same commit, C6)

**Goal:** the docs state the new exit and pending-stop rules; no "SL/TP only" claim remains.

**Target files and symbols:** `docs/system-architecture.md` (three places, located by text), `docs/deployment.md` (the "Restart while live" paragraph).

**Steps:**
1. Replace the "Exits are SL/TP only" bullet with: "- **A position exits at its SL or TP, on a strategy EXIT, or on a manual close.** EXIT means go flat: the engine cancels the subscription's pending stop, then closes the whole position through `IBrokerPort.close_position`, even when the cancel fails. A close of a position that is already closed does nothing; it never opens or reverses one. An EXIT is never skipped as stale or gapped. The risk check accepts EXIT only with an open position and rejects FLAT and any entry against an open position. An Exness position also closes at a broker stop-out. Unloading a subscription leaves a venue position open under its own SL/TP. Rejected: an opposite market order as the close, which opens a position when an SL fill lands first." <!-- Red team 2026-11-01: #2 #4 #5 -->
2. <!-- Red team 2026-11-01: #1 --> Replace "Paper positions live in broker memory. … so it never shows as a finished position." with: "- Paper positions live in broker memory. The trader that takes the lease rebuilds them from the open `positions` rows and the realized pnl in `trades`. A pending stop never outlives its strategy: stop, unload, edit and handover cancel it, the takeover cancels every stored pending stop, and the strategy re-places it on its next bar."
3. Replace the section from "### One take-profit per entry, closed in full" through "The Exness broker also sends one take-profit per order." with a section `### One position and one pending stop per subscription`: "A subscription holds at most one position and one pending stop. A new signal cancels the pending stop before it places anything; an unchanged stop (same side and price) is kept. There is no scale-out, no multi-TP and no partial close; a close is always the whole position. These layers each hold one, and all must change together, plus the position box in `web/`:". Then a table with columns Layer | Holds one | Owner, and rows: Signal | `take_profit_price`; `entry_type`; or `Direction.EXIT` | `Signal` (`core/domain/strategy/value_objects.py`). Strategy hook | `Signal \| None` per bar | `IStrategyService.on_bar_completed`. Pending stop | one SUBMITTED `STOP_MARKET` order | `OrderAppService.pending_stop`. Paper exit | the whole `pos.quantity` | `PaperBrokerAdapter._check_sl_tp`, `close_position`, `_fire_synthetic_exit`. Position store | one position per `{subscription_id}:{symbol}` | `PaperBrokerAdapter._execute_fill`. Then: "The Exness broker also sends one take-profit per order. The engine runs `PaperBrokerAdapter.fill_resting_stops` before strategies decide on a bar: resting stops fill first, then SL/TP exits. A paper stop fills on the first later finest bar whose range reaches it, at the stop or at an open beyond it; in a fast market this is optimistic. On that bar only its SL is checked, at the SL (worst case)." <!-- Red team 2026-11-01: #12 #14 -->
4. In `docs/deployment.md`, the sentence "…and restores each open direction from the open positions (`StrategyAppService.take_over`)." becomes "…restores each open direction from the open positions and cancels every stored pending stop; the strategy re-places it on its next bar (`StrategyAppService.take_over`)." <!-- Red team 2026-11-01: #1 -->

**Success criteria:** A13 holds; both docs stay under 800 lines; every symbol named exists (`git grep -n "def pending_stop\|def close_position\|def fill_resting_stops" -- src | wc -l` prints at least `4`).

**Verify:** `git grep -n -i "SL/TP only\|One take-profit per entry\|neither SL nor TP" -- docs | wc -l` prints `0`, and `grep -c -F "never outlives its strategy" docs/system-architecture.md` prints `1`.

### Task 09.6 — CLOSE

**Goal:** the behaviour change and its docs land in one commit on `develop`, with every gate green.

**Target files and symbols:** none new; `pyproject.toml` `[tool.code-metrics]` only if the ratchet alone fails.

**Steps:**
1. GATES: `uv run lint-imports | tail -1` prints `Contracts: 6 kept, 0 broken.`; `uv run python scripts/code_metrics.py --ratchet; echo "exit=$?"` prints `exit=0`; `uv run ruff check src tests scripts; echo "exit=$?"` prints `exit=0`. If only the ratchet fails, raise the ceiling in its own commit `chore(metrics): raise the code metric ceiling` and record the old and new values in the report.
2. FULLSUITE: `uv run python -m pytest tests/ -q > .cache/pytest.txt 2>&1; tail -1 .cache/pytest.txt; grep -E "^(FAILED|ERROR) " .cache/pytest.txt | grep -v -E "test_utc_runtime_guard|test_cron_trigger_timezone" | wc -l`. The tail contains `4 failed` and `4 errors`; the count prints `0`.
3. One commit with code, tests and both docs: `feat(execution): stop entries and strategy exits`.
4. Push: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.
5. `sleep 15`, then repeat the Verify command until it prints `completed`.

**Success criteria:** CI on the pushed HEAD concludes `success`; `git show --stat HEAD` lists `docs/system-architecture.md` and `docs/deployment.md` (or, when a metric commit came last, `HEAD~1` does).

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.headSha) \(.status) \(.conclusion)"'` prints `<git rev-parse HEAD> completed success`.

## Rollback

Nothing is deployed and live trading stays disarmed. Run `git revert --no-edit <phase-commit>` (plus the metric commit, if any) and push; the revert restores the docs with the code. Order documents written by this code carry `sl_price`/`tp_price`, which the old code ignores; a stop order left SUBMITTED in a dev store is loaded by the old `load_pending_orders` and never fills, because the old paper broker rejects non-market orders.

## Report

`reports/phase-09-capabilities-in-paper.md` holds: the commit SHAs; every new, renamed and inverted test with pass counts; the A13 grep output (`0`); one line confirming the pass order (stops, then SL/TP, before strategies, only with the lease) and that stop, unload, handover and takeover cancel a resting stop; the FULLSUITE tail line; the CI run id and conclusion; any metric ceiling change. It ends with `Result: PASS`.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same failure evidence to the user. Never continue by self-reasoning.
