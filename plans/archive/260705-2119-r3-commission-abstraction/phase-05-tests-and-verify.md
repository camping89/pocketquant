# Phase 05 — Tests + verify

**Priority:** P2 · **Status:** completed · **Depends:** P01–P04

## Overview

Test mới cho commission + update assertions churned (balance/equity lệch do entry commission — **expected**). Verify toolchain đầy đủ.

## New tests

1. **CommissionModel** — `tests/core_test/unit/domain/trading/test_commission_model.py` (NEW):
   - `PercentageCommissionModel(bps=4).compute(100.10, 10) ≈ 0.40040`.
   - `bps=0` → `0.0` (seam).
   - qty/price âm → `abs` → ≥ 0.

2. **Paper broker commission** — bổ sung `tests/core_test/infra/brokers/paper_broker_futures_accounting_test.py` (hoặc file mới `paper_broker_commission_test.py`):
   - Entry MARKET fill → `_balance` giảm đúng entry commission; `OrderResult.commission > 0`.
   - Exit (close) → `_balance += pnl_delta − exit_commission`; round-trip balance khớp worked-example (net = gross − entry_comm − exit_comm).
   - **4 fill path đều có commission**: market, limit-immediate, limit-cross (bar), synthetic SL/TP exit. ⚠️ Test riêng path synthetic exit (rủi ro #1).
   - `_can_afford`: notional+commission > balance → REJECTED (`REASON_INSUFFICIENT_BALANCE`).
   - `commission_model` default (bps=0) → balance như pre-R3 (backward compat).

3. **Factory wiring** — `broker_factory` build paper với `commission_percent=0.0004` → broker tính 4bps (khẳng định percent→bps đúng, không ×10000 sai).

4. **OKX fee** — `tests/core_test/infra/brokers/okx/test_okx_order_mapper.py` (NEW):
   - `fee="-0.42"` → `commission == 0.42`.
   - `fee="0.05"` (rebate) → `0.05`.
   - không `fee` / `fee=""` → `0.0`, không raise.

## Churned assertions (update — expected)

- `tests/backtest_test/engine/test_engulfing_backtest.py`, `test_hitnrun2_backtest.py`: **số trades + gross PnL KHÔNG đổi**; **net/final balance đổi** do commission model. Update expected net/balance.
- `test_result_collector_*`: commission giờ từ `result.commission` — value giống formula cũ nếu broker inject cùng bps. Kiểm tra collector test dùng broker có commission_bps khớp config → metrics KHÔNG đổi. Nếu test dựng broker không inject model (default bps=0) mà config có commission → phát hiện + fix wiring test.
- `paper_broker_futures_accounting_test.py`: balance assertions cũ (no-commission) → thêm commission hoặc dùng bps=0 để giữ, tách case commission riêng.

## Verify (bắt buộc pass)

```
just test
ruff check src tests
pyright
lint-imports          # 8 contracts — CommissionModel ở trading không tạo contract mới
```

## Todo

- [x] `test_commission_model.py` (unit)
- [x] Paper broker commission tests (4 path + can_afford + backward-compat)
- [x] Factory percent→bps test
- [x] `test_okx_order_mapper.py` fee dấu
- [x] Update engulfing/hitnrun2 net+balance
- [x] Update collector/accounting assertions
- [x] `just test` xanh
- [x] `ruff` + `pyright` xanh
- [x] `lint-imports` 8/8

## Success criteria

- Toàn bộ test xanh; net PnL phản ánh commission; gross PnL + trade count bất biến.
- Coverage 4 fill path commission + OKX dấu âm→dương.
- Toolchain 4/4 pass.

## Risks

- **Đừng** sửa expected để "pass" mà giấu bug — nếu gross PnL/trade count đổi (không phải chỉ net) → có lỗi logic fill, dừng điều tra (không phải commission).
- Collector test có thể lộ wiring gap (broker không nhận model) — đó là tín hiệu đúng, fix wiring không phải fudge test.
