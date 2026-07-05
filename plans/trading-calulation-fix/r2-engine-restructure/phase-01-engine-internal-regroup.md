# Phase 01 — Engine internal regroup → {strategy, execution, live}

**Context:** [plan](plan.md) · [roadmap R2](../roadmap.md) · STRUCTURE-ONLY.
**Priority:** high · **Status:** done · **Depends:** R1 (done).

## Overview

Regroup các file đang nằm phẳng/rải trong `engine/` vào 3 feature area mới:
`strategy/`, `execution/`, `live/`. **Chưa đụng `backtest/`** — tầng 4 giữ nguyên nên
import-linter không cần đổi ở phase này. Kết thúc phase: 4 tầng cũ vẫn xanh.

## Key insight

- `market_data/` đã là feature area PEP 420 (không `__init__.py`) → 3 dir mới theo cùng pattern.
- `backtest_sandbox` (còn ở `backtest/engine/`) import máy chung → phải update path của nó ở phase này dù backtest chưa move.
- `strategy_app_service` import `RiskCheckHandler` qua `TYPE_CHECKING` → cả 2 cùng move, update import.

## Move map

| Từ | Đến |
|---|---|
| `engine/app_services/order_app_service.py` | `engine/execution/order_app_service.py` |
| `engine/app_services/position_app_service.py` | `engine/execution/position_app_service.py` |
| `engine/orders_positions_service.py` | `engine/execution/orders_positions_service.py` |
| `engine/handlers/risk/check_risk/handler.py` | `engine/execution/risk_check.py` |
| `engine/app_services/strategy_app_service.py` | `engine/strategy/strategy_app_service.py` |
| `engine/strategy_command_service.py` | `engine/strategy/strategy_command_service.py` |
| `engine/strategy_query_service.py` | `engine/strategy/strategy_query_service.py` |
| `engine/app_services/strategy_reconcile_app_service.py` | `engine/live/strategy_reconcile_app_service.py` |

**Đổi tên duy nhất:** `check_risk/handler.py` → `risk_check.py`. Class `RiskCheckHandler` **giữ nguyên tên**.
**Xoá dir rỗng sau move:** `engine/app_services/` (+ `__init__.py`), `engine/handlers/` (cả cây `risk/check_risk/`).

## Importers cần update (path mới)

**src (engine internal):**
- `engine/execution/orders_positions_service.py` → import order/position từ `engine.execution.*`
- `engine/strategy/strategy_app_service.py` → import order/position từ `engine.execution.*`, `RiskCheckHandler` từ `engine.execution.risk_check`
- `engine/live/strategy_reconcile_app_service.py` → import `StrategyAppService` từ `engine.strategy.strategy_app_service`

**src (app):**
- `app/di/execution.py` → order/position/strategy từ mới; `strategy_reconcile` từ `engine.live.*`; `RiskCheckHandler` từ `engine.execution.risk_check`
- `app/di/trading_services.py` → `orders_positions_service`, `strategy_command_service`, `strategy_query_service` path mới
- `app/main_extensions.py` → `strategy_reconcile` (L63), `strategy_app_service` (L133 TYPE_CHECKING)

**src (backtest driver, chưa move):**
- `backtest/engine/backtest_sandbox_app_service.py` → order/position/strategy từ mới + `RiskCheckHandler` từ `engine.execution.risk_check`

**tests:** cập nhật import trong (grep xác nhận):
`tests/engine_test/test_order_app_service_immediate_fill.py`, `test_order_filled_event_routing.py`,
`test_orders_positions_service.py`, `test_strategy_service.py`, `test_strategy_reconcile_service.py`,
`test_reconcile_restart_resume_integration.py`, `strategy_injection_roundtrip_characterization_test.py`,
`tests/app_test/integration/test_app_standalone_runtime.py` + bất kỳ file nào `grep` bắt.

## Implementation steps

1. `mkdir engine/strategy engine/execution engine/live` (PEP 420, không tạo `__init__.py`).
2. `git mv` từng file theo move map (giữ history). `git mv handler.py → risk_check.py`.
3. Update import nội bộ 3 file engine đã move (order/position/strategy/risk/reconcile trỏ nhau).
4. Update importers src (app/di, main_extensions, backtest_sandbox).
5. `grep -rn "engine.app_services\|engine.handlers\|engine.orders_positions_service\|engine.strategy_command_service\|engine.strategy_query_service" src tests` → update mọi hit còn lại (tests).
6. Xoá `engine/app_services/`, `engine/handlers/` (cây rỗng).
7. Gate sweep.

## Todo

- [x] Tạo 3 dir feature area (PEP 420)
- [x] `git mv` 8 file theo move map (+ rename handler→risk_check)
- [x] Update import 3 file engine đã move (trỏ nhau)
- [x] Update app/di/execution, app/di/trading_services, app/main_extensions
- [x] Update backtest_sandbox (import máy chung path mới)
- [x] Update test imports (grep-driven)
- [x] Xoá `engine/app_services/`, `engine/handlers/` rỗng
- [x] `just test` + `ruff check` + `pyright` + `lint-imports` xanh

## Success criteria

- `grep -rn "pocketquant.engine.app_services\|pocketquant.engine.handlers\|pocketquant.engine.orders_positions_service\|pocketquant.engine.strategy_command_service\|pocketquant.engine.strategy_query_service" src tests` = **0 hit**.
- `lint-imports` xanh (4-tier cũ chưa đổi — hợp lệ vì backtest còn top-level).
- `just test` xanh, không đổi số test pass.

## Next

P2: fold `backtest/` → `engine/backtest/` + hạ tầng import-linter + intra-engine contracts.
