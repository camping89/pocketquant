---
phase: 7
title: "Exness broker behind the live-trading switch (off)"
status: completed
priority: P1
effort: 6d
dependencies: [6]
---

# Phase 07: Exness broker behind the live-trading switch (off)

<!-- Updated: 2026-10-13 develop reshape - develop paths, trade subscription, BrokerFactory in core/infra, new 429 rule -->
## Develop status
- Base branch: `develop` (`develop-sync` tracking `origin/develop` in `D:/w/_me/algotrading/pocketquant`); ship with `git push origin develop-sync:develop`. Deploys are approved; there is no `master` step.
- On develop the engine lives in `engine/strategy/` and `engine/execution/`, the broker port is `IBrokerPort` and requires a trade subscription (`subscribe_trades`), `BrokerFactory` lives in `core/infra/brokers/broker_factory.py`, and the live strategy picks its broker from `StrategyConfig.broker` (default `"paper"`). The broker is a strategy setting, independent of the symbol suffix.
- Phase 06 delivered `ExnessClient` (`core/infra/exness/exness_client.py`), the mappers and `ExnessStream`; this phase reuses them.

## Completion (2026-10-19)
- T7.1–T7.11 pass. The worktree branch is `develop` tracking `origin/develop`, so the push is `git push origin develop`.
- `just test`: 1132 passed; the only failures are the 4 Windows `time.tzset` tests. lint-imports keeps 8 contracts; ruff and pyright are clean on `src` and the touched tests.
- Ratchet: delegations rose from 87 to 93. Four are `IBrokerPort` members (`subscribe_/unsubscribe_order_updates`, `subscribe_/unsubscribe_trades`); `_reconcile_snapshot` and `_publish_close_fill` are the other two. The coordinator approved `max_delegations = 93`, which supersedes "never a higher ceiling" here and in T7.11 (precedent `3f6c6e6`). `max_tiny_share` moved down to the measured 0.4867. Because of that approval, the T7.11 Verify one-liner (written against 77) is replaced by: measured values ≤ ceiling, and `max_tiny_share` is the lower of 0.4877 and the measurement.
- Deviations from the task text, taken on kongming counsel:
  - the stop-loss rule and the daily loss cap apply to opens only, because blocking an exit would keep the risk open;
  - a close is rejected unless its quantity equals the held units, since `OrderAggregate.fill` raises on a mismatch;
  - `_on_snapshot` keeps positions it already mapped from its own fills, and a deferred reconcile runs once the last in-flight request settles;
  - a broker-side partial close reduces the held position;
  - a trade is emitted after a fill delivered through the pre-ACK stash;
  - a fill for a dropped request id marks the instrument unmapped.
- Go-live blockers (kongming review; live trading is off, so none blocks this commit):
  - a request left in `_inflight` (unresolved operation, or a recovered fill with no deal) keeps the snapshot gate closed until restart. A lost ACK or 429 also sets `_needs_snapshot`, and nothing schedules the reconcile;
  - `_on_snapshot` replaces `_positions` after awaits, so a fill applied concurrently can be lost;
  - a fill that arrives during an ACK call that then fails with TRANSPORT is delivered after the order was already rejected, so the engine never records the position.

## Context Links
- Spike journal `docs/journals/2026-10-13-exness-api-spike.md` (recorded fixtures in `tests/core_test/infra/exness/fixtures/`, written `fixtures/` below): account currency USD; the recorded conditions (`fixtures/conditions_{XAUUSD,EURUSD,BTCUSD}.json`: `contract_size`, `volume_min`, `volume_step`, `volume_max`, `point_digits`); the deals envelope `{items: [{event_time, deal}], has_more, range}` (`fixtures/deals.json`, only `balance` deals recorded, so tests fill `close` deals from the spec schema inside that envelope); the snapshot shape `{account_state: {balance, equity, used_margin, leverage}, orders, positions}` (`fixtures/snapshot.json`); the events WS acknowledgement `{"id": "spike-tx", "code": "200"}` (`fixtures/events_snapshot.json`); the deals window must stay inside `history_age_days` (use `ExnessClient.deals_window_days()`); the sizer cannot reach one minimum lot on the current balance.
- `IBrokerPort`: `src/pocketquant/core/domain/brokers/broker_port.py:13` (abstract members :22-104, including `subscribe_trades` :92, which must fire a `TradeClosedEvent` after the matching fill). `OrderResult` (`core/domain/brokers/value_objects.py:8`, `commission` :23, `is_success` :26 is true for every status except `REJECTED`).
- Engine, `src/pocketquant/engine/strategy/strategy_app_service.py`: `load_strategy` :102 (broker from `config.broker` at :120), `_on_bar_completed` :237 (`except` :258), `_on_quote_received` :266 (submit :283), `_on_order_filled` :293, `_process_signal` :334 (`no_broker_for_strategy` :339, `signal_rejected_by_risk` :354, sizing :366, `zero_position_size` :376, submit :381), `_get_or_create_broker` :426 (`create` :437, `subscribe_trades` :441, pooled per `(broker_type, contract_spec)`).
- `src/pocketquant/engine/execution/order_app_service.py`: `submit` :34 (exception path returns `REJECTED`), `on_order_update` :174 with the CANCELLED branch at :202-205. `on_order_update` has no live subscriber today (the only `subscribe_order_updates` caller is the backtest, `engine/backtest/backtest_app_service.py:114`), so async fills from a live broker never reach it.
- Order state machine: `src/pocketquant/core/domain/order/entities.py` (`_VALID_TRANSITIONS` :52-56; `SUBMITTED → REJECTED` is not allowed, so an async rejection maps to `CANCELLED`; `fill` :140-149 raises unless the fill quantity equals the order quantity).
- Strategies: `IStrategyService.on_order_filled` (`src/pocketquant/core/domain/strategy/strategy_service_interface.py:76`). `HitNRun2StrategyService` (`core/domain/strategy/services/hitnrun2_strategy_service.py:44`) sets `_open_direction` when it emits a signal (:105, :113) and clears it only on an opposite fill (:125-128), so a rejected entry silences it. `EngulfingStrategyService` sets it on the entry fill (`engulfing_strategy_service.py:143-147`) and needs no change.
- Events: `OrderCancelledEvent(order_id, subscription_id, reason)` (`core/domain/order/events.py:45`), `OrderFilledEvent`, `TradeClosedEvent` (`core/domain/position/events.py:40`; fields `position_id`, `subscription_id`, `symbol`, `direction`, `entry_*`, `quantity`, `exit_*`, `pnl`, `commission`). `LiveTradeCollector` persists live trades from the bus (`engine/live/live_trade_collector.py`).
- PaperBrokerAdapter broker-side exit pattern: `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py:797` (exit fill price) and :837 (publishes `OrderFilledEvent`); `_order_callbacks` :135.
- `PositionAppService(event_bus, position_repository, symbol_lookup=None)` (`engine/execution/position_app_service.py:17-21`, `start` :31, `get` :128). `PositionRepository.find_open` (`core/infra/persistence/repositories/position_repository.py:29`). `PositionAggregate.opened_at` (`core/domain/position/entities.py:37`).
- `BrokerFactory` (`src/pocketquant/core/infra/brokers/broker_factory.py:9`, `__init__(event_bus)` :17, `create` :20, `get_available_types` :74 returns `["paper", "okx"]` and stays so). It is provided by `broker_factory = provide(BrokerFactory, scope=Scope.APP)` (`app/di/adapters.py:35`) and built directly as `BrokerFactory(event_bus)` in four tests (`tests/core_test/infra/brokers/paper_broker_commission_test.py:181`, `tests/engine_test/test_contract_spec_wiring.py:63`, `test_live_trade_collector_integration.py:83`, `test_reconcile_restart_resume_integration.py:69`). `default_broker_config` is built in `ServicesProvider.get_strategy_engine` (`app/di/services.py:158-166`).
- Client: `ExnessClient.call` with operation ids, `conditions()`, `deals_window_days()`, the live gate `LIVE_TRADING_DISABLED`, same-key retries on transport errors, up to 3 retries of a 429 on non-order calls, and no retry of a 429 on `openPosition`/`closePosition` (Phase 06 T6.6).
- Spec: `openPosition` takes `instrument`, `side`, `volume`, `stop_loss_price`, `take_profit_price` and returns `202 {operation_id, client_request_id, status}`. The events WS sends `trading_state_snapshot` on subscribe and `transaction_event` with `operation_id`, `client_request_id`, `status` (`success|rejected|failed`), `error_code`, `error_message` and `payload.{orders, positions, deals}`. A position is `{position_id, direction, instrument, volume, open_price}`; a deal is `{deal_id, type, direction, instrument, volume, price, position_id, profit: {amount, currency}, commission, create_time}`. `getOperationStatus` returns `pending|confirmed|rejected|failed` for 24 h. WS streams never replay; state is recovered from the snapshot and trading history. Deal types: `open, close, balance, null_compensation, admin_fee, swap_fee, dividend, exness_dollar`.

## Goal
An `ExnessBrokerAdapter` that converts quantity to lots inside the adapter, always attaches SL, never exceeds the minimum lot unless `EXNESS_MAX_LOTS` is raised, enforces a daily loss cap from real deals, blocks orders until the trading snapshot is reconciled, recovers missed fills and restarts, maps async fills and broker-side closes into the existing engine flow exactly once, and emits a `TradeClosedEvent` per closed position. It ships switched off: while `EXNESS_LIVE_TRADING` is false (the default), `BrokerFactory` refuses `exness`, and the client refuses every order call. No public API or OpenAPI change is made and no subscription is pointed at it; selecting `config.broker = "exness"` belongs to the later go-live plan. No live order is placed. Engine fixes ship with it: async fill wiring for brokers that declare async fills (only Exness; PaperBrokerAdapter and OKXBrokerAdapter stay byte-identical), a broker quantity hook so fills always match the order quantity, and rejection delivery on every path where a signal never ends in a fill, so `hitnrun2` never goes silent.

## Files to Create or Modify
- Create: `src/pocketquant/core/infra/brokers/exness/__init__.py`, `src/pocketquant/core/infra/brokers/exness/exness_broker_adapter.py`
- Create tests: `tests/core_test/infra/brokers/exness/{__init__,test_exness_broker_adapter,test_exness_broker_factory}.py`, `tests/engine_test/test_strategy_reject_delivery.py`, `tests/engine_test/test_async_broker_fill_wiring.py`, `tests/engine_test/test_exness_clamp_fill_position.py`, `tests/app_test/integration/test_exness_live_trading_off.py`
- Create report: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-after-exness.json`
- Modify:
  - `src/pocketquant/core/config.py`
  - `src/pocketquant/core/domain/brokers/broker_port.py`, `src/pocketquant/core/domain/strategy/strategy_service_interface.py`, `src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`
  - `src/pocketquant/engine/strategy/strategy_app_service.py`, `src/pocketquant/engine/execution/order_app_service.py`
  - `src/pocketquant/core/infra/brokers/broker_factory.py`, `src/pocketquant/app/di/adapters.py` (`BrokerFactory` provider), `src/pocketquant/app/di/services.py` (`default_broker_config`)
  - `pyproject.toml` (`[tool.code-metrics]`, only to lower the ceiling in T7.11)

## Tasks

<!-- Updated: 2026-10-13 develop reshape - no feature branch; base recorded for diffs -->
### T7.1 Base and risk settings
- **Goal:** Start from current develop; the risk-cap configuration keys exist and stay optional.
- **Target files and symbols:** git; `src/pocketquant/core/config.py` → `Settings.exness_daily_loss_cap: float | None = None` and `Settings.exness_max_lots: float | None = None`
- **Steps:**
  1. `git switch develop-sync && git pull --ff-only && git rev-parse HEAD > .cache/phase07-base`
  2. Add the two fields after `exness_rate_fraction`.
- **Success criteria:** Both fields are optional; the live switch is unchanged.
- **Verify:** `uv run pyright src/pocketquant/core/config.py` reports `0 errors`.

### T7.2 Broker hooks and strategy rejection hook
- **Goal:** A broker can normalize an order quantity before the order is created and can declare that it reports fills asynchronously, and a strategy can learn that its entry did not go through. Paper and OKX behaviour is unchanged.
- **Target files and symbols:** `IBrokerPort.normalize_quantity` and `IBrokerPort.fills_async` in `core/domain/brokers/broker_port.py`; `IStrategyService.on_order_rejected` in `core/domain/strategy/strategy_service_interface.py`; `HitNRun2StrategyService.on_order_rejected` in `core/domain/strategy/services/hitnrun2_strategy_service.py`
- **Steps:**
  1. Add a non-abstract method to `IBrokerPort`: `async def normalize_quantity(self, symbol: str, quantity: float) -> float | None: return quantity`, and a class attribute `fills_async: bool = False`. Neither `PaperBrokerAdapter` nor `OKXBrokerAdapter` is edited, so both keep `False`.
  2. Add a non-abstract method to `IStrategyService` next to `on_order_filled` (:76): `async def on_order_rejected(self, reason: str) -> None: return None`, with a one-line docstring saying it is called when an entry signal does not end in a fill (risk rejection, zero size, broker minimum, broker rejection or cancellation).
  3. In `HitNRun2StrategyService`, override `on_order_rejected` to set `self._open_direction = None`.
- **Success criteria:** The ports gain two defaults; no venue name enters the domain.
- **Verify:** no verification needed; T7.3 covers these hooks.

### T7.3 Engine wiring and tests
- **Goal:** Normalized sizes reach the order, every signal that does not end in a fill reaches the strategy as a rejection, and only brokers with `fills_async = True` (Exness) deliver async fills into `OrderAppService.on_order_update`.
- **Target files and symbols:** `StrategyAppService._process_signal`, `_on_quote_received`, `_on_bar_completed`, `_get_or_create_broker` and a new `@event_handler(OrderCancelledEvent) _on_order_cancelled`; `OrderAppService.on_order_update`
- **Steps:**
  1. `_process_signal`, existing early returns: before the `return` after each of `no_broker_for_strategy` (:339), `signal_rejected_by_risk` (:354) and `zero_position_size` (:376), add `await strategy.on_order_rejected(...)` with `"no broker"`, the risk `reason`, or `"zero position size"`.
  2. `_process_signal`: after the `size <= 0` check, add `size = await broker.normalize_quantity(signal.symbol, size)`. When it is None, log info `order_quantity_below_broker_minimum` with `strategy_id`, `await strategy.on_order_rejected("quantity below broker minimum")` and return.
  3. `_process_signal`: after `result = await self._order_app_service.submit(order, broker)` (:381), add `if not result.is_success: await strategy.on_order_rejected(result.error_message or "rejected")`. In `_on_quote_received` (:283), keep the submit result and apply the same check.
  4. `_on_bar_completed`: in the existing `except Exception` branch (:258), when a signal had been produced, also `await strategy.on_order_rejected(str(e))` inside its own `try/except` that logs `strategy_on_order_rejected_error`.
  5. `OrderAppService.on_order_update`, CANCELLED branch (:202-205): after the save, publish `OrderCancelledEvent(order_id=result.order_id, subscription_id=order.subscription_id, reason=result.error_message or "")`.
  6. `StrategyAppService`: add `@event_handler(OrderCancelledEvent) async def _on_order_cancelled(self, event)` that finds the loaded strategy by `event.subscription_id` (the same key `_on_order_filled` uses) and awaits `strategy.on_order_rejected(event.reason)` inside the same try/except logging shape.
  7. `_get_or_create_broker`: after `broker = self._broker_factory.create(broker_type, config)` (:437), add `if broker.fills_async: await broker.subscribe_order_updates(self._order_app_service.on_order_update)` next to the existing `subscribe_trades` call. A pooled broker is returned before this line, so it is subscribed once.
  8. `tests/engine_test/test_strategy_reject_delivery.py`:
     - `HitNRun2StrategyService` with `_open_direction` set has it cleared after `on_order_rejected("x")`;
     - on paper (a real `PaperBrokerAdapter` from `BrokerFactory(EventBus())` and a loaded `HitNRun2StrategyService` with `_open_direction = Direction.LONG`): a risk handler stub whose `validate` returns `(False, "max exposure")` leads to no `submit_order` call and `_open_direction is None` after `_process_signal`;
     - on paper, with `PositionCalculatorDomainService.calculate` monkeypatched to return a zero `PositionCalculation`, `_process_signal` leaves `_open_direction is None`;
     - `_process_signal` with a fake broker whose `submit_order` returns `REJECTED` calls `strategy.on_order_rejected` once;
     - a fake broker whose `normalize_quantity` returns None leads to no `submit_order` call and one `on_order_rejected`;
     - `on_order_update` with `CANCELLED` for a pending order publishes one `OrderCancelledEvent`, and the registered strategy's `on_order_rejected` runs once.
  9. `tests/engine_test/test_async_broker_fill_wiring.py`:
     - a fake `IBrokerPort` named `fake` with `fills_async = True` whose `submit_order` returns `OrderResult(status=SUBMITTED, broker_order_id="op1")`; load a strategy through a stub factory returning it and submit through `OrderAppService.submit`;
     - invoke the stored callback with `OrderResult(order_id=<id>, broker_order_id="op1", status=FILLED, filled_quantity=<order quantity>, filled_price=10)`;
     - assert one `OrderFilledEvent` was published and, after `await position_app_service.start()`, `PositionAppService.get(sub_id)` is not None;
     - a `PaperBrokerAdapter` from the factory is not subscribed: `len(broker._order_callbacks) == 0` after `load_strategy`;
     - `IBrokerPort.fills_async`, `PaperBrokerAdapter.fills_async` and `OKXBrokerAdapter.fills_async` are all `False` (class attributes only; no OKX instance is built and no OKX test file is touched).
- **Success criteria:** The wiring is generic, with no venue name in the engine.
- **Verify:** `uv run python -m pytest tests/engine_test/test_strategy_reject_delivery.py tests/engine_test/test_async_broker_fill_wiring.py tests/engine_test tests/backtest_test -q` exits 0. `grep -c '"exness"' src/pocketquant/engine/strategy/strategy_app_service.py` prints `0`. `git diff --name-only $(cat .cache/phase07-base) -- src/pocketquant/core/infra/brokers/paper src/pocketquant/core/infra/brokers/okx tests/core_test/infra/brokers | grep -v /exness/` prints nothing.

<!-- Updated: 2026-10-13 develop reshape - deals envelope items[].deal; 429 handling follows the new rule -->
### T7.4 `exness_broker_adapter.py`, the order path
- **Goal:** Submission enforces every live-safety rule before any HTTP call, and every accepted request is tracked until a terminal outcome.
- **Target files and symbols:** `src/pocketquant/core/infra/brokers/exness/exness_broker_adapter.py` → `class ExnessBrokerAdapter(IBrokerPort)`. Constructor: `(client: ExnessClient, event_bus: EventBus, position_repository: PositionRepository, daily_loss_cap: float | None, max_lots: float | None)`. Members: `name -> "exness"`, class attribute `fills_async = True`, `is_connected`, `normalize_quantity`, `submit_order`, `_realized_today`, `_deals`, `_send_tracked`, `_watch_operation`. State: `_positions: dict[str, _Held]` (position_id → subscription_id, symbol, `PositionSide`, units, lots, open price, open time), `_held_unmapped: set[str]` (instrument names), `_inflight: dict[str, _Inflight]` (client request id → subscription_id, symbol, side, instrument, `kind` open|close, position_id, acked wall time), `_pending_ack: set[str]`, `_early: dict[str, OrderResult]`, `_acked_at: dict[str, float]`, `_seen_terminal: set[str]`, `_snapshot_ready = False`, `_needs_snapshot = False`.
- **Steps:**
  1. `normalize_quantity(symbol, quantity)`: `name = instrument_name(symbol)`; when None, log a warning `exness.order_rejected_presubmit` with `reason="unknown_instrument"` and return None. `cond = await client.conditions(name)`; `lots = units_to_lots(Decimal(str(quantity)), contract_size=Decimal(cond["contract_size"]), volume_min=..., volume_step=..., volume_max=..., max_lots=Decimal(str(max_lots)) if max_lots else None)`. When None, log `exness.order_rejected_presubmit` with `reason="below_min_lot"`, `quantity` and `volume_min`, and return None. When `lots` is below the raw lot count, log a warning `exness.lots_clamped` with `requested` and `sent`. Return `lots_to_units(lots, Decimal(cond["contract_size"]))`.
  2. `submit_order(order)` returns `OrderResult(status=REJECTED, error_message=...)` without any HTTP call, in this order:
     - (a) `order.order_type != OrderType.MARKET` → `"exness adapter supports market orders only"`;
     - (b) `order.sl_price is None` → `"stop loss required"`;
     - (c) `daily_loss_cap is None` → `"EXNESS_DAILY_LOSS_CAP not set"`;
     - (d) `not self._snapshot_ready or self._needs_snapshot` → `"awaiting trading snapshot reconciliation"`;
     - (e) `instrument_name(order.symbol)` is None → `"unknown exness instrument"`;
     - (f) the instrument is in `_held_unmapped` → `f"unmapped exness position on {name}"`.
  3. `_deals(**params)` pages `client.call("getDealsHistory", params={**params, "limit": 200})`, then `params={"cursor": body["next_cursor"], "limit": 200}` while `has_more` is true and `next_cursor` is set, and yields `item["deal"]` for each entry of `items`. Every `from` it is given is clamped to at least `now - await client.deals_window_days()` days.
  4. Daily loss: `_realized_today()` reads `_deals(from=<UTC midnight ISO>)` and sums over every deal whose `type` is not `balance` (deposits and withdrawals are excluded): add `float(deal["profit"]["amount"])` when the type is in `_PNL_DEAL_TYPES = frozenset({"close", "swap_fee", "admin_fee", "dividend"})` and the deal carries `profit`, and subtract `abs(float(deal.get("commission") or 0))` for every non-`balance` deal (commission is always a cost, whatever sign the API reports). When the result is `<= -daily_loss_cap`, reject with `"daily loss cap reached"`. Any `ExnessApiError` while paging rejects the order with `f"daily loss check failed: {e.code}"`, so the cap fails closed; a 429 reaches here only after the client's 3 retries.
  5. Open position for `order.subscription_id` in `_positions`: same direction → REJECTED `"position already open for subscription"`; opposite direction → close it with `_send_tracked("closePosition", order, kind="close", position_id=pid, path_params={"position_id": pid})`.
  6. Otherwise check the grid: `cond = await client.conditions(name)`, `lots = units_to_lots(...)`; when `lots is None` or `lots_to_units(lots, contract_size) != order.quantity`, log `exness.order_rejected_presubmit` with `reason="not_normalized"` and reject with `"quantity not normalized to the exness lot grid"`. This guarantees the fill quantity equals the order quantity. Then `_send_tracked("openPosition", order, kind="open", json_body={"instrument": name, "side": "buy"|"sell", "volume": str(lots), "stop_loss_price": format_price(order.sl_price, cond["point_digits"]), **({"take_profit_price": format_price(order.tp_price, cond["point_digits"])} if order.tp_price else {})})`.
  7. `_send_tracked(op, order, *, kind, position_id=None, path_params=None, json_body=None)`: `rid = str(order.id)`; register `_inflight[rid]` and `_pending_ack.add(rid)`; `ack = await client.call(op, path_params=path_params, json_body=json_body, idempotency_key=rid)` (the client retries transport errors with the same key and never retries a 429 on these two operations). On `ExnessApiError` with `code` `"TRANSPORT"` or `"REQUEST_RATE_LIMIT"`, set `_needs_snapshot = True` so new orders wait for an idempotent snapshot reconcile; on any `ExnessApiError` drop `_inflight[rid]` and return REJECTED with `f"{e.code}: {e.message}"`. On success record `_acked_at[rid] = time.monotonic()`, log info `exness.order_submitted` with `order_id`, `operation_id`, `instrument`, `kind`, `volume` and `volume_min`, start `asyncio.create_task(self._watch_operation(rid, ack["operation_id"]))`, and return `OrderResult(order_id=rid, broker_order_id=ack["operation_id"], status=SUBMITTED, submitted_at, sl_price, tp_price, side)`. In `finally`, `_pending_ack.discard(rid)`, and if `rid in self._early`, schedule `asyncio.create_task(self._notify(self._early.pop(rid)))`, so `OrderAppService.submit` finishes `order.submit(...)` under its lock first.
  8. `_watch_operation(rid, operation_id)`: sleep `_FILL_TIMEOUT_S = 15`; then up to 4 times: return if `rid in _seen_terminal`; read `status` from `client.call("getOperationStatus", path_params={"operation_id": operation_id})`; on `confirmed`, call `_recover_fill(rid)` and return; on `rejected` or `failed`, deliver `OrderResult(order_id=rid, status=CANCELLED, error_message=f"{error_code}: {error_message}")` through `_deliver` and return; on `pending`, sleep 15 s and repeat. After the loop, log an error `exness.operation_unresolved` and set `_needs_snapshot = True`. The whole body sits in `try/except Exception` that logs `exness.watch_failed` and sets `_needs_snapshot = True`; it never raises.
  9. `_recover_fill(rid)`: read `_deals(from=<inflight acked wall time>, instrument=<name>)`, take the first deal of the inflight `kind` (`open` or `close`), apply it exactly as a `success` transaction would (T7.5 step 5), and then run `_reconcile_snapshot()`.
  10. Every function stays ≤ 60 lines.
- **Success criteria:** No order can bypass the cap, the SL rule, the minimum lot or the snapshot gate, and every acknowledged request reaches a terminal outcome or blocks new orders.
- **Verify:** no verification needed; T7.6 covers this module.

<!-- Updated: 2026-10-13 develop reshape - trade subscription emits TradeClosedEvent, as IBrokerPort requires on develop -->
### T7.5 `exness_broker_adapter.py`, the events path, trades, reconciliation and account state
- **Goal:** Fills, async rejections and broker-side closes reach the engine exactly once, each closed position emits one `TradeClosedEvent` after its fill, the listener never dies, and reconnects and restarts reconcile against the snapshot in both directions.
- **Target files and symbols:** `ExnessBrokerAdapter.connect`, `disconnect`, `_on_event`, `_on_snapshot`, `_close_missing`, `_on_transaction`, `_apply_deal`, `_emit_trade`, `_deliver`, `_notify`, `_reconcile_snapshot`, `get_positions`, `get_balance`, `cancel_order`, `subscribe_order_updates`, `unsubscribe_order_updates`, `subscribe_trades` and `unsubscribe_trades`.
- **Steps:**
  1. `connect()` starts `ExnessStream(client, f"/v1/server-events/accounts/{account}/ws/events", on_message=self._on_event, on_connect=self._on_stream_connect, stale_after_s=None)` as a task and sets `_connected`. `_on_stream_connect` sets `_snapshot_ready = False` and sends `{"id": "tx", "subscribe": {"event": "transactions"}}`; the server acknowledges with `{"id", "code"}` and then sends a fresh `trading_state_snapshot`. `disconnect()` closes the stream and cancels the task.
  2. `_on_event(frame)` dispatches inside `try/except Exception` (logging an error `exness.event_handler_failed`, never raising): an `{"id", "code"}` acknowledgement → DEBUG; `trading_state_snapshot` → `_on_snapshot(payload)`; `transaction_event` → `_on_transaction(frame)`; `hmr_snapshot` or `hmr_update` → info `exness.hmr_event`; `account_state_event` is ignored.
  3. `_on_snapshot(snapshot)`:
     - `repo_open = [p for p in await position_repository.find_open() if p.symbol.endswith(":EXNESS")]`;
     - rebuild `_positions` and `_held_unmapped`: for each snapshot position, `composite = composite_for(pos["instrument"])` and the repo candidates with that symbol and matching side (`buy`→LONG, `sell`→SHORT). Exactly one → map it. None or several → add the instrument to `_held_unmapped` and log an error `exness.position_unmapped` with `instrument` and `reason` (`no_match` or `ambiguous`);
     - each repo position with no snapshot counterpart → `_close_missing(pos)`;
     - set `_snapshot_ready = True` and `_needs_snapshot = False` only when no inflight request is still unresolved.
  4. `_close_missing(pos)`: read `_deals(from=pos.opened_at, instrument=<name>)` (clamped to the history window) and take the latest `close` deal. When found, publish `OrderFilledEvent(order_id=generate_id_str(), subscription_id=pos.subscription_id, symbol=pos.symbol, side=<opposite of pos.side>, filled_quantity=pos.quantity, filled_price=float(deal["price"]))`, then `_emit_trade(...)`, and log info `exness.position_closed_while_away`. When not found, add the instrument to `_held_unmapped` and log an error `exness.position_missing_close_deal`.
  5. `_on_transaction(event)`:
     - `rid = event.get("client_request_id")`. When `rid` is set and `rid in self._seen_terminal`, return (dedupe).
     - `rid` set and `status == "success"`: `_apply_deal(rid, deal)` for the payload deal of the inflight `kind`. `_apply_deal` maps an `open` deal's `position_id` into `_positions` or removes a `close` deal's position, builds `OrderResult(order_id=rid, broker_order_id=event["operation_id"], status=FILLED, filled_quantity=lots_to_units(Decimal(deal["volume"]), contract_size), filled_price=float(deal["price"]), commission=abs(float(deal.get("commission") or 0)), side=...)`, and logs `exness.order_filled` with `order_id` and `ack_to_fill_ms=int((time.monotonic()-self._acked_at.pop(rid, now))*1000)`.
     - `rid` set and `status` is `rejected` or `failed`: `OrderResult(order_id=rid, status=CANCELLED, error_message=f"{error_code}: {error_message}")` and a warning `exness.order_rejected_async`.
     - In both `rid` cases: add `rid` to `_seen_terminal`, drop `_inflight[rid]`, `await self._deliver(result)`, and for a `close` deal then `await self._emit_trade(held, deal)`.
     - No `rid` and the payload has a `close` deal whose `position_id` is in `_positions`: publish `OrderFilledEvent(order_id=generate_id_str(), subscription_id=held.subscription_id, symbol=held.symbol, side=<opposite of held side>, filled_quantity=held.units, filled_price=float(deal["price"]))` on `event_bus`, then `_emit_trade(held, deal)`, remove the position and log info `exness.position_closed_by_broker` with `reason` from the matching order when present.
  6. `_emit_trade(held, deal)` builds `TradeClosedEvent(position_id=deal["position_id"], subscription_id=held.subscription_id, symbol=held.symbol, direction="LONG"|"SHORT", entry_price=held.open_price, entry_time=held.opened_at, quantity=held.units, exit_price=float(deal["price"]), exit_time=<deal create_time>, sl_price, tp_price, pnl=float(deal["profit"]["amount"]), commission=abs(float(deal.get("commission") or 0)))` and calls each trade callback inside its own `try/except Exception` (warning `exness.trade_callback_failed`). It always runs after the fill is delivered, as `IBrokerPort.subscribe_trades` requires. `subscribe_trades` appends the callback; `unsubscribe_trades` clears the list.
  7. `_deliver(result)`: if `result.order_id in self._pending_ack`, store it in `self._early`; otherwise `await self._notify(result)`. `_notify(result)` calls each order callback inside its own `try/except Exception` (warning `exness.callback_failed`) and never raises.
  8. `_reconcile_snapshot()`: `await self._on_snapshot(await client.call("getTradingStateSnapshot"))`.
  9. `get_balance()` reads `(await client.call("getTradingStateSnapshot"))["account_state"]` and returns `AccountBalance(total_equity=float(equity), available_balance=float(equity)-float(used_margin), currency=<settings.currency from client.call("getAccountDetails"), cached>, margin_used=float(used_margin), unrealized_pnl=float(equity)-float(balance))`.
  10. `get_positions()` maps snapshot positions to `PositionAggregate.open(subscription_id=<mapped or "">, symbol=composite_for(instrument), side=..., entry_price=float(open_price), quantity=lots_to_units(...))`.
  11. `cancel_order(broker_order_id)` logs a warning `exness.cancel_unsupported` and returns False, because this adapter places market orders only.
- **Success criteria:** Every path is mapped, trades are emitted once per close, and nothing raises out of the WS listener.
- **Verify:** no verification needed; T7.6 covers this module.

<!-- Updated: 2026-10-13 develop reshape - recorded conditions and deals envelope; 429 order case; trade emission -->
### T7.6 Broker tests (recorded fixtures)
- **Goal:** Pin every safety rule, the event mapping, trade emission and recovery against recorded API shapes.
- **Target files and symbols:** `tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py`
- **Steps:**
  1. Fake client: `AsyncMock` with `conditions` returning `fixtures/conditions_XAUUSD.json` (contract size 100, volume 0.01/0.01/200, `point_digits` 3), `deals_window_days` returning 29, and `call` routed by operation id: `getDealsHistory` returns pages built on the `fixtures/deals.json` envelope (`items[].deal`, `has_more`; set `next_cursor` and the deals per test), `openPosition`/`closePosition` return `{"operation_id": "op1", "client_request_id": "<id>", "status": "accepted"}`, `getTradingStateSnapshot` returns `fixtures/snapshot.json` with positions set per test, `getOperationStatus` per test. Feed a snapshot before order tests unless a test says otherwise. Orders use quantity `1.0` (0.01 lots) unless stated.
  2. Rejections with no order call (assert no `openPosition` call): a LIMIT order; `sl_price=None`; `daily_loss_cap=None`; no snapshot received yet; an instrument in `_held_unmapped`; quantity `7.9` (not normalized).
  3. Loss cap with cap `50`:
     - two pages (`has_more: true` + `next_cursor`, then `has_more: false`): page 1 holds a `close` deal with `profit.amount "-40"` and `commission "2"` plus a `balance` deal of `+1000`; page 2 holds a `close` deal of `-5` and a `dividend` deal of `-4`. The result is `-51`, so the order is REJECTED with `"daily loss cap reached"`, and page 2 was requested with `cursor`;
     - the same pages without the `dividend` deal give `-47`, and the order is sent;
     - `commission "-2"` instead of `"2"` gives the same results (commission counts as a cost whatever its sign);
     - a lone `balance` deal of `-1000` (a withdrawal) gives `0`, and the order is sent;
     - `getDealsHistory` raising `ExnessApiError(429, "REQUEST_RATE_LIMIT", "x")` (what the client raises after its 3 retries) rejects with `"daily loss check failed: REQUEST_RATE_LIMIT"`;
     - a `from` older than 29 days is clamped to now minus 29 days.
  4. `normalize_quantity("XAUUSD:EXNESS", 7.9)` returns `1.0` and logs `exness.lots_clamped`; `normalize_quantity(..., 0.5)` returns None and logs `exness.order_rejected_presubmit`; the open request's `stop_loss_price` has 3 decimals.
  5. An entry `transaction_event` (`success`, deal `{type:"open", volume:"0.01", price:"2345.100", position_id:"p1", direction:"buy"}`) calls the order callback once with `FILLED`, `filled_quantity == 1.0` and `filled_price == 2345.1`; a duplicate event does not call it again.
  6. An event that arrives while the id is in `_pending_ack` is delivered exactly once, after `submit_order` returns (make `call("openPosition")` invoke `_on_event` before returning).
  7. A `rejected` event with `error_message "TRADING_RULE_INSUFFICIENT_MARGIN"` produces `CANCELLED` with the code in `error_message`.
  8. After the entry fill, an event with no `client_request_id` and a `close` deal for `p1` (`profit.amount "-3.5"`, `commission "0.2"`) publishes one `OrderFilledEvent` with side `SELL` and the mapped `subscription_id`, and then one `TradeClosedEvent` reaches the trade callback with `pnl == -3.5`, `commission == 0.2` and `entry_price == 2345.1`.
  9. With `p1` held, an opposite-direction order calls `closePosition` with `path_params={"position_id": "p1"}` and the order id as key, registers it in `_pending_ack` during the call, and its `success` close event delivers `FILLED` once, followed by one `TradeClosedEvent`.
  10. A same-direction order is REJECTED.
  11. Missed fill: no event arrives; with `_FILL_TIMEOUT_S` patched to 0, `getOperationStatus` returning `confirmed` and a deals page holding the `open` deal, the callback receives one `FILLED` and `p1` is mapped.
  12. Lost ACK or 429 on the order: `call("openPosition")` raising `ExnessApiError(0, "TRANSPORT", "x")`, and separately `ExnessApiError(429, "REQUEST_RATE_LIMIT", "x")`, each return REJECTED, make exactly one `openPosition` call, and set `_needs_snapshot`; the next order is rejected with `"awaiting trading snapshot reconciliation"` until `_reconcile_snapshot()` runs.
  13. Restart: a snapshot with one position matching one open repo position maps it; a snapshot position with no repo match puts its instrument in `_held_unmapped`; an open repo `XAUUSD:EXNESS` position absent from the snapshot publishes one synthetic close `OrderFilledEvent` priced from the latest `close` deal and one `TradeClosedEvent`.
  14. A callback that raises does not propagate out of `_on_event`, and a later event is still delivered; the events acknowledgement `fixtures/events_snapshot.json` is ignored without error.
  15. Under `capture_logs()`, no captured event contains the API key string.
- **Success criteria:** All tests pass.
- **Verify:** `uv run python -m pytest tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py -q` exits 0.

### T7.7 Clamp → fill → position integration test
- **Goal:** Prove that a clamped size is normalized before order creation, so the fill passes through `OrderAppService` into `PositionAppService` without a quantity mismatch.
- **Target files and symbols:** `tests/engine_test/test_exness_clamp_fill_position.py`
- **Steps:**
  1. Build a real `EventBus`, `OrderAppService` and `PositionAppService` over the real-Mongo repositories used by `tests/engine_test/test_reconcile_restart_resume_integration.py` (its `db` fixture, :50-51), and `await position_app_service.start()`.
  2. Build `ExnessBrokerAdapter` over the T7.6 fake client, feed it an empty snapshot, and `await broker.subscribe_order_updates(order_app_service.on_order_update)`.
  3. `size = await broker.normalize_quantity("XAUUSD:EXNESS", 7.9)`; create a MARKET BUY `OrderAggregate` with `quantity=size` and an SL; `await order_app_service.submit(order, broker)`.
  4. Feed a `success` `transaction_event` with `client_request_id=str(order.id)` and an `open` deal of volume `"0.01"`.
  5. Assert `size == 1.0`, the order status is `FILLED`, and `position_app_service.get(order.subscription_id).quantity == 1.0`.
- **Success criteria:** The clamp-to-position path works end to end.
- **Verify:** `uv run python -m pytest tests/engine_test/test_exness_clamp_fill_position.py -q` exits 0.

<!-- Updated: 2026-10-13 develop reshape - factory in core/infra/brokers; keyword-only deps keep the four existing constructions unchanged -->
### T7.8 Broker factory entry `exness`, refused while live trading is off
- **Goal:** `BrokerFactory` can build an `ExnessBrokerAdapter` only when `EXNESS_LIVE_TRADING` is true and the client is configured; the paper and OKX branches and every existing `BrokerFactory(event_bus)` call stay unchanged.
- **Target files and symbols:** `src/pocketquant/core/infra/brokers/broker_factory.py` → `BrokerFactory.__init__(self, event_bus: EventBus, *, exness_client: ExnessClient | None = None, position_repository: PositionRepository | None = None, exness_live_trading: bool = False)` and `create`; `app/di/adapters.py` → `AdaptersProvider.get_broker_factory`; `app/di/services.py` → `default_broker_config`
- **Steps:**
  1. Add the keyword-only parameters and the branch `elif broker_type == "exness":` before the final `else`. If not `self._exness_live_trading`, raise `ValueError("exness broker is disabled: EXNESS_LIVE_TRADING is false")`. If `self._exness_client is None or not self._exness_client.is_configured or self._position_repository is None`, raise `ValueError("exness broker requires EXNESS_* settings")`. Otherwise return `ExnessBrokerAdapter(self._exness_client, self._event_bus, self._position_repository, daily_loss_cap=config.get("exness_daily_loss_cap"), max_lots=config.get("exness_max_lots"))`.
  2. `get_available_types()` stays `["paper", "okx"]`; selection is the go-live plan's decision.
  3. In `app/di/adapters.py`, replace `broker_factory = provide(BrokerFactory, scope=Scope.APP)` (:35) with `@provide(scope=Scope.APP) def get_broker_factory(self, event_bus: EventBus, settings: Settings, exness_client: ExnessClient, position_repository: PositionRepository) -> BrokerFactory` that passes the three keywords (`exness_live_trading=settings.exness_live_trading`).
  4. Add `"exness_daily_loss_cap": settings.exness_daily_loss_cap` and `"exness_max_lots": settings.exness_max_lots` to `default_broker_config` (`app/di/services.py:158-166`).
  5. `tests/core_test/infra/brokers/exness/test_exness_broker_factory.py`: `BrokerFactory(EventBus()).create("exness", {})` raises `ValueError` containing `EXNESS_LIVE_TRADING is false`; with `exness_live_trading=True` and no client it raises `requires EXNESS_* settings`; with `exness_live_trading=True` and a configured stub client it returns an `ExnessBrokerAdapter`; `get_available_types() == ["paper", "okx"]`.
- **Success criteria:** The paper and OKX branches are byte-identical, and no existing test file changes.
- **Verify:** `uv run python -m pytest tests/core_test/infra/brokers tests/engine_test/test_reconcile_restart_resume_integration.py tests/engine_test/test_contract_spec_wiring.py tests/engine_test/test_live_trade_collector_integration.py -q` exits 0.

<!-- Updated: 2026-10-13 develop reshape - production container with the real settings fixture; no tests/baseline -->
### T7.9 Proof that live trading stays off
- **Goal:** With `EXNESS_LIVE_TRADING=false`, the production container builds, `BrokerFactory` refuses `exness`, and no Exness order endpoint can be called.
- **Target files and symbols:** `tests/app_test/integration/test_exness_live_trading_off.py`
- **Steps:**
  1. Take the `settings` fixture (`tests/app_test/conftest.py:16`, real Mongo and Redis) and `model_copy(update=...)` it with a valid-looking Exness configuration (generated 128-hex secret key, `https://api.exness.com`, account id, API key) and `exness_live_trading=False`. Build `create_container(settings)`, resolve `client = await container.get(ExnessClient)` and replace `client._http` with an `httpx.AsyncClient` over a recording `httpx.MockTransport` (the same injection point as Phase 06 T6.7).
  2. Assert `client.is_configured` is True, the resolved `IDataProviderPort` routes `"exness"` to an `ExnessAdapter`, and `(await container.get(BrokerFactory)).create("exness", {})` raises `ValueError` containing `EXNESS_LIVE_TRADING is false`.
  3. Assert `await client.call("openPosition", json_body={}, idempotency_key="order-00001")` raises `ExnessApiError` with `code == "LIVE_TRADING_DISABLED"`, and the transport recorded no request whose path contains `/positions`.
  4. Close the container.
- **Success criteria:** D2's "off" half holds in tests.
- **Verify:** `uv run python -m pytest tests/app_test/integration/test_exness_live_trading_off.py tests/app_test/integration/test_app_standalone_runtime.py -q` exits 0. `grep -rnE '"(openPosition|closePosition)"' src | grep -v "core/infra/exness/exness_client.py\|core/infra/brokers/exness/exness_broker_adapter.py" | wc -l` prints `0`.

### T7.10 Phase gate
- **Goal:** Develop's gate holds.
- **Target files and symbols:** whole repo
- **Steps:**
  1. `uv run lint-imports`
  2. `uv run ruff check src $(git diff --name-only $(cat .cache/phase07-base) -- tests scripts)` and `uv run ruff format --check` on the same files
  3. `uv run pyright src $(git diff --name-only $(cat .cache/phase07-base) -- tests scripts)`
  4. `just test 2>&1 | tail -n 15`
  5. `uv run python scripts/code_metrics.py --ratchet`
  6. `uv run python scripts/code_metrics.py --out .cache/metrics-phase07.json`
- **Success criteria:** Green, the ratchet holds, and no function in `exness_broker_adapter.py` is over 60 lines.
- **Verify:**
  - Step 1 prints `Contracts: 8 kept, 0 broken.`
  - Steps 2 and 3 report 0 errors in `src/` and in every touched file (pre-existing debt in untouched test files is accepted).
  - Step 4 shows no new failure: the only failures are the 4 pre-existing Windows `time.tzset` tests.
  - Step 5 exits 0 (on failure follow the Failure Protocol; the remedy is restructuring, never a higher ceiling).
  - `uv run python -c "import json;d=json.load(open('.cache/metrics-phase07.json'));print([f for f in d['functions_over_60'] if 'exness' in f])"` prints `[]`.

<!-- Updated: 2026-10-13 develop reshape - ceiling frozen on develop (reports/metrics-develop-ratchet.json) -->
### T7.11 Ratchet re-measure after the Exness code
- **Goal:** The Exness code did not raise either metric above develop's frozen ceiling, and the ceiling moves down if a metric improved.
- **Target files and symbols:** `plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-after-exness.json`, `pyproject.toml` `[tool.code-metrics]` (`max_tiny_share = 0.48`, `max_delegations = 77` at :178-180, frozen from `reports/metrics-develop-ratchet.json`)
- **Steps:**
  1. `uv run python scripts/code_metrics.py --out plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-after-exness.json`
  2. For each of `max_tiny_share` and `max_delegations`, when the new measured value is lower than the current ceiling, set the ceiling to the new value. Never raise it.
- **Success criteria:** Both measured values are at or below the frozen ceiling, and the ceiling equals the lower of the frozen value and the new measurement.
- **Verify:** `uv run python -c "import json,tomllib;a=json.load(open('plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-develop-ratchet.json'));b=json.load(open('plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-after-exness.json'));c=tomllib.load(open('pyproject.toml','rb'))['tool']['code-metrics'];print(b['tiny_share']<=a['tiny_share'] and b['delegations']<=a['delegations'] and c['max_tiny_share']==min(a['tiny_share'],b['tiny_share']) and c['max_delegations']==min(a['delegations'],b['delegations']))"` prints `True`.

<!-- Updated: 2026-10-13 develop reshape - push develop-sync to develop -->
### T7.12 Ship (broker switched off)
- **Goal:** The broker code is deployed and cannot trade.
- **Target files and symbols:** git, VPS
- **Steps:**
  1. `git add -A src tests pyproject.toml plans/261009-0858-exness-venue-lean-sync-refactor && git commit -m "feat(exness): add exness broker behind a default-off live trading switch"`
  2. `git push origin develop-sync:develop`. Wait for the CI run whose `headSha` equals `git rev-parse HEAD`, then `gh run watch <databaseId> --exit-status`.
  3. `ssh -i "$KEY" "$HOST" "docker exec pocketquant-app python -c \"from pocketquant.core.config import get_settings;print(get_settings().exness_live_trading)\""` (`KEY` and `HOST` as in Phase 06 T6.19).
- **Success criteria:** Deployed with live trading off.
- **Verify:** `gh run watch <databaseId> --exit-status` exits 0, and `gh run view <databaseId> --log | grep "=== Verdict:" | grep -c ", 0 failures)"` prints a number ≥ 1. Step 3 prints `False`.

## Verification
T7.3 (engine wiring), T7.6 (safety, mapping, trades and recovery), T7.7 (clamp to position), T7.8 (factory), T7.9 (live off), T7.10 (gate) and T7.11 (ratchet re-measure).

## Stop-and-ask
- Any change that would enable live Exness trading or set `EXNESS_LIVE_TRADING=true`, anywhere (config, tests run against prod, `pocketquant-config`).
- Any change that sets `config.broker = "exness"` on a subscription, adds a public API or OpenAPI change for broker selection, or adds `exness` to `get_available_types`.
- A request to raise `EXNESS_MAX_LOTS` or to place any order.
- The ratchet would need a higher ceiling.
- A step would delete Binance, OKX or TradingView code, or a test failure stays unexplained.

## Risks
- **A fill arrives before the ACK** (M/H). Handled by the `_pending_ack` and `_early` stash with the `create_task` hand-off; T7.6 step 6 covers it.
- **A fill is lost during a WS outage or restart** (M/H). Mitigation: same-key retries on transport errors, `getOperationStatus` polling, deals-based recovery and two-way snapshot reconciliation; orders are blocked until the snapshot is reconciled (T7.6 steps 11–13).
- **Resetting `hitnrun2` on risk rejection and zero size changes paper and backtest behaviour** (M/M): the strategy can now re-enter after such a signal instead of going silent. This is the user's decision. If an existing test pins the old silent behaviour, STOP and ask before changing its assertion.
- **429 on an order is not retried** (M/M): the order is REJECTED and new orders wait for a snapshot reconcile. A 429 on a deals, snapshot or operation-status read is retried by the client up to 3 times; if it still fails, the loss check fails closed or the watcher sets `_needs_snapshot`.
- **Deals older than the history window are invisible** (L/M while live is off): `_close_missing` cannot price a close that happened more than 29 days ago; the instrument is held as unmapped and blocks new orders on it.
- **A hedging account opens a hedge instead of closing** (M/H). Mitigation: an opposite-direction order closes the held position, and a same-direction order is rejected.
- **The sizer cannot reach the minimum lot on a small account** (H/L while live is off). The spike recorded minimum balances of 41 836 USD (XAUUSD), 11 178 USD (EURUSD) and 8 336 USD (BTCUSD). `normalize_quantity` returns None, the strategy is told, and `exness.order_rejected_presubmit` is logged.

## Security
Every live-money rule is in code: SL required, the minimum-lot cap, the daily loss cap from real deals (close, swap, admin fee, dividend and commission; deposits and withdrawals excluded), market orders only, and the snapshot gate. Two independent locks keep live trading off: `BrokerFactory` refuses `exness` and the client refuses order operations while `EXNESS_LIVE_TRADING` is false. Secrets are never logged (T7.6 step 15). Authentication on mutation routes is not built here; it is a written precondition of the go-live plan.

## Rollback
`git revert` the phase commit and push it with `git push origin develop-sync:develop`. No data shape changes: no subscription field was added, no symbol-keyed collection or Redis key was added, and the new settings are optional.

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
