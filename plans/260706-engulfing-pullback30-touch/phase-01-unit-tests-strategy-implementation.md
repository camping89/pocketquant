---
phase: 1
title: "Unit tests + strategy implementation"
status: completed
priority: P1
dependencies: []
---

# Phase 1: Unit tests + strategy implementation

## Overview

TDD core: viết unit test khoá từng nhánh state machine (RED), rồi implement `EngulfingPullback30TouchStrategyService` tới GREEN. Direct `on_bar_completed` calls (không qua bus), mirror `tests/core_test/unit/domain/strategy/test_engulfing.py`.

## Requirements

- Functional: state machine 2-bar — arm tại bar engulfing đạt filter, resolve tại bar kế tiếp (enter-on-touch / discard / SL-guard).
- Functional: signal khi enter mang `entry_price = close(N+1)`, `entry_logic = "engulfing_pullback30_touch:bullish|bearish"`, SL/TP neo pattern.
- Non-functional: dùng lại pure `detect_engulfing`; không sửa bản gốc; core import contract (stdlib + core only).

## Architecture

State trên instance (ngoài `_open_direction` position-cap kế thừa ý tưởng gốc):

```
_armed: dict | None   # {direction, open_n, close_n, level, sl, key_level_extreme} hoặc None
```

Luồng `on_bar_completed(bar)`:
1. Snapshot key-level window BEFORE append (như gốc), append high/low.
2. Warmup guard (`len(key_highs) < key_level_lookback_bars`) → set `_prev_bar`, return None.
3. **Nếu `_armed` is not None** (đang chờ bar kế tiếp — đây LÀ bar N+1):
   - LONG: `touched = low ≤ _armed.level`; `sl_hit = low ≤ _armed.sl`.
   - SHORT: `touched = high ≥ _armed.level`; `sl_hit = high ≥ _armed.sl`.
   - `entry = close(bar N+1)`; risk-valid: LONG `entry > sl`, SHORT `entry < sl`.
   - Nếu `touched and not sl_hit and risk_valid` → build signal (SL/TP từ `_armed`), `_armed=None`, set `_prev_bar=bar`, return signal.
   - Ngược lại → `_armed=None` (huỷ, chỉ 1 bar), set `_prev_bar=bar`, return None. **Không** re-detect engulfing trên bar này (bar N+1 dùng để resolve, không đồng thời arm mới).
4. Position-cap: nếu `_open_direction is not None` → `_prev_bar=bar`, return None.
5. `_prev_bar is None` → set, return None.
6. `detect_engulfing(prev, bar)`; nếu bullish+direction+wick-filter (hoặc bearish mirror) đạt → **arm** (tính `level`, `sl`, `key_level_extreme` từ pattern & window hiện tại), `_prev_bar=bar`, return None (KHÔNG phát signal).
7. `_prev_bar=bar`, return None.

`on_order_filled`: y hệt gốc (set open-direction trên entry fill, clear trên opposite-side close).

Arm payload tính tại bar N (bullish LONG):
- `level = close_n − pullback_pct×(close_n − open_n)`
- `pattern_low = min(low_n, low_prev)`; `sl = pattern_low×(1 − sl_buffer_pct)`
- `key_high = max(key_highs)`  (snapshot tại bar N, trước append)
- TP tính lúc enter: `tp = max(entry + (entry − sl), key_high)` với `entry = close(N+1)`.
SHORT mirror.

Params: `direction`, `sl_buffer_pct`, `key_level_lookback_bars`, `max_rejection_wick_pct` (validate y hệt gốc) + `pullback_pct` (default 0.30, validate `0 < pullback_pct < 1`).

## Related Code Files

- Create: `src/pocketquant/core/domain/strategy/services/engulfing_pullback30_touch_strategy_service.py`
- Create: `tests/core_test/unit/domain/strategy/test_engulfing_pullback30_touch.py` (cạnh `test_engulfing.py`)
- Read (mirror, không sửa): `src/pocketquant/core/domain/strategy/services/engulfing_strategy_service.py`, `tests/core_test/unit/domain/strategy/test_engulfing.py`

## Implementation Steps

1. **RED** — Viết `test_engulfing_pullback30_touch.py`, mirror helper `_bar`/`_strategy`/`_warm_to_pattern_long` từ test gốc. Ca test tối thiểu:
   - `test_engulfing_bar_does_not_emit_signal` — bar engulfing đạt filter → return None (armed).
   - `test_next_bar_touch_emits_long_at_next_close` — bar N+1 có `low ≤ level` → signal LONG, `entry_price == close(N+1)`, `entry_logic == "engulfing_pullback30_touch:bullish"`.
   - `test_next_bar_no_touch_discards_setup` — bar N+1 `low > level` → None; bar sau đó (không phải engulfing) cũng None; xác nhận `_armed is None`.
   - `test_next_bar_touches_sl_skips_entry` — bar N+1 `low ≤ sl` → None (dù chạm level).
   - `test_long_sl_uses_pattern_low_minus_buffer` + `test_long_tp_rr_vs_key_level` — SL/TP đúng công thức, entry = close(N+1).
   - `test_short_mirror_touch_high` — bearish: arm rồi `high(N+1) ≥ level` → SHORT.
   - `test_direction_filter_long_only_ignores_bearish` / `short_only`.
   - `test_pullback_pct_param_shifts_level` — đổi `pullback_pct=0.5` dịch mức trigger.
   - `test_position_cap_blocks_until_close` — sau entry fill, engulfing mới bị chặn tới opposite fill.
   - `test_invalid_params_raise` — parametrize gồm `pullback_pct` 0.0 / 1.0 / -0.1 + các case gốc.
   - Chạy → đỏ (module chưa tồn tại).
2. **GREEN** — Tạo `engulfing_pullback30_touch_strategy_service.py` theo Architecture. Docstring mô tả AS-IS ngắn gọn (chính sách comment: chỉ giải thích chỗ khó/hack).
3. Chạy lại file test tới xanh; chỉnh fixture OHLC nếu số học lệch (giữ ý nghĩa từng nhánh).

## Success Criteria

- [ ] `test_engulfing_pullback30_touch.py` xanh toàn bộ.
- [ ] Bar engulfing không phát signal; bar N+1 touch (không thủng SL) phát signal với entry=close(N+1).
- [ ] No-touch và SL-touch đều không vào; setup reset sau đúng 1 bar.
- [ ] Invalid `pullback_pct` raise `ValueError`.
- [ ] Không sửa file bản gốc `engulfing_strategy_service.py`.

## Risk Assessment

- **Same-bar arm+resolve nhầm:** nếu re-detect engulfing ngay trên bar N+1 sẽ sai semantics "chờ đúng bar kế tiếp". Mitigation: nhánh armed return sớm, không rơi xuống detect (bước 3 trước bước 6).
- **Fixture số học:** OHLC craft cho touch/SL-hit dễ lệch. Mitigation: tính tay `level`/`sl` trong test, assert bằng `pytest.approx`.
- **Warmup + arm tương tác:** arm chỉ sau khi qua warmup guard (giống gốc) để key-level hợp lệ.
