---
phase: 5
title: "Verify"
status: done
priority: P1
dependencies: [3, 4]
---

# Phase 5: Verify

## Overview

Chạy full quality gates + xác nhận không regression cho forward-test path. Đóng acceptance criteria. KHÔNG hard-pin số đo cũ; KHÔNG dùng `PYTHONWARNINGS=error` toàn suite (red-team C9/C12).

## Requirements

- Functional: toàn bộ suite xanh; divide-by-zero biến mất; metrics đúng; forward path (sizing/exposure) không vỡ.
- Non-functional: import-linter 7 contracts giữ nguyên.

## Architecture

Verify theo tầng: broker unit → backtest integration → engine/risk → full suite + lint + types.

## Related Code Files

- Read-only verify: touchpoints Phase 2-4.

## Implementation Steps

1. Broker unit: `uv run pytest tests/core_test/infra/brokers -q` → Phase 1 tests + characterization + SL/TP suite PASS.
2. Divide-by-zero: targeted check 2 hàm metric không phát RuntimeWarning (không gate toàn suite — red-team C12): `uv run pytest tests/backtest_test/engine/test_engulfing_backtest.py tests/backtest_test/engine/test_hitnrun2_backtest.py -W error::RuntimeWarning -q`.
3. Verify số (re-derive, KHÔNG hard-pin — red-team C9): engulfing broker final balance == `10000 + Σ(t.pnl for t in trades)` từ trade log của chính run; structural "no double-count" (test #4 Phase 1).
4. SL/TP exit accounting: `tests/core_test/infra/brokers/test_paper_broker_sl_tp_fill.py` + Phase 1 test #6 (balance assertion) — red-team C5.
5. Forward sizing không regress (red-team C1/C8): vì giữ `available_balance = _balance`, sizing không đổi. Verify bằng `uv run pytest tests/engine_test -q` + nếu chưa có test sizing trực tiếp, xác nhận `available_balance == _balance` qua Phase 1 test #8 (đủ vì semantics không đổi).
6. Cascade + persistence: `tests/app_test/integration/test_run_all_backtest_cascade.py`, `tests/backtest_test/engine/test_backtest_app_service_persistence.py` (đã pre-check: KHÔNG assert balance number → an toàn).
7. `just test` (full) + `just lint` + `just types`.
8. import-linter 7 contracts (trong `just lint`/`just types` hoặc `uv run lint-imports`).
9. Đối chiếu acceptance criteria `plan.md`, tick từng mục.

## Success Criteria

- [ ] Broker unit + characterization + SL/TP PASS
- [ ] 2 hàm metric không phát divide-by-zero (targeted, không gate toàn suite)
- [ ] Engulfing balance == `10000 + Σ realized` re-derive từ trade log (không hard-pin 10553.7)
- [ ] Sharpe/Sortino finite-non-zero (fixture biến động); curve track giá per-bar
- [ ] SL/TP exit có balance assertion PASS
- [ ] `available_balance == _balance` (sizing không đổi); `tests/engine_test` PASS
- [ ] `just test` + `just lint` + `just types` xanh; import-linter 7 contracts OK

## Risk Assessment

- **Risk:** test ẩn dựa số sai cũ. **Mitigation:** đã pre-check cascade/persistence KHÔNG assert balance number; nếu fail vì số → xác nhận số mới đúng rồi update, ghi lý do (không weaken test).
- **Risk:** forward reconcile (live) dùng balance khác. **Mitigation:** OKXBroker balance từ sàn (`map_okx_balance_to_domain`), không qua `_execute_fill`; `available_balance` PaperBroker giữ `= _balance` → sizing không đổi.
- **Risk:** price-propagation side-effect trong `get_balance` gây flaky nếu gọi đa luồng. **Mitigation:** trong `_lock`; idempotent (chỉ set current_price).
