# PocketQuant TODO

## Debugging Starting Point

**Entry endpoint:** `POST /api/v1/market-data/sync` — simplest write path, touches every layer

### Request Flow to Trace
```
sync/sync_one/route.py:18 → SyncSymbolCommand → mediator.send()
  → mediator.py:22 → looks up handler by type(request)
    → sync/sync_one/handler.py → SyncSymbolHandler.handle()
      → TradingViewProvider.fetch_ohlcv() → DB insert → EventBus.publish()
```

### Key Files for Breakpoints
| File                                                 | Why                               |
|------------------------------------------------------|-----------------------------------|
| `src/features/market_data/sync/sync_one/route.py:18` | Request entry                     |
| `src/common/mediator/mediator.py:22`                 | Dispatcher (type→handler mapping) |
| `src/features/market_data/sync/sync_one/handler.py`  | Core business logic               |
| `src/common/messaging/event_bus.py:37`               | Event publish                     |
| `src/main.py` (lifespan)                             | Wiring at startup                 |

### Exercise Progression (from learning guide)
- [ ] **Ex 1** (30min): Trace sync request flow, answer: where is command created? how does mediator find handler? what events published? who receives them?
- [ ] **Ex 2** (1hr): Create `GetSymbolStatsQuery` handler (reinforces CQRS)
- [ ] **Ex 3** (45min): Add event subscriber for `HistoricalDataSyncedEvent` (reinforces decoupling)
- [ ] **Ex 4** (1hr): Write tests with mocked singletons (reinforces pytest)

### After Sync, Try Read Path
`GET /api/v1/market-data/ohlcv/NASDAQ/AAPL` — no events, just query→handler→MongoDB

### Learning Materials
- `plans/reports/brainstorm-260201-1223-python-learning-guide.md` — main guide (C# → Python)
- `docs/learning/python-asyncio-guide.md` — coroutines, event loop, locks
- `docs/learning/python-event-patterns-guide.md` — Observer, EventBus, domain events
- `docs/learning/uuid-versions-guide.md` — UUID7 time-ordered IDs

### How to Start
1. `just start` (spins up MongoDB, Redis, app)
2. Open Swagger UI: `http://localhost:8765/api/v1/docs`
3. Hit POST `/sync` with `{"symbol": "AAPL", "exchange": "NASDAQ", "interval": "1d", "n_bars": 500}`
4. Step through with debugger or add log statements at each layer

---

## Next Steps

### 1. Learn Python from this project
- [ ] Follow learning plan: `plans/260201-1223-python-learning-plan-csharp-developer/`
- [ ] Week 1: Read & understand patterns (CQRS, Mediator, EventBus)
- [ ] Week 2: Small modifications
- [ ] Week 3: Create new features
- [ ] Week 4: Testing mastery

### 2. Test with real accounts
- [ ] Configure TradingView credentials in `.env`
- [ ] Test real-time quotes with TradingView WebSocket
- [ ] Configure OKX API credentials (API key, secret, passphrase)
- [ ] Test OKX paper trading (demo mode)
- [ ] Test OKX live trading (small amounts)

---

## Pending Plans

| Plan                                             | Priority | Description                             |
|--------------------------------------------------|----------|-----------------------------------------|
| `260108-1144-trading-features`                   | P1       | Backtesting, Portfolio, Risk Management |
| `260108-1144-vps-deployment`                     | P1       | Deploy to Vultr Singapore               |
| `260131-2006-okx-websocket-backtest-integration` | P1       | Backtest engine + OKX WebSocket         |
| `260128-1529-job-feature-flag`                   | P3       | Enable/disable background jobs          |

---

## Completed (removed from plans/)
- Strategy Engine Architecture
- DDD + Vertical Slice Refactor
- MongoDB Persistence (Orders/Positions)
- PyMongo Async Migration
- Pyright Type Checking
- Event Handler Auto-Discovery
- UUID v7 Migration
- Pydantic Everywhere
- Vertical Slice Restructure (all features → operation-first folder pattern)

---

## Legacy Roadmap

### Priority 1: Core Trading Engine
- [x] Strategy Framework - Base class, YAML loader, MA crossover example
- [x] Backtesting Engine - Run/optimize strategies against historical OHLCV data
- [x] Portfolio Tracker - Position tracking via PositionTracker + MongoDB persistence

### Priority 2: Simulation & Analysis
- [x] Forward Testing - Paper broker with simulated fills
- [x] Risk Management - RiskCheckHandler, position sizer, risk value objects
- [ ] Performance Reports - Trade logs, equity curves, analytics dashboard

### Priority 3: Live Trading
- [x] Broker Integration - OKX (live + demo), Paper broker via BrokerFactory
- [x] Order Management - OrderManager with MongoDB persistence, event-driven fills

---

## Code Improvements
- Update to simplify the port, we dont want it to be mentioned in too many places
- Same for configs
- All ports, configs, username, pwd should be centralized somewhere
