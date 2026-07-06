# Phase 01 — Scaffold `core.domain.trading` + move Trade/Fill/EquityPoint + rename `PerformanceMetrics`

**Priority:** P0 · **Status:** pending · **Depends:** —
**Context:** [plan](plan.md) · [design §4](../design-execution-metrics-separation.md) · nguồn `src/pocketquant/core/domain/backtest/value_objects.py`

## Mục tiêu
Tạo package `core.domain.trading`; move `Trade`/`Fill`/`EquityPoint` + `BacktestMetrics`→`PerformanceMetrics` sang `core/domain/trading/value_objects.py`; update mọi importer + đổi tên. Thuần di chuyển, `to_mongo`/`from_mongo` không đổi.

## Files
**Create**
- `src/pocketquant/core/domain/trading/__init__.py` — re-export `Trade, Fill, EquityPoint, PerformanceMetrics`
- `src/pocketquant/core/domain/trading/value_objects.py` — cắt nguyên `EquityPoint`, `Fill`, `Trade` (dòng 30-49, 52-103, 226-296) + `BacktestMetrics`→rename `PerformanceMetrics` (dòng 299-378). Giữ nguyên body/`to_mongo`/`from_mongo`/`empty`. Import `OrderSide` từ `core.domain.order.enums` (Fill cần).

**Modify**
- `core/domain/backtest/value_objects.py` — bỏ `EquityPoint/Fill/Trade/BacktestMetrics`; **giữ** `Order`, `OpenLot`. Update docstring (chỉ còn Order+OpenLot). `Order.fills: list[Fill]` → import `Fill` từ `core.domain.trading.value_objects`.
- `core/domain/backtest/entities.py` — `BacktestResult` import `PerformanceMetrics, EquityPoint` từ `core.domain.trading`; `OpenLot` giữ local; đổi `BacktestMetrics`→`PerformanceMetrics` (field type, `.empty()`, `.from_mongo()`).
- `core/domain/backtest/__init__.py` — bỏ export `BacktestMetrics/EquityPoint/Fill/Trade`; giữ `BacktestResult, OpenLot, Order` (Order xử lý ở P4).

**Update importers** (đổi path + rename `BacktestMetrics`→`PerformanceMetrics`):
| File | Đổi |
|---|---|
| `core/infra/persistence/repositories/backtest_trade_repository.py` | `Trade` ← `core.domain.trading` |
| `backtest/engine/collected_results.py` | `Trade` ← `core.domain.trading`; `BacktestResult, Order` giữ `core.domain.backtest` |
| `backtest/backtest_stats_service.py` | `Trade` ← `core.domain.trading` |
| `backtest/workers/backtest_dispatch.py` | `BacktestResult` giữ nguyên (không đụng) |
| `backtest/engine/metrics_builder.py` | `BacktestMetrics→PerformanceMetrics, EquityPoint, Trade` ← `core.domain.trading` (file này xoá ở P2 — update tối thiểu cho gates xanh, hoặc gộp P1+P2 nếu thuận) |
| `backtest/engine/backtest_result_app_service.py` | tách import: `Fill, Trade, EquityPoint, PerformanceMetrics` ← `core.domain.trading`; `BacktestResult, OpenLot, Order` giữ `core.domain.backtest`; đổi annotation `BacktestMetrics`→`PerformanceMetrics` |
| `backtest/engine/backtest_app_service.py` | không đụng (chỉ dùng `BacktestResult`) |
| `backtest/domain/services/trade_stats_calculator.py` | `EquityPoint` ← `core.domain.trading` (file move ở P2) |

**Tests** (update import + rename):
- `tests/core_test/unit/domain/backtest/test_value_objects_roundtrip.py`, `test_backtest_value_objects_uuid_id.py` — di chuyển/đổi import Trade/Fill/EquityPoint/PerformanceMetrics sang `core.domain.trading`; cân nhắc tách phần trading sang `tests/core_test/unit/domain/trading/`.
- `tests/core_test/infra/persistence/backtest/test_trade_repository.py` — `Trade` path.
- Bất kỳ test nào assert `BacktestMetrics` → rename `PerformanceMetrics`.

## Steps
1. Tạo `core/domain/trading/{__init__,value_objects}.py`; cắt-dán 4 class, rename `BacktestMetrics`→`PerformanceMetrics` (grep xác nhận không sót tên cũ trong file mới).
2. Dọn `core/domain/backtest/value_objects.py` (còn Order+OpenLot) + fix `Order.fills` import Fill.
3. Sửa `entities.py` + `backtest/__init__.py`.
4. Update từng importer theo bảng (grep `BacktestMetrics` toàn repo `src` → 0 sau khi xong, trừ web TS).
5. Update tests.
6. `uv run ruff check . && uv run pyright && uv run lint-imports && just test`.

## Success
- `grep -rn "BacktestMetrics" src/` → rỗng (chỉ còn web TS).
- `core.domain.trading` export 4 symbol; `core.domain.backtest` không còn Trade/Fill/EquityPoint/PerformanceMetrics.
- 7 contracts + test xanh; số liệu backtest `engulfing`/`hitnrun2` không đổi.

## Rủi ro
- `Fill` dùng ở cả `Order` (backtest) — vòng import trading↔backtest: an toàn (Order import Fill từ trading; trading không import backtest). Nếu pyright báo circular → đặt `from __future__ import annotations` (đã có) + import trực tiếp module.
- Sót call-site `.empty()`/`.from_mongo()` khi rename → chạy pyright bắt.
