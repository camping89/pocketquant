# Phase 02 — Fold `backtest/` → `engine/backtest/` + import-linter 4→3 tầng

**Context:** [plan](plan.md) · [roadmap R2](../roadmap.md) · STRUCTURE-ONLY.
**Priority:** high · **Status:** done · **Depends:** P1.

## Overview

**Phase atomic** — move package + đổi import-linter phải cùng nhau (nếu tách, contract
`source_modules = ["pocketquant.backtest"]` trỏ module không tồn tại → import-linter lỗi).
Gộp toàn bộ 12 file `backtest/` **phẳng** vào `engine/backtest/`, hạ layers 4→3 tầng,
xoá contract backtest-top-tier, thêm 2 contract intra-engine.

## Move map (phẳng — bỏ subfolder engine/jobs/workers)

| Từ | Đến |
|---|---|
| `backtest/backtest_command_service.py` | `engine/backtest/backtest_command_service.py` |
| `backtest/backtest_query_service.py` | `engine/backtest/backtest_query_service.py` |
| `backtest/backtest_stats_service.py` | `engine/backtest/backtest_stats_service.py` |
| `backtest/backtest_execution_service.py` | `engine/backtest/backtest_execution_service.py` |
| `backtest/engine/backtest_app_service.py` | `engine/backtest/backtest_app_service.py` |
| `backtest/engine/backtest_sandbox_app_service.py` | `engine/backtest/backtest_sandbox_app_service.py` |
| `backtest/engine/backtest_result_app_service.py` | `engine/backtest/backtest_result_app_service.py` |
| `backtest/engine/historical_replay_app_service.py` | `engine/backtest/historical_replay_app_service.py` |
| `backtest/engine/collected_results.py` | `engine/backtest/collected_results.py` |
| `backtest/engine/lot_tracking_helper.py` | `engine/backtest/lot_tracking_helper.py` |
| `backtest/jobs/backtest_strategy_loader.py` | `engine/backtest/backtest_strategy_loader.py` |
| `backtest/workers/backtest_dispatch.py` | `engine/backtest/backtest_dispatch.py` |

**Không đổi tên file** (kể cả `backtest_result_app_service.py` → report là R5).
**Xoá dir rỗng sau move:** cả cây `backtest/` (`backtest/engine/`, `backtest/jobs/`, `backtest/workers/`, `backtest/__init__.py`).

## Importers cần update

**src (internal backtest cross-imports):** mọi `from pocketquant.backtest.engine.*` / `.jobs.*` / `.workers.*` / top-level → `from pocketquant.engine.backtest.*` (đã phẳng).
**src (app):**
- `app/di/backtest_worker.py` (L9–10)
- `app/di/services.py` (L14–16)
- `app/routes/backtest.py` (L15–27)
**tests:** `tests/backtest_test/**` + `tests/app_test/integration/test_app_standalone_runtime.py` — mọi hit `pocketquant.backtest.*`.

## Import-linter (`pyproject.toml`) — 8 contract cuối

**Sửa:**
1. **Layers** → 3 tầng: `["pocketquant.app", "pocketquant.engine", "pocketquant.core"]` (bỏ `pocketquant.backtest`).
2. **"Core imports no inner package"** → forbidden `["pocketquant.engine", "pocketquant.app"]` (bỏ backtest).
3. **"Engine imports no sibling/upper package"** → rename *"Engine imports no upper package"*, forbidden `["pocketquant.app"]` (bỏ backtest).
4. **"fastapi only in app"** → source `["pocketquant.core", "pocketquant.engine"]` (bỏ backtest).

**Xoá:** contract **"Backtest imports no upper package"** (`source_modules = ["pocketquant.backtest"]`).

**Thêm (2 intra-engine):**

```toml
[[tool.importlinter.contracts]]
name = "Engine backtest and live drivers stay independent"
type = "independence"
modules = [
    "pocketquant.engine.backtest",
    "pocketquant.engine.live",
]

[[tool.importlinter.contracts]]
name = "Shared engine machinery must not import drivers"
type = "forbidden"
source_modules = [
    "pocketquant.engine.strategy",
    "pocketquant.engine.execution",
    "pocketquant.engine.market_data",
]
forbidden_modules = [
    "pocketquant.engine.backtest",
    "pocketquant.engine.live",
]
```

**Giữ nguyên:** "Core domain stays free of infra adapters", "No bson/ObjectId usage".

## Test purity fix

`tests/core_test/unit/domain/test_domain_purity.py:14` — xoá dòng `"pocketquant.backtest",`
khỏi `FORBIDDEN_IMPORTS` (đã được `"pocketquant.engine"` bao trùm; giữ lại = tham chiếu module chết).

## Implementation steps

1. `mkdir engine/backtest` (PEP 420).
2. `git mv` 12 file theo move map (phẳng).
3. Update cross-import nội bộ `engine/backtest/*` (trỏ nhau qua path mới).
4. Update app importers (di/backtest_worker, di/services, routes/backtest).
5. Sửa `pyproject.toml`: 4 contract sửa + xoá 1 + thêm 2 (theo trên).
6. Sửa `test_domain_purity.py:14`.
7. `grep -rn "pocketquant.backtest" src tests` → update mọi hit test còn lại → **0**.
8. Xoá cây `backtest/` rỗng.
9. Gate sweep.

## Todo

- [x] Tạo `engine/backtest/` (PEP 420)
- [x] `git mv` 12 file (phẳng)
- [x] Update cross-import nội bộ engine/backtest
- [x] Update app/di/backtest_worker, app/di/services, app/routes/backtest
- [x] Sửa pyproject.toml: layers 4→3, 3 forbidden bỏ backtest, xoá "Backtest imports no upper", thêm 2 intra-engine
- [x] Sửa test_domain_purity.py:14
- [x] Update test imports (grep `pocketquant.backtest` → 0)
- [x] Xoá cây `backtest/` rỗng
- [x] `just test` + `ruff` + `pyright` + `lint-imports` (8 contract) xanh

## Success criteria

- `grep -rn "pocketquant.backtest" src tests` = **0 hit**.
- `lint-imports` report **8 contracts kept** (gồm 2 intra-engine mới).
- `python -c "import pocketquant.engine.backtest.backtest_app_service"` OK; `import pocketquant.backtest` → `ModuleNotFoundError`.
- `just test` xanh, số test pass không đổi.

## Rủi ro

- **Independence contract fail** nếu còn import ngầm backtest↔live → không xảy ra (đồ thị verified), nhưng nếu đỏ = có logic-coupling ẩn → dừng, báo cáo (không thuộc R2).
- **Namespace discover**: nếu `lint-imports` không thấy `engine.backtest` → thêm `engine/backtest/__init__.py` rỗng (khớp `engine/app_services` cũ).

## Next

P3: docs sync + roadmap R2 done + final full-gate sweep.
