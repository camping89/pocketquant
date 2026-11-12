# Strategy Assessment Rubric

A strategy gets real money only after it passes this rubric. Score one frozen configuration, and do it before any talk of position size or leverage.

## Terms

- **R:** the net result of one trade divided by its planned risk, which is the distance from entry to stop. A full stop-out is -1 R.
- **Out of sample (OOS):** data that was never used to choose any rule, parameter or interval.
- **Trial:** every configuration ever run while searching, including discarded ones and offline re-pricings. Keep a running count for each strategy family.
- **Planned risk:** the risk per trade that live trading would use. The owner fixed it at 2% of equity per trade.

## Hard Gates

A failed gate means no real money. Stop, or redesign the strategy and test it again on a new untouched sample.

| # | Gate | How to compute | Pass |
|---|---|---|---|
| G1 | Honest backtest | Follow [No look-ahead rules](./no-look-ahead-rules.md). Charge spread, commission, slippage and swap. Count trades whose result depends on the unknown order of events inside one bar, such as a stop entry and its stop loss touched in the same bar. | At most 2% of trades are ambiguous, or they are replayed on finer bars. The verdict is the same under the pessimistic and the optimistic fill. |
| G2 | Trials counted and deflated | Deflated Sharpe Ratio (DSR) of the chosen run, with N = the trial count. It is the probability that the Sharpe ratio beats the best Sharpe that N no-skill trials would show by luck. | DSR at least 0.95. Quick check: in-sample t at least 3.0. |
| G3 | Out-of-sample edge | t = mean(R) / sd(R) x sqrt(n) on the OOS trades. In a market with a trend, also subtract what that trend pays a random trade of the same side and holding time. | Mean R above 0, t at least 2.0, n at least 300, and the trend-adjusted mean above 0. |
| G4 | Survivable at the planned risk | Bootstrap at least 10 000 one-year paths from the OOS R list at the planned risk. Kelly fraction: the risk per trade that maximises mean log growth on the OOS list. | P(drawdown of 50% or more within a year) at most 10%. Planned risk at most half the Kelly fraction. |
| G5 | Cost stress | Re-price the OOS trades at twice the modelled round-trip cost, or at the measured spread plus stop-order slippage. | OOS mean R still above 0. |
| G6 | Paper incubation | Paper trade the frozen configuration for 3 to 6 months. | At least 100 trades. The realised mean R is inside the backtest's bootstrap 90% band. Fills and stops behave as modelled. |

Power check before any test: the smallest mean R that can reach t = 2 is 2 x sd(R) / sqrt(n). A sample too small for the expected edge can reject a strategy but cannot confirm one.

## Scored Criteria

Compute each on the OOS trades, net of costs. Score 0 (fail), 1 (warn) or 2 (pass), for 20 points in total.

| # | Criterion | How to compute | Fail / warn / pass |
|---|---|---|---|
| S1 | Expectancy quality | SQN-100 = 10 x mean(R) / sd(R) | below 1.6 / 1.6 to 2.5 / 2.5 or more |
| S2 | Profit factor in R | sum of winning R / sum of losing R | below 1.0 / 1.0 to 1.2 / 1.2 or more |
| S3 | Walk-forward efficiency | OOS R per year / in-sample R per year | below 25% / 25 to 50% / 50% or more |
| S4 | Selection robustness | Probability of Backtest Overfitting (PBO) by CSCV on the monthly results of every configuration tried. Also the share of splits in which the in-sample best loses money out of sample. | either above 0.5 / PBO 0.2 to 0.5 / both at most 0.2 |
| S5 | Parameter plateau | The chosen value and its two grid neighbours | any negative / all positive but more than 30% apart / all positive within 30% |
| S6 | Profit concentration | Sum R without the 5 best trades and without the 10 best; share of profit from the best year | negative without the top 5 / negative without the top 10, or one year above 50% / positive without the top 10 |
| S7 | Consistency | Share of positive months; long and short results | below 50% / 50 to 60%, or one side negative / 60% or more and both sides positive (or one-sided by design, stated before the test) |
| S8 | Return to drawdown | CAGR / max drawdown at the planned risk (MAR ratio) | below 1.0 / 1.0 to 2.0 / 2.0 or more |
| S9 | Depth and length of pain | Ulcer Index (root mean square percent drawdown) and the longest time under water, at the planned risk | above 20 or over 12 months / 10 to 20 or 6 to 12 months / at most 10 and at most 6 months |
| S10 | Cost against the stop | Mean of round-trip cost / stop distance | above 5% / 2 to 5% / at most 2% |

The S4, S5, S9 and S10 thresholds are this project's settings, not values from the literature.

## Decision

- Any of G1 to G5 fails: no real money.
- All gates pass and the score is 14 or more: incubate (G6), then trade at no more than half the Kelly fraction.
- All gates pass and the score is 10 to 13: incubate, with the weak criteria named.
- A score below 10: reject.

## Read, Do Not Score

- **Trade anatomy:** MAE and MFE per trade, exit efficiency, holding time by outcome, exit-reason mix and gap losses.
- **Loss streaks:** compare the longest streak with its expected length, about ln(n x win rate) / ln(1 / loss rate).
- **Regime tables:** by year, side, volatility, session and weekday. Use them to understand the strategy, never to pick filters. Every cut is one more trial.
- **Large rule searches:** use White's Reality Check or Hansen's SPA test in place of G2.

## Sources

- Bailey and Lopez de Prado, "The Deflated Sharpe Ratio", 2014: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
- Bailey, Borwein, Lopez de Prado and Zhu, "The Probability of Backtest Overfitting", 2017: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf
- Bailey, Borwein, Lopez de Prado and Zhu, "Pseudo-Mathematics and Financial Charlatanism" (minimum backtest length), 2014: https://www.ams.org/notices/201405/rnoti-p458.pdf
- Harvey and Liu, "Backtesting", 2015: https://www.cmegroup.com/education/files/backtesting.pdf
- White, "A Reality Check for Data Snooping", 2000, and Hansen, "A Test for Superior Predictive Ability", 2005.
- Pardo, "The Evaluation and Optimization of Trading Strategies", chapter 11 (walk-forward): https://onlinelibrary.wiley.com/doi/10.1002/9781119196969.ch11
- Davey, "Building a trading strategy: after testing and optimization" (Monte Carlo, incubation), 2014: https://kjtradingsystems.com/WhatHappensAfterOptimization.pdf
- Van Tharp, System Quality Number; Sweeney, "Maximum Adverse Excursion", 1997.
- Martin, Ulcer Index: https://www.tangotools.com/ui/ui.htm
- Bajgrowicz and Scaillet, "Technical trading revisited" (costs remove rule profits), 2012: https://ideas.repec.org/a/eee/jfinec/v106y2012i3p473-491.html

The SQN bands, Pardo's 50% efficiency line and Davey's thresholds were taken from secondary summaries, not the original books.
