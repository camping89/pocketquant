# PocketQuant: Project Overview & Product Development Requirements

**Last Updated:** 2026-03-23 | **Status:** v1.0 Complete | **Codebase:** 278 Python files, 13,641 LOC in packages/ | **Architecture:** DDD + CQRS + Clean Architecture + Dishka | **Structure:** 4-package uv workspace monorepo | **Test Coverage:** 78%+ average

## Project Vision

PocketQuant is an algorithmic trading platform providing real-time market data synchronization, automated bar aggregation, and structured data storage for backtesting and forward testing workflows. The platform bridges TradingView data with MongoDB persistence, enabling traders and quants to build strategies on reliable, comprehensive market data.

## Product Goals

1. **Data Reliability:** Efficient historical bar sync from TradingView with MongoDB persistence
2. **Real-time Processing:** Live quote streaming with automatic aggregation into multiple timeframe bars
3. **Developer Experience:** Clean REST API with OpenAPI documentation, minimal setup friction
4. **Production Ready:** Structured logging, error handling, graceful degradation
5. **Extensibility:** DDD + CQRS architecture with vertical slice features and clean separation of concerns

## Functional Requirements

### F1: Historical Data Synchronization

**Requirement:** Fetch bar data from TradingView and persist to MongoDB.

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
- TradingView tick → QuoteAppService → QuoteAggregator → MongoDB + Redis

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
- GET `/api/v1/market-data/bar/{exchange}/{symbol}` - Bars with query params

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
| DDD Refactoring | ✅ Complete | N/A | Yes | 78%+ |
| Structured Logging | ✅ Complete | N/A | N/A | 100% |
| Docker Setup | ✅ Complete | N/A | N/A | N/A |

### Module Breakdown (Clean Architecture + DDD + CQRS)

```
packages/pocketquant-core/
├── domain/             (2,364 LOC, 39 files)
│   ├── Entities (6): Bar, Symbol, Order, Position, Backtest, SyncStatus
│   ├── Aggregates (2): OrderAggregate, PositionAggregate
│   ├── Value Objects, Events, Services (pure logic, zero I/O)
│   └── MongoDB Persistence: `to_mongo()`/`from_mongo()` methods
├── common/             (993 LOC, 32 files)
│   ├── Mediator & EventBus, CQRS/Event handler auto-discovery
│   ├── UUID Utilities (UUID7), DI Container Integration
│   └── Middleware, Logging (structlog), Health Checks
├── infrastructure/     (2,883 LOC, 28 files)
│   ├── Brokers (IBroker, PaperBroker, OKXBroker)
│   ├── Data Providers (TradingView REST/WebSocket)
│   ├── OKX WebSocket with HMAC-SHA256 auth
│   ├── Job Scheduling (APScheduler)
│   └── HTTP Client & Webhooks
└── persistence/        (1,214 LOC, 18 files)
    ├── Database (MongoDB, PyMongo async)
    ├── Cache (Redis async)
    └── Repositories (7): Bar, Order, Position, Backtest, Optimization, Symbol, SyncStatus

packages/pocketquant-backtest/
├── engine/
│   ├── BacktestAppService (execute strategy on historical bars)
│   ├── GridOptimizationAppService (parameter search)
│   └── HistoricalReplayAppService (bar injection)
├── domain/
│   └── BacktestResult, OptimizationResult entities
└── persistence/
    └── BacktestRepository, OptimizationRepository

packages/pocketquant-trading/
├── app_services/
│   ├── OrderAppService (order state machine + recovery)
│   └── PositionAppService (P&L calculation)
├── brokers/
│   └── OKX broker implementation (live trading)
└── persistence/
    └── Order/Position repositories

packages/pocketquant-api/        (3,016 LOC, 134 files)
├── features/           - Operation-First Vertical Slices
│   ├── backtesting/    - Run, optimize, retrieve backtests
│   ├── market_data/    - Sync, bar queries, quotes, symbols
│   ├── strategy/       - Load, start, stop strategies
│   ├── trading/        - Orders, positions
│   └── risk/           - Risk checks
├── di/                 - Dishka dependency injection
│   ├── container.py    - Factory + handler registration
│   └── 6 Provider classes
└── main.py            - FastAPI app + lifespan setup

**Total: 13,641 LOC (278 Python files)**
- pocketquant-core: 97 files, 5,609 LOC
- pocketquant-backtest: 40 files
- pocketquant-trading: 65 files
- pocketquant-api: 86 files, ~2,738 LOC
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
# 1. Install dependencies (uv workspace)
uv sync

# 2. Start infrastructure (MongoDB + Redis)
docker compose -f docker/compose.yml up -d

# 3. Run app (F5 in VS Code for debugging, or terminal)
uvicorn pocketquant.api.main:app --reload --port 41920
```

**Production:**
```bash
docker compose -f docker/compose.yml up -d
uv sync
uvicorn pocketquant.api.main:app --host 0.0.0.0 --port 41920 --workers 4
```

## Contact & Support

- **Issues:** Report via GitHub Issues
- **Questions:** Refer to `./docs/` for detailed guides
- **Code Review:** Follow conventions in `CLAUDE.md`

## License

MIT License - See LICENSE file
