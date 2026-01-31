---
title: "OKX WebSocket & Backtest Integration"
description: "Add historical replay backtesting with grid optimizer and real-time OKX WebSocket for order/position updates"
status: pending
priority: P1
effort: 16h
branch: feat/strategy-init
tags: [backtest, websocket, okx, trading]
created: 2026-01-31
---

# OKX WebSocket & Backtest Integration

## Summary

Two critical infrastructure gaps:
1. **Backtest** - No historical replay capability to validate strategies
2. **OKX WebSocket** - Placeholder exists but never connects for real-time fills

## Architecture Overview

```
                    BACKTEST                              LIVE TRADING
                       │                                       │
                       ▼                                       ▼
┌─────────────────────────────────────┐  ┌─────────────────────────────────────┐
│  HistoricalReplayEngine             │  │  OkxWebSocketClient                 │
│  ├─ Load OHLCV from MongoDB         │  │  ├─ HMAC-SHA256 auth                │
│  ├─ Emit BarCompletedEvent          │  │  ├─ orders + positions channels     │
│  └─ Time simulation (ContextVar)    │  │  └─ Exponential backoff reconnect   │
└─────────────────┬───────────────────┘  └─────────────────┬───────────────────┘
                  │                                        │
                  └──────────────┬─────────────────────────┘
                                 ▼
                    ┌─────────────────────────────┐
                    │  StrategyEngine (existing)   │
                    │  └─ on_bar() → Signal → Broker│
                    └─────────────────────────────┘
```

## Phases

| Phase | Name | Status | Est. |
|-------|------|--------|------|
| 01 | [Backtest Foundation](./phase-01-backtest-foundation.md) | pending | 3h |
| 02 | [Backtest Metrics & Persistence](./phase-02-backtest-metrics-persistence.md) | pending | 2h |
| 03 | [Backtest API & Grid Optimizer](./phase-03-backtest-api-grid-optimizer.md) | pending | 3h |
| 04 | [OKX WebSocket Client](./phase-04-okx-websocket-client.md) | pending | 3h |
| 05 | [OKX Message Parsing & Callbacks](./phase-05-okx-message-parsing-callbacks.md) | pending | 2h |
| 06 | [OKX Reconnection & Sync](./phase-06-okx-reconnection-sync.md) | pending | 3h |

## Priority Order

1. **Backtest first** - Enables strategy validation before risking capital
2. **OKX WebSocket second** - Required for live trading

## Dependencies

- MongoDB with OHLCV data (exists)
- PaperBroker with `reset()` (exists)
- StrategyEngine subscribes to BarCompletedEvent (exists)
- python-okx SDK (exists in deps)

## Success Criteria

- [ ] Replay 1 year 5min bars in <10 seconds
- [ ] Grid optimizer runs in parallel
- [ ] Order fills reach on_fill() within 500ms
- [ ] Auto-reconnect within 30s of disconnect

## Related Files

- Research: `./research/researcher-01-okx-websocket-api.md`
- Research: `./research/researcher-02-backtest-patterns.md`
- Brainstorm: `plans/reports/brainstorm-260131-1953-okx-websocket-backtest-integration.md`

---

## Validation Summary

**Validated:** 2026-01-31
**Questions asked:** 6

### Confirmed Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Equity curve sampling | Every trade only | Smaller data, accurate drawdown calculation |
| Commission model | Flat BPS (10 = 0.1%) | Simple, matches brainstorm spec |
| Failed backtests | Persist with error details | Debugging and audit trail |
| Grid optimizer limit | 1,000 combinations max | Prevent runaway resource usage |
| OKX endpoint default | Configurable via `OKX_DEMO` env var | Flexible deployment |
| Reconnection strategy | Unlimited with circuit breaker | Keep trying, pause 5min after 10 consecutive failures |

### Action Items

- [ ] Phase 02: Update equity curve to record only on position changes
- [ ] Phase 02: Add `commission_bps` to BacktestConfig (default 10)
- [ ] Phase 02: Add `status: failed` with `error_message` field to BacktestRun
- [ ] Phase 03: Add validation: reject if combinations > 1,000
- [ ] Phase 04: Read `OKX_DEMO` env var to set demo/live endpoint
- [ ] Phase 06: Add circuit breaker (10 failures → 5min pause)
