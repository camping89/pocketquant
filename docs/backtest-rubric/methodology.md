# Backtest Rubric Methodology

`RUBRIC_VERSION = 1.0.0`

An offline scorecard that grades every finished backtest run on three axes —
**Performance**, **Robustness**, **Design-integrity** — from the run's stored
result, its trade path, and its strategy source. It answers two questions: is a
run healthy by quant best-practice, and does the strategy *design* (not just the
DB result) hold up. It describes run health; it does not predict live results.

> **Crypto-1m caveat.** The thresholds below come from equity/daily-frequency
> research. On 1-minute crypto they are directional references, not calibrated
> cutoffs. Read grades as relative health signals, not verdicts.

## Axes and aggregation

Two aggregation levels, deliberately different:

- **metric → axis**: weighted sum. A metric scoring N/A is dropped and the
  remaining weights are re-normalized (no false zero).
- **axis → overall**: **minimum** (weakest-axis dominates). A robustness F drags
  the overall down even with A-grade performance — a weighted average would hide
  the F.

Grade map (applies to axis score and overall): A ≥ 3.5, B ≥ 2.5, C ≥ 1.5,
D ≥ 0.5, F < 0.5.

## Metric bands (value → points 0-4)

Each metric scores by the first band its raw value falls under (`<` upper bound;
last band is +inf). Higher-better unless noted.

| Metric | Axis | 0 | 1 | 2 | 3 | 4 | Note |
|---|---|---|---|---|---|---|---|
| calmar | performance | <0 | <1 | <2 | <3 | ≥3 | CAGR / \|maxDD\| |
| mar | performance | <0 | <0.5 | <1 | <2 | ≥2 | return / \|maxDD\| |
| ulcer_index | performance | ≥15 | <15 | <10 | <5 | <2 | **lower better** |
| ulcer_performance_index | performance | <0 | <0.5 | <1 | <2 | ≥2 | |
| recovery_factor | performance | <0.5 | <1 | <2 | <3 | ≥3 | |
| psr | robustness | <0.5 | <0.75 | <0.9 | <0.95 | ≥0.95 | Probabilistic Sharpe |
| sqn | robustness | <1 | <1.6 | <2 | <3 | ≥3 | System Quality Number |
| tail_ratio | robustness | <0.8 | <1.0 | <1.2 | <1.5 | ≥1.5 | \|p95/p5\| of returns |
| common_sense_ratio | robustness | <0.8 | <1.0 | <1.5 | <2.0 | ≥2.0 | PF × tail |
| gain_to_pain | robustness | <0 | <0.5 | <1.0 | <1.5 | ≥1.5 | |
| cost_to_edge | design_integrity | <0.5 | <0.8 | <1.0 | <1.25 | ≥1.25 | gross edge / friction |
| mfe_capture | design_integrity | <0.3 | <0.45 | <0.6 | <0.75 | ≥0.75 | exit profit / MFE |
| mae_to_stop | design_integrity | <0.5 → 1 | | 2 if <1.0 | 3 if <0.6 | 4 if <0.85 | **range-optimal**, best 0.6-0.85 |
| degrees_of_freedom | design_integrity | ≥10 | <10 | <8 | <6 | <4 | **lower better** (Gray-penalty) |

`mae_to_stop` is a bell: `<0.5 → 1` (stop too wide), `0.5-0.6 → 3`, `0.6-0.85 → 4`
(calibrated), `0.85-1.0 → 2`, `≥1.0 → 1` (stop too tight).

## Axis weights (sum to 1 per axis)

| Axis | Metric | Weight |
|---|---|---|
| performance | calmar | 0.25 |
| performance | mar | 0.25 |
| performance | ulcer_index | 0.25 |
| performance | ulcer_performance_index | 0.15 |
| performance | recovery_factor | 0.10 |
| robustness | psr | 0.30 |
| robustness | sqn | 0.25 |
| robustness | tail_ratio | 0.15 |
| robustness | common_sense_ratio | 0.15 |
| robustness | gain_to_pain | 0.15 |
| design_integrity | cost_to_edge | 0.35 |
| design_integrity | degrees_of_freedom | 0.25 |
| design_integrity | mfe_capture | 0.20 |
| design_integrity | mae_to_stop | 0.20 |

## Formulas

Returns basis:

- **Distribution metrics** (tail_ratio, gain_to_pain) use per-trade **net**
  returns (`(pnl − commission) / notional`).
- **sqn** uses realized **R-multiples** (`move / stop_distance`), the van Tharp
  definition — not net returns. Only trades with a usable stop contribute.
- **Drawdown metrics** (ulcer, calmar, recovery, mar) use the **equity curve**
  (peak-to-trough by construction).
- `profit_factor` is reported **gross** (matches the stored metric); `cost_to_edge`
  then shows whether costs erase the gross edge.

| Metric | Formula |
|---|---|
| calmar | `CAGR / \|maxDD\|` |
| mar | `total_return / \|maxDD\|` |
| ulcer_index | `sqrt(Σ (dd%)² / (n−1))`, dd% = drawdown × 100 |
| ulcer_performance_index | `(total_return×100 − rf) / ulcer_index`, rf=0 |
| tail_ratio | `\|p95 / p5\|` of per-trade net returns |
| common_sense_ratio | `profit_factor × tail_ratio` |
| cpc_index | `profit_factor × win_rate × win_loss_ratio` |
| gain_to_pain | `Σ returns / \|Σ negative returns\|` |
| recovery_factor | `\|Σ returns\| / \|maxDD\|` |
| kelly | `((b·p) − q) / b`, b=win/loss ratio, p=win rate, q=1−p |
| risk_of_ruin | `((1−wr)/(1+wr))^n`, log-space |
| sqn | `(mean R / std R) × sqrt(n)` |
| cost_to_edge | `gross_edge_bps / friction_bps` |
| friction_bps | `2 × (commission_bps + slippage_bps)` (round-trip) |
| psr | `Φ( (SR − SR*)·√(n−1) / √(1 − γ3·SR + ((γ4−1)/4)·SR²) )` |

- `Φ` is the standard normal CDF via `math.erf` (no scipy).
- `SR*` = 0 (no benchmark family at n=6 runs; caveat carried in output).
- `γ3` = skew, `γ4` = **raw** kurtosis (normal = 3). Excess kurtosis would flip
  the denominator sign.

## Robustness sampling

- **PSR** — single-series confidence that true Sharpe > SR*, given the return
  distribution's skew, kurtosis, and sample size.
- **Sequencing bootstrap** — permutes trade **order** (same PnL set) 1000×,
  rebuilds equity, records max-drawdown percentiles (p50/p95/p99). Measures
  sequencing risk; it does NOT resample with replacement, so it says nothing
  about the tail of the PnL distribution itself. Seeded for reproducibility.

## Trade-path MAE/MFE (offline approximation)

Reconstructed from bar high/low inside `[entry_time, exit_time]`. The entry bar
may hold the fill mid-bar, so extremes can slightly overstate the true
excursion. `low_coverage` flags runs whose bar windows have gaps. When the engine
writes MAE/MFE natively, prefer those.

## Static AST audit

Parses the strategy source (resolved via `STRATEGY_REGISTRY`) — never runs it.
Extracts degrees of freedom (`_DEFAULTS` keys), SL/TP geometry shape,
entry-frequency class, lookahead safety, and direction bias. Heuristic, not
formal verification; every field falls back to `unknown` rather than raising.

## Versioning

Any change to a band, weight, or formula bumps `RUBRIC_VERSION`. Persisted
scorecards are keyed by version; a re-score at a new version overwrites the
`scorecard` field (latest only).
