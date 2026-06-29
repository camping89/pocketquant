---
phase: 3
title: "Remove queue optimize run-all"
status: done
effort: ""
---

# Phase 3: Remove queue optimize run-all

## Overview

Gỡ machinery chết: queue (`backtest_requests` + worker), `/optimize` grid, `run-all-backtests` fan-out, coupling `ENABLE_JOBS` cho backtest. Characterization (phase 1/2) là lưới an toàn. Áp dụng red-team H1 (move BacktestConfig trước khi xóa optimization/). C3 (StrategyCommandService dep) xử lý ở phase 4 cùng subscription decouple.

## Requirements

- Functional: không còn route/service/repo/collection của queue + optimize + run-all.
- Functional: `ENABLE_JOBS` không còn gate backtest.
- Non-functional: import-linter 7 contracts xanh; grep sạch import mồ côi.
- Constraint (H1): `BacktestConfig` MOVE ra khỏi `optimization/` TRƯỚC khi xóa dir.

## Architecture

Xóa theo cụm, test sau mỗi cụm.

**Cụm H1 (làm TRƯỚC) — move BacktestConfig:**
`BacktestConfig` ở `backtest/optimization/models/backtest_config.py:9`, dùng bởi `backtest_dispatch.py:25` + `backtest_app_service.py:8` (KHÔNG chỉ optimize). MOVE → `backtest/models/backtest_config.py`, update 2 import. Rồi mới xóa phần còn lại của `optimization/`.

**Cụm A — Queue/worker:**
- `BacktestRequestWorker` (`workers/backtest_request_worker.py`)
- `BacktestRequestRepository` (`repositories/backtest_request_repository.py`) — NHƯNG xem C3 phase 4: `StrategyCommandService` dep phải gỡ TRƯỚC. Thứ tự: phase 4 gỡ dep → phase 3 (hoặc cuối phase 4) xóa repo. Để an toàn, xóa repo file ở phase 4 sau khi gỡ dep; phase 3 chỉ xóa worker + provider worker.
- `start/stop_backtest_worker`, (sweep cũ `recover_stale_backtests` đã thay bằng sweep nhẹ ở phase 2 — đổi tên/giữ).
- `BacktestWorkerProvider.get_backtest_worker` (`di/backtest_worker.py`) — XÓA; GIỮ `get_dispatch_deps`.
- `COLLECTION_BACKTEST_REQUESTS` (`constants.py:19`) — xóa ở phase 4 cùng repo.

**Cụm B — Optimize:**
- Routes `run_optimization`, `get_optimization` (`routes/backtest.py:62,139`) + `/requests/{id}` route.
- `RunOptimizationCommand`, `BacktestCommandService.optimize`.
- `GridOptimizationAppService` + optimize-only models trong `optimization/` (SAU cụm H1).
- `OptimizationResult` + `OptimizationResultEntry` (`entities.py`).
- `OptimizationRepository` (`repositories/optimization_repository.py`) + provider (`persistence.py:75`).
- `GetOptimizationQuery`, `OptimizationSummaryResponse`, `get_optimization`, `get_request_status` (`backtest_query_service.py`).
- `COLLECTION_BACKTEST_OPTIMIZATION_RUNS` (`constants.py:18`).

**Cụm C — Tests:**
- `tests/backtest_test/test_grid_optimization_isolation.py`, `test_backtest_request_service.py`.
- `tests/http/backtest/run-optimization.bru`.
- Regen `tests/baseline/route_inventory_app_snapshot.json` + `openapi_app_snapshot.json`.

## Related Code Files

- Move: `backtest/optimization/models/backtest_config.py` → `backtest/models/backtest_config.py` (+ update `backtest_dispatch.py:25`, `backtest_app_service.py:8`).
- Delete: `backtest/workers/backtest_request_worker.py`, `backtest/optimization/grid_optimization_app_service.py` + optimize models, `repositories/optimization_repository.py`.
- Delete tests: `test_grid_optimization_isolation.py`, `test_backtest_request_service.py`, `run-optimization.bru`.
- Modify: `app/routes/backtest.py` — xóa optimize routes + `/requests/{id}`; giữ `/run`, `/{run_id}`, `/{run_id}/equity`, `/strategy/{id}`, `/strategies`.
- Modify: `backtest/backtest_command_service.py` — xóa `optimize`, `RunOptimizationCommand`. (`run_all` xóa ở phase 4.)
- Modify: `backtest/backtest_query_service.py` — xóa optimization + request-status methods/DTOs.
- Modify: `core/domain/backtest/entities.py` — xóa `OptimizationResult*`.
- Modify: `core/domain/backtest/__init__.py` — xóa export `OptimizationResult` (BacktestRequest export xóa ở phase 4).
- Modify: `core/common/constants.py` — xóa `COLLECTION_BACKTEST_OPTIMIZATION_RUNS` (requests const ở phase 4).
- Modify: `app/di/backtest_worker.py` — xóa `get_backtest_worker`, giữ `get_dispatch_deps`.
- Modify: `app/di/persistence.py` — xóa `optimization_repository` provider (request repo ở phase 4).
- Modify: `app/main.py` + `main_extensions.py` — xóa import + call `start/stop_backtest_worker`.

## Implementation Steps

1. Cụm H1: move `BacktestConfig` + update 2 import → `ruff`+`lint-imports`+`pytest`.
2. Cụm A (worker, provider, lifespan worker calls) → test. (Repo `BacktestRequestRepository` để phase 4.)
3. Cụm B (optimize toàn bộ) → test.
4. Cụm C (tests + regen snapshots) → `pytest`.
5. Grep sạch: `grep -rn "optimization\|GridOptimization\|RunOptimizationCommand\|BacktestRequestWorker\|/optimize\|get_request_status" src/ tests/` → 0.
6. `pyright` full → xanh.

## Success Criteria

- [x] H1: `BacktestConfig` ở `backtest/models/backtest_config.py`, 11 import cập nhật, `optimization/` xóa sạch (không mồ côi).
- [x] Queue worker + optimize (grid + config + repo + entity + routes) + `/requests` route xóa hết; `lint-imports` (7) KEPT.
- [x] `ENABLE_JOBS` không còn gate backtest (worker start/stop gỡ khỏi lifespan ở phase 2).
- [x] Baseline snapshots regen: optimize/optimization/requests routes mất, `/{run_id}/trades` thêm.
- [x] `ruff`/`pyright`(src + changed tests)/`lint-imports` xanh; characterization + direct-task `/run` pass.

## Notes — deferred to phase 4

- `BacktestRequestRepository` + `request.py` + `COLLECTION_BACKTEST_REQUESTS` GIỮ (C3: gỡ StrategyCommandService dep trước).
- `run_all` route + command GIỮ (xóa phase 4 cùng subscription decouple).
- Test `run_all`/subscription-cache (`test_concurrent_run_all`, `test_run_all_backtest_cascade`, `test_backtest_repository_subscription_cache`) còn pass với code cũ — xử lý phase 4.
- Cosmetic: `request.py` docstring + `tests/manual/api-test.http` còn nhắc optimize/worker — dọn phase 6 docs.

## Risk Assessment

- **Risk (H1)**: xóa `optimization/` wholesale kéo theo `BacktestConfig` → `/run` vỡ. Mitigation: MOVE trước (cụm H1), grep refs xác nhận.
- **Risk**: xóa `BacktestRequestRepository` sớm → C3 (StrategyCommandService) vỡ boot. Mitigation: hoãn xóa repo sang phase 4 sau khi gỡ dep.
- **Risk**: `OptimizationResult` export còn ref. Mitigation: grep trước, xóa export cuối.
- **Risk**: snapshot tests đỏ (đúng chủ ý). Mitigation: regen, review diff chỉ mất optimize/requests.
