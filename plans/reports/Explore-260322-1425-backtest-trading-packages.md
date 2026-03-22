# PocketQuant Packages Exploration Report

**Date:** 2026-03-22 | **Scope:** pocketquant-backtest & pocketquant-trading

---

## 1. POCKETQUANT-BACKTEST (40 Python files)

### Directory Structure
```
src/pocketquant/backtest/
├── domain/                     # DDD domain entities & value objects
│   ├── entities.py             # BacktestResult, OptimizationResult
│   ├── value_objects.py        # TradeRecord, EquityPoint, BacktestMetrics, OptimizationResultEntry
│   └── services/
│       └── performance_calculator.py  # Sharpe, Sortino, max_drawdown, CAGR
├── engine/                     # Core backtest execution
│   ├── backtest_app_service.py         # Single backtest orchestrator
│   ├── historical_replay_app_service.py # Time replay engine
│   └── result_collector.py             # Equity curve & trade tracking
├── optimization/               # Grid parameter optimization
│   ├── grid_optimization_app_service.py # Parallel parameter sweep
│   └── models/
│       ├── backtest_config.py  # Single run configuration
│       └── optimization_config.py # Grid optimization config
├── handlers/                   # CQRS handlers (commands/queries)
│   ├── run/    (RunBacktestCommand/Handler)
│   ├── optimize/ (RunOptimizationCommand/Handler)
│   ├── get_result/ (GetBacktestResultQuery/Handler)
│   ├── get_optimization/ (GetOptimizationQuery/Handler)
│   ├── list_results/ (ListBacktestResultsQuery/Handler)
│   └── router.py               # FastAPI route aggregation
└── persistence/
    ├── backtest_repository.py  # MongoDB CRUD for runs
    └── optimization_repository.py # MongoDB CRUD for optimizations
```

### Key Classes & Entities

#### Domain (entities.py)
- **BacktestResult** (Main output aggregate)
  - `id, strategy_id, config_snapshot` (serialized config)
  - `metrics: BacktestMetrics` (Sharpe, Sortino, return, drawdown, trades)
  - `equity_curve: list[EquityPoint]` (timestamp, equity, drawdown)
  - `trades: list[TradeRecord]` (order_id, symbol, side, qty, price, pnl)
  - `started_at, completed_at, status` ("completed" or "failed")
  - `error_message: str | None` (failure audit trail)
  - `to_mongo() / from_mongo()` (persistence)

- **OptimizationResult** (Grid optimization output)
  - `config_snapshot, target_metric, parameter_grid`
  - `total_combinations, completed_combinations, failed_combinations`
  - `results: list[OptimizationResultEntry]` (ranked by metric)
  - `best_parameters, best_metrics`
  - Status: "running" | "completed" | "failed"

#### Value Objects (value_objects.py)
- **BacktestMetrics**: total_return, cagr, sharpe_ratio, sortino_ratio, max_drawdown, win_rate, profit_factor, total_trades, avg_win, avg_loss, avg_trade_duration, total_commission
- **EquityPoint**: timestamp, equity, drawdown (tracked only on trades)
- **TradeRecord**: order_id, symbol, side, qty, price, commission, pnl, timestamp
- **OptimizationResultEntry**: parameters dict, metrics, backtest_id, rank

#### Services (domain/services/)
- **PerformanceCalculator** (static methods)
  - `total_return(initial, final)` → % return
  - `cagr(initial, final, days)` → annualized growth
  - `sharpe_ratio(equity_curve)` → annualized (365 trading days)
  - `sortino_ratio(equity_curve)` → downside deviation only
  - `max_drawdown(equity_curve)` → peak-to-trough %
  - `drawdown_series(equity_curve)` → point-wise drawdown
  - `win_rate(), profit_factor(), average_win_loss()`
  - Edge cases: division by zero, empty data, NaN handling

#### Application Services (engine/)
- **BacktestAppService** (orchestrates single run)
  - Dependencies: EventBus, PaperBroker, BacktestRepository, BarRepository
  - Flow:
    1. Reset broker state
    2. Subscribe collector to broker fills
    3. Load bars from MongoDB (AsyncIterator[Bar])
    4. Wrap bars to set broker price before each bar
    5. Execute replay via HistoricalReplayAppService
    6. Finalize & calculate metrics via ResultCollector
    7. Persist result if enabled
    8. Clean up simulation time
  - Returns: BacktestResult (with metrics or error_message)

- **GridOptimizationAppService** (parallel parameter sweep)
  - Dependencies: EventBus, BacktestRepository, BarRepository
  - Flow:
    1. Generate parameter combinations (itertools)
    2. Create semaphore for max_workers concurrency
    3. Run backtest for each combo in parallel
    4. Rank results by target_metric (sharpe_ratio, return, etc.)
    5. Persist all individual BacktestResults
    6. Return OptimizationResult with best params

- **HistoricalReplayAppService** (time replay engine)
  - Replays bars to strategy (creates on_bar events)
  - Sets simulation time for each bar

#### ResultCollector (engine/result_collector.py)
- Registers as OrderResult callback on PaperBroker
- Tracks: equity_curve (only on trades), position (qty, cost), total_commission, peak equity
- Calculates:
  - Trade P&L (realized)
  - Running equity (realized + unrealized)
  - Drawdown from peak
  - Total/winning/losing trades
  - Win rate, profit factor, avg win/loss
- `finalize()` → BacktestResult with all metrics calculated

### CQRS Handler Patterns

**Commands:**
- `RunBacktestCommand(strategy_id, symbol, exchange, interval, start_date, end_date, initial_capital, slippage_bps, commission_bps, parameters)`
  - Handler creates fresh PaperBroker, config, calls BacktestAppService.run()
  
- `RunOptimizationCommand(strategy_id, symbol, exchange, interval, dates, parameter_grid, target_metric, max_workers)`
  - Handler creates GridOptimizationAppService, calls optimize()

**Queries:**
- `GetBacktestResultQuery(run_id)` → Handler queries BacktestRepository
- `ListBacktestResultsQuery(strategy_id, limit, include_failed)` → Handler lists from repo
- `GetOptimizationQuery(optimization_id)` → Handler queries OptimizationRepository

### Repositories (persistence/)

**BacktestRepository**
- Collection: `COLLECTION_BACKTEST_RUNS`
- Methods:
  - `save(result)` → upsert by _id
  - `get(run_id)` → BacktestResult | None
  - `list_by_strategy(strategy_id, limit, include_failed)` → sorted by started_at DESC
  - `get_best_by_metric(strategy_id, metric, limit)` → sorted by metrics.{metric} DESC
  - `delete(run_id)` → bool
  - `ensure_indexes()` → Creates 6 indexes on strategy_id, started_at, status, (strategy_id, started_at), (strategy_id, sharpe_ratio), (strategy_id, sortino_ratio), (strategy_id, win_rate)

**OptimizationRepository**
- Similar structure for optimization results

### Dependencies
- `pocketquant-core` (core domain, brokers, persistence)
- `numpy>=1.26.0` (vectorized calculations)
- `pandas>=2.1.0` (data structures)

### Configuration Objects

**BacktestConfig** (models/backtest_config.py)
- strategy_id, symbol, exchange, interval, start_date, end_date
- initial_capital, slippage_bps, commission_bps, replay_speed
- parameters: dict (strategy-specific)
- Methods: `with_parameters()`, `slippage_percent`, `commission_percent` properties

**OptimizationConfig** (models/optimization_config.py)
- Extends BacktestConfig
- parameter_grid: dict[str, list[Any]]
- target_metric: str (default "sharpe_ratio")
- max_workers: int (1-16, default 4)

---

## 2. POCKETQUANT-TRADING (65 Python files)

### Directory Structure
```
src/pocketquant/trading/
├── app_services/               # Core orchestration services
│   ├── strategy_app_service.py         # Strategy engine & event dispatch
│   ├── order_app_service.py            # Order lifecycle & broker submission
│   ├── position_app_service.py         # Position tracking & P&L
│   └── yaml_strategy_loader.py         # YAML config loading
├── brokers/okx/                # Live trading (OKX exchange)
│   ├── okx_broker.py           # Main OKX implementation (IBroker)
│   ├── okx_mapper.py           # API response → domain mapping
│   └── websocket/              # WebSocket real-time updates
│       ├── okx_websocket_client.py
│       ├── okx_message_parser.py
│       ├── okx_order_mapper.py
│       ├── okx_position_mapper.py
│       ├── okx_reconnection_handler.py
│       ├── okx_auth.py
│       └── __init__.py (exports)
├── handlers/                   # CQRS handlers
│   ├── strategy/
│   │   ├── load/ (LoadStrategyCommand/Handler)
│   │   ├── start/ (StartStrategyCommand/Handler)
│   │   ├── stop/ (StopStrategyCommand/Handler)
│   │   ├── get_one/ (GetStrategyQuery/Handler)
│   │   ├── get_all/ (ListStrategiesQuery/Handler)
│   │   └── router.py
│   ├── trading/                # Order & position queries
│   │   ├── get_order/
│   │   ├── list_orders/
│   │   ├── get_position/
│   │   ├── list_positions/
│   │   └── router.py
│   └── risk/
│       └── check_risk/ (RiskCheckHandler)
├── persistence/
│   ├── order_repository.py     # MongoDB order persistence
│   ├── position_repository.py  # MongoDB position tracking
│   └── (inherited from core)
├── webhooks/                   # External webhook handlers
│   ├── dispatcher.py
│   └── config.py
└── tests/conftest.py
```

### Key Classes & Services

#### StrategyAppService (app_services/strategy_app_service.py)
- **Responsibilities:**
  - Load strategies from StrategyConfig (or via StrategyLoader)
  - Manage broker per strategy (create/reuse)
  - Subscribe to BarCompletedEvent & QuoteReceivedEvent
  - Dispatch to strategy.on_bar() or strategy.on_tick()
  - Process signals through risk → position sizing → order submission
  
- **State:**
  - `_strategies: dict[strategy_id → IStrategy]`
  - `_brokers: dict[strategy_id → IBroker]`
  - `_configs: dict[strategy_id → StrategyConfig]`
  - `_running: bool`, `_lock: asyncio.Lock`

- **Public Methods:**
  - `async start()` → registers event handlers
  - `async stop()` → stops all strategies, disconnects brokers
  - `async load_strategy(config, strategy_class=None)` → str (strategy_id)
  - `async start_strategy(strategy_id)` → connects broker, calls strategy.on_start()
  - `async stop_strategy(strategy_id)` → calls strategy.on_stop()
  - `async unload_strategy(strategy_id)` → full cleanup
  - `get_strategies()` → list of dicts with status
  - `get_strategy(strategy_id)` → IStrategy | None

- **Event Handlers:**
  - `@event_handler(BarCompletedEvent)` → finds matching strategies, calls on_bar(), processes signal
  - `@event_handler(QuoteReceivedEvent)` → finds matching strategies, calls on_tick(), submits order
  
- **Signal Processing Pipeline:**
  1. Risk check (via RiskCheckHandler)
  2. Position size calculation (PositionSizer)
  3. Order creation (from signal + size)
  4. Order submission via OrderAppService
  5. Logs signal processing result

- **Default Strategy:** `_DefaultStrategy` returns no signal (pass-through)

#### OrderAppService (app_services/order_app_service.py)
- **Responsibilities:**
  - Submit orders to brokers
  - Track order status (pending → filled/cancelled)
  - Publish OrderFilledEvent
  - Handle broker callbacks (WebSocket updates)
  
- **State:**
  - `_orders: dict[order_id → OrderAggregate]` (completed)
  - `_pending: dict[order_id → OrderAggregate]` (open)
  - `_broker_map: dict[order_id → broker_order_id]`
  - `_lock: asyncio.Lock`

- **Key Methods:**
  - `async submit(order, broker)` → OrderResult
    - Saves order to repo
    - Calls broker.submit_order()
    - If FILLED immediately: publishes OrderFilledEvent
    - Otherwise: tracks as SUBMITTED
  
  - `async cancel(order_id, broker)` → bool
    - Calls broker.cancel_order()
    - Updates status, removes from pending
  
  - `async on_order_update(result)` → handles WebSocket callbacks
    - Updates order with fill info if FILLED
    - Publishes OrderFilledEvent
  
  - `async load_pending_orders()` → loads from DB on startup
  
  - Query methods: `get_order()`, `get_pending_orders()`, `get_filled_orders()`, `get_orders_by_strategy()`

#### PositionAppService (app_services/position_app_service.py)
- **Responsibilities:**
  - Track per-strategy positions (open/closed)
  - Update on OrderFilledEvent
  - Calculate unrealized P&L
  - Persist position state
  
- **State:**
  - `_positions: dict[strategy_id → PositionAggregate]`
  - `_lock: asyncio.Lock`

- **Key Methods:**
  - `async start()` → loads open positions, registers event handler
  - `async stop()` → cleanup
  
  - `@event_handler(OrderFilledEvent)` → updates/creates position
    - New position: creates PositionAggregate, persists, publishes PositionOpenedEvent
    - Same side: adds qty (averaging), persists
    - Opposite side: reduces qty, persists, closes if qty=0
  
  - Query: `get(strategy_id)`, `get_all()`, `get_position_summary()`, `get_all_summaries()`
  - `async update_price()` → updates current_price for P&L calculation

#### OKXBroker (brokers/okx/okx_broker.py)
- **Implements:** IBroker (from core)
- **Key Features:**
  - REST API via python-okx SDK (Trade, Account)
  - WebSocket for real-time order/position updates
  - Demo mode support (flag="1" vs "0")
  - Automatic reconnection handling
  
- **State:**
  - `_api_key, _api_secret, _passphrase` (credentials)
  - `_demo: bool`, `_inst_suffix: str` (e.g., "USDT")
  - `_trade_api, _account_api` (lazy init)
  - `_ws_client: OkxWebSocketClient | None`
  - `_order_callbacks: list[OrderCallback]`
  - `_connected: bool`
  - `_seen_terminal_orders: set[str]` (deduplication)

- **Key Methods:**
  - `async connect()` → initializes APIs, connects WebSocket
  - `async disconnect()` → closes WebSocket
  - `async submit_order(order)` → calls trade_api.place_order, maps response to OrderResult
  - `async cancel_order(broker_order_id)` → calls trade_api.cancel_order
  - `async get_balance()` → calls account_api, maps to AccountBalance
  - `async subscribe_order_updates(callback)` → WebSocket subscriptions
  - `async unsubscribe_order_updates()`
  - Properties: `name`, `is_connected`, `trade_api`, `seen_terminal_orders`

- **WebSocket Integration:**
  - OkxWebSocketClient handles subscribe/unsubscribe
  - OkxMessageParser parses updates
  - OkxOrderMapper converts to OrderResult
  - OkxPositionMapper converts to PositionAggregate
  - OkxReconnectionHandler manages reconnection logic

#### OkxMapper (brokers/okx/okx_mapper.py)
- `map_okx_order_state(state: str)` → OrderStatus (live→SUBMITTED, filled→FILLED, etc.)
- `map_order_side_to_okx(side: OrderSide)` → "buy" | "sell"
- `map_order_type_to_okx(type: OrderType)` → "market" | "limit" | "trigger"
- `map_order_to_okx_params(order, inst_suffix)` → dict for OKX API call
- `map_okx_position_to_domain(data, strategy_id)` → PositionAggregate | None
- `map_okx_balance_to_domain(data)` → AccountBalance

### CQRS Handler Patterns

**Strategy Commands:**
- `LoadStrategyCommand(config: StrategyConfig | None, path: Path | None)`
  - Handler loads from config or YAML, calls strategy_app_service.load_strategy()
  
- `StartStrategyCommand(strategy_id)`
  - Handler calls strategy_app_service.start_strategy()
  
- `StopStrategyCommand(strategy_id)`
  - Handler calls strategy_app_service.stop_strategy()

**Strategy Queries:**
- `GetStrategyQuery(strategy_id)` → dict with status
- `ListStrategiesQuery()` → list of strategy dicts

**Trading Queries:**
- `GetOrderQuery(order_id)` → OrderAggregate
- `ListOrdersQuery(strategy_id)` → list[OrderAggregate]
- `GetPositionQuery(strategy_id)` → position summary dict
- `ListPositionsQuery()` → list of position summaries

### Repositories

**OrderRepository** (persistence/order_repository.py)
- Collection: `COLLECTION_ORDERS`
- Methods:
  - `save(order)` → upsert
  - `get(order_id)` → OrderAggregate | None
  - `find_by_strategy(strategy_id, limit)` → list
  - `find_pending(limit)` → list (status in [pending, submitted, partially_filled])
  - `ensure_indexes()` → on strategy_id, status, (symbol, exchange)

**PositionRepository** (persistence/position_repository.py)
- Collection: `COLLECTION_POSITIONS`
- Methods: similar to OrderRepository
- `find_open()` → list (is_closed=false)

### Dependencies
- `pocketquant-core`
- `python-okx>=0.4.1` (OKX API SDK)
- `websockets>=12.0` (WebSocket client)
- `pyyaml>=6.0` (YAML strategy config)

### Event Flow & Integration
1. **Strategy Events:** BarCompletedEvent, QuoteReceivedEvent trigger on_bar(), on_tick()
2. **Signal Processing:** Signal → Risk check → Position sizing → OrderAggregate
3. **Order Events:** OrderFilledEvent triggers PositionAppService position updates
4. **Position Events:** PositionOpenedEvent, PositionClosedEvent published on position changes
5. **Broker Updates:** OKX WebSocket → OrderResult callbacks → OrderAppService.on_order_update()

---

## 3. Cross-Package Integration Points

### Shared Dependencies (via pocketquant-core)
- **Domain:** OrderAggregate, OrderSide, OrderStatus, PositionAggregate, BarCompletedEvent
- **Interfaces:** IBroker, IBrokerFactory, IStrategy
- **Infrastructure:** PaperBroker, EventBus, Mediator (CQRS)
- **Persistence:** BaseRepository, MongoDB collections

### Backtest → Core Brokers
- BacktestAppService uses **PaperBroker** (from core)
- Simulates fills, slippage, commission
- ResultCollector subscribes to fill events

### Trading → Core + Backtest
- StrategyAppService uses **IBroker** (interface in core)
- OKXBroker implements **IBroker** for live trading
- PaperBroker injected in tests (from core)

### Backtest → Trading (potential)
- Both share order/position domain models
- OptimizationResult could inform live strategy parameters
- Backtest metrics inform strategy performance tuning

---

## 4. Summary of Key Patterns

| Pattern | Backtest | Trading |
|---------|----------|---------|
| **Engine** | BacktestAppService (sync replay) | StrategyAppService (event-driven) |
| **Execution** | Batch (historical data) | Real-time (WebSocket) |
| **Broker** | PaperBroker (simulated) | OKXBroker (live API) |
| **Order Mgmt** | Implicit (in replay) | OrderAppService (lifecycle) |
| **Position Mgmt** | ResultCollector (trade tracking) | PositionAppService (event-driven) |
| **Persistence** | BacktestResult, OptimizationResult | Order, Position aggregates |
| **Optimization** | GridOptimizationAppService | Manual parameter tuning |
| **Event Model** | Simulation time events | Real-time event bus |

---

## 5. Test Coverage

**Backtest:** conftest.py exists but empty (tests directory exists)
**Trading:** conftest.py exists but empty (tests directory exists)

No unit tests found in either package. Test infrastructure ready but not implemented.

---

## Unresolved Questions

1. How are strategy parameters passed to strategies during execution?
2. What is StrategyLoader.load() implementation (YAML parsing)?
3. How does strategy trigger filtering work (trigger="bar" vs trigger="tick")?
4. Does OrderAppService handle partial fills (PARTIALLY_FILLED status)?
5. How are WebSocket reconnections tested?
6. What is the intended rate limit handling for OKX API calls?
