# Brainstorm: Strategy Engine Architecture

**Date:** 2026-01-31
**Status:** Agreed

---

## Problem Statement

Build modular trading strategy execution system that:
- Runs forward testing (live) + backtesting simultaneously
- Supports configurable risk (1% per trade default)
- Abstracts brokers (OKX first, others later)
- Loads strategies from YAML config
- Allows multiple strategies per symbol (independent positions)
- Uses existing WebSocket quotes + OHLCV infrastructure

---

## Architecture Decision

**Selected:** Hybrid DDD/CQRS pattern (extends existing architecture)

### Event Flow
```
BarCompletedEvent/QuoteReceivedEvent
    → StrategyEngine (dispatches to active strategies)
        → IStrategy.on_bar() / on_tick()
            → Signal (direction, confidence)
                → RiskManager.calculate_position_size()
                    → Order (with TP/SL)
                        → IBroker.submit_order()
                            → OrderFilledEvent
                                → PositionTracker.update()
```

---

## Components

### 1. Domain Layer (`src/domain/`)

| Aggregate | Responsibility |
|-----------|----------------|
| `StrategyAggregate` | Signal generation, state machine |
| `OrderAggregate` | Order lifecycle (pending→submitted→filled) |
| `PositionAggregate` | Entry/exit tracking, P&L |

**Value Objects:**
- `Signal`: direction (long/short/flat), symbol, timestamp, confidence
- `OrderType`: market, limit, stop_limit
- `OrderSide`: buy, sell
- `RiskConfig`: model, risk_per_trade, max_positions

### 2. Infrastructure Layer (`src/infrastructure/brokers/`)

**IBroker Interface:**
```python
class IBroker(ABC):
    async def submit_order(order: Order) -> OrderResult
    async def cancel_order(order_id: str) -> bool
    async def get_positions() -> list[Position]
    async def get_account_balance() -> AccountBalance
    async def subscribe_order_updates(callback) -> None
```

**Implementations:**
- `OKXBroker` - Uses `python-okx` SDK (REST + WS)
- `PaperBroker` - Simulated fills for testing/backtesting

### 3. Feature Layer (`src/features/`)

| Feature | Purpose |
|---------|---------|
| `strategy/` | YAML loader, engine, strategy registry |
| `trading/` | OrderManager, PositionTracker |
| `risk/` | Position sizing, exposure limits |

---

## Strategy Config Format (YAML)

```yaml
name: "MA Cross"
symbol: "BTCUSDT"
exchange: "OKX"
interval: "5m"
trigger: "bar"  # bar | tick
broker: "okx"

parameters:
  fast_period: 10
  slow_period: 20

risk:
  model: "percent_risk"  # percent_risk | kelly | fixed
  risk_per_trade: 0.01
  max_positions: 3

orders:
  entry: "market"
  take_profit:
    type: "limit"
    distance_percent: 0.02
  stop_loss:
    type: "limit"
    distance_percent: 0.01
```

---

## OKX Integration Details

**SDK:** `python-okx` (official)

**Key Endpoints:**
- `POST /api/v5/trade/order` - Place order
- Order types: market, limit, FOK, IOC, TP/SL

**Rate Limits:**
- 1000 orders/2s per sub-account
- Shared across REST + WebSocket

**WebSocket:**
- Private channel for order updates
- Max 30 connections per channel

**Auth:**
- HMAC SHA256 signature
- Headers: OK-ACCESS-KEY, OK-ACCESS-SIGN, OK-ACCESS-TIMESTAMP, OK-ACCESS-PASSPHRASE

---

## Directory Structure

```
src/
├── domain/
│   ├── strategy/          # StrategyAggregate, Signal
│   ├── order/             # OrderAggregate, OrderType
│   ├── position/          # PositionAggregate, PnL
│   └── risk/              # RiskConfig, PositionSizer
│
├── features/
│   ├── strategy/
│   │   ├── api/           # REST routes
│   │   ├── loader/        # YAML parser
│   │   ├── engine/        # StrategyEngine
│   │   ├── handlers/      # CQRS handlers
│   │   └── models/        # DTOs
│   │
│   ├── trading/
│   │   ├── api/           # Order/position routes
│   │   ├── managers/      # OrderManager, PositionTracker
│   │   └── handlers/      # CQRS handlers
│   │
│   └── risk/
│       ├── handlers/      # RiskCheckHandler
│       └── models/        # RiskConfig DTO
│
├── infrastructure/
│   └── brokers/
│       ├── interface.py   # IBroker ABC
│       ├── okx/           # OKXBroker
│       ├── paper/         # PaperBroker
│       └── factory.py     # BrokerFactory
│
└── strategies/            # YAML configs (outside src/)
    ├── ma_cross.yaml
    └── rsi_reversal.yaml
```

---

## Implementation Phases

### Phase 1: Core Abstractions
- [ ] IBroker interface + PaperBroker
- [ ] Strategy base class + loader
- [ ] Order/Position domain models
- [ ] Basic StrategyEngine (bar-triggered)

### Phase 2: OKX Integration
- [ ] OKXBroker (REST orders)
- [ ] OKX WebSocket order updates
- [ ] Account balance/position sync

### Phase 3: Risk Management
- [ ] Position sizing algorithms
- [ ] TP/SL order attachment
- [ ] Max exposure limits

### Phase 4: Backtesting Mode
- [ ] Historical data feed adapter
- [ ] PaperBroker with fill simulation
- [ ] Performance metrics

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| OKX rate limits | Queue orders, batch when possible |
| WebSocket disconnects | Exponential backoff (existing pattern) |
| Position sync drift | Periodic reconciliation job |
| Strategy bugs cause losses | Paper trading validation period |

---

## Success Criteria

1. Strategy can be defined in YAML, loaded without code changes
2. Same strategy code runs on backtest and live
3. Orders submitted to OKX within 100ms of signal
4. Position sizing respects 1% risk rule
5. Multiple strategies run independently on same symbol

---

## Sources

- [QuantStart Event-Driven Backtesting](https://www.quantstart.com/articles/Event-Driven-Backtesting-with-Python-Part-I/)
- [OKX API Documentation](https://www.okx.com/docs-v5/en/)
- [python-okx PyPI](https://pypi.org/project/python-okx/)
- [PyQuant Event-Driven Architecture](https://www.pyquantnews.com/free-python-resources/event-driven-backtesting-for-trading-strategies)

---

## Next Steps

Create detailed implementation plan with:
- Specific file names and interfaces
- CQRS command/query definitions
- MongoDB collection schemas
- API endpoint specifications
