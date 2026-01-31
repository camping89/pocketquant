# Phase 01: Backtest Foundation

## Context Links

- Parent: [plan.md](./plan.md)
- Research: [researcher-02-backtest-patterns.md](./research/researcher-02-backtest-patterns.md)
- Existing: `src/infrastructure/brokers/paper/paper_broker.py` (has `reset()`)
- Existing: `src/features/strategy/engine/strategy_engine.py` (subscribes to BarCompletedEvent)

## Overview

| Field | Value |
|-------|-------|
| Priority | P1 - Critical |
| Status | pending |
| Estimate | 3h |

Core replay engine that loads historical OHLCV from MongoDB and emits synthetic BarCompletedEvent to drive StrategyEngine.

## Key Insights

1. **Event-driven replay** - Same handlers for backtest + live (code reuse)
2. **ContextVar clock** - No dependency injection boilerplate, works async
3. **PaperBroker ready** - Has `reset()` for backtest state clearing
4. **StrategyEngine ready** - Already subscribes to BarCompletedEvent

## Requirements

### Functional
- Load OHLCV bars from MongoDB by symbol, exchange, interval, date range
- Emit BarCompletedEvent for each bar in timestamp order
- Set simulated time context before each event
- Support configurable replay speed: 0 (max), 1x, 10x, 100x
- Single strategy per backtest run

### Non-Functional
- Replay 1 year 5min bars (105,120 bars) in <10 seconds at max speed
- Memory efficient: stream bars, don't load all in memory
- No lookahead bias: use bar close price only

## Architecture

```
BacktestRunner.run(config)
    │
    ├─ PaperBroker.reset()
    │
    ├─ Load OHLCV cursor from MongoDB
    │   └─ Filter: symbol, exchange, interval, start_date..end_date
    │
    └─ HistoricalReplayEngine.replay(cursor)
        │
        ├─ for bar in cursor:
        │   ├─ set_simulation_time(bar.timestamp)
        │   ├─ Calculate delay based on replay_speed
        │   ├─ Emit BarCompletedEvent → EventBus
        │   └─ StrategyEngine._on_bar_completed() triggered
        │
        └─ Return ReplayStats(bars_processed, duration)
```

### Time Simulation

```python
# src/common/time/simulation.py
from contextvars import ContextVar
from datetime import UTC, datetime

_simulated_time: ContextVar[datetime | None] = ContextVar("simulated_time", default=None)

def get_current_time() -> datetime:
    """Return simulated time if set, else real UTC time."""
    return _simulated_time.get() or datetime.now(UTC)

def set_simulation_time(ts: datetime) -> None:
    """Set simulated time for backtest."""
    _simulated_time.set(ts)

def clear_simulation_time() -> None:
    """Clear simulated time, return to real time."""
    _simulated_time.set(None)
```

## Related Code Files

### Create
| File | Purpose | LOC |
|------|---------|-----|
| `src/common/time/__init__.py` | Time module exports | ~5 |
| `src/common/time/simulation.py` | ContextVar time simulation | ~30 |
| `src/features/backtesting/__init__.py` | Feature module | ~5 |
| `src/features/backtesting/engine/__init__.py` | Engine submodule | ~5 |
| `src/features/backtesting/engine/historical-replay-engine.py` | Bar replay logic | ~100 |
| `src/features/backtesting/engine/backtest-runner.py` | Orchestrates single run | ~80 |
| `src/features/backtesting/models/backtest-config.py` | Config dataclasses | ~50 |

### Modify
| File | Change |
|------|--------|
| `src/infrastructure/brokers/paper/paper_broker.py` | Add `set_current_price()` for market orders |

## Implementation Steps

1. **Create time simulation module**
   - `src/common/time/simulation.py` with ContextVar
   - Export `get_current_time()`, `set_simulation_time()`, `clear_simulation_time()`

2. **Create BacktestConfig dataclass**
   ```python
   @dataclass
   class BacktestConfig:
       strategy_id: str
       symbol: str
       exchange: str
       interval: str
       start_date: date
       end_date: date
       initial_capital: float = 10_000.0
       slippage_bps: float = 10.0  # 0.1%
       replay_speed: float = 0.0  # 0 = max speed
   ```

3. **Create HistoricalReplayEngine**
   - Constructor takes EventBus
   - `async replay(config, ohlcv_cursor)` method
   - For each bar: set time, calculate delay, emit event
   - Return ReplayStats with bar count and duration

4. **Create BacktestRunner**
   - Constructor takes EventBus, StrategyEngine, PaperBroker, OHLCV repository
   - `async run(config)` orchestrates full backtest
   - Returns BacktestRun with metrics placeholder

5. **Update PaperBroker**
   - Add `_current_prices: dict[str, float]` for market price tracking
   - Add `set_current_price(symbol, price)` method
   - Update `_get_market_price()` to use tracked price

6. **Wire up in backtest runner**
   - Before each bar: `broker.set_current_price(symbol, bar.close)`
   - Ensures market orders fill at bar close

## Todo List

- [ ] Create `src/common/time/simulation.py`
- [ ] Create `src/features/backtesting/models/backtest-config.py`
- [ ] Create `src/features/backtesting/engine/historical-replay-engine.py`
- [ ] Create `src/features/backtesting/engine/backtest-runner.py`
- [ ] Update PaperBroker with price tracking
- [ ] Unit tests for time simulation
- [ ] Integration test: replay 100 bars, verify events emitted

## Success Criteria

- [ ] `set_simulation_time()` affects `get_current_time()` return
- [ ] HistoricalReplayEngine emits N events for N bars
- [ ] Events emitted in timestamp order
- [ ] Replay 105k bars in <10 seconds (max speed)
- [ ] PaperBroker market orders fill at bar close price

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| MongoDB cursor timeout on large datasets | Medium | High | Use batch fetching with skip/limit |
| Event loop blocked during replay | Low | High | Use `asyncio.sleep(0)` to yield periodically |
| Memory pressure from large results | Medium | Medium | Stream bars, don't buffer |

## Security Considerations

- No external API calls (local MongoDB only)
- No credentials involved
- Backtest runs isolated from live trading

## Next Steps

After this phase:
- Phase 02: Add metrics calculation and MongoDB persistence
- Phase 03: Add API endpoints and grid optimizer
