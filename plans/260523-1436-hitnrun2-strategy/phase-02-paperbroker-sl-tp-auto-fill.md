---
phase: 2
title: "PaperBroker SL/TP auto-fill"
status: completed
priority: P1
effort: "3-4h"
dependencies: []
---

# Phase 2: PaperBroker SL/TP auto-fill

## Overview

Make `PaperBroker` actually close positions when bar range crosses `sl_price` or `tp_price`. Today the broker stores SL/TP on the lot but never emits exit fills — strategies that set SL/TP have orphan positions. Without this fix, hitnrun2 (and any future SL/TP-using strategy) cannot loop.

## Requirements

**Functional:**
- For each open lot tracked by PaperBroker, on every new bar:
  - LONG lot: if `bar.low <= sl_price` → emit SELL fill at `sl_price` (after slippage = `sl_price * (1 - slippage)`).
  - LONG lot: else if `bar.high >= tp_price` → emit SELL fill at `tp_price` (after slippage = `tp_price * (1 - slippage)`).
  - SHORT lot: if `bar.high >= sl_price` → emit BUY fill at `sl_price * (1 + slippage)`.
  - SHORT lot: else if `bar.low <= tp_price` → emit BUY fill at `tp_price * (1 + slippage)`.
- Emit a synthetic `OrderResult` with `status=FILLED`, `filled_quantity=lot.quantity`, `side=opposite_of_entry`, `order_id=<new uuid>`.
- Notify subscribers via `_notify_callbacks` so `BacktestResultCollector.on_fill` records the exit.
- Update `_balance` and clear `_positions[position_key]` via `_execute_fill` reuse OR direct manipulation.

**Non-functional:**
- Idempotent: once a lot fires SL or TP, it is removed — no double-fire.
- Deterministic ordering when bar covers both SL and TP: **SL fires first** (conservative — assume worst path inside the bar). Document this contract in the docstring.
- No behaviour change for orders without SL/TP set.

## Architecture

```
BarCompletedEvent
       │
       ▼
PaperBroker._on_bar_completed (new @event_handler)
       │
       ├── filter positions by event.symbol
       ├── for each open position with sl/tp:
       │     ├── decide SL vs TP vs none using bar.high/low
       │     └── if hit:
       │           ├── compute fill price (with slippage)
       │           ├── _execute_fill(synthetic_exit_order)
       │           └── _notify_callbacks(synthetic_result)
       └── set_current_price(symbol, bar.close)  # piggyback
```

PaperBroker currently does **not** subscribe to the EventBus. Add `event_bus` to `__init__` (Optional — None disables auto-fill so unit tests can drive directly). Register handler via `get_event_registry().register_instance(self, event_bus)` on connect.

**Lot-level SL/TP tracking.** Current `PaperBroker` stores `PositionAggregate` per `strategy_id:symbol`. SL/TP is on the `OrderAggregate` at submit time, not retained on the position. Two options:

- **Option A (minimal):** add `sl_price`/`tp_price` to `PositionAggregate`. Persist on open; clear on close. Net change small.
- **Option B (lot tracker):** mirror `LotTracker` in broker. Heavy — duplicate state.

**Choose A.** Smaller surface area. `PositionAggregate.open()` already in `pocketquant.core.domain.position.entities`.

## Related Code Files

**Modify:**
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/brokers/paper/paper_broker.py` — add `event_bus` arg, `_on_bar_completed` handler, SL/TP fill logic.
- `packages/pocketquant-core/src/pocketquant/core/domain/position/entities.py` — add `sl_price: float | None`, `tp_price: float | None` to `PositionAggregate` (verify field doesn't already exist).
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/brokers/paper/__init__.py` — re-export unchanged.
- `packages/pocketquant-api/src/pocketquant/api/di/broker_factory.py` (or wherever broker is wired) — pass event_bus when creating PaperBroker.
- `packages/pocketquant-backtest/src/pocketquant/backtest/handlers/run/handler.py` — when creating fresh PaperBroker for backtest, pass `event_bus=self._event_bus`.
- `packages/pocketquant-trading/src/pocketquant/trading/jobs/backtest_strategy_loader.py` — same as above.

**Create:** none.

## Implementation Steps

1. **Verify position aggregate field gap.** Read `position/entities.py` — confirm `sl_price`/`tp_price` not already present. If present, skip step 2.
2. **Add sl/tp to PositionAggregate.** Default `None`. Setter on `_execute_fill` BUY open (entry).
3. **Add event_bus to PaperBroker.__init__.** Optional `event_bus: EventBus | None = None`. Store `self._event_bus`. Do NOT auto-subscribe in `__init__` (constructor would have side effects). Subscribe in `connect()` only when `event_bus is not None`.
4. **Implement `_on_bar_completed(event: BarCompletedEvent)`:**
   ```python
   async def _on_bar_completed(self, event):
       async with self._lock:
           # Update current price snapshot
           self._current_prices[event.symbol.upper()] = event.close
           # Walk open positions matching this symbol
           to_close: list[tuple[str, PositionAggregate, float, OrderSide]] = []
           for key, pos in self._positions.items():
               if pos.is_closed or pos.symbol != event.symbol:
                   continue
               sl, tp = pos.sl_price, pos.tp_price
               hit = self._check_sl_tp(pos, sl, tp, event.high, event.low)
               if hit is not None:
                   exit_price, exit_side = hit
                   to_close.append((key, pos, exit_price, exit_side))
           for key, pos, exit_price, exit_side in to_close:
               await self._fire_synthetic_exit(key, pos, exit_price, exit_side)
   ```
5. **`_check_sl_tp(pos, sl, tp, bar_high, bar_low)`** returns `(fill_price, exit_side)` or `None`. Rules in Requirements above. SL takes precedence when both hit in same bar.
6. **`_fire_synthetic_exit(key, pos, exit_price, exit_side)`** builds `OrderAggregate` with `strategy_id=pos.strategy_id, symbol=pos.symbol, side=exit_side, order_type=MARKET, quantity=pos.quantity, price=exit_price, sl_price=None, tp_price=None`, then calls `self._execute_fill(order, exit_price)` and notifies. Reuses existing close logic in `_execute_fill`.
7. **Wire event_bus into PaperBroker creation.** Three call-sites:
   - `pocketquant-api/.../di/...` — DI provider.
   - `pocketquant-backtest/.../handlers/run/handler.py` — `broker = PaperBroker(..., event_bus=self._event_bus)`.
   - `pocketquant-trading/.../jobs/backtest_strategy_loader.py` — same.
8. **Update `pocketquant-backtest/optimization/grid_optimization_app_service.py` and any other PaperBroker construction call sites** — search with `Grep "PaperBroker("`. Pass event_bus or accept None gracefully.
9. **Verify reset() clears SL/TP too** since it clears positions.
10. **Compile check.** `uv run python -c "from pocketquant.core.infrastructure.brokers.paper.paper_broker import PaperBroker; PaperBroker()"`.

## Success Criteria

- [ ] `PositionAggregate` carries `sl_price`/`tp_price`.
- [ ] `PaperBroker(event_bus=bus)` subscribes to `BarCompletedEvent` on `connect()`.
- [ ] In a hand-written test (phase 4): open LONG at 100 with SL=98 TP=104; feed bar(low=97, high=101) → emits SELL at ~98 (minus slippage); position closed.
- [ ] In a hand-written test: open SHORT at 100 with SL=102 TP=96; feed bar(low=99, high=103) → SELL fired first because SL hit (102) → emits BUY at ~102.
- [ ] Bar that covers both SL and TP: SL fires, TP never fires for that lot.
- [ ] Existing PaperBroker tests still pass (`test_lot_tracker.py`, `test_result_collector_fifo.py` exercise lot tracker not broker; safe).

## Risk Assessment

- **Risk:** Adding `event_bus` to PaperBroker constructor breaks every existing call-site. **Mitigation:** make it `Optional`, default `None` ⇒ auto-fill disabled. Backtest path explicitly opts in. Live trading uses real broker, paper-only.
- **Risk:** `_on_bar_completed` async handler runs *before* strategy's `on_bar` on the same event — race. EventBus likely dispatches handlers in registration order; if strategy registers first (via StrategyAppService), strategy fills entry first, then broker checks exit on the same bar. **Mitigation:** document in PaperBroker docstring — "bar's entry order fires same bar; SL/TP check uses bar high/low so entry bar is excluded only if entry price = bar.close > sl threshold". Phase 4 tests both ordering scenarios.
- **Risk:** SL and TP both hit in same bar — random which wins in reality. **Mitigation:** deterministic SL-first contract (worst case). Documented.
- **Risk:** Synthetic exit emits OrderFilledEvent? Check `_notify_callbacks` flow — confirm BacktestResultCollector receives result. If yes, positions+equity update. If not, manual `_event_bus.publish(OrderFilledEvent(...))` needed.
