# PocketQuant Project Overview
**For: New Team Members & Learning Context**
**Date:** 2026-01-28 | **Status:** Core Platform Ready (v1.0)

---

## What Problem Does PocketQuant Solve?

Imagine you're a stock trader or a quant researcher building trading strategies. You need:

1. **Historical market data** (OHLCV = Open/High/Low/Close/Volume bars) for backtesting
2. **Real-time price quotes** to track markets as they move
3. **Multiple time frames** (1-minute bars, 5-minute bars, daily bars, etc.) all at once
4. **Reliable storage** so you don't lose data when something crashes

**The Problem:** Getting this data from TradingView is hard, organizing it is messy, and building your own system takes weeks.

**The Solution:** PocketQuant automates all of this.

---

## What Does PocketQuant Do? (In 30 Seconds)

PocketQuant is a **data backbone for traders and quants**. It:

1. **Pulls historical stock/crypto data** from TradingView (can grab 5,000 bars at a time)
2. **Connects to live price streams** via WebSocket (real-time quotes)
3. **Automatically groups ticks** into different time-period bars (1-min, 5-min, hourly, daily, etc.)
4. **Stores everything safely** in MongoDB (a flexible database)
5. **Caches hot data** in Redis (super fast access)
6. **Runs automatic updates** on a schedule (every 6 hours, daily market hours, etc.)
7. **Gives you clean APIs** to query all this data via HTTP requests

Think of it as: **TradingView data → PocketQuant → Your trading strategy engine**

---

## Who Uses It?

- **Algorithmic Traders:** Building automated trading bots
- **Quant Researchers:** Backtesting strategies on reliable data
- **Data Engineers:** Need clean market data pipelines
- **Traders:** Want programmatic access to market data

---

## Main Features

### 1. Historical Data Sync
- Pull OHLCV bars from TradingView for any stock/crypto
- Works with 13 different time intervals (1 minute to 1 month)
- Max 5,000 bars per request (smart pagination)
- Stores in MongoDB with no duplicates
- Can sync single symbol or bulk sync many symbols

**Example:** Fetch 5 years of daily Apple stock data in one request.

### 2. Real-time Quotes
- Live price updates via WebSocket
- Auto-reconnects if connection drops
- Caches latest quote in Redis (60-second TTL)
- Can subscribe/unsubscribe to any symbol

**Example:** Get Apple's latest price updated every tick (~milliseconds).

### 3. Automatic Bar Aggregation
- Takes raw ticks and groups them into bars
- Creates bars for ALL intervals simultaneously (1m, 5m, 15m, 1h, daily, etc.)
- Automatically saves complete bars to MongoDB
- Keeps in-progress bars in Redis cache

**Example:** One tick stream → 13 different interval bars all building in real-time.

### 4. Background Jobs
- Scheduled sync every 6 hours (500 bars per symbol)
- Market hours sync for daily data (hourly on trading days)
- Graceful error handling (one failure doesn't break everything)

**Example:** Every morning at 9am, automatically update yesterday's daily bars.

### 5. Clean APIs
- Simple HTTP endpoints
- OpenAPI documentation (Swagger UI built-in)
- Request/response validation (no garbage in/out)
- Rate limiting (200 requests per 10 seconds max)

---

## How It's Built (Simple Version)

### Architecture Pattern: "Vertical Slices"

Instead of organizing by layer (all routes together, all databases together), PocketQuant organizes by **feature**:

```
Each feature = API routes + business logic + database code together

Example: "Market Data" slice contains:
  - API endpoints (/market-data/sync, /market-data/ohlcv)
  - Sync/query logic
  - MongoDB interactions
  - Redis caching
  - Background jobs
```

**Why?** When you need to change something about market data, it's all in one place. Easier to understand, test, and maintain.

### Infrastructure Stack

| Component | Purpose |
|-----------|---------|
| **FastAPI** | HTTP server with automatic docs |
| **MongoDB** | Stores all OHLCV bars (indexed by symbol + timestamp) |
| **Redis** | Cache for fast lookups (quotes, recent bars) |
| **APScheduler** | Runs background sync jobs on schedule |
| **TradingView APIs** | REST API (historical data) + WebSocket (real-time) |
| **Docker Compose** | Runs MongoDB + Redis locally (development) |

---

## What Does It Look Like to Use It?

### Start Everything
```bash
just install   # Setup Python environment
just start     # Launch MongoDB, Redis, and PocketQuant
```

### Pull Historical Data
```bash
curl -X POST http://localhost:8765/api/v1/market-data/sync \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "exchange": "NASDAQ",
    "interval": "1d",
    "n_bars": 5000
  }'
```

**Response:**
```json
{
  "bars_synced": 5000,
  "status": "completed"
}
```

### Subscribe to Live Quotes
```bash
# Start the WebSocket connection
curl -X POST http://localhost:8765/api/v1/quotes/start

# Subscribe to Apple
curl -X POST http://localhost:8765/api/v1/quotes/subscribe \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "exchange": "NASDAQ"}'

# Get latest price
curl http://localhost:8765/api/v1/quotes/latest/NASDAQ/AAPL
```

### Query Historical Data
```bash
curl "http://localhost:8765/api/v1/market-data/ohlcv/NASDAQ/AAPL?interval=1d&limit=100"
```

**Response:**
```json
{
  "bars": [
    {
      "timestamp": "2026-01-28T00:00:00Z",
      "open": 220.5,
      "high": 221.3,
      "low": 220.1,
      "close": 220.8,
      "volume": 45000000
    },
    ...
  ]
}
```

### View API Docs
Open browser: `http://localhost:8765/api/v1/docs`

(Interactive Swagger UI with all endpoints, try them out)

---

## Key Concepts to Know

### Symbol + Exchange
- **Symbol:** Ticker code (AAPL, BTC, EUR/USD)
- **Exchange:** Where it trades (NASDAQ, NYSE, BINANCE, FOREX)
- **Unique pair:** NASDAQ:AAPL is different from OTC:AAPL

### Intervals
13 standard intervals supported:
- **1m, 5m, 15m, 30m** (intraday - trades within a day)
- **1h, 4h** (hours)
- **1d** (daily - one bar per trading day)
- **1w, 2w, 1M** (weekly, bi-weekly, monthly)

### OHLCV Data
- **Open:** Price when bar started
- **High:** Highest price during bar
- **Low:** Lowest price during bar
- **Close:** Price when bar ended
- **Volume:** Total shares/contracts traded

### Sync Status
- **Pending:** Waiting to start
- **Syncing:** In progress
- **Completed:** Done (bar count included)
- **Error:** Failed (reason included)

---

## Configuration (Environment Variables)

```env
# Server
API_HOST=0.0.0.0
API_PORT=8765

# Database (MongoDB)
MONGODB_URL=mongodb://localhost:27018
MONGODB_DATABASE=pocketquant

# Cache (Redis)
REDIS_URL=redis://localhost:6379

# TradingView Auth (optional)
TRADINGVIEW_USERNAME=your_username
TRADINGVIEW_PASSWORD=your_password

# Logging
LOG_FORMAT=console  # or "json" for production
LOG_LEVEL=info

# Environment
ENVIRONMENT=development  # or "production", "staging"
```

All config comes from `.env` file (never hardcoded, never committed to git).

---

## Development Commands

| Command | Purpose |
|---------|---------|
| `just install` | Create Python environment + install dependencies |
| `just start` | Start Docker services + PocketQuant |
| `just stop` | Stop all services |
| `just logs` | View live logs |
| `pytest` | Run all tests |
| `ruff check .` | Check code quality |
| `mypy src/` | Check type safety |
| `uvicorn src.main:app --reload` | Run with hot reload (dev) |

---

## Project Status

### What's Done ✅
- Historical data sync from TradingView
- Real-time WebSocket quotes
- Multi-interval bar aggregation
- MongoDB storage (optimized)
- Redis caching (smart TTL)
- Background job scheduling
- REST API with 100% documentation
- Docker setup for local dev
- Comprehensive tests (75%+ coverage)
- Structured JSON logging for production

### What's Planned 🚀
- **Phase 2:** More data sources (Binance, Kraken, crypto, fundamentals)
- **Phase 3:** Backtesting engine (replay history, performance metrics)
- **Phase 4:** Live trading (paper trading, broker integrations)
- **Phase 5:** Web dashboard + visualization

---

## Key Design Decisions

### Why Vertical Slices?
- Easy to understand (all market-data logic = one folder)
- Easy to test (self-contained feature)
- Easy to extend (add new feature = add new slice)

### Why CQRS (Command/Query)?
- **Commands:** Modify data (sync, subscribe, unsubscribe)
- **Queries:** Read data (get bars, status)
- Separates "do something" from "get info" (clearer thinking)

### Why MongoDB + Redis?
- **MongoDB:** Flexible schema (OHLCV bars have consistent structure, but schema can evolve)
- **Redis:** Fast cache (quotes change every millisecond, can't query MongoDB that fast)

### Why ThreadPool for TradingView REST?
- TradingView's tvdatafeed library is blocking (old-style API)
- ThreadPool prevents blocking the async event loop
- Max 4 workers = controlled concurrency

---

## Files You Should Know

| File | Purpose |
|------|---------|
| `src/config.py` | All environment configuration |
| `src/main.py` | FastAPI app setup + startup/shutdown |
| `src/features/market_data/` | All market data logic (sync, quotes, bars) |
| `src/common/` | Shared infrastructure (database, cache, logging, jobs) |
| `docker/compose.yml` | Local dev services (MongoDB + Redis) |
| `.env.example` | Template for environment variables |
| `justfile` | Development commands (just install, just start) |
| `docs/` | Architecture guides and standards |

---

## Common Questions

**Q: How much historical data can I sync?**
A: TradingView limits to 5,000 bars per request. For daily Apple, that's ~20 years. You can make multiple requests for different time ranges.

**Q: Can I use it without TradingView?**
A: Not currently - the data comes from TradingView. Phase 2 will add more sources.

**Q: How fast is it?**
A: Historical sync: 1-5 seconds for 5,000 bars. Cache lookups: <5ms. Bar aggregation: <1ms per tick.

**Q: What if MongoDB/Redis crashes?**
A: You'll get errors. The app has health checks and will log failures. Restart the containers and resync.

**Q: Can I run it in production?**
A: Yes. Change `.env` to `LOG_FORMAT=json`, use cloud MongoDB/Redis, deploy with Docker. See `docs/deployment-guide.md`.

**Q: Is there a web UI?**
A: Not yet (Phase 5 planned). Currently API-only. Use Postman or curl to interact.

---

## Next Steps to Explore

1. **See it in action:** `just start` → visit `http://localhost:8765/api/v1/docs`
2. **Try an API call:** Sync some data, query it back
3. **Read detailed docs:** `./docs/system-architecture.md` (advanced)
4. **Check code standards:** `./docs/code-standards.md`
5. **Run tests:** `pytest` (see if everything works)

---

## Unresolved Questions

None - this overview covers the complete v1.0 platform.
