# Phase 4: Verify & Update Docs

**Priority:** Medium
**Status:** completed
**Depends on:** Phases 1-3 completed

## Overview

Verify the refactor compiles and passes tests, then update all documentation files that reference old names.

## Step 1: Verification

```bash
ruff check src/ tests/
pyright src/
pytest
```

All three must pass before proceeding to doc updates.

## Step 2: Documentation Files to Update

### `docs/system-architecture.md` (~30 replacements)

| Old Name | New Name |
|---|---|
| `StrategyEngine` | `StrategyAppService` |
| `BacktestRunner` | `BacktestAppService` |
| `BarManager` | `BarAppService` |
| `OrderManager` | `OrderAppService` |
| `PositionTracker` | `PositionAppService` |
| `QuoteService` | `QuoteAppService` |
| `GridOptimizer` | `GridOptimizationAppService` |
| `HistoricalReplayEngine` | `HistoricalReplayAppService` |
| `TradingViewProvider` | `TradingViewClient` |
| `TradingViewWebSocketProvider` | `TradingViewWebSocketClient` |
| `src/providers/` | `src/di/` |
| `handler_provider.py` | `handlers.py` |
| `core_provider.py` | `core.py` |
| `persistence_provider.py` | `persistence.py` |
| `infrastructure_provider.py` | `infrastructure.py` |
| `market_data_provider.py` | `market_data.py` |
| `trading_provider.py` | `trading.py` |

Also update file tree listings and file path references:
- `strategy_engine.py` -> `strategy_app_service.py`
- `backtest_runner.py` -> `backtest_app_service.py`
- `bar_manager.py` -> `bar_app_service.py`
- `order_manager.py` -> `order_app_service.py`
- `position_tracker.py` -> `position_app_service.py`
- `quote_service.py` -> `quote_app_service.py`
- `grid_optimizer.py` -> `grid_optimization_app_service.py`
- `historical_replay_engine.py` -> `historical_replay_app_service.py`
- `provider.py` (tradingview) -> `tradingview_client.py`
- `websocket.py` (tradingview) -> `tradingview_websocket_client.py`

### `docs/architecture-visual-map.md` (~40 replacements)

Same class name replacements as above, plus:
- Mermaid diagram node labels and IDs
- DI subgraph label: `src/providers/` -> `src/di/`
- Sequence diagram participant names
- Suffix table at the bottom

### `docs/codebase-summary.md` (~35 replacements)

Same class/file name replacements, plus:
- Section headers referencing old names
- Directory tree listings
- Provider section: `src/providers/` -> `src/di/`

### `docs/code-standards.md` (~25 replacements)

Same class/file name replacements, plus:
- Code examples showing class definitions
- DI provider references: `src/providers/` -> `src/di/`
- File tree examples

### `docs/handler-pipelines.md` (~30 replacements)

Same class name replacements in pipeline descriptions.

### `docs/project-overview-pdr.md` (~10 replacements)

Same class name replacements in architecture overview.

### `docs/README.md` (~5 replacements)

Module breakdown and flow descriptions.

## Step 3: Suffix Naming Table Update

In `docs/architecture-visual-map.md`, update the suffix convention table:

```markdown
| Suffix | Layer | Purpose | Count |
|--------|-------|---------|-------|
| `AppService` | Application | Stateful orchestrator | 8 |
| `Client` | Infrastructure | External service caller | 2 |
| `Handler` | Features | CQRS command/query handler | 27 |
| `Repository` | Persistence | Data access | 7 |
| `Factory` | Infrastructure | Object creation | 1 |
| `Provider` | DI | Dishka dependency provider | 6 |
```

## Todo

- [x] Run `ruff check src/ tests/`
- [x] Run `pyright src/`
- [x] Run `pytest` -- all pass
- [x] Update `docs/system-architecture.md`
- [x] Update `docs/architecture-visual-map.md`
- [x] Update `docs/codebase-summary.md`
- [x] Update `docs/code-standards.md`
- [x] Update `docs/handler-pipelines.md`
- [x] Update `docs/project-overview-pdr.md`
- [x] Update `docs/README.md`
- [x] Final grep: confirm zero old-name references in `src/` and `docs/`

## Success Criteria

- `ruff check` + `pyright` + `pytest` all green
- `grep -r "StrategyEngine\|OrderManager\|PositionTracker\|BarManager\|BacktestRunner\|GridOptimizer\|HistoricalReplayEngine\|TradingViewProvider\|TradingViewWebSocketProvider\|src/providers" docs/` returns zero matches
- `grep -r "src\.providers\|src/providers" src/ tests/` returns zero matches
- Docs are internally consistent (no broken references)
