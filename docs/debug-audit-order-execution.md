# How a Real Order Gets Created — A Complete Walkthrough

**Last Updated:** 2026-03-22 | **Scope:** Every line of code executed from API call to exchange fill

This document walks you through the entire order execution path, step by step, explaining what each piece does and why we built it that way. By the end, you will understand every file, function, and design decision involved in placing a real trade.

---

## The Big Picture

When a user wants to trade, seven things happen in sequence:

```
1. Load Strategy    → Parse YAML config, store in memory
2. Start Strategy   → Connect broker, subscribe to market events
3. Market Data In   → WebSocket ticks build into OHLCV bars
4. Signal Generated → Strategy logic decides to buy/sell
5. Order Placed     → Submit to exchange via broker
6. Order Filled     → Exchange confirms execution
7. Position Updated → Track P&L, persist to database
```

Each step flows into the next through either direct function calls or async events. We use events to decouple the "what happened" from "who cares about it" — the bar builder does not need to know that strategies exist, it just announces "a bar completed" and whoever is listening reacts.

---

## Step 1: Loading a Strategy

**You call:** `POST /api/v1/strategy/load` with `{"path": "strategies/ma_crossover.yaml"}`

### 1a. The Route

**File:** `packages/pocketquant-trading/src/pocketquant/trading/handlers/strategy/load/route.py`

The request hits a FastAPI route. We use `FromDishka[Mediator]` to inject the CQRS mediator — this is the backbone of the system. Every API endpoint sends a Command or Query through the Mediator rather than calling services directly.

**Why Mediator?** It decouples routes from business logic. The route does not know which handler processes the command. This means we can swap, extend, or test handlers independently.

### 1b. YAML Parsing

**File:** `packages/pocketquant-trading/src/pocketquant/trading/app_services/yaml_strategy_loader.py`

`StrategyLoader.load(path)` reads the YAML file, parses it with `yaml.safe_load()`, and converts it into a `StrategyConfig` dataclass. Validation happens here — if the YAML is malformed or missing required fields, this is where it fails.

**Sample YAML:**
```yaml
id: "test-ma-crossover"
name: "MA Crossover Test"
symbol: "BTC-USDT"
exchange: "OKX"
interval: "1m"
broker: "paper"               # "paper" for testing, "okx" for real trading
strategy_type: "ma_crossover"
parameters:
  fast_period: 10
  slow_period: 20
risk:
  max_position_pct: 0.02      # Risk 2% of balance per trade
  max_drawdown_pct: 0.05
orders:
  entry_type: "market"
  stop_loss:
    distance_percent: 0.02
```

**Why YAML?** Strategies are configured externally so you can change parameters without touching code. The `broker` field controls whether you trade with real money or a simulated paper broker — same strategy logic, different execution backend.

### 1c. The CQRS Handler

**File:** `packages/pocketquant-trading/src/pocketquant/trading/handlers/strategy/load/handler.py`

`LoadStrategyHandler` receives the `LoadStrategyCommand` from the Mediator and delegates to `StrategyAppService.load_strategy()`. The handler is a thin adapter — it exists so the route never directly depends on the app service.

### 1d. Storing in Memory

**File:** `packages/pocketquant-trading/src/pocketquant/trading/app_services/strategy_app_service.py`

`load_strategy()` does three things under an asyncio lock:
1. Creates a broker instance — `PaperBroker` (in-memory simulation) or `OKXBroker` (real exchange)
2. Instantiates the strategy object (e.g., `MACrossover`)
3. Stores everything in three dictionaries keyed by strategy ID: `_strategies`, `_brokers`, `_configs`

**Why in-memory dicts?** Strategies are stateful — they maintain indicators, counters, internal state. Persisting them to a database on every tick would be too slow. The trade-off is that a restart loses loaded strategies (they must be reloaded).

**Why an asyncio lock?** Multiple API calls could try to load strategies concurrently. The lock prevents race conditions on the shared dictionaries.

**After this step:** The strategy exists in memory but is not yet trading. It has no connection to market data or events.

---

## Step 2: Starting the Strategy

**You call:** `POST /api/v1/strategy/{strategy_id}/start`

### 2a. Broker Connection

**File:** `packages/pocketquant-trading/src/pocketquant/trading/brokers/okx/okx_broker.py`

`start_strategy()` calls `broker.connect()`. For PaperBroker this is a no-op. For OKXBroker, it initializes the OKX SDK:
- `Trade.TradeAPI(api_key, secret, passphrase, flag)` — for placing orders
- `Account.AccountAPI(...)` — for checking balances

The `flag` parameter controls demo vs live: `"1"` = demo, `"0"` = real money. This comes from `OKX_DEMO` in your `.env`.

**Why lazy connection?** We do not connect to OKX when the strategy loads — only when it starts. This means you can load and inspect a strategy config without needing valid API keys.

### 2b. Event Subscriptions

**File:** `packages/pocketquant-core/src/pocketquant/core/common/messaging/event_registry.py`

The `EventRegistry` scans `StrategyAppService` for methods decorated with `@event_handler` and subscribes them to the EventBus:
- `_on_bar_completed` listens for `BarCompletedEvent`
- `_on_quote_received` listens for `QuoteReceivedEvent`

Similarly, `PositionAppService._on_order_filled` is subscribed to `OrderFilledEvent`.

**Why decorator-based discovery?** It keeps event wiring close to the handler code. You read the method and immediately see which event triggers it. The registry auto-discovers these at startup — no manual wiring table to maintain.

**After this step:** The strategy is armed. It is connected to the exchange and listening for market data events. But no data is flowing yet.

---

## Step 3: Market Data Flowing In

**Prerequisite:** `POST /api/v1/quotes/start` to open the WebSocket feed.

### 3a. Tick Ingestion

**File:** `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/quote_app_service.py`

`on_quote_update(quote_data)` is called each time TradingView sends a tick via WebSocket. It:
1. Parses the raw dict into a `Quote` object (symbol, price, bid, ask, volume)
2. Caches the latest quote in Redis (so other endpoints can read it without waiting for the next tick)
3. Creates a `QuoteTick` and passes it to `BarAppService.add_tick()`

**Why Redis cache?** The `/quotes/latest` endpoint needs instant access to the most recent price. Storing it in Redis means any process can read it, not just the one running the WebSocket.

### 3b. Building Bars from Ticks

**File:** `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/bar_app_service.py`

`add_tick()` processes each tick across all configured intervals (1m, 5m, 1h, 1d). For each interval, `_process_tick_for_interval()` does:
1. Calculates the bar's start time based on the interval (e.g., a 1m bar starting at 10:05:00)
2. If there is no current bar for this symbol+interval, creates a new `BarBuilder`
3. If the tick belongs to a new period (the previous bar is complete), calls `_save_completed_bar()`
4. Adds the tick's price and volume to the current bar

**Why build bars ourselves?** TradingView gives us raw ticks. We aggregate them into OHLCV bars locally because: (a) we need bars at exact intervals for strategy logic, (b) we control the bar boundaries, and (c) we can emit events the instant a bar completes rather than polling.

### 3c. Bar Completion — The Critical Event

**File:** `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/bar_app_service.py`

`_save_completed_bar()` is where market data becomes actionable:
1. Creates a domain `Bar` entity from the builder's accumulated state
2. Persists it to MongoDB (`bars` collection) — this is your historical data
3. Creates a `BarCompletedEvent` with all OHLCV fields
4. Publishes the event via `EventBus.publish()`
5. Clears the Redis cache for this bar (the persisted version is now the source of truth)

### 3d. EventBus Dispatches to Subscribers

**File:** `packages/pocketquant-core/src/pocketquant/core/common/messaging/event_bus.py`

`publish()` looks up all handlers registered for `BarCompletedEvent` and calls them in FIFO order. This is synchronous-await — each handler runs to completion before the next one starts. The event is also appended to an in-memory history (last 100 events) for debugging.

**Why in-memory EventBus?** Simplicity. We do not need message persistence or multi-process fanout. A single async Python process handles everything. If we needed horizontal scaling, we would swap this for Redis Pub/Sub or a proper message broker — but we are not there yet (YAGNI).

**After this step:** The `BarCompletedEvent` is traveling to `StrategyAppService._on_bar_completed()`.

---

## Step 4: Strategy Decides to Trade

### 4a. Strategy Receives the Bar

**File:** `packages/pocketquant-trading/src/pocketquant/trading/app_services/strategy_app_service.py`

`_on_bar_completed()` is the event handler that wakes the strategy up. It:
1. Finds all strategies subscribed to this symbol + exchange + interval
2. Converts the event into a plain dict (the strategy interface does not depend on our event classes)
3. Calls `strategy.on_bar(bar)` — this is the user's custom logic

The strategy returns either a `Signal` (direction + stop loss + optional entry price) or `None` (no trade).

**Why a plain dict?** The `IStrategy` interface is defined in `pocketquant-core/concepts/strategy/`. We want strategy authors to write pure logic without importing our event system. A dict is the simplest contract.

### 4b. Risk Validation

**File:** `packages/pocketquant-trading/src/pocketquant/trading/app_services/strategy_app_service.py`

If a signal is returned, `_process_signal()` runs before any order is created:
1. **Get balance** — `broker.get_balance()` calls the OKX REST API (or reads PaperBroker's in-memory balance). This is a network call for live trading.
2. **Check existing position** — prevents opening conflicting positions
3. **Risk validation** — `RiskCheckHandler.validate()` checks max position size, max drawdown, and other constraints from the YAML config. If validation fails, the signal is rejected and logged. No order is created.
4. **Position sizing** — `PositionSizer.calculate_size()` determines how much to buy/sell based on balance, current price, stop loss distance, and risk percentage. If size is zero (e.g., balance too low), no order is created.

**Why validate before creating the order?** We do not want invalid orders hitting the exchange. OKX would reject them anyway, but validating locally is faster and gives us better error messages.

### 4c. Creating the Order

**File:** `packages/pocketquant-core/src/pocketquant/core/domain/order/entities.py`

`OrderAggregate.create()` is a factory method that builds an order with:
- A unique UUID7 ID (time-sortable, globally unique)
- Status set to `PENDING` (not yet submitted to exchange)
- All trade parameters: symbol, side (BUY/SELL), type (MARKET/LIMIT), quantity, price

**Why an Aggregate?** Orders have a state machine (PENDING → SUBMITTED → PARTIALLY_FILLED → FILLED) and invariants (you cannot fill more than the order quantity). The aggregate pattern encapsulates these rules — state transitions happen through methods like `order.submit()` and `order.fill()` that enforce the rules.

---

## Step 5: Submitting to the Exchange

### 5a. Order Persistence and Submission

**File:** `packages/pocketquant-trading/src/pocketquant/trading/app_services/order_app_service.py`

`submit(order, broker)` is the critical function:
1. Acquires a lock (prevent concurrent submissions from racing)
2. Stores the order in `_pending` dict
3. **Persists to MongoDB first** (`orders` collection, status=PENDING) — this is important. If the app crashes after placing the order on OKX but before recording it, we would have a ghost order on the exchange. By writing to DB first, we have a record.
4. Calls `broker.submit_order(order)`

**Why persist before submitting?** This is the "write-ahead" pattern. The worst case is an order in our DB that was never actually placed (which we can detect and clean up). The alternative — an order placed on the exchange with no local record — is much harder to recover from.

### 5b. OKX Broker Execution

**File:** `packages/pocketquant-trading/src/pocketquant/trading/brokers/okx/okx_broker.py`

`submit_order()` translates our domain order into OKX API parameters:
- `instId`: the trading pair (e.g., "BTC-USDT")
- `side`: "buy" or "sell"
- `ordType`: "market" or "limit"
- `sz`: quantity as string (OKX requires strings)
- `clOrdId`: our order ID — this links the OKX order back to our system

Then it calls `self._trade_api.place_order(**params)` — this is the actual REST call to OKX.

The response contains the OKX-assigned `ordId` (their order ID) and possibly immediate fill information (for market orders). We parse this into an `OrderResult`.

**Common OKX error codes to watch for:**
- `51000` — parameter error (wrong format)
- `51001` — instrument not found (wrong symbol)
- `51008` — insufficient balance
- `51010` — order size below minimum

### 5c. After Submission

Back in `OrderAppService`, after the broker responds:
- If successful: store the broker-to-local ID mapping in `_broker_map`
- If market order and immediately filled: call `order.fill()`, move to `_orders` dict, update MongoDB, publish `OrderFilledEvent`
- If limit order: mark as SUBMITTED, wait for fill via WebSocket notification

**Why two ID mappings?** Our system uses UUID7 IDs. OKX uses its own numeric IDs. The `_broker_map` lets us correlate OKX callbacks with our orders. When OKX says "order 12345 is filled", we look up which local order that maps to.

---

## Step 6: Order Filled — Position Created

### 6a. The Fill Event

**File:** `packages/pocketquant-trading/src/pocketquant/trading/app_services/order_app_service.py`

When an order is filled (either immediately for market orders or via WebSocket for limit orders), `OrderFilledEvent` is published to the EventBus with: order ID, strategy ID, symbol, exchange, side, filled quantity, and filled price.

### 6b. Position Tracking

**File:** `packages/pocketquant-trading/src/pocketquant/trading/app_services/position_app_service.py`

`_on_order_filled()` is the event handler that manages positions:
1. Acquires a lock (position updates must be atomic)
2. Looks up existing position for this strategy
3. If **no position exists**: creates a new `PositionAggregate.open()` → publishes `PositionOpenedEvent`
4. If **position exists, same direction** (e.g., buying more when already long): `add_quantity()` updates the weighted average entry price
5. If **position exists, opposite direction** (e.g., selling when long): `reduce_quantity()` realizes P&L. If fully closed, `position.close()` → publishes `PositionClosedEvent`
6. Persists to MongoDB (`positions` collection)

**Why weighted average entry?** When you add to a position at different prices, the entry price becomes the weighted average. This is standard accounting — it tells you at what average cost you entered, which determines your unrealized P&L.

### 6c. Position State Machine

**File:** `packages/pocketquant-core/src/pocketquant/core/domain/position/entities.py`

`PositionAggregate` tracks:
- `side`: LONG or SHORT
- `quantity`: current size
- `entry_price`: weighted average
- `current_price` + `unrealized_pnl`: updated on new market data
- `realized_pnl`: from partial or full closes
- `status`: OPEN → CLOSED (terminal)

**Why an Aggregate?** Same reason as orders — positions have invariants. You cannot reduce below zero quantity. Closing a position must calculate realized P&L. The aggregate enforces these rules.

---

## Step 7: Verifying Everything Persisted

At this point the order has been placed, filled, and a position created. Three things should be in MongoDB:

```bash
mongosh "mongodb://localhost:27018"

# The order (should be FILLED)
db.orders.find({strategy_id: "test-ma-crossover"}).sort({created_at: -1}).limit(5)

# The position (should be OPEN with correct entry price)
db.positions.find({strategy_id: "test-ma-crossover"})

# The bar that triggered the trade
db.bars.find({symbol: "BTC-USDT", exchange: "OKX"}).sort({datetime: -1}).limit(5)
```

And in Redis:
```bash
redis-cli
KEYS quote:*     # Latest cached quotes
KEYS bar:*       # Current incomplete bars being built
```

---

## Verification Checklist

| # | Step | What to Verify |
|---|------|----------------|
| 1 | Infra | Docker up: MongoDB on 27018, Redis on 6379 |
| 2 | Infra | App starts, `GET /health` returns OK |
| 3 | Load | POST /strategy/load — YAML parsed, no errors |
| 4 | Load | Strategy stored in memory (check "strategy_loaded" log) |
| 5 | Start | POST /strategy/{id}/start — broker connected |
| 6 | Start | Event subscriptions registered (check "handlers_registered" log) |
| 7 | Data | POST /quotes/start — WebSocket opens |
| 8 | Data | Ticks arriving (DEBUG logs show "quote_update") |
| 9 | Data | Bars building (check Redis for `bar:*` keys) |
| 10 | Data | Bar completes → MongoDB write (check `bars` collection) |
| 11 | Data | BarCompletedEvent published (log: "bar_completed") |
| 12 | Signal | strategy.on_bar() called (log: "strategy_on_bar") |
| 13 | Signal | Signal generated — or explain why not (not enough bars for MA?) |
| 14 | Risk | Risk check passed (log: "risk_check_passed" or "signal_rejected_by_risk") |
| 15 | Risk | Position size > 0 (log: "position_size_calculated") |
| 16 | Order | OrderAggregate created with correct fields |
| 17 | Order | Order persisted to MongoDB (status=PENDING) |
| 18 | Broker | broker.submit_order() called — check OKX response |
| 19 | Broker | Order status updated (FILLED for market, SUBMITTED for limit) |
| 20 | Fill | OrderFilledEvent published |
| 21 | Position | PositionAppService received fill → position created/updated |
| 22 | Position | Position persisted to MongoDB |
| 23 | Final | MongoDB orders + positions match expected state |
| 24 | Final | Redis state consistent (no stale keys) |

---

## Key Files (22 files, in execution order)

All paths relative to `packages/pocketquant-{package}/src/pocketquant/{package}/`:

| Step | Package | File | What It Does |
|------|---------|------|--------------|
| 1a | trading | `handlers/strategy/load/route.py` | API entry point |
| 1b | trading | `app_services/yaml_strategy_loader.py` | Parse YAML config |
| 1c | trading | `handlers/strategy/load/handler.py` | CQRS command handler |
| 1d | trading | `app_services/strategy_app_service.py` | Store strategy + broker in memory |
| 2a | trading | `handlers/strategy/start/route.py` | API entry point |
| 2a | trading | `handlers/strategy/start/handler.py` | CQRS command handler |
| 2b | trading | `brokers/okx/okx_broker.py` | Initialize OKX SDK connection |
| 2c | core | `common/messaging/event_registry.py` | Auto-discover @event_handler methods |
| 3a | api | `market_data/app_services/quote_app_service.py` | WebSocket tick → Quote → cache |
| 3b | api | `market_data/app_services/bar_app_service.py` | Ticks → OHLCV bars → BarCompletedEvent |
| 3d | core | `common/messaging/event_bus.py` | Dispatch events to subscribers |
| 4a | trading | `app_services/strategy_app_service.py` | Receive bar → call strategy.on_bar() |
| 4b | core | `concepts/risk/risk_check_handler.py` | Validate signal against risk rules |
| 4b | core | `concepts/risk/position_sizer.py` | Calculate order size from risk params |
| 4c | core | `domain/order/entities.py` | OrderAggregate with state machine |
| 5a | trading | `app_services/order_app_service.py` | Persist-then-submit pattern |
| 5b | trading | `brokers/okx/okx_broker.py` | REST API call to OKX |
| 6a | trading | `app_services/order_app_service.py` | Publish OrderFilledEvent |
| 6b | trading | `app_services/position_app_service.py` | Create/update position on fill |
| 6c | core | `domain/position/entities.py` | PositionAggregate with P&L tracking |
| 7 | core | `persistence/repositories/*` | MongoDB read/write for all entities |

---

## Design Decisions Summary

| Decision | Why |
|----------|-----|
| CQRS + Mediator | Decouple routes from business logic; handlers are testable in isolation |
| EventBus (in-memory) | Simple, fast, sufficient for single-process. No message broker overhead (YAGNI) |
| Write-ahead persistence | Order saved to DB before exchange submission — prevents ghost orders |
| IBroker protocol | Same strategy code works with PaperBroker (testing) and OKXBroker (live) |
| Aggregates for Order/Position | Enforce state machine invariants — cannot skip states or violate rules |
| YAML config | Change strategy parameters without code changes; broker field toggles paper/live |
| Async locks per AppService | Prevent race conditions on in-memory state from concurrent events |
| Redis for quotes/bars cache | Fast read access from any endpoint without waiting for the next tick |
| Decorator-based event wiring | Keeps subscription logic next to handler code; auto-discovered at startup |
