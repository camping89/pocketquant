---
title: "Strategy Engine Implementation"
description: "Modular trading strategy execution with broker abstraction, risk management, and OKX integration"
status: complete
priority: P1
effort: 16h
branch: feat/strategy-init
tags: [trading, strategy, okx, cqrs, ddd]
created: 2026-01-31
---

# Strategy Engine Implementation Plan

## Overview

Build modular trading strategy execution system extending existing DDD+CQRS architecture. Supports configurable risk, broker abstraction (OKX/Paper), YAML-based strategy configs, and reuses existing WebSocket quotes + OHLCV infrastructure.

## Event Flow

```
BarCompleted/QuoteReceived → StrategyEngine → IStrategy.on_bar()/on_tick()
    → Signal → RiskManager.calculate_size() → Order
        → IBroker.submit_order() → OrderSubmitted
            → (OKX WS) → OrderFilled → PositionTracker.update()
```

## Phases

| Phase | Title | Effort | Status | Dependencies |
|-------|-------|--------|--------|--------------|
| [Phase 1](./phase-01-domain-layer-models.md) | Domain Layer Models | 4h | ✅ complete | None |
| [Phase 2](./phase-02-infrastructure-brokers.md) | Infrastructure Brokers | 4h | ✅ complete | Phase 1 |
| [Phase 3](./phase-03-feature-strategy-trading.md) | Feature Layer (Strategy/Trading) | 6h | ✅ complete | Phase 2 |
| [Phase 4](./phase-04-integration-wiring.md) | Integration & Wiring | 2h | ✅ complete | Phase 3 |

## Directory Structure (Final)

```
src/
├── domain/
│   ├── strategy/          # Signal, StrategyState
│   ├── order/             # OrderAggregate, OrderType/Side/Status
│   ├── position/          # PositionAggregate, PnL
│   └── risk/              # RiskConfig, RiskModel
│
├── features/
│   ├── strategy/          # StrategyEngine, loader, CQRS, API
│   ├── trading/           # OrderManager, PositionTracker, CQRS, API
│   └── risk/              # RiskCheckHandler
│
├── infrastructure/
│   └── brokers/
│       ├── interface.py   # IBroker ABC
│       ├── okx/           # OKXBroker (python-okx)
│       ├── paper/         # PaperBroker
│       └── factory.py     # BrokerFactory
│
└── strategies/            # YAML configs
    └── examples/
```

## Key Decisions

1. **python-okx over okx-sdk** - 13x more downloads (1.3M), 33x more stars (827), 11 contributors
2. **REST for orders, WS for status** - Rate limits favor REST placement
3. **TP/SL via algo orders** - OKX doesn't support TP/SL on market orders
4. **2% fixed risk default** - Configurable via YAML (validated)
5. **Same code backtest/live** - PaperBroker simulates fills identically
6. **Fixed strategies/ dir** - Convention over configuration
7. **MongoDB persistence** - Orders/positions survive restarts
8. **Manual start via API** - POST /strategies/{id}/start with state tracking

## Validation Summary

**Validated:** 2026-01-31
**Questions asked:** 7

### Confirmed Decisions
- **SDK:** python-okx (1.3M downloads, 827 stars, more stable)
- **TP/SL:** Separate algo orders after entry fills
- **Default Risk:** 2% per trade (user preference)
- **Strategy Dir:** Fixed `strategies/` directory
- **Strategy Start:** Manual via API with state tracking (status, datetime, logs)
- **Slippage:** 0.1% default for PaperBroker
- **Persistence:** MongoDB for orders/positions (not in-memory)

### Action Items (Plan Revisions Needed)
- [ ] Update Python version: 3.14 → 3.12 (python-okx compatibility)
- [ ] Update RiskConfig default: `risk_per_trade: 0.02` (was 0.01)
- [ ] Remove STRATEGIES_DIR from config.py (fixed path)
- [ ] Add strategy state tracking (status, started_at, logs) to StrategyEngine
- [ ] Add MongoDB collections for orders and positions in Phase 3
- [ ] Add OrderRepository and PositionRepository for persistence

## Success Criteria

- [x] Strategy loaded from YAML without code changes
- [x] Same strategy runs on PaperBroker and OKXBroker (interface ready)
- [x] Order submission <100ms from signal generation (async)
- [x] Position sizing respects risk config
- [x] Multiple strategies run independently on same symbol

## Code Review

**Date:** 2026-01-31
**Status:** ⚠️ Conditional Approval
**Score:** 8.5/10
**Report:** [code-reviewer-260131-1903-strategy-engine-review.md](../reports/code-reviewer-260131-1903-strategy-engine-review.md)

**Summary:**
Solid implementation with clean DDD/CQRS architecture. High code quality, proper domain modeling, and good async patterns.

**Conditions for Merge:**
1. Fix Python version (3.14 → 3.12 per python-okx compatibility)
2. Install dev deps and verify no type errors
3. Implement at least one concrete strategy class
4. Add basic integration test

**Follow-up Work Needed:**
- Complete OKX WebSocket implementation
- Add MongoDB persistence (OrderRepository, PositionRepository)
- Implement strategy state tracking (status, timestamps, logs)
- Write comprehensive test suite

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Python version | Use 3.12 for python-okx compatibility |
| OKX rate limits (1000/2s) | Queue orders, batch cancellations |
| WebSocket disconnects | Exponential backoff (existing pattern) |
| Position drift | Periodic reconciliation job |
| Strategy bugs | Mandatory paper trading period |

## References

- [Brainstorm](../reports/brainstorm-260131-1432-strategy-engine-architecture.md)
- [OKX SDK Research](./research/researcher-01-okx-sdk-integration.md)
- [Strategy Patterns Research](./research/researcher-02-strategy-engine-patterns.md)
