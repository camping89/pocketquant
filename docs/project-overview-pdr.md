# PocketQuant: Project Overview & Product Development Requirements

Architecture: DDD + CQRS + Clean Architecture + Dishka. Structure: single Python package `src/pocketquant/` + `web/` as a separate npm app.

Discover architecture, code patterns, and conventions in `./docs/` — see [system-architecture.md](./system-architecture.md), [code-standards.md](./code-standards.md), [README.md](../README.md).

## Project Vision

PocketQuant is an algorithmic trading platform providing real-time market data synchronization, automated bar aggregation, and structured data storage for backtesting and forward testing workflows. The platform bridges Binance public market data with MongoDB persistence, enabling traders and quants to build strategies on reliable, comprehensive market data.

## Product Goals

1. **Data Reliability:** Efficient historical bar sync from Binance with MongoDB persistence
2. **Real-time Processing:** Live quote streaming with automatic aggregation into multiple timeframe bars
3. **Developer Experience:** Clean REST API with OpenAPI documentation, minimal setup friction
4. **Production Ready:** Structured logging, error handling, graceful degradation
5. **Extensibility:** DDD + CQRS architecture with vertical slice features and clean separation of concerns

## Functional Requirements

### F1: Historical Data Synchronization

**Requirement:** Fetch bar data from Binance public REST and persist to MongoDB.

**Sub-requirements:**
- Sync single symbol with configurable interval and bar count
- Bulk sync multiple symbols in single operation
- Background/async sync without blocking client
- Track sync progress and status
- Prevent duplicate data via upsert operations
- Support 7 standard intervals (1m, 5m, 15m, 1h, 4h, 1d, 1w)
- Auto-paginate when `n_bars > 1000` (Binance returns max 1000 bars/call, 1200 weight/min budget)

**API Endpoints:**
- POST `/api/v1/market-data/sync` - Single symbol
- POST `/api/v1/market-data/sync/background` - Async single symbol
- POST `/api/v1/market-data/sync/bulk` - Multiple symbols
- GET `/api/v1/market-data/sync-status` - All sync progress
- GET `/api/v1/market-data/sync-status/{symbol}` - Per-symbol (composite, e.g. `BTCUSDT:BINANCE`)

**Status Tracking:**
- Pending (request received, awaiting processing)
- Syncing (fetch in progress)
- Completed (success with bar count)
- Error (with error message)

### F2: Real-time Quote Streaming

**Requirement:** Consume live price updates from Binance `@aggTrade` WebSocket and distribute to subscribers.

**Sub-requirements:**
- Maintain persistent WebSocket connection (singleton, app-wide), auto-started by the FastAPI lifespan
- Auto-reconnect with exponential backoff (1s to 60s)
- Subscribe/unsubscribe to specific symbols; `WsSubscriptionManager` reconciles vs `tracked_symbols` every 5s
- Cache latest quotes in Redis (~60s TTL)
- Re-subscribe after reconnection

**API Endpoints:**
- POST `/api/v1/quotes/subscribe` - Register symbol
- POST `/api/v1/quotes/unsubscribe` - Deregister symbol
- GET `/api/v1/quotes/latest/{symbol}` - Latest quote (composite symbol: `BTCUSDT:BINANCE`, URL-encoded `%3A`)
- GET `/api/v1/quotes/all` - All cached quotes
- GET `/api/v1/quotes/status` - Quote service status
- GET `/api/v1/quotes/stream/{symbol}` - SSE live quote stream

### F3: Multi-interval Bar Aggregation

**Requirement:** Aggregate real-time ticks into OHLCV bars at multiple timeframes simultaneously.

**Sub-requirements:**

- Build bars for all 7 intervals (1m, 5m, 15m, 1h, 4h, 1d, 1w) from single tick stream
- Atomic OHLC/V updates (no data corruption)
- Proper time alignment (midnight UTC for daily, epoch-aligned for intraday)
- Detect bar completion and auto-save to MongoDB
- Maintain in-progress bars in Redis (300s TTL)
- Flush incomplete bars on shutdown (no data loss)
- Concurrent tick processing with lock protection

**Data Flow:**
- Binance `@aggTrade` tick → QuoteAppService → BarAppService (bar aggregation) → MongoDB + Redis

### F4: Data Retrieval

**Requirement:** Query historical bar data with filtering and caching.

**Sub-requirements:**
- Retrieve bars by symbol, exchange, interval
- Support pagination (limit, offset)
- Sort by timestamp (descending)
- Cache queries (300s TTL)
- Invalidate cache after sync
- Support flexible time ranges

**API Endpoints:**
- GET `/api/v1/market-data/ohlcv/{symbol}/{interval}` - Bars with query params (composite symbol: `BTCUSDT:BINANCE`, URL-encoded `%3A`)

### F5: Symbol Registry

**Requirement:** Maintain list of tracked symbols.

**Sub-requirements:**
- Create, read, update, delete symbols
- Store metadata (exchange, name, description)
- List all tracked symbols
- Optional: Search implementation

**API Endpoints:**
- GET `/api/v1/market-data/symbols` - List symbols

### F6: Background Job Scheduling

**Requirement:** Automatically sync data on schedule with integrity verification.

**Sub-requirements:**
- Tiered sync by interval (5m, 15m, 1h, 4h, daily)
- Full backfill sync (5000 bars across all intervals)
- Daily integrity checks (bar alignment + gaps)
- Scheduled gap-fill repairs every 12h with verification
- Per-symbol error handling (don't break loop)
- Job execution history tracking (7-day TTL)

**Jobs (8 total):**
- sync_5m, sync_15m, sync_hourly, sync_swing, sync_daily — Per-interval syncs (varying bar counts: 30, 30, 10, 6, 7)
- sync_backfill (03:00 UTC) — Full backfill (5000 bars, all intervals)
- sync_integrity (04:00 UTC) — Check alignment + gaps (7 days back)
- sync_repair (every 12h) — Delete misaligned, resync gaps, verify still_missing

### F7: Strategy Engine

**Requirement:** Load and execute trading strategies with flexible broker abstraction.

**Sub-requirements:**
- Load strategy templates from the in-code `STRATEGY_REGISTRY` (e.g. `hitnrun2`)
- Support multiple strategy implementations via the `IStrategy` interface
- Route market data events to strategy handlers (`on_bar_completed`, `on_quote_received`, `on_order_filled`)
- Broker abstraction: paper trading + live trading support
- Position/order tracking from execution fills
- Risk checks before order submission

**API Endpoints:**
- GET `/api/v1/strategies` - List registered strategy templates
- POST `/api/v1/strategies/{strategy_code}/subscriptions` - Create a live subscription
- POST `/api/v1/subscriptions/{sub_id}/start` - Start strategy execution
- POST `/api/v1/subscriptions/{sub_id}/stop` - Stop strategy

### F8: Backtesting Engine

**Requirement:** Run historical backtests with parameter optimization.

**Sub-requirements:**
- Backtest runner with historical bar replay
- GridOptimizationAppService for parallel parameter searches
- Performance metrics (Sharpe, Sortino, max drawdown, win rate)
- Results storage in MongoDB
- Parameter optimization support

**API Endpoints:**
- POST `/api/v1/backtest/run` - Execute backtest
- POST `/api/v1/backtest/optimize` - Run parameter optimization
- GET `/api/v1/backtest/{run_id}` - Retrieve results

### F9: Order & Position Management

**Requirement:** Track orders and positions with MongoDB persistence.

**Sub-requirements:**
- Order lifecycle: pending → filled → closed
- Position tracking with entry/exit prices
- Profit/loss calculations
- P&L updates on fills
- MongoDB persistence for historical records

**API Endpoints:**
- GET `/api/v1/trading/orders` - List all orders
- GET `/api/v1/trading/orders/{order_id}` - Get one order
- GET `/api/v1/trading/positions` - List positions
- GET `/api/v1/trading/positions/{strategy_id}` - Positions by strategy

### F10: Live Trading (OKX)

**Requirement:** Execute live trades via OKX exchange.

**Sub-requirements:**
- OKX WebSocket connection with HMAC-SHA256 authentication
- Exponential backoff reconnection (1s → 30s max)
- Circuit breaker on failures (5-min pause after 10 failures)
- State reconciliation on reconnect
- Order submission and fill handling

**Configuration:**
- OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE environment variables

## Non-Functional Requirements

### NF1: Performance

**Response Time:**
- Historical sync: <5s for 5000 bars
- Quote cache lookup: <5ms
- Bar aggregation: <1ms per tick

**Throughput:**
- Concurrent syncs: 4 (thread pool limited)
- Quote subscriptions: 1000+ ticks/sec
- Database: 1000+ bars/sec upsert

**Memory:**
- MongoDB pool: ~10-20MB per connection
- Redis pool: <1MB
- Aggregator state: ~10MB per 10k subscriptions

### NF2: Reliability

**Availability:**
- 99.5% uptime target
- Auto-reconnect WebSocket
- Graceful error handling

**Data Integrity:**
- No duplicate OHLCV records (unique key constraint)
- Atomic bar building (asyncio.Lock)
- No data loss on shutdown (flush_all_bars)

**Error Recovery:**
- Transient errors: Exponential backoff retry
- Permanent errors: Update status, log, notify
- Job failures: Per-symbol isolation (don't break loop)

### NF3: Logging & Observability

**Logging:**
- All events logged as JSON (production-ready)
- Structured logging with context variables
- Compatible with: Datadog, Splunk, ELK, CloudWatch, Google Cloud, Loki
- Log levels: DEBUG, INFO, WARNING, ERROR

**Metrics (Monitored):**
- Sync success/failure rates
- WebSocket connection uptime
- Cache hit rates
- Database query latency
- Job execution time

### NF4: Security

**Configuration Management:**
- All secrets in environment variables (not committed)
- .env.example with dummy values
- No credentials in code or logs

**Data Protection:**
- Binance public market data needs no auth; OKX live trading uses API key/secret/passphrase (optional)
- MongoDB/Redis authentication via DSN
- CORS configuration available

### NF5: Maintainability

**Code Quality:**
- Max 200 LOC per file (exceptions documented)
- Type hints on all public APIs
- 80%+ test coverage
- Structured comments (WHY, not WHAT)
- Self-documenting code via naming

**Documentation:**
- API docs (OpenAPI/Swagger)
- Architecture guide
- Code standards guide
- Quick start guide

### NF6: Scalability

**Horizontal Scaling:**
- Multiple workers supported
- Shared MongoDB/Redis
- Each worker independent singletons
- Future: Distributed job scheduling

**Vertical Scaling:**
- Tunable connection pools
- Thread pool worker configuration
- Redis batch operations
- Bulk database upserts

## Architecture & Module Breakdown (Single Python package + web)

Dependency direction: `core ◁ engine ◁ backtest ◁ app`, `web → app` (HTTP only). Enforced by import-linter contracts in `pyproject.toml`.

```
src/pocketquant/
├── core/                 # 0 deps — domain + adapters
│   ├── domain/           TOP-LEVEL entities (bar, order, position, symbol, sync_status,
│   │                     backtest, subscription) + ports/DTOs (brokers, market_data)
│   ├── concepts/         non-persisted logic (quote, risk, strategy: IStrategy + hitnrun2)
│   ├── common/           AppError, EventBus, middleware, UUID7, health, structlog
│   ├── config/           Settings
│   ├── infra/
│   │   └── persistence/  Database (MongoDB), Cache (Redis), all 12 repositories
│   ├── brokers/paper/    PaperBroker (shared by backtest + paper trading)
│   ├── market_data/binance/  BinanceClient (REST) + BinanceWebSocketClient (@aggTrade)
│   ├── scheduling/       JobScheduler (APScheduler)
│   └── http_client/      ResilientHttpClient (retry/backoff)
│
├── engine/               # → core — shared market data services
│   └── market_data/      SyncService, OHLCVService, QuotesService, SyncStatusService,
│                         TrackedSymbolsService, SymbolsService
│
├── backtest/             # → core + engine — backtesting engine
│   ├── engine/           BacktestAppService, ResultCollector, HistoricalReplayAppService
│   ├── optimization/     GridOptimizationAppService, config models
│   ├── jobs/             BackgroundTask runners: run_subscription_backtest, etc.
│   ├── {feature}_command_service.py  Command service
│   ├── {feature}_query_service.py    Query service
│   └── domain/services/  PerformanceCalculator (NumPy metrics)
│
├── trading/              # → core + engine — strategy & trading logic
│   ├── brokers/okx/      OKXBroker + WebSocket support (auth, mappers, reconnection)
│   ├── domain/           Subscription aggregate (uuid7 ID, triple dedup via unique index)
│   ├── strategy_command_service.py   Write: add_symbol, start, stop, delete
│   ├── strategy_query_service.py     Read: list, get, positions, trades
│   ├── orders_positions_service.py   Live trading queries
│   └── app_services/     StrategyAppService, OrderAppService, PositionAppService,
│                         RiskCheckHandler (shared by backtest + trading)
│
└── app/                  # → core, engine, backtest — FastAPI runtime + all API routes + SPA
    ├── routes/           Feature modules: strategy.py, backtest.py, market_data_sync.py, etc.
    ├── market_data/      Sync/quotes/ohlcv/status app-services
    ├── middleware/       Admin auth, symbol validation, etc.
    ├── di/               Dishka container + 6 Provider classes
    └── main.py           FastAPI app + lifespan (indexes, scheduler, WS feed, SPA serve)

web/                                 # React 19 + Vite SPA (separate npm app)
├── Components: TradingChart, SymbolSelector, IntervalSelector, StrategySelector
├── Hooks: useOHLCV, useBacktest, useSymbols, use-realtime-bar, use-realtime-quote
└── Tech: React 19, Vite, TypeScript, TanStack Router/Query, Lightweight Charts
```

**Service + Route Pattern:** Each route calls a command/query service; service contains logic; exceptions handled globally. See [code-standards.md](./code-standards.md#routes--services) for naming and patterns.

## Success Criteria

### Version 1.0 (Complete)

**Core Features (F1-F6):**
- [x] Historical OHLCV sync from Binance
- [x] Real-time quote streaming via WebSocket
- [x] Multi-interval bar aggregation (1m, 5m, 15m, 1h, 4h, 1d, 1w)
- [x] MongoDB persistence with proper schema
- [x] Redis caching with TTL management
- [x] Background job scheduling

**Extended Features (F7-F10):**
- [x] Strategy Engine with YAML loader and IStrategy interface
- [x] Backtesting Engine with historical replay and GridOptimizationAppService
- [x] Order & Position Management with MongoDB persistence
- [x] Live Trading via OKX WebSocket (HMAC-SHA256, reconnection, circuit breaker)

**Infrastructure:**
- [x] Structured JSON logging (structlog)
- [x] Docker Compose infrastructure
- [x] REST API with OpenAPI docs
- [x] Graceful error handling
- [x] Type-safe codebase (pyright compliant)
- [x] 78%+ test coverage

### Validation Methods

- Unit tests (pytest)
- Integration tests (Docker + live services)
- Performance tests (load testing)
- Manual API testing (curl/Postman)
- Log analysis (structured logging verification)

## Known Limitations & TODOs

### Technical Debt

- [ ] Bulk sync parallelization (currently sequential per symbol)
- [ ] Symbol search/filtering implementation
- [ ] Configurable aggregator intervals post-initialization
- [ ] Persistent job storage (currently in-memory only)
- [ ] Automatic MongoDB/Redis reconnection
- [ ] Health check endpoint for infrastructure

### Testing Gaps

- [ ] Singleton mocking utilities for consistent testing
- [ ] End-to-end integration tests
- [ ] Performance/load testing
- [ ] Chaos engineering tests (connection failures)

### Documentation Gaps

- [ ] Algorithm explanation (QuoteAggregator time alignment)
- [ ] Troubleshooting guide
- [ ] Performance tuning guide
- [ ] Example strategy using the API

## Development Practices

### Branching Strategy

- `master` - Production-ready code
- `feature/*` - New features
- `bugfix/*` - Bug fixes
- `docs/*` - Documentation only

### Commit Messages

Follow conventional commits:
- `feat(scope): description` - New feature
- `fix(scope): description` - Bug fix
- `docs(scope): description` - Documentation
- `refactor(scope): description` - Code refactoring
- `test(scope): description` - Test improvements
- `style(scope): description` - Code style

### Code Review

- All PRs require at least 1 approval
- Tests must pass before merge
- Type checking (pyright) required
- Code coverage ≥80%

### Deployment

**Development:**
```bash
# 1. Install dependencies
uv sync

# 2. Start infrastructure (MongoDB + Redis)
docker compose -f deploy/compose.local.yml up -d

# 3. Run app (F5 in VS Code for debugging, or terminal)
uvicorn pocketquant.app.main:app --reload --port 41921
```

**Production:**
```bash
docker compose -f deploy/compose.prod.yml --env-file deploy/.env up -d
uv sync
uvicorn pocketquant.app.main:app --host 0.0.0.0 --port 41921
```

**Note:** Single worker only. Scheduler/WS/broker are in-process singletons; `--workers N` duplicates the reconcile loop and live broker connection.

## Contact & Support

- **Issues:** Report via GitHub Issues
- **Questions:** Refer to `./docs/` for detailed guides
- **Code Review:** Follow conventions in `CLAUDE.md`

## License

MIT License - See LICENSE file
