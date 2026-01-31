# Planner Report: OKX WebSocket & Backtest Integration

**Date:** 2026-01-31 | **Plan:** `plans/260131-2006-okx-websocket-backtest-integration/`

## Summary

Created comprehensive 6-phase implementation plan for two critical trading infrastructure features:

1. **Backtest Integration** (Phases 01-03) - Historical replay engine with grid optimizer
2. **OKX WebSocket** (Phases 04-06) - Real-time order/position updates with guaranteed delivery

## Plan Structure

```
plans/260131-2006-okx-websocket-backtest-integration/
├── plan.md                                    # Overview (P1, 16h total)
├── phase-01-backtest-foundation.md            # Replay engine, time sim (3h)
├── phase-02-backtest-metrics-persistence.md   # Metrics, MongoDB (2h)
├── phase-03-backtest-api-grid-optimizer.md    # API, grid search (3h)
├── phase-04-okx-websocket-client.md           # WS connection, auth (3h)
├── phase-05-okx-message-parsing-callbacks.md  # Message parsing (2h)
├── phase-06-okx-reconnection-sync.md          # Reconnection, REST sync (3h)
└── research/
    ├── researcher-01-okx-websocket-api.md
    └── researcher-02-backtest-patterns.md
```

## Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Replay pattern | Event-driven | Code reuse with live trading |
| Time simulation | ContextVar | No DI boilerplate, async-safe |
| Grid optimizer | asyncio.Semaphore | Control concurrency without threads |
| WS authentication | HMAC-SHA256 | OKX v5 API requirement |
| Guaranteed delivery | REST sync on reconnect | OKX has no sequence IDs |

## Files to Create (~1,200 LOC)

### Backtest Feature
- `src/common/time/simulation.py` (~30 LOC)
- `src/features/backtesting/engine/historical-replay-engine.py` (~100 LOC)
- `src/features/backtesting/engine/backtest-runner.py` (~80 LOC)
- `src/features/backtesting/models/backtest-config.py` (~50 LOC)
- `src/features/backtesting/models/backtest-result.py` (~60 LOC)
- `src/features/backtesting/metrics/performance-calculator.py` (~80 LOC)
- `src/features/backtesting/metrics/result-collector.py` (~100 LOC)
- `src/features/backtesting/repository/backtest-repository.py` (~80 LOC)
- `src/features/backtesting/optimizer/grid-optimizer.py` (~100 LOC)
- `src/features/backtesting/api/backtest-routes.py` (~80 LOC)
- CQRS commands/handlers (~200 LOC)

### OKX WebSocket Feature
- `src/infrastructure/brokers/okx/websocket/okx-websocket-client.py` (~150 LOC)
- `src/infrastructure/brokers/okx/websocket/okx-auth.py` (~40 LOC)
- `src/infrastructure/brokers/okx/websocket/okx-message-parser.py` (~60 LOC)
- `src/infrastructure/brokers/okx/websocket/okx-order-mapper.py` (~80 LOC)
- `src/infrastructure/brokers/okx/websocket/okx-position-mapper.py` (~60 LOC)
- `src/infrastructure/brokers/okx/websocket/okx-reconnection-handler.py` (~120 LOC)
- `src/infrastructure/brokers/okx/websocket/okx-state-reconciler.py` (~80 LOC)

## Success Criteria

- [ ] Replay 1 year 5min bars (105k bars) in <10 seconds
- [ ] Grid optimizer runs combinations in parallel
- [ ] Order fills reach callbacks within 500ms
- [ ] Auto-reconnect within 30 seconds of disconnect

## Priority Order

1. **Backtest first** - Enables strategy validation before capital risk
2. **OKX WebSocket second** - Required for live trading

## Leveraged Existing Code

- `PaperBroker.reset()` - Ready for backtest state clearing
- `StrategyEngine` - Already subscribes to BarCompletedEvent
- `OkxBroker` - REST API methods exist, placeholder WS listener
- `IBroker` interface - Consistent broker abstraction

## Unresolved Questions

1. Commission model - Flat BPS or tiered by volume?
2. Equity curve resolution - Every bar or only on trades?
3. Max concurrent backtests before MongoDB bottleneck?
4. OKX demo vs live endpoint differences?

---

**Plan Location:** `D:/w/_me/pocketquant/plans/260131-2006-okx-websocket-backtest-integration/plan.md`
