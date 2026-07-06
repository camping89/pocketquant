# PocketQuant: Project Overview & Product Development Requirements

Kiến trúc: DDD + CQRS + Clean Architecture + Dishka. Cấu trúc: một Python package `src/pocketquant/` + `web/` là một npm app riêng biệt.

Khám phá kiến trúc, code pattern và quy ước trong `./docs/` — xem [system-architecture.md](./system-architecture.md), [code-standards.md](./code-standards.md), [README.md](../../README.md).

## Project Vision

PocketQuant là một nền tảng algorithmic trading cung cấp đồng bộ dữ liệu thị trường real-time, tự động aggregate bar và lưu trữ dữ liệu có cấu trúc cho các workflow backtesting và forward testing. Nền tảng bắc cầu giữa dữ liệu thị trường công khai của Binance và persistence trên MongoDB, cho phép trader và quant xây dựng chiến lược trên dữ liệu thị trường đáng tin cậy, toàn diện.

## Product Goals

1. **Data Reliability:** Đồng bộ bar lịch sử hiệu quả từ Binance với persistence trên MongoDB
2. **Real-time Processing:** Live quote streaming với tự động aggregate thành bar ở nhiều timeframe
3. **Developer Experience:** REST API sạch với tài liệu OpenAPI, tối thiểu ma sát khi setup
4. **Production Ready:** Structured logging, xử lý lỗi, graceful degradation
5. **Extensibility:** Kiến trúc DDD + CQRS với vertical slice feature và tách bạch mối quan tâm rõ ràng

## Functional Requirements

### F1: Historical Data Synchronization

**Requirement:** Fetch dữ liệu bar từ Binance public REST và persist vào MongoDB.

**Sub-requirements:**
- Sync một symbol với interval và số lượng bar tùy chỉnh
- Bulk sync nhiều symbol trong một thao tác duy nhất
- Sync background/async không block client
- Theo dõi tiến trình và trạng thái sync
- Ngăn dữ liệu trùng lặp qua thao tác upsert
- Hỗ trợ 7 interval chuẩn (1m, 5m, 15m, 1h, 4h, 1d, 1w)
- Tự động phân trang khi `n_bars > 1000` (Binance trả về tối đa 1000 bar/call, budget 1200 weight/min)

**API Endpoints:**
- POST `/api/v1/market-data/sync` - Single symbol
- POST `/api/v1/market-data/sync/background` - Async single symbol
- POST `/api/v1/market-data/sync/bulk` - Multiple symbols
- GET `/api/v1/market-data/sync-status` - All sync progress
- GET `/api/v1/market-data/sync-status/{symbol}` - Per-symbol (composite, e.g. `BTCUSDT:BINANCE`)

**Status Tracking:**
- Pending (đã nhận request, chờ xử lý)
- Syncing (đang fetch)
- Completed (thành công với số lượng bar)
- Error (kèm thông báo lỗi)

### F2: Real-time Quote Streaming

**Requirement:** Tiêu thụ live price update từ Binance `@aggTrade` WebSocket và phân phối tới các subscriber.

**Sub-requirements:**
- Duy trì kết nối WebSocket persistent (singleton, app-wide), tự động khởi động bởi FastAPI lifespan
- Auto-reconnect với exponential backoff (1s tới 60s)
- Subscribe/unsubscribe tới symbol cụ thể; `WsSubscriptionAppService` reconcile so với `tracked_symbols` mỗi 5s
- Cache quote mới nhất trong Redis (~60s TTL)
- Re-subscribe sau khi reconnect

**API Endpoints:**
- POST `/api/v1/quotes/subscribe` - Register symbol
- POST `/api/v1/quotes/unsubscribe` - Deregister symbol
- GET `/api/v1/quotes/latest/{symbol}` - Latest quote (composite symbol: `BTCUSDT:BINANCE`, URL-encoded `%3A`)
- GET `/api/v1/quotes/all` - All cached quotes
- GET `/api/v1/quotes/status` - Quote service status
- GET `/api/v1/quotes/stream/{symbol}` - SSE live quote stream

### F3: Multi-interval Bar Aggregation

**Requirement:** Aggregate tick real-time thành bar OHLCV ở nhiều timeframe đồng thời.

**Sub-requirements:**

- Build bar cho cả 7 interval (1m, 5m, 15m, 1h, 4h, 1d, 1w) từ một tick stream duy nhất
- Cập nhật OHLC/V atomic (không hỏng dữ liệu)
- Căn thời gian chính xác (midnight UTC cho daily, epoch-aligned cho intraday)
- Phát hiện bar hoàn thành và tự động save vào MongoDB
- Duy trì bar in-progress trong Redis (300s TTL)
- Flush bar chưa hoàn thành khi shutdown (không mất dữ liệu)
- Xử lý tick đồng thời với lock protection

**Data Flow:**
- Binance `@aggTrade` tick → QuoteAppService → BarAppService (bar aggregation) → MongoDB + Redis

### F4: Data Retrieval

**Requirement:** Query dữ liệu bar lịch sử với filtering và caching.

**Sub-requirements:**
- Truy xuất bar theo symbol, exchange, interval
- Hỗ trợ phân trang (limit, offset)
- Sort theo timestamp (giảm dần)
- Cache query (300s TTL)
- Invalidate cache sau khi sync
- Hỗ trợ time range linh hoạt

**API Endpoints:**
- GET `/api/v1/market-data/ohlcv/{symbol}/{interval}` - Bars with query params (composite symbol: `BTCUSDT:BINANCE`, URL-encoded `%3A`)

### F5: Symbol Registry

**Requirement:** Duy trì danh sách các symbol được theo dõi.

**Sub-requirements:**
- Create, read, update, delete symbol
- Lưu metadata (exchange, name, description)
- List tất cả symbol được theo dõi
- Optional: Triển khai Search

**API Endpoints:**
- GET `/api/v1/market-data/symbols` - List symbols

### F6: Background Job Scheduling

**Requirement:** Tự động sync dữ liệu theo lịch với kiểm tra tính toàn vẹn.

**Sub-requirements:**
- Sync phân tầng theo interval (5m, 15m, 1h, 4h, daily)
- Full backfill sync (5000 bar trên tất cả interval)
- Kiểm tra tính toàn vẹn hàng ngày (bar alignment + gap)
- Sửa chữa gap-fill theo lịch mỗi 12h kèm verification
- Xử lý lỗi per-symbol (không phá vỡ loop)
- Theo dõi lịch sử thực thi job (7-day TTL)

**Jobs (8 total):**
- sync_5m, sync_15m, sync_hourly, sync_swing, sync_daily — Per-interval syncs (varying bar counts: 30, 30, 10, 6, 7)
- sync_backfill (03:00 UTC) — Full backfill (5000 bars, all intervals)
- sync_integrity (04:00 UTC) — Check alignment + gaps (7 days back)
- sync_repair (every 12h) — Delete misaligned, resync gaps, verify still_missing

### F7: Strategy Engine

**Requirement:** Load và thực thi chiến lược trading với broker abstraction linh hoạt.

**Sub-requirements:**
- Load strategy template từ `STRATEGY_REGISTRY` in-code (e.g. `hitnrun2`)
- Hỗ trợ nhiều triển khai chiến lược qua interface `IStrategyService`
- Route event dữ liệu thị trường tới các strategy handler (`on_bar_completed`, `on_quote_received`, `on_order_filled`)
- Broker abstraction: hỗ trợ paper trading + live trading
- Theo dõi position/order từ execution fill
- Risk check trước khi submit order

**API Endpoints:**
- GET `/api/v1/strategies` - List registered strategy templates
- POST `/api/v1/strategies/{strategy_code}/subscriptions` - Create a live subscription
- POST `/api/v1/subscriptions/{sub_id}/start` - Start strategy execution
- POST `/api/v1/subscriptions/{sub_id}/stop` - Stop strategy

### F8: Backtesting Engine

**Requirement:** Chạy backtest đơn ad-hoc với replay bar lịch sử.

**Sub-requirements:**
- Backtest single-run qua in-process async task (không queue): save doc `started` → spawn engine → persist `finished`/`failed`
- Cô lập sandbox per-run khỏi live engine
- Performance metrics (Sharpe, Sortino, max drawdown, win rate)
- Lưu kết quả trong MongoDB (runs + orders + trades, chia sẻ chung một run_id)

**API Endpoints:**
- POST `/api/v1/backtest/run` - Start a backtest (202, returns run_id)
- GET `/api/v1/backtest/{run_id}` - Poll status + result
- GET `/api/v1/backtest/{run_id}/equity` - Equity curve
- GET `/api/v1/backtest/{run_id}/trades` - Closed trades

### F9: Order & Position Management

**Requirement:** Theo dõi order và position với persistence trên MongoDB.

**Sub-requirements:**
- Order lifecycle: pending → filled → closed
- Position tracking với giá entry/exit
- Tính toán profit/loss
- Cập nhật P&L khi fill
- Persistence trên MongoDB cho bản ghi lịch sử

**API Endpoints:**
- GET `/api/v1/trading/orders` - List all orders
- GET `/api/v1/trading/orders/{order_id}` - Get one order
- GET `/api/v1/trading/positions` - List positions
- GET `/api/v1/trading/positions/{strategy_id}` - Positions by strategy

### F10: Live Trading (OKX)

**Requirement:** Thực thi live trade qua sàn OKX.

**Sub-requirements:**
- Kết nối OKX WebSocket với authentication HMAC-SHA256
- Reconnection với exponential backoff (1s → 30s max)
- Circuit breaker khi lỗi (pause 5 phút sau 10 lần lỗi)
- Reconcile state khi reconnect
- Submit order và xử lý fill

**Configuration:**
- OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE environment variables

## Non-Functional Requirements

### NF1: Performance

**Response Time:**
- Historical sync: <5s cho 5000 bar
- Quote cache lookup: <5ms
- Bar aggregation: <1ms mỗi tick

**Throughput:**
- Concurrent syncs: 4 (giới hạn bởi thread pool)
- Quote subscriptions: 1000+ tick/sec
- Database: 1000+ bar/sec upsert

**Memory:**
- MongoDB pool: ~10-20MB mỗi connection
- Redis pool: <1MB
- Aggregator state: ~10MB mỗi 10k subscription

### NF2: Reliability

**Availability:**
- Mục tiêu uptime 99.5%
- Auto-reconnect WebSocket
- Graceful error handling

**Data Integrity:**
- Không có bản ghi OHLCV trùng lặp (unique key constraint)
- Bar building atomic (asyncio.Lock)
- Không mất dữ liệu khi shutdown (flush_all_bars)

**Error Recovery:**
- Lỗi transient: Exponential backoff retry
- Lỗi permanent: Cập nhật status, log, notify
- Job failures: Cô lập per-symbol (không phá vỡ loop)

### NF3: Logging & Observability

**Logging:**
- Tất cả event log dưới dạng JSON (production-ready)
- Structured logging với context variables
- Tương thích với: Datadog, Splunk, ELK, CloudWatch, Google Cloud, Loki
- Log levels: DEBUG, INFO, WARNING, ERROR

**Metrics (Monitored):**
- Tỉ lệ sync success/failure
- WebSocket connection uptime
- Cache hit rate
- Database query latency
- Job execution time

### NF4: Security

**Configuration Management:**
- Tất cả secret trong environment variables (không commit)
- .env.example với giá trị dummy
- Không credential trong code hoặc log

**Data Protection:**
- Dữ liệu thị trường công khai của Binance không cần auth; live trading OKX dùng API key/secret/passphrase (optional)
- Authentication MongoDB/Redis qua DSN
- Có sẵn cấu hình CORS

### NF5: Maintainability

**Code Quality:**
- Tối đa 200 LOC mỗi file (ngoại lệ được ghi tài liệu)
- Type hint trên tất cả public API
- 80%+ test coverage
- Structured comment (WHY, không phải WHAT)
- Code tự tài liệu hóa qua naming

**Documentation:**
- API docs (OpenAPI/Swagger)
- Architecture guide
- Code standards guide
- Quick start guide

### NF6: Scalability

**Horizontal Scaling:**
- Hỗ trợ nhiều worker
- Shared MongoDB/Redis
- Mỗi worker có singleton độc lập
- Future: Distributed job scheduling

**Vertical Scaling:**
- Connection pool có thể điều chỉnh
- Cấu hình worker thread pool
- Redis batch operation
- Bulk database upsert

## Architecture & Module Breakdown (Single Python package + web)

Hướng phụ thuộc: `core ◁ engine ◁ app`, `web → app` (HTTP only). Backtest và live là hai driver trên một engine chia sẻ. Được thực thi bởi import-linter contract trong `pyproject.toml` (8 contract).

```
src/pocketquant/
├── core/                 # 0 deps — domain + adapters
│   ├── domain/           TOP-LEVEL entities (bar, order, position, symbol, sync_status,
│   │                     backtest, subscription, tracked_symbol) + ports/DTOs (brokers, market_data)
│   ├── domain/trading/   Value objects (Trade, Fill, EquityPoint, PerformanceMetrics) +
│   │                     PerformanceCalculatorDomainService + trade_stats functions
│   ├── domain/{quote,risk,strategy}/  non-persisted logic (risk: PositionCalculatorDomainService +
│   │                     PositionCalculation VO; strategy: IStrategyService + HitNRun2/Engulfing)
│   ├── common/           AppError, EventBus, middleware, UUID7, health, structlog
│   ├── config.py         Settings
│   └── infra/            All external I/O adapters
│       ├── persistence/  Database (MongoDB), Cache (Redis), all 12 repositories
│       ├── brokers/      PaperBrokerAdapter, OKXBrokerAdapter (+WS auth/mappers/reconnection), broker_factory.py
│       ├── binance/      BinanceAdapter (REST) + BinanceWebSocketAdapter (@aggTrade)
│       ├── scheduling/   JobScheduler (APScheduler)
│       └── http_client/  ResilientHttpClient (retry/backoff)
│
├── engine/               # → core — shared engine with 5 feature areas
│   ├── strategy/         strategy_app_service, strategy_command_service, strategy_query_service
│   ├── execution/        order_app_service, position_app_service, orders_positions_service, risk_check
│   ├── market_data/      sync/ohlcv/quotes/status services + app_services/ (bar, quote, ws-subscription, jobs)
│   ├── backtest/         backtest driver (isolated per run)
│   │   ├── backtest_app_service.py
│   │   ├── backtest_sandbox_app_service.py
│   │   ├── backtest_command_service.py
│   │   ├── backtest_query_service.py
│   │   ├── backtest_stats_service.py
│   │   ├── backtest_execution_service.py
│   │   ├── backtest_report_app_service.py
│   │   ├── historical_replay_app_service.py
│   │   ├── collected_results.py
│   │   ├── backtest_dispatch.py
│   │   └── backtest_strategy_loader.py
│   └── live/             Live trading driver
│       ├── strategy_reconcile_app_service.py  (reconcile loop, 5s poll + bootstrap)
│       ├── live_trade_collector.py            (EventBus subscriber → persist trades)
│       └── live_metrics_query_service.py      (on-demand per-subscription metrics)
│
└── app/                  # → core, engine — FastAPI runtime + all API routes + SPA
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

**Service + Route Pattern:** Mỗi route gọi một command/query service; service chứa logic; exception được xử lý globally. Xem [code-standards.md](./code-standards.md#routes--services) cho naming và pattern.

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
- [x] Strategy Engine with YAML loader and IStrategyService interface
- [x] Backtesting Engine with historical replay (single-run direct-task)
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

- Unit test (pytest)
- Integration test (Docker + live services)
- Performance test (load testing)
- Manual API testing (curl/Postman)
- Log analysis (kiểm chứng structured logging)

## Known Limitations & TODOs

### Technical Debt

- [ ] Bulk sync parallelization (hiện tuần tự per symbol)
- [ ] Triển khai symbol search/filtering
- [ ] Aggregator interval có thể cấu hình post-initialization
- [ ] Persistent job storage (hiện chỉ in-memory)
- [ ] Tự động reconnect MongoDB/Redis
- [ ] Health check endpoint cho infrastructure

### Testing Gaps

- [ ] Singleton mocking utilities cho testing nhất quán
- [ ] End-to-end integration test
- [ ] Performance/load testing
- [ ] Chaos engineering test (connection failures)

### Documentation Gaps

- [ ] Giải thích thuật toán (QuoteAggregator time alignment)
- [ ] Troubleshooting guide
- [ ] Performance tuning guide
- [ ] Chiến lược ví dụ dùng API

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

- Tất cả PR yêu cầu ít nhất 1 approval
- Test phải pass trước khi merge
- Yêu cầu type checking (pyright)
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

- **Issues:** Report qua GitHub Issues
- **Questions:** Tham khảo `./docs/` cho hướng dẫn chi tiết
- **Code Review:** Tuân theo quy ước trong `CLAUDE.md`

## License

MIT License - See LICENSE file
