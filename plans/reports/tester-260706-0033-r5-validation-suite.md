# R5 Refactor Validation Suite Report
**Date:** 2026-07-06 | **Scope:** Full validation (no edits)

---

## Test Execution Results

### pytest (Full Suite)
- **Total Tests:** 560 passed, 1 skipped
- **Execution Time:** 8.76s
- **Status:** ✓ PASS
- **Notes:** Exact match to expected ~560 tests. All critical parity tests passing:
  - `test_engulfing.py` suite: 16 tests passing (parity proof)
  - `test_hitnrun2.py` suite: 18 tests passing (parity proof)
  - Backtest report collection: All tests passing
  - Broker equity integration: All tests passing

### Code Quality Checks

| Check | Result | Details |
|-------|--------|---------|
| **ruff** | ✓ PASS | All checks passed (0 violations) |
| **pyright** | ⚠ 1 ERROR | `test_engulfing.py:177` — reportOptionalOperand (Optional type assertion) |
| **lint-imports** | ✓ PASS | 8 contracts kept, 0 broken |

---

## Validation Details

### 1. Lint Results
```
ruff: All checks passed!
```
No violations detected. Code adheres to linting standards.

### 2. Type Checking (pyright)
```
Errors: 1 | Warnings: 0
```

**Issue:** `test_engulfing.py:177:12 - error: Operator "<" not supported for "None"`

**Location & Context:**
```python
Line 170:  assert sig is not None
Line 176:  assert sig.take_profit_price == pytest.approx(entry - (sl - entry))
Line 177:  assert sig.take_profit_price < entry  # TP below entry for a short
```

**Assessment:** Type annotation issue in test file (not R5-modified code). `SignalOut.take_profit_price` is typed as `Optional[float]`. Pyright correctly flags that line 177 doesn't narrow the type despite line 170's assertion on `sig` itself. Pre-existing issue (engulfing strategy is core domain, unmodified by R5).

**Impact:** None. Test passes at runtime; type checker is conservative.

### 3. Import Contracts
```
Contracts: 8 kept, 0 broken

✓ Layered architecture — app top tier KEPT
✓ Core domain stays free of infra adapters KEPT
✓ Core imports no inner package KEPT
✓ Engine imports no upper package KEPT
✓ Engine backtest and live drivers stay independent KEPT
✓ Shared engine machinery must not import drivers KEPT
✓ fastapi only in app KEPT
✓ No bson/ObjectId usage — UUID7 only KEPT
```

All architectural contracts maintained. No import violations introduced.

---

## Parity Verification

**Key Assertion:** Backtest metrics are numerically identical after refactor.

| Metric | Tests | Status |
|--------|-------|--------|
| **Engulfing Characterization** | 16 tests | ✓ PASS |
| **HitNRun2 Characterization** | 18 tests | ✓ PASS |
| **Equity Ledger (broker-sourced)** | Multiple suites | ✓ PASS |
| **Report Collection** | Full suite | ✓ PASS |

Parity tests passing = backtest output (max_drawdown, total_return, Sharpe, total_trades, gross PnL) is numerically identical to pre-refactor state.

---

## Summary

**pytest:** 560 passed / 1 skipped / 0 failed  
**ruff:** 0 violations  
**pyright:** 1 error (pre-existing, test file, no functional impact)  
**lint-imports:** 8 kept / 0 broken  

**Verdict:** **PARITY OK** — R5 refactor maintains numerical parity. No regressions detected. Pyright error is pre-existing type annotation issue in test code unrelated to R5 changes.

---

**Status:** DONE  
**Summary:** Full validation suite executed; 560 tests pass (parity proof tests included); no R5-related regressions. Pyright flagged pre-existing type annotation issue in engulfing test (not modified by R5).

---

## Unresolved Questions
None. Validation complete and conclusive.
