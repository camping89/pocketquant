---
phase: 7
title: "Exness broker behind the live-trading switch (off)"
status: pending
priority: P1
effort: 6d
dependencies: [6]
---

# Phase 07: Exness broker behind the live-trading switch (off)

## Context Links
- Advice §2.6 (CFD impedance in the adapter, async fills, the OKX dedupe pattern, `trading_disabled` and HMR) and §3 (do not fork the domain).
- `IBroker`: `src/pocketquant/core/domain/brokers/interfaces.py:13` (abstract methods :22-87). `OrderResult.is_success` (`src/pocketquant/core/domain/brokers/value_objects.py:25`) is true for every status except `REJECTED`.
- Engine: `src/pocketquant/engine/app_services/strategy_app_service.py` (`load_strategy` :96, `_on_order_filled` :286, `_process_signal` :328 with sizing at :357-367 and submit at :373, `_get_or_create_broker` :409) and `src/pocketquant/engine/app_services/order_app_service.py` (`submit` :34, reject paths :98-124, `on_order_update` :174 with the CANCELLED branch at :202-205). `on_order_update` has no subscriber today, so async fills from a non-paper broker never reach it.
- Order state machine: `src/pocketquant/core/domain/order/entities.py`. `fill` (:140-149) raises unless the fill quantity equals the order quantity, and `SUBMITTED→REJECTED` is not allowed, so an async rejection maps to `CANCELLED`.
- Strategies: `IStrategy.on_order_filled` (`src/pocketquant/core/domain/strategy/interfaces.py:76`). `hitnrun2` sets `_open_direction` when it emits a signal (`hitnrun2.py:102,110`) and clears it only on an opposite fill (:115-125), so a rejected entry silences it. `engulfing` sets it on the entry fill (`engulfing.py:140-144`) and needs no change.
- Events: `OrderCancelledEvent(order_id, subscription_id, reason)` (`src/pocketquant/core/domain/order/events.py:45`), `OrderFilledEvent`.
- PaperBroker broker-side exit pattern: `src/pocketquant/core/infra/brokers/paper/paper_broker.py:678` (exit fill price) and :715 (publishes `OrderFilledEvent` for the strategy).
- `PositionAppService.start()` registers its `OrderFilledEvent` handler (`src/pocketquant/engine/app_services/position_app_service.py:22-25,38`); `get(strategy_id)` :113. `PositionRepository.find_open` (`src/pocketquant/core/infra/persistence/repositories/position_repository.py:29`); `PositionAggregate.opened_at`.
- `BrokerFactory` lives in `src/pocketquant/app/di/adapters.py` (Phase 04); `get_available_types` returns `["paper", "okx"]` and stays so. `default_broker_config` is in the `StrategyAppService` factory in `src/pocketquant/app/di/services.py` (moved from `execution.py:65`).
- Client: `ExnessClient.call` with operation ids, `conditions()`, the live gate `LIVE_TRADING_DISABLED`, same-key retries on transport errors only, and no automatic retry on 429 (`REQUEST_RATE_LIMIT` is raised to the caller) (Phase 06 T6.6).
- Early exits in `_process_signal` that never tell the strategy today: `no_broker_for_strategy`, `signal_rejected_by_risk` and `zero_position_size` (`strategy_app_service.py:328-370`).
- Spec: `openPosition` takes `instrument`, `side`, `volume`, `stop_loss_price`, `take_profit_price` and returns `202 {operation_id, client_request_id, status}`. The events WS sends `trading_state_snapshot` on subscribe and `transaction_event` with `operation_id`, `client_request_id`, `status` (`success|rejected|failed`), `error_code`, `error_message` and `payload.{orders, positions, deals}`. A position is `{position_id, direction, instrument, volume, open_price}`; a deal is `{deal_id, type, direction, instrument, volume, price, position_id, profit: {amount, currency}, create_time}`. `getOperationStatus` returns `pending|confirmed|rejected|failed` for 24 h. WS streams never replay; state is recovered from the snapshot and trading history. Deal types: `open, close, balance, null_compensation, admin_fee, swap_fee, dividend, exness_dollar`.

<!-- Updated: Validation Session 1 - broker built and tested but kept off; no broker field; no live order -->
<!-- Updated: Validation Session 1 - follow-up: async fills for Exness only; hitnrun2 reset on every no-fill path -->
## Goal
An `ExnessBroker` that converts quantity to lots inside the adapter, always attaches SL, never exceeds the minimum lot unless `EXNESS_MAX_LOTS` is raised, enforces a daily loss cap from real deals, blocks signals until the trading snapshot is reconciled, recovers missed fills and restarts, and maps async fills and broker-side closes into the existing engine flow exactly once. It ships switched off: while `EXNESS_LIVE_TRADING` is false (the default), `BrokerFactory` refuses `exness`, and the client refuses every order operation. No per-subscription `broker` field and no public API or OpenAPI change is made; broker selection belongs to the later go-live plan. No live order is placed. Engine fixes ship with it: async fill wiring for brokers that declare async fills (only `ExnessBroker`; PaperBroker and OKX stay byte-identical), a broker quantity hook so fills always match the order quantity, and rejection delivery on every path where a signal never ends in a fill, so `hitnrun2` never goes silent.

## Files to Create or Modify
- Create: `src/pocketquant/core/infra/exness/broker.py`
- Create tests: `tests/core_test/infra/exness/test_broker.py`, `tests/engine_test/test_strategy_reject_delivery.py`, `tests/engine_test/test_async_broker_fill_wiring.py`, `tests/engine_test/test_exness_clamp_fill_position.py`, `tests/app_test/integration/test_exness_live_trading_off.py`
- Create report: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-after-exness.json`
- Modify:
  - `src/pocketquant/core/config.py`
  - `src/pocketquant/core/domain/brokers/interfaces.py`, `src/pocketquant/core/domain/strategy/interfaces.py`, `src/pocketquant/core/domain/strategy/services/hitnrun2.py`
  - `src/pocketquant/engine/app_services/strategy_app_service.py`, `src/pocketquant/engine/app_services/order_app_service.py`
  - `src/pocketquant/app/di/adapters.py` (`BrokerFactory`), `src/pocketquant/app/di/services.py` (`default_broker_config`)
  - `tests/engine_test/test_reconcile_restart_resume_integration.py`, `tests/app_test/integration/test_di_resolution_characterization.py`
  - `pyproject.toml` (`[tool.code-metrics]`, only to lower the ceiling in T7.11)

## Tasks

<!-- Updated: Validation Session 1 - settings follow the live switch -->
### T7.1 Branch and risk settings
- **Goal:** The risk-cap configuration keys exist and stay optional.
- **Target files and symbols:** `src/pocketquant/core/config.py` → `Settings.exness_daily_loss_cap: float | None = None` and `Settings.exness_max_lots: float | None = None`
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c feat/exness-broker`
  2. Add the two fields after `exness_live_trading`.
- **Success criteria:** Both fields are optional; the live switch is unchanged.
- **Verify:** `uv run pyright src/pocketquant/core/config.py` reports `0 errors`.

<!-- Updated: Validation Session 1 - normalize hook, reject hook, and a fills_async flag so only Exness gets async wiring -->
### T7.2 Broker hooks and strategy rejection hook
- **Goal:** A broker can normalize an order quantity before the order is created and can declare that it reports fills asynchronously, and a strategy can learn that its entry did not go through. Paper and OKX behaviour is unchanged.
- **Target files and symbols:** `IBroker.normalize_quantity` and `IBroker.fills_async` in `core/domain/brokers/interfaces.py`; `IStrategy.on_order_rejected` in `core/domain/strategy/interfaces.py`; `HitNRun2Strategy.on_order_rejected` in `core/domain/strategy/services/hitnrun2.py:41`
- **Steps:**
  1. Add a non-abstract method to `IBroker`: `async def normalize_quantity(self, symbol: str, quantity: float) -> float | None: return quantity`, and a class attribute `fills_async: bool = False`. Neither `PaperBroker` nor `OKXBroker` is edited, so both keep `False`.
  2. Add a non-abstract method to `IStrategy` next to `on_order_filled`: `async def on_order_rejected(self, reason: str) -> None: pass`, with a one-line docstring saying it is called when an entry signal does not end in a fill (risk rejection, zero size, broker minimum, broker rejection or cancellation).
  3. In `hitnrun2`, override `on_order_rejected` to set `self._open_direction = None`.
- **Success criteria:** The ports gain two defaults; no venue name enters the domain.
- **Verify:** no verification needed; T7.3 covers these hooks.

<!-- Updated: Validation Session 1 - reject delivery on every no-fill path; async fills wired only for fills_async brokers (Exness) -->
### T7.3 Engine wiring and tests
- **Goal:** Normalized sizes reach the order, every signal that does not end in a fill reaches the strategy as a rejection, and only brokers with `fills_async = True` (Exness) deliver async fills into `OrderAppService.on_order_update`.
- **Target files and symbols:** `StrategyAppService._process_signal`, `_get_or_create_broker` and a new `@event_handler(OrderCancelledEvent) _on_order_cancelled`; `OrderAppService.on_order_update`
- **Steps:**
  1. `_process_signal`, existing early returns: before the `return` after each of `no_broker_for_strategy`, `signal_rejected_by_risk` and `zero_position_size`, add `await strategy.on_order_rejected(...)` with `"no broker"`, the risk `reason`, or `"zero position size"`.
  2. `_process_signal`: after the `size <= 0` check, add `size = await broker.normalize_quantity(signal.symbol, size)`. When it is None, log info `order_quantity_below_broker_minimum` with `strategy_id`, `await strategy.on_order_rejected("quantity below broker minimum")` and return.
  3. `_process_signal`: after `result = await self._order_app_service.submit(order, broker)`, add `if not result.is_success: await strategy.on_order_rejected(result.error_message or "rejected")`. In `_on_quote_received`, keep the submit result and apply the same check.
  4. `_on_bar_completed`: in the existing `except Exception` branch, when a signal had been produced, also `await strategy.on_order_rejected(str(e))` inside its own `try/except` that logs `strategy_on_order_rejected_error`.
  5. `OrderAppService.on_order_update`, CANCELLED branch: after the save, publish `OrderCancelledEvent(order_id=result.order_id, subscription_id=order.subscription_id, reason=result.error_message or "")`.
  6. `StrategyAppService`: add `@event_handler(OrderCancelledEvent) async def _on_order_cancelled(self, event)` that finds the running strategy by `event.subscription_id` (same lookup as `_on_order_filled`) and awaits `strategy.on_order_rejected(event.reason)` inside the same try/except logging shape.
  7. `_get_or_create_broker`: after `broker = self._broker_factory.create(broker_type, config)`, add `if broker.fills_async: await broker.subscribe_order_updates(self._order_app_service.on_order_update)`. Only `ExnessBroker` sets the flag, so PaperBroker and OKX are never subscribed. A reused broker found by name is returned before this line, so it is subscribed once.
  8. `tests/engine_test/test_strategy_reject_delivery.py`:
     - `hitnrun2` with `_open_direction` set has it cleared after `on_order_rejected("x")`;
     - on paper (a real `PaperBroker` from `BrokerFactory` and a loaded `HitNRun2Strategy` with `_open_direction = Direction.LONG`): a risk handler stub whose `validate` returns `(False, "max exposure")` leads to no `submit_order` call and `_open_direction is None` after `_process_signal`;
     - on paper, with `PositionSizer.calculate_size` monkeypatched to return `0.0`, `_process_signal` leaves `_open_direction is None`;
     - `_process_signal` with a fake broker whose `submit_order` returns `REJECTED` calls `strategy.on_order_rejected` once;
     - a fake broker whose `normalize_quantity` returns None leads to no `submit_order` call and one `on_order_rejected`;
     - `on_order_update` with `CANCELLED` for a pending order publishes one `OrderCancelledEvent`, and the registered strategy's `on_order_rejected` runs once.
  9. `tests/engine_test/test_async_broker_fill_wiring.py`:
     - a fake `IBroker` named `fake` with `fills_async = True` whose `submit_order` returns `OrderResult(status=SUBMITTED, broker_order_id="op1")`; load a strategy through a stub factory returning it and submit through `OrderAppService.submit`;
     - invoke the stored callback with `OrderResult(order_id=<id>, broker_order_id="op1", status=FILLED, filled_quantity=<order quantity>, filled_price=10)`;
     - assert one `OrderFilledEvent` was published and, after `await position_app_service.start()`, `PositionAppService.get(sub_id)` is not None;
     - a `PaperBroker` from the factory is not subscribed: `len(broker._order_callbacks) == 0` after `load_strategy`;
     - `IBroker.fills_async`, `PaperBroker.fills_async` and `OKXBroker.fills_async` are all `False` (class attributes only; no OKX instance is built and no OKX test file is touched).
- **Success criteria:** The wiring is generic, with no venue name in the engine.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/engine_test/test_strategy_reject_delivery.py tests/engine_test/test_async_broker_fill_wiring.py -q` exits 0 with `passed`. `grep -c '"exness"' src/pocketquant/engine/app_services/strategy_app_service.py` prints `0`. `git diff master --name-only -- src/pocketquant/core/infra/brokers tests/core_test/infra/brokers | wc -l` prints `0` (PaperBroker, OKX and their tests are untouched).

<!-- Updated: Validation Session 1 - normalize before order creation; snapshot gate; unmapped hold; paginated deals cap; same-key send; close path tracked; operation watch -->
<!-- Updated: Validation Session 1 - follow-up: fills_async flag, loss cap adds dividend and commission, 429 rejects and reconciles -->
### T7.4 `broker.py`, the order path
- **Goal:** Submission enforces every live-safety rule before any HTTP call, and every accepted request is tracked until a terminal outcome.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/broker.py` → `class ExnessBroker(IBroker)`. Constructor: `(client: ExnessClient, event_bus: EventBus, position_repository: PositionRepository, daily_loss_cap: float | None, max_lots: float | None)`. Members: `name -> "exness"`, class attribute `fills_async = True`, `is_connected`, `normalize_quantity`, `submit_order`, `_realized_today`, `_send_tracked`, `_watch_operation`. State: `_positions: dict[str, _Held]` (position_id → subscription_id, symbol, `PositionSide`, units, lots), `_held_unmapped: set[str]` (instrument names), `_inflight: dict[str, _Inflight]` (client request id → subscription_id, symbol, side, instrument, `kind` open|close, position_id, acked wall time), `_pending_ack: set[str]`, `_early: dict[str, OrderResult]`, `_acked_at: dict[str, float]`, `_seen_terminal: set[str]`, `_snapshot_ready = False`, `_needs_snapshot = False`.
- **Steps:**
  1. `normalize_quantity(symbol, quantity)`: `name = instrument_name(symbol)`; when None, log a warning `exness.order_rejected_presubmit` with `reason="unknown_instrument"` and return None. `cond = await client.conditions(name)`; `lots = units_to_lots(Decimal(str(quantity)), contract_size=Decimal(cond["contract_size"]), volume_min=..., volume_step=..., volume_max=..., max_lots=Decimal(str(max_lots)) if max_lots else None)`. When None, log `exness.order_rejected_presubmit` with `reason="below_min_lot"`, `quantity` and `volume_min`, and return None. When `lots` is below the raw lot count, log a warning `exness.lots_clamped` with `requested` and `sent`. Return `lots_to_units(lots, Decimal(cond["contract_size"]))`.
  2. `submit_order(order)` returns `OrderResult(status=REJECTED, error_message=...)` without any HTTP call, in this order:
     - (a) `order.order_type != OrderType.MARKET` → `"exness adapter supports market orders only"`;
     - (b) `order.sl_price is None` → `"stop loss required"`;
     - (c) `daily_loss_cap is None` → `"EXNESS_DAILY_LOSS_CAP not set"`;
     - (d) `not self._snapshot_ready or self._needs_snapshot` → `"awaiting trading snapshot reconciliation"`;
     - (e) `instrument_name(order.symbol)` is None → `"unknown exness instrument"`;
     - (f) the instrument is in `_held_unmapped` → `f"unmapped exness position on {name}"`.
  3. Daily loss: `_realized_today()` pages `client.call("getDealsHistory", params={"from": <UTC midnight ISO>, "limit": 200})`, then `params={"cursor": next_cursor, "limit": 200}` while `has_more` is true, and computes the day's result over every deal whose `type` is not `balance` (deposits and withdrawals are excluded): add `float(deal["profit"]["amount"])` when the type is in `_PNL_DEAL_TYPES = frozenset({"close", "swap_fee", "admin_fee", "dividend"})` and the deal carries `profit`, and subtract `abs(float(deal.get("commission") or 0))` for every non-`balance` deal (commission is always a cost, whatever sign the API reports). When the result is `<= -daily_loss_cap`, reject with `"daily loss cap reached"`. Any `ExnessApiError` while paging (including a 429) rejects the order with `f"daily loss check failed: {e.code}"`, so the cap fails closed.
  4. Open position for `order.subscription_id` in `_positions`: same direction → REJECTED `"position already open for subscription"`; opposite direction → close it with `_send_tracked("closePosition", order, kind="close", position_id=pid, path_params={"position_id": pid})`.
  5. Otherwise check the grid: `cond = await client.conditions(name)`, `lots = units_to_lots(...)`; when `lots is None` or `lots_to_units(lots, contract_size) != order.quantity`, log `exness.order_rejected_presubmit` with `reason="not_normalized"` and reject with `"quantity not normalized to the exness lot grid"`. This guarantees the fill quantity will equal the order quantity. Then `_send_tracked("openPosition", order, kind="open", json_body={"instrument": name, "side": "buy"|"sell", "volume": str(lots), "stop_loss_price": format_price(order.sl_price, cond["point_digits"]), **({"take_profit_price": format_price(order.tp_price, cond["point_digits"])} if order.tp_price else {})})`.
  6. `_send_tracked(op, order, *, kind, position_id=None, path_params=None, json_body=None)`: `rid = str(order.id)`; register `_inflight[rid]` and `_pending_ack.add(rid)`; `ack = await client.call(op, path_params=path_params, json_body=json_body, idempotency_key=rid)` (the client retries transport errors with the same key and never retries a 429). On `ExnessApiError` with `code` `"TRANSPORT"` or `"REQUEST_RATE_LIMIT"`, set `_needs_snapshot = True` so new orders wait for an idempotent snapshot reconcile; on any `ExnessApiError` drop `_inflight[rid]` and return REJECTED with `f"{e.code}: {e.message}"`. On success record `_acked_at[rid] = time.monotonic()`, log info `exness.order_submitted` with `order_id`, `operation_id`, `instrument`, `kind`, `volume` and `volume_min`, start `asyncio.create_task(self._watch_operation(rid, ack["operation_id"]))`, and return `OrderResult(order_id=rid, broker_order_id=ack["operation_id"], status=SUBMITTED, submitted_at, sl_price, tp_price, side)`. In `finally`, `_pending_ack.discard(rid)`, and if `rid in self._early`, schedule `asyncio.create_task(self._notify(self._early.pop(rid)))`, so `OrderAppService.submit` finishes `order.submit(...)` under its lock first.
  7. `_watch_operation(rid, operation_id)`: sleep `_FILL_TIMEOUT_S = 15`; then up to 4 times: return if `rid in _seen_terminal`; read `status` from `client.call("getOperationStatus", path_params={"operation_id": operation_id})`; on `confirmed`, call `_recover_fill(rid)` and return; on `rejected` or `failed`, deliver `OrderResult(order_id=rid, status=CANCELLED, error_message=f"{error_code}: {error_message}")` through `_deliver` and return; on `pending`, sleep 15 s and repeat. After the loop, log an error `exness.operation_unresolved` and set `_needs_snapshot = True`. The whole body sits in `try/except Exception` that logs `exness.watch_failed` and sets `_needs_snapshot = True` (a 429 on a poll is not retried here); it never raises.
  8. `_recover_fill(rid)`: page `getDealsHistory` from the inflight acked time with `instrument=<name>`, take the first deal of the inflight `kind` (`open` or `close`), apply it exactly as a `success` transaction would (T7.5 step 4), and then run `_reconcile_snapshot()`.
  9. Every function stays ≤ 60 lines.
- **Success criteria:** No order can bypass the cap, the SL rule, the minimum lot or the snapshot gate, and every acknowledged request reaches a terminal outcome or blocks new orders.
- **Verify:** no verification needed; T7.6 covers this module.

<!-- Updated: Validation Session 1 - exception-safe dispatch; two-way snapshot reconciliation; account currency from getAccountDetails -->
### T7.5 `broker.py`, the events path, reconciliation and account state
- **Goal:** Fills, async rejections and broker-side closes reach the engine exactly once; the listener never dies; reconnects and restarts reconcile against the snapshot in both directions.
- **Target files and symbols:** `ExnessBroker.connect`, `disconnect`, `_on_event`, `_on_snapshot`, `_close_missing`, `_on_transaction`, `_apply_deal`, `_deliver`, `_notify`, `_reconcile_snapshot`, `get_positions`, `get_balance`, `cancel_order`, `subscribe_order_updates` and `unsubscribe_order_updates`.
- **Steps:**
  1. `connect()` starts `ExnessStream(client, f"/v1/server-events/accounts/{account}/ws/events", on_message=self._on_event, on_connect=self._on_stream_connect, stale_after_s=None)` as a task and sets `_connected`. `_on_stream_connect` sets `_snapshot_ready = False` and sends `{"id":"tx","subscribe":{"event":"transactions"}}`; the server answers with a fresh `trading_state_snapshot`. `disconnect()` closes the stream and cancels the task.
  2. `_on_event(frame)` dispatches inside `try/except Exception` (logging an error `exness.event_handler_failed`, never raising): `trading_state_snapshot` → `_on_snapshot(payload)`; `transaction_event` → `_on_transaction(frame)`; `hmr_snapshot` or `hmr_update` → info `exness.hmr_event`; `account_state_event` is ignored.
  3. `_on_snapshot(snapshot)`:
     - `repo_open = [p for p in await position_repository.find_open() if p.symbol.endswith(":EXNESS")]`;
     - rebuild `_positions` and `_held_unmapped`: for each snapshot position, `composite = composite_for(pos["instrument"])` and the repo candidates with that symbol and matching side (`buy`→LONG, `sell`→SHORT). Exactly one → map it. None or several → add the instrument to `_held_unmapped` and log an error `exness.position_unmapped` with `instrument` and `reason` (`no_match` or `ambiguous`);
     - each repo position with no snapshot counterpart → `_close_missing(pos)`;
     - set `_snapshot_ready = True` and `_needs_snapshot = False` only when no inflight request is still unresolved.
  4. `_close_missing(pos)`: page `getDealsHistory` from `pos.opened_at` with the instrument filter and take the latest `close` deal. When found, publish `OrderFilledEvent(order_id=generate_id_str(), subscription_id=pos.subscription_id, symbol=pos.symbol, side=<opposite of pos.side>, filled_quantity=pos.quantity, filled_price=float(deal["price"]))` and log info `exness.position_closed_while_away`. When not found, add the instrument to `_held_unmapped` and log an error `exness.position_missing_close_deal`.
  5. `_on_transaction(event)`:
     - `rid = event.get("client_request_id")`. When `rid` is set and `rid in self._seen_terminal`, return (dedupe).
     - `rid` set and `status == "success"`: `_apply_deal(rid, deal)` for the payload deal of the inflight `kind`. `_apply_deal` maps an `open` deal's `position_id` into `_positions` or removes a `close` deal's position, builds `OrderResult(order_id=rid, broker_order_id=event["operation_id"], status=FILLED, filled_quantity=lots_to_units(Decimal(deal["volume"]), contract_size), filled_price=float(deal["price"]), side=...)`, and logs `exness.order_filled` with `order_id` and `ack_to_fill_ms=int((time.monotonic()-self._acked_at.pop(rid, now))*1000)`.
     - `rid` set and `status` is `rejected` or `failed`: `OrderResult(order_id=rid, status=CANCELLED, error_message=f"{error_code}: {error_message}")` and a warning `exness.order_rejected_async`.
     - In both `rid` cases: add `rid` to `_seen_terminal`, drop `_inflight[rid]`, and `await self._deliver(result)`.
     - No `rid` and the payload has a `close` deal whose `position_id` is in `_positions`: publish `OrderFilledEvent(order_id=generate_id_str(), subscription_id=held.subscription_id, symbol=held.symbol, side=<opposite of held side>, filled_quantity=held.units, filled_price=float(deal["price"]))` on `event_bus`, remove the position and log info `exness.position_closed_by_broker` with `reason` from the matching order when present.
  6. `_deliver(result)`: if `result.order_id in self._pending_ack`, store it in `self._early`; otherwise `await self._notify(result)`. `_notify(result)` calls each callback inside its own `try/except Exception` (warning `exness.callback_failed`) and never raises.
  7. `_reconcile_snapshot()`: `await self._on_snapshot(await client.call("getTradingStateSnapshot"))`.
  8. `get_balance()` reads `(await client.call("getTradingStateSnapshot"))["account_state"]` and returns `AccountBalance(total_equity=float(equity), available_balance=float(equity)-float(used_margin), currency=<settings.currency from client.call("getAccountDetails"), cached>, margin_used=float(used_margin), unrealized_pnl=float(equity)-float(balance))`.
  9. `get_positions()` maps snapshot positions to `PositionAggregate.open(subscription_id=<mapped or "">, symbol=composite_for(instrument), side=..., entry_price=float(open_price), quantity=lots_to_units(...))`.
  10. `cancel_order(broker_order_id)` logs a warning `exness.cancel_unsupported` and returns False, because this adapter places market orders only.
- **Success criteria:** Every path is mapped, and nothing raises out of the WS listener.
- **Verify:** no verification needed; T7.6 covers this module.

<!-- Updated: Validation Session 1 - fixture-based tests for every live-money finding -->
<!-- Updated: Validation Session 1 - follow-up: loss-cap expectations with commission and dividend; 429 order case -->
### T7.6 Broker tests (recorded fixtures)
- **Goal:** Pin every safety rule, the event mapping and recovery against recorded API shapes.
- **Target files and symbols:** `tests/core_test/infra/exness/test_broker.py`
- **Steps:**
  1. Fake client: `AsyncMock` with `conditions` returning `{"contract_size":"100","volume_min":"0.01","volume_step":"0.01","volume_max":"200","point_digits":2}` and `call` routed by operation id: `getDealsHistory` returns pages built from `fixtures/deals.json` (keep its envelope; set `deal` objects and amounts per test), `openPosition`/`closePosition` return `{"operation_id":"op1","client_request_id":"<id>","status":"accepted"}`, `getTradingStateSnapshot` returns `fixtures/snapshot.json` with positions set per test, `getOperationStatus` per test. Feed a snapshot before order tests unless a test says otherwise. Orders use quantity `1.0` (0.01 lots) unless stated.
  2. Rejections with no order call (assert no `openPosition` call): a LIMIT order; `sl_price=None`; `daily_loss_cap=None`; no snapshot received yet; an instrument in `_held_unmapped`; quantity `7.9` (not normalized).
  3. Loss cap with cap `50`, using the recorded deals envelope:
     - two pages (`has_more: true` + `next_cursor`, then `has_more: false`): page 1 holds a `close` deal with `profit.amount "-40"` and `commission "2"` plus a `balance` deal of `+1000`; page 2 holds a `close` deal of `-5` and a `dividend` deal of `-4`. The result is `-51`, so the order is REJECTED with `"daily loss cap reached"`, and page 2 was requested with `cursor`;
     - the same pages without the `dividend` deal give `-47`, and the order is sent;
     - the same pages with `commission "-2"` instead of `"2"` give the same results (commission counts as a cost whatever its sign);
     - a lone `balance` deal of `-1000` (a withdrawal) gives `0`, and the order is sent;
     - `getDealsHistory` raising `ExnessApiError(429, "REQUEST_RATE_LIMIT", "x")` rejects with `"daily loss check failed: REQUEST_RATE_LIMIT"`.
  4. `normalize_quantity("XAUUSD:EXNESS", 7.9)` returns `1.0` and logs `exness.lots_clamped`; `normalize_quantity(..., 0.5)` returns None and logs `exness.order_rejected_presubmit`.
  5. An entry `transaction_event` (`success`, deal `{type:"open", volume:"0.01", price:"2345.10", position_id:"p1", direction:"buy"}`) calls the callback once with `FILLED`, `filled_quantity == 1.0` and `filled_price == 2345.10`; a duplicate event does not call it again.
  6. An event that arrives while the id is in `_pending_ack` is delivered exactly once, after `submit_order` returns (make `call("openPosition")` invoke `_on_event` before returning).
  7. A `rejected` event with `error_message "TRADING_RULE_INSUFFICIENT_MARGIN"` produces `CANCELLED` with the code in `error_message`.
  8. After the entry fill, an event with no `client_request_id` and a `close` deal for `p1` publishes one `OrderFilledEvent` with side `SELL` and the mapped `subscription_id`.
  9. With `p1` held, an opposite-direction order calls `closePosition` with `path_params={"position_id": "p1"}` and the order id as key, registers it in `_pending_ack` during the call, and its `success` close event delivers `FILLED` once.
  10. A same-direction order is REJECTED.
  11. Missed fill: no event arrives; with `_FILL_TIMEOUT_S` patched to 0, `getOperationStatus` returning `confirmed` and a deals page holding the `open` deal, the callback receives one `FILLED` and `p1` is mapped.
  12. Lost ACK or 429: `call("openPosition")` raising `ExnessApiError(0, "TRANSPORT", "x")`, and separately `ExnessApiError(429, "REQUEST_RATE_LIMIT", "x")`, each return REJECTED, make exactly one `openPosition` call, and set `_needs_snapshot`; the next order is rejected with `"awaiting trading snapshot reconciliation"` until `_reconcile_snapshot()` runs.
  13. Restart: a snapshot with one position matching one open repo position maps it; a snapshot position with no repo match puts its instrument in `_held_unmapped`; an open repo `XAUUSD:EXNESS` position absent from the snapshot publishes one synthetic close `OrderFilledEvent` priced from the latest `close` deal.
  14. A callback that raises does not propagate out of `_on_event`, and a later event is still delivered.
  15. Under `capture_logs()`, no captured event contains the API key string.
- **Success criteria:** All tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_broker.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - clamp to fill to position integration test -->
### T7.7 Clamp → fill → position integration test
- **Goal:** Prove that a clamped size is normalized before order creation, so the fill passes through `OrderAppService` into `PositionAppService` without a quantity mismatch.
- **Target files and symbols:** `tests/engine_test/test_exness_clamp_fill_position.py`
- **Steps:**
  1. Build a real `EventBus`, `OrderAppService` and `PositionAppService` over in-memory or testcontainers repositories (follow `tests/engine_test/test_reconcile_restart_resume_integration.py` for repository setup), and `await position_app_service.start()`.
  2. Build `ExnessBroker` over the T7.6 fake client, feed it an empty snapshot, and `await broker.subscribe_order_updates(order_app_service.on_order_update)`.
  3. `size = await broker.normalize_quantity("XAUUSD:EXNESS", 7.9)`; create a MARKET BUY `OrderAggregate` with `quantity=size` and an SL; `await order_app_service.submit(order, broker)`.
  4. Feed a `success` `transaction_event` with `client_request_id=str(order.id)` and an `open` deal of volume `"0.01"`.
  5. Assert `size == 1.0`, the order status is `FILLED`, and `position_app_service.get(order.subscription_id).quantity == 1.0`.
- **Success criteria:** The clamp-to-position path works end to end.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/engine_test/test_exness_clamp_fill_position.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - factory refuses exness while the switch is off; no available-type change -->
### T7.8 Broker factory entry `exness`, refused while live trading is off
- **Goal:** `BrokerFactory` can build an `ExnessBroker` only when `EXNESS_LIVE_TRADING` is true and the client is configured.
- **Target files and symbols:** `app/di/adapters.py` → `BrokerFactory.__init__(self, event_bus: EventBus, settings: Settings, exness_client: ExnessClient, position_repository: PositionRepository)` and `create`; `app/di/services.py` → `default_broker_config`
- **Steps:**
  1. Add the branch `elif broker_type == "exness":`. If `not self._settings.exness_live_trading`, raise `ValueError("exness broker is disabled: EXNESS_LIVE_TRADING is false")`. If `not self._exness_client.is_configured`, raise `ValueError("exness broker requires EXNESS_* settings")`. Otherwise return `ExnessBroker(self._exness_client, self._event_bus, self._position_repository, daily_loss_cap=config.get("exness_daily_loss_cap"), max_lots=config.get("exness_max_lots"))`.
  2. `get_available_types()` stays `["paper", "okx"]`; selection is the go-live plan's decision.
  3. Add `"exness_daily_loss_cap": settings.exness_daily_loss_cap` and `"exness_max_lots": settings.exness_max_lots` to `default_broker_config`.
  4. `test_reconcile_restart_resume_integration.py`: construct `BrokerFactory` with the new arguments (a Settings stub with `exness_live_trading=False`, an unconfigured `ExnessClient`, and the test's own position repository). The current construction is `BrokerFactory(event_bus)` at line 69; read the surrounding lines to find the position repository variable name.
  5. `test_di_resolution_characterization.py`: `get_available_types() == ["paper","okx"]` still holds, and `create("exness", {})` raises `ValueError` whose message contains `EXNESS_LIVE_TRADING is false`.
- **Success criteria:** The paper and OKX branches are byte-identical.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/integration/test_di_resolution_characterization.py tests/engine_test/test_reconcile_restart_resume_integration.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - D2 proof that live trading stays off -->
### T7.9 Proof that live trading stays off
- **Goal:** With `EXNESS_LIVE_TRADING=false`, the app boots, `BrokerFactory` refuses `exness`, and no Exness order endpoint can be called.
- **Target files and symbols:** `tests/app_test/integration/test_exness_live_trading_off.py`
- **Steps:**
  1. Build `create_container(settings)` with test settings that carry a valid-looking Exness configuration (generated 128-hex secret key, `https://<U2 api host>` base URL, account id, API key) and `exness_live_trading=False`; patch `ExnessClient._http` with an `httpx.MockTransport` that records requests.
  2. Assert `(await container.get(ExnessClient)).is_configured` is True, `(await container.get(SyncPolicies)).policy_for("XAUUSD:EXNESS")` is not None, and `(await container.get(BrokerFactory)).create("exness", {})` raises `ValueError` containing `EXNESS_LIVE_TRADING is false`.
  3. Assert `await client.call("openPosition", json_body={}, idempotency_key="order-00001")` raises `ExnessApiError` with `code == "LIVE_TRADING_DISABLED"`, and the transport recorded no request whose path contains `/positions`.
  4. Close the container.
- **Success criteria:** D2's "off" half holds in tests.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/integration/test_exness_live_trading_off.py tests/baseline/test_app_boot_smoke.py -q` exits 0 with `passed`. `grep -rnE '"(openPosition|closePosition)"' src | grep -v "core/infra/exness/client.py\|core/infra/exness/broker.py" | wc -l` prints `0`.

<!-- Updated: Validation Session 1 - gate includes the ratchet; Windows-safe metrics -->
### T7.10 Phase gate
- **Goal:** Full green.
- **Target files and symbols:** whole repo
- **Steps:**
  1. `just test 2>&1 | tail -n 3`
  2. `uv run ruff check`
  3. `uv run pyright`
  4. `uv run lint-imports`
  5. The venue command from Phase 02 T2.6.
  6. `uv run python scripts/code_metrics.py --ratchet`
  7. `uv run python scripts/code_metrics.py --out .cache/metrics.json`
- **Success criteria:** Green, the ratchet holds, and no function over 60 lines in `exness/broker.py`.
- **Verify:**
  - Steps 1–4 meet the same pass conditions as Phase 04 T4.6.
  - Step 5's count equals the baseline.
  - Step 6 exits 0 (on failure follow the Failure Protocol; the remedy is restructuring, never a higher ceiling).
  - `uv run python -c "import json;d=json.load(open('.cache/metrics.json'));print([f for f in d['functions_over_60'] if 'exness' in f])"` prints `[]`.

<!-- Updated: Validation Session 1 - ratchet re-measured at the end of the Exness phases -->
### T7.11 Ratchet re-measure after the Exness code
- **Goal:** The Exness code did not raise either metric, and the ceiling moves down if it improved.
- **Target files and symbols:** `plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-after-exness.json`, `pyproject.toml` `[tool.code-metrics]`
- **Steps:**
  1. `uv run python scripts/code_metrics.py --out plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-after-exness.json`
  2. For each of `max_tiny_share` and `max_delegations`, when the new measured value is lower than the current ceiling, set the ceiling to the new value. Never raise it.
- **Success criteria:** Both measured values are at or below the Phase 05 ceiling, and the ceiling equals the lower of the two measurements.
- **Verify:** `uv run python -c "import json,tomllib;a=json.load(open('plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-after-refactor.json'));b=json.load(open('plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-after-exness.json'));c=tomllib.load(open('pyproject.toml','rb'))['tool']['code-metrics'];print(b['tiny_share']<=a['tiny_share'] and b['delegations']<=a['delegations'] and c['max_tiny_share']==min(a['tiny_share'],b['tiny_share']) and c['max_delegations']==min(a['delegations'],b['delegations']))"` prints `True`.

<!-- Updated: Validation Session 1 - shipped switched off; post-deploy check of the switch -->
### T7.12 Ship (broker switched off)
- **Goal:** The broker code is deployed and cannot trade.
- **Target files and symbols:** git
- **Steps:**
  1. `git add -A src tests pyproject.toml plans/261009-0858-exness-venue-lean-sync-refactor`
  2. `git commit -m "feat(exness): add exness broker behind a default-off live trading switch"`
  3. Ask the user for approval, then merge, push and watch CI as in Phase 01 T1.7 steps 4-6.
  4. `ssh -i "$KEY" "$HOST" "docker exec pocketquant-app python -c \"from pocketquant.core.config import get_settings;print(get_settings().exness_live_trading)\""`
- **Success criteria:** Deployed with live trading off.
- **Verify:** `gh run watch` exits 0, and the CI log `=== Verdict:` line contains `, 0 failures)`. Step 4 prints `False`.

## Verification
T7.3 (engine wiring), T7.6 (safety, mapping and recovery), T7.7 (clamp to position), T7.8 (factory), T7.9 (live off), T7.10 (gate) and T7.11 (ratchet re-measure).

<!-- Updated: Validation Session 1 - stop-and-ask list for this phase -->
## Stop-and-ask
- Any change that would enable live Exness trading or set `EXNESS_LIVE_TRADING=true`, anywhere (config, tests run against prod, `pocketquant-config`).
- Any change that adds a per-subscription broker field, a public API or OpenAPI change for broker selection, or `exness` to `get_available_types`.
- A request to raise `EXNESS_MAX_LOTS` or to place any order.
- The ratchet would need a higher ceiling.
- A step would delete Binance or OKX code, or a test failure stays unexplained.

<!-- Updated: Validation Session 1 - follow-up: OKX wiring risk removed; reject-reset and 429 risks added -->
## Risks
- **A fill arrives before the ACK** (M/H). Handled by the `_pending_ack` and `_early` stash with the `create_task` hand-off; T7.6 step 6 covers it.
- **A fill is lost during a WS outage or restart** (M/H). Mitigation: same-key retries on transport errors, `getOperationStatus` polling, deals-based recovery and two-way snapshot reconciliation; orders are blocked until the snapshot is reconciled (T7.6 steps 11–13).
- **Resetting `hitnrun2` on risk rejection and zero size changes paper and backtest behaviour** (M/M): the strategy can now re-enter after such a signal instead of going silent. This is the user's decision. If an existing test pins the old silent behaviour, STOP and ask before changing its assertion.
- **A 429 is surfaced, not retried** (M/M): an order hit by a 429 is REJECTED and blocks new orders until a snapshot reconcile; a data call fails for this run and the next scheduled run retries.
- **A hedging account opens a hedge instead of closing** (M/H). Mitigation: an opposite-direction order closes the held position, and a same-direction order is rejected.
- **The sizer cannot reach the minimum lot on a small account** (H/L while live is off). Mitigation: `normalize_quantity` returns None, the strategy is told, and `exness.order_rejected_presubmit` is logged; the spike's `sizer_feasibility` line records the facts for the go-live plan.

<!-- Updated: Validation Session 1 - follow-up: loss-cap deal set -->
## Security
Every live-money rule is in code: SL required, the minimum-lot cap, the daily loss cap from real deals (close, swap, admin fee, dividend and commission; deposits and withdrawals excluded), market orders only, and the snapshot gate. Two independent locks keep live trading off: `BrokerFactory` refuses `exness` and the client refuses order operations while `EXNESS_LIVE_TRADING` is false. Secrets are never logged (T7.6 step 15). Authentication on mutation routes is not built here; it is a written precondition of the go-live plan.

## Rollback
`git revert` the merge commit and push. No data shape changes: no subscription field was added, and the new settings are optional.

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
