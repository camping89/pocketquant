# Code Review — R6 PositionSizer → PositionCalculator refactor

Date: 2026-07-06 · Reviewer: code-reviewer · Scope: R6 logic-only rename/rewrite (parity-critical)

## Verdict

**CLEAN.** Không tìm thấy bug thật (Critical/High/Medium = 0). Parity verified empirically, circular-import safe, consts centralization đúng, duck-typing khớp signature. Chỉ vài Low-severity notes mang tính DRY/YAGNI/observational — không blocking.

## Scope

- Files: `core/domain/risk/{position_calculation.py(new), enums.py, value_objects.py, __init__.py, services/{__init__.py, position_calculator_domain_service.py}}`, `engine/execution/risk_check.py`, `engine/strategy/strategy_app_service.py`, `tests/core_test/unit/domain/strategy/test_engulfing.py`
- LOC diff: +88 / -133 (net simplification, xoá kelly/fixed/validate_size)
- Independent checks run: ruff (green), leftover-symbol grep (empty), import smoke, parity smoke, persistence-rehydration trace

## Verified (bằng chứng, không chỉ đọc diff)

- **Parity byte-identical**: chạy `calculate()` cho các nhánh — `config` vs `None` cho size hệt nhau (10.0); no-SL (price_risk=entry*0.01); `price_risk==0` → `PositionCalculation(0,0,0,0)`; guards `balance<=0`/`entry<=0` → zero; commission `PercentageCommissionModel(10)` → est khớp `abs(price*size)*bps/1e4`. `size = min(risk_amount/price_risk, cap)` trùng `min(size, max_size)` cũ. Guard `account_balance<=0 or entry_price<=0` giữ nguyên semantics của 2 guard tách rời cũ.
- **No circular import**: runtime chain `value_objects → service → position_calculation(leaf)`. Service chỉ import `RiskConfig`/`CommissionModel` dưới `TYPE_CHECKING` + `from __future__ import annotations`. Test cả 2 entry point (qua `risk/__init__` và import trực tiếp `value_objects`) — không vòng. `RiskConfig` defaults resolve `PositionCalculatorDomainService.RISK_PER_TRADE=0.02`, `MAX_EXPOSURE_PERCENT=0.10` OK.
- **Duck-typing**: Protocol `compute(self, price, quantity)`; call `commission_model.compute(entry_price, size)` map positional đúng (price←entry_price, quantity←size). Live call site truyền `commission_model=None` → est=0.0.
- **Consts 1-source** (cho 3 giá trị trong scope): `risk_per_trade`/`max_exposure_percent`/`default_sl` đều tham chiếu class consts ở cả RiskConfig defaults lẫn risk_check fallback. Đúng.
- **No leftover**: grep `PositionSizerDomainService|calculate_size|RiskModel.KELLY|RiskModel.FIXED|_kelly_size|_fixed_size|validate_size` trong src/tests = rỗng.
- **fastapi containment**: core/engine không import fastapi (không đổi).
- **ruff**: All checks passed trên toàn bộ file R6.

## Critical / High / Medium

Không có.

## Low (non-blocking, observational)

### L1 — `max_positions` fallback literal `3` không centralize (risk_check.py:135)
`max_positions = config.max_positions if config else 3`. Literal `3` trùng default `RiskConfig.max_positions: int = 3` (value_objects.py:13). Refactor này đã đưa risk_per_trade/max_exposure/default_sl thành class-const 1-source nhưng bỏ sót max_positions → còn 2 nơi giữ magic `3`. Nhất quán hơn nếu thêm `DEFAULT_MAX_POSITIONS` const. Impact thấp (giá trị trùng nhau nên không gây sai lệch runtime), chỉ là DRY gap so với chính mục tiêu refactor.

### L2 — Dead `StrategyConfig.from_dict` giữ literal 0.02/0.10 + `RiskModel(risk_model)` (strategy/value_objects.py:94-100)
Đúng như plan flag (known trade-off). Xác nhận thêm bằng trace persistence: **không có** caller của `.from_dict` trong src/tests, và **không** có rehydration path nào khác gọi `RiskModel(<string>)` (không có strategy repo/from_mongo trong `core/infra` dựng RiskConfig từ model string). ⇒ việc bỏ enum `kelly`/`fixed` KHÔNG thể vỡ production qua config đã lưu (nhánh raise `ValueError("kelly")` không reachable). Ghi nhận là dead-code trade-off, không phải bug. Nếu sau này from_dict được nối lại làm entry deserialize config-đã-lưu, cần graceful fallback cho legacy model string trước khi tin cậy.

### L3 — API mở rộng chưa có consumer (YAGNI, cố ý)
`PositionCalculation.{notional, risk_amount, est_entry_commission}` và tham số `commission_model` được tính/plumb đầy đủ nhưng caller live duy nhất (strategy_app_service.py:361 `calc.size`) chỉ dùng `.size`. Forward-looking cho backtest R-series — deliberate, chấp nhận được. Note để tránh bit-rot: nếu R7/R8 không tiêu thụ các field này, cân nhắc thu hẹp VO.

### L4 — `calculate_max_size` + `get_risk_summary` không có caller (risk_check.py:84,111)
Refactor thêm nhánh `config | None` fallback vào 2 method vốn không có caller nào trong src/tests (chỉ `validate` được gọi tại strategy_app_service.py:341, luôn truyền `strategy.config.risk`). Deadness là pre-existing, không do R6 tạo ra; R6 chỉ mở rộng chữ ký. Không hại, nhưng fallback logic ở đây là speculative.

### L5 — `RiskModel` còn 1 member; `RiskConfig.model` vestigial
Sau khi bỏ KELLY/FIXED, `RiskModel` chỉ còn `PERCENT_RISK`; calculator không còn branch theo `model`; field `RiskConfig.model` không ảnh hưởng kết quả. Giữ lại là lựa chọn backward-compat hợp lý (tránh vỡ API/serialize). Harmless.

## Positive

- Refactor giảm bề mặt đáng kể: xoá kelly/fixed/validate_size + branch dispatch, gộp về 1 hàm `calculate()` thuần — dễ đọc, ít nhánh chết.
- `PositionCalculation` frozen VO là leaf sạch (zero dep) → nền tảng đúng cho việc phá vòng import.
- Comment tuân thủ policy: các comment còn lại (`RISK_PER_TRADE = 0.02  # ...`, `cap gần như luôn thắng`) là magic-number rationale — đúng ngoại lệ được cho phép, không restate/name-echo.
- Fallback `config=None` behavior-equivalent với `RiskConfig()` (verified: size bằng nhau) → widening chữ ký an toàn, backward-compatible cho mọi caller đang truyền config.

## Metrics

- Tests: 560/560 pass (báo cáo từ tester, không chạy lại)
- ruff (R6 files): 0 issue
- Leftover old-symbol refs: 0
- Parity smoke (6 cases): pass

## Unresolved questions

- L3/L4: R7/R8 có thực sự tiêu thụ `notional`/`risk_amount`/`est_entry_commission` và `commission_model` (qua backtest sandbox) không? Nếu không, các mở rộng này thành dead surface. Ngoài scope R6 — chỉ cần confirm ở roadmap.
