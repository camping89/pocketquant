# CLAUDE.md — PocketQuant

**Last Updated:** 2026-03-15 | **Status:** v1.0 production | **Critical Architecture Change:** Schemas deleted, persistence in domain

## Domain Entities (Pydantic BaseModel with MongoDB Persistence)

All domain entities (Bar, OrderAggregate, PositionAggregate, etc.) are **Pydantic BaseModel** with built-in MongoDB persistence:
- `to_mongo()` → dict for storage
- `@classmethod from_mongo(doc)` → entity reconstruction
- No separate schemas/ directory (deleted 2026-03-15)
- Repositories import directly from domain: `from src.domain.ohlcv.entities import Bar`

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
