# DDD Strategic Map

**Last Updated:** 2026-05-25 | **Scope:** Bounded contexts, context relationships, ubiquitous language
**For tactical detail** (aggregates, entities, VOs per context) → see [system-architecture.md](./system-architecture.md) § Domain Layer.

---

## 6 Bounded Contexts

| Context | Responsibility | Owns | Package |
|---|---|---|---|
| **Market Data** | Bar/quote ingestion, storage, real-time streaming | `Bar`, `SyncStatus`, market-data DTOs | `pocketquant-core` (domain) + `pocketquant-api` (sync jobs) |
| **Trading** | Order execution + position lifecycle | `OrderAggregate`, `PositionAggregate` | `pocketquant-core` (domain) + `pocketquant-trading` (orchestration) |
| **Strategy** | Trading logic interfaces + signal generation | `IStrategy`, `Signal`, strategy implementations | `pocketquant-core` (interfaces) + `pocketquant-trading` (registry, services) |
| **Risk** | Position sizing + risk validation | `RiskModel`, `PositionSizer` | `pocketquant-core` (pure calculations) |
| **Symbol** | Tradeable-asset metadata | `Symbol` (flat entity since 2026-03-15) | `pocketquant-core` |
| **Backtest** | Historical replay + performance analysis | `BacktestResult`, `TradeRecord`, `PerformanceCalculator` | `pocketquant-backtest` (engine, persistence) |

> A 7th container — `pocketquant-web` (Node/Vite SPA) — is a **UI surface**, not a bounded context. It consumes the API HTTP boundary; no domain logic lives there.

---

## Context Map (Relationships)

```
                                    ┌──────────────┐
                                    │  Backtest    │
                                    │ (replays MD) │
                                    └──────┬───────┘
                                           │ consumes Bar
                                           ▼
┌──────────────┐   BarCompletedEvent ┌──────────────┐    SignalGeneratedEvent  ┌──────────────┐
│ Market Data  │────────────────────▶│  Strategy    │─────────────────────────▶│   Trading    │
│   (Bar)      │                     │  (IStrategy) │                          │ (OrderAgg,   │
└──────┬───────┘                     └──────┬───────┘                          │  PositionAgg)│
       │ Quote (DTO/Redis)                  │ Symbol lookup                    └──────┬───────┘
       │                                    ▼                                          │
       │                            ┌──────────────┐         RiskConfig                │
       │                            │   Symbol     │◀─────────────────────────────────┤
       │                            │   (entity)   │                                   │
       │                            └──────────────┘         ┌──────────────┐          │
       │                                                     │     Risk     │◀─────────┘
       │                                                     │ (PositionSizer)         (pre-trade check)
       │                                                     └──────────────┘
       ▼
   (no upstream)
```

**Relationship types:**
- **Market Data → Strategy** — *Customer/Supplier* via published events (`BarCompletedEvent`, `QuoteReceivedEvent`)
- **Strategy → Trading** — *Customer/Supplier* via `SignalGeneratedEvent`
- **Trading → Position lifecycle** — internal aggregate-to-aggregate event chain (`OrderFilledEvent` → `PositionAggregate`)
- **Risk → Trading** — *Shared Kernel* (risk calculations consumed pre-trade)
- **Symbol → all** — *Conformist* (everyone reads `Symbol`; no one mutates without ownership)
- **Backtest → Market Data** — *Customer* (replays historical Bars)

---

## Ubiquitous Language

| Term | Meaning in this codebase | Common false synonyms to avoid |
|---|---|---|
| **Symbol** | Composite identifier `BTCUSDT:BINANCE` — code + exchange in one string | "Ticker", "pair", "instrument" |
| **Bar** | Time-bucketed OHLCV record. **Not** "candle", "kline", "ohlcv-row" | "Candle" (UI term only); use "Bar" in domain code |
| **Quote** | Latest tick (price + size + timestamp), cached in Redis. Not persisted long-term | "Tick" (used only inside `BarBuilder` aggregation) |
| **Subscription** | Strategy's registration for `(symbol, exchange, interval)` → drives feed routing | "Watch", "follow" |
| **Sync** | Bringing local Bar storage up-to-date from an external source (TradingView, Binance) | "Backfill" (specific to one-off historical loads), "refresh" |
| **Strategy** | A pluggable trading-logic class implementing `IStrategy`. Loaded by id, not file path | "Algorithm" (too broad), "bot" (UI term) |
| **Aggregate** | DDD construct: entity with invariants + lifecycle + event emission. Earn this name. | Don't apply to data records (e.g. Bar isn't an aggregate) |
| **Composite symbol** | The `CODE:EXCHANGE` format. Replaced earlier `(exchange, code)` 2-tuple API | "Exchange-prefixed symbol" |
| **In-progress bar** | Bar currently being built from live ticks; `is_complete=False` | "Open bar", "partial bar" |

---

## DDD Classification Guide

### When to use an Aggregate
- Entity has **invariants** to protect (e.g. `OrderAggregate` state machine)
- Entity has **lifecycle behavior** (e.g. `PositionAggregate` open → scale → close)
- Entity **owns other entities** within a consistency boundary
- Entity **emits domain events** from business operations

### When NOT to use an Aggregate
- Entity is a **data record** (e.g. `Bar` — just OHLCV data, serialization only)
- Class is an **event factory** with no state (anti-pattern, deleted 2026-03-15)
- Class is **never instantiated** in practice
- Behavior is **CRUD-only** — use a plain entity or model

### Project Rules
1. Aggregates earn their complexity — no invariants, no aggregate.
2. Events can be created directly where needed — no wrapper aggregate required.
3. Value objects stay as frozen dataclasses — simple, immutable, no persistence.
4. DTOs live in the application layer — they're infrastructure, not domain.

---

## Open Strategic Questions

1. **Event sourcing** — events are fire-and-forget via `EventBus`. If we need audit/replay at scale, should events be persisted in an event store?
2. **Multi-strategy broker isolation** — each strategy gets its own broker instance. At 50+ strategies, do we need a shared order router?
3. **Distributed scheduling** — APScheduler is in-memory; for horizontal scaling, switch to a distributed scheduler (Celery, etc.)?
4. **Risk as a service** — currently `PositionSizer` is a pure-function dependency of Trading. If risk grows policies (max-concurrent-positions, daily loss limits, correlation caps), should it become its own service with its own state?

---

## Historical Note

For the 2026-03-15 refactoring history (deletions of `OHLCVAggregate`, `QuoteAggregate`, `SymbolAggregate`, ohlcv→bar rename, schemas-directory removal) → see `journals/` and git history. Removed from this doc to keep it strategic-only.
