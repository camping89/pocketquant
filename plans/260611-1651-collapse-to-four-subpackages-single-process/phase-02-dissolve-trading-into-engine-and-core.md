---
phase: 2
title: "Dissolve trading into engine and core"
status: pending
priority: P1
effort: "4h"
dependencies: [1]
---

# Phase 2: Dissolve trading into engine and core

## Overview

Giải thể `pocketquant.trading`: 3 services chuyển sang `engine/`, OKX broker chuyển về `core/infra/brokers/okx/` (cạnh `paper/`), tests `trading_test/` chuyển theo đích mới. Sau phase này `src/pocketquant/trading/` không còn tồn tại. Pure move — không đổi class name, không đổi behavior, OpenAPI snapshot diff rỗng.

## Context Links

- Brainstorm: [report](../reports/brainstorm-260611-1651-collapse-six-subpackages-to-four-single-process-report.md)
- Import edges đã verify: `trading` được import bởi `app` (2 files), `bff` (3 files); `trading` import `engine.app_services` (2 files) + `core` (7 files).

## Key Insights

- `okx_broker.py` chỉ import `core.domain.*` + sibling modules trong `trading/brokers/okx/` — sau move chỉ import `core.*` → hợp lệ nằm trong `core/infra/` (contract "Core imports no inner package" giữ nguyên).
- `orders_positions_service.py` import `engine.app_services.order_app_service` + `position_app_service` → khi nằm trong `engine/` thành import nội bộ, hợp lệ.
- `strategy_command_service.py` / `strategy_query_service.py` chỉ import `core.*` → nằm trong `engine/` hợp lệ.
- import-linter: layer `"pocketquant.backtest | pocketquant.trading"` → còn `"pocketquant.backtest"`; xóa contract "Backtest and Trading are independent siblings"; xóa `pocketquant.trading` khỏi mọi forbidden lists VÀ mọi `source_modules` (import-linter HARD-ERROR khi source module không tồn tại; forbidden module thiếu thì chỉ "KEPT"). Hai vị trí source bị sót dễ nhất: contract "Trading does not import Backtest" (`pyproject.toml:124-128` — xóa nguyên contract) và contract fastapi-containment (`pyproject.toml:145-150` — gỡ `pocketquant.trading` khỏi `source_modules`). <!-- red-team: enumeration cũ thiếu 2 contracts dạng source -->
- `tests/trading_test/conftest.py` định nghĩa fixtures testcontainers session-scoped (`mongo_container`, `redis_container`, `settings`) mà 5+ test files moved phụ thuộc; `tests/engine_test/` chưa có conftest — phải move/merge conftest theo, không chỉ move test files.
- `tests/app_test/integration/test_reconcile_di_resolution.py:24-25` import `pocketquant.trading.strategy_*` — nằm ngoài `tests/trading_test/`, phải sửa import.
- justfile comment dòng 37 liệt kê subpackages cho `just test-sub` — cập nhật.

## Requirements

- Functional: mọi route hoạt động y hệt; OpenAPI snapshot diff rỗng.
- Non-functional: không còn dir `trading/`; import-linter contracts gọn lại.

## Architecture

```text
TRƯỚC                                    SAU
trading/strategy_command_service.py  →  engine/strategy_command_service.py
trading/strategy_query_service.py    →  engine/strategy_query_service.py
trading/orders_positions_service.py  →  engine/orders_positions_service.py
trading/brokers/okx/**               →  core/infra/brokers/okx/**
trading/webhooks/                    →  (đã xóa ở Phase 1)
```

Layers sau phase: `core ◁ engine ◁ backtest ◁ {app, bff}` (trading biến mất khỏi tier 2).

## Related Code Files

- Move: 3 service files → `src/pocketquant/engine/`; `trading/brokers/okx/**` → `src/pocketquant/core/infra/brokers/okx/`
- Modify (import paths):
  - `src/pocketquant/app/di/broker_factory.py` (OKX import)
  - `src/pocketquant/app/di/trading_services.py` (3 services)
  - `src/pocketquant/bff/di/services.py` (2 strategy services)
  - `src/pocketquant/bff/routes/strategy.py`, `bff/routes/trading_orders_positions.py`
- Modify (config): `pyproject.toml` import-linter contracts (cả forbidden lists lẫn source_modules — xem Key Insights); `justfile` comment
- Move tests: `tests/trading_test/` → phân bổ vào `tests/engine_test/` (services) + `tests/core_test/` (okx nếu có); move/merge `tests/trading_test/conftest.py` → `tests/engine_test/conftest.py` (fixtures testcontainers); cập nhật import paths trong tests
- Modify: `tests/app_test/integration/test_reconcile_di_resolution.py` (import `pocketquant.trading.strategy_*` → engine)
- Delete: `src/pocketquant/trading/` (dir rỗng sau move)

## Implementation Steps

1. **TDD-lock:** chạy `just test tests/trading_test` + OpenAPI snapshot test → xanh. Đây là behavior cần giữ.
2. `git mv` 3 service files sang `src/pocketquant/engine/`. Giữ nguyên tên file (đã snake_case, tự mô tả).
3. `git mv src/pocketquant/trading/brokers/okx src/pocketquant/core/infra/brokers/okx`.
4. Sửa toàn bộ import `pocketquant.trading.strategy_command_service` → `pocketquant.engine.strategy_command_service` (tương tự 2 services kia); `pocketquant.trading.brokers.okx` → `pocketquant.core.infra.brokers.okx`. Sweep bằng grep, sửa cả nội bộ files vừa move (okx_broker import sibling qua path tuyệt đối).
5. Xóa `src/pocketquant/trading/__init__.py` + dir.
6. `pyproject.toml`:
   - Layer contract: `"pocketquant.backtest | pocketquant.trading"` → `"pocketquant.backtest"`.
   - Xóa contract "Backtest and Trading are independent siblings".
   - Xóa nguyên contract "Trading does not import Backtest" (source_modules trỏ module sắp chết → lint-imports hard-error nếu giữ).
   - Gỡ `pocketquant.trading` khỏi `source_modules` của contract fastapi-containment.
   - Gỡ `pocketquant.trading` khỏi forbidden lists của contracts "Core imports no inner package", "Engine imports no sibling/upper package" — LƯU Ý: engine giờ chứa services từng nằm trên nó; kiểm tra contract engine không tự cấm mình.
7. Move tests: `git mv tests/trading_test/test_strategy_*.py tests/engine_test/` (+ orders_positions, add_symbol, handlers_declarative); move/merge `tests/trading_test/conftest.py` thành `tests/engine_test/conftest.py` (fixtures `mongo_container`/`redis_container`/`settings` mà các test moved phụ thuộc); sửa imports kể cả `tests/app_test/integration/test_reconcile_di_resolution.py`. Xóa dir `tests/trading_test/`. Cập nhật justfile comment (danh sách subpackage cho test-sub).
8. Docstring sweep: 3 services có docstring nhắc "app process" / "bff DI" — giữ nguyên (vẫn đúng tới Phase 3).
9. Full gates: `just test && just lint-imports && just types && just lint` → xanh (xfail Phase 1 vẫn xfail vì bff còn sống).
10. OpenAPI snapshot + route inventory: diff rỗng.
11. Commit: `refactor(structure): dissolve trading — services to engine, okx broker to core infra`.

## Todo List

- [ ] TDD-lock xanh trước move
- [ ] Move 3 services → engine
- [ ] Move okx → core/infra/brokers
- [ ] Import sweep toàn src + tests
- [ ] import-linter contracts cập nhật
- [ ] tests/trading_test phân bổ xong, dir xóa
- [ ] Full gates xanh, snapshot diff rỗng
- [ ] Commit

## Success Criteria

- [ ] `src/pocketquant/trading/` không tồn tại
- [ ] `core/infra/brokers/` chứa cả `paper/` lẫn `okx/`
- [ ] `grep -rn "pocketquant.trading" src tests` → rỗng
- [ ] Full gates xanh; OpenAPI + route inventory snapshot diff rỗng

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Import sót (string-based / TYPE_CHECKING) | grep sweep cả `"pocketquant.trading"` dạng string; pyright bắt phần còn lại |
| import-linter layer độc lập backtest⊥trading mất đi mà backtest vô tình import engine service mới | backtest đã import `engine.app_services` hợp lệ từ trước; contract layers vẫn chặn chiều ngược |
| Test move làm trùng tên file trong engine_test | importlib mode đã bật (`--import-mode=importlib`) cho phép trùng tên giữa dirs; vẫn nên giữ tên file gốc |

## Security Considerations

- OKX credentials flow không đổi (`app/di/execution.py` đọc settings như cũ, chỉ đổi import path của broker class).

## Next Steps

- Phase 3: merge `bff` vào `app`, single process.
