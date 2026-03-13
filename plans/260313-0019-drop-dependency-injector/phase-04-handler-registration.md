# Phase 4: Rewrite Handler Registration

**Priority:** High | **Status:** Pending | **Effort:** M

## Overview

Replace string-based `getattr(container, name)` + `resolve()` with explicit handler constructor calls. No more `_HANDLER_PROVIDERS` string list, no more `asyncio.gather` with awaitable detection.

## Context Links

- Current: `src/container.py:231-365` (27 Factory providers + string list + register fn)
- Handler registry: `src/common/mediator/handler_registry.py`

## Implementation Steps

1. Create `src/handler-registration.py` (or add to `src/main_extensions.py`):

```python
"""CQRS handler construction and registration."""

from src.common.mediator.handler_registry import HandlerRegistry
from src.services import Services

# All handler imports (same as current container.py lines 24-55)
from src.features.market_data.sync.sync_one.handler import SyncSymbolHandler
from src.features.market_data.sync.sync_bulk.handler import BulkSyncHandler
# ... all 27 handler imports ...


def register_all_handlers(services: Services) -> None:
    """Register all CQRS handlers with mediator — explicit constructors."""
    mediator = services.mediator
    registry = HandlerRegistry()

    handlers = [
        # Market data (13)
        SyncSymbolHandler(
            provider=services.tv_provider,
            event_bus=services.event_bus,
            cache=services.cache,
            ohlcv_repository=services.ohlcv_repository,
            symbol_repository=services.symbol_repository,
            sync_status_repository=services.sync_status_repository,
        ),
        BulkSyncHandler(sync_handler=SyncSymbolHandler(
            provider=services.tv_provider,
            event_bus=services.event_bus,
            cache=services.cache,
            ohlcv_repository=services.ohlcv_repository,
            symbol_repository=services.symbol_repository,
            sync_status_repository=services.sync_status_repository,
        )),
        GetOHLCVHandler(cache=services.cache, ohlcv_repository=services.ohlcv_repository),
        StartQuoteFeedHandler(quote_service=services.quote_service),
        StopQuoteFeedHandler(quote_service=services.quote_service),
        SubscribeHandler(quote_service=services.quote_service),
        UnsubscribeHandler(quote_service=services.quote_service, cache=services.cache),
        GetLatestQuoteHandler(cache=services.cache),
        GetAllQuotesHandler(quote_service=services.quote_service, cache=services.cache),
        GetSyncStatusHandler(sync_status_repository=services.sync_status_repository),
        GetSymbolSyncStatusHandler(sync_status_repository=services.sync_status_repository),
        GetQuoteServiceStatusHandler(quote_service=services.quote_service),
        ListSymbolsHandler(symbol_repository=services.symbol_repository),

        # Trading (4)
        ListOrdersHandler(order_manager=services.order_manager),
        GetOrderHandler(order_manager=services.order_manager),
        ListPositionsHandler(position_tracker=services.position_tracker),
        GetPositionHandler(position_tracker=services.position_tracker),

        # Strategy (5)
        LoadStrategyHandler(engine=services.strategy_engine),
        StartStrategyHandler(engine=services.strategy_engine),
        StopStrategyHandler(engine=services.strategy_engine),
        GetStrategiesHandler(engine=services.strategy_engine),
        GetStrategyHandler(engine=services.strategy_engine),

        # Backtesting (5)
        RunBacktestHandler(
            event_bus=services.event_bus,
            strategy_engine=services.strategy_engine,
            backtest_repository=services.backtest_repository,
            ohlcv_repository=services.ohlcv_repository,
        ),
        RunOptimizationHandler(
            event_bus=services.event_bus,
            strategy_engine=services.strategy_engine,
            backtest_repository=services.backtest_repository,
            ohlcv_repository=services.ohlcv_repository,
            optimization_repository=services.optimization_repository,
        ),
        GetBacktestHandler(backtest_repository=services.backtest_repository),
        GetOptimizationHandler(optimization_repository=services.optimization_repository),
        ListBacktestsHandler(backtest_repository=services.backtest_repository),
    ]

    registry.register_all(mediator, handlers)
```

## Key Changes

| Before | After |
|--------|-------|
| `providers.Factory(Handler, dep=dep)` | `Handler(dep=services.dep)` |
| String list `_HANDLER_PROVIDERS` | Direct constructor list |
| `asyncio.gather(*(resolve(...)))` | Synchronous construction |
| `resolve()` to handle Futures | No Futures — instances are concrete |

## Important: BulkSyncHandler

Current container has `BulkSyncHandler(sync_handler=sync_symbol_handler)` where `sync_symbol_handler` is a Factory. Need to verify if BulkSyncHandler expects a handler *instance* or a *factory*. Check constructor signature during implementation.

## Todo

- [ ] Create handler registration function (in `src/handler-registration.py` or `src/main_extensions.py`)
- [ ] Move all 27 handler imports from `container.py`
- [ ] Verify each handler's constructor params match Services fields
- [ ] Special attention: BulkSyncHandler's sync_handler dependency
- [ ] Remove `resolve()` helper entirely
- [ ] Remove `_HANDLER_PROVIDERS` string list
- [ ] Run `pyright` to verify constructor args

## Success Criteria

- All 27 handlers registered with correct dependencies
- No `resolve()`, no `asyncio.gather`, no `getattr` string lookup
- Pyright validates all constructor calls
- Mediator dispatches correctly (existing tests pass)
