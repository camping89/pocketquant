# Phase 02 — YAML Config Example

## Overview

- **Status:** pending
- **Priority:** P1
- **Effort:** S (~10 min)
- **File to create:** `strategies/examples/hitnrun-btcusdt-5m.yaml`

## Context Links

- Reference: [ma-crossover-btc-usdt.yaml](../../strategies/examples/ma-crossover-btc-usdt.yaml)

## YAML Content

```yaml
# HitAndRun Strategy — BTC/USDT 5m
# Long: double/triple bottom (ATR-clustered) + downtrend (MA filter)
# Short: double/triple top + uptrend (MA filter)
# SL/TP: dynamic from 10-bar range ± offset%

id: hitnrun-btcusdt-5m
name: "HitAndRun BTC/USDT 5m"
symbol: BTCUSDT
exchange: OKX
interval: 5m
trigger: bar
broker: paper
enabled: true

parameters:
  lookback: 10              # bars to scan for pattern
  atr_period: 14            # ATR calculation period
  bottom_atr_mult: 0.5      # lows within 0.5*ATR = "near each other"
  min_bottoms: 2            # min bottoms/tops to confirm pattern
  ma_period: 20             # SMA period for trend filter
  sl_offset_pct: 0.10       # SL = lowest_low * (1 - 0.10) for long
  tp_offset_pct: 0.10       # TP = highest_high * (1 + 0.10) for long
  direction: both           # "long", "short", or "both"

risk:
  model: percent_risk
  risk_per_trade: 0.02      # 2% per trade
  max_positions: 1
  max_exposure_percent: 0.10

orders:
  entry_type: market
  take_profit:
    enabled: false          # TP managed dynamically by strategy, not OrderConfig
    distance_percent: 0.02
  stop_loss:
    enabled: false          # SL managed dynamically by strategy, not OrderConfig
    distance_percent: 0.01
```

## Note on `orders.take_profit` / `orders.stop_loss`

Set `enabled: false` for both — `HitAndRunStrategy` computes SL/TP directly in the `Signal`
(`stop_loss_price`, `take_profit_price` fields). The `OrderConfig.distance_percent` fields are
irrelevant for this strategy and only kept for schema compliance.

## Implementation Steps

1. Create `strategies/examples/hitnrun-btcusdt-5m.yaml` with above content
2. Verify YAML loads via `StrategyConfig.from_dict()` without errors

## Success Criteria

- [ ] YAML parses without validation errors
- [ ] All `parameters` keys accessible via `config.parameters.get(key)`
- [ ] Strategy ID, symbol, exchange, interval, trigger all populated correctly
