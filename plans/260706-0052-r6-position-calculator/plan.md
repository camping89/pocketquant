---
title: "R6 — PositionCalculatorDomainService + PositionCalculation VO"
description: "Rename PositionSizerDomainService→PositionCalculatorDomainService; calculate() trả PositionCalculation{size,notional,risk_amount,est_entry_commission}; risk params thành class consts (1 source, RiskConfig defaults tham chiếu); xoá KELLY/FIXED + validate_size dead code; RiskCheckHandler import consts (config optional). Giữ RiskConfig override (tests dùng). Kế thừa Model E §5/§9."
status: completed
priority: P2
branch: develop
tags: [trading-calc, risk, domain-service, rename, position-sizing, dead-code]
blockedBy: []
blocks: []
created: "2026-07-06T00:52:00+07:00"
createdBy: "ck:plan"
source: "plans/trading-calulation-fix/roadmap.md (R6) + design-execution-metrics-separation.md §5/§9"
---

# R6 — PositionCalculatorDomainService + PositionCalculation VO

Đổi tên `PositionSizerDomainService`→`PositionCalculatorDomainService`; `calculate_size()` (trả `float`) → `calculate()` (trả VO `PositionCalculation{size, notional, risk_amount, est_entry_commission}`). Risk params (`0.02`/`0.10`/`0.01`) thành **class consts có giải thích** = 1 nguồn (RiskConfig defaults tham chiếu). Xoá dead code `KELLY`/`FIXED` + `validate_size`. `RiskCheckHandler` import consts. Logic-only, R1+R3 done.

## Context

- Roadmap hàng R6: `plans/trading-calulation-fix/roadmap.md` · Model E §5 (consts) + §9 (decision 9): `plans/trading-calulation-fix/design-execution-metrics-separation.md`
- Depends: R1 (`core.domain.risk` ổn định) + R3 (`CommissionModel` ở `core.domain.trading` cho `est_entry_commission`). Cả hai done.
- Roadmap unresolved R6: *"có strategy nào override `risk_per_trade`/`max_exposure_percent` per-strategy? Nếu có → const thuần phá; giữ optional override."*

## Findings (đã kiểm tra codebase)

- **4 site dựng `StrategyConfig` runtime** (`main_extensions`, `strategy_reconcile`, `backtest_dispatch`, `backtest_strategy_loader`) **KHÔNG** truyền `risk=` → `RiskConfig()` mặc định. API backtest payload không đọc risk param. `StrategyConfig.from_dict` (YAML reader) **dead** (không caller).
- **NHƯNG tests override thật**: `test_engulfing_backtest.py:208` + `test_hitnrun2_backtest.py:250/266/334/349` truyền `RiskConfig(max_exposure_percent=…)` để parameterize sizing. Roadmap invariant cấm đổi số characterization.
- → **Kết luận: giữ `RiskConfig` optional override** (pure-const sẽ phá tests). Consts là nguồn **default**, không thay thế param.
- `validate_size`: **dead** (chỉ definition, 0 caller) → xoá.
- Call site sizing duy nhất trong hot path: `strategy_app_service.py:361`. Unit test trực tiếp: `test_engulfing.py:232`.

## Quyết định khoá (chốt với user)

- **D1 — Giữ optional `RiskConfig` override; consts = nguồn default.** `calculate()` + `RiskCheckHandler` vẫn nhận `RiskConfig` (override giữ nguyên → tests không đổi số). 3 consts trong class là nguồn DUY NHẤT của default values; `RiskConfig` field defaults tham chiếu consts. *(User chọn — không pure-const.)*
- **D2 — `est_entry_commission` = optional param, default `0.0`.** `calculate()` nhận `commission_model: CommissionModel | None = None`; `None` → `0.0`. Call site live truyền `None` (R6 logic-only; `IBrokerPort` không expose CommissionModel — không đụng broker port). *(User chọn — không scope creep sang port.)*
- **D3 — `PositionCalculation` VO ở file riêng** `core/domain/risk/position_calculation.py` (frozen, no deps) để tránh **runtime circular import**: service trả VO này; nếu VO ở `value_objects.py` mà `value_objects` lại import consts từ service → vòng lặp. Tách file cắt vòng.
- **D4 — Consts PUBLIC class attrs** (`RISK_PER_TRADE`/`MAX_EXPOSURE_PERCENT`/`DEFAULT_SL_RISK_PERCENT`), không `_`-prefix như design nháp: RiskConfig + RiskCheckHandler import cross-module → import tên `_private` xuyên module là smell. Service import `RiskConfig`/`CommissionModel` chỉ dưới `TYPE_CHECKING` (đọc qua attribute/Protocol lúc runtime) → cắt vòng với value_objects.
- **D5 — Xoá `KELLY`/`FIXED` enum + branches + `validate_size`.** Giữ `RiskModel.PERCENT_RISK` + `RiskConfig.model` (config compat, `from_dict`). `calculate()` bỏ dispatch theo model (chỉ còn 1 model) → luôn percent-risk. Logic percent-risk **byte-identical** cũ → số không đổi.
- **D6 — `RiskCheckHandler` config → `RiskConfig | None = None`, fallback consts.** Import consts, resolve `max_exposure`/`risk_per_trade`/`max_positions` từ consts khi `config is None`. Live call site + tests luôn truyền config (override) → nhánh fallback là nguồn 1-source cho forward path không dựng RiskConfig. Fulfill "RiskCheckHandler import consts".

## Phases

| # | Phase | Status | Depends |
|---|---|---|---|
| 01 | [Rename service + PositionCalculation VO + consts + kill dead code + wire](phase-01-rename-vo-consts-wire.md) | done | — |
| 02 | [Test updates + full validation parity](phase-02-test-validation.md) | done | 01 |
| 03 | [Docs sync + roadmap R6 done + journal](phase-03-docs-roadmap-journal.md) | done | 02 |

## Invariants (mọi phase giữ)

- **Parity**: engulfing/hitnrun2 characterization tests pass **KHÔNG sửa số** (total_trades/gross PnL/net/equity/Sharpe…). Bằng chứng logic percent-risk không đổi. `calculate().size` == `calculate_size()` cũ với cùng input.
- **1 source consts**: `git grep` không còn literal `0.02`/`0.10`/`0.01` rời rạc cho risk default ngoài 3 consts (RiskConfig defaults + RiskCheckHandler + sizer đều tham chiếu). *(bound validation `__post_init__` literal giữ — semantic khác.)*
- **Override giữ**: `StrategyConfig(risk=RiskConfig(max_exposure_percent=…))` vẫn tác động sizing y hệt.
- **import-linter 8 contract xanh**: risk→trading chỉ `TYPE_CHECKING`; engine.execution→core.domain.risk hợp lệ. No fastapi/bson. Không circular import (verify `python -c "import pocketquant.core.domain.risk"`).
- `git grep 'PositionSizerDomainService\|calculate_size\|validate_size\|RiskModel.KELLY\|RiskModel.FIXED\|position_sizer_domain_service'` sạch (chỉ còn journal lịch sử).

## Validation cuối

`just test` (parity number không đổi) · `uv run ruff check .` · `uv run pyright` · `uv run lint-imports` (8) — tất cả xanh. `python -c "import pocketquant.core.domain.risk; import pocketquant.engine.execution.risk_check"` OK (no circular).

## Key risks

- **Circular import** (D3): mitigations = VO file riêng + `TYPE_CHECKING` cho RiskConfig/CommissionModel trong service. Verify bằng import smoke-test trong phase-01 ngay sau sửa.
- **Parity drift**: `calculate()` phải giữ đúng `min(risk_amount/price_risk, cap)`. Không refactor công thức. Test characterization là glate; phase-02 chạy đầy đủ.
- **`from_dict` dead nhưng còn `RiskModel(risk_model)`**: nếu ai truyền `"kelly"`/`"fixed"` YAML sẽ raise (enum bỏ member). Chấp nhận — config dead, không caller.
