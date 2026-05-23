# Brainstorm — hitnrun2 strategy (1m breakdown-buy / breakup-sell)

**Date:** 2026-05-23
**Branch:** worktree-hitnrun2-strategy (rebased on develop @ 2b42fdb)
**Worktree:** `C:/w/_me/pocketquant/.claude/worktrees/hitnrun2-strategy`

## Problem

User muốn:
1. Xóa sạch 2 strategy hiện tại (`ma_crossover`, `hit_and_run`) — code, YAML, tests refs, frontend refs.
2. Tạo strategy mới `hitnrun2` — code-only (no YAML config), khung 1m.
3. Backtest hỗ trợ + tests đầy đủ (unit + integration).

Spec gốc của user:
> **hitnrun2**
> * khung 1m
> Lệnh Long:
>  - Tìm đáy của 4 giờ trước, khi giá rơi xuống thì vào lệnh long
>  - SL = Min (đáy 8h, 1% tài khoản)
>  - TP = max (ở đỉnh 1 tiếng trước, 2% tài khoản)
> Lệnh short: Ngược lại với lệnh Long ở trên

## Clarifications (đã chốt với user)

| Item | Decision |
|---|---|
| Entry condition | Giá break xuống dưới đáy 4h (breakdown buy) |
| SL semantic | SL gần entry hơn — chọn loss ít hơn. 1% account = hard cap |
| TP semantic | TP xa entry hơn — chọn target ambitious. 2% account = min target |
| Cleanup scope | Xóa sạch: code + YAML + tests + frontend refs |
| Position cap | Max 1 position cùng lúc |
| Direction | Configurable: long/short/both, default `both` |
| Lookback | Configurable (default 240/480/60 bars) |
| Exit | Broker tự đóng qua SL/TP price trên Signal |
| Tests | Unit + Integration backtest e2e |

## Approaches Considered

### A. Hardcode 1m + lookback (KISS)
- Pros: code đơn giản, đúng nghĩa "hitnrun2" = strategy cụ thể.
- Cons: không grid-optimize được, ít flexibility cho experimentation.

### B. Configurable params + interval guard
- Pros: optimize qua grid search, dễ ablation study, reuse logic cho khung khác.
- Cons: thêm code path validation.
- **CHỌN** — phù hợp pipeline backtest hiện có.

### C. Strategy tự manage exit qua on_tick
- Pros: không phụ thuộc broker capabilities.
- Cons: phức tạp, broker hiện tại đã support sl/tp price tốt.
- **REJECT** — broker đã làm được.

## Final Design

### Class: `HitNRun2Strategy(IStrategy)`

**File:** `packages/pocketquant-core/src/pocketquant/core/concepts/strategy/services/hitnrun2.py`

**Logic (long):**
```
prev_low_4h  = min(lows[-entry_lookback-1 : -1])     # excludes current bar
prev_low_8h  = min(lows[-sl_lookback-1    : -1])
prev_high_1h = max(highs[-tp_lookback-1   : -1])

if direction in (long, both) and not in_position:
    if current.close < prev_low_4h:
        entry = current.close
        sl    = MAX( prev_low_8h,  entry * (1 - max_loss_pct) )    # closer = safer
        tp    = MAX( prev_high_1h, entry * (1 + min_profit_pct) )  # farther = bigger R
        emit LONG signal
```

Short = mirror (break đỉnh 4h, SL = MIN(đỉnh 8h, entry*(1+max_loss_pct)), TP = MIN(đáy 1h, entry*(1-min_profit_pct)))

**Parameters:**

| Param | Default | Notes |
|---|---|---|
| `entry_lookback_bars` | 240 | 4h |
| `sl_lookback_bars` | 480 | 8h |
| `tp_lookback_bars` | 60 | 1h |
| `max_loss_pct` | 0.01 | hard cap |
| `min_profit_pct` | 0.02 | min target |
| `direction` | `"both"` | long/short/both |

**State:**
- `deque(maxlen=max(sl,entry,tp)+1)` cho `_highs`, `_lows`, `_closes`
- `_open_direction: Direction | None` — track 1-position cap
- `on_fill` reset state khi exit fill (broker đóng SL hoặc TP)

**Warmup:** skip on_bar tới khi `len(buffer) >= sl_lookback_bars + 1`

### Registry

```python
# services/__init__.py
from pocketquant.core.concepts.strategy.services.hitnrun2 import HitNRun2Strategy
STRATEGY_REGISTRY = {"hitnrun2": HitNRun2Strategy}
__all__ = ["HitNRun2Strategy", "STRATEGY_REGISTRY"]
```

### Files touched

**Create:**
- `packages/pocketquant-core/src/pocketquant/core/concepts/strategy/services/hitnrun2.py`
- `packages/pocketquant-core/tests/unit/concepts/strategy/test_hitnrun2.py`
- `packages/pocketquant-core/tests/unit/concepts/strategy/__init__.py`
- `packages/pocketquant-backtest/tests/engine/test_hitnrun2_backtest.py`

**Edit:**
- `packages/pocketquant-core/src/pocketquant/core/concepts/strategy/services/__init__.py`
- `packages/pocketquant-api/tests/integration/test_run_all_backtest_cascade.py`
- `packages/pocketquant-api/tests/integration/test_concurrent_run_all.py`
- `README.md` (strategy list)

**Delete:**
- `packages/pocketquant-core/src/pocketquant/core/concepts/strategy/services/ma_crossover.py`
- `packages/pocketquant-core/src/pocketquant/core/concepts/strategy/services/hit_and_run.py`
- `strategies/examples/ma-crossover-btc-usdt.yaml`
- `strategies/examples/hitnrun-btcusdt-5m.yaml`

### Test Plan

**Unit** (`test_hitnrun2.py`):
- `test_warmup_returns_none_until_sl_lookback_full`
- `test_long_entry_on_breakdown_below_4h_low`
- `test_short_entry_on_breakup_above_4h_high`
- `test_sl_capped_at_max_loss_pct_when_8h_low_too_far`
- `test_sl_uses_8h_technical_when_within_cap`
- `test_tp_uses_min_profit_pct_when_1h_high_too_close`
- `test_tp_uses_1h_technical_when_above_min_target`
- `test_direction_long_only_skips_short_signal`
- `test_direction_short_only_skips_long_signal`
- `test_position_cap_blocks_second_signal_while_open`
- `test_on_fill_resets_state_for_next_entry`

**Integration** (`test_hitnrun2_backtest.py`):
- `test_backtest_runs_on_synthetic_downtrend_fires_long_signals`
- `test_backtest_runs_on_synthetic_uptrend_fires_short_signals`
- Both assert `metrics.total_trades > 0`, `equity_curve` populated, `status == "completed"`.

## Risks

1. **Warmup 8h** = 480 bars on 1m. Backtest < 8h → 0 trades. Document trong docstring + raise warning nếu range không đủ.
2. **Falling-knife exposure** — không có MA / trend filter. Đúng spec user; rủi ro thuộc về user.
3. **Sticky open position** — nếu broker không fill SL/TP (bug, mismatch price), state stuck. Mitigation: log "position_held_too_long" sau N bars (deferred — không có trong scope hiện tại).
4. **Frontend refs** — `subscription-panel.tsx` v.v. dùng `strategy_id` dynamic (qua API list), không hardcode. README và http test files có thể hardcode.

## Success Criteria

- `uv run pytest packages/pocketquant-core/tests/unit/concepts/strategy/test_hitnrun2.py` → all green
- `uv run pytest packages/pocketquant-backtest/tests/engine/test_hitnrun2_backtest.py` → all green
- `uv run pytest packages/pocketquant-api/tests/integration/test_run_all_backtest_cascade.py packages/pocketquant-api/tests/integration/test_concurrent_run_all.py` → all green (sau khi update id)
- `just lint` + `just types` clean
- POST `/api/v1/backtest/run` với `{"strategy_id": "hitnrun2", "symbol": "BTCUSDT:BINANCE", "interval": "1m", ...}` trả `status: completed`

## Unresolved Questions

Không còn.
