# Backtest Rubric — Per-run Scorecards

`RUBRIC_VERSION = 1.0.0`

> **Caveat.** Thresholds derive from equity/daily research; on 1m crypto they are directional references, not calibrated cutoffs. Scores describe run health, not future performance.


## engulfing — 019f141c-a437-70a9-8d2a-d748b773d9e7

- **Overall:** F (0.10) — weakest-axis minimum
- **Symbol/Interval:** BTCUSDT:BINANCE 1m
- **Name:** —
- **Diagnosis:** no directional edge: gross edge ≈ 0 before costs; statistically unreliable (PSR < 0.5)

### performance — F (0.10)

| Metric | Value | Points | Weight |
|---|---|---|---|
| calmar | -1.000 | 0 | 0.25 |
| mar | -1.000 | 0 | 0.25 |
| ulcer_index | 33.720 | 0 | 0.25 |
| ulcer_performance_index | -1.603 | 0 | 0.15 |
| recovery_factor | 1.000 | 1 | 0.10 |

### robustness — F (0.15)

| Metric | Value | Points | Weight |
|---|---|---|---|
| psr | 0.000 | 0 | 0.30 |
| sqn | -4.407 | 0 | 0.25 |
| tail_ratio | 0.810 | 1 | 0.15 |
| common_sense_ratio | 0.751 | 0 | 0.15 |
| gain_to_pain | -0.489 | 0 | 0.15 |

### design_integrity — C (1.95)

| Metric | Value | Points | Weight |
|---|---|---|---|
| cost_to_edge | -0.113 | 0 | 0.35 |
| degrees_of_freedom | 4 | 3 | 0.25 |
| mfe_capture | 0.819 | 4 | 0.20 |
| mae_to_stop | 0.919 | 2 | 0.20 |

### Reconciliation (design vs realized)

- Planned R:R (mean / median): 1.239 / 0.955
- Realized R-multiple (mean / median): -0.046 / -1.017
- Gross edge: -0.789 bps · Friction: 7.000 bps · Net edge: -7.789 bps

### Trade-path MAE/MFE (offline approximation)

- MFE capture (winners): 0.819
- MAE-to-stop: 0.919
- MAE_R p50/p90: -1.016 / -0.365
- MFE_R p50/p90: 0.933 / 1.695
- Low coverage: False (1/11451 trades)

### Static audit (strategy definition)

- Degrees of freedom: 4 (direction, key_level_lookback_bars, max_rejection_wick_pct, sl_buffer_pct)
- Direction bias: both
- SL/TP geometry: pattern_extreme_sl + max/min(R, key_level)_tp
- Entry frequency: stateful_setup
- Lookahead safety: safe

## hitnrun2 — 019f1780-546f-743f-b919-e826b348c51b

- **Overall:** F (0.30) — weakest-axis minimum
- **Symbol/Interval:** BTCUSDT:BINANCE 1m
- **Name:** —
- **Diagnosis:** cost-killed: gross edge positive but costs erase it; statistically unreliable (PSR < 0.5)
- **Dedup aliases:** 019f1780-6b52-7493-8f84-5b7d7923ba78

### performance — D (0.75)

| Metric | Value | Points | Weight |
|---|---|---|---|
| calmar | -0.455 | 0 | 0.25 |
| mar | -0.455 | 0 | 0.25 |
| ulcer_index | 4.255 | 3 | 0.25 |
| ulcer_performance_index | -0.733 | 0 | 0.15 |
| recovery_factor | 0.455 | 0 | 0.10 |

### robustness — F (0.30)

| Metric | Value | Points | Weight |
|---|---|---|---|
| psr | 0.000 | 0 | 0.30 |
| sqn | -1.628 | 0 | 0.25 |
| tail_ratio | 0.533 | 0 | 0.15 |
| common_sense_ratio | 1.125 | 2 | 0.15 |
| gain_to_pain | -0.074 | 0 | 0.15 |

### design_integrity — C (2.05)

| Metric | Value | Points | Weight |
|---|---|---|---|
| cost_to_edge | 0.775 | 1 | 0.35 |
| degrees_of_freedom | 6 | 2 | 0.25 |
| mfe_capture | 0.478 | 2 | 0.20 |
| mae_to_stop | 0.778 | 4 | 0.20 |

### Reconciliation (design vs realized)

- Planned R:R (mean / median): 1025.412 / 45.026
- Realized R-multiple (mean / median): -1.850 / 0.847
- Gross edge: 5.422 bps · Friction: 7.000 bps · Net edge: -1.578 bps

### Trade-path MAE/MFE (offline approximation)

- MFE capture (winners): 0.478
- MAE-to-stop: 0.778
- MAE_R p50/p90: -0.781 / -0.093
- MFE_R p50/p90: 2.163 / 15.601
- Low coverage: False (0/5406 trades)

### Static audit (strategy definition)

- Degrees of freedom: 6 (direction, entry_lookback_bars, max_loss_pct, min_profit_pct, sl_lookback_bars, tp_lookback_bars)
- Direction bias: both
- SL/TP geometry: pattern_extreme_sl + max/min(R, key_level)_tp
- Entry frequency: windowed_continuation
- Lookahead safety: safe

## hitnrun2 — 019f1c6b-c4b0-7755-b11d-1edb428801de

- **Overall:** F (0.30) — weakest-axis minimum
- **Symbol/Interval:** BTCUSDT:BINANCE 1m
- **Name:** —
- **Diagnosis:** cost-killed: gross edge positive but costs erase it; statistically unreliable (PSR < 0.5)

### performance — D (0.75)

| Metric | Value | Points | Weight |
|---|---|---|---|
| calmar | -0.434 | 0 | 0.25 |
| mar | -0.434 | 0 | 0.25 |
| ulcer_index | 4.141 | 3 | 0.25 |
| ulcer_performance_index | -0.704 | 0 | 0.15 |
| recovery_factor | 0.434 | 0 | 0.10 |

### robustness — F (0.30)

| Metric | Value | Points | Weight |
|---|---|---|---|
| psr | 0.000 | 0 | 0.30 |
| sqn | -1.626 | 0 | 0.25 |
| tail_ratio | 0.525 | 0 | 0.15 |
| common_sense_ratio | 1.112 | 2 | 0.15 |
| gain_to_pain | -0.069 | 0 | 0.15 |

### design_integrity — C (2.05)

| Metric | Value | Points | Weight |
|---|---|---|---|
| cost_to_edge | 0.780 | 1 | 0.35 |
| degrees_of_freedom | 6 | 2 | 0.25 |
| mfe_capture | 0.478 | 2 | 0.20 |
| mae_to_stop | 0.779 | 4 | 0.20 |

### Reconciliation (design vs realized)

- Planned R:R (mean / median): 1025.042 / 44.737
- Realized R-multiple (mean / median): -1.847 / 0.847
- Gross edge: 5.460 bps · Friction: 7.000 bps · Net edge: -1.540 bps

### Trade-path MAE/MFE (offline approximation)

- MFE capture (winners): 0.478
- MAE-to-stop: 0.779
- MAE_R p50/p90: -0.781 / -0.093
- MFE_R p50/p90: 2.167 / 15.636
- Low coverage: False (0/5406 trades)

### Static audit (strategy definition)

- Degrees of freedom: 6 (direction, entry_lookback_bars, max_loss_pct, min_profit_pct, sl_lookback_bars, tp_lookback_bars)
- Direction bias: both
- SL/TP geometry: pattern_extreme_sl + max/min(R, key_level)_tp
- Entry frequency: windowed_continuation
- Lookahead safety: safe

## engulfing — 019f3676-9c08-71f2-a143-d60dc9d7d3b2

- **Overall:** F (0.10) — weakest-axis minimum
- **Symbol/Interval:** BTCUSDT:BINANCE 1m
- **Name:** —
- **Diagnosis:** no directional edge: gross edge ≈ 0 before costs; statistically unreliable (PSR < 0.5)

### performance — F (0.10)

| Metric | Value | Points | Weight |
|---|---|---|---|
| calmar | -1.000 | 0 | 0.25 |
| mar | -1.000 | 0 | 0.25 |
| ulcer_index | 33.443 | 0 | 0.25 |
| ulcer_performance_index | -1.605 | 0 | 0.15 |
| recovery_factor | 1.000 | 1 | 0.10 |

### robustness — F (0.15)

| Metric | Value | Points | Weight |
|---|---|---|---|
| psr | 0.000 | 0 | 0.30 |
| sqn | -3.827 | 0 | 0.25 |
| tail_ratio | 0.815 | 1 | 0.15 |
| common_sense_ratio | 0.764 | 0 | 0.15 |
| gain_to_pain | -0.484 | 0 | 0.15 |

### design_integrity — C (1.95)

| Metric | Value | Points | Weight |
|---|---|---|---|
| cost_to_edge | -0.099 | 0 | 0.35 |
| degrees_of_freedom | 4 | 3 | 0.25 |
| mfe_capture | 0.818 | 4 | 0.20 |
| mae_to_stop | 0.918 | 2 | 0.20 |

### Reconciliation (design vs realized)

- Planned R:R (mean / median): 1.241 / 0.955
- Realized R-multiple (mean / median): -0.040 / -1.016
- Gross edge: -0.694 bps · Friction: 7.000 bps · Net edge: -7.694 bps

### Trade-path MAE/MFE (offline approximation)

- MFE capture (winners): 0.818
- MAE-to-stop: 0.918
- MAE_R p50/p90: -1.015 / -0.366
- MFE_R p50/p90: 0.937 / 1.706
- Low coverage: False (1/11486 trades)

### Static audit (strategy definition)

- Degrees of freedom: 4 (direction, key_level_lookback_bars, max_rejection_wick_pct, sl_buffer_pct)
- Direction bias: both
- SL/TP geometry: pattern_extreme_sl + max/min(R, key_level)_tp
- Entry frequency: stateful_setup
- Lookahead safety: safe

## engulfing_pullback30_touch — 019f36d2-5f4f-75cc-95c6-49a7496c3a86

- **Overall:** F (0.10) — weakest-axis minimum
- **Symbol/Interval:** BTCUSDT:BINANCE 1m
- **Name:** engulfing_pullback30_touch_take1
- **Diagnosis:** no directional edge: gross edge ≈ 0 before costs; statistically unreliable (PSR < 0.5)

### performance — F (0.10)

| Metric | Value | Points | Weight |
|---|---|---|---|
| calmar | -1.000 | 0 | 0.25 |
| mar | -1.000 | 0 | 0.25 |
| ulcer_index | 27.007 | 0 | 0.25 |
| ulcer_performance_index | -1.612 | 0 | 0.15 |
| recovery_factor | 1.000 | 1 | 0.10 |

### robustness — F (0.15)

| Metric | Value | Points | Weight |
|---|---|---|---|
| psr | 0.000 | 0 | 0.30 |
| sqn | -2.751 | 0 | 0.25 |
| tail_ratio | 0.839 | 1 | 0.15 |
| common_sense_ratio | 0.778 | 0 | 0.15 |
| gain_to_pain | -0.538 | 0 | 0.15 |

### design_integrity — C (1.95)

| Metric | Value | Points | Weight |
|---|---|---|---|
| cost_to_edge | -0.089 | 0 | 0.35 |
| degrees_of_freedom | 5 | 3 | 0.25 |
| mfe_capture | 0.811 | 4 | 0.20 |
| mae_to_stop | 0.897 | 2 | 0.20 |

### Reconciliation (design vs realized)

- Planned R:R (mean / median): 1.706 / 0.969
- Realized R-multiple (mean / median): -0.039 / -1.023
- Gross edge: -0.620 bps · Friction: 7.000 bps · Net edge: -7.620 bps

### Trade-path MAE/MFE (offline approximation)

- MFE capture (winners): 0.811
- MAE-to-stop: 0.897
- MAE_R p50/p90: -1.031 / -0.172
- MFE_R p50/p90: 0.963 / 2.119
- Low coverage: False (1/8629 trades)

### Static audit (strategy definition)

- Degrees of freedom: 5 (direction, key_level_lookback_bars, max_rejection_wick_pct, pullback_pct, sl_buffer_pct)
- Direction bias: both
- SL/TP geometry: pattern_extreme_sl + max/min(R, key_level)_tp
- Entry frequency: stateful_setup
- Lookahead safety: safe
