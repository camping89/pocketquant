---
title: "Trading Engine Features"
description: "Core trading engine: strategy framework, backtesting, portfolio tracking, forward testing, risk management, and performance reports"
status: pending
priority: P1
effort: 32h
branch: feat/trading-engine
tags: [trading, backtesting, portfolio, risk-management]
created: 2026-01-08
---

# PocketQuant Plan C: Trading Engine Features

## Executive Summary

Build core trading engine following vertical slice architecture. Leverages existing market_data feature (OHLCV repository, quote service, Redis cache, MongoDB). Six phases: Strategy Framework, Backtesting Engine, Portfolio Tracker, Forward Testing, Risk Management, Performance Reports.

## Architecture Overview

```
src/features/
├── market_data/          # Existing - OHLCV, quotes, sync
└── trading/              # NEW - Trading engine feature
    ├── api/              # FastAPI routes
    ├── models/           # Domain models
    ├── repositories/     # Data persistence
    ├── services/         # Business logic
    ├── strategies/       # Strategy implementations
    └── reports/          # Report generators
```

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Existing Infrastructure                       │
│  MongoDB (OHLCV) ←→ OHLCVRepository ←→ DataSyncService          │
│  Redis (Quotes)  ←→ Cache           ←→ QuoteService              │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Trading Engine                              │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │  Strategy   │───▶│  Backtest   │───▶│  Reports    │          │
│  │  Framework  │    │  Engine     │    │  Generator  │          │
│  └─────────────┘    └─────────────┘    └─────────────┘          │
│         │                  │                                     │
│         ▼                  ▼                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │  Forward    │◀──▶│  Portfolio  │◀──▶│    Risk     │          │
│  │  Testing    │    │  Tracker    │    │  Manager    │          │
│  └─────────────┘    └─────────────┘    └─────────────┘          │
│                            │                                     │
│                            ▼                                     │
│               MongoDB (positions, trades, portfolios)            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Strategy Framework (5h)

### Objective
Define abstract base class for trading strategies with signals, position sizing, and timeframe handling.

### Models

**File: `src/features/trading/models/strategy.py`**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

class SignalType(str, Enum):
    LONG = "long"
    SHORT = "short"
    EXIT = "exit"
    HOLD = "hold"

@dataclass
class Signal:
    type: SignalType
    symbol: str
    exchange: str
    timestamp: datetime
    price: float
    confidence: float = 1.0  # 0-1
    metadata: dict[str, Any] | None = None

@dataclass
class StrategyContext:
    symbol: str
    exchange: str
    interval: str
    current_bar: dict  # OHLCV
    history: list[dict]  # Previous bars
    position: "Position | None"
    portfolio: "Portfolio"

class BaseStrategy(ABC):
    """Abstract base for all trading strategies."""

    name: str
    supported_intervals: list[str]
    required_history: int  # Bars needed for indicators

    @abstractmethod
    def generate_signal(self, ctx: StrategyContext) -> Signal:
        """Generate trading signal from context."""
        pass

    @abstractmethod
    def calculate_position_size(
        self,
        signal: Signal,
        portfolio: "Portfolio",
        risk_params: "RiskParams"
    ) -> float:
        """Determine position size based on signal and risk."""
        pass

    def validate_signal(self, signal: Signal, ctx: StrategyContext) -> bool:
        """Optional signal validation hook."""
        return True
```

### Tasks

| # | Task | File | Est |
|---|------|------|-----|
| 1.1 | Create trading feature structure | `src/features/trading/__init__.py` | 15m |
| 1.2 | Define Signal and SignalType models | `models/strategy.py` | 30m |
| 1.3 | Define StrategyContext dataclass | `models/strategy.py` | 20m |
| 1.4 | Implement BaseStrategy ABC | `models/strategy.py` | 45m |
| 1.5 | Create Position model (for context) | `models/position.py` | 30m |
| 1.6 | Create Portfolio model (for context) | `models/portfolio.py` | 30m |
| 1.7 | Create RiskParams model | `models/risk.py` | 20m |
| 1.8 | Implement SMA crossover example strategy | `strategies/sma_crossover.py` | 45m |
| 1.9 | Unit tests for strategy framework | `tests/trading/test_strategy.py` | 45m |

### Deliverables
- Abstract BaseStrategy class
- Signal/SignalType enums
- StrategyContext with position awareness
- SMA crossover reference implementation

---

## Phase 2: Backtesting Engine (8h)

### Objective
Simulate strategy execution against historical OHLCV data with order simulation and metrics.

### Architecture

```
BacktestEngine
├── DataIterator          # Iterates OHLCV bars
├── OrderSimulator        # Simulates market/limit orders
├── PositionTracker       # Tracks open positions
├── MetricsCalculator     # Sharpe, drawdown, etc.
└── TradeLogger           # Records all trades
```

### Models

**File: `src/features/trading/models/backtest.py`**

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

@dataclass
class Order:
    id: str
    symbol: str
    exchange: str
    side: OrderSide
    type: OrderType
    quantity: float
    price: float | None  # For limit orders
    stop_price: float | None  # For stop orders
    created_at: datetime
    filled_at: datetime | None = None
    filled_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    commission: float = 0.0

@dataclass
class Trade:
    id: str
    order_id: str
    symbol: str
    exchange: str
    side: OrderSide
    quantity: float
    price: float
    timestamp: datetime
    commission: float
    pnl: float | None = None  # For closing trades

@dataclass
class BacktestConfig:
    symbol: str
    exchange: str
    interval: str
    start_date: datetime
    end_date: datetime
    initial_capital: float = 100000.0
    commission_rate: float = 0.001  # 0.1%
    slippage_rate: float = 0.0005  # 0.05%

@dataclass
class BacktestResult:
    config: BacktestConfig
    trades: list[Trade]
    metrics: "BacktestMetrics"
    equity_curve: list[dict]  # timestamp, equity
    drawdown_curve: list[dict]  # timestamp, drawdown%

@dataclass
class BacktestMetrics:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_return: float
    total_return_pct: float
    annualized_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration_days: int
    profit_factor: float
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    avg_trade_duration: float  # hours
```

### Services

**File: `src/features/trading/services/backtest_engine.py`**

```python
class BacktestEngine:
    """Main backtesting orchestrator."""

    async def run(
        self,
        strategy: BaseStrategy,
        config: BacktestConfig
    ) -> BacktestResult:
        """Execute backtest and return results."""
        pass

class OrderSimulator:
    """Simulates order execution with slippage/commission."""

    def execute_market_order(
        self, order: Order, bar: dict
    ) -> Trade | None:
        pass

    def check_limit_order(
        self, order: Order, bar: dict
    ) -> Trade | None:
        pass

class MetricsCalculator:
    """Calculate performance metrics from trades."""

    def calculate(
        self,
        trades: list[Trade],
        equity_curve: list[dict],
        config: BacktestConfig
    ) -> BacktestMetrics:
        pass
```

### Tasks

| # | Task | File | Est |
|---|------|------|-----|
| 2.1 | Define Order, Trade models | `models/backtest.py` | 30m |
| 2.2 | Define BacktestConfig, Result, Metrics | `models/backtest.py` | 45m |
| 2.3 | Implement OrderSimulator (market orders) | `services/order_simulator.py` | 60m |
| 2.4 | Add limit/stop order simulation | `services/order_simulator.py` | 45m |
| 2.5 | Implement PositionTracker | `services/position_tracker.py` | 45m |
| 2.6 | Implement MetricsCalculator (Sharpe) | `services/metrics_calculator.py` | 60m |
| 2.7 | Add drawdown, win rate, profit factor | `services/metrics_calculator.py` | 45m |
| 2.8 | Implement BacktestEngine core loop | `services/backtest_engine.py` | 90m |
| 2.9 | Add trade logging | `services/trade_logger.py` | 30m |
| 2.10 | Backtest repository (save results to MongoDB) | `repositories/backtest_repository.py` | 45m |
| 2.11 | Unit tests | `tests/trading/test_backtest.py` | 60m |

### Deliverables
- Complete backtest engine with order simulation
- Metrics: Sharpe, Sortino, max drawdown, win rate, profit factor
- Trade log with P&L
- Equity curve generation

---

## Phase 3: Portfolio Tracker (5h)

### Objective
Track positions, P&L, holdings, and cash balance across multiple symbols.

### Models

**File: `src/features/trading/models/portfolio.py`**

```python
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

@dataclass
class Position:
    symbol: str
    exchange: str
    quantity: float
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    opened_at: datetime
    last_updated: datetime

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_entry_price

@dataclass
class Portfolio:
    id: str
    name: str
    cash_balance: float
    positions: dict[str, Position]  # key: "EXCHANGE:SYMBOL"
    created_at: datetime
    updated_at: datetime

    @property
    def total_equity(self) -> float:
        positions_value = sum(p.market_value for p in self.positions.values())
        return self.cash_balance + positions_value

    @property
    def total_unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def total_realized_pnl(self) -> float:
        return sum(p.realized_pnl for p in self.positions.values())

@dataclass
class PortfolioSnapshot:
    portfolio_id: str
    timestamp: datetime
    cash_balance: float
    positions_value: float
    total_equity: float
    unrealized_pnl: float
    realized_pnl: float
```

### Services

**File: `src/features/trading/services/portfolio_service.py`**

```python
class PortfolioService:
    """Manages portfolio state and operations."""

    async def create_portfolio(
        self, name: str, initial_capital: float
    ) -> Portfolio:
        pass

    async def update_position(
        self, portfolio_id: str, trade: Trade
    ) -> Position:
        """Update position from executed trade."""
        pass

    async def get_holdings(
        self, portfolio_id: str
    ) -> list[Position]:
        pass

    async def calculate_pnl(
        self, portfolio_id: str, current_prices: dict[str, float]
    ) -> dict:
        """Calculate P&L with current market prices."""
        pass

    async def take_snapshot(
        self, portfolio_id: str
    ) -> PortfolioSnapshot:
        """Record current state for history."""
        pass
```

### Tasks

| # | Task | File | Est |
|---|------|------|-----|
| 3.1 | Define Position model | `models/position.py` | 30m |
| 3.2 | Define Portfolio model | `models/portfolio.py` | 30m |
| 3.3 | Define PortfolioSnapshot model | `models/portfolio.py` | 20m |
| 3.4 | Implement PortfolioRepository | `repositories/portfolio_repository.py` | 45m |
| 3.5 | Implement PositionRepository | `repositories/position_repository.py` | 45m |
| 3.6 | Implement PortfolioService (CRUD) | `services/portfolio_service.py` | 60m |
| 3.7 | Add P&L calculation logic | `services/portfolio_service.py` | 45m |
| 3.8 | Add snapshot functionality | `services/portfolio_service.py` | 30m |
| 3.9 | Portfolio API routes | `api/portfolio_routes.py` | 45m |
| 3.10 | Unit tests | `tests/trading/test_portfolio.py` | 45m |

### Deliverables
- Portfolio CRUD with positions
- Real-time P&L calculation
- Holdings snapshot history
- REST API for portfolio management

---

## Phase 4: Forward Testing (6h)

### Objective
Paper trading mode using real-time quotes with simulated order execution.

### Architecture

```
ForwardTestRunner
├── QuoteService (existing)     # Real-time prices
├── OrderSimulator              # Reuse from backtest
├── PortfolioService            # Reuse from Phase 3
├── SignalProcessor             # Process strategy signals in real-time
└── LivePnLTracker              # Track P&L in real-time
```

### Models

**File: `src/features/trading/models/forward_test.py`**

```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class ForwardTestStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"

@dataclass
class ForwardTestConfig:
    name: str
    strategy_name: str
    symbols: list[dict]  # [{"symbol": "AAPL", "exchange": "NASDAQ"}]
    interval: str
    initial_capital: float
    commission_rate: float

@dataclass
class ForwardTestSession:
    id: str
    config: ForwardTestConfig
    portfolio_id: str
    status: ForwardTestStatus
    started_at: datetime
    stopped_at: datetime | None
    last_signal_at: datetime | None
    total_signals: int
    total_trades: int
```

### Services

**File: `src/features/trading/services/forward_test_service.py`**

```python
class ForwardTestService:
    """Manages paper trading sessions."""

    async def start_session(
        self, config: ForwardTestConfig, strategy: BaseStrategy
    ) -> ForwardTestSession:
        """Start paper trading session."""
        pass

    async def stop_session(self, session_id: str) -> ForwardTestSession:
        pass

    async def on_quote_update(
        self, session_id: str, quote: Quote
    ) -> Signal | None:
        """Process quote update, generate signals."""
        pass

    async def get_live_pnl(self, session_id: str) -> dict:
        """Get real-time P&L for session."""
        pass
```

### Tasks

| # | Task | File | Est |
|---|------|------|-----|
| 4.1 | Define ForwardTestConfig, Session models | `models/forward_test.py` | 30m |
| 4.2 | Implement ForwardTestRepository | `repositories/forward_test_repository.py` | 45m |
| 4.3 | Implement SignalProcessor | `services/signal_processor.py` | 60m |
| 4.4 | Implement ForwardTestService (start/stop) | `services/forward_test_service.py` | 60m |
| 4.5 | Integrate with QuoteService callbacks | `services/forward_test_service.py` | 45m |
| 4.6 | Implement LivePnLTracker | `services/live_pnl_tracker.py` | 45m |
| 4.7 | Forward test API routes | `api/forward_test_routes.py` | 45m |
| 4.8 | WebSocket endpoint for live updates (optional) | `api/forward_test_routes.py` | 45m |
| 4.9 | Unit tests | `tests/trading/test_forward_test.py` | 45m |

### Deliverables
- Paper trading session management
- Real-time signal processing
- Live P&L tracking
- REST API for session control

---

## Phase 5: Risk Management (4h)

### Objective
Implement stop loss, take profit, position limits, and exposure controls.

### Models

**File: `src/features/trading/models/risk.py`**

```python
from dataclasses import dataclass
from enum import Enum

class RiskRuleType(str, Enum):
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    MAX_POSITION_SIZE = "max_position_size"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    MAX_EXPOSURE = "max_exposure"
    MAX_POSITIONS = "max_positions"

@dataclass
class RiskParams:
    stop_loss_pct: float | None = None  # e.g., 0.02 = 2%
    take_profit_pct: float | None = None
    max_position_pct: float = 0.1  # Max 10% of portfolio per position
    daily_loss_limit_pct: float = 0.05  # Stop trading if 5% daily loss
    max_exposure_pct: float = 1.0  # Max 100% invested
    max_positions: int = 10

@dataclass
class RiskAlert:
    rule_type: RiskRuleType
    symbol: str | None
    message: str
    current_value: float
    threshold: float
    triggered_at: datetime

@dataclass
class RiskCheckResult:
    passed: bool
    alerts: list[RiskAlert]
    blocked_reason: str | None = None
```

### Services

**File: `src/features/trading/services/risk_manager.py`**

```python
class RiskManager:
    """Enforces risk rules on trading operations."""

    def check_order(
        self, order: Order, portfolio: Portfolio, params: RiskParams
    ) -> RiskCheckResult:
        """Validate order against risk rules."""
        pass

    def check_stop_loss(
        self, position: Position, current_price: float, params: RiskParams
    ) -> Signal | None:
        """Generate exit signal if stop loss triggered."""
        pass

    def check_take_profit(
        self, position: Position, current_price: float, params: RiskParams
    ) -> Signal | None:
        """Generate exit signal if take profit triggered."""
        pass

    def check_daily_limit(
        self, portfolio: Portfolio, params: RiskParams
    ) -> bool:
        """Check if daily loss limit breached."""
        pass

    def calculate_max_position_size(
        self, portfolio: Portfolio, signal: Signal, params: RiskParams
    ) -> float:
        """Calculate max allowed position size."""
        pass
```

### Tasks

| # | Task | File | Est |
|---|------|------|-----|
| 5.1 | Define RiskParams model | `models/risk.py` | 20m |
| 5.2 | Define RiskAlert, RiskCheckResult | `models/risk.py` | 20m |
| 5.3 | Implement stop loss logic | `services/risk_manager.py` | 30m |
| 5.4 | Implement take profit logic | `services/risk_manager.py` | 30m |
| 5.5 | Implement position size limits | `services/risk_manager.py` | 30m |
| 5.6 | Implement daily loss limits | `services/risk_manager.py` | 30m |
| 5.7 | Implement exposure limits | `services/risk_manager.py` | 30m |
| 5.8 | Integrate RiskManager into BacktestEngine | `services/backtest_engine.py` | 30m |
| 5.9 | Integrate RiskManager into ForwardTestService | `services/forward_test_service.py` | 30m |
| 5.10 | Unit tests | `tests/trading/test_risk.py` | 30m |

### Deliverables
- Complete risk rule enforcement
- Stop loss / take profit automation
- Position and exposure limits
- Integration with backtest and forward test

---

## Phase 6: Performance Reports (4h)

### Objective
Generate equity curves, trade history exports, performance summaries, and comparison reports.

### Models

**File: `src/features/trading/models/report.py`**

```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class ReportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"
    HTML = "html"

@dataclass
class PerformanceSummary:
    period_start: datetime
    period_end: datetime
    starting_equity: float
    ending_equity: float
    total_return: float
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    sharpe_ratio: float
    max_drawdown: float
    best_trade: dict
    worst_trade: dict
    monthly_returns: list[dict]  # [{"month": "2024-01", "return_pct": 2.5}]

@dataclass
class ComparisonReport:
    strategies: list[str]
    period_start: datetime
    period_end: datetime
    metrics_comparison: dict  # strategy -> metrics
    equity_curves: dict  # strategy -> equity curve
    correlation_matrix: list[list[float]]
```

### Services

**File: `src/features/trading/services/report_generator.py`**

```python
class ReportGenerator:
    """Generate performance reports."""

    async def generate_equity_curve(
        self, trades: list[Trade], initial_capital: float
    ) -> list[dict]:
        """Generate equity curve from trades."""
        pass

    async def generate_trade_history(
        self, trades: list[Trade], format: ReportFormat
    ) -> str | bytes:
        """Export trade history in specified format."""
        pass

    async def generate_summary(
        self, backtest_result: BacktestResult
    ) -> PerformanceSummary:
        """Generate performance summary."""
        pass

    async def generate_comparison(
        self, results: list[BacktestResult]
    ) -> ComparisonReport:
        """Compare multiple backtest results."""
        pass

    async def generate_monthly_breakdown(
        self, trades: list[Trade]
    ) -> list[dict]:
        """Break down returns by month."""
        pass
```

### Tasks

| # | Task | File | Est |
|---|------|------|-----|
| 6.1 | Define PerformanceSummary model | `models/report.py` | 20m |
| 6.2 | Define ComparisonReport model | `models/report.py` | 20m |
| 6.3 | Implement equity curve generator | `services/report_generator.py` | 45m |
| 6.4 | Implement trade history export (CSV/JSON) | `services/report_generator.py` | 45m |
| 6.5 | Implement performance summary | `services/report_generator.py` | 30m |
| 6.6 | Implement monthly breakdown | `services/report_generator.py` | 30m |
| 6.7 | Implement comparison report | `services/report_generator.py` | 45m |
| 6.8 | Report API routes | `api/report_routes.py` | 45m |
| 6.9 | Unit tests | `tests/trading/test_reports.py` | 30m |

### Deliverables
- Equity curve visualization data
- Trade history export (CSV, JSON)
- Performance summary with monthly breakdown
- Strategy comparison reports

---

## API Routes Summary

All routes under `/api/v1/trading/`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/strategies` | GET | List available strategies |
| `/backtest` | POST | Run backtest |
| `/backtest/{id}` | GET | Get backtest result |
| `/backtest/{id}/trades` | GET | Get trades from backtest |
| `/portfolios` | GET, POST | List/create portfolios |
| `/portfolios/{id}` | GET, PATCH, DELETE | Portfolio CRUD |
| `/portfolios/{id}/positions` | GET | Get positions |
| `/portfolios/{id}/snapshot` | POST | Take snapshot |
| `/forward-test` | POST | Start paper trading |
| `/forward-test/{id}` | GET, DELETE | Get/stop session |
| `/forward-test/{id}/pnl` | GET | Get live P&L |
| `/reports/summary/{backtest_id}` | GET | Performance summary |
| `/reports/trades/{backtest_id}` | GET | Trade history export |
| `/reports/comparison` | POST | Compare strategies |

---

## File Structure

```
src/features/trading/
├── __init__.py
├── api/
│   ├── __init__.py
│   ├── backtest_routes.py
│   ├── portfolio_routes.py
│   ├── forward_test_routes.py
│   └── report_routes.py
├── models/
│   ├── __init__.py
│   ├── strategy.py
│   ├── position.py
│   ├── portfolio.py
│   ├── backtest.py
│   ├── forward_test.py
│   ├── risk.py
│   └── report.py
├── repositories/
│   ├── __init__.py
│   ├── backtest_repository.py
│   ├── portfolio_repository.py
│   ├── position_repository.py
│   └── forward_test_repository.py
├── services/
│   ├── __init__.py
│   ├── backtest_engine.py
│   ├── order_simulator.py
│   ├── position_tracker.py
│   ├── metrics_calculator.py
│   ├── trade_logger.py
│   ├── portfolio_service.py
│   ├── forward_test_service.py
│   ├── signal_processor.py
│   ├── live_pnl_tracker.py
│   ├── risk_manager.py
│   └── report_generator.py
├── strategies/
│   ├── __init__.py
│   └── sma_crossover.py
└── reports/
    └── __init__.py
```

---

## Dependencies

No new dependencies required. Uses existing:
- `pandas`, `numpy` - calculations
- `motor`, `pymongo` - MongoDB
- `redis` - caching
- `pydantic` - models

---

## Testing Strategy

1. **Unit tests**: Each service/module
2. **Integration tests**: Backtest with real OHLCV from MongoDB
3. **End-to-end tests**: Full API workflow

Test files:
- `tests/trading/test_strategy.py`
- `tests/trading/test_backtest.py`
- `tests/trading/test_portfolio.py`
- `tests/trading/test_forward_test.py`
- `tests/trading/test_risk.py`
- `tests/trading/test_reports.py`

---

## Implementation Order

```
Phase 1 (Strategy) ──┐
                     ├──▶ Phase 2 (Backtest) ──┐
Phase 3 (Portfolio) ─┘                         │
                                               ├──▶ Phase 6 (Reports)
Phase 5 (Risk) ────────────────────────────────┤
                                               │
Phase 4 (Forward Test) ────────────────────────┘
```

**Recommended sequence:**
1. Phase 1 + Phase 3 in parallel (foundation)
2. Phase 2 (depends on 1, 3)
3. Phase 5 (can start after 2)
4. Phase 4 (depends on 1, 3, 5)
5. Phase 6 (depends on 2)

---

## Effort Summary

| Phase | Description | Effort |
|-------|-------------|--------|
| 1 | Strategy Framework | 5h |
| 2 | Backtesting Engine | 8h |
| 3 | Portfolio Tracker | 5h |
| 4 | Forward Testing | 6h |
| 5 | Risk Management | 4h |
| 6 | Performance Reports | 4h |
| **Total** | | **32h** |

---

## Unresolved Questions

1. **Decimal vs float for prices?** - Consider `Decimal` for precision in production
2. **Multi-currency support?** - Defer to future phase
3. **WebSocket for live updates?** - Optional in Phase 4, could use Server-Sent Events instead
4. **Historical volatility for Sharpe?** - Use 252 trading days annualization factor?
5. **Timezone handling?** - Assume UTC throughout, document clearly
