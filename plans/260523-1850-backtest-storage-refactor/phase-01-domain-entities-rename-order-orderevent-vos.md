---
phase: 1
title: "Domain entities rename + Order/OrderEvent VOs"
status: pending
priority: P2
effort: "0.5d"
dependencies: []
---

# Phase 1: Domain entities rename + Order/OrderEvent VOs

## Overview

Rename `TradeRecord` → `Fill` and `PositionRecord` → `Trade` to match Backtrader/QuantConnect convention. Add new `Order` value object (lifecycle-aware) and `OrderEvent` value object (status transitions). Add `OpenLot` value object for run-end snapshots. No persistence wiring yet — just the data shapes that subsequent phases will reference.

## Requirements

- Functional: All four canonical types defined as dataclasses with `to_mongo()`/`from_mongo()`
- Functional: New `Fill`, `Trade`, `Order`, `OrderEvent`, `OpenLot` VOs defined; reuse core `OrderStatus` + `OrderType` enums (Phase 2 extends `OrderStatus` with `EXPIRED`)
- Non-functional: Old names continue to work via alias for ONE commit to keep diffs reviewable (drop alias at end of Phase 4)
- Non-functional: 200-line file size cap per CLAUDE.md — split `value_objects.py` if needed

## Architecture

`packages/pocketquant-backtest/src/pocketquant/backtest/domain/value_objects.py` currently 236 lines. After this phase it will grow → split into logical files:

```
domain/
├── value_objects/
│   ├── __init__.py          # re-export all
│   ├── fill.py              # Fill (was TradeRecord)
│   ├── trade.py             # Trade (was PositionRecord) — round-trip
│   ├── order.py             # Order + OrderEvent (reuse core OrderStatus + OrderType)
│   ├── equity.py            # EquityPoint
│   ├── metrics.py           # BacktestMetrics
│   ├── open_lot.py          # OpenLot (snapshot)
│   └── optimization.py      # OptimizationResultEntry
```

OR keep `value_objects.py` single file if under 200 lines after additions (preferred; KISS). Re-evaluate after adding Order/OrderEvent/OpenLot.

**Estimate after additions:** ~340 lines → MUST split. Use folder layout above.

### Type shapes

```python
# fill.py
@dataclass
class Fill:
    """Atomic execution event. One order may emit multiple Fills (partials)."""
    fill_id: str
    order_id: str
    symbol: str
    side: str            # "BUY" | "SELL"
    quantity: float
    price: float
    commission: float
    slippage: float
    timestamp: datetime
    # to_mongo / from_mongo

# order.py — reuse core enums; Phase 2 extends OrderStatus with EXPIRED
from pocketquant.core.domain.order import OrderStatus, OrderType

@dataclass
class OrderEvent:
    """Status transition record. Embedded in Order doc."""
    timestamp: datetime
    from_status: str | None       # None for initial SUBMITTED
    to_status: str
    reason: str | None = None     # e.g. "auto_sl", "auto_tp", "user_cancel"

@dataclass
class Order:
    """Order intent with full lifecycle. Persisted standalone (backtest_orders)."""
    order_id: str
    run_id: str
    strategy_id: str
    symbol: str
    side: OrderSide               # core enum: BUY | SELL
    order_type: OrderType         # core enum: MARKET | LIMIT | STOP
    quantity: float
    price: float | None           # required for LIMIT/STOP
    sl_price: float | None
    tp_price: float | None
    status: OrderStatus           # core enum (Phase 2 adds EXPIRED)
    submitted_at: datetime
    last_updated_at: datetime
    events: list[OrderEvent]      # embed
    fills: list[Fill]             # embed (only fill_id+...+commission; redundant order_id can be dropped on embed)
    resulting_trade_id: str | None = None

# trade.py
@dataclass
class Trade:
    """Round-trip economic outcome. Persisted standalone (backtest_trades)."""
    trade_id: str
    run_id: str
    strategy_id: str
    symbol: str
    direction: str                # "LONG" | "SHORT"
    entry_order_id: str
    entry_price: float
    entry_time: datetime
    quantity: float
    exit_order_id: str
    exit_price: float
    exit_time: datetime
    sl_price: float | None
    tp_price: float | None
    pnl: float
    commission: float
    duration_seconds: float

# open_lot.py
@dataclass
class OpenLot:
    """Snapshot of a still-open lot at end of backtest run. Embedded in backtest_runs.open_positions[]."""
    symbol: str
    direction: str
    entry_price: float
    entry_time: datetime
    quantity: float
    sl_price: float | None
    tp_price: float | None
    entry_order_id: str
    entry_commission_portion: float
```

### Backward-compat aliases (Phase 1 only)

In `value_objects/__init__.py`:
```python
from .fill import Fill
from .trade import Trade
from .order import Order, OrderEvent  # status/type enums imported from core
# Phase 1 transition: keep old names alive
TradeRecord = Fill          # DEPRECATED — remove in Phase 4
PositionRecord = Trade      # DEPRECATED — remove in Phase 4
__all__ = [...]
```

This keeps `result_collector.py`, `metrics_builder.py`, `backtest_repository.py` compilable until Phase 4 rewires.

⚠️ **CAVEAT — incompatible field rename:** old `PositionRecord` had `entry_time/exit_time/entry_price/exit_price` at top level; new `Trade` has `entry: {price,time,qty,order_id}` and `exit: {price,time,order_id}`. So the alias is **semantic only** — code that field-accesses must continue using flat `PositionRecord` shape. Solution: keep both classes during transition (defer alias until field-access sites are also rewritten in Phase 4). Document loud at top of `__init__.py`.

**Simpler alternative:** Don't alias. Phases 2-4 happen on a feature branch so the compile-broken window stays local; keep transition atomic. **Recommend this alternative.** Revise plan if user disagrees.

## Related Code Files

- **Create:**
  - `packages/pocketquant-backtest/src/pocketquant/backtest/domain/value_objects/__init__.py`
  - `packages/pocketquant-backtest/src/pocketquant/backtest/domain/value_objects/fill.py`
  - `packages/pocketquant-backtest/src/pocketquant/backtest/domain/value_objects/trade.py`
  - `packages/pocketquant-backtest/src/pocketquant/backtest/domain/value_objects/order.py`
  - `packages/pocketquant-backtest/src/pocketquant/backtest/domain/value_objects/equity.py`
  - `packages/pocketquant-backtest/src/pocketquant/backtest/domain/value_objects/metrics.py`
  - `packages/pocketquant-backtest/src/pocketquant/backtest/domain/value_objects/open_lot.py`
  - `packages/pocketquant-backtest/src/pocketquant/backtest/domain/value_objects/optimization.py`
- **Modify:**
  - `packages/pocketquant-backtest/src/pocketquant/backtest/domain/entities.py` — keep `BacktestResult` shape but switch `trades: list[Fill]` → drop entirely (moved to backtest_orders.fills[]); switch `positions: list[Trade]` → drop (moved to backtest_trades); add `open_positions: list[OpenLot]`. Update `to_mongo`/`from_mongo`. (Defer concrete switch to Phase 3 to keep Phase 1 additive.)
  - `packages/pocketquant-backtest/src/pocketquant/backtest/domain/__init__.py` — export new types
- **Delete:**
  - `packages/pocketquant-backtest/src/pocketquant/backtest/domain/value_objects.py` (after move complete)

## Implementation Steps

1. Create `domain/value_objects/` directory.
2. Move `BacktestMetrics`, `EquityPoint`, `OptimizationResultEntry` verbatim into respective files (`metrics.py`, `equity.py`, `optimization.py`).
3. Rename in-place during move: `TradeRecord` → `Fill` (file `fill.py`, drop unused `pnl` field — pnl now belongs only to Trade not Fill).
4. Rename + reshape during move: `PositionRecord` → `Trade` with nested `entry`/`exit` subdocs OR flat fields with `entry_*`/`exit_*` prefix. **Recommend flat** for Mongo simplicity (no nested obj traversal in queries). File `trade.py`.
5. Add `Order`, `OrderEvent` in `order.py`. Import `OrderStatus`, `OrderType`, `OrderSide` from `pocketquant.core.domain.order`. `Order.fills[]` uses `Fill` type (cross-import OK since `fill.py` has no dependency on `order.py`). When serializing to Mongo, convert enums to `.value` strings.
6. Add `OpenLot` in `open_lot.py`.
7. Write `to_mongo()` / `from_mongo()` for each new type.
8. Update `domain/value_objects/__init__.py` to re-export everything.
9. Update `domain/__init__.py` likewise.
10. Run mypy / `python -m compileall packages/pocketquant-backtest/src` — must compile.
11. DO NOT delete old `value_objects.py` until all imports updated.

## Decision Point — Aliases

Recommend **NOT** keeping `TradeRecord`/`PositionRecord` aliases. Rationale:
- Field shapes diverge (Trade has entry_/exit_ prefix; old TradeRecord has flat single-fill shape)
- Atomic rewire in Phases 2-4 keeps each PR self-contained
- Trade and Fill have semantically incompatible meanings — alias hides the meaning shift

If user pushes back: implement aliases as `from .fill import Fill as TradeRecord` only for compilation; runtime access patterns differ.

## Success Criteria

- [ ] `value_objects/` folder created with 7 files, each <200 lines
- [ ] `Fill`, `Trade`, `Order`, `OrderEvent`, `OpenLot`, `BacktestMetrics`, `EquityPoint`, `OptimizationResultEntry` all defined
- [ ] Core `OrderStatus` enum extended with `EXPIRED` value (deferred to Phase 2)
- [ ] `Order.status`/`side`/`order_type` typed as core enums, not bare strings
- [ ] All `to_mongo()`/`from_mongo()` roundtrip-tested via doctest or unit test
- [ ] `python -m compileall packages/pocketquant-backtest/src` exits 0
- [ ] Old `value_objects.py` deleted; no broken imports project-wide (`pytest --collect-only` succeeds)

## Risk Assessment

- **Field-rename diff blast radius:** `TradeRecord` and `PositionRecord` referenced in `result_collector.py`, `metrics_builder.py`, `backtest_repository.py` (via BacktestResult), tests. Mitigation: rewire in Phases 3-4 atomically; Phase 1 only adds new types without removing old usages.
- **Duplicate definitions during transition:** Old `value_objects.py` still has `TradeRecord`/`PositionRecord` at end of Phase 1. Mitigation: clearly mark old file as DEPRECATED in comment, schedule delete in Phase 4.
- **Naming collision with core `Order`/`OrderAggregate`:** Backtest `Order` VO is different from core `OrderAggregate`. Mitigation: live in `pocketquant.backtest.domain.value_objects.order` namespace; never import simultaneously without alias.
