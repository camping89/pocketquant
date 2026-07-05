# Phase 04 — `Order` → `OrderRecord` → `core.domain.order`

**Priority:** P1 · **Status:** pending · **Depends:** P1
**Context:** [plan](plan.md) · nguồn `core/domain/backtest/value_objects.py` (`Order`, dòng 107-172) · [design §4](../design-execution-metrics-separation.md)

## Mục tiêu
`Order` (audit record: dataclass + `events[]`/`fills[]`, persist `backtest_orders`) đang lẫn với VO backtest. Move sang `core.domain.order` cạnh `OrderAggregate` (live) và **rename `OrderRecord`** để dứt nhập nhằng ngữ nghĩa. `to_mongo`/`from_mongo` giữ y nguyên field (`_id`, `events`, `fills`, …) → DB compat tuyệt đối.

## Files
**Create**
- `core/domain/order/records.py` — move `Order`→`OrderRecord` (dataclass nguyên vẹn). Import `OrderEvent` từ `core.domain.brokers.events`, `OrderSide/OrderStatus/OrderType` từ `.enums`, `Fill` từ `core.domain.trading.value_objects`.

**Modify**
- `core/domain/order/__init__.py` — thêm export `OrderRecord`.
- `core/domain/backtest/value_objects.py` — bỏ `Order` (còn `OpenLot`); cập nhật docstring.
- `core/domain/backtest/__init__.py` — bỏ export `Order`.

**Update importers** (`Order` → `OrderRecord`, path `core.domain.order`):
| File | Đổi |
|---|---|
| `core/infra/persistence/repositories/backtest_order_repository.py` | `Order`→`OrderRecord` ← `core.domain.order`; đổi mọi annotation/call trong file |
| `backtest/engine/collected_results.py` | `Order`→`OrderRecord`; field `orders: list[OrderRecord]` |
| `backtest/engine/backtest_result_app_service.py` | `Order`→`OrderRecord`; mọi chỗ tạo/append |

**Tests**
- `tests/core_test/infra/persistence/backtest/test_order_repository.py` — `Order`→`OrderRecord` + path.
- `tests/app_test/integration/test_backtest_orders_api.py` — nếu tham chiếu class (chỉ JSON API thì không đổi).
- Grep `\bOrder\b` (không phải OrderAggregate/OrderSide/…) trong test backtest → rename.

## Steps
1. Move `Order` → `core/domain/order/records.py` rename `OrderRecord`; export ở `__init__`.
2. Dọn `Order` khỏi `core.domain.backtest`.
3. Rename tại 3 importer src + tests (grep `import Order\b` / `Order(` cẩn thận tách khỏi `OrderAggregate`, `OrderSide`, `OrderStatus`, `OrderType`, `OrderEvent`).
4. Gates: `ruff && pyright && lint-imports && just test`.

## Success
- `core.domain.backtest` không còn `Order`; `core.domain.order` export `OrderRecord` + `OrderAggregate` cạnh nhau, **không clash**.
- `backtest_orders` round-trip (`to_mongo`/`from_mongo`) không đổi field; test repo + integration xanh; 7 contracts xanh.

## Rủi ro
- Rename dễ sót vì tiền tố `Order*` nhiều (Aggregate/Side/Status/Type/Event). Dùng grep whole-word + pyright để bắt.
- `resulting_trade_id: str | None` là FK `str` → không đụng.
