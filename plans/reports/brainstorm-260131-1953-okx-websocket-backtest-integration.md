# Brainstorm: OKX WebSocket & Backtest Integration

**Date:** 2026-01-31 | **Status:** Agreed | **Branch:** feat/strategy-init

---

## Problem Statement

Two critical gaps in PocketQuant's trading infrastructure:

1. **OKX WebSocket** - Placeholder implementation exists but never connects. Strategies can't receive real-time order fills, limiting live trading viability.

2. **Backtest Integration** - No historical replay capability. Cannot validate strategies against past data or optimize parameters before deploying capital.

---

## Requirements Summary

| Feature | Requirement |
|---------|-------------|
| **WS Events** | Orders + Positions (fills, cancels, position updates) |
| **WS Reliability** | Guaranteed delivery with sequence tracking, REST sync on reconnect |
| **Backtest Mode** | Parameter optimization via grid search |
| **Backtest Speed** | Configurable (1x, 10x, 100x, max) |
| **Data Source** | Existing MongoDB OHLCV only |
| **Multi-Strategy** | Single strategy per backtest |
| **Results Storage** | MongoDB persistence for historical comparison |

---

## Feature 1: OKX WebSocket Implementation

### Current State
- `okx_broker.py:283-301` - Empty placeholder loop
- Callback infrastructure exists (`_notify_callbacks`, `OrderResult`)
- Uses `python-okx` SDK (has WebSocket support)

### Approach: Full WebSocket with Guaranteed Delivery

**Architecture:**
```
OKX Private WebSocket (wss://ws.okx.com:8443/ws/v5/private)
    ↓
OkxWebSocketClient (new class)
    ├─ Login with HMAC-SHA256 signature
    ├─ Subscribe: orders, positions channels
    ├─ Sequence tracking per channel
    └─ Heartbeat/ping-pong
        ↓
Message Parser
    ├─ Order updates → OrderResult → _notify_callbacks()
    └─ Position updates → PositionUpdate → new callback
        ↓
Reconnection Handler
    ├─ Exponential backoff (1s, 2s, 4s... max 30s)
    ├─ Detect sequence gaps
    └─ REST sync on reconnect (fetch open orders + positions)
```

**Key Components:**

| Component | Responsibility |
|-----------|----------------|
| `OkxWebSocketClient` | Connection lifecycle, auth, subscriptions |
| `OkxMessageParser` | JSON parsing, map OKX format to domain models |
| `OkxReconnectionHandler` | Backoff logic, gap detection, REST sync |
| `SequenceTracker` | Track `seqId` per channel, detect gaps |

**OKX Message Format (orders channel):**
```json
{
  "arg": {"channel": "orders", "instType": "SWAP"},
  "data": [{
    "instId": "BTC-USDT-SWAP",
    "ordId": "312269865356374016",
    "clOrdId": "b1",
    "state": "filled",
    "fillPx": "50000",
    "fillSz": "0.01",
    "avgPx": "50000",
    "seqId": 1
  }]
}
```

**State Mapping:**
| OKX State | Domain OrderStatus |
|-----------|-------------------|
| `live` | SUBMITTED |
| `partially_filled` | PARTIALLY_FILLED |
| `filled` | FILLED |
| `canceled` | CANCELLED |

**Reconnection Protocol:**
1. Detect disconnect (ping timeout or socket error)
2. Clear subscription state
3. Exponential backoff reconnect
4. Re-authenticate
5. Fetch open orders via REST (`/api/v5/trade/orders-pending`)
6. Fetch positions via REST (`/api/v5/account/positions`)
7. Sync local state with REST response
8. Re-subscribe to channels
9. Resume sequence tracking

**Files to Modify/Create:**
| File | Action | LOC Est. |
|------|--------|----------|
| `okx_broker.py` | Modify `_ws_listener()` | ~50 |
| `okx_websocket_client.py` | New | ~150 |
| `okx_message_parser.py` | New | ~80 |
| `okx_reconnection_handler.py` | New | ~100 |

**Risks & Mitigations:**
| Risk | Mitigation |
|------|------------|
| Rate limits (480 ops/hour) | Batch subscriptions, avoid reconnect storms |
| Message ordering during reconnect | Sequence tracking + REST sync before resume |
| Auth signature errors | Unit test HMAC generation against known vectors |

---

## Feature 2: Backtest Integration

### Current State
- No backtest infrastructure
- Paper broker has `reset()` method (ready for backtest)
- MongoDB stores OHLCV bars from real-time collection
- Strategy engine expects async event flow

### Approach: Historical Replay Engine with Grid Optimizer

**Architecture:**
```
POST /backtest/run
    ↓
BacktestRunner
    ├─ Load OHLCV from MongoDB (date range)
    ├─ Configure PaperBroker (reset, slippage, fees)
    ├─ Initialize StrategyEngine
    └─ Start HistoricalReplayEngine
        ↓
HistoricalReplayEngine
    ├─ Iterate bars in timestamp order
    ├─ Set simulated time context
    ├─ Emit synthetic BarCompleted events
    └─ Control replay speed (delay between bars)
        ↓
StrategyEngine (existing)
    ├─ on_bar() → Signal
    ├─ _process_signal() → Order
    └─ PaperBroker.submit_order()
        ↓
BacktestResultCollector
    ├─ Track equity curve (per bar)
    ├─ Record all trades
    ├─ Calculate metrics (Sharpe, drawdown, win rate)
    └─ Persist to MongoDB
```

**Grid Optimizer Flow:**
```
POST /backtest/optimize
    ↓
GridOptimizer
    ├─ Parse parameter ranges from config
    ├─ Generate all combinations
    └─ For each combination (parallel):
        ├─ Clone strategy config with params
        ├─ Run BacktestRunner
        └─ Collect results
            ↓
OptimizationResult
    ├─ Best params by metric (Sharpe, return, etc.)
    ├─ Full results grid
    └─ Persist to MongoDB
```

**Key Components:**

| Component | Responsibility |
|-----------|----------------|
| `HistoricalReplayEngine` | Load bars, emit events, time control |
| `BacktestRunner` | Orchestrate single backtest run |
| `BacktestResultCollector` | Equity curve, trades, metrics |
| `GridOptimizer` | Parameter grid generation, parallel runs |
| `BacktestConfig` | Date range, capital, slippage, params |

**Time Simulation:**
```python
# Context var for simulated time
simulated_time: ContextVar[datetime | None] = ContextVar("simulated_time", default=None)

def get_current_time() -> datetime:
    """Return simulated time if in backtest, else real time."""
    sim = simulated_time.get()
    return sim if sim else datetime.now(UTC)
```

**Backtest Config Schema:**
```python
@dataclass
class BacktestConfig:
    strategy_id: str
    start_date: date
    end_date: date
    initial_capital: float = 10_000.0
    slippage_bps: float = 10.0  # 0.1%
    commission_bps: float = 10.0  # 0.1%
    replay_speed: float = 0.0  # 0 = max speed

@dataclass
class OptimizationConfig(BacktestConfig):
    parameter_grid: dict[str, list[Any]]
    target_metric: str = "sharpe_ratio"
    max_workers: int = 4
```

**Replay Speed Implementation:**
| Speed | Delay Between Bars |
|-------|-------------------|
| 0 (max) | No delay |
| 1x | Actual bar interval (5min = 5min delay) |
| 10x | Interval / 10 |
| 100x | Interval / 100 |

**Metrics Calculated:**
- Total return (%)
- CAGR
- Sharpe ratio
- Sortino ratio
- Max drawdown (%)
- Win rate (%)
- Profit factor
- Total trades
- Avg trade duration

**MongoDB Collections:**
```
backtest_runs:
  - _id: ObjectId
  - strategy_id: str
  - config: BacktestConfig
  - started_at: datetime
  - completed_at: datetime
  - status: "running" | "completed" | "failed"
  - metrics: dict
  - equity_curve: list[{timestamp, equity}]
  - trades: list[Trade]

optimization_runs:
  - _id: ObjectId
  - strategy_id: str
  - config: OptimizationConfig
  - results: list[{params, metrics}]
  - best_params: dict
  - best_metrics: dict
```

**API Endpoints:**
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/backtest/run` | POST | Execute single backtest |
| `/backtest/optimize` | POST | Run grid optimization |
| `/backtest/{id}` | GET | Get backtest results |
| `/backtest/{id}/equity` | GET | Get equity curve data |
| `/optimization/{id}` | GET | Get optimization results |

**Files to Create:**
| File | Purpose | LOC Est. |
|------|---------|----------|
| `historical_replay_engine.py` | Bar replay, time control | ~120 |
| `backtest_runner.py` | Single run orchestration | ~100 |
| `backtest_result_collector.py` | Metrics, equity tracking | ~150 |
| `grid_optimizer.py` | Parameter grid, parallel runs | ~100 |
| `backtest_config.py` | Config dataclasses | ~50 |
| `backtest_repository.py` | MongoDB persistence | ~80 |
| `backtest_handlers.py` | API handlers | ~100 |

**Risks & Mitigations:**
| Risk | Mitigation |
|------|------------|
| Look-ahead bias | Strictly use bar close price, no future data |
| Survivorship bias | Data already in DB, user responsibility |
| Overfitting on grid search | Document best practices, consider walk-forward later |
| Memory pressure on long backtests | Stream results to MongoDB, don't hold all bars |

---

## Implementation Priority

**Phase 1: Backtest Foundation (Higher ROI)**
- Historical replay engine
- Single backtest runner
- Basic metrics + persistence
- API endpoints

**Phase 2: OKX WebSocket**
- WebSocket client with auth
- Message parser
- Order/position callbacks
- Basic reconnection

**Phase 3: Advanced Features**
- Grid optimizer
- Guaranteed delivery (sequence tracking)
- REST sync on reconnect

**Rationale:** Backtest first because:
1. Enables strategy validation before risking capital
2. Grid optimization finds optimal params
3. Uses existing PaperBroker + StrategyEngine
4. Lower risk than live WebSocket integration

---

## Success Criteria

### OKX WebSocket
- [ ] Real-time order fills reach strategy `on_fill()` within 500ms
- [ ] Position updates reflect after every fill
- [ ] Reconnects automatically within 30s of disconnect
- [ ] No missed events after reconnect (verified by REST sync)
- [ ] Handles 480 ops/hour rate limit without errors

### Backtest Integration
- [ ] Replays 1 year of 5min bars in <10 seconds (max speed)
- [ ] Equity curve matches manual calculation on sample data
- [ ] Grid optimization runs N combinations in parallel
- [ ] Results persist and queryable via API
- [ ] Configurable speed (1x, 10x, 100x, max) works correctly

---

## Dependencies

### OKX WebSocket
- `python-okx` SDK WebSocket support
- OKX API credentials (existing in env)
- Stable network connection

### Backtest
- MongoDB with OHLCV data populated
- Strategy YAML configs
- PaperBroker reset capability (exists)

---

## Unresolved Questions

1. **Position channel format** - Need to verify OKX `positions` channel message structure
2. **Parallel optimization workers** - How many concurrent backtests before MongoDB bottleneck?
3. **Commission model** - Flat BPS or tiered based on volume?
4. **Equity curve resolution** - Every bar or only on trades?

---

## Agreed Solution Summary

| Feature | Approach |
|---------|----------|
| OKX WebSocket | Full implementation with guaranteed delivery, REST sync on reconnect |
| Backtest | Historical replay engine with grid optimizer, MongoDB persistence |
| Priority | Backtest first, then WebSocket |
| Complexity | Moderate - leverages existing broker/strategy abstractions |

**Estimated Total LOC:** ~1,200 across 12 files
