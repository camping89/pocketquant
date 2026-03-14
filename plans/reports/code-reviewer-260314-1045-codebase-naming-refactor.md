# Code Review: Codebase Naming Refactor

**Date:** 2026-03-14 | **Branch:** `feat/strategy-init`

## Scope

- **Refactor 1:** `src/providers/` -> `src/di/` (folder + 6 file renames, dropping `_provider` suffix)
- **Refactor 2:** 8 application services to `*AppService` suffix
- **Refactor 3:** 2 infrastructure classes to `*Client` suffix
- **Review method:** grep/glob for all old names across `src/`, `tests/`, `testscripts/`, `docs/`, config files

## Overall Assessment

**CLEAN.** The rename was executed thoroughly across all source code. Zero stale references in `src/`, `tests/`, or `testscripts/`. DI providers resolve new class names correctly. `__init__.py` re-exports are consistent. Pyright reports 7 pre-existing errors (none related to the refactor). Ruff reports 1 pre-existing style issue.

---

## Critical Issues

None.

## High Priority

None.

## Medium Priority: Stale References in Non-Source Files

### 1. README.md -- 5 stale references to old class names

| Line | Old Name | Should Be |
|------|----------|-----------|
| 64 | `StrategyEngine, BacktestRunner` | `StrategyAppService, BacktestAppService` |
| 68 | `BacktestRunner, GridOptimizer` | `BacktestAppService, GridOptimizationAppService` |
| 69 | `BarManager` | `BarAppService` |
| 70 | `StrategyEngine` | `StrategyAppService` |
| 71 | `OrderManager, PositionTracker` | `OrderAppService, PositionAppService` |

### 2. TODO.md -- 3 stale references

| Line | Old Name | Should Be |
|------|----------|-----------|
| 12 | `TradingViewProvider.fetch_ohlcv()` | `TradingViewClient.fetch_ohlcv()` |
| 100 | `PositionTracker` | `PositionAppService` |
| 109 | `OrderManager` | `OrderAppService` |

### 3. Agent memory file -- stale `src/providers/` paths and old class names

File: `.claude/agent-memory/code-reviewer/project_dishka_di.md`

- Line 7: `src/providers/` -> `src/di/`
- Lines 13-16: old file paths and old class names (OrderManager, PositionTracker, StrategyEngine)

### 4. Plans directory -- many stale references (historical, not actionable)

Old plan files under `plans/260313-*` and `plans/260215-*` contain extensive old-name references. These are historical records of past plans and do not affect runtime. **No action needed** -- updating them would be churn with no value.

## Low Priority

### 5. Structlog event strings still use old names

These are internal log event keys. Changing them would break log queries and dashboards. Flagged for awareness only.

| File | Logger Event |
|------|-------------|
| `src/application/market_data/bar_app_service.py:106` | `"bar_manager.bar_saved"` |
| `src/application/market_data/bar_app_service.py:149` | `"bar_manager.bars_flushed"` |
| `src/application/market_data/quote_app_service.py:70` | `"quote_service.tick_received"` |
| `src/application/strategy/strategy_app_service.py:69` | `"strategy_engine_started"` |
| `src/application/strategy/strategy_app_service.py:85` | `"strategy_engine_stopped"` |
| `src/application/trading/position_app_service.py:33` | `"position_tracker_started"` |
| `src/application/trading/position_app_service.py:45` | `"position_tracker_stopped"` |
| `src/features/market_data/quotes/*/handler.py` | `"quote_service.*"` (6 events) |

### 6. Variable name `provider` in SyncSymbolHandler

`src/features/market_data/sync/sync_one/handler.py:29` -- param `provider: TradingViewClient` and `self.provider`. Type hint is correct (dishka resolves by type), but variable name is slightly mismatched with `*Client` naming. Cosmetic only.

---

## Verification Results

| Check | Result |
|-------|--------|
| Old class names in `src/**/*.py` | 0 matches |
| Old class names in `tests/**/*.py` | 0 matches |
| Old class names in `testscripts/**` | 0 matches |
| `src/providers/` directory exists | No (correctly removed) |
| Old filenames (e.g., `bar_manager.py`, `provider.py`) | All removed |
| `from src.providers` imports in source | 0 matches |
| Old class names in `docs/` | 0 matches |
| `src/di/__init__.py` re-exports | Correct (6 providers) |
| `src/infrastructure/tradingview/__init__.py` | Correct (`TradingViewClient`, `TradingViewWebSocketClient`) |
| DI providers resolve new names | Verified (all type hints match new classes) |
| pyright errors | 7 pre-existing, 0 from refactor |
| ruff issues | 1 pre-existing (UP046), 0 from refactor |
| pytest collection | 60 tests collected successfully |
| Old class names in `README.md` | 5 stale (lines 64-71) |
| Old class names in `TODO.md` | 3 stale (lines 12, 100, 109) |
| Old class names in `docs/` directory | 0 (already updated) |
| Old class names in `.yaml/.json/.toml` | 0 matches |

## Positive Observations

1. Source code is completely clean -- no stale imports or references
2. DI wiring is correct with new names throughout
3. `docs/` directory was already updated as part of the refactor
4. File renames are consistent -- old files all deleted, new files all present
5. `__init__.py` re-exports at the DI and infrastructure level are consistent
6. The refactor scope was well-bounded -- no unnecessary changes

## Recommended Actions

1. **Update README.md** lines 64-71 to use new class names
2. **Update TODO.md** lines 12, 100, 109 to use new class names
3. **Update agent memory** `.claude/agent-memory/code-reviewer/project_dishka_di.md` to reflect `src/di/` paths and new class names
4. (Optional) Rename `self.provider` to `self.client` in `SyncSymbolHandler` for consistency with `*Client` convention

## Unresolved Questions

- Should structlog event keys be renamed to match new class names? This affects log search/monitoring tooling. Recommend deferring unless there's no existing log queries depending on these keys.
