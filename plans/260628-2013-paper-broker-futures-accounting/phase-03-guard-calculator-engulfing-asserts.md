---
phase: 3
title: "Guard calculator + engulfing asserts"
status: done
priority: P2
dependencies: [2]
---

# Phase 3: Guard calculator + engulfing asserts

## Overview

Thêm defense-in-depth guard ở `performance_calculator` + cập nhật engulfing/characterization test. Vì giữ `available_balance = _balance`, characterization `available_balance` assert KHÔNG đổi giá trị — chỉ thêm post-mark block khóa price propagation (red-team C10).

## Requirements

- Functional: `sharpe_ratio`/`sortino_ratio` không phát divide-by-zero kể cả khi curve chứa 0 (defense); engulfing test khóa Sharpe non-zero với fixture biến động; characterization test khóa price propagation (upl≠0).
- Non-functional: guard không đổi kết quả số khi curve hợp lệ; KHÔNG dùng `PYTHONWARNINGS=error` toàn suite (red-team C12).

## Architecture

### Guard (`performance_calculator.py:80` + `:122`)

```python
prev = equity_curve[:-1]
returns = np.divide(
    np.diff(equity_curve), prev,
    out=np.zeros(len(prev), dtype=float), where=prev != 0,
)
```

Áp 2 callsite. Guard hạ nguồn `std_return == 0 or isnan` giữ nguyên.

### Characterization test (`paper_broker_fills_characterization_test.py:93-101`)

`available_balance` GIỮ NGUYÊN giá trị (`= _balance`, không đổi semantics) — nhưng hiện code trừ notional khỏi `_balance` ở open (spot). Sau Phase 2 futures, open KHÔNG trừ `_balance` → `available_balance == 1_000_000` (full), KHÁC giá trị cũ `1M − notional`. **Đây là thay đổi đúng** (open không debit cash dưới futures). Update:

```python
balance = await b.get_balance()
# futures: open does NOT debit balance; cash only moves on realized close
assert balance.available_balance == pytest.approx(1_000_000.0)
assert balance.total_equity == pytest.approx(1_000_000.0)   # upl=0 at entry, no price moved yet

# red-team C10: price moves → total_equity tracks unrealized, available stays = _balance
b.set_current_price(_SYM, expected_fill * 1.10)
moved = await b.get_balance()
assert moved.total_equity > 1_000_000.0          # unrealized tracked (price propagation)
assert moved.available_balance == pytest.approx(1_000_000.0)  # available = _balance unchanged
```

Rename docstring "debits balance" → "opens position without debiting cash (futures)".

### Engulfing test (`test_engulfing_backtest.py`)

<!-- Updated: Validation Session 1 - Sharpe≠0 dùng fixture high-volatility riêng, không dựa engulfing round-trip -->

Engulfing multi-trade test: chỉ assert finite + balance re-derive (KHÔNG assert ≠0 ở đây — round-trip có thể ít biến động):
```python
assert result.metrics.sharpe_ratio == result.metrics.sharpe_ratio  # not NaN
assert abs(result.metrics.sharpe_ratio) != float("inf")
expected = 10_000.0 + sum(t.pnl for t in collected.trades)  # re-derive, không hard-pin
assert broker_final_balance == pytest.approx(expected)
```

Assert Sharpe **≠ 0** dùng **fixture high-volatility riêng** (validate-chốt): bars có swing giá rõ rệt giữa các bar (không phẳng) để MTM curve có variance thật → Sharpe non-zero. Test riêng `test_sharpe_nonzero_on_volatile_curve` (có thể test thẳng `PerformanceCalculator.sharpe_ratio` trên curve synthetic biến động, tách khỏi engulfing flow để không flaky).

## Related Code Files

- Modify: `src/pocketquant/backtest/domain/services/performance_calculator.py` (guard ×2)
- Modify: `tests/core_test/infra/brokers/paper_broker_fills_characterization_test.py` (futures + post-mark)
- Modify: `tests/backtest_test/engine/test_engulfing_backtest.py` (Sharpe non-zero + re-derived balance)

## Implementation Steps

1. Áp guard `np.divide` vào `sharpe_ratio:80` + `sortino_ratio:122`.
2. Update characterization `:93-101`: futures open semantics + post-mark price-propagation block.
3. Engulfing multi-trade test: assert finite + balance re-derived từ trade log. Thêm test riêng `test_sharpe_nonzero_on_volatile_curve` (fixture high-volatility) cho assert Sharpe≠0.
4. Chạy `uv run pytest tests/core_test/infra/brokers tests/backtest_test/engine/test_engulfing_backtest.py -q`.
5. Verify guard không đổi numerics: so `sharpe_ratio` trên 1 curve hợp lệ trước/sau guard bằng giá trị cụ thể (pin 1 số trong unit test calculator nếu cần — red-team C12).

## Success Criteria

- [ ] Guard áp 2 callsite; curve hợp lệ → numerics không đổi (pin 1 giá trị Sharpe cụ thể)
- [ ] Characterization test PASS: open không debit; post-mark total_equity tăng, available == _balance
- [ ] Engulfing multi-trade: Sharpe finite + balance re-derived PASS; test riêng `test_sharpe_nonzero_on_volatile_curve` assert ≠0 PASS
- [ ] KHÔNG dùng `PYTHONWARNINGS=error` toàn suite; chỉ targeted check 2 hàm metric

## Risk Assessment

- **Risk:** `out=np.zeros` dtype mismatch nếu int. **Mitigation:** `dtype=float`; equity là float.
- **Risk:** engulfing Sharpe == 0 hợp lệ nếu ít biến động. **Mitigation:** fixture cycles=3 có spike bar (test_engulfing_backtest.py:154) tạo biến động; nếu vẫn 0, dùng fixture high-volatility riêng cho assert non-zero.
