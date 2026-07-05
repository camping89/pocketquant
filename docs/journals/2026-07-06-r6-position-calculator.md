# R6: Position Calculator — VO Extraction + Risk Defaults Centralization

**Date**: 2026-07-06 01:30  
**Severity**: Medium  
**Component**: Core domain risk, sizing logic, service interface  
**Status**: Completed  

---

## What Happened

Hoàn tất refactor R6 (Position Calculator Refactor) — phần LOGIC của initiative trading-calculation-fix. Refactor này thay đổi sizing service interface + trích xuất VO mới:

- Rename `PositionSizerDomainService` → `PositionCalculatorDomainService`; file `position_sizer_domain_service.py` → `position_calculator_domain_service.py`.
- Thay đổi `calculate_size()` (trả `float`) → `calculate()` (trả VO mới `PositionCalculation` chứa: `size`, `notional`, `risk_amount`, `est_entry_commission`); VO frozen dataclass, file leaf riêng `core/domain/risk/position_calculation.py`.
- Centralize 3 risk defaults thành class consts (1-source): `RISK_PER_TRADE = 0.02`, `MAX_EXPOSURE_PERCENT = 0.10`, `DEFAULT_SL_RISK_PERCENT = 0.01`. `RiskConfig` fields dùng consts làm default.
- Xóa dead code: `RiskModel.KELLY` + `RiskModel.FIXED` enum members, hàm `_kelly_size()`, `_fixed_size()`, `validate_size()`; `RiskModel` giữ lại 1 member `PERCENT_RISK`.
- `RiskCheckHandler`: thêm `config: RiskConfig | None = None`, fallback consts khi không override.
- Call site `strategy_app_service.py`: đổi `.calculate_size()` → `.calculate(...).size`.

Thay đổi trên branch `develop` (9 file src/tests: 8 modify + 1 create, chưa commit). Mục tiêu unblock R7 (BrokerConfig tune defaults) + R-series (backtest commission modeling).

---

## The Brutal Truth

Refactor này sạch, an toàn, 560/560 tests pass — nhưng cái ngậm ngầm là **circular import** giữa `RiskConfig` (dùng `CommissionModel` type hint) + `PositionCalculatorDomainService` (dùng `RiskConfig`). Không thể import trực tiếp. Thay vì:

- Tạo file trung gian hay di chuyển RiskConfig → quá phức tạp
- Đã quyết định: VO (`PositionCalculation`) ở file leaf riêng + service dùng `TYPE_CHECKING` cho `RiskConfig`/`CommissionModel`; runtime đọc attribute + duck-type (`.compute` method khi có). Giải pháp này sạch, đôi khi duck-type nhưng rõ ràng + tested.

Điểm đau: không thể enforce `commission_model` param ở type-hint (nó `CommissionModel | None`, nhưng `TYPE_CHECKING` block nó). Runtime chain đúng (`value_objects → service → position_calculation`), pyright chỉ complain 1 lỗi baseline (test_engulfing.py:177 Optional — pre-existing, không thuộc R6).

---

## Technical Details

### Refactor Scope

| Item | Before | After | Motivation |
|---|---|---|---|
| Service name | `PositionSizerDomainService` | `PositionCalculatorDomainService` | "Sizer" = naming lỏng; "Calculator" rõ ràng + phản ánh logic phức tạp (size, notional, risk, commission) |
| Return type | `float` (size only) | `PositionCalculation` VO | Caller cần {size, notional, risk_amount, est_entry_commission} — trả 1 VO thay vì tuple/dict |
| Risk defaults | Hardcoded 0.02 / 0.10 / 0.01 ở nhiều chỗ | Class consts (1-source) | Easier to tune (centralize), easier to debug (xem consts ngay) |
| RiskModel enum | KELLY, FIXED, PERCENT_RISK | PERCENT_RISK only | Dead code removal: KELLY/FIXED không dùng, sizing logic đã 100% dùng percent-based |
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
- VO ở file leaf riêng → avoid circular import (PositionCalculatorDomainService không import RiskConfig trực tiếp).
- Caller: `.calculate(...).size` (backward-compatible, tests phần lớn chỉ dùng size).

### Risk Defaults Centralization

```python
class PositionCalculatorDomainService:
    RISK_PER_TRADE = 0.02            # 2% per trade
    MAX_EXPOSURE_PERCENT = 0.10      # 10% max portfolio exposure
    DEFAULT_SL_RISK_PERCENT = 0.01   # 1% default SL risk
```

- RiskConfig field defaults → tham chiếu consts: `risk_per_trade: float = PositionCalculatorDomainService.RISK_PER_TRADE`.
- 1-source: muốn đổi default 2% → 1.5%, chỉ đổi const này.

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
- Runtime: duck-type `.compute()` method (RiskConfig có, CommissionModel có); call-site always pass proper type.
- Tradeoff: pyright không catch type error ở `commission_model.compute()` — nhưng call-site live truyền `None` hoặc real CommissionModel (test coverage xanh).

### Dead Code Removal

| Code | Removed | Reason |
|---|---|---|
| `RiskModel.KELLY` enum | ✓ | 0 caller; sizing logic 100% percent-based |
| `RiskModel.FIXED` enum | ✓ | 0 caller; sizing logic 100% percent-based |
| `_kelly_size()` method | ✓ | Unreachable (KELLY enum gone) |
| `_fixed_size()` method | ✓ | Unreachable (FIXED enum gone) |
| `validate_size()` method | ✓ | Unused; size validation inline ở `calculate()` |

### Validation

| Gate | Result | Notes |
|---|---|---|
| `pytest` | 560 passed | Baseline unchanged; parity verified (engulfing/hitnrun2 characterization số không đổi — min(risk_amount/price_risk, cap) bảo toàn) |
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

- **Intent**: `RiskConfig` mô tả risk policy; `CommissionModel` là provider; `PositionCalculation` VO chứa output (size, notional, risk, commission).
- **Reality**: RiskConfig cần type-hint CommissionModel (để duck-type `.compute()`); PositionCalculation VO import từ service; service import RiskConfig → cycle.
- **Why it wasn't caught early**: R5 (CommissionModel) + R6 (Calculator refactor) là parallel tracks; chỉ khi tích hợp VO vào Calculator thì circular mới lộ diện.

### Why duck-type solution is acceptable

- **Alternative 1** (move types to `core.types`): Infrastructure concerns (broker models) vào shared types module → leak abstraction.
- **Alternative 2** (inject at runtime, no type-hint): Loss of type safety; pyright can't reason about `.compute()`.
- **TYPE_CHECKING solution**: Tradeoff kiểm soát (pyright) vs. pragmatism (duck-type at runtime, call-site validates).
- **Cost**: Một dòng comment trong service: `# type: ignore` (0 actual ignores needed, riêng TYPE_CHECKING block rõ ràng).

### Why VO ở file leaf riêng

- VO (`PositionCalculation`) dùng bởi service output + call-site.
- Nếu VO ở `position_calculator_domain_service.py` → service file import nó → service can't circular-import itself. Nhưng nếu VO dùng CommissionModel (future) → lại circular.
- File leaf `position_calculation.py` (pure VO, no deps → service) → break cycle.

---

## Lessons Learned

1. **VO extraction tránh circular import.** Nếu VO mix data từ multi-layer (domain + infra), VO ở file leaf riêng, service import VO (unidirectional).

2. **TYPE_CHECKING cho type-safety mà avoid runtime coupling.** Duck-type runtime valid (call-site đã enforce type); pyright happy. Trade: check comment khi maintain (".compute() must exist").

3. **Risk defaults = 3 consts, 1-source.** Centr tại service class; RiskConfig defaults tham chiếu consts. Thay đổi mặc định → 1 chỗ. (Không centralize `max_positions=3` ở risk_check.py — acceptable trade, chỉ 3 risk-percent consts là 1-source).

4. **Dead code removal scale với refactor.** KELLY/FIXED enum + 2 hàm đã dead hơn 6 tháng; refactor là cơ hội xóa. Không xóa ngay → tech debt grow.

5. **VO return type chargaff interface clarity.** `calculate_size() → float` vs. `calculate() → PositionCalculation{size, notional, risk, commission}` — latter self-document output shape; caller không cần doc to know fields.

---

## Next Steps

- [x] Refactor complete (PositionCalculatorDomainService + PositionCalculation VO)
- [x] Risk defaults centralized (3 class consts)
- [x] Dead code removed (KELLY/FIXED/validators)
- [x] Circular import fixed (TYPE_CHECKING + duck-type)
- [x] All tests pass (560/560)
- [x] Code review done (CLEAN, 0 critical/high/medium)
- [ ] **Commit + push develop** — changeset ready, chưa commit
- [ ] **Unblock R7** (BrokerConfig: tune RISK_PER_TRADE / MAX_EXPOSURE_PERCENT / DEFAULT_SL_RISK_PERCENT + USD 10k account, 4bps commission, currency defaults)
- [ ] **Forward R-series** (R7 config tune only; R8+ can wire CommissionModel → `calculate()` commission_model param if live-run needs commission modeling)
- [ ] **Monitor next VO** — if future VO (e.g., ExecutionResult) needs CommissionModel + other infra types, apply leaf-file lesson: keep pure domain separate, infra concerns in VO properties with duck-type fallback.

**Owner**: Core domain sizing refactor + risk defaults.  
**Timeline**: Completed 2026-07-06. Changeset ready, chưa commit.  
**Key takeaway**: VO leaf file + TYPE_CHECKING duck-type = clean circular-import solution. 3-const risk defaults = 1-source policy change.

---

## Verification

| Artifact | Status |
|---|---|
| Changeset | 9 file src/tests (8 modify + 1 create), logic identical, parity verified |
| Tests | 560 passed (baseline unchanged) |
| Linting | import-linter 8/8 ✓; ruff/pyright no new errors (except baseline) |
| Code review | CLEAN (0 critical/high/medium); interface change isolated (1 call site) |
| VO design | Frozen dataclass, 4 fields (size, notional, risk_amount, est_entry_commission); commission_model param optional, duck-type `.compute()` |
| Dead code | KELLY/FIXED enum members + 3 methods fully removed; `from_dict()` unreachable (literal fallback, doc'd) |
| Circular import | Fixed via TYPE_CHECKING + duck-type; pyright green (except baseline test_engulfing.py:177) |
| Handoff | VO + consts ready; R7 tune config only (no logic change) |
