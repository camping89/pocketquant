# Monorepo Migration — Doubts & Notes

**Date:** 2026-03-21
**Status:** All items resolved (2026-03-21)

## 1. Backtest → Trading Coupling (StrategyAppService) — RESOLVED

`StrategyAppService` was injected into 4 backtest files but never called. Removed the dead parameter entirely from all 4 files. `ignore_imports` removed from pyproject.toml. lint-imports passes clean.

## 2. Backtest Repositories — RESOLVED (No-op)

Already in correct location (`backtest/persistence/`). No action needed.

## 3. Config .env Path Resolution — RESOLVED

Replaced `Path(__file__).parents[5]` with `_find_project_root()` — walks up to `pyproject.toml` containing `[tool.uv.workspace]`. Falls back to `POCKETQUANT_ROOT` env var.

## 4. Namespace Packages — RESOLVED (No-op)

Already correct — no `__init__.py` at `pocketquant/` level. PEP 420 compliant.

## 5. Tests Not Migrated — RESOLVED

Moved root `tests/` into `packages/pocketquant-core/tests/`. Updated stale `src.*` paths in `test_domain_purity.py` and `test_websocket.py`. Created scaffold conftest for backtest, trading, api packages. 52 tests pass.

## 6. DI Provider Imports — RESOLVED

Verified all DI providers in `api/di/` have correct import paths. Pyright 0 errors on DI directory.

## 7. Order/Position Repos — RESOLVED

Moved `order_repository.py` and `position_repository.py` from `core/persistence/repositories/` to `trading/persistence/`. Updated 5 import consumers. lint-imports passes clean.

## Resolved Questions

1. Order/position repos → moved to trading package. Done.
2. Strategy YAML path resolution → deferred (not blocking, handled by CWD-relative resolution).
3. Tests per-package → yes, each package has its own `tests/` directory.
