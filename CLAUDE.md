# CLAUDE.md — PocketQuant

**Last Updated:** 2026-03-15 | **Status:** v1.0 production | **Critical Architecture Change:** DDD three-tier domain structure

## Domain Structure (Three-Tier DDD)

`src/domain/` is organized into three tiers:
- **Top-level** (collection-backed): `bar/`, `order/`, `position/`, `symbol/`, `sync_status/`, `backtest/`
- **`concepts/`** (non-persisted logic): `concepts/quote/`, `concepts/risk/`, `concepts/strategy/`
- **`shared/`** (cross-cutting): `enums.py`, `events.py`, `value_objects.py`

Standard file names per folder: `entities.py`, `events.py`, `value_objects.py`, `enums.py`, `interfaces.py`, `services/`

## Domain Entities (Pydantic BaseModel with MongoDB Persistence)

All domain entities (Bar, Symbol, OrderAggregate, PositionAggregate, BacktestResult, etc.) use `to_mongo()`/`from_mongo()`:
- Repositories import directly from domain: `from src.domain.bar.entities import Bar`
- Backtest results: `from src.domain.backtest import BacktestResult, OptimizationResult`
- No separate schemas/ directory
- `INTERVAL_TO_TVDATAFEED` lives in `infrastructure/tradingview/tradingview_client.py` (not domain)

## Handler Extract-Method Pattern

Complex handlers (>30 lines, 8+ operations) use private helper methods:
- `handle()` method reads as clean checklist
- Each `_helper_name()` does one logical operation
- Examples: SyncSymbolHandler (8 helpers), GetOHLCVHandler (_build_cache_key), StopQuoteFeedHandler (_cancel_ws_task)
- Simple handlers (1-3 ops) should NOT extract methods

## DI Container (Dishka)

6 providers organize services by concern:
- CoreProvider: Settings, EventBus, Mediator
- PersistenceProvider: Database, Cache, 7 repositories
- InfrastructureProvider: Brokers, TradingView, JobScheduler
- MarketDataProvider: BarAppService, QuoteAppService, sync jobs
- TradingProvider: OrderAppService, PositionAppService
- HandlerProvider: All 27 CQRS handlers

Routes use `FromDishka[Mediator]` + `DishkaRoute` (NOT `Depends()`)

## Schema Consolidation

No empty subclasses. Use base classes directly:
- ❌ Don't create `OHLCVCreate(OHLCVBase): pass` — use `Bar` directly
- ✅ Repository methods work with domain entities directly (Bar.to_mongo(), Bar.from_mongo())
