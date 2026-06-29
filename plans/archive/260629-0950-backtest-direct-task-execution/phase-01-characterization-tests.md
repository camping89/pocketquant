---
phase: 1
title: "Characterization tests"
status: done
effort: ""
---

# Phase 1: Characterization tests

## Overview

TDD gate: khóa hành vi đúng của backtest ENGINE + 3-collection persist (phần GIỮ qua refactor) TRƯỚC khi gỡ queue/worker/optimize/run-all. Nếu phase 2/3/4 làm vỡ `run_single` engine path hoặc shape persisted data → test đỏ ngay.

KHÔNG viết test cho code mới — ghim hành vi engine (giữ nguyên) làm lưới an toàn.

## Requirements

- Functional: sau 1 single backtest chạy xong, `backtest_runs` + `backtest_orders` + `backtest_trades` có doc đúng shape.
- Functional (C2 — red-team): test ghim run_id contract — `_id` run doc == `backtest_orders.run_id` == `backtest_trades.run_id`. Đây là invariant phase 2 phải giữ khi thread run_id từ route.
- Functional (C5 — red-team): test ghim `list_by_strategy_code` trả run vừa finished (bắt lỗi status-filter rename trước khi nó thành silent break).
- Non-functional: chạy trên ephemeral testcontainers, KHÔNG đụng prod. `tests/conftest.py` guard refuse khi `MONGODB_URL` chứa prod host; `unset MONGODB_URL REDIS_URL` trước pytest.

## Architecture

Engine GIỮ qua toàn bộ refactor: `BacktestAppService.run()` → `result_collector.finalize()` → `save_many(orders)` + `save_many(trades)` + `backtest_repo.save(run)`. Phase 2 đổi (a) ai gọi (worker → asyncio task), (b) run_id truyền vào thay vì engine tự sinh (C2), (c) status literal `completed→finished`. Characterization test nhắm `run_single` + repos.

```
test_backtest_persistence_characterization (bền):
  build_backtest_sandbox → inject engulfing → run_single(deps, config)
  → assert backtest_runs doc: status, metrics keys, equity_curve non-empty
  → assert backtest_orders.run_id == run doc _id == backtest_trades.run_id   # C2 invariant
  → assert list_by_strategy_code(engulfing) chứa run vừa chạy               # C5 invariant
  → assert sandbox isolation: live positions/orders count unchanged
```

## Related Code Files

- Create: `tests/backtest_test/test_backtest_persistence_characterization.py` — pin run_single 3-collection persist + shape + run_id invariant (C2) + list filter (C5) + sandbox isolation.
- Read (không sửa): `src/pocketquant/backtest/workers/backtest_dispatch.py` (`run_single`).
- Read: `src/pocketquant/backtest/engine/backtest_app_service.py` (run + run_id line 72 + persist 134-140), `engine/result_collector.py`.
- Read: `src/pocketquant/core/infra/persistence/repositories/backtest_repository.py` (save, get, list_by_strategy_code:65, get_best_by_metric:80), `backtest_order_repository.py`, `backtest_trade_repository.py`.
- Read: existing `tests/backtest_test/` fixtures; golden fixture engulfing nếu có.

## Implementation Steps

1. Đọc test harness `tests/backtest_test/` — fixture sandbox + testcontainers Mongo + seed bars.
2. Viết `test_backtest_persistence_characterization.py`:
   - Seed bars nhỏ đủ tạo ≥1 engulfing signal.
   - `run_single(deps, config)` strategy `engulfing`.
   - Assert: `backtest_runs.get(run_id)` doc tồn tại, `status == "completed"` (giá trị HIỆN TẠI — phase 2 đổi "finished" + cập nhật test cùng commit), metrics đủ keys, equity non-empty.
   - Assert C2: orders + trades doc dùng CÙNG run_id với run doc `_id`.
   - Assert C5: `list_by_strategy_code("engulfing")` chứa run vừa chạy.
   - Assert: live `positions`/`orders` count không đổi.
3. Chạy `unset MONGODB_URL REDIS_URL; pytest tests/backtest_test/test_backtest_persistence_characterization.py -v` → xanh.
4. Docstring: "characterization — pins engine persist + run_id + list invariant" (không nhắc plan id/phase number).
5. Liệt kê (trong notes phase 3) test queue/optimize sẽ xóa: `test_grid_optimization_isolation.py`, `test_backtest_request_service.py`.

## Success Criteria

- [x] `test_backtest_persistence_characterization.py` xanh: 3-collection persist + shape + run_id invariant (C2) + list filter (C5) + sandbox isolation.
- [x] Test chạy testcontainers, KHÔNG đụng prod (conftest guard verify — `MONGODB_URL` prod host → pytest refuse).
- [x] Danh sách test queue/optimize cần xóa được ghi cho phase 3 (xem Notes).

## Notes — tests queue/optimize cần xóa ở phase 3

- `tests/backtest_test/test_grid_optimization_isolation.py`
- `tests/backtest_test/test_backtest_request_service.py`
- `tests/backtest_test/test_backtest_request_queue.py`
- `tests/http/backtest/run-optimization.bru`
- Regen baseline snapshots: `tests/baseline/route_inventory_app_snapshot.json`, `openapi_app_snapshot.json`

## Risk Assessment

- **Risk**: fixture bars engulfing chưa có → synthetic bars tối thiểu tự tạo signal. Mitigation: tái dùng golden fixture nếu có.
- **Risk**: test ghim `completed` rồi phase 2 đổi `finished` → đỏ. CHỦ Ý (bắt thay đổi contract); cập nhật cùng commit phase 2.
- **Risk**: flaky do sandbox event loop. Mitigation: await đầy đủ, teardown trong fixture.
