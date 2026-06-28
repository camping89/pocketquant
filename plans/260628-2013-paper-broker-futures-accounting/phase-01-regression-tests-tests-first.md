---
phase: 1
title: "Regression tests (tests-first)"
status: done
priority: P1
dependencies: []
---

# Phase 1: Regression tests (tests-first)

## Overview

Viết test **trước** để pin hành vi accounting **ĐÚNG** (futures model, `available_balance = _balance` giữ nguyên). Mỗi test phải **FAIL** trên code hiện tại với arithmetic chứng minh được (red-first), rồi PASS sau Phase 2.

## Requirements

- Functional: long/short round-trip, all-in open (no zero total_equity), partial-close no-double-count, add-then-reduce (long+short), SL/TP synthetic-exit balance, price-propagation (unrealized track giá per-bar).
- Non-functional: precompute current-code result VS expected post-fix result cho mỗi test — confirm khác nhau (không defer "run and see"). `available_balance` assert == `_balance` (semantics KHÔNG đổi).

## Architecture

Test mới: `tests/core_test/infra/brokers/paper_broker_futures_accounting_test.py`. Dùng `PaperBroker` trực tiếp + `BarCompletedEvent` cho SL/TP path (như `paper_broker_fills_characterization_test.py`).

Mô hình kỳ vọng (futures 1×, initial=10000, no commission/slippage):

| Test | Action | current-code _balance (buggy) | expected _balance | expected total_equity |
|---|---|---|---|---|
| long round-trip | open 100@100, mark→110, close@110 | `10000 −10000 +(11000+1000)=12000` ❌ | `10000 +1000=11000` | entry:10000 → mark:11000 → close:11000 |
| all-in no-zero | open 100@100 | total_equity = `(10000−10000)+0 = 0` ❌ | total_equity=10000 (upl=0) | 10000 |
| short round-trip | open 100@100, mark→90, close@90 | `10000 +10000 +(9000+1000)... ` ❌ double | `10000+1000=11000` | 10000→11000→11000 |
| partial no-double | open 100@100, close 40@110, close 60@110 | proceeds+cumulative realized → ❌ | `10000 + (40+60)×10 = 11000` | — |
| add-then-reduce long | open 100@100, add 100@120, reduce 100@130 | ❌ | avg entry=110; realized=(130−110)×100=2000 → `12000` | track |
| add-then-reduce short | open 100@100, add 100@80, cover 100@70 | ❌ | avg entry=90; realized=(90−70)×100=2000 → `12000` | track |
| SL/TP exit | open long SL=95, bar low=94 | ❌ exit accounting | `_balance += (95−100)×qty` realized | flat sau exit |
| price propagation | open 100@100, set price 110, get_balance | total_equity=10000 (frozen current_price) ❌ | total_equity=11000 (unrealized tracks) | — |
| available==balance | sau open all-in | — | `available_balance == _balance` (giữ nguyên) | — |

**Bỏ** (red-team C3/C5): `test_can_afford_under_free_margin`, `test_available_balance_is_free_margin` (free-margin) — vì giữ `available_balance = _balance`, không đổi `_can_afford`.

## Related Code Files

- Create: `tests/core_test/infra/brokers/paper_broker_futures_accounting_test.py`
- Read: `tests/core_test/infra/brokers/paper_broker_fills_characterization_test.py`, `tests/core_test/infra/brokers/test_paper_broker_sl_tp_fill.py`, `src/pocketquant/core/domain/position/entities.py` (cost_basis/unrealized/realized + add averaging :96-98)

## Implementation Steps

1. `test_long_round_trip_balance_only_changes_by_realized` — assert `_balance` đổi đúng `Δrealized`. Precompute current=12000, expected=11000.
2. `test_open_all_in_total_equity_not_zero` — `get_balance().total_equity == initial` tại entry (upl=0). Precompute current=0, expected=10000.
3. `test_short_round_trip_balance` — precompute current (double), expected=11000.
4. `test_partial_close_no_double_count` — close 40 rồi 60; expected=11000. Khóa cảnh báo delta (plan.md).
5. `test_add_then_reduce_long` + `test_add_then_reduce_short` — verify avg entry_price + realized delta sau add (red-team C11).
6. `test_sl_tp_synthetic_exit_balance` — open long SL, drive BarCompletedEvent low≤SL, assert `total_equity == initial + realized`, `available_balance == _balance` flat sau exit (red-team C5).
7. `test_unrealized_tracks_price_per_bar` — open, publish `BarCompletedEvent` (close khác entry, không chạm SL/TP), `get_balance().total_equity` phản ánh unrealized (red-team C4). Dùng `BarCompletedEvent` (KHÔNG chỉ `set_current_price`) vì mark giờ ở `_on_bar_completed` (validate-chốt). FAIL hiện tại (current_price frozen).
8. `test_available_balance_equals_balance` — assert `available_balance == _balance` (pin semantics giữ nguyên).
9. Chạy `uv run pytest <newfile> -q` → confirm tất cả FAIL với lý do khớp precompute.

## Success Criteria

- [ ] 8 test viết xong, chạy được
- [ ] Mỗi test có precompute current-vs-expected trong comment, FAIL hiện tại đúng lý do
- [ ] Có test SL/TP synthetic-exit balance + add-then-reduce + price-propagation
- [ ] KHÔNG có free-margin test (giữ available=_balance)

## Risk Assessment

- **Risk:** `set_current_price` không đủ để `unrealized_pnl` cập nhật (current_price frozen) — đây CHÍNH là điều test #7 phải bắt; Phase 2 mark trong `_on_bar_completed` fix nó. **Mitigation:** test #7 publish `BarCompletedEvent` (không chỉ `set_current_price`), red-first chứng minh gap.
- **Risk:** số kỳ vọng sai. **Mitigation:** bảng arithmetic + cross-check `cost_basis`/`_calculate_pnl_per_unit` (entities.py:162-166).
