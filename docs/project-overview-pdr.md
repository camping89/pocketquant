# PocketQuant: Project Overview & Product Development Requirements

**Last Updated:** 2026-02-21 | **Status:** v1.0 Complete | **Codebase:** 277 Python files, 13,641 LOC in src/ | **Architecture:** DDD + CQRS + Clean Architecture + IoC Container | **Test Coverage:** 78%+ average

## Project Vision

PocketQuant is an algorithmic trading platform providing real-time market data synchronization, automated bar aggregation, and structured data storage for backtesting and forward testing workflows. The platform bridges TradingView data with MongoDB persistence, enabling traders and quants to build strategies on reliable, comprehensive market data.

## Product Goals

1. **Data Reliability:** Efficient historical OHLCV sync from TradingView with MongoDB persistence
2. **Real-time Processing:** Live quote streaming with automatic aggregation into multiple timeframe bars
3. **Developer Experience:** Clean REST API with OpenAPI documentation, minimal setup friction
4. **Production Ready:** Structured logging, error handling, graceful degradation
5. **Extensibility:** Vertical slice architecture for adding new data sources and features

## Functional Requirements

### F1: Historical Data Synchronization

**Requirement:** Fetch OHLCV data from TradingView and persist to MongoDB.

**Sub-requirements:**
- Sync single symbol with configurable interval and bar count
- Bulk sync multiple symbols in single operation
- Background/async sync without blocking client
- Track sync progress and status
- Prevent duplicate data via upsert operations
- Support 13 standard intervals (1m to 1M)
- Enforce 5000 bar maximum per fetch (TradingView limit)

**API Endpoints:**
- POST `/api/v1/market-data/sync` - Single symbol (blocking)
- POST `/api/v1/market-data/sync/background` - Async sync
- POST `/api/v1/market-data/sync/bulk` - Multiple symbols
- GET `/api/v1/market-data/sync-status` - Sync progress

**Status Tracking:**
- Pending (request received, awaiting processing)
- Syncing (fetch in progress)
- Completed (success with bar count)
- Error (with error message)

### F2: Real-time Quote Streaming

**Requirement:** Consume live price updates from TradingView WebSocket and distribute to subscribers.

**Sub-requirements:**
- Maintain persistent WebSocket connection
- Auto-reconnect with exponential backoff (1s to 60s)
- Subscribe/unsubscribe to specific symbols
- Cache latest quotes in Redis (60s TTL)
- Log all quote events for audit trail
- Handle binary protocol (TradingView custom format)
- Re-subscribe after reconnection

**API Endpoints:**
- POST `/api/v1/quotes/start` - Start WebSocket
- POST `/api/v1/quotes/stop` - Stop WebSocket
- POST `/api/v1/quotes/subscribe` - Register symbol
- POST `/api/v1/quotes/unsubscribe` - Deregister symbol
- GET `/api/v1/quotes/status` - Connection status
- GET `/api/v1/quotes/latest/{exchange}/{symbol}` - Latest quote
- GET `/api/v1/quotes/all` - All cached quotes

### F3: Multi-interval Bar Aggregation

**Requirement:** Aggregate real-time ticks into OHLCV bars at multiple timeframes simultaneously.

**Sub-requirements:**
- Build bars for all 13 intervals (1m to 1M) from single tick stream
- Atomic OHLC/V updates (no data corruption)
- Proper time alignment (midnight UTC for daily, epoch-aligned for intraday)
- Detect bar completion and auto-save to MongoDB
- Maintain in-progress bars in Redis (300s TTL)
- Flush incomplete bars on shutdown (no data loss)
- Concurrent tick processing with lock protection

**Data Flow:**
- TradingView tick → QuoteService → QuoteAggregator → MongoDB + Redis

### F4: Data Retrieval

**Requirement:** Query historical OHLCV data with filtering and caching.

**Sub-requirements:**
- Retrieve bars by symbol, exchange, interval
- Support pagination (limit, offset)
- Sort by timestamp (descending)
- Cache queries (300s TTL)
- Invalidate cache after sync
- Support flexible time ranges

**API Endpoints:**
- GET `/api/v1/market-data/ohlcv/{exchange}/{symbol}` - Bars with query params

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

**Requirement:** Automatically sync data on schedule.

**Sub-requirements:**
- Periodic sync all symbols (6 hours)
- Market hours sync for daily data (hourly, Mon-Fri 9-17 UTC)
- Per-symbol error handling (don't break loop)
- Status tracking for each job execution
- Graceful shutdown (wait for jobs to complete)

**Jobs:**
- sync_all_symbols: Every 6 hours (500 bars per symbol)
- sync_daily_data: Hourly Mon-Fri 9-17 UTC (10 bars, daily only)

### F7: Strategy Engine

**Requirement:** Load and execute trading strategies with flexible broker abstraction.

**Sub-requirements:**
- Load strategies from YAML configuration files
- Support multiple strategy implementations (MA crossover, etc.)
- Route market data events to strategy handlers (on_bar, on_tick, on_fill)
- Broker abstraction: paper trading + live trading support
- Position/order tracking from execution fills
- Risk checks before order submission

**API Endpoints:**
- GET `/api/v1/strategies` - List available strategies
- POST `/api/v1/strategies/load` - Load strategy by name
- POST `/api/v1/strategies/start` - Start strategy execution
- POST `/api/v1/strategies/stop` - Stop strategy

### F8: Backtesting Engine

**Requirement:** Run historical backtests with parameter optimization.

**Sub-requirements:**
- Backtest runner with historical bar replay
- GridOptimizer for parallel parameter searches
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
- GET `/api/v1/orders` - List all orders
- GET `/api/v1/positions` - List open positions
- POST `/api/v1/orders/{order_id}/cancel` - Cancel order

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
- Optional TradingView authentication
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

## Current Implementation Status

### Implemented (Core & Extended)

| Feature | Status | API Complete | Tests | Coverage |
|---------|--------|--------------|-------|----------|
| Historical Sync (F1) | ✅ Complete | Yes | Yes | 80%+ |
| Real-time Quotes (F2) | ✅ Complete | Yes | Yes | 75%+ |
| Bar Aggregation (F3) | ✅ Complete | Yes | Yes | 85%+ |
| Data Retrieval (F4) | ✅ Complete | Yes | Yes | 80%+ |
| Symbol Registry (F5) | ✅ Complete | Yes | Partial | 70% |
| Background Jobs (F6) | ✅ Complete | Yes | Yes | 75%+ |
| Strategy Engine (F7) | ✅ Complete | Yes | Yes | 80%+ |
| Backtesting (F8) | ✅ Complete | Yes | Yes | 78%+ |
| Order/Position Mgmt (F9) | ✅ Complete | Yes | Yes | 82%+ |
| Live Trading/OKX (F10) | ✅ Complete | Yes | Yes | 76%+ |
| Structured Logging | ✅ Complete | N/A | N/A | 100% |
| Docker Setup | ✅ Complete | N/A | N/A | N/A |

### Module Breakdown (Clean Architecture + DDD + CQRS)

```
src/common/             (993 LOC, 32 files)
├── Mediator & EventBus - CQRS dispatcher & event pub/sub (max 100 event history)
├── Event Handler Auto-Discovery (@event_handler, EventRegistry)
├── CQRS Handler Auto-Discovery (@handles decorator, HandlerRegistry)
├── UUID Utilities (UUID7 generation - time-ordered IDs)
├── DI Container Integration - dependency-injector setup
├── Middleware (correlation ID, rate limit, idempotency)
├── Logging (structlog) - Structured JSON logs
├── Health Coordinator - Infrastructure health checks
└── Job Scheduler (APScheduler)

src/domain/             (2,364 LOC, 39 files)
├── Aggregates: OHLCV, Order, Position, Quote, Symbol, Risk (all with UUID7)
├── Value Objects: Price, Signal, BarRange, PnL, SymbolInfo, etc.
├── Domain Events (13+ event types: OrderSubmitted, BarCompleted, etc.)
├── Domain Services: BarBuilder, PositionSizer (pure logic, zero I/O)
├── Enums: OrderType, OrderStatus, OrderSide, Direction, Interval, etc.
└── Immutable frozen dataclasses with validation in __post_init__

src/application/        (2,559 LOC, 21 files)
├── Orchestrators: StrategyEngine, BacktestRunner, BarManager
├── Order Management: OrderManager (state machine + recovery)
├── Position Management: PositionTracker (P&L calculation)
├── Market Data: QuoteService, HistoricalReplayEngine
├── Optimization: GridOptimizer (parameter search)
├── Strategy: StrategyLoader (YAML → IStrategy)
└── Result Collectors: ResultCollector (metrics aggregation)

src/infrastructure/     (2,883 LOC, 28 files)
├── Brokers: IBroker interface, PaperBroker, OKXBroker, BrokerFactory
├── OKX WebSocket: Client, ReconnectionHandler, Mappers, Auth (HMAC-SHA256)
├── TradingView: REST Provider (tvdatafeed), WebSocket Provider
├── Scheduling: JobScheduler (APScheduler wrapper)
├── HTTP & Webhooks: AsyncHTTPClient, WebhookDispatcher
└── (Database & Cache moved to src/persistence/)

src/persistence/        (1,214 LOC, 18 files)
├── Database: MongoDB async client (PyMongo native async API)
├── Cache: Redis async client (redis-py)
├── BaseRepository: Mixin with _collection() helper
├── Repositories (7): OHLCV, Order, Position, Backtest, Optimization, Symbol, SyncStatus
└── MongoDB Schemas: Document validation

src/features/           (3,016 LOC, 134 files) - Operation-First Vertical Slices
├── backtesting/        (626 LOC, 22 files)
│   ├── run/ optimize/ get_result/ get_optimization/ list_results/
├── market_data/        (1,534 LOC, 68 files)
│   ├── sync/sync_one/ sync/sync_bulk/ ohlcv/get_ohlcv/ quotes/
│   ├── status/ list_symbols/
├── strategy/           (416 LOC, 22 files)
│   ├── get_all/ get_one/ load/ start/ stop/
├── trading/            (281 LOC, 18 files)
│   ├── list_orders/ get_order/ list_positions/ get_position/
└── risk/               (158 LOC, 3 files)
    └── check_risk/

tests/                  (902 LOC, 17 files)
docker/                 (401 LOC, 5 files)

Total: 13,641 LOC (277 Python files in src/)
```

**Operation-First Pattern:** Each feature contains self-contained operations (folders). Each operation is a complete use case: command/query definition, handler logic, optional route. Shared infrastructure within a feature is in base/.

## Success Criteria

### Version 1.0 (Complete)

**Core Features (F1-F6):**
- [x] Historical OHLCV sync from TradingView
- [x] Real-time quote streaming via WebSocket
- [x] Multi-interval bar aggregation (1m to 1M)
- [x] MongoDB persistence with proper schema
- [x] Redis caching with TTL management
- [x] Background job scheduling

**Extended Features (F7-F10):**
- [x] Strategy Engine with YAML loader and IStrategy interface
- [x] Backtesting Engine with historical replay and GridOptimizer
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
- [ ] Rate limiting on TradingView requests
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

## Roadmap (Future Phases)

### Phase 2: Extended Data Sources

- Alternative data providers (Binance, Kraken, IEX)
- Fundamental data (earnings, dividends, splits)
- Sentiment data integration
- News feed integration

### Phase 3: Backtesting Engine

- Strategy runner with historical replay
- Performance metrics (Sharpe, max drawdown, etc.)
- Parameter optimization
- Risk analysis tools

### Phase 4: Live Trading

- Paper trading simulator
- Broker integrations (Alpaca, Interactive Brokers)
- Order management
- Portfolio tracking

### Phase 5: Analytics & Visualization

- Web dashboard
- Chart rendering
- Performance analytics
- Risk dashboards

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
just start  # Start all services + app
```

**Production:**
```bash
docker compose -f docker/compose.yml up -d
python -m src.main  # Config via .env (API_PORT, MONGODB_URL, etc.)
```

## Contact & Support

- **Issues:** Report via GitHub Issues
- **Questions:** Refer to `./docs/` for detailed guides
- **Code Review:** Follow conventions in `CLAUDE.md`

## License

MIT License - See LICENSE file
