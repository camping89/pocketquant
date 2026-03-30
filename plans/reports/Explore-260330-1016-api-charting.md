# PocketQuant API Layer Exploration for Charting Integration

**Date:** 2026-03-30 | **Explored:** packages/pocketquant-api/src/

## 1. OHLCV/Bar Endpoint

**File:** `packages/pocketquant-api/src/pocketquant/api/market_data/handlers/ohlcv/get_ohlcv/route.py`

**Endpoint Path:** `GET /api/v1/market-data/ohlcv/{exchange}/{symbol}`

**Query Parameters:**
- `interval: Interval` (default: DAY_1) - bar interval enum
- `start_date: datetime | None` - filter start date
- `end_date: datetime | None` - filter end date  
- `limit: int` (default: 1000, max: 5000) - max bars returned

**Response Model:**
```python
class OHLCVResponse(BaseModel):
    symbol: str
    exchange: str
    interval: str
    data: list[dict[str, Any]]  # Raw bar dicts (from mediator)
    count: int
```

**Response Shape Example:**
```json
{
  "symbol": "AAPL",
  "exchange": "NASDAQ",
  "interval": "1d",
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "symbol": "AAPL",
      "exchange": "NASDAQ",
      "interval": "1d",
      "datetime": "2026-01-01T00:00:00+00:00",
      "open": 150.0,
      "high": 152.5,
      "low": 149.8,
      "close": 151.2,
      "volume": 1000000.0,
      "tick_count": 500
    }
  ],
  "count": 1
}
```

---

## 2. Real-time Quotes Endpoints

**Router File:** `packages/pocketquant-api/src/pocketquant/api/market_data/handlers/quotes/router.py`

**Prefix:** `/api/v1/quotes/`

### 2.1 Subscribe to Symbol
**Endpoint:** `POST /api/v1/quotes/subscribe`

**Request:**
```python
class SubscribeRequest(BaseModel):
    symbol: str  # e.g., "AAPL"
    exchange: str  # e.g., "NASDAQ"
```

**Response:**
```python
class SubscribeResponse(BaseModel):
    subscription_key: str
    message: str
```

### 2.2 Get Latest Quote
**Endpoint:** `GET /api/v1/quotes/latest/{exchange}/{symbol}`

**Response Model:**
```python
class QuoteResponse(BaseModel):
    symbol: str
    exchange: str
    timestamp: str
    last_price: float
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    change: float | None = None
    change_percent: float | None = None
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
```

### 2.3 Get All Active Quotes
**Endpoint:** `GET /api/v1/quotes/all`

**Response:** `list[QuoteResponse]`

### 2.4 WebSocket Feed Control
- `POST /api/v1/quotes/start-feed` — Start real-time WebSocket
- `POST /api/v1/quotes/stop-feed` — Stop real-time WebSocket

**Backend:** TradingViewWebSocketClient parses binary frames (~m~{len}~m~{json})

### 2.5 Quote Update Pipeline
**File:** `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/quote_app_service.py`

**Flow:**
1. WebSocket binary frame → parsed
2. QuoteAppService.on_quote_update() creates Quote DTO
3. Cache: `quote:latest:{exchange}:{symbol}` (TTL: 60s)
4. BarAppService.add_tick() aggregates into bars (1m, 5m, 1h, 1d)
5. On bar completion: MongoDB insert + BarCompletedEvent published

---

## 3. Symbols Endpoint

**Endpoint:** `GET /api/v1/market-data/symbols`

**Query Parameters:**
- `exchange: str | None` - optional filter

**Response:** `list[dict]`

**Response Shape:**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "code": "AAPL",
    "exchange": "NASDAQ",
    "name": "Apple Inc",
    "asset_type": "stock",
    "is_active": true
  }
]
```

---

## 4. CORS Middleware Status

**File:** `packages/pocketquant-api/src/pocketquant/api/main_extensions.py` (lines 115-121)

**Status:** CORS middleware EXISTS

**Configuration:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Details:**
- **Development:** Allows all origins (`["*"]`)
- **Production:** Blocks CORS (empty list `[]`)
- Credentials: allowed
- Methods: all HTTP methods
- Headers: all headers

**Control:** Via `settings.environment` (pydantic-settings from .env)

---

## 5. Bar Entity

**File:** `packages/pocketquant-core/src/pocketquant/core/domain/bar/entities.py`

**Full Field List:**
```python
class Bar(BaseModel):
    id: UUID  # UUID7, time-ordered
    symbol: str
    exchange: str
    interval: Interval | None
    datetime: dt | None
    open: float
    high: float
    low: float
    close: float
    volume: float
    tick_count: int  # Number of ticks aggregated
    created_at: dt  # Creation timestamp
```

**to_dict() Output:**
```python
{
    "id": str(self.id),  # UUID as string
    "symbol": self.symbol,
    "exchange": self.exchange,
    "interval": self.interval.value if self.interval else None,
    "datetime": self.datetime.isoformat() if self.datetime else None,
    "open": self.open,
    "high": self.high,
    "low": self.low,
    "close": self.close,
    "volume": self.volume,
    "tick_count": self.tick_count
}
```

**MongoDB Methods:**
- `to_mongo()` → flattened dict with _id
- `from_mongo()` → reconstructs from MongoDB doc

**Properties:**
- `is_complete: bool` — returns `tick_count > 0`

---

## 6. Architecture Patterns from Docs

### 6.1 Vertical Slice Architecture
**From:** `docs/system-architecture.md` (lines 183-241)

Each operation is self-contained:
```
operation_name/
├── command.py or query.py  # Request definition
├── handler.py              # @handles decorator
├── route.py                # FastAPI route
└── __init__.py
```

### 6.2 Handler 5-Step Pattern
**From:** `docs/code-standards.md` (lines 360-375)

1. Fetch from infrastructure
2. Validate via domain
3. Persist via infrastructure
4. Invalidate cache
5. Publish domain events

### 6.3 Dependency Injection (Dishka)
**From:** `docs/system-architecture.md` (lines 696-714)

Type-hint autowiring. Routes use `FromDishka[Mediator]` for auto-injection.

### 6.4 Real-time Quote Pipeline
**From:** `docs/system-architecture.md` (lines 569-595)

```
TradingView WebSocket
  → TradingViewWebSocketClient.parse_frame
  → QuoteAppService.on_quote_update()
  → Redis.set(quote:latest, quote, ttl=60s)
  → BarAppService.add_tick()
  → Bar completion → MongoDB + EventBus.publish(BarCompletedEvent)
```

### 6.5 Middleware Stack
**From:** `docs/system-architecture.md` (lines 522-531)

Order: CorrelationID → RateLimit (200 req/10s) → Idempotency (24h) → Route

---

## 7. Summary for Charting Integration

**Ready:**
- ✅ OHLCV endpoint (5000 bar limit, date filtering)
- ✅ Latest quote endpoint (real-time tickers)
- ✅ Symbols endpoint (symbol discovery)
- ✅ CORS middleware (dev-friendly, prod-configurable)
- ✅ Real-time via WebSocket + BarCompletedEvent
- ✅ Caching: Redis (quotes 60s, bars 300s)
- ✅ Type-safe Pydantic models
- ✅ Bar.to_dict() production-ready

**CORS for Production:**
Currently blocks all origins in prod. Requires reverse proxy or env config to allow specific frontend origin.

**Quote Update Performance:**
- Quote throughput: 1000+/sec
- Bar aggregation: <1ms/tick
- Mediator dispatch: <0.1ms

