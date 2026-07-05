# Phase 01 — Domain: TradeClosedEvent + PositionAggregate emit

## Context Links
- Plan: [plan.md](plan.md) · Brainstorm: `plans/reports/brainstorm-260705-2216-r4-broker-trade-emission-remove-fifo.md`
- Files: `core/domain/position/events.py`, `core/domain/position/entities.py`, `core/domain/position/enums.py` (ref)

## Overview
- **Priority:** P2 · **Status:** done
- Thêm domain event `TradeClosedEvent` + mở rộng `PositionAggregate` để emit nó lúc `reduce_quantity`/`close` (average-cost). Pure domain, thuần default-arg → mọi caller hiện tại KHÔNG vỡ. Additive.

## Key Insights
- `DomainEvent` = `@dataclass(frozen=True, eq=False)`, mọi field có default → subclass field cũng phải có default (dataclass ordering). Theo đúng pattern `PositionClosedEvent`.
- `PositionSide.LONG="long"`, `SHORT="short"` (lowercase). `Trade.direction`="LONG"/"SHORT". → map bằng `side.name`, KHÔNG `.value`.
- `PositionAggregate.reduce_quantity` đã tính `realized = pnl_per_unit * quantity` + cộng `realized_pnl`. `_close` set `is_closed`. Chỉ cần chèn emit + accounting commission portion.
- Hiện `opened_at` default `utc_now()` = wall-clock; trong backtest sai duration. Trước đây FIFO override entry_time nên latent. Giờ open_positions dùng `opened_at` → phải cho phép broker inject sim-time.
- Commission-per-fill vào aggregate: `entry_commission` cộng dồn khi open/add; `reduce` lấy portion tỉ lệ.

## Requirements
**Functional**
- `TradeClosedEvent` mang economic-only (không run_id/strategy_code).
- `reduce_quantity` emit đúng 1 `TradeClosedEvent`/lần gọi (partial scale-out cũng emit — round-trip chunk).
- `entry_commission_portion = entry_commission * qty/qty_before`; aggregate trừ portion khỏi `entry_commission` còn lại.
- `pnl` trong event = realized delta của CHUNK này (không cumulative).
- `direction` = `self.side.name`.

**Non-functional**
- Default-arg toàn bộ chữ ký mới. Không đổi hành vi caller cũ (sandbox, live PositionAppService, tests).

## Architecture
```
open(entry_order_id, entry_commission, opened_at) ─┐
add_quantity(qty, price, commission) ──────────────┤ entry_commission tích luỹ
reduce_quantity(qty, price, exit_commission,        │
                exit_order_id, exit_time) ──────────┴─► append TradeClosedEvent → _events
                                                        (drain qua collect_events)
```

## Related Code Files
**Modify**
- `src/pocketquant/core/domain/position/events.py` — thêm `TradeClosedEvent`.
- `src/pocketquant/core/domain/position/entities.py` — +2 field, mở rộng `open`/`add_quantity`/`reduce_quantity`, emit event.

**Create**
- `tests/core_test/unit/domain/position/test_position_trade_emission.py` (hoặc mở rộng test position hiện có).

## Implementation Steps
1. **`TradeClosedEvent`** (`events.py`) — `@dataclass(frozen=True, eq=False)` kế `DomainEvent`, mọi field default:
   `position_id:str="", subscription_id:str="", symbol:str="", direction:str="LONG", entry_order_id:str|None=None, entry_price:float=0.0, entry_time:datetime|None=None, quantity:float=0.0, exit_order_id:str|None=None, exit_price:float=0.0, exit_time:datetime|None=None, sl_price:float|None=None, tp_price:float|None=None, pnl:float=0.0, commission:float=0.0, duration_seconds:float=0.0`.
2. **Fields** (`entities.py`) — `entry_order_id: str | None = None`, `entry_commission: float = 0.0`.
3. **`open`** — thêm param `entry_order_id: str|None=None`, `entry_commission: float=0.0`, `opened_at: datetime|None=None`; set lên instance (opened_at chỉ set khi truyền, else giữ default_factory).
4. **`add_quantity`** — thêm `commission: float = 0.0`; sau khi cập nhật avg entry: `self.entry_commission += commission`.
5. **`reduce_quantity`** — thêm `exit_commission: float=0.0, exit_order_id: str|None=None, exit_time: datetime|None=None`. Trước mutate: `qty_before=self.quantity`, `entry_comm_before=self.entry_commission`, `entry_time=self.opened_at`, `entry_price_snap=self.entry_price`, `direction=self.side.name`. Tính `realized` (như cũ). `portion = entry_comm_before * quantity/qty_before if qty_before>0 else 0.0`; `self.entry_commission -= portion`. `xt = exit_time or utc_now()`; `duration=(xt-entry_time).total_seconds()`. Append `TradeClosedEvent(...)` vào `_events` với `pnl=realized, commission=portion+exit_commission, quantity=quantity, exit_price=price, exit_time=xt, entry_time=entry_time, entry_price=entry_price_snap, ...`. GIỮ nguyên decrement + `_close` if qty→0.
6. Đảm bảo emit TRƯỚC nhánh `_close` return (để không mất event khi full close).

## Todo List
- [x] `TradeClosedEvent` frozen dataclass all-default
- [x] `PositionAggregate` +entry_order_id +entry_commission
- [x] `open` nhận entry_order_id/entry_commission/opened_at
- [x] `add_quantity` cộng dồn commission
- [x] `reduce_quantity` emit TradeClosedEvent + trừ entry_commission portion
- [x] Unit test: open→reduce full (pnl+commission+duration+direction name)
- [x] Unit test: open→add→partial reduce (avg-cost pnl, portion commission, entry_commission còn lại)
- [x] Unit test: SHORT direction; sim-time opened_at inject
- [x] `pyright` + `ruff` xanh; caller cũ không vỡ

## Success Criteria
- `reduce_quantity`/`close` emit đúng TradeClosedEvent với pnl/commission/duration/direction đúng.
- Mọi test hiện có xanh (default-arg → additive).

## Risk Assessment
- **Ordering dataclass field default** — DomainEvent base có default nên OK; giữ tất cả field mới có default.
- **entry_time None** khi position tạo qua constructor trực tiếp (không qua `open`) — dùng `self.opened_at` (luôn có default_factory) an toàn.

## Security Considerations
Không I/O, không external. Pure domain.

## Next Steps
Phase 02 nối broker forward event qua port.
