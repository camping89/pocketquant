---
phase: 1
title: "WS1 representation id str to UUID"
status: in-progress # code DONE + reviewed; pending deploy verify (11-verify.sh)
priority: P2
effort: "4h"
dependencies: []
---

# Phase 1: WS1 representation id str to UUID

## Overview

Flip type `id: str` → `id: UUID` cho các entity mà GIÁ TRỊ đã là uuid7 (chỉ đổi representation, KHÔNG migration data). Pattern chuẩn theo `Bar` (`core/domain/bar/entities.py:32,63,84`): field `UUID = Field(default_factory=generate_id)`, `to_mongo()` ghi `str(self.id)`, `from_mongo()` đọc `UUID(doc["_id"])`.

**KHÔNG nằm trong phase này (lý do verified trong code):**
- `BacktestRequest.id` — run-all còn ghi `bt:{sub_id}` (`backtest_command_service.py:177`) → Phase 4.
- `BacktestResult.id` — `save_for_subscription` override `result.id = sub_id` 16-hex (`backtest_repository.py:125`) → Phase 5.
- `Subscription.id` — còn sha256 16-hex → Phase 6.

**Quyết định scope:** chỉ flip PK attribute của document. FK reference fields (`subscription_id`, `run_id`, `broker_order_id`, `entry_order_id`, `exit_order_id`, `resulting_trade_id`) giữ `str` — chúng chỉ lưu giá trị tham chiếu, serialize string ở Mongo; flip sẽ cascade churn không cần thiết (YAGNI). Rule §12.6 chỉ ràng buộc `_id`.

## Requirements

- Functional: behavior không đổi — API responses giữ id dạng uuid string, Mongo docs giữ `_id` string như cũ.
- Non-functional: OpenAPI snapshot + route inventory diff rỗng; full gates xanh.

## Architecture

Type flip tại entity + boundary conversion tại `to_mongo`/`from_mongo`. Pydantic models (`OrderAggregate`, `PositionAggregate`) tự coerce str→UUID khi validate; dataclasses (`Fill`, `Order`, `Trade`, `OptimizationResult`) cần `UUID(...)` tường minh trong `from_mongo` và `str(...)` trong `to_mongo`.

## Related Code Files

Modify:
- `src/pocketquant/core/domain/order/entities.py` — `OrderAggregate.id: UUID`; `create()` dùng `generate_id()` (`:81`); `to_mongo` `"_id": str(self.id)` (`:226`); `from_mongo` giữ `id=doc["_id"]` (Pydantic coerce).
- `src/pocketquant/core/domain/position/entities.py` — `PositionAggregate.id: UUID`; `create()` `:62`; `to_mongo`/`from_mongo` `:204,:223` tương tự.
- `src/pocketquant/core/domain/backtest/entities.py` — `OptimizationResult.id: UUID`; `to_mongo` `:99`, `from_mongo` `:118`.
- `src/pocketquant/core/domain/backtest/value_objects.py` — `Fill.fill_id: UUID` (+`order_id` GIỮ str — FK); `Order.order_id: UUID` (`to_mongo :135`, `from_mongo :157` — chú ý `from_mongo` truyền `order_id=order_id` xuống embedded fills dạng str); `Trade.trade_id: UUID` (`to_mongo :258`, `from_mongo :279`).
- `src/pocketquant/backtest/engine/result_collector.py` — `fill_id=generate_id_str()` `:229` → `generate_id()`; `trade_id=generate_id_str()` `:255` → `generate_id()`. Chú ý: nơi nào dùng các giá trị này làm dict key / so sánh với str thì wrap `str(...)`.
- `src/pocketquant/backtest/optimization/grid_optimization_app_service.py:68` — `optimization_id = generate_id_str()` → `generate_id()` nếu chỉ feed vào `OptimizationResult.id`; nếu dùng làm str ở chỗ khác thì convert tại điểm dùng.
- Callers đọc `.id`/`.order_id`/`.trade_id` rồi interpolate vào response/log: wrap `str(...)` nơi cần (grep `\.id` trong `backtest/engine/`, `engine/app_services/`, route DTOs).

KHÔNG đổi: repositories (filter `{"_id": <str>}` vẫn nhận str từ route params — service layer convert `str(entity.id)` khi gọi).

## Implementation Steps (TDD)

1. **Tests first — lock representation:** viết test mới `tests/core_test/unit/domain/` cho mỗi entity flip: (a) construct qua factory → `isinstance(e.id, UUID)`; (b) `to_mongo()["_id"]` là `str` và parse được `UUID(...)`; (c) `from_mongo(to_mongo())` round-trip giữ nguyên id; (d) `from_mongo` với doc `_id` string uuid cũ (giả lập docs hiện hữu) → đọc OK. Chạy → FAIL (id còn str).
2. Flip `OrderAggregate` + `PositionAggregate` (Pydantic): đổi annotation, `create()` dùng `generate_id()`, `to_mongo` wrap `str()`.
3. Flip dataclasses `OptimizationResult`, `Fill.fill_id`, `Order.order_id`, `Trade.trade_id`: annotation + `to_mongo` `str()` + `from_mongo` `UUID()`.
4. Sửa construction sites trong `result_collector.py`, `grid_optimization_app_service.py`; grep toàn repo chỗ so sánh/concat các id này với str → wrap `str()`.
5. Chạy unit tests step 1 → PASS. Chạy full: `just test && just lint && just types && just lint-imports`.
6. Verify snapshot: `tests/baseline/` OpenAPI + route inventory diff rỗng (id trong schema vẫn `string`).

## Success Criteria

- [x] Tests step 1 pass; toàn bộ suite xanh (574 passed, 5 skipped).
- [x] `to_mongo()` của mọi entity flip ghi `_id` là str(uuid); `from_mongo` đọc docs cũ không lỗi (legacy-doc tests per entity).
- [x] OpenAPI + route inventory snapshot không đổi (tests/baseline/ 9 passed, snapshots untouched).
- [x] Không còn `generate_id_str()` tại construction site của các entity đã flip (grep verified — còn lại chỉ broker_order_id, sync_status, job_history, run_id, BacktestRequest.id: đúng scope Phase 2-5).
- [ ] Deploy: `11-verify.sh` HEALTHY.

## Risk Assessment

- **Pydantic coerce che lỗi type ở call sites** — mitigation: `just types` (mypy/pyright) bắt chỗ truyền UUID vào param str.
- **Embedded fill `order_id` đọc từ parent (`from_mongo(f, order_id=order_id)`)** — parent `order_id` giờ là UUID, embedded field là str → truyền `str(order_id)`. Test round-trip ở step 1c bắt lỗi này.
