# Order Execution — Debug Audit

**Last Updated:** 2026-05-25 | **Scope:** Full execution path, API call → exchange fill → DB persist

> Deep-dive walkthrough. For local run steps see [run-and-test-guide](./run-and-test-guide.md).

## Prerequisites

- Docker up: MongoDB on `$MONGO_PORT` (default 52017), Redis on `$REDIS_PORT` (default 53679)
- `GET /health` returns OK
- Valid `.env` with `OKX_DEMO=1` (demo) or `OKX_DEMO=0` (live)

## Doc Map

| Section | Lines |
|---------|-------|
| [Golden Path — 7 Steps](#golden-path) | Steps 1–7 |
| [Appendix A — Edge Cases](#appendix-a-edge-cases) | Partial fills, broker errors, races |
| [Appendix B — Diagnostic Commands](#appendix-b-diagnostic-commands) | mongosh, redis-cli |

---

## Golden Path

### Step 1 — Load Strategy

**API:** `POST /api/v1/strategies/load` `{"path": "strategies/your-strategy.yaml"}`

- Route (`trading/handlers/strategy/load/route.py`) injects `Mediator` via `FromDishka`; sends `LoadStrategyCommand`.
- Handler (`handlers/strategy/load/handler.py`) delegates to `StrategyAppService.load_strategy()`.
- `yaml_strategy_loader.py` reads + validates YAML → `StrategyConfig` dataclass.
- `StrategyAppService` (under asyncio lock) creates broker instance (`PaperBroker` or `OKXBroker`) + strategy object; stores both in in-memory dicts keyed by strategy ID.

**Expected:** `200 OK`, log `strategy_loaded`. **Unexpected:** YAML parse error → fix config; missing fields → add required keys.

---

### Step 2 — Start Strategy

**API:** `POST /api/v1/strategy/{strategy_id}/start`

- `OKXBroker.connect()` initializes OKX SDK (`Trade.TradeAPI`, `Account.AccountAPI`). `PaperBroker.connect()` is a no-op.
- `EventRegistry` scans `StrategyAppService` for `@event_handler` methods and subscribes them to `EventBus`: `_on_bar_completed` → `BarCompletedEvent`; `_on_quote_received` → `QuoteReceivedEvent`. `PositionAppService._on_order_filled` → `OrderFilledEvent`.

**Expected:** log `handlers_registered`, broker connected. **Unexpected:** OKX SDK init failure → check API keys / `OKX_DEMO` flag.

---

### Step 3 — Market Data In

**API (prerequisite):** `POST /api/v1/quotes/start`

- `QuoteAppService.on_quote_update()`: parses tick → `Quote`; caches latest in Redis; passes `QuoteTick` to `BarAppService`.
- `BarAppService.add_tick()`: aggregates ticks into OHLCV bars per interval; when bar period ends calls `_save_completed_bar()`.
- `_save_completed_bar()`: persists `Bar` to MongoDB (`bars` collection); publishes `BarCompletedEvent` via `EventBus`; clears Redis bar cache.
- `EventBus.publish()` dispatches event synchronously to all subscribers (FIFO).

**Expected:** DEBUG logs `quote_update`; Redis `bar:*` keys appear; MongoDB `bars` collection grows; log `bar_completed`. **Unexpected:** no ticks → check WebSocket; bars not completing → check interval alignment.

---

### Step 4 — Strategy Generates Signal

- `StrategyAppService._on_bar_completed()`: finds strategies for this symbol+exchange+interval; converts event to plain dict; calls `strategy.on_bar(bar)` → returns `Signal` or `None`.
- If signal: `_process_signal()` runs:
  1. `broker.get_balance()` — REST call for live, in-memory for paper.
  2. Check existing position — block conflicting direction.
  3. `RiskCheckHandler.validate()` — enforces YAML risk params (max position %, max drawdown %).
  4. `PositionSizer.calculate_size()` — size from balance × risk% ÷ stop-distance.

**Expected:** log `strategy_on_bar`; either `risk_check_passed` + `position_size_calculated`, or `signal_rejected_by_risk`. **Unexpected:** `None` signal → insufficient bars for indicator warmup (normal early on); size=0 → balance too low.

---

### Step 5 — Submit Order to Exchange

- `OrderAggregate.create()`: UUID7 ID, status=`PENDING`, all trade params (symbol, side, type, qty, price).
- `OrderAppService.submit()` (under lock):
  1. Persist to MongoDB (`orders`, status=`PENDING`) — write-ahead before exchange call.
  2. `broker.submit_order()` translates to OKX params (`instId`, `side`, `ordType`, `sz` as string, `clOrdId`=our UUID) → REST call.
  3. On success: store broker↔local ID mapping in `_broker_map`.
  4. Market order filled immediately → `order.fill()`, move to `_orders`, update MongoDB, publish `OrderFilledEvent`.
  5. Limit order → mark `SUBMITTED`, await WebSocket fill notification.

**Expected:** MongoDB order `PENDING` then `FILLED`/`SUBMITTED`; log OKX `ordId`. **Unexpected:** see [Appendix A](#appendix-a-edge-cases) for OKX error codes.

---

### Step 6 — Fill → Position Update

- `OrderFilledEvent` carries: order ID, strategy ID, symbol, exchange, side, filled qty, filled price.
- `PositionAppService._on_order_filled()` (under lock):
  - No position → `PositionAggregate.open()` → `PositionOpenedEvent`.
  - Same direction → `add_quantity()`, updates weighted-average entry price.
  - Opposite direction → `reduce_quantity()`, realizes P&L; if fully closed → `position.close()` → `PositionClosedEvent`.
  - Persists to MongoDB (`positions` collection) via `trading/persistence/position_repository.py`.

**Expected:** MongoDB `positions` doc created/updated with correct entry price. **Unexpected:** no position doc → check `OrderFilledEvent` was published; wrong P&L → verify side mapping.

---

### Step 7 — Verify Persistence

Check all three stores are consistent:

```bash
# MongoDB — order FILLED, position OPEN
mongosh "mongodb://localhost:52017"
db.orders.find({strategy_id: "your-strategy-id"}).sort({created_at: -1}).limit(5)
db.positions.find({strategy_id: "your-strategy-id"})
db.bars.find({symbol: "BTC-USDT", exchange: "OKX"}).sort({datetime: -1}).limit(5)
```

```bash
# Redis — no stale bar keys
redis-cli
KEYS quote:*
KEYS bar:*
```

**Expected:** order `status=FILLED`, position `status=OPEN` with correct `entry_price`; Redis bar keys only for current incomplete bars. **Unexpected:** see [Appendix B](#appendix-b-diagnostic-commands).

---

## Appendix A: Edge Cases

### Partial Fills (Limit Orders)

OKX may fill a limit order in multiple chunks. Each partial fill triggers a WebSocket message → `OrderAppService` calls `order.fill(partial_qty, partial_price)` → publishes `OrderFilledEvent` with partial qty → `PositionAppService.add_quantity()` updates weighted average. Order stays `PARTIALLY_FILLED` until cumulative qty = original qty.

**Debug:** `db.orders.find({status: "PARTIALLY_FILLED"})` — if stuck, check OKX order status via REST.

### OKX Broker Errors

| Code | Meaning | Fix |
|------|---------|-----|
| 51000 | Parameter error (format) | Check `sz` is string, `instId` format e.g. `BTC-USDT` |
| 51001 | Instrument not found | Verify symbol mapping in broker; use OKX-format not TradingView |
| 51008 | Insufficient balance | Reduce `max_position_pct` in YAML or fund account |
| 51010 | Order size below minimum | Increase balance or lower risk %; OKX minimums vary by pair |

### Race Condition: Concurrent Bar Events

Two `BarCompletedEvent`s for same strategy arrive concurrently (e.g., 1m and 5m bar complete simultaneously). Both call `_on_bar_completed()` → both may generate signals → `OrderAppService` lock prevents double submission but both risk checks run. Mitigate: check existing position before risk check (Step 4, point 2 above blocks conflicting signals).

### Strategy Restart After Crash

In-memory state (loaded strategies, brokers, in-flight orders) is lost on restart. Orders in MongoDB with `status=PENDING` or `SUBMITTED` are orphans — no local record. Recovery: query `db.orders.find({status: {$in: ["PENDING","SUBMITTED"]}})` and reconcile with OKX REST API manually. No automatic recovery is implemented (YAGNI).

### Paper Broker Fills

`PaperBroker` fills market orders instantly at current price (from Redis quote cache). If Redis has no quote cached (e.g., quotes feed not started), fill price defaults to order price. Start `POST /api/v1/quotes/start` before loading/starting strategy in paper mode.

---

## Appendix B: Diagnostic Commands

### MongoDB Queries

```bash
mongosh "mongodb://localhost:52017"

# Full order detail
db.orders.findOne({strategy_id: "your-id"}, {_id:0})

# Orders stuck in non-terminal state
db.orders.find({status: {$in: ["PENDING","SUBMITTED","PARTIALLY_FILLED"]}})

# Position P&L check
db.positions.findOne({strategy_id: "your-id"}, {entry_price:1, realized_pnl:1, unrealized_pnl:1, status:1, _id:0})

# Last 10 bars for a symbol
db.bars.find({symbol:"BTC-USDT", exchange:"OKX", interval:"1m"}).sort({datetime:-1}).limit(10)
```

### Redis Inspection

```bash
redis-cli -p 53679   # or $REDIS_PORT

KEYS quote:*         # cached latest quotes (should have entries if feed running)
KEYS bar:*           # current incomplete bars (cleared when bar completes)
GET quote:BTC-USDT:OKX
TTL quote:BTC-USDT:OKX
```

### Log Grep Patterns

```bash
# Filter key lifecycle events from app logs
grep -E "strategy_loaded|handlers_registered|bar_completed|strategy_on_bar|risk_check|position_size|order_submitted|order_filled|position_opened" app.log

# OKX API errors
grep -E "OKX|51[0-9]{3}" app.log
```
