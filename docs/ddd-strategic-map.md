# DDD Strategic Map

**Last Updated:** 2026-03-15 | **Status:** Living Document

## Bounded Contexts

### Market Data
Data ingestion, storage, and real-time streaming.

| Type | Name | Persisted | Status |
|------|------|-----------|--------|
| Entity | `Bar` | MongoDB | Active — OHLCV price bar with `to_mongo()`/`from_mongo()` |
| Model | `SyncStatus` | MongoDB | Active — tracks sync progress per symbol/interval |
| VO | `Interval`, `OHLCV`, `BarRange`, `Price` | — | Active |
| Service | `BarBuilder` | — | Active — aggregates ticks into bars |
| DTO | `Quote`, `QuoteTick`, `AggregatedBar`, `QuoteSubscription` | Redis | Active — application-layer cache DTOs |
| Event | `BarCompletedEvent` | — | Active (backtest only, not wired for real-time) |
| Event | `HistoricalDataSyncedEvent` | — | Active (fired after historical sync) |
| ~~Aggregate~~ | ~~`OHLCVAggregate`~~ | No | **Dead weight** — event factory shell, no state, no invariants |
| ~~Aggregate~~ | ~~`QuoteAggregate`~~ | No | **Dead code** — zero instantiations anywhere |

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
| Aggregate | `SymbolAggregate` | MongoDB | **Borderline** — has `activate()`/`deactivate()` behavior |
| VO | `SymbolInfo` | — | Active — frozen dataclass extending `Symbol` |

Note: `SymbolAggregate._events` exists but zero events are ever defined or appended. Dead event infrastructure.

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
  TradingView API → Bar entities → MongoDB
  → HistoricalDataSyncedEvent (inline in sync handler)

Backtesting:
  MongoDB → Bar stream → HistoricalReplayAppService
  → BarCompletedEvent → StrategyAppService._on_bar_completed()
  → Strategy.on_bar() → Signal → RiskCheck → OrderAggregate
  → OrderFilledEvent → PositionAppService → PositionAggregate

Order→Position:
  OrderAggregate state transitions
  → OrderFilledEvent → PositionAppService._on_order_filled()
  → PositionAggregate.open() / add_quantity() / reduce_quantity()
```

### Not Yet Wired (Real-Time Gap)

```
Real-time bars:
  QuoteTick → BarBuilder → Bar saved to MongoDB
  ╳ BarCompletedEvent NOT emitted → strategies don't fire

Real-time quotes:
  WebSocket → Quote DTO cached in Redis
  ╳ QuoteReceivedEvent NOT emitted → tick strategies don't fire
```

**Impact:** Real-time strategy execution does not work via events. Only backtesting replays trigger strategies. When live trading ships, `BarAppService._save_completed_bar()` and `QuoteAppService.on_quote_update()` need to emit events.

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

## Open Questions

1. **SyncStatus identity**: Should `SyncStatus` get a proper `_id`? Currently has no identity field — the repo upserts by `(symbol, exchange, interval)` compound key. Works but differs from other entities.
2. **SymbolAggregate vs flat entity**: Is the `SymbolInfo` VO wrapping worth the indirection? The aggregate has real behavior (`activate`/`deactivate`) but the VO adds a layer for 5 flat fields.
3. **Real-time event wiring priority**: When should `BarCompletedEvent` and `QuoteReceivedEvent` be wired for live trading? This is the critical gap between backtest-works and live-works.
4. **Event sourcing depth**: Current events are fire-and-forget via EventBus. If the project scales, should events be persisted (event store) for audit/replay?
5. **Multi-strategy broker isolation**: Each strategy gets its own broker instance. At scale (50+ strategies), is this sustainable or should there be a shared order router?
