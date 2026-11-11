# Gold timeframe and edge: where trend-following earns on XAUUSD:EXNESS

Date: 2026-11-10. Advisory only. No code changed, no backtest started, no prod write.
Runtime: kongming on Fable 5.2. Angle: market and timeframe, not strategy code.

## TL;DR

- The brief's premise is wrong in this data. Gold did not rise over the window. It opened at 4004.90 and closed at 4055.47 (+1.26%). It rose 39% to 5563 on 2026-01-29 and then fell 30% to 3876 on 2026-10-30. Long PF equal to short PF is what a symmetric system shows on a round trip. It says nothing about the strategy by itself.
- Returns in this window look like a random walk at every horizon from 1m to 1d (lag-1 autocorrelation within about 2 standard errors of zero, variance ratios 0.95-1.02 up to 1h). A trend edge, where one exists, is small per bar. It can be collected only when the move per trade is large against the 0.24 USD cost.
- A 1m signal timeframe is not viable for trend-following at these costs. Seven generic trend rules on 1m bars have gross PF 0.99-1.14 and six of seven lose after cost. The same rules on 5m-1h bars mostly stay positive after cost. Use 1m only to time an order for a trade whose stop and hold belong to an hourly or slower timeframe.
- Cheapest next step: rerun the three older Triple Screen sets at the current 0.1 bp slippage on the same window. The `15m,1h,4h` stop/strategy run had PF 1.118 at 0.5 bp slippage and is the only run near the gate.

## Reframed problem

The owner asks why valid strategies do not win. The decision behind it is which timeframe and strategy family to spend the next plan on. A strategy can be logically valid and still have no edge at the horizon it trades. The horizon of a trade is set by its stop distance and its exit, not by the slowest interval it reads.

## Measured facts (prod bars, read-only, 2026-11-10)

Source: `bars`, `XAUUSD:EXNESS`, 2025-11-09 to 2026-11-08, bid prices. Raw output: `D:/w/_me/algotrading/pocketquant/.cache/mk_out.txt` (not committed). Cost used: 0.238 USD per oz per round trip (spread 0.08, commission 0.07, slippage 0.1 bp per side at 4400). The alternative 0.326 uses the measured spread 0.168.

### The window

| Fact | Value |
|---|---|
| First open / last close | 4004.90 / 4055.47, +50.57 USD, +1.26% |
| High | 5595.35 on 2026-01-29 |
| Low | 3869.96 on 2026-10-30 |
| Largest drawdown (1h closes) | -30.3%, 5563 to 3876, not recovered inside the window |
| Month-end closes | 4222, 4319, 4892, 5279, 4696, 4626, 4540, 4006, 4044, 4452, 4156, 3876, 4055 |
| Daily stats | 312 days, up days 49.8%, annualized volatility 26.6%, net change / sum of absolute daily changes 0.003 |

### Autocorrelation, variance ratio and cost by timeframe

`rho1` is the lag-1 autocorrelation of log returns. `se` is 1/sqrt(n). VR(q) is the variance of a q-bar return over q times the one-bar variance; 1.0 is a random walk, above 1 trends, below 1 reverts.

| Interval | Bars | rho1 (se) | VR2 | VR4 | VR8 | VR16 | Median range, USD | Cost / median range | Cost at 0.168 spread / median range |
|---|---|---|---|---|---|---|---|---|---|
| 1m | 352 298 | +0.0035 (0.0017) | 1.002 | 0.991 | 0.983 | 0.974 | 1.97 | 12.1% | 16.6% |
| 5m | 70 599 | +0.0069 (0.0038) | 1.007 | 1.009 | 1.021 | 1.013 | 4.56 | 5.2% | 7.2% |
| 15m | 23 539 | -0.0019 (0.0066) | 1.004 | 1.002 | 0.983 | 0.938 | 8.02 | 3.0% | 4.1% |
| 1h | 5 889 | -0.0221 (0.0136) | 0.999 | 0.951 | 0.950 | 1.016 | 16.63 | 1.4% | 2.0% |
| 4h | 1 593 | +0.0089 (0.0251) | 1.009 | 1.017 | 1.100 | 1.005 | 33.60 | 0.7% | 1.0% |
| 1d | 312 | +0.0090 (0.0568) | 1.008 | 0.849 | 0.802 | 0.739 | 82.04 | 0.3% | 0.4% |

- No interval shows a lag-1 autocorrelation beyond about 2 standard errors. I did not compute standard errors for the variance ratios.
- The daily VR16 of 0.74 points to reversion at a 2-3 week scale in this window. With 312 days this is weak evidence.
- Mean return per 1m bar is 0.0006 standard deviations. Up-bar share is 49.97%.

### Generic trend rules by timeframe (benchmark, not a strategy proposal)

Each rule is always long or short, fills at the bar close on bid, and pays 0.238 per position. Donchian N: long above the prior N-bar high, short below the prior N-bar low. SMA N: long above the average, short below. TSMOM N: sign of the N-bar change. Figures are USD per oz over the window. This is my own calculation, not the engine.

| Interval | Rule | Positions | Gross | Long / short gross | Gross PF | Net PF | Net PF at 0.326 |
|---|---|---|---|---|---|---|---|
| 1m | Donchian 20 | 8 124 | -247 | -99 / -148 | 0.993 | 0.936 | 0.917 |
| 1m | Donchian 55 | 3 354 | +63 | +56 / +7 | 1.003 | 0.967 | 0.954 |
| 1m | Donchian 200 | 1 010 | +1559 | +804 / +755 | 1.139 | 1.116 | 1.107 |
| 1m | SMA 50 | 26 846 | +969 | +509 / +460 | 1.023 | 0.886 | 0.843 |
| 1m | SMA 200 | 12 970 | +1032 | +541 / +492 | 1.043 | 0.923 | 0.884 |
| 1m | TSMOM 20 | 37 160 | +327 | +188 / +139 | 1.006 | 0.862 | 0.817 |
| 1m | TSMOM 100 | 16 668 | +1606 | +827 / +778 | 1.053 | 0.929 | 0.888 |
| 5m | Donchian 20 / 55 / 200 | 1609 / 671 / 190 | +921 / +1084 / +1039 | near equal | 1.063 / 1.112 / 1.213 | 1.036 / 1.095 / 1.203 | 1.026 / 1.088 / 1.199 |
| 5m | SMA 50 / 200 | 5428 / 2430 | +1297 / +1690 | near equal | 1.067 / 1.159 | 1.000 / 1.100 | 0.977 / 1.079 |
| 5m | TSMOM 20 / 100 | 7456 / 3127 | +1351 / +1580 | near equal | 1.054 / 1.120 | 0.984 / 1.061 | 0.959 / 1.040 |
| 15m | Donchian 20 / 55 / 200 | 553 / 188 / 69 | +310 / +2378 / -419 | near equal | 1.033 / 1.586 / 0.884 | 1.019 / 1.571 / 0.880 | 1.014 / 1.566 / 0.878 |
| 15m | SMA 50 / 200 | 1649 / 880 | +1575 / +169 | near equal | 1.145 / 1.025 | 1.106 / 0.994 | 1.092 / 0.983 |
| 15m | TSMOM 20 / 100 | 2493 / 1128 | +1120 / +1164 | near equal | 1.076 / 1.148 | 1.035 / 1.111 | 1.020 / 1.098 |
| 1h | Donchian 20 / 55 / 200 | 112 / 53 / 14 | +1486 / +368 / -538 | near equal | 1.392 / 1.139 / 0.692 | 1.383 / 1.134 / 0.691 | 1.380 / 1.132 / 0.690 |
| 1h | SMA 50 / 200 | 460 / 169 | +176 / +233 | near equal | 1.028 / 1.076 | 1.010 / 1.062 | 1.004 / 1.057 |
| 1h | TSMOM 20 / 100 | 611 / 264 | +1231 / +1118 | near equal | 1.176 / 1.292 | 1.153 / 1.273 | 1.144 / 1.265 |
| 4h | Donchian 20 / 55 / 200 | 36 / 12 / 4 | -21 / -1 / +1164 | near equal | 0.989 / 0.999 / 33.2 | 0.984 / 0.997 / 33.0 | 0.982 / 0.996 / 32.9 |
| 4h | SMA 50 / 200 | 97 / 45 | +898 / +757 | near equal | 1.426 / 1.540 | 1.412 / 1.529 | 1.407 / 1.525 |
| 4h | TSMOM 20 / 100 | 179 / 53 | -133 / +964 | near equal | 0.971 / 1.664 | 0.962 / 1.652 | 0.959 / 1.647 |
| 1d | Donchian 20 / 55 / 200 | 4 / 4 / 2 | +1305 / -167 / -316 | near equal | 9.67 / 0.655 / 0.0 | 9.65 / 0.653 / 0.0 | same |
| 1d | SMA 50 / 200 | 10 / 8 | +1603 / +499 | 823 / 780, 272 / 228 | 5.85 / 2.32 | 5.83 / 2.31 | same |
| 1d | TSMOM 20 / 100 | 23 / 11 | +235 / +651 | near equal | 1.133 / 2.679 | 1.130 / 2.666 | same |

Readings that are fact:

- Net positive rules at 0.238: 1m 1 of 7, 5m 5 of 7, 15m 5 of 7, 1h 7 of 7, 4h 4 of 7, 1d 5 of 7.
- On 1m the gross gain per position is 0.04-0.10 USD for six rules, against a cost of 0.238. The one 1m rule that survives uses a 200-bar (3.3 hour) lookback and trades 1010 times.
- Long and short gross are near equal for every rule at every interval. The window, not the rule, produces that symmetry.
- 4h and 1d rules have 2-97 positions. One window cannot rank them.
- Buy and hold earned +50.57 USD per oz (+1.26%) with a 30% drawdown. The daily SMA 50 rule earned +1600 with 10 positions. Ten positions is an anecdote, not an estimate.

These are 42 looks at one window with no significance test. Read the pattern across intervals. Do not pick a winner from the table.

### Range and drift by UTC hour

| Hours UTC | Median 1h range, USD | Median 1m range, USD | Cost / 1m range |
|---|---|---|---|
| 13-15 (New York open) | 23.5-27.0 | 2.74-3.25 | 7-9% |
| 01 (Asia open) | 24.4 | 2.78 | 9% |
| 00, 02, 12, 16 | 17.4-20.7 | 2.12-2.28 | 10-11% |
| 03-11, 17-19 | 11.2-18.3 | 1.39-2.00 | 12-17% |
| 20-23 | 11.0-13.8 | 1.24-1.57 | 15-19% |

- Sum of close minus open of 1h bars: Asia 00-07 +32, London 07-13 +335, New York 13-21 -1322, late 21-24 +448, gaps between bars +558.
- Session return correlation over 257 days: Asia to London -0.156, London to New York -0.094. The standard error is about 0.062. I treat neither as a tradable finding.

### Stored backtests by direction and holding time

| Run | Long PF / short PF | Median hold, min | Trades |
|---|---|---|---|
| ts 1m,5m,15m market/sl_tp, 0.1 bp | 0.819 / 0.868 | 2 / 1 | 36 847 |
| ts 1m,5m,15m stop/strategy, 0.1 bp | 0.852 / 0.919 | 3 / 3 | 14 943 |
| ts 1m,15m,1h market/sl_tp, 0.1 bp | 0.821 / 0.846 | 2 / 2 | 27 265 |
| ts 1m,15m,1h stop/strategy, 0.1 bp | 0.821 / 0.801 | 5 / 4 | 7 798 |
| ts 5m,15m,1h market/sl_tp, 0.5 bp | 0.743 / 0.764 | 5 / 5 | 8 608 |
| ts 5m,15m,1h stop/strategy, 0.5 bp | 0.740 / 0.756 | 15 / 15 | 3 662 |
| ts 15m,1h,4h market/sl_tp, 0.5 bp | 0.902 / 0.889 | 30 / 30 | 2 487 |
| ts 15m,1h,4h stop/strategy, 0.5 bp | 1.175 / 1.063 | 60 / 60 | 941 |
| ts 1h,4h,1d market/sl_tp, 0.5 bp | 0.826 / 0.777 | 120 / 60 | 705 |
| ts 1h,4h,1d stop/strategy, 0.5 bp | 0.624 / 0.748 | 300 / 240 | 276 |

- The last six rows are the "raw-spread costs" runs of 2026-11-07 (`backtest_runs` names). Their overall PF: 0.754, 0.748, 0.895, 1.118, 0.803, 0.676. I did not read their date range; I assume it is the Phase 16 range 2025-11-03 to 2026-10-30.
- The Phase 16 report (`D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation/reports/phase-16-backtests-and-paper-start.md`) lists the first version of those runs with PF 0.79, 0.78, 0.93, 1.14, 0.81, 0.69 under the older cost model. That plan directory is under `plans/`, not `plans/archive/`.
- Triple Screen is not better the slower it gets. The `1h,4h,1d` set is the worst of the three older sets.

## Sourced facts

- Time-series momentum: the past 12-month excess return of a futures contract predicts its next-month return, in all 58 contracts studied, including gold. Lookbacks tested are 1, 3 and 12 months. [Moskowitz, Ooi, Pedersen 2012](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf).
- A 1, 3 and 12 month trend portfolio across 67 markets from 1880 to 2016 had a Sharpe ratio of 0.76 after fees and costs. [Hurst, Ooi, Pedersen](https://www.pm-research.com/content/iijpormgmt/44/1/15), summary at [Alpha Architect](https://alphaarchitect.com/time-series-momentum-aka-trend-following-the-historical-evidence/). This is a diversified portfolio result. Neither paper claims a single-market edge of that size.
- Markets trend on horizons from a few hours to a few years and revert on shorter and longer ones, on 14 years of futures tick data and longer daily and monthly series. [Safari and Schmidhuber, arXiv 2501.16772](https://arxiv.org/abs/2501.16772).
- Short-term trend-following has stopped delivering reliable returns since about 2009 across about 100 futures; the break is tied to tick size relative to volatility. [Kurth, Eisler, Rej, Bouchaud, arXiv 2607.01550](https://arxiv.org/abs/2607.01550). I read the abstract only.
- Cost rule of thumb: spend at most one third of the expected pre-cost Sharpe ratio on costs. Cost per trade in Sharpe units is the cost as a percent of price divided by annualized volatility. [Carver, "How fast should we trade?"](https://qoppac.blogspot.com/2020/04/how-fast-should-we-trade.html).
- A simulated minutes-scale bracket strategy showed double-digit Sharpe ratios that depended on fill assumptions; the same-bar stop/target order flipped it from +8 to -9, and the author's live attempt failed. [Carver, scalping post](https://qoppac.blogspot.com/2025/05/can-i-build-scalping-bot-blogpost-with.html).
- Gold volatility and volume peak at the Tokyo, London and New York opens, highest at New York. [Watkins, Kobe University](https://www.econ.kobe-u.ac.jp/wp-content/uploads/2023/06/1722.pdf).
- Intraday momentum (opening half-hour predicts the closing half-hour) is documented for equity ETFs and reported with mixed patterns for gold ETFs and Chinese gold futures. [Commodity ETF study](https://pmc.ncbi.nlm.nih.gov/articles/PMC7480318/), [Chinese gold and silver futures](https://www.sciencedirect.com/science/article/abs/pii/S1044028325000110). I found no test on spot gold CFDs.
- Exness gold costs from third-party measurements: Raw Spread about 0.09 spread plus 7 USD per lot round turn; Pro about 0.18 spread, no commission. [copi-tools](https://copi-tools.com/blog/xauusd-spread-comparison/). No official Exness page was found. The Pro figure matches the 0.168 the seed comment records for the prod account (`D:/w/_me/algotrading/pocketquant/scripts/seed_exness_symbols.py:32-35`).
- Not found: a published 1m or 5m return autocorrelation for gold, and a peer-reviewed retail backtest of a gold CFD trend strategy. The [precious metals stylized-facts paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC5407636/) would not load.

## Inference (mine, labelled)

1. Carver's rule applied here. One fill costs 0.119 USD, 0.0027% of price. Divided by 26.6% volatility that is 0.0001 Sharpe units per fill, 0.0002 per round trip. With an expected Sharpe of 0.4 the budget is 0.13, about 650 round trips a year. Run r1 makes 36 847, about 57 times the budget. The `15m,1h,4h` stop run makes 941, about 1.4 times. The `1h,4h,1d` stop run makes 276. The rule assumes a full-size position held all the time, so these are rough.
2. Why long PF equals short PF. First, the window is a round trip, so a symmetric system has no net drift to lean on. Second, even in a year that rises 40%, drift over a 2-minute hold is about 0.01 USD against a 0.24 cost and a 2 USD bar range. A system that holds for minutes cannot collect a yearly trend in any year. Both points hold together; the first is enough for this window.
3. The slowest interval Triple Screen reads does not make it a slow system. With a 5-bar stop on the entry interval, the 1m sets hold 1-5 minutes and the `15m,1h,4h` set holds 60 minutes. The trade lives on the entry interval.
4. The 1m rows of the generic table and the bid-to-bid PF of the Triple Screen 1m runs (0.89-1.01) agree: gross edge on 1m is about zero. This matches the sourced claim that trends start at a few hours.
5. The 2026-11-07 `15m,1h,4h` stop/strategy run paid 0.5 bp slippage. At 0.1 bp it saves about 0.35 USD per oz per trade against a mean gain near 1 USD. I expect its PF to rise toward 1.2 on rerun. It is one result picked from at least twelve runs on one window, so a pass is not proof of edge.

## What to do

1. Rerun the three older Triple Screen sets at the current default slippage on the six-run window (2025-11-09 to 2026-11-08), both `entry_type`/`exit_mode` pairs. Six runs, 20-270 s each by the Phase 16 timings. Parameters only.
2. On the `15m,1h,4h` and `5m,15m,1h` sets, rerun with `stop_lookback` 20 and 60 and `risk_reward` 2.0 and 3.0. This widens the stop from a 5-bar extreme and lengthens the hold. It tests inference 3 without code.
3. Run `1h,4h,1d` on an older window as an out-of-sample check. Stored 1h bars start 2023-10-31, 4h 2023-09-01, 1d 2019-03-25. Check 1h coverage with the Phase 16 Task 16.1 rule first. The 15m and 5m sets cannot do this: their bars start 2025-10-21.
4. Report every run with PF at spread 0.08 and at 0.168 (send `spread` in the request). The 1m sets are the most sensitive to it; the hourly sets barely move.
5. Decide the next plan from those runs. Recommended default: stop spending on 1m signal sets, and keep 1m only as an order-timing step if a slower set passes.
6. Before any multi-day hold goes live, check the Exness swap on gold for this account. The paper broker charges no financing that I could find by grep (`swap` appears only in `exness_broker_adapter.py` and `backtest_report_app_service.py`); I did not read those files.

## What to avoid

- Do not explain the six failures by "gold trended and we missed it". The window did not trend net.
- Do not adopt a generic rule from the benchmark table. It is 42 looks at one window.
- Do not treat one passing rerun as an edge. Ask for a second window or a parameter neighbourhood that also passes.
- Do not trade the session drift (New York -1322, late +448). It is one year and matches only blog-level sources.
- Do not lower spread or slippage to pass the gate. The measured account spread is 0.168, twice the seeded value.
- Do not judge a strategy's horizon by its top interval. Read the median hold and stop distance.

## Alternatives and trade-offs

| Option | Gain | Cost |
|---|---|---|
| Hourly Triple Screen with wider stops (recommended first) | No code; 200-1000 trades a year gives a readable sample; cost is 1-3% of a bar | One strategy family; `1h,4h,1d` already lost on this window |
| A plain daily or 4h trend rule (Donchian or moving average, wide stop) | The family with the strongest published evidence; cost is negligible | Needs new strategy code and a multi-year test; 2-25 trades a year means years to judge; swap cost unverified; single-market trend has long flat periods |
| Keep refining 1m sets | Many trades, fast feedback | Gross edge measured at about zero; costs are 12-17% of a bar; fill-order assumptions dominate the result |

## Work checklist

- [ ] Six reruns of `5m,15m,1h`, `15m,1h,4h`, `1h,4h,1d` at 0.1 bp on the six-run window.
- [ ] `stop_lookback` and `risk_reward` variants on the two faster sets.
- [ ] `1h,4h,1d` on 2023-11 to 2025-11 after a coverage check.
- [ ] Each result at spread 0.08 and 0.168; record long PF, short PF and median hold.
- [ ] Owner decision on the next plan's timeframe.
- [ ] Exness gold swap check before any hold longer than a day.

## Success metrics

- A set passes the gate (net PF at or above 1.2, at least 100 trades) at spread 0.168 on the main window.
- The same set and parameters have PF above 1.0 on a second window.
- Neighbouring parameter values do not flip the result below 1.0.
- If no set meets the first line, that is the answer: Triple Screen has no measurable edge on gold at any tested interval, and the next plan is a different family.

## Assumptions

| Assumption | Confidence | What would change it |
|---|---|---|
| The stored bars are correct Exness bid prices for the window. | High | A vendor comparison. The price path past mid-2026 is outside what I can check from memory. |
| Round-trip cost is 0.238 USD (0.326 at the measured spread). | Medium | Real fills. Slippage is unmeasured. |
| The 2026-11-07 runs used the Phase 16 date range. | Medium | Their `config_snapshot`. |
| Close-to-close fills in my benchmark are a fair gross estimate. | Medium | An engine run of the same rule. The 1m rows are the most optimistic because they ignore intrabar stops. |
| One 12-month window is representative. | Low | A second window. The window holds one large rise and one large fall, which favours slow trend rules. |
| No swap is charged in backtests. | Medium | Reading the two files the grep found. |

## Unresolved

1. Which spread is right, 0.08 or 0.168? Recommended default: gate on 0.168 because it was measured on this account.
2. Does the owner accept a slower family (tens of trades a year) if the hourly sets fail? Recommended default: yes, as a multi-year backtest only, before any paper run.
3. Is the Exness gold swap zero on this account? Unverified.
4. The variance ratios have no standard errors; the daily reversion reading is untested.

## Cleanup

My key `.cache/ssh/vps_key_mk`, `.cache/mk_q.py` and `/tmp/mk_q.py` on the VPS and in the `api` container are removed (both remote listings print 0). `.cache/mk_out.txt` stays as the raw output; it holds no secret.
