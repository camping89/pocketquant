# Handler Pipelines & Detailed Flows

37 registered CQRS handlers (16 market data + 4 trading + 12 strategy + 5 backtest) + ~45 HTTP endpoints (includes SSE + app-service-direct routes). Pattern: DDD + CQRS + Extract-Method. DI: Dishka. Data provider: Binance (`BinanceClient` implements `IDataProvider`, 1200 weight/min rate limit, max 1000 bars/call).

Naming: `strategy_id` (template code) vs `subscription_id` (per-subscription instance). Symbol is composite `CODE:EXCHANGE` (URL-encoded `%3A`). Verify against OpenAPI or [README](../README.md) if a path disagrees with the live app.

This document details the complete pipeline for each CQRS handler, showing request flow, processing steps, and side effects.

**Handler & Endpoint Distribution:**
- **37 registered CQRS handlers:** Discovered by Dishka via `@handles` decorator (count verified by `@handles` decorator usages across packages)
- **~45 HTTP endpoints total:** CQRS handlers (37) + SSE/app-service-direct routes (8)
- **37 registered handlers grouped by:**
  - **Market Data (16):** sync, bulk-sync, ohlcv, subscribe, unsubscribe, get-latest-quote, get-all-quotes, list-symbols, sync-status, symbol-sync-status, quotes-status, quote-service-status, tracked-symbols (list, add, update, remove)
  - **Backtesting (5):** run, optimize, get-backtest, get-optimization, list-backtests
  - **Strategy (12):** start, stop, get-one, get-all, add-symbol, list-symbols, remove-symbol, run-all-backtests, get-subscription-backtest, get-positions, get-trades, delete-cascade
  - **Trading (4):** list-orders, get-order, list-positions, get-position

**Distinction (NOT counted in the 37):** SSE streams (bars-stream, quotes-stream), integrity check/repair, and the tracked-symbol backfill route use app-service-direct calls or iterate over in-memory data — they are NOT mediator-routed CQRS handlers. `BackfillTrackedSymbolHandler` has no `@handles` decorator; its route calls it directly via DI.

## A. Market Data Handlers & Endpoints (16 CQRS + SSE/Direct)

### 1. SyncSymbolHandler (SyncSymbolCommand)

**Request:** POST `/api/v1/market-data/sync`

**Command Fields:**
- `symbol: str` - Trading symbol (e.g., BTCUSDT)
- `exchange: str` - Exchange name (e.g., BINANCE)
- `interval: Interval` - Time interval (default: DAY_1)
- `n_bars: int` - Number of bars to fetch (default: 1000; auto-paginates above)
- `skip_filter: bool` - Bypass `_filter_new_bars` — used by repair to fill gaps (default: False)

**Implementation (Extract-Method Pattern — illustrative):** The real handler in `handlers/sync/sync_one/` keeps `handle()` as a readable checklist and pushes detail into private helpers plus sibling modules (`bar_filters.filter_new_bars`/`drop_misaligned_bars`, `provider_fetch.fetch_with_retry`, `responses.build_success`, `anomaly_log.emit_no_progress`). The snippet below shows the shape, not the exact line-by-line code.

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
        Rate limits: Binance 1200 weight/min, max 1000 bars/call (auto-paginated)."""
        return await self.provider.fetch_ohlcv(
            cmd.symbol, cmd.interval, cmd.n_bars
        )

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

### Quote Feed Lifecycle (no CQRS handler)

The Binance `@aggTrade` WS feed has **no start/stop handler**. It is auto-started and torn down by the FastAPI lifespan (`start_quote_feed` / `stop_quote_feed` in `api/main_extensions.py`). `WsSubscriptionManager` reconciles live subscriptions against the `tracked_symbols` collection every 5s. See [WebSocket Architecture](./websocket-architecture.md).

---

### 4. SubscribeHandler (SubscribeCommand)

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

### 5. UnsubscribeHandler (UnsubscribeCommand)

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

### 6. GetLatestQuoteHandler (GetLatestQuoteQuery)

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

### 7. GetAllQuotesHandler (GetAllQuotesQuery)

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

### 8. ListSymbolsHandler (ListSymbolsQuery)

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

### 9. GetSyncStatusHandler (GetSyncStatusQuery)

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

### 10. GetSymbolSyncStatusHandler (GetSymbolSyncStatusQuery)

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

### 11. Quote-status handlers — GetQuotesStatusHandler + GetQuoteServiceStatusHandler

Two distinct CQRS handlers, two routes, both simple status reads:

**11a. GetQuotesStatusHandler (GetQuotesStatusQuery)** — GET `/api/v1/quotes/status`
```
GetQuotesStatusQuery()
  ↓
Check QuoteAppService.is_running + count subscriptions
  ↓
Response: QuotesStatusResponse(is_running, subscription_count)
```

**11b. GetQuoteServiceStatusHandler (GetQuoteServiceStatusQuery)** — GET `/api/v1/market-data/status`
```
GetQuoteServiceStatusQuery()
  ↓
svc = QuoteAppService
  ↓
Response: QuoteServiceStatus(
    running=svc.running and svc.provider.is_connected(),
    subscription_count=svc.provider.subscription_count,
    active_symbols=svc.bar_manager.active_symbols,
)
```

---

### 12. StreamBarsHandler (SSE endpoint — app-service direct)

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

### 13. StreamQuoteHandler (SSE endpoint — app-service direct)

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

### 14. check_integrity (app-service direct — `integrity_jobs.py`)

**Request:** POST `/api/v1/market-data/integrity/check`

**Request body:** `{symbol (composite), interval, days_back (1–90, default 7)}`

**Implementation:**
1. Build the alignment grid for the window: `end = get_bar_start(now, interval)` (last CLOSED bar), `start = end - days_back`.
2. Fetch stored datetimes: `bar_repo.find_datetimes(symbol, interval, start, end)`.
3. Partition: bars where `is_bar_aligned()` false → `misaligned`; aligned datetimes → set.
4. Compute `missing = expected_grid - aligned_times`; group consecutive misses into `gap_ranges`.
5. Return: `{symbol, interval, total, misaligned_count, misaligned_ids, missing_count, gap_ranges}`.

> Checks **alignment + gaps only** — NOT OHLC ordering or negative volumes. Reliable only for 24/7 markets (crypto); equity symbols produce false-positive gaps on weekends/holidays.

**Side Effects:** None (read-only diagnostic).

---

### 15. repair_integrity (app-service direct — `integrity_jobs.py`)

**Request:** POST `/api/v1/market-data/integrity/repair`

**Request body:** `{symbol (composite), interval, days_back (1–90, default 7)}`

**Implementation:**
1. Run `check_integrity()` to get the report.
2. Delete misaligned: `bar_repo.delete_many_by_ids(report["misaligned_ids"])`.
3. If `gap_ranges` non-empty: send one `SyncSymbolCommand(symbol, interval, n_bars=5000, skip_filter=True, source=...)` via mediator to backfill; on exception, log `integrity.resync_failed` and continue.
4. Re-check (`check_integrity()` again) to capture `still_missing` + `still_missing_ranges`; warn `integrity.repair.still_missing` if gaps remain.
5. Return: `{symbol, interval, deleted, gaps_resynced, missing_before, still_missing, still_missing_ranges}`.

**Side Effects:** MongoDB bars collection modified (misaligned deleted, gaps re-upserted via sync pipeline).

> Also runs unattended: background job `sync_repair` (~every 12h) iterates tracked symbols × intervals calling `repair_integrity`. See `code-standards.md` §9.5 for the canonical 5-step description.

---

### 16. ListTrackedSymbolsHandler (ListTrackedSymbolsQuery — CQRS)

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

### 17. AddTrackedSymbolHandler (AddTrackedSymbolCommand — CQRS, admin-protected)

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

### 18. UpdateTrackedSymbolHandler (UpdateTrackedSymbolCommand — CQRS, admin-protected)

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

### 19. RemoveTrackedSymbolHandler (RemoveTrackedSymbolCommand — CQRS, admin-protected)

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

### 20. BackfillTrackedSymbolHandler (BackfillTrackedSymbolCommand — CQRS, admin-protected)

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

### 21. RunBacktestHandler (RunBacktestCommand)

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

### 22. RunOptimizationHandler (RunOptimizationCommand)

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

### 23. GetBacktestHandler (GetBacktestQuery)

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

### 24. GetOptimizationHandler (GetOptimizationQuery)

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

### 25. ListBacktestsHandler (ListBacktestsQuery)

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

### 26. StartStrategyHandler (StartStrategyCommand)

**Request:** POST `/api/v1/subscriptions/{sub_id}/start`

**Declarative design:** Writes `desired_state=running` to Mongo; returns immediately before engine starts. The reconcile loop converges within ≤1 poll interval (default 5s).

**Pipeline:**
```
StartStrategyCommand(subscription_id)
  ↓
Handler.handle():
  1. Update Mongo: SubscriptionRepository.update_desired_state(sub_id, "running")
     └─ Control-plane write only; no engine call
  ↓
  2. Validate: modified_count > 0 → subscription exists; else raise NotFoundError (404)
  ↓
Response: HTTP 200 (success) or 404 (not found)

[Meanwhile, background reconcile loop will:
  - Read subscription.desired_state="running" (within 5s)
  - Compare to live StrategyAppService instance
  - If drift: call start_strategy(sub_id) to converge
  - Write actual_state="running" back to Mongo]
```

---

### 27. StopStrategyHandler (StopStrategyCommand)

**Request:** POST `/api/v1/subscriptions/{sub_id}/stop`

**Declarative design:** Writes `desired_state=stopped` to Mongo; returns immediately. Reconcile loop converges within ≤1 interval.

**Pipeline:**
```
StopStrategyCommand(subscription_id)
  ↓
Handler.handle():
  1. Update Mongo: SubscriptionRepository.update_desired_state(sub_id, "stopped")
     └─ Control-plane write only; no engine call
  ↓
  2. Validate: modified_count > 0 → subscription exists; else raise NotFoundError (404)
  ↓
Response: HTTP 200 (success) or 404 (not found)

[Meanwhile, background reconcile loop will:
  - Read subscription.desired_state="stopped" (within 5s)
  - Compare to live StrategyAppService instance
  - If drift: call stop_strategy(sub_id) to converge
  - Write actual_state="stopped" back to Mongo]
```

**Async-eventual semantics:** The API returns success before the engine actually stops. Clients poll `GET /subscriptions/{sub_id}` to observe `actual_state` transition.

---

### 28. GetStrategyHandler (GetStrategyQuery) — template metadata

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

### 29. GetStrategiesHandler (GetStrategiesQuery) — list templates

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

### 30. AddSymbolHandler (AddSymbolCommand) — create subscription

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
  4. Auto-load instance (stopped): if StrategyAppService.get_strategy(sub_id) is None
     └─ StrategyAppService.load_strategy(StrategyConfig(id=sub_id, name=strategy_code, ...))
        Load strategy instance but do NOT start it (desired_state=stopped)
  ↓
  5. Persist: SubscriptionRepository.add(
       Subscription(
         id=sub_id, 
         strategy_code, 
         symbol, 
         interval,
         desired_state="stopped",    # opt-in: user must POST /start
         actual_state="stopped"
       )
     )
     └─ DuplicateKeyError → SubscriptionAlreadyExistsError (400 DomainError)
  ↓
Response: {id, strategy_code, symbol, interval, created_at, desired_state, actual_state}
```

**Side Effects:**
- MongoDB: document inserted into `subscriptions` collection with `desired_state="stopped"`
- In-process: new IStrategy instance loaded (pre-loaded but not running) into `StrategyAppService._strategies[sub_id]`
- FE must POST `/start` explicitly for live trading; no auto-start on add

---

### 31. ListSymbolsHandler (ListSymbolsQuery) — list subscriptions

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
Compute is_running per sub: Sub.actual_state == "running" (from Mongo, NOT RAM)
  └─ Sources control-plane truth (actual_state written by reconcile loop)
  ↓
Response: list[{
  id, 
  strategy_code, 
  symbol, 
  interval, 
  created_at,
  desired_state,       # what user/API wants
  actual_state,        # what reconcile loop observed on last tick
  is_running,          # derived: actual_state == "running"
  backtest             # cached backtest result (if exists)
}]
```

**No RAM read:** The handler reads subscriptions from Mongo; `is_running` is computed from `actual_state` (written by reconcile loop), not from live RAM. This decouples the API from the in-memory engine state.

---

### 32. RemoveSymbolHandler (RemoveSymbolCommand) — delete one subscription

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

### 33. RunAllBacktestsHandler (RunAllBacktestsCommand) — fan-out backtests

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

### 34. GetSubscriptionBacktestHandler (GetSubscriptionBacktestQuery)

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

### 35. DeleteStrategyHandler (DeleteStrategyCommand) — cascade by template

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

### 36. GetStrategyPositionsHandler (GetStrategyPositionsQuery)

**Request:** GET `/api/v1/subscriptions/{sub_id}/positions`

**Pipeline:**
```
GetStrategyPositionsQuery(subscription_id)
  ↓
Fetch: PositionRepository.find_open_by_subscription(sub_id)
  ↓
Map each open position → FE dict (symbol, direction, entry_price, quantity,
  unrealized_pnl, entry_time, sl_price, tp_price)
  ↓
Response: list[dict] (0 or more)
```

**Side Effects:** None (read-only).

---

### 37. GetStrategyTradesHandler (GetStrategyTradesQuery)

**Request:** GET `/api/v1/subscriptions/{sub_id}/trades?limit=100` (limit 1–500)

**Pipeline:**
```
GetStrategyTradesQuery(subscription_id, limit)
  ↓
Fetch: PositionRepository.find_closed_by_subscription(sub_id, limit)
  ↓
Map each closed position → StrategyTrade dict (id, direction, entry_price,
  exit_price=current_price, entry_time, exit_time, pnl=realized_pnl, quantity)
  ↓
Response: list[dict]
```

**Side Effects:** None (read-only).

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

Registry auto-discovered at container build time in `packages/pocketquant-app/src/pocketquant/app/di/container.py`:
```python
await register_handlers(container)  # Resolves all @handles classes and wires them to the Mediator
```

---

## Performance Notes

| Handler | Latency | Notes |
|---------|---------|-------|
| **SyncSymbolHandler** | 1-5s | ThreadPoolExecutor (4 workers) for blocking I/O |
| **GetOHLCVHandler** | <5ms | Redis cache hit, <100ms miss |
| **GetLatestQuoteHandler** | <5ms | Redis in-memory |
| **RunBacktestHandler** | 10s-2min | Depends on bar count, strategy complexity |
| **StrategyAppService.on_bar()** | <1ms | In-memory strategy execution |
| **RiskCheckHandler** | <0.1ms | Memory checks only |
