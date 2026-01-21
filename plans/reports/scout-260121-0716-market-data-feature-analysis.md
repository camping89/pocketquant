# Market Data Feature Analysis Report

Date: 2026-01-21 | Focus: market_data feature slice | Scope: 2,714 LOC

## Executive Summary

The market_data feature implements data synchronization and real-time quotes using vertical slice architecture. Two independent pipelines: historical data (TradingView REST to MongoDB) and real-time quotes (TradingView WebSocket to Redis + MongoDB).

## Architecture

- api/ (472 LOC) - FastAPI routes
- services/ (848 LOC) - Business logic
- repositories/ (428 LOC) - Data access
- models/ (289 LOC) - Pydantic models
- providers/ (572 LOC) - TradingView integrations
- jobs/ (118 LOC) - Scheduled sync

## API Endpoints

Market Data:
- POST /market-data/sync (single, blocking)
- POST /market-data/sync/background (async)
- POST /market-data/sync/bulk (multiple)
- GET /market-data/ohlcv/{exchange}/{symbol}
- GET /market-data/symbols
- GET /market-data/sync-status

Real-time Quotes:
- POST /quotes/start/stop
- POST /quotes/subscribe/unsubscribe
- GET /quotes/latest/{exchange}/{symbol}
- GET /quotes/all
- GET /quotes/current-bar/{exchange}/{symbol}
- GET /quotes/status

## Services

DataSyncService (244 LOC):
- Per-request via dependency injection
- sync_symbol: Updates status (pending -> syncing -> completed/error)
- Fetches from TradingView in thread pool
- Upserts to MongoDB, updates metadata
- Caches invalidation: Cache.delete_pattern()

QuoteService (236 LOC):
- Global singleton for WebSocket persistence
- start/stop: Manage connection lifecycle
- subscribe: Register callbacks
- _on_quote_update: Cache quote (Redis 60s), feed aggregator
- is_running: Checks both _running flag AND provider.is_connected()

QuoteAggregator (368 LOC):
- Converts ticks to OHLCV bars at multiple intervals
- BarBuilder: Stateful container with OHLC/V tracking
- Time alignment: Midnight UTC for daily, epoch-aligned for intraday
- asyncio.Lock: Thread-safe concurrent updates
- flush_all_bars: Save in-progress bars on shutdown

## Repositories

OHLCVRepository (299 LOC):
- All class methods (stateless)
- Collections: ohlcv, sync_status
- upsert_many: Bulk operations with unique key
- get_bars: Query with filters, sorted descending
- update_sync_status: Track sync progress

SymbolRepository (129 LOC):
- Class method CRUD
- Collections: symbols

## Models

- Interval: 13 timeframes (1m to 1M)
- OHLCV, OHLCVCreate, SyncStatus
- Quote, QuoteTick, AggregatedBar
- Symbol, SymbolBase

## Providers

TradingViewProvider (217 LOC):
- ThreadPoolExecutor (max 4): Isolate blocking I/O
- Wraps tvdatafeed library
- 5000 bar max enforced
- Lazy client init with optional auth

TradingViewWebSocketProvider (355 LOC):
- Protocol: wss://data.tradingview.com/socket.io/websocket
- Message format: ~m~{length}~m~{json}
- Auto-reconnect: Exponential backoff 1s to 60s
- Re-subscribes after reconnect
- Responds to heartbeat pings

## Jobs

sync_all_symbols: Every 6 hours (n_bars=500)
sync_daily_data: Hourly Mon-Fri 9-17 UTC (n_bars=10, daily only)
register_sync_jobs: Called at app startup

## Caching

Redis Layers (TTLs):
- quote:latest:{EXCHANGE}:{SYMBOL} (60s)
- bar:current:{EXCHANGE}:{SYMBOL}:{interval} (300s)
- ohlcv:{SYMBOL}:{EXCHANGE}:{interval}:{limit} (300s)

Invalidation:
- After sync: Cache.delete_pattern
- On unsubscribe: Delete quote cache
- On shutdown: flush_all_bars saves in-progress

## Error Handling

DataSyncService: Catches errors, updates status, returns error dict
QuoteService: Isolated callbacks, auto-reconnect, re-subscribe
QuoteAggregator: asyncio.Lock (atomic), empty bars skip, flush on stop
Jobs: Per-symbol errors don't break loop

## Key Design Decisions

1. Two service patterns: DataSyncService (per-request), QuoteService (singleton)
2. Repository as static methods: Stateless design
3. Thread pool: Isolate blocking I/O
4. Aggregator: Single tick feeds all intervals
5. Cache invalidation: Pattern-based + TTL-based
6. No bar loss: flush_all_bars saves on stop

## Strengths

- Vertical slice architecture
- Clear separation of concerns
- Minimal comments (only non-obvious)
- Full type hints + Pydantic validation
- Robust error handling + logging
- Resource cleanup (close, finally blocks)
- Async-first + thread pool isolation
- Multiple intervals (1m to 1M)
- Flexible caching with TTLs
- Independent pipelines

## Considerations

- Bulk sync sequential (could parallelize)
- WebSocket singleton needs lifecycle care
- Aggregator intervals hardcoded at init
- Redis SCAN slow with many keys (noted)
- Symbol search unimplemented
- No explicit rate limiting

## Unresolved Questions

1. TradingView credentials scoped per environment?
2. Sequential bulk sync intentional?
3. How are symbols initially added to tracking?
4. Provider implement rate limiting?
5. Aggregator intervals configurable post-init?
