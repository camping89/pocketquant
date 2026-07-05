# Phase 02 — Test updates + full validation parity

**Priority:** P2 · **Status:** done · **Depends:** 01

Cập nhật test tham chiếu trực tiếp symbol đổi tên; chạy full gate; khẳng định số characterization **không đổi**.

## Context links

- `plan.md` (Invariants) · phase-01 (API mới)

## Related test files

**Modify**
- `tests/core_test/unit/domain/strategy/test_engulfing.py` — import + call rename + `.size`

**Verify (không sửa — chỉ construct `RiskConfig`, không đụng symbol đổi tên)**
- `tests/backtest_test/engine/test_engulfing_backtest.py` (`risk=RiskConfig(max_exposure_percent=…)`)
- `tests/backtest_test/engine/test_hitnrun2_backtest.py` (`RiskConfig(max_exposure_percent=…)`, `max_exposure_percent=1.0`)
- `tests/engine_test/test_reconcile_restart_resume_integration.py`, `tests/backtest_test/test_backtest_single_run_direct_task.py` (không ref trực tiếp — confirm)

## Implementation steps

### 1. `test_engulfing.py`

- Import (line ~19): `PositionSizerDomainService` → `PositionCalculatorDomainService`.
- `test_position_size_positive_for_shallow_pattern` (line ~232):
  ```python
  calc = PositionCalculatorDomainService.calculate(
      account_balance=10_000.0,
      entry_price=sig.entry_price,  # type: ignore[arg-type]
      stop_loss_price=sig.stop_loss_price,
      risk_config=RiskConfig(),
  )
  assert calc.size > 0
  ```

### 2. Grep sạch toàn repo (src + tests)

```bash
git grep -n 'PositionSizerDomainService\|\.calculate_size(\|\.validate_size(\|RiskModel\.KELLY\|RiskModel\.FIXED' -- 'src' 'tests'
```
→ rỗng (trừ journals `docs/`). Nếu còn hit ngoài dự kiến → sửa.

### 3. Full validation

```bash
just test                 # parity: engulfing/hitnrun2 số KHÔNG đổi
uv run ruff check .
uv run pyright
uv run lint-imports       # 8 contract
```

- **Parity check**: nếu bất kỳ số characterization (total_trades/gross PnL/net/final equity/Sharpe/max_drawdown) đổi → STOP, `calculate()` lệch công thức cũ; so lại step-2 phase-01 (`min(risk_amount/price_risk, cap)`).
- **Circular guard**: `pyright`/import phải xanh; nếu `ImportError` circular → xem lại TYPE_CHECKING trong service + thứ tự `risk/__init__.py`.

## Todo

- [x] `test_engulfing.py` rename + `.size`
- [x] `git grep` sạch symbol cũ
- [x] `just test` xanh, số parity không đổi
- [x] ruff + pyright + lint-imports (8) xanh

## Success criteria

- Toàn bộ suite pass; engulfing/hitnrun2 characterization number **không đổi** (bằng chứng logic percent-risk bảo toàn).
- 4 gate xanh (`just test`, ruff, pyright, lint-imports).
- Không circular import.

## Risk

- Nếu `test_hitnrun2_backtest.py`/`test_engulfing_backtest.py` số đổi → không phải test lỗi mà là parity drift ở `calculate()`; fix service, không sửa số kỳ vọng.

## Next

→ phase-03 (docs + roadmap + journal).
