# Phase 01 — CommissionModel + OrderResult.commission

**Priority:** P2 · **Status:** completed · **Depends:** — · **Blocks:** P02, P04

## Overview

Foundation không đổi behavior: tạo abstraction commission (pure, `core.domain.trading`) + thêm field `commission` vào `OrderResult`. Sau phase này code compile, chưa ai tính commission → tất cả `= 0.0` (backward compat).

## Requirements

- `CommissionModel` (Protocol) + `PercentageCommissionModel(bps)` ở `core.domain.trading`.
- Export cả hai qua `core/domain/trading/__init__.py`.
- `OrderResult.commission: float = 0.0`.
- Placement `trading` (KHÔNG `brokers`): R6 `PositionCalculator` (position domain) sẽ dùng chung → tránh coupling position→brokers.

## Related code files

- **NEW** `src/pocketquant/core/domain/trading/commission_model.py`
- **MODIFY** `src/pocketquant/core/domain/trading/__init__.py` (export)
- **MODIFY** `src/pocketquant/core/domain/brokers/value_objects.py` (`OrderResult.commission`)

## Implementation steps

1. Tạo `commission_model.py`:
   ```python
   from typing import Protocol


   class CommissionModel(Protocol):
       def compute(self, price: float, quantity: float) -> float: ...


   class PercentageCommissionModel:
       def __init__(self, bps: float) -> None:
           self._bps = bps

       def compute(self, price: float, quantity: float) -> float:
           return abs(price * quantity) * self._bps / 10_000
   ```
   - Protocol structural (không ABC — pure strategy object, không shared behavior).
   - `abs()` phòng qty/price âm → cost luôn ≥ 0.
   - Không comment thừa (code tự rõ); chỉ comment nếu cần rationale magic-number (10_000 = bps→fraction, hiển nhiên → bỏ).

2. Export ở `core/domain/trading/__init__.py`: thêm `CommissionModel`, `PercentageCommissionModel` vào import + `__all__` (theo pattern hiện có của package).

3. Thêm field vào `OrderResult` (`value_objects.py`) — đặt cạnh `side`, giữ dataclass order (field có default, không phá positional):
   ```python
   commission: float = 0.0  # cost per fill (paper: computed; OKX: abs(venue fee)); 0 for non-fills
   ```

## Todo

- [x] `commission_model.py` — Protocol + PercentageCommissionModel
- [x] Export ở `trading/__init__.py`
- [x] `OrderResult.commission: float = 0.0`
- [x] `python -c "import pocketquant"` / compile check sạch
- [x] `lint-imports` vẫn 8/8 (không contract mới)

## Success criteria

- `from pocketquant.core.domain.trading import CommissionModel, PercentageCommissionModel` chạy.
- `PercentageCommissionModel(bps=4).compute(100.10, 10) == pytest.approx(0.40040)`.
- `PercentageCommissionModel(bps=0).compute(x, y) == 0.0` (seam test zero-commission).
- `OrderResult(...).commission == 0.0` khi không set.
- `pyright` + `ruff` + `lint-imports` pass.

## Risks

- Thêm field default vào dataclass giữa các field khác — đảm bảo nằm sau field có default cuối (`side`) để không lỗi "non-default after default". `side` đã có default `None` → thêm sau OK.
