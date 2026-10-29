# R7: Config Defaults Tune — Completed

**Date**: 2026-07-06 01:57  
**Severity**: Low  
**Component**: Backtest config, paper broker config, currency defaults  
**Status**: Shipped

---

## What Changed

Tuned three groups of defaults (no logic/contract changes).

| Group | Change | Sites | Rationale |
|-------|--------|-------|-----------|
| **A: Paper Initial Balance** | `100_000` → `10_000` | `core/config.py`, `app/di/broker_factory.py` (paper branch), `core/infra/brokers/paper/paper_broker_adapter.py`, `.env` | Faster test iteration; 10k base = tighter margin simulation for slippage/commission visibility |
| **B: Currency Default** | `"USDT"` → `"USD"` | `paper_broker_adapter.py`, `broker_factory.py` (paper), `engine/backtest/backtest_sandbox_app_service.py` | Paper/backtest ops are domestic (USD quote); OKX kept `"USDT"` (inst_suffix + okx_* logic untouched); `AccountBalance` VO default left `"USDT"` (no-op — all call sites pass explicit currency) |
| **C: Backtest Commission** | `10.0 bps` → `4.0 bps` | `core/domain/backtest/config.py` (field + docstring example), `engine/backtest/backtest_command_service.py`, `engine/backtest/backtest_dispatch.py` | Aligns paper live (`paper_commission_percent=0.0004` = 4 bps from R3); web UI backtest-form inherits 4 bps (sends no explicit commission_bps) |

---

## Critical: `.env` Overrides Code

**Gotcha caught**: `.env` has `PAPER_INITIAL_BALANCE=100_000` (old hardcoded value). Code defaults changed, but `.env` override was **NOT updated** → local runs would stay at 100k.

**Action taken**: Updated `.env` to `PAPER_INITIAL_BALANCE=10000`. This is config state tracked in `.gitignore`, so deployment `.env` remains under ops control; local dev now matches code default.

---

## Verification

**Test suite**: `pytest` → **561 passed, 1 skipped**. Zero failures.

**New worked-example test** (`tests/backtest_test/engine/test_r7_worked_example_defaults.py`):
- Drives real `PaperBrokerAdapter` with R7 defaults: qty=10, initial=10_000, slippage=0.001, commission=4 bps, currency=USD
- Entry fill: 100.10 (commission 0.4004)
- Exit fill: 103.896 (commission 0.415584)
- Gross PnL: 37.96 → final balance: **10_037.144**
- Asserts structural invariants: per-fill commission = `price*qty*0.0004`; net = gross − Σfee; final = 10_000 + net_pnl
- Reproduces design doc §6 exactly

**Characterization tests** (engulfing/hitnrun2, collector mark-to-market): Pin explicit `commission_bps`/`initial_capital`/`currency`, unchanged by defaults → tests passed.

**Static checks**:
- ruff: clean
- pyright: 0 new errors (1 pre-existing baseline in test_engulfing.py)
- import-linter: 8/8 contracts held

**Code review**: Independent re-derivation of 10_037.144 final balance. CLEAN verdict.

---

## Lesson

Tuning defaults is mechanical, but environment overrides (`.env`) can silently negate code changes. Always audit override sources when changing defaults.

---

## Next Steps

None—R7 is config-only. Ready for merge.
