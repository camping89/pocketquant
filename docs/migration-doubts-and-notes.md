# Monorepo Migration — Doubts & Notes

**Date:** 2026-03-21

## Known Coupling: Backtest → Trading (StrategyAppService)

4 files in backtest import `StrategyAppService` from trading:
- `backtest/engine/backtest_app_service.py` (TYPE_CHECKING)
- `backtest/optimization/grid_optimization_app_service.py` (TYPE_CHECKING)
- `backtest/handlers/run/handler.py` (direct — DI type hint)
- `backtest/handlers/optimize/handler.py` (direct — DI type hint)

**Analysis**: BacktestAppService stores `strategy_engine` but never calls methods on it — strategy execution happens via EventBus. The coupling is DI-wiring only.

**Recommended fix**: Define `IStrategyEngine` Protocol in core. Backtest depends on protocol. StrategyAppService (trading) implements it implicitly (structural typing). Or remove the parameter entirely since it's unused.

**Current mitigation**: `ignore_imports` in import-linter pyproject.toml.

## Backtest Repositories Moved to Backtest Package

`backtest_repository.py` and `optimization_repository.py` moved from `core/persistence/repositories/` to `backtest/persistence/` because they import `BacktestResult`/`OptimizationResult` from backtest domain. This broke the "core owns all persistence" decision, but was necessary to avoid circular deps.

**Impact**: API's `di/persistence.py` now imports from backtest package for these repos.

## Config .env Path Resolution

`config.py` uses `Path(__file__).parents[5]` to reach project root. This is fragile — if package nesting changes, the path breaks.

**Recommended fix**: Use environment variable `POCKETQUANT_ROOT` or `dotenv_values()` with explicit path, or resolve relative to workspace root via `pyproject.toml` discovery.

## Namespace Packages

All 4 packages share the `pocketquant` namespace via implicit namespace packages (no `__init__.py` at `packages/*/src/pocketquant/` level). This is standard PEP 420 but:
- Each package's `pyproject.toml` uses `packages = ["src/pocketquant"]` — hatchling builds only the subdirectory present in that package
- If a package accidentally creates `src/pocketquant/__init__.py`, namespace resolution breaks for other packages

## Tests Not Migrated

Tests in `tests/` still use old `from src.*` imports. They need to be updated to match new package paths. No tests were run during migration (would fail).

## DI Provider Imports

`di/infrastructure.py` previously imported `BrokerFactory` — now should import from `api/di/broker_factory.py`. Verify all DI providers have correct import paths.

## Unresolved Questions

1. Should `order_repository.py` and `position_repository.py` also move to trading package? (Same pattern as backtest repos — they import from order/position domain, but those are in core, so no circular dep currently.)
2. How to handle strategy YAML files path resolution after the split?
3. Should tests live per-package (`packages/pocketquant-core/tests/`) or in root `tests/`?
