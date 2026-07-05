# Phase 02 — Port + broker transport (paper emit, OKX no-op, mapper side)

## Context Links
- Plan: [plan.md](plan.md) · Prev: [phase-01](phase-01-domain-trade-closed-event.md)
- Files: `core/domain/brokers/broker_port.py`, `core/infra/brokers/paper/paper_broker_adapter.py`, `core/infra/brokers/okx/okx_broker_adapter.py`, `core/infra/brokers/okx/websocket/okx_order_mapper.py`

## Overview
- **Priority:** P2 · **Status:** done · **Depends:** 01
- Thêm kênh trade thứ 3 vào `IBrokerPort` (`subscribe_trades`); paper broker drain `TradeClosedEvent` từ PositionAggregate và forward; OKX implement no-op (defer R8); fix OKX order mapper `side`. Additive → fill/event channel cũ nguyên vẹn, test cũ xanh.

## Key Insights
- `IBrokerPort` hiện chỉ có `subscribe_order_updates(OrderResult)`. `subscribe_order_event` là paper-only (KHÔNG trên port). → `subscribe_trades` thêm vào port (đối xứng order_updates), OKX buộc implement.
- Paper broker: `_execute_fill(order, fill_price)` gọi `add_quantity`/`_reduce_and_credit` → `reduce_quantity`. Commission hiện tính SAU (`_execute_fill_with_commission` wrapper). Muốn thread commission vào fill (entry/exit) phải tính commission TRƯỚC.
- 1 fill = 1 vai trò (no flip): open/add = entry_commission; reduce = exit_commission. Không split trong 1 fill.
- 4 fill path đều qua `_execute_fill_with_commission` (single debit point R3) → chèn drain event ở đây = phủ hết (submit_order, fill_pending, synthetic_exit, cancel-cover nếu có).
- Notify: fill callback (OrderResult) phải TRƯỚC trade callback (TradeClosedEvent) — để collector.on_fill dựng OrderRecord trước on_trade back-link. Notify NGOÀI lock (giữ pattern `_notify_callbacks`).
- OKX adapter không giữ local position state, không event_bus/commission_model → chỉ lưu callback, không gọi.

## Requirements
**Functional**
- `subscribe_trades(cb)` / `unsubscribe_trades()` trên IBrokerPort + cả 2 adapter.
- Paper broker forward mọi `TradeClosedEvent` do reduce/close sinh ra, đúng thứ tự sau OrderResult.
- OKX `to_order_result` set `OrderResult.side` từ `data["side"]`.

**Non-functional**
- `_execute_fill_with_commission` refactor giữ single-debit-point; return `(commission, list[TradeClosedEvent])`.
- Không await trong atomic block; notify ngoài lock.

## Architecture
```
_execute_fill_with_commission(order, price):        # dưới lock
  commission = _commission(price, qty)
  trades = _execute_fill(order, price, commission)   # thread entry/exit; drain position.collect_events()→lọc TradeClosedEvent
  _balance -= commission
  return commission, trades
caller (async, ngoài lock):
  result = OrderResult(..., commission=commission)
  await _notify_callbacks(result)          # fill TRƯỚC
  for t in trades: await _notify_trade_callbacks(t)   # trade SAU
```

## Related Code Files
**Modify**
- `broker_port.py` — `TradeCallback = Callable[[TradeClosedEvent], None|Awaitable[None]]`; abstract `subscribe_trades`/`unsubscribe_trades`.
- `paper_broker_adapter.py` — `self._trade_callbacks`, `subscribe_trades`/`unsubscribe_trades`, `_notify_trade_callbacks`; `_execute_fill(order, price, commission)` thread + drain; `_execute_fill_with_commission` return tuple; cập nhật 4 call site để forward trades sau fill notify; `_reduce_and_credit` giữ credit balance (drain có thể ở đây hoặc `_execute_fill`).
- `okx_broker_adapter.py` — `subscribe_trades`(lưu callback, no-op)/`unsubscribe_trades` + comment defer R8.
- `okx_order_mapper.py` — set `side=OrderSide(data["side"].lower()==...)`; dùng `OrderSide` từ `core.domain.order`.

**Create**
- `tests/backtest_test/engine/test_paper_broker_trade_emission.py` — integration: subscribe_trades nhận event khi close/partial close; thứ tự fill trước trade.

## Implementation Steps
1. **Port** — thêm `TradeCallback` + 2 abstract method vào `IBrokerPort`.
2. **Paper broker state** — `self._trade_callbacks: list[TradeCallback] = []`; `subscribe_trades`(append)/`unsubscribe_trades`(clear); `_notify_trade_callbacks(event)` mirror `_notify_callbacks` (iterate, await coroutine, collect errors, raise first).
3. **`_execute_fill` refactor** — thêm param `commission: float`; nhánh open→`PositionAggregate.open(..., entry_order_id=order.id, entry_commission=commission, opened_at=get_current_time())`; add→`live.add_quantity(qty, price, commission=commission)`; reduce→`_reduce_and_credit(live, qty, price, exit_commission=commission, exit_order_id=order.id)`. Sau mutate: gom `position.collect_events()` lọc `TradeClosedEvent` → return list.
4. **`_reduce_and_credit`** — thêm `exit_commission`, `exit_order_id`; gọi `reduce_quantity(qty, price, exit_commission=exit_commission, exit_order_id=exit_order_id, exit_time=get_current_time())`; giữ `_balance += realized delta`; return drained trades.
5. **`_execute_fill_with_commission`** — tính commission TRƯỚC; `trades = _execute_fill(order, price, commission)`; `_balance -= commission`; return `(commission, trades)`.
6. **4 call site** (submit_order, `_fill_pending_on_bar`, `_fire_synthetic_exit`, cancel-cover nếu có) — nhận tuple; sau `_notify_callbacks(result)` → `for t in trades: await _notify_trade_callbacks(t)`.
7. **OKX** — `subscribe_trades(cb)`: `self._trade_callback = cb` (lưu, không dùng); comment `# OKX position→Trade emission wired ở R8 (cần demo payload chốt nguồn orders/positions/history)`. `unsubscribe_trades`: clear.
8. **OKX order mapper** — `side_raw = data.get("side","")`; `side = OrderSide.BUY if side_raw=="buy" else OrderSide.SELL if side_raw=="sell" else None`; set vào `OrderResult(side=side)`.

## Todo List
- [x] IBrokerPort +subscribe_trades/unsubscribe_trades + TradeCallback
- [x] Paper broker _trade_callbacks + notify helper
- [x] `_execute_fill` thread commission + drain TradeClosedEvent
- [x] `_execute_fill_with_commission` return (commission, trades)
- [x] 4 call site forward trades SAU fill notify
- [x] OKX subscribe_trades no-op + comment R8
- [x] OKX order mapper set side
- [x] Integration test: partial + full close emit; thứ tự fill→trade
- [x] `pyright`/`ruff`/`lint-imports` xanh; test cũ xanh

## Success Criteria
- Subscribe callback nhận TradeClosedEvent đúng số lượng + giá trị khi close/partial.
- Balance/equity paper KHÔNG đổi (parity) — commission vẫn single-debit.
- import-linter 8 contract xanh.

## Risk Assessment
- **Thread commission sai phía** (entry vào reduce) → test partial close bắt.
- **Drain nhầm event khác** (PositionOpened/Updated) — lọc `isinstance(e, TradeClosedEvent)`.
- **collect_events() nuốt event lifecycle khác** đang được ai dùng? — hiện 0 consumer (an toàn drain).

## Security Considerations
OKX side map từ payload venue — validate giá trị lạ → None (không crash).

## Next Steps
Phase 03 chuyển collector sang subscribe kênh trade + xoá FIFO.
