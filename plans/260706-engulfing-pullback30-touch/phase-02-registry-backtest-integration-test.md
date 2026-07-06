---
phase: 2
title: "Registry + backtest integration test"
status: completed
priority: P1
dependencies: [1]
---

# Phase 2: Registry + backtest integration test

## Overview

Đăng ký variant vào `STRATEGY_REGISTRY` và khoá hành vi end-to-end qua `BacktestAppService` (real strategy + PaperBrokerAdapter + wiring, chỉ persistence fake). Mirror `tests/backtest_test/engine/test_engulfing_backtest.py`.

## Requirements

- Functional: `STRATEGY_REGISTRY["engulfing_pullback30_touch"]` resolve tới class mới.
- Functional: backtest với bar sequence có pullback → mở lệnh tại close(N+1); sequence không pullback → 0 trade.
- Non-functional: giữ import contract; không đổi bản gốc registry entry `engulfing`.

## Architecture

Dòng chảy: `on_bar_completed` phát signal tại bar N+1 → `StrategyAppService._process_signal` → market order fill tại `current_price` = close(N+1) → `PaperBrokerAdapter` SL/TP auto-fill round-trip. Cùng cơ chế bản gốc, chỉ khác thời điểm phát signal.

Fixture cần **3 loại bar chuỗi** cho 1 cycle LONG:
1. red prev, 2. green engulfing (arm, KHÔNG vào), 3. **pullback bar** (`low ≤ level`, `low > SL`, close hợp lệ) → vào tại close(3), 4. spike clears TP → round-trip, rồi flat fillers roll key-level.

Đối chứng: fixture "engulfing nhưng bar kế tiếp không pullback" → 0 trade (khác bản gốc vốn vào ngay).

## Related Code Files

- Modify: `src/pocketquant/core/domain/strategy/services/__init__.py` — thêm import + entry `"engulfing_pullback30_touch": EngulfingPullback30TouchStrategyService` + `__all__`.
- Create: `tests/backtest_test/engine/test_engulfing_pullback30_touch_backtest.py`
- Read (mirror): `tests/backtest_test/engine/test_engulfing_backtest.py`

## Implementation Steps

1. **RED** — Viết `test_engulfing_pullback30_touch_backtest.py`:
   - `test_registered_in_strategy_registry` — `"engulfing_pullback30_touch" in STRATEGY_REGISTRY`.
   - `test_pullback_cycle_opens_and_round_trips` — build bars có pullback bar giữa engulfing và spike; assert `status=="finished"`, `total_trades >= 1`, positions rỗng cuối run, cash == initial + Σrealized (re-derive như test gốc).
   - `test_no_pullback_no_trade` — engulfing nhưng bar kế tiếp không chạm level → `total_trades == 0`.
   - Reuse `_run_backtest` helper (copy, đổi `STRATEGY_REGISTRY[...]` + `strategy_code`, thêm param `pullback_pct`).
   - Chạy → đỏ (chưa có registry entry).
2. **GREEN** — Thêm entry vào `services/__init__.py`.
3. Chạy lại tới xanh; tinh chỉnh fixture OHLC nếu cần (dùng lại tính tay level/SL từ Phase 1).

## Success Criteria

- [ ] `engulfing_pullback30_touch` trong `STRATEGY_REGISTRY`, `__all__` cập nhật.
- [ ] Backtest cycle có pullback → `finished`, ≥1 trade, positions rỗng, cash khớp Σrealized.
- [ ] Sequence không pullback → 0 trade.
- [ ] Entry `engulfing` cũ giữ nguyên; test backtest gốc vẫn xanh.

## Risk Assessment

- **Fixture same-bar fill:** market entry fill tại close(N+1) qua engine — không dùng LIMIT nên không dính vụ pending fill trên bar submit. An toàn.
- **Key-level roll:** thiếu flat fillers giữa cycle làm spike high kẹt trong window → entry sau lệch TP. Mitigation: giữ ≥ `lookback+1` filler như test gốc.
- **Import contract:** class ở core/domain, chỉ stdlib+core import → không phá import-linter.
