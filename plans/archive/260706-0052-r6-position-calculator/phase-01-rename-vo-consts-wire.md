# Phase 01 — Rename service + PositionCalculation VO + consts + kill dead code + wire

**Priority:** P2 · **Status:** done · **Depends:** —

Rename `PositionSizerDomainService`→`PositionCalculatorDomainService`, đổi `calculate_size()→calculate()` trả `PositionCalculation`, đưa risk params thành class consts (1 source), xoá `KELLY`/`FIXED`/`validate_size`, `RiskCheckHandler` import consts, rewire call site.

## Context links

- `plan.md` (D1–D6) · design `…/design-execution-metrics-separation.md` §5/§9

## Related code files

**Create**
- `src/pocketquant/core/domain/risk/position_calculation.py` — VO `PositionCalculation` (frozen, no deps)

**Rename**
- `src/pocketquant/core/domain/risk/services/position_sizer_domain_service.py` → `position_calculator_domain_service.py`

**Modify**
- `…/risk/services/position_calculator_domain_service.py` — class rename, consts, `calculate()`, xoá KELLY/FIXED/validate_size
- `…/risk/value_objects.py` — RiskConfig defaults tham chiếu consts
- `…/risk/enums.py` — xoá `KELLY`, `FIXED`
- `…/risk/__init__.py` — export `PositionCalculatorDomainService`, `PositionCalculation` (bỏ `PositionSizerDomainService`)
- `…/risk/services/__init__.py` — export `PositionCalculatorDomainService`
- `src/pocketquant/engine/execution/risk_check.py` — import consts, config `RiskConfig | None`
- `src/pocketquant/engine/strategy/strategy_app_service.py` — import + call site `.calculate(...).size`

## Implementation steps

### 1. `position_calculation.py` (VO mới)

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class PositionCalculation:
    size: float           # base units
    notional: float       # size * entry_price
    risk_amount: float    # account_balance * risk_per_trade (khoản vốn đặt rủi ro)
    est_entry_commission: float  # ước phí entry (0.0 nếu không có CommissionModel)
```

### 2. `position_calculator_domain_service.py` (rename file + rewrite)

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from pocketquant.core.domain.risk.position_calculation import PositionCalculation

if TYPE_CHECKING:
    from pocketquant.core.domain.risk.value_objects import RiskConfig
    from pocketquant.core.domain.trading import CommissionModel


class PositionCalculatorDomainService:
    RISK_PER_TRADE = 0.02           # phần vốn rủi ro mỗi lệnh, đo trên khoảng entry→SL
    MAX_EXPOSURE_PERCENT = 0.10     # trần notional theo phần vốn (cap gần như luôn thắng)
    DEFAULT_SL_RISK_PERCENT = 0.01  # price-risk dự phòng khi lệnh không có SL

    @staticmethod
    def calculate(
        account_balance: float,
        entry_price: float,
        stop_loss_price: float | None,
        risk_config: RiskConfig | None = None,
        commission_model: CommissionModel | None = None,
    ) -> PositionCalculation:
        cls = PositionCalculatorDomainService
        if account_balance <= 0 or entry_price <= 0:
            return PositionCalculation(0.0, 0.0, 0.0, 0.0)

        risk_per_trade = risk_config.risk_per_trade if risk_config else cls.RISK_PER_TRADE
        max_exposure = risk_config.max_exposure_percent if risk_config else cls.MAX_EXPOSURE_PERCENT

        if stop_loss_price is None:
            price_risk = entry_price * cls.DEFAULT_SL_RISK_PERCENT
        else:
            price_risk = abs(entry_price - stop_loss_price)
        if price_risk == 0:
            return PositionCalculation(0.0, 0.0, 0.0, 0.0)

        risk_amount = account_balance * risk_per_trade
        cap = (account_balance * max_exposure) / entry_price
        size = min(risk_amount / price_risk, cap)
        notional = size * entry_price
        est = commission_model.compute(entry_price, size) if commission_model else 0.0
        return PositionCalculation(
            size=size, notional=notional, risk_amount=risk_amount, est_entry_commission=est
        )
```

- **XOÁ** `_percent_risk_size`, `_kelly_size`, `_fixed_size`, `validate_size`, dispatch `if/elif model`.
- **Parity**: `size = min(risk_amount/price_risk, cap)` y hệt `_percent_risk_size` cũ. Không đổi thứ tự/độ chính xác float.
- `RiskConfig`/`CommissionModel` chỉ `TYPE_CHECKING` (runtime đọc attribute + gọi `.compute` duck-typed) → cắt vòng import + không thêm runtime dep risk→trading.

### 3. `value_objects.py` (RiskConfig defaults ← consts)

```python
from dataclasses import dataclass

from pocketquant.core.domain.risk.enums import RiskModel
from pocketquant.core.domain.risk.services.position_calculator_domain_service import (
    PositionCalculatorDomainService,
)


@dataclass(frozen=True)
class RiskConfig:
    model: RiskModel = RiskModel.PERCENT_RISK
    risk_per_trade: float = PositionCalculatorDomainService.RISK_PER_TRADE
    max_positions: int = 3
    max_exposure_percent: float = PositionCalculatorDomainService.MAX_EXPOSURE_PERCENT

    def __post_init__(self) -> None:
        if not 0 < self.risk_per_trade <= 0.10:
            raise ValueError(f"risk_per_trade must be 0-10%, got {self.risk_per_trade:.1%}")
        if self.max_positions < 1:
            raise ValueError("max_positions must be >= 1")
        if not 0 < self.max_exposure_percent <= 1.0:
            raise ValueError(
                f"max_exposure_percent must be 0-100%, got {self.max_exposure_percent:.1%}"
            )
```

- Runtime import service module OK: service KHÔNG runtime-import value_objects (TYPE_CHECKING) → không vòng. `position_calculation.py` là leaf.
- `__post_init__` bound `0.10` literal GIỮ (validation cap "max 10% risk/lệnh", semantic khác `MAX_EXPOSURE_PERCENT`).

### 4. `enums.py` (bỏ dead members)

```python
from enum import Enum


class RiskModel(Enum):
    PERCENT_RISK = "percent_risk"  # % vốn cố định mỗi lệnh (model duy nhất)
```

### 5. `risk/__init__.py` + `risk/services/__init__.py`

- `services/__init__.py`: import + `__all__ = ["PositionCalculatorDomainService"]`.
- `risk/__init__.py`:
  ```python
  from pocketquant.core.domain.risk.enums import RiskModel
  from pocketquant.core.domain.risk.position_calculation import PositionCalculation
  from pocketquant.core.domain.risk.services.position_calculator_domain_service import (
      PositionCalculatorDomainService,
  )
  from pocketquant.core.domain.risk.value_objects import RiskConfig

  __all__ = ["PositionCalculatorDomainService", "PositionCalculation", "RiskConfig", "RiskModel"]
  ```
  Thứ tự: enums → position_calculation → service → value_objects (service load trước value_objects, không vòng).

### 6. `risk_check.py` (import consts, config optional)

- Import: `from pocketquant.core.domain.risk import PositionCalculatorDomainService` (giữ `RiskConfig`).
- Đổi `validate`/`_check_exposure`/`calculate_max_size`/`get_risk_summary`: `config: RiskConfig | None = None`.
- Resolve đầu method:
  ```python
  _pc = PositionCalculatorDomainService
  max_exposure = config.max_exposure_percent if config else _pc.MAX_EXPOSURE_PERCENT
  ```
  Tương tự `risk_per_trade` (`_pc.RISK_PER_TRADE`), `max_positions` (`config.max_positions if config else 3`).
- Thay mọi `config.max_exposure_percent`/`config.risk_per_trade` bằng biến resolved. Logic so sánh giữ nguyên.

### 7. `strategy_app_service.py` (call site)

- Line 22 import: `PositionSizerDomainService` → `PositionCalculatorDomainService`.
- Line ~361:
  ```python
  calc = PositionCalculatorDomainService.calculate(
      balance.available_balance, current_price, stop_loss, strategy.config.risk,
  )
  size = calc.size
  ```
  Giữ `if size <= 0: … return`. Không truyền `commission_model` (None → est 0.0; port không expose model).

## Compile + import smoke (chạy ngay sau sửa)

```bash
uv run python -c "import pocketquant.core.domain.risk; import pocketquant.engine.execution.risk_check; import pocketquant.engine.strategy.strategy_app_service; print('ok')"
uv run ruff check src/pocketquant/core/domain/risk src/pocketquant/engine/execution/risk_check.py src/pocketquant/engine/strategy/strategy_app_service.py
```

## Todo

- [x] Tạo `position_calculation.py`
- [x] `git mv` file service + rewrite (consts, `calculate()`, xoá KELLY/FIXED/validate_size)
- [x] RiskConfig defaults ← consts
- [x] enums bỏ KELLY/FIXED
- [x] 2 `__init__.py` exports
- [x] risk_check.py consts + config optional
- [x] strategy_app_service.py call site
- [x] import smoke + ruff xanh

## Success criteria

- Import smoke OK (no circular). ruff sạch trên file đã sửa.
- `git grep 'PositionSizerDomainService\|calculate_size\|validate_size\|_kelly_size\|_fixed_size\|RiskModel.KELLY\|RiskModel.FIXED'` trong `src/` = rỗng.
- `calculate()` trả `PositionCalculation` 4 field; consts là 1 source cho default.

## Next

→ phase-02 (tests + validation parity).
