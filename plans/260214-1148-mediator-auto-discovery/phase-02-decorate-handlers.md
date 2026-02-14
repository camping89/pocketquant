# Phase 2: Decorate All 28 Handlers with `@handles`

**Priority:** High | **Status:** Pending

## Overview

Add `@handles(RequestType)` decorator to every existing handler class. Mechanical change — no logic changes.

## All 28 Handlers to Decorate

### market_data (14 handlers)

| Handler | Request Type | File |
|---------|-------------|------|
| `SyncSymbolHandler` | `SyncSymbolCommand` | `sync/sync_one/handler.py` |
| `BulkSyncHandler` | `BulkSyncCommand` | `sync/sync_bulk/handler.py` |
| `GetOHLCVHandler` | `GetOHLCVQuery` | `ohlcv/get_ohlcv/handler.py` |
| `StartQuoteFeedHandler` | `StartQuoteFeedCommand` | `quotes/start_feed/handler.py` |
| `StopQuoteFeedHandler` | `StopQuoteFeedCommand` | `quotes/stop_feed/handler.py` |
| `SubscribeHandler` | `SubscribeCommand` | `quotes/subscribe/handler.py` |
| `UnsubscribeHandler` | `UnsubscribeCommand` | `quotes/unsubscribe/handler.py` |
| `GetLatestQuoteHandler` | `GetLatestQuoteQuery` | `quotes/get_latest/handler.py` |
| `GetAllQuotesHandler` | `GetAllQuotesQuery` | `quotes/get_all/handler.py` |
| `GetSyncStatusHandler` | `GetSyncStatusQuery` | `status/get_sync_status/handler.py` |
| `GetSymbolSyncStatusHandler` | `GetSymbolSyncStatusQuery` | `status/get_symbol_sync_status/handler.py` |
| `GetQuoteServiceStatusHandler` | `GetQuoteServiceStatusQuery` | `status/get_quote_service_status/handler.py` |
| `ListSymbolsHandler` | `ListSymbolsQuery` | `list_symbols/handler.py` |

### backtesting (5 handlers)

| Handler | Request Type | File |
|---------|-------------|------|
| `RunBacktestHandler` | `RunBacktestCommand` | `run/handler.py` |
| `RunOptimizationHandler` | `RunOptimizationCommand` | `optimize/handler.py` |
| `GetBacktestHandler` | `GetBacktestQuery` | `get_result/handler.py` |
| `GetOptimizationHandler` | `GetOptimizationQuery` | `get_optimization/handler.py` |
| `ListBacktestsHandler` | `ListBacktestsQuery` | `list_results/handler.py` |

### strategy (5 handlers)

| Handler | Request Type | File |
|---------|-------------|------|
| `LoadStrategyHandler` | `LoadStrategyCommand` | `load/handler.py` |
| `StartStrategyHandler` | `StartStrategyCommand` | `start/handler.py` |
| `StopStrategyHandler` | `StopStrategyCommand` | `stop/handler.py` |
| `GetStrategiesHandler` | `GetStrategiesQuery` | `get_all/handler.py` |
| `GetStrategyHandler` | `GetStrategyQuery` | `get_one/handler.py` |

### trading (4 handlers)

| Handler | Request Type | File |
|---------|-------------|------|
| `ListOrdersHandler` | `ListOrdersQuery` | `list_orders/handler.py` |
| `GetOrderHandler` | `GetOrderQuery` | `get_order/handler.py` |
| `ListPositionsHandler` | `ListPositionsQuery` | `list_positions/handler.py` |
| `GetPositionHandler` | `GetPositionQuery` | `get_position/handler.py` |

### risk (1 handler)

| Handler | Request Type | File |
|---------|-------------|------|
| `RiskCheckHandler` | (no mediator registration — called directly) | `check_risk/handler.py` |

**Note:** `RiskCheckHandler` is NOT registered with mediator — called directly by StrategyEngine. Skip decorating it unless we want it discoverable for documentation purposes.

## Implementation Pattern

Each handler file gets one import + one decorator line:

```python
from src.common.mediator import Handler, handles
from .command import SyncSymbolCommand

@handles(SyncSymbolCommand)
class SyncSymbolHandler(Handler[SyncSymbolCommand, SyncResponse]):
    ...
```

## Success Criteria

- [ ] All 27 mediator-registered handlers decorated with `@handles`
- [ ] No logic changes in any handler
- [ ] All existing tests pass
- [ ] `ruff check` passes
