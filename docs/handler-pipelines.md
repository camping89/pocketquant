# Handler Pipelines & Detailed Flows

37 registered CQRS handlers (16 market data + 4 trading + 12 strategy + 5 backtest) + ~45 HTTP endpoints (includes SSE + app-service-direct routes). Pattern: DDD + CQRS + Extract-Method. DI: Dishka. Data provider: Binance (IDataProvider impl, 1200 weight/min rate limit).

Naming: `strategy_id` (template code) vs `subscription_id` (per-subscription instance). Symbol is composite `CODE:EXCHANGE` (URL-encoded `%3A`). Verify against OpenAPI or [README](../README.md) if a path disagrees with the live app.

This document details the complete pipeline for each CQRS handler, showing request flow, processing steps, and side effects.

**Handler & Endpoint Distribution:**
- **37 registered CQRS handlers:** Discovered by Dishka via `@handles` decorator
- **~45 HTTP endpoints total:** CQRS handlers (37) + SSE/app-service-direct routes (8)
- **37 registered handlers grouped by:**
  - **Market Data (16):** sync, bulk-sync, ohlcv, bars-stream (SSE), quotes-stream (SSE), subscriptions (6 CRUD), symbols, sync-status, quotes-status, integrity operations, tracked-symbols (5 CRUD)
  - **Backtesting (5):** run, optimize, get-backtest, get-optimization, list-backtests
  - **Strategy (12):** start, stop, get-one, get-all, add-symbol, list-symbols, remove-symbol, run-all-backtests, get-subscription-backtest, delete-cascade, (plus 2 legacy routing shims)
  - **Trading (4):** list-orders, get-order, list-positions, get-position

**Distinction:** Some routes (bars-stream, quotes-stream, integrity operations) use app-service direct calls or iterate directly over in-memory data, not mediator-routed CQRS handlers.

## A. Market Data Handlers & Endpoints (16 CQRS + 8 SSE/Direct)

### 1. SyncSymbolHandler (SyncSymbolCommand)

**Request:** POST `/api/v1/market-data/sync`

**Command Fields:**
- `symbol: str` - Trading symbol (e.g., AAPL)
- `exchange: str` - Exchange name (e.g., NASDAQ)
- `interval: Interval` - Time interval (default: DAY_1)
- `n_bars: int` - Number of bars to fetch (default: 5000)
- `skip_filter: bool` - **NEW** Bypass `_filter_new_bars` — used by repair to fill gaps (default: False)

**Implementation (Extract-Method Pattern, 8 Private Helpers):**

```python
@handles(SyncSymbolCommand)
class SyncSymbolHandler(Handler[SyncSymbolCommand, SyncResponse]):
    async def handle(self, cmd: SyncSymbolCommand) -> SyncResponse:
        """Main orchestration — clean checklist."""
        # Checklist: 8 logical steps
        bars = await self._fetch_bars(cmd)
        if not bars:
            return await self._fail("No bars returned")

        # Filter out bars we already have (skip for repair to allow gap filling)
        if not cmd.skip_filter:
            bars = await self._filter_new_bars(bars, cmd.symbol, cmd.exchange, cmd.interval)
        bars = self._filter_misaligned_bars(bars, cmd.interval)
        
        count = await self._persist_bars(bars, cmd.symbol)
        await self._invalidate_cache(cmd.symbol)
        await self._publish_sync_event(cmd, count)
        return await self._success(count)

    async def _fetch_bars(self, cmd: SyncSymbolCommand) -> List[Bar]:
        """Fetch via IDataProvider (current impl: BinanceClient).
        Returns bars with per-tick delta volumes (required by BarBuilder).
        Rate limits: Binance 1200 weight/min."""
        return await self.provider.fetch_ohlcv(
            cmd.symbol, cmd.exchange, cmd.interval, cmd.n_bars
        )

    def _validate_bars(self, bars: List[Bar]) -> None:
        """Validate bar structure."""
        if not bars:
            raise ValueError("Empty bars")
        # ... validation logic

    async def _persist_bars(self, bars: List[Bar], symbol: str) -> int:
        """Bulk insert/update to MongoDB."""
        await self.bar_repo.upsert_many(bars)
        return len(bars)

    async def _invalidate_cache(self, symbol: str) -> None:
        """Pattern-based cache deletion."""
        await self.cache.delete_pattern(f"bar:{symbol}:*")

    async def _publish_sync_event(self, cmd: SyncSymbolCommand, count: int) -> None:
        """Publish domain event."""
        event = HistoricalDataSyncedEvent(symbol=cmd.symbol, count=count)
        await self.event_bus.publish(event)

    async def _success(self, count: int) -> SyncResponse:
        """Format success response."""
        return SyncResponse(bars_synced=count, status="completed")

    async def _fail(self, reason: str) -> SyncResponse:
        """Format error response."""
        return SyncResponse(bars_synced=0, status="failed", error=reason)
```

**Benefits:**
- `handle()` reads as clear checklist (no implementation details)
- Each helper single-responsibility (testable in isolation)
- Private prefix `_` indicates internal implementation
- Improved readability and maintainability

**Side Effects:**
- MongoDB: bars collection updated
- Redis: cache invalidated (pattern: bar:*)
- EventBus: event published, subscribers react async

**Error Cases:**
- Transient (timeout): Exponential backoff + retry
- Permanent (invalid symbol): Return 400 Bad Request
- Network: Log and return error status

---

### 2. BulkSyncHandler (BulkSyncCommand)

**Request:** POST `/api/v1/market-data/sync/bulk`

**Pipeline:**
```
BulkSyncCommand(symbols: list[dict], interval, n_bars)
  ↓
For each symbol:
  └─ Delegate to SyncSymbolHandler (parallel or sequential per config)
  ↓
Collect results: BulkSyncResponse(results: List[SyncResult])
```

---

### 3. GetOHLCVHandler (GetOHLCVQuery)

**Request:** GET `/api/v1/market-data/ohlcv/{symbol}/{interval}?limit=1000&start_date=...&end_date=...`

> `{symbol}` is composite e.g. `BTCUSDT%3ABINANCE` (URL-encoded `BTCUSDT:BINANCE`).

**Pipeline:**
```
GetOHLCVQuery(symbol, interval, limit, start_date, end_date)
  ↓
Check cache: Cache.get(build_bar_cache_key(symbol, interval, limit))
  ├─ Cache HIT: Return OHLCVResponse immediately
  └─ Cache MISS:
      ↓
      Fetch: BarRepository.get_bars(symbol, interval, limit, start_date, end_date)
      └─ MongoDB bars collection, sorted by timestamp (desc)
      ↓
      Validate: Bar value objects immutable, to_mongo()/from_mongo()
      ↓
      Cache: Cache.set(key, result, ttl=300)
      └─ Redis TTL 5 minutes, key: build_bar_cache_key()
      ↓
Response: OHLCVResponse(symbol, interval, data, count)
```

**Cache Management:** Query results cached with 300s TTL using `build_bar_cache_key()`

---

### 4. StartQuoteFeedHandler (StartQuoteFeedCommand)

> ⚠️ STALE — handler removed (verify before deleting). WS feed is now auto-started at app lifespan (`start_quote_feed` in `main_extensions.py`). `POST /quotes/start` endpoint no longer exists.

**Request:** ~~POST `/api/v1/market-data/quotes/start`~~ — **REMOVED**

**Pipeline:**
```
StartQuoteFeedCommand()
  ↓
Handler.handle():
  1. Connect: BinanceWebSocketClient.connect() (implements IRealtimeQuoteProvider)
     └─ wss://stream.binance.com:9443/ws/{symbol}@aggTrade
  ↓
  2. Start async task: asyncio.create_task(provider.listen())
     └─ Background loop receives aggTrade events
  ↓
  3. Set flag: QuoteAppService.is_running = True
  ↓
Response: QuoteServiceStatus(status='connected')
```

**Background Task:** Continuously receives WebSocket frames, parses JSON, distributes to subscribers.

---

### 5. StopQuoteFeedHandler (StopQuoteFeedCommand)

> ⚠️ STALE — handler removed (verify before deleting). WS feed teardown now handled at app lifespan (`stop_quote_feed` in `main_extensions.py`). `POST /quotes/stop` endpoint no longer exists.

**Request:** ~~POST `/api/v1/market-data/quotes/stop`~~ — **REMOVED**

**Pipeline:**
```
StopQuoteFeedCommand()
  ↓
Handler.handle():
  1. Cancel task: asyncio.Task.cancel()
  ↓
  2. Disconnect: TradingViewWebSocketClient.disconnect()
  ↓
  3. Clear subscriptions: QuoteAppService._subscriptions.clear()
  ↓
  4. Set flag: QuoteAppService.is_running = False
  ↓
Response: QuoteServiceStatus(status='disconnected')
```

---

### 6. SubscribeHandler (SubscribeCommand)

**Request:** POST `/api/v1/quotes/subscribe`

**Pipeline:**
```
SubscribeCommand(symbol)
  ↓
Validate feed running (if not, return error)
  ↓
Provider.subscribe(symbol, callback=on_quote_update)
  └─ Registers callback for this composite symbol
  ↓
Cache subscription: QuoteAppService._subscriptions[symbol] = True
  ↓
Response: SubscribeResponse(symbol, subscribed=True)
```

---

### 7. UnsubscribeHandler (UnsubscribeCommand)

**Request:** POST `/api/v1/quotes/unsubscribe`

**Pipeline:**
```
UnsubscribeCommand(symbol)
  ↓
Provider.unsubscribe(symbol)
  ↓
Delete cache: Cache.delete(f"QUOTE_LATEST:{symbol}")
  ↓
Response: SubscribeResponse(subscribed=False)
```

---

### 8. GetLatestQuoteHandler (GetLatestQuoteQuery)

**Request:** GET `/api/v1/quotes/latest/{symbol}`

> `{symbol}` is composite e.g. `BTCUSDT%3ABINANCE`.

**Pipeline:**
```
GetLatestQuoteQuery(symbol)
  ↓
Fetch: Cache.get(f"QUOTE_LATEST:{symbol}")
  └─ Redis (TTL 5s, updated on each tick)
  ↓
Deserialize: QuoteTick(price, volume, timestamp)
  ↓
Response: QuoteResponse
```

---

### 9. GetAllQuotesHandler (GetAllQuotesQuery)

**Request:** GET `/api/v1/quotes/all`

**Pipeline:**
```
GetAllQuotesQuery()
  ↓
Query all subscriptions: QuoteAppService._subscriptions.keys()
  ↓
For each subscription:
  └─ Cache.get(f"QUOTE_LATEST:{symbol}")
  ↓
Serialize list: list[QuoteResponse]
  ↓
Response: list[QuoteResponse]
```

---

### 10. ListSymbolsHandler (ListSymbolsQuery)

**Request:** GET `/api/v1/market-data/symbols`

**Pipeline:**
```
ListSymbolsQuery()
  ↓
Fetch: SymbolRepository.list_all()
  └─ MongoDB symbols collection
  ↓
Serialize: List[SymbolDTO]
  ↓
Response: SymbolsDTO
```

---

### 11. GetSyncStatusHandler (GetSyncStatusQuery)

**Request:** GET `/api/v1/market-data/sync-status`

**Pipeline:**
```
GetSyncStatusQuery()
  ↓
Fetch: SyncStatusRepository.find_latest()
  └─ MongoDB sync_status collection
  ↓
Response: SyncStatusDTO(status, bars_synced, error_message)
```

---

### 12. GetSymbolSyncStatusHandler (GetSymbolSyncStatusQuery)

**Request:** GET `/api/v1/market-data/sync-status/{symbol}?interval=1d`

> `{symbol}` is composite e.g. `BTCUSDT%3ABINANCE`. Optional `interval` query param (default `1d`).

**Pipeline:**
```
GetSymbolSyncStatusQuery(symbol, interval)
  ↓
Fetch: SyncStatusRepository.find_by_symbol(symbol, interval)
  ↓
Response: SyncStatusDTO
```

---

### 13. GetQuotesStatusHandler (GetQuotesStatusQuery)

**Request:** GET `/api/v1/quotes/status`

**Pipeline:**
```
GetQuotesStatusQuery()
  ↓
Check QuoteAppService.is_running
  ↓
Count subscriptions: len(QuoteAppService._subscriptions)
  ↓
Response: QuotesStatusResponse(is_running, subscription_count)
```

---

### 14. StreamBarsHandler (SSE endpoint — app-service direct)

**Request:** GET `/api/v1/market-data/bars/stream/{symbol}?interval={interval}`

> `{symbol}` is composite e.g. `BTCUSDT%3ABINANCE`. Returns Server-Sent Events stream; NOT CQRS.

**Implementation:**
1. Client opens EventSource → server starts poll loop (interval 1.0s).
2. Every poll: `BarAppService.get_current_bar(symbol, interval)` → reads Redis `bar:current:{symbol}:{interval}`.
3. Compare vs last emitted: emit only if `bar_start` changed, `volume`/`price` increased, or `is_in_progress` flipped.
4. Fallback: If Redis miss, query MongoDB closed bars (recovery after disconnect).
5. Response stream (SSE):
   ```
   data: {"symbol":"BTCUSDT:BINANCE","interval":"1m","bar_start":1...,"open":101.0,"high":101.5,"low":100.8,"close":101.2,"volume":1000,"tick_count":10,"is_in_progress":true,"staleness_ms":50}
   ```
6. Disconnect: `asyncio.CancelledError` caught silently; client auto-retries.
7. Max lag: ~1.2s (1s poll + overhead).

**Side Effects:** None (read-only).

---

### 15. StreamQuoteHandler (SSE endpoint — app-service direct)

**Request:** GET `/api/v1/market-data/quotes/stream/{symbol}`

> `{symbol}` composite. Returns Server-Sent Events stream; NOT CQRS.

**Implementation:**
1. Client opens EventSource → server starts poll loop (interval 0.5s).
2. Every poll: `QuoteAppService.get_latest_quote(symbol)` → reads Redis `quote:latest:{symbol}`.
3. Compare vs last emitted: emit only if `last_price` or `volume` changed.
4. Fallback (initial miss): REST GET `/api/v1/market-data/quotes/latest/{symbol}` to warm-start cache.
5. Response stream (SSE):
   ```
   data: {"symbol":"BTCUSDT:BINANCE","last_price":101.50,"bid":101.48,"ask":101.52,"volume":1000,"change":0.5,"change_percent":0.49,"ts":1234567890}
   ```
6. Max lag: <700ms (0.5s poll + overhead).

**Side Effects:** None (read-only).

---

### 16. IntegrityCheckHandler (app-service direct)

**Request:** POST `/api/v1/market-data/integrity/check`

**Implementation:**
1. Scan all bars in MongoDB → validate:
   - OHLC order (open ≤ high, low ≤ close)
   - No negative volumes
   - Timestamp monotonicity within symbol+interval
   - Volume delta > 0 (no backwards ticks)
2. Return: `{total_bars, violations: [{bar_id, error_msg}, ...], valid_count}`

**Side Effects:** None (read-only diagnostic).

---

### 17. IntegrityRepairHandler (app-service direct)

**Request:** POST `/api/v1/market-data/integrity/repair`

**Implementation:**
1. Iterate violations from `IntegrityCheckHandler`
2. For each:
   - Clamp OHLC to valid order (if high < low, swap)
   - Delete bars with negative volumes
   - Trigger re-sync: `SyncSymbolCommand(symbol, interval, skip_filter=True)` to backfill
3. Return: `{repaired_count, deleted_count, resync_jobs_queued}`

**Side Effects:** MongoDB bars collection modified; sync jobs enqueued.

---

### 18. ListTrackedSymbolsHandler (ListTrackedSymbolsQuery — CQRS)

**Request:** GET `/api/v1/market-data/tracked-symbols`

**Pipeline:**
```
ListTrackedSymbolsQuery()
  ↓
Fetch: TrackedSymbolRepository.list_all()
  └─ MongoDB tracked_symbols collection
  ↓
Serialize: List[{code, exchange, status, last_sync_at}]
  ↓
Response: list[TrackedSymbolDTO]
```

---

### 19. AddTrackedSymbolHandler (AddTrackedSymbolCommand — CQRS, admin-protected)

**Request:** POST `/api/v1/market-data/tracked-symbols` (requires `X-Admin-Token` header)

**Pipeline:**
```
AddTrackedSymbolCommand(code, exchange)
  ↓
Validate: not already tracked (DuplicateKeyError → 400)
  ↓
Create: TrackedSymbol(code, exchange, status='pending', last_sync_at=None)
  ↓
Persist: TrackedSymbolRepository.add()
  ↓
Response: {code, exchange, status, created_at}
```

**Side Effects:** MongoDB tracked_symbols collection updated.

---

### 20. UpdateTrackedSymbolHandler (UpdateTrackedSymbolCommand — CQRS, admin-protected)

**Request:** PUT `/api/v1/market-data/tracked-symbols/{symbol}`

**Pipeline:**
```
UpdateTrackedSymbolCommand(code, exchange, status)
  ↓
Fetch existing: TrackedSymbolRepository.find(code, exchange) → 404 if not found
  ↓
Update: Set status (e.g., 'paused', 'active')
  ↓
Persist: TrackedSymbolRepository.update()
  ↓
Response: {code, exchange, status, updated_at}
```

---

### 21. RemoveTrackedSymbolHandler (RemoveTrackedSymbolCommand — CQRS, admin-protected)

**Request:** DELETE `/api/v1/market-data/tracked-symbols/{symbol}`

**Pipeline:**
```
RemoveTrackedSymbolCommand(code, exchange)
  ↓
Delete: TrackedSymbolRepository.delete(code, exchange) → 404 if not found
  ↓
Side effect: Unsubscribe from WS via WsSubscriptionManager (reconcile loop picks it up in next 5s cycle)
  ↓
Response: 204 No Content
```

**Side Effects:** MongoDB tracked_symbols collection updated; WS subscription eventually removed (within reconcile cycle).

---

### 22. BackfillTrackedSymbolHandler (BackfillTrackedSymbolCommand — CQRS, admin-protected)

**Request:** POST `/api/v1/market-data/tracked-symbols/{symbol}/backfill`

**Pipeline:**
```
BackfillTrackedSymbolCommand(code, exchange, interval, n_bars)
  ↓
Delegate: SyncSymbolCommand(code, exchange, interval, n_bars, skip_filter=True)
  └─ Allows re-filling gaps (filter is bypassed)
  ↓
Response: {bars_synced, status}
```

**Side Effects:** MongoDB bars collection updated via SyncSymbolHandler.

---

## B. Backtesting Handlers (5)

### 23. RunBacktestHandler (RunBacktestCommand)

**Request:** POST `/api/v1/backtest/run`

**Pipeline:**
```
RunBacktestCommand(strategy_id, symbol, start_date, end_date, params)
  ↓
Handler.handle():
  1. Resolve strategy class: STRATEGY_REGISTRY[strategy_code]
     └─ Registry lookup → IStrategy class
  ↓
  2. Fetch bars: BarRepository.get_bars(symbol, start_date, end_date)
     └─ MongoDB bars collection (renamed from ohlcv), sorted ascending by timestamp
  ↓
  3. Run backtest: BacktestAppService.run(strategy, bars, PaperBroker)
     ├─ Initialize PaperBroker with 100k starting capital
     ├─ For each bar (chronological):
     │   ├─ StrategyAppService.on_bar(bar)
     │   ├─ Strategy.on_bar(bar) → Signal(BUY/SELL/HOLD, qty)
     │   ├─ RiskCheckHandler.check_signal() → approved?
     │   ├─ PaperBroker.submit_order() → instant fill with slippage
     │   ├─ PositionAppService.update() → P&L calculation
     │   └─ Collect OrderFilledEvent
     └─ Return filled trades + final positions
  ↓
  4. Calculate metrics: PerformanceCalculator
     ├─ Sharpe ratio
     ├─ Sortino ratio
     ├─ Max drawdown
     ├─ Win rate
     └─ Return metrics
  ↓
  5. Persist: BacktestRepository.save(BacktestResult)
     └─ MongoDB backtests collection
  ↓
Response: BacktestResultDTO(run_id, sharpe, drawdown, trades)
```

**Side Effects:**
- MongoDB: backtests collection updated
- No real trades (PaperBroker simulation)

---

### 24. RunOptimizationHandler (RunOptimizationCommand)

**Request:** POST `/api/v1/backtest/optimize`

**Pipeline:**
```
RunOptimizationCommand(strategy_name, param_grid, symbol, date_range)
  ↓
Handler.handle():
  1. GridOptimizationAppService.optimize(param_grid)
     ├─ Generate parameter combinations: [(p1=1, p2=2), (p1=1, p2=3), ...]
     ├─ For each combo (parallel via multiprocessing):
     │   └─ Run BacktestAppService with params
     ├─ Collect results: {combo: (sharpe, trades, metrics)}
     └─ Rank by metric (e.g., Sharpe)
  ↓
  2. Select best: best_params, best_metric
  ↓
  3. Persist: OptimizationRepository.save(OptimizationResult)
  ↓
Response: OptimizationResultDTO(best_params, best_metric, all_results)
```

---

### 25. GetBacktestHandler (GetBacktestQuery)

**Request:** GET `/api/v1/backtest/{run_id}`

**Pipeline:**
```
GetBacktestQuery(run_id)
  ↓
Fetch: BacktestRepository.find_by_id(run_id)
  └─ MongoDB backtests collection
  ↓
Response: BacktestResultDTO
```

---

### 26. GetOptimizationHandler (GetOptimizationQuery)

**Request:** GET `/api/v1/backtest/optimization/{id}`

**Pipeline:**
```
GetOptimizationQuery(optimization_id)
  ↓
Fetch: OptimizationRepository.find_by_id(id)
  ↓
Response: OptimizationResultDTO
```

---

### 27. ListBacktestsHandler (ListBacktestsQuery)

**Request:** GET `/api/v1/backtest/strategy/{strategy_id}`

> Note: Path param `strategy_id` semantically holds a template code (from the YAML loader). The underlying handler maps this to `list_by_strategy_code()` internally. Phase 2 did not rename the backtest API surface — only its entity fields use the `subscription_id` for per-subscription instances.

**Pipeline:**
```
ListBacktestsQuery(strategy_id)
  ↓
Query: BacktestRepository.list_by_strategy_code(strategy_id)
  └─ MongoDB query with pagination
  ↓
Response: List[BacktestResultDTO]
```

---

## C. Strategy Handlers (12)

### 28. StartStrategyHandler (StartStrategyCommand)

**Request:** POST `/api/v1/subscriptions/{sub_id}/start`

**Pipeline:**
```
StartStrategyCommand(subscription_id)
  ↓
Handler.handle():
  1. Fetch: StrategyAppService.get_strategy(subscription_id)
     └─ Per-subscription strategy instance
  ↓
  2. Connect broker: IBroker.connect()
     └─ OKXBroker or PaperBroker
  ↓
  3. Initialize: await strategy.on_start()
     └─ Strategy can subscribe to quotes, set initial state
  ↓
  4. Set running: StrategyAppService.set_running(subscription_id, True)
  ↓
  5. Start listening: Subscribe to BarCompletedEvent, QuoteReceivedEvent
  ↓
Response: StrategyStatusDTO(status='running')
```

---

### 29. StopStrategyHandler (StopStrategyCommand)

**Request:** POST `/api/v1/subscriptions/{sub_id}/stop`

**Pipeline:**
```
StopStrategyCommand(subscription_id)
  ↓
Handler.handle():
  1. Call: await strategy.on_stop()
     └─ Strategy cleanup
  ↓
  2. Disconnect broker: IBroker.disconnect()
  ↓
  3. Unsubscribe: Remove BarCompletedEvent subscriber
  ↓
  4. Set running: StrategyAppService.set_running(subscription_id, False)
  ↓
Response: StrategyStatusDTO(status='stopped')
```

---

### 30. GetStrategyHandler (GetStrategyQuery) — template metadata

**Request:** GET `/api/v1/strategies/{strategy_code}`

**Pipeline:**
```
GetStrategyQuery(strategy_code)
  ↓
Lookup: STRATEGY_REGISTRY.get(strategy_code)
  └─ Returns the registered template class or None
  ↓
Response: {strategy_code, class_name, description} or 404
```

---

### 31. GetStrategiesHandler (GetStrategiesQuery) — list templates

**Request:** GET `/api/v1/strategies/`

**Pipeline:**
```
GetStrategiesQuery()
  ↓
Iterate: STRATEGY_REGISTRY.keys()
  ↓
Response: list[{strategy_code}]
```

---

### 32. AddSymbolHandler (AddSymbolCommand) — create subscription

**Request:** POST `/api/v1/strategies/{strategy_code}/subscriptions`

**Pipeline:**
```
AddSymbolCommand(strategy_id=strategy_code, symbol, interval)
  ↓
Handler.handle():
  1. Validate: TrackedSymbolRepository.exists(symbol) → 404 SYMBOL_NOT_TRACKED if missing
  ↓
  2. Resolve template: STRATEGY_REGISTRY.get(strategy_code) → 404 if unknown
  ↓
  3. Compute sub_id: Subscription.deterministic_id(strategy_code, symbol, interval)
     └─ sha256(f"{strategy_code}|{symbol.upper()}|{interval_val}")[:16]
  ↓
  4. Auto-load instance: if StrategyAppService.get_strategy(sub_id) is None
     └─ StrategyAppService.load_strategy(StrategyConfig(id=sub_id, name=strategy_code, ...))
  ↓
  5. Persist: SubscriptionRepository.add(Subscription(id=sub_id, strategy_code, symbol, interval))
     └─ DuplicateKeyError → SubscriptionAlreadyExistsError (400 DomainError)
  ↓
Response: {id, strategy_code, symbol, interval, created_at}
```

**Side Effects:**
- MongoDB: document inserted into `subscriptions` collection
- In-process: new IStrategy instance loaded into `StrategyAppService._strategies[sub_id]`

---

### 33. ListSymbolsHandler (ListSymbolsQuery) — list subscriptions

**Request:** GET `/api/v1/subscriptions/?strategy_code=...` (filter optional)

**Pipeline:**
```
ListSymbolsQuery(strategy_code: str | None)
  ↓
Fetch: SubscriptionRepository.list_all() if filter None
       else SubscriptionRepository.list_by_strategy_code(strategy_code)
  └─ MongoDB query: subscriptions {strategy_code} (index: ix_subscriptions_strategy_code)
  ↓
Enrich (single batched call): BacktestRepository.get_subscription_statuses([sub_ids])
  ↓
Compute is_running per sub: StrategyAppService.get_strategy(sub.id).is_running
  ↓
Response: list[{id, strategy_code, symbol, interval, created_at, is_running, backtest}]
```

---

### 34. RemoveSymbolHandler (RemoveSymbolCommand) — delete one subscription

**Request:** DELETE `/api/v1/subscriptions/{sub_id}`

**Pipeline:**
```
RemoveSymbolCommand(sub_id)
  ↓
Handler.handle():
  1. Cancel scheduled job: JobScheduler.remove_job(f"bt:{sub_id}") (suppress errors)
  ↓
  2. Unload runtime instance: StrategyAppService.unload_strategy(sub_id) if loaded
  ↓
  3. Delete cached backtest: BacktestRepository.delete_by_subscription(sub_id)
  ↓
  4. Delete subscription: SubscriptionRepository.delete(sub_id)
  ↓
Response: 204 No Content
```

**Side Effects:**
- MongoDB: document deleted from `subscriptions`
- MongoDB: backtest doc with `_id=sub_id` in `backtest_runs` deleted (if exists)
- APScheduler: any pending `bt:{sub_id}` job cancelled
- In-process: `StrategyAppService._strategies[sub_id]` and friends popped

---

### 35. RunAllBacktestsHandler (RunAllBacktestsCommand) — fan-out backtests

**Request:** POST `/api/v1/strategies/{strategy_code}/run-all-backtests`

**Pipeline:**
```
RunAllBacktestsCommand(strategy_id=strategy_code)
  ↓
Handler.handle():
  1. Fetch subscriptions: SubscriptionRepository.list_by_strategy_code(strategy_code)
     └─ 404 NotFoundError if no subscriptions exist for the template
  ↓
  2. For each subscription:
     └─ JobScheduler.add_one_off_job(
          "pocketquant.backtest.jobs.subscription_backtest_jobs:run_subscription_backtest",
          job_id=f"bt:{sub.id}",
          subscription_id=sub.id,
        )
  ↓
Response: {job_ids: [...]} (HTTP 202)
```

**Job Worker:** `pocketquant.backtest.jobs.subscription_backtest_jobs:run_subscription_backtest(subscription_id)`
- Resolve subscription → `sub.strategy_code`, `sub.symbol`, `sub.interval`
- `BacktestRepository.upsert_status(sub_id, strategy_code=..., status='running')`
- Load synthetic instance under `f"{strategy_code}::bt::{sub_id}"` (concurrency-safe)
- `BacktestAppService.run(BacktestConfig(strategy_code, symbol, interval, ...))` (PaperBroker)
- TOCTOU recheck: skip persist if subscription was deleted mid-run
- Persist via `BacktestRepository.save_for_subscription(sub_id, result)` → `_id = sub_id`
- Maps `result.status`: `'failed' → 'failed' + error_msg`; otherwise `'completed'`

**Side Effects:**
- APScheduler: one-off job enqueued per subscription (`apscheduler_jobs` collection)
- MongoDB `backtest_runs`: status doc created/updated with `status='running'` then terminal status

---

### 36. GetSubscriptionBacktestHandler (GetSubscriptionBacktestQuery)

**Request:** GET `/api/v1/subscriptions/{sub_id}/backtest`

**Pipeline:**
```
GetSubscriptionBacktestQuery(sub_id)
  ↓
Fetch: BacktestRepository.find_doc_by_subscription(sub_id)
  └─ MongoDB query: backtest_runs {_id: sub_id} (sparse unique on subscription_id)
  └─ Returns raw doc including status='running'|'failed'|'completed'
  ↓
Response: raw doc | 404 NotFoundError ("trigger a run via run-all-backtests first")
```

---

### 37. DeleteStrategyHandler (DeleteStrategyCommand) — cascade by template

**Request:** DELETE `/api/v1/strategies/{strategy_code}`

**Pipeline:**
```
DeleteStrategyCommand(strategy_id=strategy_code)
  ↓
Handler.handle():
  1. Fetch subs: SubscriptionRepository.list_by_strategy_code(strategy_code)
  ↓
  2. For each sub: cancel JobScheduler job f"bt:{sub.id}" + unload instance from StrategyAppService
  ↓
  3. Delete cached backtests: BacktestRepository.delete_by_strategy_code(strategy_code)
  ↓
  4. Delete subscriptions: SubscriptionRepository.delete_by_strategy_code(strategy_code)
  ↓
  5. Also unload any legacy template-keyed instance (pre-refactor data)
  ↓
Response: 204 No Content
```

**Side Effects:**
- In-memory: every `sub.id`-keyed instance for this template unloaded from StrategyAppService
- MongoDB `subscriptions`: all docs with matching `strategy_code` deleted
- MongoDB `backtest_runs`: all docs with matching `strategy_code` deleted
- APScheduler: all `bt:{sub.id}` jobs for this template cancelled

---

## D. Trading Handlers (4)

### 38-41. Order & Position Handlers

Simple in-memory reads from `OrderAppService` and `PositionAppService`.

**Routes:**
```
38. ListOrdersHandler:    GET /api/v1/trading/orders                  → list[OrderDTO]
39. GetOrderHandler:      GET /api/v1/trading/orders/{order_id}       → OrderDTO
40. ListPositionsHandler: GET /api/v1/trading/positions               → list[PositionDTO]
41. GetPositionHandler:   GET /api/v1/trading/positions/{subscription_id} → PositionDTO
```

**Pipelines:**
```
38. ListOrdersHandler:    OrderAppService.list_all() → list[dict]
39. GetOrderHandler:      OrderAppService.get_by_id(order_id) → dict
40. ListPositionsHandler: PositionAppService.list_all() → list[dict]
41. GetPositionHandler:   PositionAppService.get_async(subscription_id) → dict
```

---

## Key Data Flows

> End-to-end data flows (historical sync, real-time quotes, integrity, strategy execution, backtesting, optimization) are documented once in [system-architecture.md](./system-architecture.md#data-pipelines-overview). This file covers the per-handler detail above; the cross-handler pipelines are not duplicated here.

**Real-time wiring status (unique to this surface):** Live `BarCompletedEvent` → strategy execution is wired today only in backtesting via `HistoricalReplayAppService`. Real-time emission from `BarAppService._save_completed_bar()` for live strategies is pending (Phase 5: real-time event wiring).

---

## Handler Registration

All 37 handlers registered via `@handles` decorator:

```python
@handles(SyncSymbolCommand)
class SyncSymbolHandler(Handler[SyncSymbolCommand, SyncResponse]):
    async def handle(self, cmd: SyncSymbolCommand) -> SyncResponse:
        ...
```

Registry auto-discovered in `src/container.py`:
```python
register_all_handlers(container)  # Wires all @handles decorators to Mediator
```

---

## Performance Notes

| Handler | Latency | Notes |
|---------|---------|-------|
| **SyncSymbolHandler** | 1-5s | ThreadPoolExecutor (4 workers) for blocking I/O |
| **GetBarsHandler** | <5ms | Redis cache hit, <100ms miss |
| **GetLatestQuoteHandler** | <5ms | Redis in-memory |
| **RunBacktestHandler** | 10s-2min | Depends on bar count, strategy complexity |
| **StrategyAppService.on_bar()** | <1ms | In-memory strategy execution |
| **RiskCheckHandler** | <0.1ms | Memory checks only |
