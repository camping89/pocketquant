# Triple Screen 15m,1h,4h stop/strategy, lookback 80: 2023-2026 at 2% risk and 1:500

The frozen config has no edge out of sample. On 1 497 trades from 2023-01 to 2025-11-08, the mean trade is -0.007 R (t = -0.16). At 2% risk per trade and 1:500 leverage, 10 000 USD ends at 6 910 USD after a -91.9% drawdown. The 2025-11..2026-11 result that chose this config is the only strong year in the four.

## What was run

- **Data.** Prod `bars` for XAUUSD:EXNESS were backfilled from Exness with `scripts/backfill/provider_bars.py`. 15m now starts 2022-05-01 (107 163 bars), 1h 2020-05-14 and 4h 2020-11-09. The only gaps over three days are holidays. Backups taken first are on the VPS at `/opt/pocketquant/backups/bars-xauusd-{15m,1h,4h}-pre-backfill-20261111.archive`.
- **Run.** Prod backtest `01a1c980-46bc-7400-acb1-f2f6a90c6323`, launched through the api route. Same settings as run `01a1c41f`: Triple Screen `15m,1h,4h`, `entry_type=stop`, `exit_mode=strategy`, `stop_lookback=80`, spread 0.08, commission 3 bp, slippage 0.1 bp, 10 000 USD. The window is 2023-01-01 to 2026-11-10 23:59 UTC. Nothing was tuned.
- **Stored result.** With the engine's 10% notional cap at leverage 1: +8.85%, PF 1.233, 1 991 trades, win rate 33.5%, max drawdown -2.28%.
- **Reproduction check.** The 489 trades of the earlier run all reappear with the same entry times. The new run adds one trade after 2026-11-08.
- **Rescale.** The trades were resized offline to 2% of current equity over each trade's entry-to-stop distance, as in `kongming-261111-1351-leveraged-triple-screen-reanalysis.md`. Resizing does not change the trade list. At 1:500 the margin is never binding: the largest position is 87x equity, which uses 17.4% of equity as margin.

## Per-trade edge in R

R is net profit per trade divided by its planned stop risk.

| Segment | Trades | Win rate | Mean R | t | Sum R | PF (R) | Sum R without the 5 best |
|---|---|---|---|---|---|---|---|
| Out of sample, 2023-01..2025-11-08 | 1 497 | 32.1% | -0.007 | -0.16 | -10.7 | 0.984 | -93.2 |
| In sample, 2025-11-09..2026-11-08 | 490 | 37.8% | +0.085 | 1.28 | +41.5 | 1.216 | -4.0 |
| 2023 | 539 | 31.2% | +0.061 | 0.70 | +32.8 | 1.136 | -41.5 |
| 2024 | 504 | 32.3% | +0.015 | 0.19 | +7.5 | 1.034 | -60.5 |
| 2025 | 525 | 33.5% | -0.094 | -1.82 | -49.2 | 0.784 | -84.7 |
| 2026 (to 11-10) | 423 | 37.8% | +0.093 | 1.32 | +39.4 | 1.243 | -4.1 |

Every year depends on its five best trades. Out of sample, longs made +73.4 R (t = 1.87) and shorts lost -84.1 R (t = -1.58). Gold rose strongly over the window. Reading that split as a long-only edge would be a new hypothesis chosen after the fact (inference); it needs its own untouched test.

## 2% compounding at 1:500, 2023-01-01 to 2026-11-10

| Year | Start USD | End USD | Change | Trades | Wins | Worst drawdown in the year |
|---|---|---|---|---|---|---|
| 2023 | 10,000.00 | 13,047.32 | +30.47% | 539 | 168 | -78.19% |
| 2024 | 13,047.32 | 11,609.43 | -11.02% | 504 | 163 | -64.21% |
| 2025 | 11,609.43 | 3,760.72 | -67.61% | 525 | 176 | -75.37% |
| 2026 | 3,760.72 | 6,910.39 | +83.75% | 423 | 160 | -27.75% |

- **Final:** 6 910 USD (-30.9%).
- **Max drawdown:** -91.9% on end-of-day equity, bottoming on 2025-12-11.
- **Path:** equity rose to about 35 900 USD by the end of June 2023, then fell to about 8 600 by October 2023.
- **Worst day:** 2023-07-12, -3 469 USD (-10.8%).
- **Worst losing streak:** 10 trades, -12.2%, ending 2023-07-05.
- **Worst single trade:** -3.72% of equity (-1.86 R, nearly twice the planned risk; the cause was not checked). The best was +39.0%.
- **Out of sample only** (10 000 USD from 2023-01): ends at 3 683 USD (-63.2%) after a -91.5% drawdown.
- **In sample only** (the earlier year): ends at 18 857 USD (+88.6%) with a -27.8% drawdown, matching the kongming report.

Lower risk on the same trades:

| Risk per trade | Final USD, full window | Max drawdown, full | Final USD, out of sample only |
|---|---|---|---|
| 2% | 6,910 | -91.9% | 3,683 |
| 1% | 10,494 | -67.6% | 7,309 |
| 0.5% | 10,906 | -41.1% | 8,990 |

## Risk of ruin

Method: a bootstrap that draws 517 trades per year (the run's trade rate) from the 1 497 out-of-sample R values, over 20 000 one-year paths, compounding at the given risk. "Zero edge" shifts every R so the mean is zero.

| Risk | Edge | P(drawdown ≥ 20%) | P(drawdown ≥ 50%) | P(year ends in loss) |
|---|---|---|---|---|
| 2% | out-of-sample | 100% | 75% | 70% |
| 2% | zero | 100% | 71% | 65% |
| 1% | out-of-sample | 95% | 14% | 63% |
| 0.5% | out-of-sample | 47% | 0% | 59% |

## Conclusion

- **Verified:** the config's 2025-11..2026-11 profit does not repeat on 2023-01..2025-11. The out-of-sample mean is indistinguishable from zero and slightly negative.
- **Inference:** the in-sample year was picked from about 110 configurations, and this test shows a selection artefact, not an edge. Trading it at 2% risk and 1:500 would most likely lose most of the account within a year.
- **Not tested:** the two pessimistic engine rules (SL wins a same-bar touch; a stop entry counts as stopped on its fill bar) apply equally to every year, so they do not explain the gap between years. Swap and real Exness account terms are not modelled.

## Unresolved questions

- Stop this config, or take one new hypothesis (for example long-only, or the canonical Triple Screen sketch from `kongming-261110-1218-triple-screen-canonical-gap.md`) to a fresh untouched window? No untouched gold window is left after 2023-2026, except 2022-05..2022-12 of 15m bars.
- Keep the deeper 1h, 4h and 15m bars on prod (current state), or restore the backups?
