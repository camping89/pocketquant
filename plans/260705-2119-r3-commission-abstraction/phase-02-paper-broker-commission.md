# Phase 02 — PaperBroker: compute + deduct commission (4 fill path) + _can_afford

**Priority:** P2 · **Status:** completed · **Depends:** P01 · **Blocks:** P03

## Overview

Core behavior của R3. `PaperBrokerAdapter` giữ 1 `CommissionModel`; mỗi khi **fill**, tính commission → set `OrderResult.commission` + trừ `_balance`. Gate `_can_afford` cộng commission. ⚠️ Rủi ro #1 toàn plan: có **4 OrderResult FILLED construction site** — sót path nào là mất commission path đó.

## Key insight — 4 fill path (BẮT BUỘC cả 4)

| # | Method | Path | OrderResult site |
|---|--------|------|------------------|
| 1 | `_handle_market` | MARKET fill | dòng ~221 (`status=FILLED`) |
| 2 | `_handle_limit` | LIMIT immediate (`REASON_LIMIT_IMMEDIATE`) | dòng ~282 |
| 3 | `_fill_pending_on_bar` | LIMIT cross future bar (`REASON_LIMIT_CROSS`) | dòng ~640 |
| 4 | `_fire_synthetic_exit` | SL/TP auto-exit | dòng ~692 |

Non-fill site (REJECTED/CANCELLED/EXPIRED/pending SUBMITTED) → `commission` để default `0.0`, KHÔNG trừ balance.

## Requirements

- ctor `commission_model: CommissionModel | None = None`; `None` → `PercentageCommissionModel(bps=…)` dựng trong body (không mutable default arg). Tham số truyền bps qua ctor riêng hoặc model injected — xem step 1.
- Helper `_commission(fill_price, qty) -> float` gọi model.
- Mọi fill: `commission = self._commission(fill_price, qty)`; set vào `OrderResult`; `self._balance -= commission` (dưới lock, cùng chỗ `_execute_fill`).
- `_can_afford(order, fill_price)`: opening BUY gate `fill_price*qty + commission ≤ _balance`.

## Related code files

- **MODIFY** `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py`

## Implementation steps

1. **ctor** — thêm param. Giữ tương thích `broker_factory`/`sandbox` (P03 truyền vào). Chọn shape: nhận `commission_model` trực tiếp (factory dựng `PercentageCommissionModel`):
   ```python
   def __init__(self, ..., commission_model: CommissionModel | None = None) -> None:
       ...
       self._commission_model = commission_model or PercentageCommissionModel(bps=0.0)
   ```
   - Default `bps=0.0` khi không inject → giữ backward-compat cho test cũ chưa truyền model (commission=0, balance như trước). Giá trị thật (4bps/commission_bps) do P03 inject qua factory/sandbox.

2. **Helper**:
   ```python
   def _commission(self, fill_price: float, quantity: float) -> float:
       return self._commission_model.compute(fill_price, quantity)
   ```

3. **`_can_afford`** — cộng commission vào gate opening BUY (reduce/cover short vẫn return True sớm):
   ```python
   commission = self._commission(fill_price, order.quantity)
   return fill_price * order.quantity + commission <= self._balance
   ```

4. **Trừ balance khi fill** — 2 lựa chọn, chọn **B** (tập trung, ít sót):
   - **B (khuyến nghị):** trừ trong `_execute_fill` không được (nó không biết commission) → thêm 1 điểm trừ ngay sau mỗi `self._execute_fill(...)` call trong 4 path, kèm set `OrderResult.commission`. Vì `_execute_fill` gọi ở 4 chỗ, gom bằng wrapper:
     ```python
     def _execute_fill_with_commission(self, order, fill_price) -> float:
         """MUST call under lock. Applies fill then debits commission. Returns commission."""
         self._execute_fill(order, fill_price)
         commission = self._commission(fill_price, order.quantity)
         self._balance -= commission
         return commission
     ```
     Thay 4 call `self._execute_fill(order, fill_price)` → `commission = self._execute_fill_with_commission(order, fill_price)` và set `commission=commission` vào OrderResult tương ứng.
   - ⚠️ `_fire_synthetic_exit` dùng `exit_order` (OrderAggregate tạo tại chỗ) — `order.quantity = pos.quantity`; wrapper vẫn đúng.

5. **Verify** `reset()` không cần đổi (`_balance = _initial_balance` — commission đã phản ánh trong `_balance` runtime, reset về initial đúng).

6. Comment: 1 dòng ở `_can_afford` giải thích reduce-cover vẫn trừ commission dù không gate (rủi ro #3). Không comment thừa chỗ khác.

## Todo

- [x] ctor `commission_model` param + default `PercentageCommissionModel(bps=0.0)`
- [x] `_commission` helper
- [x] `_execute_fill_with_commission` wrapper (trừ `_balance`)
- [x] Path 1 `_handle_market`: dùng wrapper + `commission=` vào OrderResult
- [x] Path 2 `_handle_limit` immediate: wrapper + `commission=`
- [x] Path 3 `_fill_pending_on_bar`: wrapper + `commission=`
- [x] Path 4 `_fire_synthetic_exit`: wrapper + `commission=`
- [x] `_can_afford` gồm commission
- [x] compile + `pyright`

## Success criteria

- 4 fill path đều set `OrderResult.commission > 0` (khi model bps>0) + trừ `_balance`.
- Entry fill: `_balance` giảm đúng entry commission ngay lúc mở (futures: notional không trừ, chỉ commission).
- Exit fill: `_balance += realized_pnl_delta` rồi `-= exit_commission`.
- `_can_afford` reject khi `notional+commission > balance`.
- Model `bps=0.0` (default chưa inject) → balance/commission như trước R3 (backward compat).

## Risks

1. **Sót 1/4 path** → dùng wrapper `_execute_fill_with_commission` để mọi fill đi qua 1 điểm trừ; grep đảm bảo KHÔNG còn `self._execute_fill(` trần ngoài wrapper (trừ định nghĩa gốc).
2. Reduce-cover: commission trừ dù `_can_afford` bỏ qua → balance có thể âm nhẹ pathological. Accept + comment.
