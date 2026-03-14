# Brainstorm: Codebase Naming Simplification

**Date:** 2026-03-14 | **Branch:** feat/strategy-init | **Status:** Agreed

## Problem

Codebase has naming collisions and inconsistent suffixes making mental model hard to form:
- "Provider" means 3 different things (DI factory, data source, WebSocket manager)
- Application layer uses 5 suffixes (Engine, Manager, Tracker, Service, Runner) with no clear rule
- Layer boundaries unclear from names alone

## Agreed Decisions

### 1. Application Layer → `*AppService`

All application-layer orchestrators get uniform `AppService` suffix.

| Current Class | New Class | Current File | New File |
|---|---|---|---|
| `StrategyEngine` | `StrategyAppService` | `strategy_engine.py` | `strategy_app_service.py` |
| `OrderManager` | `OrderAppService` | `order_manager.py` | `order_app_service.py` |
| `PositionTracker` | `PositionAppService` | `position_tracker.py` | `position_app_service.py` |
| `QuoteService` | `QuoteAppService` | `quote_service.py` | `quote_app_service.py` |
| `BarManager` | `BarAppService` | `bar_manager.py` | `bar_app_service.py` |
| `BacktestRunner` | `BacktestAppService` | `backtest_runner.py` | `backtest_app_service.py` |
| `HistoricalReplayEngine` | `HistoricalReplayAppService` | `historical_replay_engine.py` | `historical_replay_app_service.py` |
| `GridOptimizer` | `GridOptimizationAppService` | `grid_optimizer.py` | `grid_optimization_app_service.py` |

### 2. Infrastructure External Callers → `*Client`

Anything calling an external service gets `Client` suffix.

| Current Class | New Class | Current File | New File |
|---|---|---|---|
| `TradingViewProvider` | `TradingViewClient` | `provider.py` | `tradingview_client.py` |
| `TradingViewWebSocketProvider` | `TradingViewWebSocketClient` | `websocket.py` | `tradingview_websocket_client.py` |

### 3. DI Folder → `src/di/`

| Current | New |
|---|---|
| `src/providers/` | `src/di/` |
| `src/providers/core_provider.py` | `src/di/core.py` |
| `src/providers/persistence_provider.py` | `src/di/persistence.py` |
| `src/providers/infrastructure_provider.py` | `src/di/infrastructure.py` |
| `src/providers/market_data_provider.py` | `src/di/market_data.py` |
| `src/providers/trading_provider.py` | `src/di/trading.py` |
| `src/providers/handler_provider.py` | `src/di/handlers.py` |
| `src/providers/__init__.py` | `src/di/__init__.py` |

DI classes keep `*Provider` suffix (Dishka convention). Folder disambiguates.

### 4. No Changes

These stay as-is:
- `Handler` suffix for CQRS handlers (27 total) — clear and consistent
- `Repository` suffix (7 total) — universally understood
- `Factory` suffix (`BrokerFactory`) — standard pattern
- `domain/` layer naming — no issues
- `features/` vertical slice structure — solid

## Impact

- ~60+ files need import updates
- All tests need import path updates
- `docs/system-architecture.md` and `docs/architecture-visual-map.md` need updates
- Single refactor commit, mark as `refactor:`

## Risks

| Risk | Mitigation |
|---|---|
| Mass import breakage | IDE refactor + grep verification + test suite |
| Git blame noise | One clean commit |
| File naming convention change | All Python files use snake_case (project standard) |

## Unresolved Questions

None — all decisions finalized.
