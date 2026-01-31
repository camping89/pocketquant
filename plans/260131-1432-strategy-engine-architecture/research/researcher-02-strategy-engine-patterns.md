# Event-Driven Strategy Engine Patterns for Trading Systems

**Research Date:** 2026-01-31 | **Focus:** Architecture patterns, interface design, risk management integration

## 1. Core Architecture: Event-Driven Model

### Event Types & Flow

Four fundamental event types constitute the trading event loop:

```
MarketEvent → SignalEvent → OrderEvent → FillEvent
    ↓            ↓            ↓           ↓
DataHandler  Strategy    Portfolio   ExecutionHandler
```

**Event Loop Execution:**
- **Outer loop**: Heartbeat (market data update frequency)
- **Inner loop**: Process all queued events until empty, then next heartbeat
- Benefits: Eliminates lookahead bias, supports backtest/live parity, decoupled components

### Component Responsibilities

| Component | Input | Output | Responsibility |
|-----------|-------|--------|-----------------|
| **DataHandler** | Historical/live data | MarketEvent | Feed market data at heartbeat intervals |
| **Strategy** | MarketEvent | SignalEvent | Generate trading signals (direction) |
| **Portfolio** | SignalEvent | OrderEvent | Manage positions, sizing, risk constraints |
| **ExecutionHandler** | OrderEvent | FillEvent | Simulate/execute orders, apply slippage/commission |

## 2. Strategy Interface Design: on_bar vs on_tick

### Trade-offs

**On_Bar (Bar Close) Execution:**
- ✓ Simple, accurate backtest (OHLC data only)
- ✓ Fast backtests
- ✗ Misses intra-bar opportunities
- ✗ Can't implement trailing stops, breakeven logic intra-bar

**On_Tick (Every Tick) Execution:**
- ✓ Captures intra-bar execution details
- ✓ Realistic trailing stops, breakeven adjustments
- ✗ Historical backtest ≠ live trading (different tick flow)
- ✗ Slower, requires tick-level data

### Recommended Interface (Hybrid)

```python
class IStrategy(ABC):
    @abstractmethod
    async def on_bar(self, bar: Bar) -> Optional[Signal]:
        """Primary entry/exit logic. Called on bar close."""
        pass

    @abstractmethod
    async def on_tick(self, tick: Tick) -> Optional[OrderUpdate]:
        """Optional: Intra-bar adjustments (trailing stops, breakeven)."""
        # Returns order updates only, not new positions
        pass
```

**Backtest/Live Parity Technique:** Use secondary 1-tick data series for historical backtests. Strategy calculates on 1-tick granularity but executes `on_bar` decisions with tick-accurate fills. Keeps backtest realistic while maintaining consistency.

## 3. Risk Management Integration Points

### Architecture Integration

Risk checks must occur **before** OrderEvent is queued (in Portfolio component):

```
SignalEvent → [Portfolio Risk Checks] → OrderEvent (or Rejected)
               ├─ Current notional exposure
               ├─ Account max loss limit
               ├─ Position size limits
               └─ Max leverage check
```

### Position Sizing Algorithm Integration

**Two Primary Approaches:**

**A) Fixed Percent Risk (Industry Standard)**
```
position_size = (account_risk_per_trade / abs(entry - stop_loss)) * risk_percent
risk_percent = 1-2% of account per trade
```
Simple, stable, reduces ruin risk.

**B) Kelly Criterion (Performance-Based)**
```
kelly % = (W × R - L) / R
  W = win rate (decimal)
  R = reward/risk ratio (avg_win / avg_loss)
  L = loss rate (1 - W)
```
- Full Kelly is aggressive; traders use Half/Quarter Kelly
- Requires accurate win rate/ratio (backtest dependency)
- Dynamically adjusts sizing based on edge

**Integration Pattern:**
Portfolio holds both risk rules. Strategy context determines which:
- Live trading: Fixed percent risk (conservative)
- Optimized system: Kelly with 25% allocation (balance growth/safety)

## 4. Signal Generation & Order Flow

### Signal Definition

```python
@dataclass
class Signal:
    timestamp: datetime
    symbol: str
    direction: Direction  # LONG | SHORT | EXIT
    strength: float  # 0.0-1.0 confidence
    entry_logic: str  # e.g., "MA_crossover"
```

**Order Generation Rules (Portfolio):**
- If direction=LONG & no position: BUY
- If direction=EXIT & position exists: CLOSE
- If direction=SHORT & no position: SELL SHORT (if allowed)
- If direction=SHORT & LONG position: CLOSE or REVERSE
- All subject to risk checks before queuing OrderEvent

## 5. Backtest/Live Execution Parity

### Critical Design Patterns

**DataHandler Abstraction:**
- Backtest: Replay historical bar/tick data from DB
- Live: Stream real-time ticks from WebSocket, aggregate into bars
- Same output: MarketEvent stream (timestamp, OHLC, volume)

**Key to Parity:**
1. **Same event timestamps** across backtest/live (avoid micro-timing issues)
2. **Consistent position size calculations** (use class-based settings, not hardcoded)
3. **Identical strategy code** — no if-else branches for backtest vs live
4. **Slippage modeling** in backtest matches expected live slippage
5. **Order rejection rules** mimic broker behavior (e.g., min notional)

**Practical Implementation:**
- Encapsulate broker-specific logic (min order size, tick size) in ExecutionHandler
- Use a Strategy config object (not env vars) for parameters
- Log all signals/orders to same format in both modes for post-analysis

## 6. Recommended IStrategy Interface (Complete)

```python
class IStrategy(ABC):
    def __init__(self, config: StrategyConfig, logger: Logger):
        self.config = config
        self.logger = logger

    @abstractmethod
    async def on_bar(self, bar: Bar) -> Optional[Signal]:
        """Required: Process bar close, generate entry/exit signals."""
        pass

    async def on_tick(self, tick: Tick) -> Optional[OrderUpdate]:
        """Optional: Adjust open orders (trailing stop, breakeven)."""
        return None  # Default: no intra-bar adjustments

    async def on_fill(self, fill: FillEvent) -> None:
        """Optional: Post-execution callback (e.g., update internal state)."""
        pass
```

## Key Takeaways

1. **Event-driven loop** is the gold standard for backtest/live consistency
2. **on_bar primary + on_tick optional** balances simplicity with realism
3. **Risk checks in Portfolio** component, not scattered across Strategy
4. **Position sizing options:** Fixed percent (safety) or Kelly (performance)
5. **DataHandler abstraction** is critical for code reuse
6. **Secondary tick series** bridges backtest accuracy gap without code duplication

## Sources

- [Event-Driven Backtesting with Python - Part I | QuantStart](https://www.quantstart.com/articles/Event-Driven-Backtesting-with-Python-Part-I/)
- [Advanced Trading Infrastructure - QuantStart](https://www.quantstart.com/articles/Announcing-the-QuantStart-Advanced-Trading-Infrastructure-Article-Series/)
- [Position Sizing in Trading | QuantInsti](https://blog.quantinsti.com/position-sizing/)
- [Kelly Criterion in Practical Trading | QuantInsti](https://blog.quantinsti.com/risk-constrained-kelly-criterion/)
- [NautilusTrader: Event-Driven Backtesting & Live Trading](https://nautilustrader.io/)
- [QuantConnect: Unified Backtest/Live Platform](https://www.quantconnect.com/)
