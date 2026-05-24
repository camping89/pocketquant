---
phase: 2
title: "PaperBroker emit OrderEvent + persist LIMIT non-fill"
status: pending
priority: P2
effort: "0.5d"
dependencies: [1]
---

# Phase 2: PaperBroker emit OrderEvent + persist LIMIT non-fill

## Overview

Augment `PaperBroker` to emit `OrderEvent` records on every status transition (SUBMITTED → FILLED/CANCELLED/REJECTED/EXPIRED, plus AUTO_SL_FILLED/AUTO_TP_FILLED triggered by bar-event auto-fill). Add LIMIT order support: orders that don't fill on current bar stay pending and are tracked until they (a) fill on a later bar, (b) are cancelled by strategy, or (c) expire at end of run. This is required for forward-test parity — strategies must not assume LIMIT fills happen instantly.

## Requirements

- Functional: Every PaperBroker order status change produces an `OrderEvent` record delivered alongside `OrderResult` via the callback channel
- Functional: LIMIT orders that can't fill on current price stay in `_pending_orders` queue; checked on each subsequent bar
- Functional: Cancel-on-EOR (end of run) — any LIMIT still pending when backtest finishes gets `EXPIRED` status emitted
- Functional: STOP orders behave like LIMIT for now (deferred separate logic — out of scope)
- Non-functional: `IBroker` interface stays unchanged (no new required methods); event emission is internal-then-callback
- Non-functional: Existing `test_hitnrun2_backtest.py` must pass without modification (hitnrun2 uses MARKET only)

## Architecture

### Current state (file:line refs from scout)

- `paper_broker.py:87-128 submit_order()` — synchronous fill, returns `OrderResult.status = FILLED` or `REJECTED`
- `paper_broker.py:279-302 _on_bar_completed()` — checks SL/TP, fires synthetic exit
- `paper_broker.py:325-356 _fire_synthetic_exit()` — creates synthetic `OrderAggregate`, executes fill
- No state machine, no event log

### New state machine

```
                  ┌────► REJECTED (insufficient balance, invalid symbol)
                  │
SUBMITTED ────────┼────► FILLED   (MARKET; or LIMIT when bar price crosses limit)
                  │
                  ├────► PARTIAL  (out of scope — flag for future)
                  │
                  ├────► CANCELLED (explicit cancel call)
                  │
                  └────► EXPIRED  (LIMIT/STOP still pending at end of run)
```

Each transition produces an `OrderEvent` with `(timestamp, from_status, to_status, reason)`.

### Reason codes (string constants)

- `"submit"` — initial SUBMITTED event
- `"market_fill"` — MARKET filled immediately
- `"limit_cross"` — LIMIT price crossed by bar
- `"auto_sl"` — synthetic exit from SL trigger
- `"auto_tp"` — synthetic exit from TP trigger
- `"user_cancel"` — strategy called cancel_order
- `"end_of_run"` — pending order at backtest finish
- `"insufficient_balance"` — REJECT reason
- `"invalid_symbol"` — REJECT reason

### Event delivery channel

Reuse existing `subscribe_order_updates(callback)` mechanism. `OrderResult` gets a new optional field `events: list[OrderEvent]` (delta since last callback) OR a separate callback `subscribe_order_event(callback)`. **Recommend the latter** — keeps `OrderResult` semantic clean (it's a fill result, not a lifecycle log).

```python
# paper_broker.py additions
async def subscribe_order_event(self, callback: OrderEventCallback) -> None: ...
async def unsubscribe_order_event(self) -> None: ...

# emission helper
async def _emit_event(self, order_id, from_status, to_status, reason) -> None:
    event = OrderEvent(timestamp=get_current_time(), from_status=..., to_status=..., reason=reason)
    self._order_events.setdefault(order_id, []).append(event)
    for cb in self._event_callbacks:
        await maybe_await(cb(order_id, event))
```

Result collector subscribes to both:
- `subscribe_order_updates(on_fill)` — handles Fill emission
- `subscribe_order_event(on_event)` — appends to in-memory `Order.events[]`

### LIMIT pending queue

```python
# new field
self._pending_orders: dict[str, _PendingOrder] = {}

@dataclass
class _PendingOrder:
    order: OrderAggregate
    submitted_at: datetime
    limit_price: float           # price level to trigger fill

# in submit_order():
if order.order_type == OrderType.LIMIT:
    cur_price = self._current_prices.get(order.symbol)
    if self._limit_fills_now(order, cur_price):
        return self._fill_immediately(order)
    self._pending_orders[order.id] = _PendingOrder(order, now, order.price)
    await self._emit_event(order.id, None, "SUBMITTED", "submit")
    return OrderResult(order_id=order.id, status=OrderStatus.SUBMITTED, ...)

# in _on_bar_completed(): check pending LIMITs against bar.high/bar.low
# BUY LIMIT fills when bar.low <= limit_price (price reached or crossed below)
# SELL LIMIT fills when bar.high >= limit_price
```

### End-of-run hook

`BacktestAppService.run()` after `replay_engine.replay()` completes:
```python
expired = await self._broker.expire_pending_orders()  # new method
# expired returns list of (order_id, OrderResult with EXPIRED status)
# collector receives them through normal callback channel
```

`PaperBroker.expire_pending_orders()` iterates `_pending_orders`, emits EXPIRED event + OrderResult with status=EXPIRED for each, clears the queue, returns count.

## Related Code Files

- **Create:**
  - `packages/pocketquant-core/src/pocketquant/core/infrastructure/brokers/paper/pending_orders.py` (if `_pending_orders` logic grows; otherwise inline in paper_broker.py — re-evaluate after impl)
- **Modify:**
  - `packages/pocketquant-core/src/pocketquant/core/infrastructure/brokers/paper/paper_broker.py` — add state machine, event emission, LIMIT pending queue, `expire_pending_orders()`, `subscribe_order_event()`, `unsubscribe_order_event()`
  - `packages/pocketquant-core/src/pocketquant/core/infrastructure/brokers/models.py` — extend `OrderResult` with new statuses (CANCELLED, REJECTED, EXPIRED already exist? check; add if missing)
  - `packages/pocketquant-core/src/pocketquant/core/domain/order/enums.py` — verify `OrderStatus` enum has SUBMITTED/FILLED/CANCELLED/REJECTED/EXPIRED; add EXPIRED if missing
  - `packages/pocketquant-backtest/src/pocketquant/backtest/engine/backtest_app_service.py` — call `broker.expire_pending_orders()` after replay
- **Delete:** none

## Implementation Steps

1. Audit `OrderStatus` enum in `core/domain/order/enums.py`. Add `EXPIRED` if missing.
2. Add `OrderEventCallback = Callable[[str, OrderEvent], None | Awaitable[None]]` type in `paper_broker.py` (or shared types file).
3. Add `_order_events: dict[str, list[OrderEvent]]` and `_event_callbacks: list[OrderEventCallback]` fields to `PaperBroker.__init__`.
4. Add `subscribe_order_event()` / `unsubscribe_order_event()` methods.
5. Add private `_emit_event()` helper.
6. Add `_pending_orders: dict[str, _PendingOrder]` field.
7. Modify `submit_order()`:
   - For MARKET: emit `SUBMITTED` event, fill, emit `FILLED` event
   - For LIMIT: check if fills now (current price crosses limit); if yes fill+emit, else queue + emit `SUBMITTED`
   - For REJECT path: emit `SUBMITTED` then `REJECTED` with reason
8. Modify `_on_bar_completed()`:
   - First scan SL/TP for open positions (existing logic, but now also emit `FILLED` event with reason=`auto_sl`/`auto_tp`)
   - Second scan pending LIMITs; fill those crossed by bar.high/bar.low; emit `FILLED` event
9. Add `expire_pending_orders()`:
   - For each `_pending_orders`: emit `EXPIRED` event, emit final `OrderResult(status=EXPIRED, filled_quantity=0)` via update callback
   - Clear queue
10. Modify `cancel_order()`:
    - If in `_pending_orders`: remove + emit `CANCELLED` event + send OrderResult
    - Else: noop (already filled)
11. Wire `backtest_app_service.py` to call `broker.expire_pending_orders()` after `replay_engine.replay()` finishes.
12. Update existing test `test_hitnrun2_backtest.py` — must still pass without changes (MARKET-only strategy).
13. Run `python -m compileall packages/pocketquant-core/src packages/pocketquant-backtest/src`.

## Edge Cases

- LIMIT submitted at price already crossed (e.g., BUY LIMIT @ 100 when current = 99) → fill immediately (same-bar)
- LIMIT submitted with `price=None` → REJECT with reason `invalid_limit_price`
- Cancel after fill → noop (idempotent)
- Both SL and TP hit on same bar → existing convention: SL wins (preserve; document in event reason)
- Pending LIMIT at end of run with `_current_prices` empty → still emit EXPIRED (no price needed)

## Success Criteria

- [ ] `PaperBroker._order_events` populated for every order with at least 2 events (SUBMITTED + terminal)
- [ ] LIMIT order non-fill scenario: submit at unreachable price → status SUBMITTED → end-of-run expire → status EXPIRED
- [ ] LIMIT order delayed-fill scenario: submit at price reachable in bar+3 → fills at correct bar with `limit_cross` reason
- [ ] Cancel-pending LIMIT: status SUBMITTED → CANCELLED with reason `user_cancel`
- [ ] SL/TP auto-fill events carry reason `auto_sl` / `auto_tp` and the synthetic exit order has its own SUBMITTED+FILLED event pair
- [ ] `test_hitnrun2_backtest.py` passes without modification
- [ ] `IBroker` interface signatures unchanged (verify with `grep -r "class IBroker"` and diff)
- [ ] OKX broker (`pocketquant-trading/brokers/okx/okx_broker.py`) compiles without changes (new event methods are paper-broker-only additions, not on IBroker)

## Risk Assessment

- **OKX live broker break:** New methods are added on `PaperBroker` directly, NOT on `IBroker` interface. Live broker emission is out of scope. Mitigation: never call `subscribe_order_event` on IBroker; gate at composition root (StrategyAppService probably only sees IBroker — verify it does NOT need events).
- **Event ordering with async callbacks:** Multiple subscribers + async dispatch → ordering may interleave. Mitigation: collector reads events in order from `_order_events[order_id]` at end, not during fills. Define: collector listens but persists final list at finalize-time.
- **LIMIT same-bar fill ambiguity:** BUY LIMIT @ 100 with bar (open=101, low=99, high=102, close=101). Did fill happen? Existing convention: assume reachable in bar → fills at limit_price (worst-case execution). Document; revisit if backtest accuracy gripes.
- **`_pending_orders` memory:** Strategies that flood LIMITs without cancel could balloon. Out-of-scope mitigation: cap or warn at e.g. 10k pending. Defer.
