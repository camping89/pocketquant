# PocketQuant TODO

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

| Plan | Priority | Description |
|------|----------|-------------|
| `260108-1144-trading-features` | P1 | Backtesting, Portfolio, Risk Management |
| `260108-1144-vps-deployment` | P1 | Deploy to Vultr Singapore |
| `260131-2006-okx-websocket-backtest-integration` | P1 | Backtest engine + OKX WebSocket |
| `260128-1529-job-feature-flag` | P3 | Enable/disable background jobs |

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

---

## Legacy Roadmap

### Priority 1: Core Trading Engine
- [x] Strategy Framework - Base class for defining trading strategies
- [ ] Backtesting Engine - Run strategies against historical OHLCV data
- [ ] Portfolio Tracker - Track positions, P&L, holdings

### Priority 2: Simulation & Analysis
- [ ] Forward Testing - Paper trading mode using real-time quotes
- [ ] Risk Management - Stop losses, take profits, position limits
- [ ] Performance Reports - Trade logs, equity curves, analytics dashboard

### Priority 3: Live Trading
- [ ] Broker Integration - Connect to exchanges/brokers
- [ ] Order Management - Place, track, cancel orders

---

## Code Improvements
- Update to simplify the port, we dont want it to be mentioned in too many places
- Same for configs
- All ports, configs, username, pwd should be centralized somewhere
