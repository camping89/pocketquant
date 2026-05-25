# handler-pipelines.md Rewrite Report

**Date:** 2026-05-25 | **Task:** Correct stale API paths post-composite-symbol refactor

## Path Patterns Updated (9 changes)

| # | Handler | Old Path | New Path |
|---|---------|----------|----------|
| 3 | ~~GetBarsHandler~~ → **GetOHLCVHandler** | `GET /market-data/bar/{exchange}/{symbol}?interval=...` | `GET /market-data/ohlcv/{symbol}/{interval}` |
| 4 | StartQuoteFeedHandler | `POST /market-data/quotes/start` | **STALE** — endpoint removed, feed auto-starts at lifespan |
| 5 | StopQuoteFeedHandler | `POST /market-data/quotes/stop` | **STALE** — endpoint removed, teardown at lifespan |
| 6 | SubscribeHandler | `POST /market-data/quotes/subscribe` | `POST /quotes/subscribe` |
| 7 | UnsubscribeHandler | `POST /market-data/quotes/unsubscribe` | `POST /quotes/unsubscribe` |
| 8 | GetLatestQuoteHandler | `GET /market-data/quotes/latest/{exchange}/{symbol}` | `GET /quotes/latest/{symbol}` |
| 9 | GetAllQuotesHandler | `GET /market-data/quotes` | `GET /quotes/all` |
| 12 | GetSymbolSyncStatusHandler | `GET /market-data/sync-status/{symbol}/{exchange}` | `GET /market-data/sync-status/{symbol}?interval=1d` |
| 13 | ~~GetQuoteServiceStatusHandler~~ → **GetQuotesStatusHandler** | `GET /market-data/quotes/status` | `GET /quotes/status` |

Additional: Trading handler routes added explicitly (were prose-only): `GET /trading/orders`, `GET /trading/orders/{order_id}`, `GET /trading/positions`, `GET /trading/positions/{strategy_id}`.

Cache key pattern corrected: `QUOTE_LATEST:{exchange}:{symbol}` → `QUOTE_LATEST:{symbol}` in sections 7, 9, and real-time data flow.

## Handler Class Names Corrected (6 renames)

| Doc name (old) | Code name (actual) |
|---|---|
| GetBarsHandler | GetOHLCVHandler |
| GetQuoteServiceStatusHandler (handler 13) | GetQuotesStatusHandler |
| GetOneStrategyHandler | GetStrategyHandler |
| GetAllStrategiesHandler | GetStrategiesHandler |
| AddSubscriptionHandler | AddSymbolHandler |
| DeleteSubscriptionHandler | RemoveSymbolHandler |

## Handlers Marked STALE (2)

- Handler 4: `StartQuoteFeedHandler` — no route exists, feed auto-starts at app lifespan (`start_quote_feed` in `main_extensions.py`).
- Handler 5: `StopQuoteFeedHandler` — same; teardown at `stop_quote_feed` lifespan.

## Handlers in Code NOT in Doc (gaps — not added, flagging only)

These exist in code but the doc has no section for them:

| Handler | Route |
|---|---|
| `GetQuoteServiceStatusHandler` (market-data/status) | `GET /api/v1/market-data/status` |
| `AddTrackedSymbolHandler` | `POST /api/v1/market-data/tracked-symbols` |
| `ListTrackedSymbolsHandler` | `GET /api/v1/market-data/tracked-symbols` |
| `RemoveTrackedSymbolHandler` | `DELETE /api/v1/market-data/tracked-symbols/{symbol}` |
| `UpdateTrackedSymbolHandler` | `PUT /api/v1/market-data/tracked-symbols/{symbol}` |
| `BackfillTrackedSymbolHandler` | `POST /api/v1/market-data/tracked-symbols/{symbol}/backfill` |
| `GetStrategyPositionsHandler` | `GET /api/v1/strategies/{strategy_id}/positions` |
| `GetStrategyTradesHandler` | `GET /api/v1/strategies/{strategy_id}/trades` |
| Equity endpoint (GetBacktestHandler) | `GET /api/v1/backtest/{run_id}/equity` |
| List available strategies | `GET /api/v1/backtest/strategies` |

Code has ~38 handlers; doc covers 35 (2 of which are now STALE). Net undocumented: ~10 handlers/routes.

## Final Line Count

856 lines (was 837 — +19 lines from STALE annotations and route table additions).

## Files Modified

- `D:\w\_me\algo-bot\pocketquant\docs\handler-pipelines.md` — 9 path corrections, 6 class renames, 2 STALE annotations, 1 banner update, 1 trading routes table added
