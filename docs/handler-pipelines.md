# Handler Pipelines & Detailed Flows

**Last Updated:** 2026-03-23 | **Total Handlers:** 27 CQRS handlers across 4 domains | **Pattern:** DDD + CQRS + Extract-Method | **DI:** Dishka

This document details the complete pipeline for each of the 27 CQRS handlers in PocketQuant, showing request flow, processing steps, and side effects.

## Handler Categories

- **Market Data (13):** Sync, Bar retrieval, quotes, symbols, status
- **Strategy (5):** Load, start, stop, get one, get all
- **Backtesting (5):** Run, optimize, get results
- **Trading (4):** List/get orders, list/get positions

## A. Market Data Handlers (13)

### 1. SyncSymbolHandler (SyncSymbolCommand)

**Request:** POST `/api/v1/market-data/sync`

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

        self._validate_bars(bars)
        count = await self._persist_bars(bars, cmd.symbol)
        await self._invalidate_cache(cmd.symbol)
        await self._publish_sync_event(cmd, count)
        return await self._success(count)

    async def _fetch_bars(self, cmd: SyncSymbolCommand) -> List[Bar]:
        """Fetch via TradingView (thread pool)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self.provider.fetch_ohlcv,
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

### 3. GetBarsHandler (GetBarsQuery)

**Request:** GET `/api/v1/market-data/bar/{exchange}/{symbol}?interval=1d&limit=100`

**Pipeline:**
```
GetBarsQuery(symbol, exchange, interval, limit)
  ↓
Check cache: Cache.get(f"bar:{symbol}:{exchange}:{interval}:{limit}")
  ├─ Cache HIT: Return BarsDTO immediately
  └─ Cache MISS:
      ↓
      Fetch: BarRepository.get_bars(symbol, exchange, interval, limit)
      └─ MongoDB bars collection, sorted by timestamp (desc)
      ↓
      Validate: Bar value objects immutable, to_mongo()/from_mongo()
      ↓
      Cache: Cache.set(key, result, ttl=300)
      └─ Redis TTL 5 minutes, key: build_bar_cache_key()
      ↓
Response: BarsDTO (never return domain entities)
```

**Cache Management:** Query results cached with 300s TTL using `build_bar_cache_key()`

---

### 4. StartQuoteFeedHandler (StartQuoteFeedCommand)

**Request:** POST `/api/v1/market-data/quotes/start`

**Pipeline:**
```
StartQuoteFeedCommand()
  ↓
Handler.handle():
  1. Connect: TradingViewWebSocketClient.connect()
     └─ wss://data.tradingview.com/socket.io/websocket
  ↓
  2. Start async task: asyncio.create_task(provider.listen())
     └─ Background loop receives frames
  ↓
  3. Set flag: QuoteAppService.is_running = True
  ↓
Response: QuoteServiceStatus(status='connected')
```

**Background Task:** Continuously receives WebSocket frames, parses JSON, distributes to subscribers.

---

### 5. StopQuoteFeedHandler (StopQuoteFeedCommand)

**Request:** POST `/api/v1/market-data/quotes/stop`

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

**Request:** POST `/api/v1/market-data/quotes/subscribe`

**Pipeline:**
```
SubscribeCommand(symbol, exchange)
  ↓
Validate feed running (if not, return error)
  ↓
Provider.subscribe(symbol, exchange, callback=on_quote_update)
  └─ Registers callback for this symbol
  ↓
Cache subscription: QuoteAppService._subscriptions[key] = True
  ↓
Response: SubscriptionStatus(symbol, exchange, subscribed=True)
```

---

### 7. UnsubscribeHandler (UnsubscribeCommand)

**Request:** POST `/api/v1/market-data/quotes/unsubscribe`

**Pipeline:**
```
UnsubscribeCommand(symbol, exchange)
  ↓
Provider.unsubscribe(symbol, exchange)
  ↓
Delete cache: Cache.delete(f"QUOTE_LATEST:{exchange}:{symbol}")
  ↓
Response: SubscriptionStatus(subscribed=False)
```

---

### 8. GetLatestQuoteHandler (GetLatestQuoteQuery)

**Request:** GET `/api/v1/market-data/quotes/latest/{exchange}/{symbol}`

**Pipeline:**
```
GetLatestQuoteQuery(exchange, symbol)
  ↓
Fetch: Cache.get(f"QUOTE_LATEST:{exchange}:{symbol}")
  └─ Redis (TTL 5s, updated on each tick)
  ↓
Deserialize: QuoteTick(price, volume, timestamp)
  ↓
Response: QuoteDTO
```

---

### 9. GetAllQuotesHandler (GetAllQuotesQuery)

**Request:** GET `/api/v1/market-data/quotes`

**Pipeline:**
```
GetAllQuotesQuery()
  ↓
Query all subscriptions: QuoteAppService._subscriptions.keys()
  ↓
For each subscription:
  └─ Cache.get(f"QUOTE_LATEST:{exchange}:{symbol}")
  ↓
Serialize list: List[QuoteDTO]
  ↓
Response: AllQuotesDTO
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

**Request:** GET `/api/v1/market-data/sync-status/{symbol}/{exchange}`

**Pipeline:**
```
GetSymbolSyncStatusQuery(symbol, exchange)
  ↓
Fetch: SyncStatusRepository.find_by_symbol(symbol, exchange)
  ↓
Response: SyncStatusDTO
```

---

### 13. GetQuoteServiceStatusHandler (GetQuoteServiceStatusQuery)

**Request:** GET `/api/v1/market-data/quotes/status`

**Pipeline:**
```
GetQuoteServiceStatusQuery()
  ↓
Check QuoteAppService.is_running
  ↓
Count subscriptions: len(QuoteAppService._subscriptions)
  ↓
Response: QuoteServiceStatusDTO(is_running, subscription_count)
```

---

## B. Backtesting Handlers (5)

### 14. RunBacktestHandler (RunBacktestCommand)

**Request:** POST `/api/v1/backtest/run`

**Pipeline:**
```
RunBacktestCommand(strategy_name, symbol, start_date, end_date, params)
  ↓
Handler.handle():
  1. Fetch strategy: StrategyLoader.load_yaml(config_path)
     └─ YAML → IStrategy instance
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

### 15. RunOptimizationHandler (RunOptimizationCommand)

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

### 16. GetBacktestHandler (GetBacktestQuery)

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

### 17. GetOptimizationHandler (GetOptimizationQuery)

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

### 18. ListBacktestsHandler (ListBacktestsQuery)

**Request:** GET `/api/v1/backtest/strategy/{strategy_id}`

**Pipeline:**
```
ListBacktestsQuery(strategy_id)
  ↓
Query: BacktestRepository.list_by_strategy(strategy_id)
  └─ MongoDB query with pagination
  ↓
Response: List[BacktestResultDTO]
```

---

## C. Strategy Handlers (5)

### 19. LoadStrategyHandler (LoadStrategyCommand)

**Request:** POST `/api/v1/strategies/load`

**Pipeline:**
```
LoadStrategyCommand(name, config_path)
  ↓
Handler.handle():
  1. Load YAML: StrategyLoader.load_yaml(config_path)
     └─ Parse YAML → StrategyConfig dataclass
  ↓
  2. Instantiate: StrategyFactory.create(config.strategy_class, **config.params)
     └─ Dynamic import + instantiate IStrategy subclass
  ↓
  3. Register handlers: EventRegistry.register_instance(strategy)
     └─ Scan for @event_handler decorated methods
     └─ Subscribe strategy.on_order_filled, etc. to EventBus
  ↓
  4. Store in StrategyAppService: StrategyAppService.load_strategy(strategy_id, strategy)
  ↓
Response: LoadStrategyResponse(strategy_id, name, status='loaded')
```

---

### 20. StartStrategyHandler (StartStrategyCommand)

**Request:** POST `/api/v1/strategies/{id}/start`

**Pipeline:**
```
StartStrategyCommand(strategy_id)
  ↓
Handler.handle():
  1. Fetch: StrategyAppService.get_strategy(strategy_id)
  ↓
  2. Connect broker: IBroker.connect()
     └─ OKXBroker or PaperBroker
  ↓
  3. Initialize: await strategy.on_start()
     └─ Strategy can subscribe to quotes, set initial state
  ↓
  4. Set running: StrategyAppService.set_running(strategy_id, True)
  ↓
  5. Start listening: Subscribe to BarCompletedEvent, QuoteReceivedEvent
  ↓
Response: StrategyStatusDTO(status='running')
```

---

### 21. StopStrategyHandler (StopStrategyCommand)

**Request:** POST `/api/v1/strategies/{id}/stop`

**Pipeline:**
```
StopStrategyCommand(strategy_id)
  ↓
Handler.handle():
  1. Call: await strategy.on_stop()
     └─ Strategy cleanup
  ↓
  2. Disconnect broker: IBroker.disconnect()
  ↓
  3. Unsubscribe: Remove BarCompletedEvent subscriber
  ↓
  4. Set running: StrategyAppService.set_running(strategy_id, False)
  ↓
Response: StrategyStatusDTO(status='stopped')
```

---

### 22. GetOneStrategyHandler (GetOneStrategyQuery)

**Request:** GET `/api/v1/strategies/{id}`

**Pipeline:**
```
GetOneStrategyQuery(strategy_id)
  ↓
Fetch: StrategyAppService.get_strategy(strategy_id)
  └─ In-memory lookup by ID
  ↓
Response: StrategyDTO(id, name, status, config)
```

---

### 23. GetAllStrategiesHandler (GetAllStrategiesQuery)

**Request:** GET `/api/v1/strategies`

**Pipeline:**
```
GetAllStrategiesQuery()
  ↓
Fetch: StrategyAppService.list_all()
  └─ In-memory loaded strategies
  ↓
Serialize: List[StrategyDTO](id, name, status)
  ↓
Response: StrategiesDTO
```

---

## D. Trading Handlers (4)

### 24-27. Order & Position Handlers

Simple in-memory reads from `OrderAppService` and `PositionAppService`.

**Pipelines:**
```
24. ListOrdersHandler:    OrderAppService.list_all() → List[OrderDTO]
25. GetOrderHandler:      OrderAppService.get_by_id(order_id) → OrderDTO
26. ListPositionsHandler: PositionAppService.list_all() → List[PositionDTO]
27. GetPositionHandler:   PositionAppService.get_by_id(position_id) → PositionDTO
```

---

## Key Data Flows

### Real-time Quote → Strategy Execution (Real-Time Wiring Status: In Progress)

```
WebSocket tick from TradingView
  ↓
TradingViewWebSocketClient.parse_frame()
  ↓
QuoteAppService._on_quote_update(quote)
  ├─ Cache.set(f"quote:latest:{exchange}:{symbol}", quote, ttl=60)
  └─ BarAppService.process_tick(quote)
      ├─ For each interval (1m, 5m, ..., 1M):
      │   └─ Update BarBuilder[interval]
      ├─ Detect bar boundary crossed
      └─ BarAppService._save_completed_bar()
         ├─ MongoDB insert_one(bar) to bars collection [COLLECTION RENAMED: ohlcv→bars]
         ├─ Redis cache with build_bar_cache_key()
         └─ Publish BarCompletedEvent [SOURCE: _save_completed_bar(), real-time emission status: PENDING]
  ↓
EventBus.publish(BarCompletedEvent) [Real-time wiring: TODO]
  ↓
StrategyAppService._on_bar(bar)
  ├─ strategy.on_bar(bar) → Signal
  ├─ RiskCheckHandler.check_signal(signal) → approved?
  ├─ OrderAppService.submit_order(order, broker)
  │   └─ OKXBroker.submit_order() or PaperBroker.submit_order()
  └─ Publish OrderSubmittedEvent
  ↓
Broker processes order → fill/reject
  ↓
OrderFilledEvent published
  ↓
PositionAppService._on_order_filled()
  ├─ Update position: entry/exit/quantity
  ├─ Calculate P&L
  ├─ Publish PositionOpenedEvent / PositionUpdatedEvent
  └─ PositionRepository.save(position)
```

**Note:** Real-time BarCompletedEvent emission is wired in backtesting via HistoricalReplayAppService. Live event wiring for real-time strategies is scheduled for Phase 5 (real-time event wiring).

### Backtesting: Historical Replay

```
BacktestAppService receives bars (sorted chronologically)
  ↓
For each bar:
  1. Inject to StrategyAppService
  2. strategy.on_bar(bar) → Signal
  3. RiskCheckHandler validates
  4. PaperBroker fills instantly (with slippage)
  5. PositionAppService updates
  6. Collect fill event
  ↓
After all bars:
  PerformanceCalculator aggregates fills
    ├─ Calculate Sharpe, Sortino, max drawdown
    └─ Finalize P&L
  ↓
BacktestResult saved to MongoDB
```

---

## Handler Registration

All 27 handlers registered via `@handles` decorator:

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

