# Backtesting Engine Design Patterns & Performance Metrics

**Researcher:** researcher-02 | **Date:** 2026-01-31 | **Duration:** 30min

## 1. Historical Data Replay: Event-Driven vs Vectorized

### Event-Driven Pattern (Recommended for PocketQuant)

**Architecture:**
- Event class hierarchy: `MARKET`, `SIGNAL`, `ORDER`, `FILL` event types
- Event queue (Python `deque` for O(1) append/pop-left)
- Sequential processing: mimics live trading behavior
- No lookahead bias (data receipt = discrete event)

**Advantages:**
- Code reuse: same handlers for backtest + live trading
- Realistic slippage & execution modeling
- Can "drip feed" data in real-time

**Python idiom:**
```python
from collections import deque
from dataclasses import dataclass

@dataclass
class MarketEvent:
    timestamp: float
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float

class EventLoop:
    def __init__(self):
        self.event_queue = deque()

    def process(self):
        while self.event_queue:
            event = self.event_queue.popleft()
            self.handle_event(event)
```

### Vectorized Pattern (NumPy/Pandas)

**Best for:** Multi-asset portfolio analysis post-simulation.

**Pattern:** Process all symbols across all bars simultaneously using NumPy broadcasting.

```python
import pandas as pd
import numpy as np

# All symbols, all bars at once
returns = pd.DataFrame(close_prices).pct_change()
cumulative_returns = (1 + returns).cumprod()
```

**Trade-off:** Fast analysis but requires pre-computed data (lookahead bias risk).

---

## 2. Time Simulation Approaches

### ContextVar-Based Clock Injection (Testability Pattern)

Context variables allow injecting time without global state:

```python
from contextvars import ContextVar
from datetime import datetime

_current_time: ContextVar[datetime] = ContextVar('current_time')

def get_current_time() -> datetime:
    return _current_time.get(datetime.now())

def set_simulation_time(ts: datetime) -> None:
    _current_time.set(ts)

# In backtest loop:
for bar in bars:
    set_simulation_time(bar.timestamp)
    strategy.on_bar(bar)  # Calls get_current_time() internally
```

**Benefits:**
- No dependency injection boilerplate
- Works across async contexts
- Easy to test (override time per test)

### Clock Injection via Dependency Injection

Alternative: Pass clock object to strategy handlers.

```python
class Clock:
    def now(self) -> datetime: pass

class BacktestClock(Clock):
    def __init__(self):
        self._time = datetime.min

    def advance(self, timestamp: datetime):
        self._time = timestamp

    def now(self) -> datetime:
        return self._time

strategy = MyStrategy(clock=BacktestClock())
```

**Best for:** Complex multi-timeframe strategies (separate clock per agent).

---

## 3. Grid Search Optimization

**Exhaustive parameter sweep:**

1. Define parameter ranges: `{ma_fast: [5,10,20], ma_slow: [50,100,200]}`
2. Generate all combinations: 3×3 = 9 grids
3. Run backtest for each combo
4. Rank by metric (Sharpe, max DD, etc.)

**Implementation:**
```python
from itertools import product

params = {
    'ma_fast': [5, 10, 20],
    'ma_slow': [50, 100, 200]
}

results = []
for ma_f, ma_s in product(params['ma_fast'], params['ma_slow']):
    equity, sharpe = run_backtest(ma_f, ma_s)
    results.append({'ma_fast': ma_f, 'ma_slow': ma_s, 'sharpe': sharpe})

best = max(results, key=lambda x: x['sharpe'])
```

**Coarse-to-fine strategy:** Start wide (step=20), then fine-tune winning region (step=2).

**Warning:** Combinatorial explosion (5 params × 10 values each = 100k combos). Use parallelization (`multiprocessing.Pool`, `ray.tune`).

---

## 4. Performance Metrics Calculation

### Core Metrics (Daily Return Series Required)

```python
import numpy as np
from scipy import stats

def calculate_metrics(returns: np.ndarray, rf_rate: float = 0.02):
    """Returns: daily returns array. rf_rate: annual risk-free rate."""

    # Annualization: 252 trading days/year
    annual_return = returns.mean() * 252
    annual_vol = returns.std() * np.sqrt(252)

    # Sharpe: excess return per unit risk
    sharpe = (annual_return - rf_rate) / annual_vol

    # Sortino: only downside volatility penalized
    downside = returns[returns < 0].std() * np.sqrt(252)
    sortino = (annual_return - rf_rate) / downside if downside > 0 else 0

    # Max Drawdown: peak-to-trough decline
    cumulative = (1 + returns).cumprod()
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    max_dd = np.min(drawdown)

    return {
        'sharpe': sharpe,
        'sortino': sortino,
        'max_drawdown': max_dd,
        'annual_return': annual_return,
        'annual_vol': annual_vol
    }
```

### Equity Curve Tracking

```python
def track_equity_curve(trades: list[dict]) -> np.ndarray:
    """Returns cumulative portfolio value."""
    equity = [1.0]  # Start at $1.00 (or $10k)

    for trade in trades:
        pnl = trade['entry_price'] * trade['quantity'] * (trade['exit_price'] - trade['entry_price'])
        new_equity = equity[-1] + pnl
        equity.append(new_equity)

    return np.array(equity)

# Returns array of values: [1.0, 1.05, 1.02, 1.15, ...]
```

**Key insight:** Preserve trade-by-trade equity for drawdown analysis, not just daily aggregates.

---

## 5. Python Asyncio for High-Speed Replay

### Async Generator Pattern (Recommended)

Stream OHLCV bars efficiently without buffering entire dataset:

```python
async def bar_stream(bars: list[OHLCVBar]):
    """Async generator yields bars with realistic inter-bar delays."""
    for bar in bars:
        yield bar
        await asyncio.sleep(0.001)  # 1ms per bar (simulated latency)

async def backtest_loop(bars: list[OHLCVBar], strategy):
    async for bar in bar_stream(bars):
        signal = await strategy.on_bar(bar)
        if signal:
            await execute_order(signal)
```

**Throughput:** ~1000 bars/sec with minimal memory overhead.

### Concurrent Symbol Processing

```python
async def process_symbols(symbols: list[str]):
    """Run multiple symbol backtests concurrently."""
    tasks = [
        run_strategy(symbol, params)
        for symbol in symbols
    ]
    results = await asyncio.gather(*tasks)
    return results

# 10 symbols in ~same time as 1 symbol
```

**Constraint:** GIL prevents true parallelism for CPU-bound logic (use `asyncio.to_thread` for Numba JIT).

---

## 6. Architecture Integration for PocketQuant

### Proposed Backtest Module

```
src/features/backtesting/
├── engine/
│   ├── backtest_engine.py       # Main event loop
│   ├── time_simulator.py        # ContextVar clock
│   └── order_manager.py         # Order execution
├── metrics/
│   ├── performance_calculator.py # Sharpe, Sortino, DD
│   └── equity_curve_tracker.py  # Trade-by-trade equity
├── optimization/
│   ├── grid_search.py           # Parameter sweep
│   └── optimizer.py             # Results ranking
└── models/
    ├── backtest_request.py      # API request DTO
    └── backtest_result.py       # Results DTO
```

### Event Flow Integration (DDD)

```python
# Domain: Pure strategy logic
class StrategyAggregate:
    def on_bar(self, bar: OHLCVBar) -> Signal | None:
        # Pure calculation, no I/O
        pass

# Application: CQRS handler
class RunBacktestHandler(Handler[RunBacktestCommand, BacktestResultDTO]):
    async def handle(self, cmd: RunBacktestCommand):
        bars = await self.market_repo.get_ohlcv(cmd.symbol, cmd.interval)
        equity_curve = []

        for bar in bars:
            set_simulation_time(bar.timestamp)
            signal = self.strategy.on_bar(bar)
            equity_curve.append(self.portfolio.get_value())

        metrics = calculate_metrics(np.diff(equity_curve))
        return BacktestResultDTO(metrics=metrics, equity_curve=equity_curve)
```

---

## Key Decisions for PocketQuant

| Decision | Recommendation | Rationale |
|----------|---|---|
| **Replay pattern** | Event-driven | Code reuse for live trading |
| **Time simulation** | ContextVar clock | Testable, minimal boilerplate |
| **Grid search** | Coarse-to-fine + Ray Tune | Parallelizable, memory-efficient |
| **Metrics lib** | Custom (numpy/pandas) | No external deps bloat; quantstats as optional |
| **Asyncio usage** | Async generator bars + concurrent symbols | Handles 10k+ bars/sec; IPC for multi-process |

---

## Unresolved Questions

1. **Order slippage modeling:** Fixed spread vs. realistic tick-based slippage?
2. **Portfolio blotter:** Single strategy vs. multi-leg positions tracking?
3. **Optimization constraints:** Max Sharpe vs. constraints on max DD or win rate?
4. **Persistence:** Store backtest results in MongoDB for comparison/replay?

---

## Sources

- [Event-Driven Backtesting with Python - Part I | QuantStart](https://www.quantstart.com/articles/Event-Driven-Backtesting-with-Python-Part-I/)
- [A Practical Breakdown of Vector-Based vs. Event-Based Backtesting](https://www.interactivebrokers.com/campus/ibkr-quant-news/a-practical-breakdown-of-vector-based-vs-event-based-backtesting/)
- [Build Your Own Event-Based Backtester in Python](https://srome.github.io/Build-Your-Own-Event-Based-Backtester-In-Python/)
- [Grid Search Optimization for Your Trading Strategy](https://alinakhay.com/p/grid-search-optimization-for-your)
- [Sharpe, Sortino and Calmar Ratios with Python | Codearmo](https://www.codearmo.com/blog/sharpe-sortino-and-calmar-ratios-python)
- [GitHub - nkaz001/hftbacktest](https://github.com/nkaz001/hftbacktest)
- [Event-Driven Backtesting with Python - Part VII | QuantStart](https://www.quantstart.com/articles/Event-Driven-Backtesting-with-Python-Part-VII/)
- [GitHub - AsyncAlgoTrading/aat](https://github.com/AsyncAlgoTrading/aat)
- [Concurrent Scalping Algo Using Async Python | Alpaca](https://alpaca.markets/learn/concurrent-scalping-algo-async-python/)
