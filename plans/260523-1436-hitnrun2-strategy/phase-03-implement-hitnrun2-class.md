---
phase: 3
title: "Implement HitNRun2 class"
status: completed
priority: P1
effort: "2-3h"
dependencies: [2]
---

# Phase 3: Implement HitNRun2 class

## Overview

Create `HitNRun2Strategy` in `core/concepts/strategy/services/hitnrun2.py`. Pure breakdown-buy / breakup-sell on 1m, with technical levels for SL/TP capped by account-loss/profit floors. Depends on phase 2 (broker handles SL/TP fills).

## Requirements

**Entry (long):** previous closed-bar window `lows[-entry_lookback-1 : -1]` (excludes current bar). If `current.close < min(prev_lows_4h)` ⇒ emit `Signal(Direction.LONG, entry_price=close, sl, tp, ...)`.

**Entry (short):** mirror — `current.close > max(prev_highs_4h)`.

**SL (long):** `MAX( min(lows[-sl_lookback-1:-1]),  entry * (1 - max_loss_pct) )`
**TP (long):** `MAX( max(highs[-tp_lookback-1:-1]), entry * (1 + min_profit_pct) )`

**SL (short):** `MIN( max(highs[-sl_lookback-1:-1]), entry * (1 + max_loss_pct) )`
**TP (short):** `MIN( min(lows[-tp_lookback-1:-1]),  entry * (1 - min_profit_pct) )`

**Position cap:** at most 1 open position. Track via `_open_direction: Direction | None`. Skip signal generation if open.

**State reset:** `on_fill` receives the broker's exit fill (SELL closing long, BUY closing short). When fill is opposite of open direction → reset state.

**Direction param:** `"long" | "short" | "both"` (default `both`). Configurable lookbacks. No interval guard — strategy is logically 1m but params allow other tuning.

## Architecture

```
on_start  → clear deques + state
on_bar    → snapshot prev windows; append current; check warmup + position cap; emit Signal
on_fill   → if order.side opposite of _open_direction → reset _open_direction = None
```

Buffer size = `max(entry_lookback, sl_lookback, tp_lookback) + 1` (default 481). Use `deque(maxlen=...)` for O(1) append + bounded memory.

Snapshot `prev_highs/prev_lows = list(self._highs)[-N:]` **before** appending current bar so windows exclude current.

```python
async def on_bar(self, bar):
    high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])

    # Snapshot windows BEFORE appending current bar
    prev_lows_entry  = list(self._lows)[-self.entry_lookback_bars:]
    prev_highs_entry = list(self._highs)[-self.entry_lookback_bars:]
    prev_lows_sl     = list(self._lows)[-self.sl_lookback_bars:]
    prev_highs_sl    = list(self._highs)[-self.sl_lookback_bars:]
    prev_lows_tp     = list(self._lows)[-self.tp_lookback_bars:]
    prev_highs_tp    = list(self._highs)[-self.tp_lookback_bars:]

    self._highs.append(high); self._lows.append(low); self._closes.append(close)

    # Warmup: need sl_lookback_bars closed bars BEFORE current
    if len(prev_lows_sl) < self.sl_lookback_bars: return None

    # Position cap
    if self._open_direction is not None: return None

    # Long entry: break below 4h low
    if self.direction in ("long", "both"):
        prev_low_4h = min(prev_lows_entry)
        if close < prev_low_4h:
            sl = max(min(prev_lows_sl), close * (1 - self.max_loss_pct))
            tp = max(max(prev_highs_tp), close * (1 + self.min_profit_pct))
            self._open_direction = Direction.LONG
            return self._mk_signal(Direction.LONG, close, sl, tp, bar, "breakdown")

    # Short entry: break above 4h high
    if self.direction in ("short", "both"):
        prev_high_4h = max(prev_highs_entry)
        if close > prev_high_4h:
            sl = min(max(prev_highs_sl), close * (1 + self.max_loss_pct))
            tp = min(min(prev_lows_tp), close * (1 - self.min_profit_pct))
            self._open_direction = Direction.SHORT
            return self._mk_signal(Direction.SHORT, close, sl, tp, bar, "breakup")

    return None
```

## Related Code Files

**Create:**
- `packages/pocketquant-core/src/pocketquant/core/concepts/strategy/services/hitnrun2.py`

**Modify:**
- `packages/pocketquant-core/src/pocketquant/core/concepts/strategy/services/__init__.py` — register: `STRATEGY_REGISTRY = {"hitnrun2": HitNRun2Strategy}`.

## Implementation Steps

1. Create `hitnrun2.py` (target <200 lines incl. docstring; split helpers into module-level functions if needed).
2. Class: `HitNRun2Strategy(IStrategy)`.
   - `__init__(config)`: parse params with defaults (240/480/60/0.01/0.02/"both"); `_min_bars = max(sl, entry, tp)`; bounded deques `maxlen = _min_bars + 1`.
   - `on_start`: clear deques, `_open_direction = None`.
   - `on_bar`: implement logic above.
   - `on_fill(order, fill_price)`: if `(self._open_direction == LONG and order.side == SELL)` or `(self._open_direction == SHORT and order.side == BUY)` → `self._open_direction = None`.
   - `_mk_signal(direction, close, sl, tp, bar, tag)`: build `Signal(symbol=self.config.symbol, direction=direction, confidence=0.7, timestamp=bar.get("timestamp") or now(UTC), strategy_id=self.id, entry_price=close, stop_loss_price=sl, take_profit_price=tp, entry_logic=...)`.
3. Update `services/__init__.py` with import + registry entry.
4. Compile check: `uv run python -c "from pocketquant.core.concepts.strategy.services import STRATEGY_REGISTRY; assert 'hitnrun2' in STRATEGY_REGISTRY; print(STRATEGY_REGISTRY['hitnrun2'])"`.

## Success Criteria

- [ ] File <200 lines.
- [ ] All params readable from `config.parameters` with safe defaults.
- [ ] `STRATEGY_REGISTRY == {"hitnrun2": HitNRun2Strategy}`.
- [ ] Strategy can be instantiated: `HitNRun2Strategy(StrategyConfig(id="x", name="x", symbol="BTCUSDT:BINANCE", interval="1m"))`.
- [ ] `on_bar` returns `None` for first `sl_lookback_bars` bars (default 480).

## Risk Assessment

- **Risk:** Off-by-one in window slicing — `[-N:]` after appending vs before. **Mitigation:** snapshot before append, document inline; phase 4 test asserts boundary (current bar's low excluded from `prev_low_4h`).
- **Risk:** `Direction.EXIT` not used — broker SL/TP fill handles exit. Strategy never emits exit signals. Confirmed reasonable by phase 2.
- **Risk:** `on_fill` signature accepts `order: object` per IStrategy interface; need to access `.side`. **Mitigation:** in implementation, cast/check `hasattr(order, 'side')` or import `OrderAggregate` for typing. Document in docstring.
