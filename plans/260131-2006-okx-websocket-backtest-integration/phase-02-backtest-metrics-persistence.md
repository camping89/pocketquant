# Phase 02: Backtest Metrics & Persistence

## Context Links

- Parent: [plan.md](./plan.md)
- Depends on: [phase-01-backtest-foundation.md](./phase-01-backtest-foundation.md)
- Research: [researcher-02-backtest-patterns.md](./research/researcher-02-backtest-patterns.md)

## Overview

| Field | Value |
|-------|-------|
| Priority | P1 - Critical |
| Status | pending |
| Estimate | 2h |

Track equity curve, calculate performance metrics (Sharpe, Sortino, max DD), persist results to MongoDB.

## Key Insights

1. **Trade-by-trade equity** - Required for accurate drawdown, not just daily aggregates
2. **NumPy for metrics** - Fast vectorized calculation, no external deps
3. **Subscribe to OrderResult** - PaperBroker emits fills via callbacks
4. **Annualization** - 252 trading days for equities, 365 for crypto

## Requirements

### Functional
- Track equity value after each trade
- Calculate: total return, CAGR, Sharpe, Sortino, max drawdown, win rate, profit factor
- Record all trades with entry/exit details
- Persist backtest run to MongoDB
- Query historical runs by strategy_id

### Non-Functional
- Metrics calculation <100ms for 1000 trades
- MongoDB writes non-blocking (fire and forget OK)

## Architecture

```
BacktestResultCollector
    │
    ├─ on_order_filled(OrderResult)
    │   ├─ Update equity curve
    │   ├─ Record trade details
    │   └─ Track win/loss
    │
    └─ finalize() → BacktestResult
        ├─ Calculate metrics (NumPy)
        └─ Return complete result

BacktestRepository
    │
    ├─ save(BacktestRun) → ObjectId
    ├─ get(run_id) → BacktestRun
    └─ list_by_strategy(strategy_id) → list[BacktestRunSummary]
```

### Metrics Formulas

```python
# Annualized return: compound daily returns
annual_return = (final_equity / initial_equity) ** (365 / days) - 1

# Sharpe ratio: excess return / volatility
daily_returns = np.diff(equity_curve) / equity_curve[:-1]
sharpe = (daily_returns.mean() * 365 - rf_rate) / (daily_returns.std() * np.sqrt(365))

# Sortino: only penalize downside volatility
downside = daily_returns[daily_returns < 0]
sortino = (annual_return - rf_rate) / (downside.std() * np.sqrt(365))

# Max drawdown: largest peak-to-trough decline
cummax = np.maximum.accumulate(equity_curve)
drawdown = (equity_curve - cummax) / cummax
max_dd = drawdown.min()

# Win rate: winning trades / total trades
win_rate = wins / total_trades

# Profit factor: gross profit / gross loss
profit_factor = gross_profit / abs(gross_loss)
```

## Related Code Files

### Create
| File | Purpose | LOC |
|------|---------|-----|
| `src/features/backtesting/metrics/performance-calculator.py` | Sharpe, Sortino, DD | ~80 |
| `src/features/backtesting/metrics/result-collector.py` | Equity tracking | ~100 |
| `src/features/backtesting/models/backtest-result.py` | Result dataclasses | ~60 |
| `src/features/backtesting/repository/backtest-repository.py` | MongoDB persistence | ~80 |

### Modify
| File | Change |
|------|--------|
| `src/features/backtesting/engine/backtest-runner.py` | Integrate collector, persist results |

## Implementation Steps

1. **Create BacktestResult models**
   ```python
   @dataclass
   class TradeRecord:
       order_id: str
       symbol: str
       side: str  # BUY/SELL
       quantity: float
       entry_price: float
       exit_price: float | None
       pnl: float
       timestamp: datetime

   @dataclass
   class BacktestMetrics:
       total_return: float
       cagr: float
       sharpe_ratio: float
       sortino_ratio: float
       max_drawdown: float
       win_rate: float
       profit_factor: float
       total_trades: int
       avg_trade_duration: timedelta

   @dataclass
   class BacktestRun:
       id: str
       strategy_id: str
       config: BacktestConfig
       metrics: BacktestMetrics
       equity_curve: list[tuple[datetime, float]]
       trades: list[TradeRecord]
       started_at: datetime
       completed_at: datetime
       status: str  # running, completed, failed
   ```

2. **Create PerformanceCalculator**
   - Static methods for each metric
   - Input: equity curve as numpy array
   - Handle edge cases: no trades, all wins/losses

3. **Create BacktestResultCollector**
   - Constructor: initial_capital
   - `on_fill(result: OrderResult)` - callback for PaperBroker
   - Track open positions for PnL calculation
   - `finalize() -> BacktestResult`

4. **Create BacktestRepository**
   - Collection: `backtest_runs`
   - `save(run)` - upsert by run.id
   - `get(run_id)` - fetch single run
   - `list_by_strategy(strategy_id, limit=20)` - recent runs

5. **Update BacktestRunner**
   - Create collector before run
   - Subscribe collector to broker callbacks
   - Call `collector.finalize()` after replay
   - Persist via repository

## Todo List

- [ ] Create `src/features/backtesting/models/backtest-result.py`
- [ ] Create `src/features/backtesting/metrics/performance-calculator.py`
- [ ] Create `src/features/backtesting/metrics/result-collector.py`
- [ ] Create `src/features/backtesting/repository/backtest-repository.py`
- [ ] Update backtest-runner.py with collector integration
- [ ] Unit tests for metrics (known input/output)
- [ ] Integration test: verify MongoDB persistence

## Success Criteria

- [ ] Sharpe ratio matches manual calculation on sample data
- [ ] Max drawdown accurate to 0.01%
- [ ] Backtest runs persist to MongoDB
- [ ] Can query runs by strategy_id
- [ ] Equity curve has entry per trade

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Division by zero in metrics | Medium | Low | Guard with if-checks, return 0 |
| Large equity curves exceed BSON limit | Low | Medium | Store sampled curve (every Nth point) |
| Position tracking mismatch | Medium | High | Unit test with known trade sequences |

## Security Considerations

- No external APIs
- MongoDB local only
- No sensitive data in results

## Next Steps

After this phase:
- Phase 03: Add REST API endpoints and grid optimizer
