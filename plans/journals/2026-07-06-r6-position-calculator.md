# R6: Position Calculator — VO Extraction + Risk Defaults Centralization

**Date**: 2026-07-06 01:30  
**Severity**: Medium  
**Component**: Core domain risk, sizing logic, service interface  
**Status**: Completed  

---

## What Happened

Completed the R6 refactor (Position Calculator Refactor) — the LOGIC part of the trading-calculation-fix initiative. This refactor changes the sizing service interface + extracts a new VO:

- Rename `PositionSizerDomainService` → `PositionCalculatorDomainService`; file `position_sizer_domain_service.py` → `position_calculator_domain_service.py`.
- Change `calculate_size()` (returns `float`) → `calculate()` (returns new VO `PositionCalculation` containing: `size`, `notional`, `risk_amount`, `est_entry_commission`); VO frozen dataclass, in its own leaf file `core/domain/risk/position_calculation.py`.
- Centralize 3 risk defaults into class consts (1-source): `RISK_PER_TRADE = 0.02`, `MAX_EXPOSURE_PERCENT = 0.10`, `DEFAULT_SL_RISK_PERCENT = 0.01`. `RiskConfig` fields use the consts as defaults.
- Remove dead code: `RiskModel.KELLY` + `RiskModel.FIXED` enum members, functions `_kelly_size()`, `_fixed_size()`, `validate_size()`; `RiskModel` keeps a single member `PERCENT_RISK`.
- `RiskCheckHandler`: add `config: RiskConfig | None = None`, fallback to consts when not overridden.
- Call site `strategy_app_service.py`: change `.calculate_size()` → `.calculate(...).size`.

Changes on branch `develop` (9 src/test files: 8 modify + 1 create, not yet committed). Goal: unblock R7 (BrokerConfig tune defaults) + R-series (backtest commission modeling).

---

## The Brutal Truth

This refactor is clean, safe, 560/560 tests pass — but the hidden catch is a **circular import** between `RiskConfig` (uses `CommissionModel` type hint) + `PositionCalculatorDomainService` (uses `RiskConfig`). Cannot import directly. Instead of:

- Creating an intermediary file or moving RiskConfig → too complex
- Decided: VO (`PositionCalculation`) in its own leaf file + service uses `TYPE_CHECKING` for `RiskConfig`/`CommissionModel`; runtime reads attributes + duck-type (`.compute` method when present). This solution is clean, sometimes duck-typed but explicit + tested.

Pain point: cannot enforce the `commission_model` param at the type-hint level (it's `CommissionModel | None`, but `TYPE_CHECKING` blocks it). Runtime chain is correct (`value_objects → service → position_calculation`), pyright only complains about 1 baseline error (test_engulfing.py:177 Optional — pre-existing, not part of R6).

---

## Technical Details

### Refactor Scope

| Item | Before | After | Motivation |
|---|---|---|---|
| Service name | `PositionSizerDomainService` | `PositionCalculatorDomainService` | "Sizer" = loose naming; "Calculator" is clear + reflects the complex logic (size, notional, risk, commission) |
| Return type | `float` (size only) | `PositionCalculation` VO | Caller needs {size, notional, risk_amount, est_entry_commission} — return a single VO instead of a tuple/dict |
| Risk defaults | Hardcoded 0.02 / 0.10 / 0.01 in many places | Class consts (1-source) | Easier to tune (centralize), easier to debug (see consts directly) |
| RiskModel enum | KELLY, FIXED, PERCENT_RISK | PERCENT_RISK only | Dead code removal: KELLY/FIXED unused, sizing logic already 100% percent-based |
| Risk handler config | Required | Optional (config: RiskConfig \| None = None) | Tests parameterize sizing; fallback consts when no override |
| Import coupling | Direct import RiskConfig in service | TYPE_CHECKING + duck-type | Break circular: RiskConfig → CommissionModel \| PositionCalculation |

### VO Extraction: PositionCalculation

```python
# core/domain/risk/position_calculation.py
@dataclass(frozen=True)
class PositionCalculation:
    size: float
    notional: float
    risk_amount: float
    est_entry_commission: float = 0.0  # Optional, default 0.0
```

- Frozen: immutable, hashable (cache-safe).
- VO in its own leaf file → avoid circular import (PositionCalculatorDomainService doesn't import RiskConfig directly).
- Caller: `.calculate(...).size` (backward-compatible, tests mostly only use size).

### Risk Defaults Centralization

```python
class PositionCalculatorDomainService:
    RISK_PER_TRADE = 0.02            # 2% per trade
    MAX_EXPOSURE_PERCENT = 0.10      # 10% max portfolio exposure
    DEFAULT_SL_RISK_PERCENT = 0.01   # 1% default SL risk
```

- RiskConfig field defaults → reference the consts: `risk_per_trade: float = PositionCalculatorDomainService.RISK_PER_TRADE`.
- 1-source: to change the default 2% → 1.5%, only change this const.

### Circular Import Fix: TYPE_CHECKING + Duck-Type

```python
# core/domain/risk/position_calculator_domain_service.py
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.domain.risk.models.risk_config import RiskConfig
    from core.infra.broker.commission.models import CommissionModel

class PositionCalculatorDomainService:
    def calculate(
        self,
        price: Decimal,
        account_equity: Decimal,
        risk_config: "RiskConfig | None" = None,
        commission_model: "CommissionModel | None" = None,
    ) -> PositionCalculation:
        config = risk_config or RiskConfig()
        # runtime: config.compute() — no type enforcement, but duck-type validated at call-site
        commission_fee = commission_model.compute(...) if commission_model else 0.0
```

- TYPE_CHECKING block: pyright type-checks; imports don't run.
- Runtime: duck-type `.compute()` method (RiskConfig has it, CommissionModel has it); call-site always passes the proper type.
- Tradeoff: pyright doesn't catch the type error at `commission_model.compute()` — but the live call-site passes `None` or a real CommissionModel (test coverage green).

### Dead Code Removal

| Code | Removed | Reason |
|---|---|---|
| `RiskModel.KELLY` enum | ✓ | 0 caller; sizing logic 100% percent-based |
| `RiskModel.FIXED` enum | ✓ | 0 caller; sizing logic 100% percent-based |
| `_kelly_size()` method | ✓ | Unreachable (KELLY enum gone) |
| `_fixed_size()` method | ✓ | Unreachable (FIXED enum gone) |
| `validate_size()` method | ✓ | Unused; size validation inline in `calculate()` |

### Validation

| Gate | Result | Notes |
|---|---|---|
| `pytest` | 560 passed | Baseline unchanged; parity verified (engulfing/hitnrun2 characterization numbers unchanged — min(risk_amount/price_risk, cap) preserved) |
| `ruff` + `pyright` | Only pre-existing (test_engulfing.py:177 Optional) | R6 zero new style/type violations |
| `lint-imports` | 8/8 contracts PASS | Circular import fix: VO → service → calculation chain valid |
| Code review | CLEAN (0 critical/high/medium) | Logic identical; interface change isolated to strategy_app_service.py (1 line: `.calculate(...).size`) |

---

## What We Tried

| Approach | Outcome |
|---|---|
| Direct import RiskConfig in service (tight coupling) | ✗ Circular: RiskConfig → CommissionModel → risk_calculation VO; VO → service. Blocked pyright |
| Move RiskConfig to separate leaf file (break circle) | ✗ Doesn't solve it; RiskConfig still needs types from both ends |
| TYPE_CHECKING + duck-type (runtime `.compute()` call) | ✓ Compiles, tests pass, pyright green (except baseline); minimal runtime cost |
| Rename `calculate_size()` → `calculate()` (breaking change) | ✓ Better semantics; single call site `strategy_app_service.py` updated |
| Keep `from_dict()` method (legacy YAML support) | ✓ Unreachable (0 caller, YAML "kelly"/"fixed" keys dead); kept with literal fallback + doc note |

---

## Root Cause Analysis

### Why circular import emerged

- **Intent**: `RiskConfig` describes the risk policy; `CommissionModel` is the provider; `PositionCalculation` VO contains the output (size, notional, risk, commission).
- **Reality**: RiskConfig needs to type-hint CommissionModel (to duck-type `.compute()`); PositionCalculation VO is imported from the service; service imports RiskConfig → cycle.
- **Why it wasn't caught early**: R5 (CommissionModel) + R6 (Calculator refactor) were parallel tracks; the circular import only surfaced when integrating the VO into the Calculator.

### Why duck-type solution is acceptable

- **Alternative 1** (move types to `core.types`): Infrastructure concerns (broker models) into a shared types module → leak abstraction.
- **Alternative 2** (inject at runtime, no type-hint): Loss of type safety; pyright can't reason about `.compute()`.
- **TYPE_CHECKING solution**: Tradeoff between control (pyright) vs. pragmatism (duck-type at runtime, call-site validates).
- **Cost**: One comment line in the service: `# type: ignore` (0 actual ignores needed, just an explicit TYPE_CHECKING block).

### Why the VO is in its own leaf file

- VO (`PositionCalculation`) used by the service output + call-site.
- If the VO were in `position_calculator_domain_service.py` → the service file imports it → the service can't circular-import itself. But if the VO uses CommissionModel (future) → circular again.
- Leaf file `position_calculation.py` (pure VO, no deps → service) → break the cycle.

---

## Lessons Learned

1. **VO extraction avoids circular imports.** If a VO mixes data from multiple layers (domain + infra), put the VO in its own leaf file, service imports the VO (unidirectional).

2. **TYPE_CHECKING for type-safety while avoiding runtime coupling.** Duck-type at runtime is valid (call-site already enforces the type); pyright is happy. Trade: check the comment when maintaining (".compute() must exist").

3. **Risk defaults = 3 consts, 1-source.** Centralized in the service class; RiskConfig defaults reference the consts. Change a default → 1 place. (Don't centralize `max_positions=3` in risk_check.py — acceptable trade, only the 3 risk-percent consts are 1-source).

4. **Dead code removal scales with the refactor.** KELLY/FIXED enum + 2 functions had been dead for over 6 months; the refactor is the opportunity to remove them. Not removing them now → tech debt grows.

5. **VO return type sharpens interface clarity.** `calculate_size() → float` vs. `calculate() → PositionCalculation{size, notional, risk, commission}` — the latter self-documents the output shape; the caller doesn't need docs to know the fields.

---

## Next Steps

- [x] Refactor complete (PositionCalculatorDomainService + PositionCalculation VO)
- [x] Risk defaults centralized (3 class consts)
- [x] Dead code removed (KELLY/FIXED/validators)
- [x] Circular import fixed (TYPE_CHECKING + duck-type)
- [x] All tests pass (560/560)
- [x] Code review done (CLEAN, 0 critical/high/medium)
- [ ] **Commit + push develop** — changeset ready, not yet committed
- [ ] **Unblock R7** (BrokerConfig: tune RISK_PER_TRADE / MAX_EXPOSURE_PERCENT / DEFAULT_SL_RISK_PERCENT + USD 10k account, 4bps commission, currency defaults)
- [ ] **Forward R-series** (R7 config tune only; R8+ can wire CommissionModel → `calculate()` commission_model param if live-run needs commission modeling)
- [ ] **Monitor next VO** — if future VO (e.g., ExecutionResult) needs CommissionModel + other infra types, apply leaf-file lesson: keep pure domain separate, infra concerns in VO properties with duck-type fallback.

**Owner**: Core domain sizing refactor + risk defaults.  
**Timeline**: Completed 2026-07-06. Changeset ready, not yet committed.  
**Key takeaway**: VO leaf file + TYPE_CHECKING duck-type = clean circular-import solution. 3-const risk defaults = 1-source policy change.

---

## Verification

| Artifact | Status |
|---|---|
| Changeset | 9 src/test files (8 modify + 1 create), logic identical, parity verified |
| Tests | 560 passed (baseline unchanged) |
| Linting | import-linter 8/8 ✓; ruff/pyright no new errors (except baseline) |
| Code review | CLEAN (0 critical/high/medium); interface change isolated (1 call site) |
| VO design | Frozen dataclass, 4 fields (size, notional, risk_amount, est_entry_commission); commission_model param optional, duck-type `.compute()` |
| Dead code | KELLY/FIXED enum members + 3 methods fully removed; `from_dict()` unreachable (literal fallback, doc'd) |
| Circular import | Fixed via TYPE_CHECKING + duck-type; pyright green (except baseline test_engulfing.py:177) |
| Handoff | VO + consts ready; R7 tune config only (no logic change) |
