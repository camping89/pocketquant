# PocketQuant Roadmap

## Priority 1: Core Trading Engine
- [ ] Strategy Framework - Base class for defining trading strategies (entry/exit signals, position sizing)
- [ ] Backtesting Engine - Run strategies against historical OHLCV data, calculate metrics (Sharpe, drawdown, win rate)
- [ ] Portfolio Tracker - Track positions, P&L, holdings

## Priority 2: Simulation & Analysis
- [ ] Forward Testing - Paper trading mode using real-time quotes
- [ ] Risk Management - Stop losses, take profits, position limits
- [ ] Performance Reports - Trade logs, equity curves, analytics dashboard

## Priority 3: Live Trading
- [ ] Broker Integration - Connect to exchanges/brokers (Alpaca, Interactive Brokers, etc.)
- [ ] Order Management - Place, track, cancel orders

---
## Code
- Update to simplify the port, we dont want it to be mentioned in too many places
- Same for configs
- All ports, configs, username, pwd should be centralized somewhere