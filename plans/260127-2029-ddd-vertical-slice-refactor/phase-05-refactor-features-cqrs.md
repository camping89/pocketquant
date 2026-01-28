# Phase 5: Refactor Features to CQRS

## Context Links
- Parent: [plan.md](plan.md)
- Blocked by: [Phase 3](phase-03-domain-layer.md), [Phase 4](phase-04-mediator-eventbus.md)
- Research: [DDD Patterns](research/researcher-ddd-cqrs-patterns.md)

## Overview

| Field | Value |
|-------|-------|
| Date | 2026-01-27 |
| Priority | P1 |
| Status | completed |
| Effort | 3h |

Reorganize features by operation (sync, ohlcv, quote, status). Create command/query objects with handlers. Route through Mediator.

## Key Insights

Current state:
- `services/data_sync_service.py` - Mixed sync + query logic
- `services/quote_service.py` - Quote management
- Routes directly call services

Target:
- Commands/Queries as data classes
- Handlers contain business logic
- Routes dispatch via Mediator

## Requirements

### Functional
- All write operations use Commands
- All read operations use Queries
- Existing API contracts unchanged

### Non-Functional
- Handlers are testable in isolation
- Clear separation of concerns
- Direct DB access (no repository layer)

## Architecture

```
src/features/market_data/
├── sync/                        # Sync operations
│   ├── __init__.py
│   ├── command.py              # SyncSymbolCommand, BulkSyncCommand
│   ├── handler.py              # SyncSymbolHandler, BulkSyncHandler
│   ├── event_handlers.py       # Handle domain events
│   ├── jobs.py                 # Background job definitions
│   └── dto.py                  # SyncResult, SyncStatus DTOs
├── ohlcv/                       # OHLCV queries
│   ├── __init__.py
│   ├── query.py                # GetOHLCVQuery
│   ├── handler.py              # GetOHLCVHandler
│   └── dto.py                  # OHLCVResponse
├── quote/                       # Quote operations
│   ├── __init__.py
│   ├── subscribe_command.py    # SubscribeCommand, UnsubscribeCommand
│   ├── subscribe_handler.py    # SubscribeHandler
│   ├── get_query.py            # GetLatestQuoteQuery
│   ├── get_handler.py          # GetLatestQuoteHandler
│   ├── event_handlers.py       # Handle quote events
│   └── dto.py                  # QuoteResponse
├── status/                      # Status queries
│   ├── __init__.py
│   ├── query.py                # GetSyncStatusQuery
│   ├── handler.py              # GetSyncStatusHandler
│   └── dto.py                  # StatusResponse
└── api/
    ├── routes.py               # Use mediator.send()
    └── quote_routes.py         # Use mediator.send()
```

## Related Code Files

### Create
- `src/features/market_data/sync/command.py`
- `src/features/market_data/sync/handler.py`
- `src/features/market_data/sync/event_handlers.py`
- `src/features/market_data/sync/dto.py`
- `src/features/market_data/ohlcv/query.py`
- `src/features/market_data/ohlcv/handler.py`
- `src/features/market_data/ohlcv/dto.py`
- `src/features/market_data/quote/subscribe_command.py`
- `src/features/market_data/quote/subscribe_handler.py`
- `src/features/market_data/quote/get_query.py`
- `src/features/market_data/quote/get_handler.py`
- `src/features/market_data/quote/event_handlers.py`
- `src/features/market_data/quote/dto.py`
- `src/features/market_data/status/query.py`
- `src/features/market_data/status/handler.py`
- `src/features/market_data/status/dto.py`

### Modify
- `src/features/market_data/api/routes.py` - Use mediator
- `src/features/market_data/api/quote_routes.py` - Use mediator
- `src/main.py` - Register handlers with mediator

### Delete (after migration)
- `src/features/market_data/services/data_sync_service.py`
- `src/features/market_data/services/quote_service.py`

## Implementation Steps

1. **Create Sync commands and handler**
   ```python
   # src/features/market_data/sync/command.py
   from dataclasses import dataclass
   from typing import List, Optional

   @dataclass
   class SyncSymbolCommand:
       symbol: str
       exchange: str
       interval: str = "1d"
       n_bars: int = 500
       background: bool = False

   @dataclass
   class BulkSyncCommand:
       symbols: List[dict]  # [{symbol, exchange, interval, n_bars}]

   # src/features/market_data/sync/handler.py
   from src.common.mediator import Handler
   from src.infrastructure.persistence import Database, Cache
   from src.infrastructure.tradingview import TradingViewProvider
   from src.domain.ohlcv.aggregate import OHLCVAggregate
   from src.common.messaging import EventBus

   class SyncSymbolHandler(Handler[SyncSymbolCommand, dict]):
       def __init__(self, provider: TradingViewProvider, event_bus: EventBus):
           self.provider = provider
           self.event_bus = event_bus

       async def handle(self, cmd: SyncSymbolCommand) -> dict:
           # Fetch from TradingView
           bars = await self.provider.fetch_ohlcv(
               cmd.symbol, cmd.exchange, cmd.interval, cmd.n_bars
           )

           # Direct DB upsert
           collection = Database.get_collection("ohlcv")
           # ... bulk_write logic from data_sync_service

           # Create aggregate and publish events
           aggregate = OHLCVAggregate(symbol=cmd.symbol, exchange=cmd.exchange)
           aggregate.record_sync(cmd.interval, len(bars), bars[-1].timestamp)
           await self.event_bus.publish_all(aggregate.get_uncommitted_events())

           return {"bars_synced": len(bars)}
   ```

2. **Create OHLCV query and handler**
   ```python
   # src/features/market_data/ohlcv/query.py
   from dataclasses import dataclass

   @dataclass
   class GetOHLCVQuery:
       symbol: str
       exchange: str
       interval: str = "1d"
       limit: int = 100
       start_time: Optional[int] = None
       end_time: Optional[int] = None

   # src/features/market_data/ohlcv/handler.py
   from src.common.mediator import Handler
   from src.infrastructure.persistence import Database, Cache
   from src.common.constants import COLLECTION_OHLCV, CACHE_KEY_OHLCV, TTL_OHLCV_QUERY

   class GetOHLCVHandler(Handler[GetOHLCVQuery, list]):
       async def handle(self, query: GetOHLCVQuery) -> list:
           # Check cache first
           cache_key = CACHE_KEY_OHLCV.format(
               symbol=query.symbol,
               exchange=query.exchange,
               interval=query.interval,
               limit=query.limit
           )
           cached = await Cache.get(cache_key)
           if cached:
               return cached

           # Query DB
           collection = Database.get_collection(COLLECTION_OHLCV)
           cursor = collection.find({
               "symbol": query.symbol,
               "exchange": query.exchange,
               "interval": query.interval
           }).sort("timestamp", -1).limit(query.limit)

           bars = await cursor.to_list(length=query.limit)

           # Cache result
           await Cache.set(cache_key, bars, ttl=TTL_OHLCV_QUERY)

           return bars
   ```

3. **Create Quote commands and handlers**
   ```python
   # src/features/market_data/quote/subscribe_command.py
   from dataclasses import dataclass

   @dataclass
   class SubscribeCommand:
       symbol: str
       exchange: str

   @dataclass
   class UnsubscribeCommand:
       symbol: str
       exchange: str

   @dataclass
   class StartQuoteFeedCommand:
       pass

   @dataclass
   class StopQuoteFeedCommand:
       pass
   ```

4. **Update routes to use mediator**
   ```python
   # src/features/market_data/api/routes.py
   from fastapi import APIRouter, Depends
   from src.common.mediator import Mediator
   from src.common.mediator.dependencies import get_mediator
   from src.features.market_data.sync.command import SyncSymbolCommand
   from src.features.market_data.ohlcv.query import GetOHLCVQuery

   router = APIRouter(prefix="/market-data")

   @router.post("/sync")
   async def sync_symbol(
       request: SyncRequest,
       mediator: Mediator = Depends(get_mediator)
   ):
       cmd = SyncSymbolCommand(
           symbol=request.symbol,
           exchange=request.exchange,
           interval=request.interval,
           n_bars=request.n_bars
       )
       return await mediator.send(cmd)

   @router.get("/ohlcv/{exchange}/{symbol}")
   async def get_ohlcv(
       exchange: str,
       symbol: str,
       interval: str = "1d",
       limit: int = 100,
       mediator: Mediator = Depends(get_mediator)
   ):
       query = GetOHLCVQuery(
           symbol=symbol,
           exchange=exchange,
           interval=interval,
           limit=limit
       )
       return await mediator.send(query)
   ```

5. **Register handlers in main.py**
   ```python
   # In lifespan
   from src.features.market_data.sync.command import SyncSymbolCommand
   from src.features.market_data.sync.handler import SyncSymbolHandler

   provider = TradingViewProvider(settings)

   mediator.register(SyncSymbolCommand, SyncSymbolHandler(provider, event_bus))
   mediator.register(GetOHLCVQuery, GetOHLCVHandler())
   # ... register all handlers
   ```

6. **Create event handlers for side effects**
   ```python
   # src/features/market_data/sync/event_handlers.py
   from src.domain.ohlcv.events import HistoricalDataSynced
   from src.infrastructure.persistence import Cache

   async def invalidate_cache_on_sync(event: HistoricalDataSynced):
       pattern = f"ohlcv:{event.symbol}:{event.exchange}:*"
       await Cache.delete_pattern(pattern)

   # Register in main.py
   event_bus.subscribe(HistoricalDataSynced, invalidate_cache_on_sync)
   ```

## Todo List

- [x] Create `sync/` directory with command, handler, dto
- [x] Create `ohlcv/` directory with query, handler, dto
- [x] Create `quote/` directory with commands, handlers, dto
- [x] Create `status/` directory with query, handler, dto
- [x] Update `routes.py` to use mediator
- [x] Update `quote_routes.py` to use mediator
- [x] Register all handlers in `main.py`
- [x] Register event handlers in `main.py`
- [x] Migrate logic from old services
- [x] Delete old service files
- [ ] Run tests

## Success Criteria

- [x] All routes dispatch via mediator
- [x] Commands/Queries are simple data classes
- [x] Handlers contain all business logic
- [x] Domain events published after state changes
- [x] Existing API contracts unchanged
- [ ] All tests pass

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| API contract change | Medium | High | Test all endpoints |
| Missing handler | Low | High | Register at startup |
| Logic migration bugs | Medium | Medium | Copy-paste, then refactor |

## Security Considerations

- Handlers inherit service security patterns
- Input validation in DTOs
- No credential exposure

## Next Steps

After completion:
- Phase 6 adds cross-cutting middleware
- Correlation IDs will flow through mediator
