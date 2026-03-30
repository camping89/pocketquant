# Phase 01 — HitAndRunStrategy Python Class

## Overview

- **Status:** pending
- **Priority:** P0
- **Effort:** M (~90 min)
- **File to create:** `packages/pocketquant-core/src/pocketquant/core/concepts/strategy/services/hit_and_run.py`

## Context Links

- Interface: [interfaces.py](../../packages/pocketquant-core/src/pocketquant/core/concepts/strategy/interfaces.py)
- Value objects: [value_objects.py](../../packages/pocketquant-core/src/pocketquant/core/concepts/strategy/value_objects.py)
- Reference impl: [ma_crossover.py](../../packages/pocketquant-core/src/pocketquant/core/concepts/strategy/services/ma_crossover.py)

## Strategy Logic

### Long Setup
1. `price < MA(ma_period)` → downtrend confirmed
2. Collect `lows[-lookback:]` — find ≥ `min_bottoms` lows within `bottom_atr_mult * ATR(atr_period)` of each other → double/triple bottom zone
3. `current bar.low <= zone_center + bottom_atr_mult * ATR` → pullback trigger
4. Not already in long position
5. **Signal:**
   - `entry = bar["close"]`
   - `SL = min(lows[-lookback:]) * (1 - sl_offset_pct)`
   - `TP = max(highs[-lookback:]) * (1 + tp_offset_pct)`

### Short Setup (mirror)
1. `price > MA(ma_period)` → uptrend confirmed
2. Collect `highs[-lookback:]` — find ≥ `min_tops` highs within `top_atr_mult * ATR` of each other → double/triple top zone
3. `current bar.high >= zone_center - top_atr_mult * ATR` → pullback trigger
4. Not already in short position
5. **Signal:**
   - `entry = bar["close"]`
   - `SL = max(highs[-lookback:]) * (1 + sl_offset_pct)`
   - `TP = min(lows[-lookback:]) * (1 - tp_offset_pct)`

## Parameters (from YAML `parameters:`)

| Key | Default | Description |
|-----|---------|-------------|
| `lookback` | `10` | Number of bars to scan for pattern |
| `atr_period` | `14` | ATR calculation period |
| `bottom_atr_mult` | `0.5` | Lows within `mult * ATR` = "near each other" |
| `min_bottoms` | `2` | Min number of bottoms to confirm pattern |
| `ma_period` | `20` | Period for trend filter MA (SMA) |
| `sl_offset_pct` | `0.10` | SL = lowest_low * (1 ± offset) |
| `tp_offset_pct` | `0.10` | TP = highest_high * (1 ± offset) |
| `direction` | `"both"` | `"long"`, `"short"`, or `"both"` |

## Internal State

```python
self._closes: deque[float]   # maxlen = max(atr_period, ma_period, lookback)
self._highs:  deque[float]
self._lows:   deque[float]
self._in_long:  bool
self._in_short: bool
```

## ATR Calculation

```
TR(i) = max(high - low, abs(high - prev_close), abs(low - prev_close))
ATR(n) = EMA of TR over n periods (Wilder's smoothing: mult = 1/n)
```

Use Wilder's smoothing (same as TradingView default):
```python
atr = prev_atr * (n-1)/n + tr * 1/n
```

## Bottom Clustering Algorithm

```python
def _find_bottom_zone(lows, atr) -> float | None:
    """Return zone center if ≥ min_bottoms lows cluster within atr_mult*ATR."""
    threshold = self.bottom_atr_mult * atr
    for i, anchor in enumerate(lows):
        cluster = [l for l in lows if abs(l - anchor) <= threshold]
        if len(cluster) >= self.min_bottoms:
            return sum(cluster) / len(cluster)  # zone center
    return None
```

## Implementation Steps

1. Create `hit_and_run.py` in `packages/pocketquant-core/src/pocketquant/core/concepts/strategy/services/`
2. Class `HitAndRunStrategy(IStrategy)`:
   - `__init__`: extract all parameters, init deques and state
   - `on_start`: reset all state
   - `on_bar`: main logic
     - append close/high/low to deques
     - wait for enough data (`len >= max(atr_period, ma_period, lookback)`)
     - compute ATR
     - compute MA
     - detect bottom/top zone
     - check pullback trigger
     - return `Signal` or `None`
   - `_calc_atr`: Wilder's ATR
   - `_calc_sma`: simple MA
   - `_find_cluster_zone`: bottom/top clustering
   - `_create_long_signal` / `_create_short_signal`: build `Signal` with explicit SL/TP

## File Size Target

~150 LOC — within 200-line limit. No need to split.

## Success Criteria

- [ ] `HitAndRunStrategy` passes all parameter extraction from config
- [ ] Returns `Signal` with correct `direction`, `entry_price`, `stop_loss_price`, `take_profit_price`
- [ ] Returns `None` when pattern not detected or insufficient data
- [ ] `direction = "long"` only fires long signals, `"short"` only short, `"both"` fires both
- [ ] No position double-entry (tracks `_in_long`, `_in_short` state)
- [ ] ATR never divides by zero (guard when prev bar not available)

## Risk

- **ATR init period:** first `atr_period` bars return `None` — expected behavior
- **Clustering false positives:** small `bottom_atr_mult` may miss patterns on volatile assets → user tunes via YAML
