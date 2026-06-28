---
phase: 2
title: "Fix PaperBroker accounting"
status: done
priority: P1
dependencies: [1]
---

# Phase 2: Fix PaperBroker accounting

## Overview

Chuyển `_execute_fill` sang futures model (open không đụng `_balance`, close `+= Δrealized`) + thêm price propagation trong `get_balance`. **Giữ `available_balance = _balance`, KHÔNG đổi `_can_afford`** (red-team C1/C2/C3). Làm Phase 1 tests → PASS.

## Requirements

- Functional: open/add không đụng `_balance`; close/reduce `_balance += Δrealized` (delta, không cumulative); `total_equity = _balance + Σ unrealized` với unrealized track giá per-bar; `available_balance = _balance` giữ nguyên.
- Non-functional: KHÔNG đổi public signature; KHÔNG đổi `_can_afford` logic; KHÔNG thêm `_compute_free_margin`/`margin_used` tracking.

## Architecture

### `_execute_fill` (`paper_broker.py:458-504`) — bỏ `± order_value`, delta realized

```python
def _execute_fill(self, order, fill_price):
    position_key = f"{order.subscription_id}:{order.symbol}"
    existing = self._positions.get(position_key)
    live = existing if existing is not None and not existing.is_closed else None

    if order.side == OrderSide.BUY:
        if live is not None:
            if live.side == PositionSide.LONG:
                live.add_quantity(order.quantity, fill_price)          # no balance change
            else:                                                       # BUY closes/reduces short
                before = live.realized_pnl
                live.reduce_quantity(order.quantity, fill_price)
                self._balance += live.realized_pnl - before            # delta only
        else:
            self._positions[position_key] = PositionAggregate.open(... LONG ...)
    else:  # SELL
        if live is not None:
            if live.side == PositionSide.LONG:                          # SELL closes/reduces long
                before = live.realized_pnl
                live.reduce_quantity(order.quantity, fill_price)
                self._balance += live.realized_pnl - before            # delta only
            else:
                live.add_quantity(order.quantity, fill_price)          # add to short, no balance change
        else:
            self._positions[position_key] = PositionAggregate.open(... SHORT ...)
```

Áp dụng cho cả entry fill (`submit_order` path) lẫn synthetic SL/TP exit (`_fire_synthetic_exit:665` gọi cùng `_execute_fill`) → exit accounting tự đúng.

### Price propagation (validate-chốt: ở `_on_bar_completed`, KHÔNG trong getter)

<!-- Updated: Validation Session 1 - price propagation moved to _on_bar_completed (no getter side-effect) -->

Mark open positions to `event.close` ở cuối `_on_bar_completed` (`:550-576`), sau SL/TP loop:
```python
# cuối _on_bar_completed
async with self._lock:
    for pos in self._positions.values():
        if not pos.is_closed and pos.symbol == event.symbol:
            pos.update_price(event.close)   # entities.py:82 raise nếu <=0; event.close > 0
```
**Ordering (đã verify):** `_mtm_on_bar` subscribe SAU broker `_on_bar_completed` (`backtest_app_service.py:87-89`) → mark chạy trước khi `_mtm_on_bar` đọc `get_balance` → `total_equity` track giá per-bar.

### `get_balance` (`:383-391`) — thuần đọc, giữ available = _balance

```python
async def get_balance(self):
    async with self._lock:
        open_positions = [p for p in self._positions.values() if not p.is_closed]
        unrealized = sum(p.unrealized_pnl for p in open_positions)
        return AccountBalance(
            total_equity=self._balance + unrealized,                   # unrealized đã mark per-bar
            available_balance=self._balance,                           # GIỮ NGUYÊN — không đổi sizing
            currency=self._currency,
            unrealized_pnl=unrealized,
        )
```

`get_balance` KHÔNG mutate position (no side-effect trong getter — validate-chốt).

### `_can_afford` (`:441-444`) — KHÔNG đổi

Giữ nguyên `fill_price * qty <= self._balance` cho BUY. Lý do: (a) bug gốc không cần đổi; (b) đổi sang free-margin tạo trap-close-short + scope creep (red-team C3); (c) giữ `available_balance = _balance` nên không cần helper no-lock → **không có deadlock risk**, KHÔNG thêm `_compute_free_margin`.

**Ghi chú (red-team C8):** `_can_afford` gọi 3 nơi (`:200`, `:262`, `:594`) — vì không đổi nó, không phát sinh lock/deadlock concern. Lưu lại để reviewer sau không nhầm.

## Related Code Files

- Modify: `src/pocketquant/core/infra/brokers/paper/paper_broker.py` (`_execute_fill`, `_on_bar_completed` price propagation, `get_balance` giữ thuần đọc)
- Read: `src/pocketquant/core/domain/position/entities.py` (update_price :82, cost_basis, realized cumulative)
- KHÔNG modify: `_can_afford`, AccountBalance.margin_used semantics

## Implementation Steps

1. Sửa `_execute_fill`: bỏ mọi `self._balance ± order_value`; dùng delta-realized ở 2 nhánh reduce (long-close, short-cover).
2. Thêm price propagation ở cuối `_on_bar_completed` (mark open positions to `event.close` sau SL/TP loop). KHÔNG đụng `get_balance` (giữ thuần đọc).
3. KHÔNG đụng `_can_afford`.
4. Chạy Phase 1 tests → tất cả PASS (green). Đặc biệt verify test #7 (price propagation) + #8 (available==balance).
5. `just lint` + `just types` cho broker file.

## Success Criteria

- [ ] 8 Phase-1 tests PASS
- [ ] Không còn `self._balance ± order_value` trong `_execute_fill`
- [ ] Delta-realized ở cả long-close và short-cover
- [ ] `_on_bar_completed` mark open positions to `event.close`; `get_balance` thuần đọc (no side-effect)
- [ ] `available_balance == self._balance` (không đổi); `_can_afford` không đổi
- [ ] `just lint` + `just types` xanh cho broker file

## Risk Assessment

- **Risk:** mark trong `_on_bar_completed` chạy sai thứ tự so với `_mtm_on_bar`. **Mitigation:** đã verify `_mtm_on_bar` subscribe SAU broker handler (`backtest_app_service.py:87-89`); mark chạy trước. Forward (live) không có `_mtm_on_bar` nên mark chỉ phục vụ get_balance đọc đúng.
- **Risk:** SL/TP exit path qua `_execute_fill` đổi accounting. **Mitigation:** Phase 1 test #6 + Phase 5 SL/TP suite + balance assertion.
- **Risk:** `reduce_quantity` raise khi closed. **Mitigation:** guard `live is not None and not is_closed` giữ nguyên.
