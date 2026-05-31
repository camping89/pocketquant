---
phase: 5
title: "Move persistence to infrastructure"
status: pending
priority: P1
effort: "1d"
dependencies: [4]
---

# Phase 5: Move persistence to infrastructure

## Overview

Move the entire persistence layer — `Database`, `Cache`, `BaseRepository`, all core repos, plus the per-package repos (trading order/position/subscription, backtest run/order/trade/optimization) — into `pocketquant-infrastructure`. After Phase 3, every entity these repos serialize lives in core, so the repos can legally live below backtest/trading. This is the phase that empties `core/persistence/`.

## Requirements
- Functional: all repositories + `Database` + `Cache` import from `pocketquant.infrastructure.persistence.*`. `core/persistence/` deleted. Core back-reference shims (`common/database`, `common/cache`) resolved. Full suite + api boot green.
- Non-functional: zero behavior change to repository logic (the `_BAR_VALUE_CACHE` dedup, upsert diff-branches, indexes all move verbatim). Sync-status counter logic moves verbatim here; its extraction to a domain service is Phase 8.

## Architecture

Target: `pocketquant-infrastructure/src/pocketquant/infrastructure/persistence/` mirroring current `core/persistence/` (`mongodb.py`, `redis.py`, `base_repository.py`, `repositories/`). Per-package repos consolidate here too (decision #6: zero repos remain in backtest/trading). **12 repos total** (NOT 11 — `JobHistoryRepository` is the 12th, see below):
- `infrastructure/persistence/repositories/` — bar, symbol, sync_status, tracked_symbol (from core) + order, position, subscription (from trading) + backtest_run, backtest_order, backtest_trade, optimization (from backtest) + **job_history (from `core/infrastructure/scheduling/job_history_repository.py`)**.

**JobHistoryRepository moves in THIS phase (binding, not a "recommendation"):** it extends `BaseRepository` (`core/infrastructure/scheduling/job_history_repository.py:32`). Once `BaseRepository` lands in infra, leaving `job_history_repository.py` in `core/infrastructure/scheduling/` creates a `core → infrastructure` package edge that fails the Phase 5 `lint-imports` gate. Move it here; only `scheduler.py` remains for Phase 6 (it keeps a `TYPE_CHECKING` ref pointing at `infrastructure.persistence.repositories`).

Core back-reference shims that would otherwise cause core→infra-package cycle (scout found):
- `core/common/database/__init__.py` re-exports `Database` from persistence → DELETE; consumers import `infrastructure.persistence.Database`.
- `core/common/cache/__init__.py` re-exports `Cache` → DELETE; consumers import from infra. **4 api handlers import `core.common.cache.Cache` directly and must be re-pointed: `market_data/handlers/ohlcv/get_ohlcv/handler.py:4`, `quotes/get_latest/handler.py:6`, `sync/sync_one/handler.py:12`, `system_jobs/route.py:18`.**
- `core/common/health/` (BINDING decision — not "confirm during impl"): `health/__init__.py:3` EAGER-imports `check_database`/`check_redis` from `health/checks.py`, which imports `Database`/`Cache` (moving to infra). Keeping the eager re-export in core → permanent `core → infrastructure` edge at the Phase 5 boundary. Resolution: MOVE `check_database`/`check_redis` to infra, REMOVE the eager re-export from `core/common/health/__init__.py` (delete the health package from core if nothing core-legal remains), and rewire `HealthCoordinator` registration (`di/infrastructure.py:42`, `main_extensions.py:362-364`) so api imports the checks from infra directly.

## Related Code Files
- Create: `infrastructure/persistence/{mongodb.py,redis.py,base_repository.py,__init__.py}`, `infrastructure/persistence/repositories/*` (12 repos total, incl. job_history)
- Delete: `core/persistence/` (whole tree), `core/common/database/`, `core/common/cache/`, eager re-export in `core/common/health/__init__.py` (and the health package from core if nothing core-legal remains)
- Move: `packages/pocketquant-trading/.../persistence/{order,position,subscription}_repository.py` → infra; `packages/pocketquant-backtest/.../persistence/*` → infra; `core/infrastructure/scheduling/job_history_repository.py` → `infrastructure/persistence/repositories/`. Delete the now-empty trading/backtest `persistence/` dirs.
- Move: `core/common/health/checks.py` (`check_database`/`check_redis`) → infra.
- Modify (re-point, scout's consumer map): api `di/persistence.py` (12 repos incl. JobHistoryRepository at `:18`), `di/market_data.py`, `di/infrastructure.py:42` (HealthCoordinator), `main.py:28-29`, `main_extensions.py:36-46,362-364`, all market-data handlers/app-services importing `core.persistence.repositories`, the 4 `core.common.cache` consumers (ohlcv/get_ohlcv, quotes/get_latest, sync/sync_one handlers + system_jobs/route.py), backtest `engine/backtest_app_service.py:20`, `optimization/grid_optimization_app_service.py:20`, trading app-services importing own repos, backtest/trading handlers reading repos.
- Move tests: `tests/core_test/unit/persistence/` → `tests/infrastructure_test/persistence/`; `tests/backtest_test/persistence/` → `tests/infrastructure_test/persistence/backtest/`; trading repo tests likewise.
- Modify: `core/pyproject.toml` — leave pymongo/redis/cachetools until Phase 6 confirms no core code needs them (BaseRepository/Database used pymongo; once moved, core may drop pymongo/redis/cachetools — verify with grep before removing).

## Implementation Steps
1. Move `mongodb.py`, `redis.py`, `base_repository.py` into infra; fix internal imports (`core.common.logging`, `core.config.Settings` — stay valid, core is a dep of infra).
2. Move the 4 core repos + 3 trading repos + 4 backtest repos + JobHistoryRepository (12 total) into `infrastructure/persistence/repositories/`. Repo imports of promoted entities now resolve from `core.domain.*` (Phase 3). Fix `core.common.constants` collection-name imports (stay in core — valid). Leave only `scheduler.py` in `core/infrastructure/scheduling/` for Phase 6; update its `TYPE_CHECKING` ref to `infrastructure.persistence.repositories`.
3. Resolve back-reference shims: delete `common/database`, `common/cache`; move `health/checks.py` DB/redis checks to infra; remove the eager re-export in `core/common/health/__init__.py`; re-point `HealthCoordinator` wiring (`di/infrastructure.py:42`, `main_extensions.py:362-364`) to import checks from infra.
4. Grep-sweep ALL `core.persistence`, `trading.persistence`, `backtest.persistence`, `core.common.database`, `core.common.cache` import sites → re-point to `infrastructure.persistence`. (This is the largest churn phase — scout counted 20+ Bar repo sites alone; plus the 4 explicit `core.common.cache` handler consumers.)
5. Update api DI providers (`PersistenceProvider` now imports from infra; provider class may move to infra or stay in api importing infra — keep in api, import infra).
6. Delete emptied `core/persistence/`, trading/backtest `persistence/` dirs.
7. Grep core for residual pymongo/redis/cachetools usage; if none, remove those pins from `core/pyproject.toml` (else defer to Phase 6). Run `uv sync`.
8. Run sync-status counter characterization test (logic moved verbatim) + full suite + api boot smoke + `lint-imports`.
9. Commit: `refactor: move persistence layer (Database/Cache/all repositories) to pocketquant-infrastructure`.

## Success Criteria
- [ ] `core/persistence/` and per-package `persistence/` dirs gone; all 12 repos (incl. JobHistoryRepository) under `infrastructure.persistence.repositories`.
- [ ] `grep -r "core.common.\(database\|cache\)" packages/` → 0; health checks resolve from infra; no eager core→infra edge via `common/health`.
- [ ] `core/infrastructure/scheduling/` contains only `scheduler.py`; `lint-imports` shows zero `core → infrastructure` edge at this boundary.
- [ ] Sync-status counter characterization test green (verbatim move).
- [ ] Full suite + api boot green; `lint-imports` shows core no longer imports persistence.

## Risk Assessment
- Risk: largest import surface in the plan — high chance of a missed site. Mitigation: grep each old path to zero hits before deleting; api boot smoke is mandatory gate.
- Resolved (now a numbered step): `JobHistoryRepository` extends `BaseRepository` and MUST move in this phase (it is the 12th repo). Leaving it in `core/infrastructure/scheduling/` would create a `core → infrastructure` package edge that fails this phase's `lint-imports` gate. Only `scheduler.py` remains for Phase 6.
- Risk: removing pymongo from core breaks a missed core usage. Mitigation: grep `pymongo`/`motor`/`redis` across core/src before pin removal; defer removal to Phase 6 if any doubt.
