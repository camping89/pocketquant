---
phase: 1
title: "BE Foundation (scoping + orders endpoint)"
status: completed
priority: P1
dependencies: []
---

# Phase 1: BE Foundation (scoping + orders endpoint)

## Overview

Backend additive, không đụng engine: (A2) denormalize `symbol`+`interval` top-level `BacktestResult` để history scope đúng; **mở rộng** `GET /backtest/strategy/{id}` thêm optional `symbol`/`interval` filter (KHÔNG tạo `/runs` mới); thêm `GET /backtest/{run_id}/orders` wrap `BacktestOrderRepository.list_by_run` (đã có) mở khóa data orders/fills/events đang write-only. TDD.

## Requirements

- Functional:
  - `BacktestResult` mang `symbol`/`interval` top-level (denormalize từ `config_snapshot` lúc `started`/finalize).
  - `GET /backtest/strategy/{id}?symbol=&interval=&limit=&include_failed=` filter scoped; DTO thêm `symbol`/`interval`/`date_range`/`verdict`.
  - `GET /backtest/{run_id}/orders` trả orders + embedded fills + events + `resulting_trade_id`, **DTO key `order_id` (KHÔNG `_id`)**.
- Non-functional: 7 import-linter contracts; UUIDv7; FromDishka+DishkaRoute; doc cũ thiếu top-level field KHÔNG hard-fail (`from_mongo` fallback `config_snapshot`).

## Architecture

**A2 denormalize:** `symbol`/`interval` có trong `config_snapshot` (`backtest_command_service.py:62`). `symbol` là **composite `CODE:EXCHANGE`** (`backtest_command_service.py:25,29` — `"BTCUSDT:BINANCE"`), KHÔNG bare code. `list_by_strategy_code` mở rộng filter optional symbol+interval (exact match composite, normalize `.upper()` cho khớp storage).

**Scope filter (red-team H1):** filter `{"symbol": "BTCUSDT:BINANCE"}` exact — FE phải gửi composite (reuse giá trị form `backtest-form.tsx:42`, không tách exchange). Test seed doc bằng composite symbol để không giả-pass.

**Orders endpoint (red-team M4):** thuần read. Route → `BacktestQueryService.list_orders(run_id)` → `list_by_run` (đã có) → **map ở service** thành DTO key `order_id` (KHÔNG tái dùng `Order.to_mongo()` vì nó trả `_id`). FastAPI auto-encode datetime → isoformat khi route trả dict.

```
GET /backtest/strategy/hitnrun2?symbol=BTCUSDT:BINANCE&interval=1m&limit=50
→ 200 [ { id, strategy_code, status, symbol, interval, date_range:{start,end},
          parameters, metrics:{...}, verdict, started_at, completed_at, error_message } ]

GET /backtest/{run_id}/orders
→ 200 { run_id, orders:[ { order_id, side, order_type, quantity, price, sl_price, tp_price,
          status, submitted_at, last_updated_at, resulting_trade_id,
          fills:[{fill_id,side,quantity,price,commission,slippage,timestamp}],
          events:[{...}] } ] }
```

## Related Code Files

- Modify: `src/pocketquant/core/domain/backtest/entities.py` — `BacktestResult`: thêm `symbol`/`interval` + `started()`/`to_mongo`/`from_mongo` (fallback `config_snapshot`).
- Modify: `src/pocketquant/backtest/engine/result_collector.py` — `finalize` set `symbol`/`interval` từ `self._config` (chỉ field).
- Modify: `src/pocketquant/core/infra/persistence/repositories/backtest_repository.py` — `list_by_strategy_code` thêm optional `symbol`/`interval` filter; `ensure_indexes` thêm `(strategy_code, symbol, interval, started_at desc)`.
- Modify: `src/pocketquant/backtest/backtest_query_service.py` — `ListBacktestsQuery` thêm `symbol`/`interval`; `list_results` truyền filter; `list_orders(run_id)` map Order→DTO key `order_id`. **Constructor cần `BacktestOrderRepository`** (dishka auto-wire — đã register `persistence.py`).
- Modify: `src/pocketquant/app/routes/backtest.py` — `/strategy/{id}` thêm query param; `GET /{run_id}/orders`. Route order: route hiện có theo thứ tự static-trước-param đã đúng (verify: `/strategy/{id}` 2-segment không va `/{run_id}` 1-segment).
- Modify: DTO list ở route `/strategy/{id}` — thêm `symbol`/`interval`/`date_range`/`verdict`.

## TDD: Tests First

**Regression-lock (PASS không đổi):**
- `tests/core_test/unit/domain/backtest/test_value_objects_roundtrip.py`, `test_backtest_value_objects_uuid_id.py`.
- `tests/core_test/infra/persistence/backtest/test_backtest_repository_slimmed.py`, `test_order_repository.py`.
- `tests/baseline/test_route_inventory.py` — **sẽ RED sau khi thêm route → regen baseline (xem step)**.

**New tests (RED trước):**
1. `test_value_objects_roundtrip.py` — `BacktestResult` round-trip giữ `symbol`/`interval`; doc cũ thiếu → fallback `config_snapshot`, không raise.
2. `test_backtest_repository_slimmed.py` — seed 2 run cùng `(strategy_code, "BTCUSDT:BINANCE", "1m")` + 1 run symbol khác → filter chỉ trả 2 đúng scope (**dùng composite symbol**).
3. `tests/app_test/integration/test_backtest_orders_api.py` — `GET /{run_id}/orders` trả orders+fills+events, **key `order_id` không `_id`**; run không order → `{orders:[]}`.
4. `test_backtest_orders_api.py` — `GET /strategy/{id}?symbol=&interval=` filter đúng; DTO có `symbol`/`interval`/`date_range`.

## Implementation Steps

1. Viết/mở rộng tests (RED).
2. `entities.py`: thêm `symbol`/`interval` + `started()`/`to_mongo`/`from_mongo` fallback.
3. `result_collector.py finalize`: set 2 field từ `self._config`.
4. `backtest_repository.py`: `list_by_strategy_code` optional filter + composite index.
5. `backtest_query_service.py`: `ListBacktestsQuery` field + `list_orders` map key `order_id`.
6. `app/routes/backtest.py`: query param `/strategy/{id}` + `GET /{run_id}/orders`.
7. Chạy tests GREEN → **`BASELINE_UPDATE=1 just baseline`** regen `route_inventory` + `openapi` snapshot, review diff chỉ thấy route orders mới + param, commit (**red-team H2**).
8. `just lint && just types` → import-linter.

## Success Criteria

- [x] New tests RED→GREEN; regression-lock pass (sau regen baseline).
- [x] `/strategy/{id}?symbol=BTCUSDT:BINANCE&interval=1m` scope đúng — run symbol khác không lẫn.
- [x] `GET /{run_id}/orders` trả fills+events, key `order_id`; run không order → `[]`.
- [x] Doc cũ thiếu `symbol`/`interval` đọc được (fallback), không hard-fail.
- [x] `just test && just lint && just types` pass; import-linter 7 contracts pass.

## Risk Assessment

- **symbol composite (red-team H1):** filter exact composite; test seed composite; FE (P4) gửi composite. Quên → history rỗng âm thầm.
- **baseline snapshot (red-team H2):** bước 7 regen bắt buộc; nếu quên, `just test` RED ở route_inventory + openapi.
- **Order serialize (red-team M4):** map ở service key `order_id`; KHÔNG dùng `to_mongo()` (leak `_id`). Test #3 assert `order_id`.
- **Doc cũ thiếu field:** `from_mongo` fallback `config_snapshot`; nếu config_snapshot cũng thiếu (doc rất cũ) → `""`, filter không khớp (chấp nhận — data sạch từ giờ).
- **Endpoint trùng (red-team H4):** mở rộng `/strategy/{id}`, KHÔNG tạo `/runs`. Index composite chỉ thêm, không xoá index cũ.
