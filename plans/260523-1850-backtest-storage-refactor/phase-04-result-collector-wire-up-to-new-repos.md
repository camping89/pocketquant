---
phase: 4
title: "Result collector wire-up to new repos"
status: pending
priority: P2
effort: "0.5d"
dependencies: [1, 2, 3]
---

# Phase 4: Result collector wire-up to new repos

## Overview

Refactor `BacktestResultCollector` to:
- Build `Order` aggregates (with embedded `events[]`+`fills[]`) from PaperBroker callbacks
- Build `Trade` round-trips from FIFO `LotTracker` consumed-lot events
- Build `OpenLot` snapshots for any still-open lots at run end
- Emit to 3 separate repositories via `BacktestAppService` instead of embedding everything into `BacktestResult.to_mongo`

Drop deprecated `TradeRecord`/`PositionRecord` usage (replaced by `Fill`/`Trade` from Phase 1). Update `metrics_builder` if it reads positions/trades (it does — `closed_positions` parameter).

## Requirements

- Functional: For every order PaperBroker fills, `BacktestResultCollector` aggregates → `Order` with full `events[]` + `fills[]`
- Functional: For every round-trip consumed by `LotTracker`, emit `Trade` with `entry_order_id` + `exit_order_id` populated
- Functional: At `finalize()`, return BOTH `BacktestResult` (run metadata + equity + open_positions) AND lists `orders: list[Order]`, `trades: list[Trade]` for caller to persist
- Functional: `BacktestAppService.run()` persists 3 lists in order: orders → trades → run
- Non-functional: `metrics_builder.build_metrics()` works with new `Trade` shape (entry_/exit_ instead of old PositionRecord shape)
- Non-functional: Existing in-memory contract preserved for `test_hitnrun2_backtest.py` (test asserts on BacktestResult fields)

## Architecture

### Collector state — new fields

```python
class BacktestResultCollector:
    def __init__(self, config, initial_capital):
        # ... existing fields
        self._orders_by_id: dict[str, Order] = {}            # all orders seen
        self._trades: list[Trade] = []                        # round-trips
        # _trades old (Fill events) — DROPPED; orders[].fills[] holds them
        # _closed_positions old (round-trips) — REPLACED by _trades above
```

### Callback adapter

PaperBroker emits two channels:
1. `OrderResult` (fill notifications) → `on_fill()` callback
2. `(order_id, OrderEvent)` (status transitions) → `on_event()` callback

Collector subscribes to both:

```python
async def on_fill(self, result: OrderResult) -> None:
    order = self._upsert_order(result)         # create/update Order
    self._append_fill_to_order(order, result)  # add Fill to order.fills[]
    self._feed_lot_tracker(result)              # generates ConsumedLot[]
    # ConsumedLots → Trade records below

async def on_event(self, order_id: str, event: OrderEvent) -> None:
    order = self._orders_by_id.get(order_id) or self._create_order_stub(order_id)
    order.events.append(event)
    order.status = event.to_status
    order.last_updated_at = event.timestamp
```

### Round-trip Trade emission

Current `_emit_closed_positions(outcome, exit_price, exit_time)` creates `PositionRecord` per consumed lot. Replace with:

```python
def _emit_trades(self, outcome: FillOutcome, exit_order_id: str, exit_price: float, exit_time: datetime) -> None:
    for consumed in outcome.consumed:
        pnl = self._consumed_pnl(consumed, exit_price)
        self._current_equity += pnl
        commission = consumed.entry_commission_portion + consumed.exit_commission_portion
        duration = (exit_time - consumed.lot.entry_time).total_seconds()
        trade = Trade(
            trade_id=generate_id_str(),
            run_id=self._run_id,
            strategy_id=self._config.strategy_id,
            symbol=self._config.symbol,
            direction=consumed.lot.direction,
            entry_order_id=consumed.lot.entry_order_id,
            entry_price=consumed.lot.entry_price,
            entry_time=consumed.lot.entry_time,
            quantity=consumed.qty_closed,
            exit_order_id=exit_order_id,
            exit_price=exit_price,
            exit_time=exit_time,
            sl_price=consumed.lot.sl_price,
            tp_price=consumed.lot.tp_price,
            pnl=pnl,
            commission=commission,
            duration_seconds=duration,
        )
        self._trades.append(trade)
        self._record_equity_point(exit_time)
        # back-link: exit order → trade
        if exit_order_id in self._orders_by_id:
            self._orders_by_id[exit_order_id].resulting_trade_id = trade.trade_id
```

### Open-lot snapshots at finalize

```python
def _build_open_positions(self) -> list[OpenLot]:
    result = []
    for lot in self._lot_tracker.lots:
        if lot.qty_remaining <= 1e-12:
            continue
        entry_comm_portion = (
            lot.entry_commission * (lot.qty_remaining / lot.qty_original)
            if lot.qty_original > 0 else 0.0
        )
        result.append(OpenLot(
            symbol=self._config.symbol,
            direction=lot.direction,
            entry_price=lot.entry_price,
            entry_time=lot.entry_time,
            quantity=lot.qty_remaining,
            sl_price=lot.sl_price,
            tp_price=lot.tp_price,
            entry_order_id=lot.entry_order_id,
            entry_commission_portion=entry_comm_portion,
        ))
    return result
```

`LotTracker.Lot` doesn't currently store `entry_order_id`. Phase 4 adds this field.

### Finalize returns 3 outputs

```python
@dataclass
class CollectedResults:
    run: BacktestResult
    orders: list[Order]
    trades: list[Trade]

def finalize(self, run_id, started_at, completed_at, status="completed", error_message=None) -> CollectedResults:
    metrics = build_metrics(
        closed_trades=self._trades,           # signature changed: was closed_positions
        equity_curve=self._equity_curve,
        initial_capital=self._initial_capital,
        current_equity=self._current_equity,
        total_commission=self._total_commission,
        start_date=self._config.start_date,
        end_date=self._config.end_date,
    )
    open_positions = self._build_open_positions()
    run = BacktestResult(
        id=run_id, ..., metrics=metrics,
        equity_curve=self._equity_curve,
        open_positions=open_positions,
        # NOTE: no trades/positions arrays
        ...
    )
    return CollectedResults(run=run, orders=list(self._orders_by_id.values()), trades=self._trades)
```

### App service orchestration

```python
async def run(self, config: BacktestConfig) -> BacktestResult:
    # ... existing pre-run setup
    await self._broker.subscribe_order_updates(collector.on_fill)
    await self._broker.subscribe_order_event(collector.on_event)
    try:
        bars = self._load_bars(config)
        bars_with_price = self._wrap_bars_with_price_update(config, bars)
        await self._replay_engine.replay(config, bars_with_price)
        # NEW: expire any pending LIMITs (Phase 2 contract)
        await self._broker.expire_pending_orders()
        completed_at = datetime.now(UTC)

        collected = collector.finalize(run_id=run_id, ...)

        if self._persist_results:
            # Order matters: orders → trades → run; if any fails, log + raise
            await self._order_repo.save_many(collected.orders)
            await self._trade_repo.save_many(collected.trades)
            await self._backtest_repo.save(collected.run)

        return collected.run
    except Exception as e:
        # ... persist failed result (orders + trades may still be partial — accept)
        ...
```

### metrics_builder signature change

`packages/pocketquant-backtest/src/pocketquant/backtest/engine/metrics_builder.py` currently expects `closed_positions: list[PositionRecord]`. Update to `closed_trades: list[Trade]` and adjust field accesses (`p.pnl` stays; `p.entry_time`/`p.exit_time` flat access).

## Related Code Files

- **Modify:**
  - `packages/pocketquant-backtest/src/pocketquant/backtest/engine/result_collector.py` — major rewrite
  - `packages/pocketquant-backtest/src/pocketquant/backtest/engine/metrics_builder.py` — rename arg + field access
  - `packages/pocketquant-backtest/src/pocketquant/backtest/engine/backtest_app_service.py` — inject OrderRepo+TradeRepo, persist 3 lists, call `expire_pending_orders`, subscribe order events
  - `packages/pocketquant-backtest/src/pocketquant/backtest/engine/lot_tracker.py` — add `entry_order_id` field to `Lot` dataclass; thread through `feed()` signature (already accepts `order_id` per scout L78 — verify and reuse)
  - `packages/pocketquant-backtest/src/pocketquant/backtest/domain/entities.py` — drop trades/positions fields, add open_positions
  - `packages/pocketquant-backtest/src/pocketquant/backtest/domain/value_objects.py` — DELETE (moved in Phase 1)
- **Create:**
  - `packages/pocketquant-backtest/src/pocketquant/backtest/engine/collected_results.py` (CollectedResults dataclass — if it doesn't fit in result_collector.py under 200-line cap)
- **Delete:**
  - Old `value_objects.py` flat file (from Phase 1 transition)

## Implementation Steps

1. Verify `LotTracker.Lot` has `entry_order_id` (scout said `feed()` accepts `order_id` — confirm). Add field if missing; thread through.
2. Define `CollectedResults` dataclass.
3. Update `result_collector.py`:
   - New fields `_orders_by_id`, `_trades`, `_run_id`
   - Rewrite `on_fill()`: upsert Order → append Fill → feed lot tracker → emit Trades
   - Add `on_event()` handler
   - Add `_upsert_order()`, `_create_order_stub()` helpers
   - Replace `_emit_closed_positions` with `_emit_trades`
   - Add `_build_open_positions()`
   - Rewrite `finalize()` returning `CollectedResults`
4. Update `metrics_builder.build_metrics()` signature + impl.
5. Update `backtest_app_service.py`:
   - Constructor: accept `OrderRepository`, `TradeRepository`
   - DI provider update (`pocketquant-api/di/persistence.py` already wires repos; `pocketquant-api/di/` factory for BacktestAppService needs new deps)
   - `run()`: pass `run_id` to collector; subscribe both channels; call `expire_pending_orders` post-replay; persist 3 lists in order
   - Failure path: persist whatever orders/trades captured + failed run doc
6. Update `entities.py`: `BacktestResult` shape per Phase 1 (drop trades/positions; add open_positions).
7. Update `Result.to_mongo`/`from_mongo` to match new shape.
8. Delete old `value_objects.py` flat file. Verify no broken imports.
9. Run existing tests — `test_hitnrun2_backtest.py` may need assertion updates (e.g., `result.trades` → `collected.orders[].fills`). Fix assertions.
10. Run `pytest packages/pocketquant-backtest/tests/`.

## Decision Point — return type of `run()`

Current `BacktestAppService.run()` returns `BacktestResult`. After refactor caller (handler `RunAllBacktests`, `GetSubscriptionBacktest`) may need access to orders/trades. Options:
- **A.** `run()` still returns `BacktestResult`; orders/trades only persisted, never returned. Consumers query separately via repos.
- **B.** `run()` returns `CollectedResults`. Caller can pass through.
- **Recommend A** — consumers fetch via repository on demand. Keeps `run()` signature stable.

## Success Criteria

- [ ] `BacktestResultCollector` produces `CollectedResults(run, orders, trades)` at finalize
- [ ] Each `Order` has matching events (≥2: SUBMITTED+terminal) and fills (≥1 for FILLED, 0 for CANCELLED/REJECTED/EXPIRED)
- [ ] Each `Trade.entry_order_id` and `Trade.exit_order_id` references an existing Order in collected.orders
- [ ] `Order.resulting_trade_id` populated for the SELL/BUY that closes a round-trip (exit orders only)
- [ ] `metrics_builder` works with new Trade list shape
- [ ] `BacktestAppService.run()` persists orders+trades+run in correct order
- [ ] `test_hitnrun2_backtest.py` passes (with updated assertions to match new shape)
- [ ] `test_result_collector_fifo.py` passes (likely needs assertion updates)
- [ ] `test_lot_tracker.py` passes (likely unchanged unless `Lot.entry_order_id` impacts)
- [ ] Old `value_objects.py` flat file deleted; grep `TradeRecord\|PositionRecord` returns zero hits in `src/`

## Risk Assessment

- **3-write transaction-less:** Orphans possible. Mitigation: log + accept; cleanup job future work.
- **LotTracker scout said feed() accepts order_id; verify:** If lot_tracker doesn't currently store order_id on `Lot`, we need to add it. Risk: signature change breaks existing tests. Mitigation: read `lot_tracker.py` first thing in this phase; ensure additive change.
- **Test assertions:** Existing tests assert `result.trades[].pnl` etc. After refactor, test path is `collected.trades[].pnl` (Trade type, not Fill). Likely many assertion line edits. Budget time.
- **Subscription-scoped backtest cache:** `save_for_subscription` writes a single doc with `_id=sub_id`. Now orders/trades are separate; sub-scoped reads need a JOIN-like fetch. Mitigation: keep current behavior; subscription doc has just run metadata. Orders/trades fetched separately via `list_by_run(sub_id_run)`. If perf gripes later, add `subscription_id` discriminator on orders/trades collections (cheap index).
