# DDD Strategic Map

**Last Updated:** 2026-03-15 | **Status:** Living Document

## Bounded Contexts

### Market Data
Data ingestion, storage, and real-time streaming.

| Type | Name | Persisted | Status |
|------|------|-----------|--------|
| Entity | `Bar` | MongoDB (bars) | Active — bar price data with `to_mongo()`/`from_mongo()`, `symbol_key`, interval |
| Model | `SyncStatus` | MongoDB (sync_status) | Active — tracks sync progress per symbol/interval |
| VO | `Interval`, `OHLCV`, `BarRange`, `Price` | — | Active |
| Service | `BarBuilder` | — | Active — aggregates ticks into bars |
| DTO | `Quote`, `QuoteTick`, `AggregatedBar`, `QuoteSubscription` | Redis | Active — application-layer cache DTOs |
| Event | `BarCompletedEvent` | — | Active (backtesting via HistoricalReplay, real-time: TODO) |
| Event | `HistoricalDataSyncedEvent` | — | Active (fired after historical sync) |
| ~~Aggregate~~ | ~~`OHLCVAggregate`~~ | No | **DELETED 2026-03-15** — was event factory shell, no state, no invariants |
| ~~Aggregate~~ | ~~`QuoteAggregate`~~ | No | **DELETED 2026-03-15** — zero instantiations, dead code |

### Trading
Order execution and position lifecycle management.

| Type | Name | Persisted | Status |
|------|------|-----------|--------|
| Aggregate | `OrderAggregate` | MongoDB | **Legit** — full state machine, 5 event types |
| Aggregate | `PositionAggregate` | MongoDB | **Legit** — lifecycle, P&L, scale in/out |
| VO | `OrderSide`, `OrderType`, `OrderStatus` | — | Active |
| VO | `PositionSide`, `PnL` | — | Active |
| Event | `Order*Event` (5 types) | — | Active, consumed by `PositionAppService` |
| Event | `Position*Event` (3 types) | — | Active |

### Strategy
Trading logic interfaces and signal generation.

| Type | Name | Persisted | Status |
|------|------|-----------|--------|
| Interface | `IStrategy` | — | Active — `on_bar()`, `on_tick()`, `on_fill()` |
| VO | `Signal`, `Direction`, `StrategyConfig` | — | Active |
| VO | `StopLossConfig`, `TakeProfitConfig`, `OrderConfig` | — | Active |
| Event | `SignalGeneratedEvent` | — | Active |
| Impl | `MACrossoverStrategy` | — | Example implementation |

### Risk
Position sizing and risk validation.

| Type | Name | Persisted | Status |
|------|------|-----------|--------|
| VO | `RiskModel` (enum), `RiskConfig` | — | Active |
| Service | `PositionSizer` | — | Active — pure calculation service |

### Symbol
Tradeable asset metadata.

| Type | Name | Persisted | Status |
|------|------|-----------|--------|
| Entity | `Symbol` | MongoDB (symbols) | Active (FLATTENED 2026-03-15) — flat entity with `code`, `exchange`, `name`, `asset_type`, `is_active`, `create()`, `symbol_key`, `to_mongo()`/`from_mongo()` |
| ~~Aggregate~~ | ~~`SymbolAggregate`~~ | No | **DELETED 2026-03-15** — flattened to Symbol entity, no aggregate needed |
| ~~VO~~ | ~~`SymbolInfo`~~ | — | **DELETED 2026-03-15** — wrapped by SymbolAggregate, no longer needed |

### Backtest
Historical replay and performance analysis.

| Type | Name | Persisted | Status |
|------|------|-----------|--------|
| Service | `PerformanceCalculator` | — | Active — Sharpe, Sortino, max drawdown |
| Model | `BacktestResult`, `BacktestMetrics`, `TradeRecord` | MongoDB | Active |

## Event Flow

### Wired (Working)

```
Historical Sync:
  TradingView API → Bar entities → MongoDB bars collection
  → HistoricalDataSyncedEvent (inline in sync handler)

Backtesting (Events Fully Wired):
  MongoDB bars → Bar stream → HistoricalReplayAppService
  → BarCompletedEvent → StrategyAppService._on_bar_completed()
  → Strategy.on_bar() → Signal → RiskCheck → OrderAggregate
  → OrderFilledEvent → PositionAppService → PositionAggregate

Order→Position (Events Fully Wired):
  OrderAggregate state transitions
  → OrderFilledEvent → PositionAppService._on_order_filled()
  → PositionAggregate.open() / add_quantity() / reduce_quantity()
```

### In Progress (Real-Time Wiring: Phase 5)

```
Real-time bars (IMPLEMENTATION READY, EMISSION PENDING):
  QuoteTick → BarBuilder → Bar saved to MongoDB bars collection
  → BarCompletedEvent emission site ready in _save_completed_bar()
  ⟳ Real-time wiring: awaiting BarCompletedEvent emission for live strategies

Real-time quotes (IMPLEMENTATION READY, EMISSION PENDING):
  WebSocket → Quote DTO cached in Redis
  → QuoteReceivedEvent emission site ready in _on_quote_update()
  ⟳ Real-time wiring: awaiting QuoteReceivedEvent emission for tick strategies
```

**Status:** Backtesting strategy execution is fully wired and working. Real-time event emission infrastructure is in place (`_save_completed_bar()`, `_on_quote_update()`). Live trading event wiring scheduled for Phase 5 (scheduled 2026-Q2).

## DDD Classification Guide

### When to Use an Aggregate
- Entity has **invariants** to protect (e.g., OrderAggregate state machine)
- Entity has **lifecycle behavior** (e.g., PositionAggregate open→close)
- Entity **owns other entities** within a consistency boundary
- Entity **emits domain events** from business operations

### When NOT to Use an Aggregate
- Entity is a **data record** (e.g., Bar — just OHLCV data, no behavior beyond serialization)
- Class is just an **event factory** with no state (e.g., OHLCVAggregate)
- Class is **never instantiated** (e.g., QuoteAggregate)
- Behavior is **CRUD-only** (persist/query) — use a plain entity or model

### Pragmatic Rules for This Project
1. Aggregates earn their complexity — if it has no invariants, it's not an aggregate
2. Events can be created directly where they're needed — no wrapper aggregate required
3. Value objects stay as frozen dataclasses — simple, immutable, no persistence
4. DTOs live in application layer — they're infrastructure concerns, not domain

## Resolved Items (2026-03-15 Refactoring)

1. ✅ **OHLCVAggregate deleted** — Event factory shell with no state/invariants, removed dead code
2. ✅ **QuoteAggregate deleted** — Zero instantiations, never used
3. ✅ **SymbolAggregate flattened to Symbol entity** — Reduced indirection, removed SymbolInfo VO
4. ✅ **domain/ohlcv/ → domain/bar/** — Clearer naming, better semantics
5. ✅ **OHLCVRepository → BarRepository** — Consistent naming with domain
6. ✅ **MongoDB collection ohlcv → bars** — Aligns with domain entity names
7. ✅ **Schemas directory deleted** — Domain entities now handle MongoDB persistence directly via `to_mongo()`/`from_mongo()`

## Open Questions

1. **Real-time event wiring timeline** (Phase 5): When to prioritize `BarCompletedEvent` and `QuoteReceivedEvent` emission for live trading strategies?
2. **Event sourcing depth**: Current events are fire-and-forget via EventBus. If project scales, should events be persisted (event store) for audit/replay?
3. **Multi-strategy broker isolation**: Each strategy gets own broker instance. At scale (50+ strategies), is this sustainable or should there be a shared order router?
4. **SyncStatus compound key**: Currently upserts by `(symbol, exchange, interval)`. Should it get a dedicated `_id` UUID field for consistency with other repositories?
