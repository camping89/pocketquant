# Handler Pipelines & Detailed Flows

**Last Updated:** 2026-02-22 | **Total Handlers:** 27 CQRS handlers | **Pattern:** Clean Architecture + CQRS

This document details the complete pipeline for each of the 27 CQRS handlers in PocketQuant, showing request flow, processing steps, and side effects.

## Handler Categories

- **Market Data (13):** Sync, OHLCV retrieval, quotes, symbols, status
- **Strategy (5):** Load, start, stop, get one, get all
- **Backtesting (5):** Run, optimize, get results
- **Trading (4):** List/get orders, list/get positions

## A. Market Data Handlers (13)

### 1. SyncSymbolHandler (SyncSymbolCommand)

**Request:** POST `/api/v1/market-data/sync`

**Pipeline:**
```
Route receives SyncSymbolCommand(symbol, exchange, interval, n_bars)
  ↓
Mediator dispatches to SyncSymbolHandler
  ↓
Handler.handle(command):
  1. Fetch: TradingViewProvider.fetch_ohlcv(symbol, exchange, interval, n_bars)
     └─ ThreadPoolExecutor (max 4 workers) → tvdatafeed.get_hist() sync call
  ↓
  2. Validate: OHLCVAggregate validates bar structure (immutable frozen dataclass)
  ↓
  3. Persist: OHLCVRepository.upsert_many(bars)
     └─ MongoDB bulk_write (upsert on timestamp unique key)
  ↓
  4. Cache invalidate: Cache.delete_pattern(f"OHLCV:{symbol}:*")
     └─ Redis SCAN + DEL pattern-based deletion
  ↓
  5. Publish: EventBus.publish(HistoricalDataSyncedEvent)
     └─ Subscribed handlers notified sequentially
  ↓
Response: SyncResponse(bars_synced=N, status='completed')
```

**Side Effects:**
- MongoDB: ohlcv collection updated
- Redis: cache invalidated
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
BulkSyncCommand(symbols: List[SymbolInfo], interval, n_bars)
  ↓
For each symbol:
  └─ Delegate to SyncSymbolHandler (parallel or sequential per config)
  ↓
Collect results: BulkSyncResponse(results: List[SyncResult])
```

---

### 3. GetOHLCVHandler (GetOHLCVQuery)

**Request:** GET `/api/v1/market-data/ohlcv/{exchange}/{symbol}?interval=1d&limit=100`

**Pipeline:**
```
GetOHLCVQuery(symbol, exchange, interval, limit)
  ↓
Check cache: Cache.get(f"OHLCV:{symbol}:{exchange}:{interval}:{limit}")
  ├─ Cache HIT: Return BarsDTO immediately
  └─ Cache MISS:
      ↓
      Fetch: OHLCVRepository.get_bars(symbol, exchange, interval, limit)
      └─ MongoDB query → sorted by timestamp (desc)
      ↓
      Validate: OHLCVBar value objects immutable
      ↓
      Cache: Cache.set(key, result, ttl=300)
      └─ Redis TTL 5 minutes
      ↓
Response: BarsDTO (never return domain entities)
```

**Cache Management:** Query results cached with 300s TTL

---

### 4. StartQuoteFeedHandler (StartQuoteFeedCommand)

**Request:** POST `/api/v1/market-data/quotes/start`

**Pipeline:**
```
StartQuoteFeedCommand()
  ↓
Handler.handle():
  1. Connect: TradingViewWebSocketProvider.connect()
     └─ wss://data.tradingview.com/socket.io/websocket
  ↓
  2. Start async task: asyncio.create_task(provider.listen())
     └─ Background loop receives frames
  ↓
  3. Set flag: QuoteService.is_running = True
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
  2. Disconnect: TradingViewWebSocketProvider.disconnect()
  ↓
  3. Clear subscriptions: QuoteService._subscriptions.clear()
  ↓
  4. Set flag: QuoteService.is_running = False
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
Cache subscription: QuoteService._subscriptions[key] = True
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
Query all subscriptions: QuoteService._subscriptions.keys()
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
Check QuoteService.is_running
  ↓
Count subscriptions: len(QuoteService._subscriptions)
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
  2. Fetch bars: OHLCVRepository.get_bars(symbol, start_date, end_date)
     └─ MongoDB, sorted ascending by timestamp
  ↓
  3. Run backtest: BacktestRunner.run(strategy, bars, PaperBroker)
     ├─ Initialize PaperBroker with 100k starting capital
     ├─ For each bar (chronological):
     │   ├─ StrategyEngine.on_bar(bar)
     │   ├─ Strategy.on_bar(bar) → Signal(BUY/SELL/HOLD, qty)
     │   ├─ RiskCheckHandler.check_signal() → approved?
     │   ├─ PaperBroker.submit_order() → instant fill with slippage
     │   ├─ PositionTracker.update() → P&L calculation
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
  1. GridOptimizer.optimize(param_grid)
     ├─ Generate parameter combinations: [(p1=1, p2=2), (p1=1, p2=3), ...]
     ├─ For each combo (parallel via multiprocessing):
     │   └─ Run BacktestRunner with params
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
  4. Store in StrategyEngine: StrategyEngine.load_strategy(strategy_id, strategy)
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
  1. Fetch: StrategyEngine.get_strategy(strategy_id)
  ↓
  2. Connect broker: IBroker.connect()
     └─ OKXBroker or PaperBroker
  ↓
  3. Initialize: await strategy.on_start()
     └─ Strategy can subscribe to quotes, set initial state
  ↓
  4. Set running: StrategyEngine.set_running(strategy_id, True)
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
  4. Set running: StrategyEngine.set_running(strategy_id, False)
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
Fetch: StrategyEngine.get_strategy(strategy_id)
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
Fetch: StrategyEngine.list_all()
  └─ In-memory loaded strategies
  ↓
Serialize: List[StrategyDTO](id, name, status)
  ↓
Response: StrategiesDTO
```

---

## D. Trading Handlers (4)

### 24-27. Order & Position Handlers

Simple in-memory reads from `OrderManager` and `PositionTracker`.

**Pipelines:**
```
24. ListOrdersHandler:    OrderManager.list_all() → List[OrderDTO]
25. GetOrderHandler:      OrderManager.get_by_id(order_id) → OrderDTO
26. ListPositionsHandler: PositionTracker.list_all() → List[PositionDTO]
27. GetPositionHandler:   PositionTracker.get_by_id(position_id) → PositionDTO
```

---

## Key Data Flows

### Real-time Quote → Strategy Execution

```
WebSocket tick from TradingView
  ↓
TradingViewWebSocketProvider.parse_frame()
  ↓
QuoteService._on_quote_update(quote)
  ├─ Cache.set(f"QUOTE_LATEST:{exchange}:{symbol}", quote, ttl=5)
  └─ BarManager.add_tick(quote)
      ├─ For each interval (1m, 5m, ..., 1M):
      │   └─ Update BarBuilder[interval]
      ├─ Detect bar boundary crossed
      └─ Publish BarCompletedEvent
  ↓
EventBus.publish(BarCompletedEvent)
  ↓
StrategyEngine._on_bar(bar)
  ├─ strategy.on_bar(bar) → Signal
  ├─ RiskCheckHandler.check_signal(signal) → approved?
  ├─ OrderManager.submit_order(order, broker)
  │   └─ OKXBroker.submit_order() or PaperBroker.submit_order()
  └─ Publish OrderSubmittedEvent
  ↓
Broker processes order → fill/reject
  ↓
OrderFilledEvent published
  ↓
PositionTracker._on_order_filled()
  ├─ Update position: entry/exit/quantity
  ├─ Calculate P&L
  ├─ Publish PositionOpenedEvent / PositionUpdatedEvent
  └─ PositionRepository.save(position)
```

### Backtesting: Historical Replay

```
BacktestRunner receives bars (sorted chronologically)
  ↓
For each bar:
  1. Inject to StrategyEngine
  2. strategy.on_bar(bar) → Signal
  3. RiskCheckHandler validates
  4. PaperBroker fills instantly (with slippage)
  5. PositionTracker updates
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
| **GetOHLCVHandler** | <5ms | Redis cache hit, <100ms miss |
| **GetLatestQuoteHandler** | <5ms | Redis in-memory |
| **RunBacktestHandler** | 10s-2min | Depends on bar count, strategy complexity |
| **StrategyEngine.on_bar()** | <1ms | In-memory strategy execution |
| **RiskCheckHandler** | <0.1ms | Memory checks only |

