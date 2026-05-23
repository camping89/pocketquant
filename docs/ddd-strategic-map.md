# DDD Strategic Map

**Last Updated:** 2026-04-10 | **Status:** v1.0 Complete | **Bounded Contexts:** 6 (Market Data, Trading, Strategy, Risk, Symbol, Backtest)

Current note: the repo now includes `pocketquant-web` as a separate frontend package in addition to the backend bounded contexts discussed here.

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
| Impl | `HitNRun2Strategy` | — | Active — 1m breakdown/breakup with capped technical SL/TP |

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

### Fully Wired (All Events Complete)

```
Real-time bars (IMPLEMENTED ✅):
  QuoteTick → BarBuilder → Bar saved to MongoDB bars collection
  → BarCompletedEvent emitted from _save_completed_bar()
  → StrategyAppService._on_bar_completed() → live strategy execution

Real-time quotes (IMPLEMENTED ✅):
  WebSocket → Quote DTO cached in Redis
  → QuoteReceivedEvent emitted from _on_quote_update()
  → StrategyAppService._on_quote_received() → tick handlers
```

**Status:** All event wiring complete. Backtesting fully functional. Real-time event streams implemented (BarCompletedEvent, QuoteReceivedEvent). Live trading event infrastructure production-ready.

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

## Resolved Questions (2026-03-22)

1. ✅ **Real-time event wiring**: BarCompletedEvent and QuoteReceivedEvent emission now implemented in live trading pipeline
2. ✅ **4-package monorepo**: Restructured with clean dependency graph (core ← {backtest, trading} ← api)
3. ✅ **Dishka DI integration**: All 6 providers configured, handler registration automated

## Open Questions (Future Phases)

1. **Event sourcing**: Current events are fire-and-forget via EventBus. If scaling, should events be persisted (event store) for audit/replay?
2. **Multi-strategy broker isolation**: Each strategy gets own broker instance. At scale (50+ strategies), should there be a shared order router?
3. **SyncStatus compound key**: Currently upserts by `(symbol, exchange, interval)`. Should get dedicated `_id` UUID for consistency?
4. **Distributed job scheduling**: APScheduler is in-memory. For multiple workers, should use distributed scheduler (Celery, etc.)?
