# Backtest Rubric — Comparison

`RUBRIC_VERSION = 1.0.0`

> **Caveat.** Thresholds derive from equity/daily research; on 1m crypto they are directional references, not calibrated cutoffs. Scores describe run health, not future performance.


| Rank | Strategy | Symbol/Interval | Performance | Robustness | Design-integrity | Overall | Diagnosis |
|---|---|---|---|---|---|---|---|
| 1 | engulfing | BTCUSDT:BINANCE 1m | F (0.10) | F (0.15) | C (1.95) | **F** (0.10) | no directional edge: gross edge ≈ 0 before costs; statistically unreliable (PSR < 0.5) |
| 2 | engulfing | BTCUSDT:BINANCE 1m | F (0.10) | F (0.15) | C (1.95) | **F** (0.10) | no directional edge: gross edge ≈ 0 before costs; statistically unreliable (PSR < 0.5) |
| 3 | engulfing_pullback30_touch | BTCUSDT:BINANCE 1m | F (0.10) | F (0.15) | C (1.95) | **F** (0.10) | no directional edge: gross edge ≈ 0 before costs; statistically unreliable (PSR < 0.5) |
| 4 | hitnrun2 | BTCUSDT:BINANCE 1m | D (0.75) | F (0.30) | C (2.05) | **F** (0.30) | cost-killed: gross edge positive but costs erase it; statistically unreliable (PSR < 0.5) |
| 5 | hitnrun2 | BTCUSDT:BINANCE 1m | D (0.75) | F (0.30) | C (2.05) | **F** (0.30) | cost-killed: gross edge positive but costs erase it; statistically unreliable (PSR < 0.5) |
