# Phase 03 Report — IDataProvider abstraction + TradingView removal

**Date:** 2026-05-08
**Phase file:** `plans/260507-1835-vps-bars-mismatch-tv-pro-fix/phase-03-idataprovider-abstraction-and-tv-removal.md`

## Status

**Status:** DONE
**Summary:** 17 files modified/created, 3 folders deleted, 4 grep guards pass, 44/44 unit tests pass, 0 pyright errors.

## Files Created

- `packages/pocketquant-core/src/pocketquant/core/infrastructure/data_provider.py` — IDataProvider ABC (relocated from tradingview/base.py)
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/realtime_quote_provider.py` — IRealtimeQuoteProvider Protocol @runtime_checkable (9 members)
- `packages/pocketquant-api/tests/unit/di/test_di_data_provider.py` — 4 DI unit tests

## Files Modified

- `binance_client.py` — import path → `infrastructure.data_provider`
- `core/config.py` — removed `tradingview_username`, `tradingview_password`
- `api/di/infrastructure.py` — `get_tv_client` → `get_data_provider() -> IDataProvider` (BinanceClient)
- `api/di/market_data.py` — `get_ws_client` → `get_realtime_quote_provider() -> IRealtimeQuoteProvider` (BinanceWebSocketClient); provider params updated
- `quote_app_service.py` — annotation `TradingViewWebSocketClient` → `IRealtimeQuoteProvider`
- `ws_subscription_manager.py` — annotation updated; stale docstring fixed
- `main_extensions.py` — `TradingViewWebSocketClient` → `IRealtimeQuoteProvider`
- `sync_jobs.py` — `TradingViewClient` → `IDataProvider`; `container.get(TradingViewClient)` → `IDataProvider`
- `backfill/handler.py` — provider type → `IDataProvider`
- `backfill/route.py` — `FromDishka[TradingViewClient]` → `FromDishka[IDataProvider]`
- `quotes/get_status/handler.py` — `TradingViewWebSocketClient` → `IRealtimeQuoteProvider`
- `sync_one/handler.py` — provider type → `IDataProvider`
- `sync_one/provider_fetch.py` — provider type + docstring updated
- `tests/unit/handlers/sync/test_provider_fetch.py` — stale TV comment → IDataProvider
- `tests/unit/handlers/sync/test_no_progress_tracking.py` — stale TV comment → IDataProvider
- `packages/pocketquant-core/pyproject.toml` — removed `tvdatafeed` dep
- `.env.example` — removed `TRADINGVIEW_USERNAME`, `TRADINGVIEW_PASSWORD` block

## Deleted

- `packages/pocketquant-core/src/pocketquant/core/infrastructure/tradingview/` (entire folder: base.py, tradingview_client.py, tradingview_websocket_client.py, __init__.py)
- `packages/pocketquant-core/tests/unit/infrastructure/tradingview/` (test_websocket.py)
- `packages/pocketquant-core/tests/integration/tradingview/` (test_websocket_integration.py)

## Grep Guards (all pass)

```
✓ no tvdatafeed
✓ no TV classes
✓ no tradingview imports
✓ no TV env vars
```

## Tests

- `pocketquant-core` unit: 64/64 passed
- `pocketquant-api` unit: 44/44 passed (incl. 4 new DI tests)
- `pyright`: 0 errors, 0 warnings on modified files
- `ruff`: 0 errors on modified/created files

## Design Notes

- `IRealtimeQuoteProvider` is `Protocol` (not ABC) — future providers (OKX) need no inheritance
- `type: ignore[return-value]` in `market_data.py` line 26: Pyright cannot prove structural match at return site; runtime `isinstance()` in DI test confirms correctness
- `subscriptions` property on Protocol typed as `dict` (generic); BinanceWebSocketClient returns `dict[str, tuple]` — `.keys()` call in WsSubscriptionManager works correctly
