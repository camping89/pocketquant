---
phase: 2
title: "EngulfingStrategy + backtest"
status: completed
priority: P1
dependencies: [1]
---

# Phase 2: EngulfingStrategy + backtest

## Overview

`EngulfingStrategy(IStrategy)` dùng detector Phase 1: entry pattern strong (pass quality filter), SL dưới pattern extreme + buffer, một TP = `max(RR 1:1, swing key-level)`. Register vào `STRATEGY_REGISTRY`. Implement theo hook MỚI (sau 260628-1514).

## Requirements

- Functional: `on_bar_completed(bar) -> Signal | None`; emit Signal khi engulfing strong + position cap còn trống.
- Functional: `on_order_filled(order, fill_price) -> None` reset `_open_direction` khi opposite-side fill (giống `hitnrun2`).
- Functional: SL/TP theo công thức plan; quality filter `max_rejection_wick_pct`; `direction` long|short|both.
- Non-functional: zero new deps; strategy trong `core/domain/strategy/services/`; tái dùng `detect_engulfing` (DRY — KHÔNG copy logic).

## Architecture

**HARD BLOCK:** chờ `260628-1514` **commit/merge** (không phải dirty-tree — xem plan.md). Hook contract (verified working tree `interfaces.py:51,76`):
- `async def on_bar_completed(self, bar: dict) -> Signal | None`
- `async def on_order_filled(self, order: FilledOrder, fill_price: float) -> None` — param là **`FilledOrder` Protocol** (`interfaces.py:8`), KHÔNG phải `OrderAggregate`. Chỉ đọc `order.side` nên không cần import `OrderAggregate`.

**State:** `_open_direction: Direction | None`, `_prev_bar: dict | None`, `_highs/_lows: deque(maxlen=key_level_lookback_bars)`.

**on_bar_completed flow:**
```
1. snapshot key_window = list(self._highs)/list(self._lows) TRƯỚC khi append
   → đây là N bar STRICTLY TRƯỚC bar hiện tại (loại cả bar hiện tại lẫn _prev_bar pattern? xem ghi chú off-by-one)
2. append high/low của bar hiện tại vào deque
3. warmup: len(key_window) < key_level_lookback_bars → _prev_bar = bar; return None
4. position cap: _open_direction is not None → _prev_bar = bar; return None
5. nếu _prev_bar None → _prev_bar = bar; return None
6. res = detect_engulfing(_prev_bar, bar)
7. LONG nếu res.is_bullish và direction in (long,both) và res.rejection_wick_pct <= max_rejection_wick_pct:
     entry=close; pattern_low=min(bar.low, _prev_bar.low); SL=pattern_low*(1-sl_buffer_pct)
     risk=entry-SL; tp_rr=entry+risk; key=max(key_window); TP=max(tp_rr, key)
     signal = _mk_signal(LONG, ...)   # KHÔNG set _open_direction ở đây
8. SHORT mirror (key=min(key_window); TP=min(tp_rr,key))
9. cuối hàm: _prev_bar = bar (LUÔN cập nhật, mọi nhánh)
```

> **Off-by-one (red-team Finding 8 — PIN):** `key_window` là N bar **strictly trước bar hiện tại**. `max()/min()` KHÔNG được gồm high/low của bar pattern hiện tại (snapshot trước khi append ở step 1 đảm bảo điều này). Test phải assert: high của bar hiện tại KHÔNG nằm trong key-level set. `maxlen=key_level_lookback_bars` (không +1) vì snapshot trước append.

> **`_open_direction` set sau fill (red-team Finding 6 — đổi so với hitnrun2):** KHÔNG set `_open_direction` lạc quan trong `on_bar_completed` (hitnrun2 làm vậy → wedge khi order bị REJECT/size=0, vì `_process_signal` reject nhưng `_open_direction` đã LONG → kẹt vĩnh viễn). Thay vào: set `_open_direction` trong `on_order_filled` khi **entry-side fill** xác nhận (BUY→LONG, SELL→SHORT mở mới), reset khi **opposite-side fill** đóng. Cần phân biệt entry-fill vs exit-fill: dùng `_open_direction is None` (đang flat → fill này là entry) vs not-None (đang có vị thế → opposite-side fill là exit).

**Signal:** `subscription_id=self.id`, `entry_logic=f"engulfing:{bullish|bearish}"`, `confidence` cố định (vd 0.7). Dùng `Signal` hiện có (1 TP) — KHÔNG đụng value_objects.

**on_order_filled(order: FilledOrder, fill_price):** đọc `side = order.side`. Nếu `_open_direction is None`: fill này là **entry** → set `_open_direction = LONG nếu side==BUY else SHORT`. Nếu `_open_direction` not-None và side là opposite (LONG+SELL / SHORT+BUY): **exit** → `_open_direction = None`.

## Related Code Files

- Create: `src/pocketquant/core/domain/strategy/services/engulfing.py` — `EngulfingStrategy(IStrategy)`.
- Modify: `src/pocketquant/core/domain/strategy/services/__init__.py` — import + `"engulfing": EngulfingStrategy` vào `STRATEGY_REGISTRY` + `__all__`.
- Create: `tests/core_test/unit/domain/strategy/test_engulfing.py` — unit (entry long/short, filter pass/fail, TP=max(rr,key), SL buffer, position cap, on_order_filled reset, direction long-only/short-only). Tái dùng helper `_bar`/`_strategy` style của `test_hitnrun2.py`.
- Create: `tests/backtest_test/engine/test_engulfing_backtest.py` — integration full stack (synthetic bars → trades → metrics), mô phỏng theo `test_hitnrun2_backtest.py`.
- Reference (KHÔNG sửa): `core/domain/strategy/value_objects.py` (Signal 1 TP), `paper_broker.py` (auto-fill).

## Implementation Steps

1. **Gate (red-team Finding 1):** verify `260628-1514` đã **commit/merge**, KHÔNG chỉ dirty-tree: `git log --oneline -- src/pocketquant/core/domain/strategy/interfaces.py` phải có commit rename (HEAD hiện vẫn `on_bar`/`on_fill` ở :42,:67 — chưa commit); + plan đó `status: completed`; + `git status` sạch cho các file đó. Nếu còn dirty/pending → DỪNG.
2. **Verify entry-fill publish (red-team Finding 6 dependency):** xác nhận entry MARKET fill (không chỉ synthetic exit) publish `OrderFilledEvent` mang `subscription_id` → nếu KHÔNG, set-after-fill cho entry không chạy, position cap vỡ. Trace `order_app_service.on_order_update`/`submit` → publish. Nếu entry không publish → fallback optimistic-set với rollback khi reject (ghi rõ).
3. Viết `EngulfingStrategy.__init__` đọc 4 param từ `config.parameters` với `_DEFAULTS`; validate **TẤT CẢ** (red-team Finding 9): `direction in {long,short,both}`, `0 < max_rejection_wick_pct <= 1.0`, `key_level_lookback_bars >= 1`, `sl_buffer_pct >= 0` — raise `ValueError` sớm (trước event loop nuốt exception). Init state/deques.
4. `on_start` clear state. Implement `on_bar_completed` theo flow (KHÔNG set `_open_direction` ở đây). Implement `on_order_filled` set/reset theo entry-vs-exit.
5. `_mk_signal` helper trả Signal với entry/SL/TP/entry_logic. Import `FilledOrder` từ `interfaces`, KHÔNG import `OrderAggregate`.
6. Register vào `__init__.py`.
7. Unit test: craft bar sequence từng branch; assert Signal fields. Bắt buộc test: (a) TP chọn key-level khi swing xa / chọn tp_rr khi swing gần; (b) **key-level KHÔNG gồm high bar hiện tại** (off-by-one); (c) **không có same-bar exit** — entry bar's low không trigger SL (vì SL < pattern_low ≤ entry-bar low); (d) **position-size sanity** cho shallow pattern (size > 0, không bị reject); (e) invalid param mỗi loại → `ValueError`; (f) `max_rejection_wick_pct=1.0` không lọc gì; (g) reject/size=0 entry KHÔNG wedge `_open_direction`.
8. Integration test: feed synthetic OHLCV, để PaperBroker auto-fill SL/TP, assert ≥2 trade + SL/TP đúng.
9. `uv run pytest tests/core_test tests/backtest_test -q`, `uv run lint-imports`, `uv run ruff check`. (Không có mypy.)

## Success Criteria

- [ ] `GET /backtest/strategies` (hoặc `STRATEGY_REGISTRY.keys()`) chứa `engulfing`.
- [ ] Unit: bullish strong → LONG Signal; bullish weak (wick > ngưỡng) → None; mirror short.
- [ ] Unit: `TP == max(tp_rr, key_level)` LONG; `min` SHORT; luôn ≥ RR 1:1.
- [ ] Unit: SL == pattern_extreme ± buffer; `pattern_low = min(2 nến)`.
- [ ] Unit: key-level KHÔNG gồm high/low bar hiện tại (off-by-one pinned).
- [ ] Unit: KHÔNG có same-bar exit — entry-bar low không trigger SL.
- [ ] Unit: position-size sanity cho shallow pattern (size > 0, không reject).
- [ ] Unit: position cap giữ 1 lệnh; `on_order_filled` entry-fill set + opposite-fill reset; reject/size=0 KHÔNG wedge `_open_direction`.
- [ ] Unit: `direction=long` bỏ qua bearish; `max_rejection_wick_pct=1.0` không lọc gì; mỗi invalid param → `ValueError`.
- [ ] Integration: backtest ra ≥2 trade với SL/TP đúng (giả định 260628-1514 land).
- [ ] `uv run lint-imports` 7 contracts pass; `uv run ruff check` xanh.

<!-- Updated: Validation Session 1 + Red Team Session 1 - params + off-by-one pin + set-after-fill + validate-all -->
> **Params:** `_DEFAULTS = {"direction":"both", "sl_buffer_pct":0.001, "key_level_lookback_bars":20, "max_rejection_wick_pct":0.30}`. `pattern_low/high = min/max(prev, curr)` — 2 nến. `max_rejection_wick_pct=0.30` là default tune-được (chưa validate data).

## Risk Assessment

- **Risk (BLOCKER, red-team Finding 1):** implement trên dirty-tree 260628-1514 (chưa commit) → false-pass gate. Mitigation: step 1 gate kiểm tra commit + plan completed, không phải grep.
- **Risk (red-team Finding 8):** off-by-one — key-level gồm bar hiện tại → TP lệch/`TP==entry`. Mitigation: snapshot trước append, `maxlen=N` (không +1); test high bar hiện tại không trong set.
- **Risk (red-team Finding 6):** `_open_direction` set lạc quan → wedge khi entry reject/size=0. Mitigation: set trong `on_order_filled` (entry-fill), không trong `on_bar_completed`; test reject path. **Phụ thuộc:** entry fill phải publish `OrderFilledEvent` (step 2 verify); nếu không → fallback optimistic-set + rollback-on-reject.
- **Risk:** `_prev_bar` không cập nhật ở early-return → bỏ lỡ pattern kế. Mitigation: cập nhật CUỐI hàm mọi nhánh; test sequence cap→release.
- **Risk:** TP < entry do key-level sai phía. Mitigation: `max`/`min` ép đúng phía; assert TP > entry (LONG).
- **Risk (red-team, REJECTED nhưng test phòng):** same-bar entry stop-out — reviewer lo entry-bar low trigger SL. Disproven: SL = pattern_low×(1−buffer) < pattern_low ≤ entry-bar low → không trigger. Vẫn thêm test (c) canh.
