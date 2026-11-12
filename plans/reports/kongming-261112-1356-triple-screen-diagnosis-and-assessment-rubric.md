# Triple Screen on gold: why it does not win, and a rubric to judge any strategy

Date: 2026-11-12. Author: kongming (model Fable 5.2). Advisory only. No code changed. No prod write. No prod backtest was launched (0 of the 6 allowed; reason in section 8).

Labels: **[V]** = verified today (computed from prod data, read in code, or read in the paper text). **[S]** = taken from a search summary or a secondary page, not read in the original. **[I]** = my inference.

Runs: frozen run `01a1c980-46bc-7400-acb1-f2f6a90c6323` (XAUUSD:EXNESS, `15m,1h,4h`, stop entry, tide-flip exit, `stop_lookback=80`, 2023-01-01..2026-11-10, 1 991 trades). "OOS" = its trades closed before 2025-11-09 (1 497). "IS" = the year that chose the config, 2025-11-09..2026-11-08 (490 trades, same as run `01a1c41f`). R = net profit of a trade divided by its planned risk (entry to stop).

## 1. Short answer

**Verdict: do not trade this config with real money, at 2% or at any other risk.** It fails every hard gate of the rubric in section 3 and scores 2 of 20. The honest status is "no edge shown", not "proven loser": one engine rule makes the out-of-sample total uncertain between -11 R and +84 R, and both ends are statistically zero.

Why we are not winning, in order of weight:

1. **"Well-known" is not "proven".** Triple Screen is a discretionary method from 1986 for weekly and daily charts. I found no published systematic test that shows a mechanical edge. The one systematic test I could open lost money with the pure rules. Academic tests of technical rules find that profits vanish after correcting for data snooping and costs, most clearly intraday (section 5.5).
2. **We trade a different system.** Ours decides on a 15-minute bar and trades 517 times a year. Elder's trading bar is daily; my sketch of his timeframes trades about 18 times a year. Our stop has no minimum distance. His 6% monthly brake is missing, and at 2% risk it would have halted trading in 33 of 47 months [V].
3. **The signal has no measurable forecast power on our data.** One hour after a long setup, price drifts +0.34 bp beyond the market average (t 1.2). After a short setup it is -0.14 bp. The round-trip cost is about 0.8 bp [V]. Out of sample, longs made +73.4 R and shorts lost -84.1 R. Gold's own drift alone gives random trades of the same holding time +71.9 R and -87.6 R [V]. The long profit is gold rising, not timing.
4. **The payoff is a coin flip with a lottery tail.** 66.5% of trades lose. The average win is 2.06 times the average loss, which needs 32.7% winners to break even. We have 33.5% (OOS 32.1%). 3.4% of trades make half of the gross profit [V].
5. **The year that chose the config was the best 12 months of the 46, and it was picked from about 110 tries.** In that year 19 of 24 variants of this interval set were positive. In the 34 months before it, 5 of 24 were [V]. The year was good for the whole family, not the config.
6. **2% risk over an uncontrolled stop builds dangerous positions.** The stop is sometimes 0.02% of price. At 2% risk, 22% of trades are larger than 10x equity and the largest is 87x [V]. The result then depends on the trades where a 15-minute backtest is least reliable.
7. **Costs are not the main cause at 15m.** Spread, commission and slippage take 0.028 R per trade, 55 R in total. Before any cost the OOS mean is still only +0.026 R (t 0.59) [V].

## 2. What the owner sees in the app, and why it misleads

The stored run shows +8.85%, PF 1.233, Sharpe 1.33, max drawdown -2.28% [V]. Three things hide the problem.

- **Size.** The engine caps each position at 10% of balance, about 0.2 to 0.5 oz. The average loss is 2.87 USD on 10 000 USD. Nothing can hurt at that size, and nothing can earn.
- **It contains the year that chose it.** Without that year the stored run made +2.70% in 2.85 years (t 1.16) [V]. Gold rose about 119% in the same period.
- **Constant size flatters this strategy.** With constant ounces, wide-stop trades carry the profit: the widest third of stops made 243 of the 270 USD out of sample [V]. With equal risk per trade, the narrow-stop trades get the big positions and they do not win.

## 3. Assessment rubric (reusable; candidate for `docs/`)

Use it on one frozen configuration. R-multiples are the unit. "OOS" means data never used to choose anything. Any failed gate means no real money.

### 3.1 Hard gates

| # | Gate | How to compute | Pass | Source |
|---|---|---|---|---|
| G1 | Honest backtest | No look-ahead. Spread, commission, slippage and swap charged. Count trades whose result depends on the unknown order of events inside one bar. | At most 2% of trades ambiguous, or they are replayed on finer bars, and the verdict is the same under the pessimistic and the optimistic fill. | Bailey et al. 2017, section 5.2: the method "does nothing to evaluate the correctness of a backtest" [V]. Project rule: `docs/governance/no-look-ahead-rules.md`. |
| G2 | Trials counted and deflated | Log every configuration tried (N). Deflated Sharpe Ratio (DSR) of the chosen run: the probability that its Sharpe beats the best Sharpe expected from N no-skill trials, corrected for skew, fat tails and sample length. | DSR at least 0.95. Shortcut: in-sample t at least 3.0. | Bailey & Lopez de Prado 2014 [V]; Harvey, Liu & Zhu 2016 [S]; Bailey et al. 2014, minimum backtest length [V]. |
| G3 | Out-of-sample edge | t = mean(R) / sd(R) x sqrt(n), on OOS trades of the frozen config. In a drifting market also subtract what the drift pays a random trade of the same side and holding time. | mean R above 0, t at least 2.0, n at least 300, and the drift-adjusted mean above 0. | Hold-out and walk-forward testing: Pardo 2008 [S]. Drift adjustment: Aronson 2006, detrending for position bias [S]. |
| G4 | Survivable at the planned risk | Bootstrap one year of trades from the OOS R list at the planned risk percent, 10 000 paths or more. Kelly fraction = the risk percent that maximises mean log growth on the OOS list. | P(drawdown of 50% or more) at most 10%, and planned risk at most half of the Kelly fraction. | Davey 2014: Monte Carlo gives the drawdown and risk of ruin that one equity curve cannot [V]; his 10% ruin limit is [S]. Kelly: betting twice the Kelly fraction gives zero growth, half keeps about 75% of the growth [S]. |
| G5 | Cost stress | Re-run or re-price at twice the modelled round-trip cost, or at the measured spread plus stop-order slippage. | OOS mean R still above 0. | Bajgrowicz & Scaillet 2012: performance "is completely offset by the introduction of low transaction costs" [V, abstract]. Neely & Weller 2003 [S]. |
| G6 | Incubation, before real money | Paper trade the frozen config for 3 to 6 months. Add the result to the backtest curve. | At least 100 trades. Realised mean R inside the backtest's bootstrap 90% band. Fill and stop mix as modelled. | Davey 2014: run it "for a period of three to six months" without trading [V]. |

Power check before any test: the smallest mean R that can reach t = 2 is 2 x sd / sqrt(n). With sd 1.7 R it is 0.18 R at 350 trades, 0.09 R at 1 500 and 0.05 R at 5 000 [V, arithmetic]. A test below that size can kill a strategy but cannot confirm it.

### 3.2 Scored criteria (0 = fail, 1 = warn, 2 = pass; 20 points)

| # | Criterion | How to compute (OOS, net) | Fail / warn / pass | Source |
|---|---|---|---|---|
| S1 | Expectancy quality | SQN-100 = 10 x mean(R) / sd(R) | below 1.6 / 1.6 to 2.5 / 2.5 or more | Van Tharp's System Quality Number; bands as reproduced on third-party pages [S]. |
| S2 | Profit factor in R | sum of winning R / sum of losing R | below 1.0 / 1.0 to 1.2 / 1.2 or more | Project gate (PF 1.2, 100 trades). A convention, not from the literature. |
| S3 | Walk-forward efficiency | OOS R per year / IS R per year | below 25% / 25 to 50% / 50% or more | Pardo 2008, chapter 11 [S]; TradeStation's optimizer grades below 50% as fail [S]. |
| S4 | Selection robustness | Probability of Backtest Overfitting (PBO) by CSCV on the monthly results of every configuration tried; also the share of splits where the in-sample best loses out of sample. | PBO or P(loss) above 0.5 / PBO 0.2 to 0.5 / both at most 0.2 | Bailey, Borwein, Lopez de Prado & Zhu 2017 [V]. The paper sets no threshold; these are ours. |
| S5 | Parameter plateau | The chosen value and its two grid neighbours | any is negative / all positive but more than 30% apart / all positive within 30% | Pardo 2008 [S, from memory of the book]. |
| S6 | Profit concentration | Sum R without the 5 best trades; share of profit from the best year | negative without the top 5 / positive without 5 but negative without 10, or one year above 50% / positive without 10 | TradeStation's optimizer: no period above 50% of net profit [S]. |
| S7 | Consistency over time and side | Share of positive months; long and short results | below 50% / 50 to 60%, or one side negative / 60% or more and both sides positive (or one-sided by design, stated before the test) | TradeStation's optimizer: at least 50% of runs profitable [S]. |
| S8 | Return to drawdown | CAGR / max drawdown at the planned risk (MAR ratio) | below 1.0 / 1.0 to 2.0 / 2.0 or more | Calmar and MAR ratios [S]; Davey's return-to-drawdown of 2 [S]. |
| S9 | Depth and length of pain | Ulcer Index (root mean squared percent drawdown) and longest time under water, at the planned risk | above 20 or over 12 months / 10 to 20 or 6 to 12 months / at most 10 and at most 6 months | Martin 1987 [V, author's page]. Thresholds are ours. |
| S10 | Cost against the stop | mean of (round-trip cost / stop distance) | above 5% / 2 to 5% / at most 2% | Sweeney 1997, stops belong outside the normal adverse move [S]; our 1m diagnosis. |

### 3.3 Decision

- A gate G1 to G5 fails: no real money. Stop, or redesign and start again with a new untouched sample.
- All gates pass and the score is 14 or more: incubate (G6), then trade at no more than half Kelly.
- All gates pass and the score is 10 to 13: incubate with the weak criteria named.
- Score below 10: reject.

### 3.4 Read but do not score

MAE and MFE per trade (Sweeney), exit efficiency, holding time by outcome, exit-reason mix, gap losses, and loss streaks against the expected longest streak, which is about ln(n x win rate) / ln(1 / loss rate). Regime tables (year, side, volatility, session, weekday) are for understanding only. Every cut is one more trial; a cell with t near 3 among 40 cells proves nothing. When a large rule universe is searched, use White's Reality Check or Hansen's SPA test in place of G2 [S].

## 4. Scorecard

| Item | OOS, 2023-01..2025-11-08 (frozen run) | IS year, 2025-11-09..2026-11-08 |
|---|---|---|
| G1 honest backtest | **Fail.** 95 of 1 497 trades (6.3%) are stops on the fill bar; 70 cannot be judged on 15m bars. The total moves from -10.9 R to +83.8 R between the two fill rules. Swap is not modelled. No look-ahead: pass (an independent replica reproduces 1 990 of 1 991 trades). | Pass after a 1m replay: 18 of the 32 fill-bar stops since 2025-10-22 were false. Total +41.5 R as stored, +59.7 R corrected. |
| G2 trials deflated | n/a (one frozen run) | **Fail.** About 110 tries. DSR 0.13 (N = 110) to 0.60 (N = 5). t = 1.28, below 3. |
| G3 out-of-sample edge | **Fail.** mean -0.007 R, t -0.16. Upper bound +0.058 R, t 1.13. Drift-adjusted: +0.003 R. | **Fail** by definition: it is the selection sample. |
| G4 survivable | **Fail** at 2%: P(drawdown 50%+ in a year) 75%; Kelly fraction 0% (upper bound 1.75%). At 0.5%: 0%, but Kelly is still 0. | **Fail** at 2% (13%). Pass at 1% (0%; Kelly 5.0%). |
| G5 cost stress | **Fail.** Spread 0.168 and 0.3 bp slippage: -0.047 R (upper bound +0.028 R). | Pass (still positive at +1.00 USD/oz, earlier report). |
| G6 incubation | Not started. The running `15m,1h,4h` paper subscription uses `stop_lookback` 5, not 80 [V]. | - |
| S1 SQN-100 | -0.04 → 0 | 0.58 → 0 |
| S2 PF in R | 0.98 → 0 | 1.22 → 2 |
| S3 walk-forward efficiency | -3.7 R/yr against +41.5 R/yr = -9% → 0 | n/a → 0 |
| S4 selection | PBO 0.20-0.26, but the in-sample best loses out of sample in 68-70% of splits → 0 | same family → 0 |
| S5 plateau | lookback 40 / 80 / 160: -43.0 / -10.9 / -9.1 R → 0 | +43.4 / +41.5 / +36.3 R → 2 |
| S6 concentration | -93.2 R without the top 5 → 0 | -4.0 R without the top 5 → 0 |
| S7 consistency | 17 of 34 months positive; shorts -84.1 R → 1 | 9 of 12 months; both sides positive → 2 |
| S8 MAR at 2% | -0.32 → 0 | 3.2 → 2 |
| S9 pain at 2% | Ulcer 64; 863 days under water, not recovered → 0 | Ulcer 11.7; 88 days → 1 |
| S10 cost / stop | 3.3% → 1 | 1.1% → 2 |
| **Score** | **2 / 20, five gates failed** | **11 / 20, two gates failed (three at 2% risk)** |

**Reading [I].** The in-sample year alone already failed G2 and G3 on 2026-11-10. The rubric would have said "get out-of-sample data before any sizing talk". The out-of-sample run then confirmed it.

## 5. Diagnosis

Engine trade list unless marked "replica". All figures [V] unless tagged.

### 5.1 Cost of losing

| Measure | Full (1 991) | OOS (1 497) | IS (490) |
|---|---|---|---|
| Losing trades | 66.5% | 67.9% | 62.2% |
| Average / median loss | -0.64 R / -0.74 R | -0.65 / -0.75 | -0.63 / -0.73 |
| 5% of losses worse than / worst | -1.05 R / -1.86 R | -1.05 / -1.86 | -1.02 / -1.03 |
| Average / median win | +1.32 R / +0.60 R | +1.35 / +0.56 | +1.26 / +0.70 |
| Win needed to break even / actual | 32.7% / 33.5% | 32.5% / 32.1% | 33.3% / 37.8% |
| Mean R (sd) | +0.015 (1.65) | -0.007 (1.71) | +0.085 (1.46) |

Loss shape (full): 580 trades are full stops near -1.0 R. 54 are worse than -1.05 R. 690 are small losses between -0.95 R and 0, closed by the tide flip. Among winners, 303 are under +0.5 R and only 68 reach +3 R.

**In money.**

| Sizing | Average loss | Median loss | Full stop | Worst trade | Average win |
|---|---|---|---|---|---|
| 2% of equity | 1.29% | 1.48% | 2.05% | 3.72% | 2.65% |
| 2% on a fixed 10 000 USD | 129 USD | 148 USD | 205 USD | 372 USD | 265 USD |
| Stored run (10% notional cap) | 2.87 USD | 2.00 USD | - | 28.87 USD | 7.03 USD |

**Frequency.** About 10 trades a week, 6.6 of them losers. 60% of days, 53% of weeks and 43% of months end down (OOS: 62%, 56%, 49%). The worst day is -9.1 R, the worst week -14.4 R and the worst month -27.6 R. One week in four is worse than -3 R, which is -6% at 2% risk.

**Losing streaks.** The longest is 17 trades. With a 66.5% loss rate and independent trades the expected longest is 16.8 (95th percentile 22), so 17 is normal, not bad luck. A run of 5 or more losses comes 24 times a year, 8 or more 7 times a year, 10 or more happened 10 times. The deepest run of consecutive losses cost -10.3 R (about -19% at 2%). Losses do not cluster more than chance (runs test z = +0.8).

**Drawdown.**

| Sizing, full window | Max drawdown | Peak → trough | Recovered | Days under water | Ulcer Index | Worst day | Days below -5% |
|---|---|---|---|---|---|---|---|
| 2% compounding | -91.9% | 2023-06-28 → 2025-12-11 (897 days) | No, 334 days later | 96% | 71 | -16.1% (2023-10-12) | 94 |
| 1% | -67.6% | same | No | 96% | 46 | -8.3% | 11 |
| 0.5% | -41.1% | same | No | 96% | 25 | -4.3% | 0 |
| Stored run | -2.3% | 2023-06-08 → 2024-04-22 (318 days) | 2024-07-19 | 96% | 0.8 | - | 0 |
| IS year only, 2% | -27.8% | 2026-08-19 → 2026-09-01 | 2026-11-05 | 92% | 12 | -13.3% | 16 |

- In R, the drawdown is -98.7 R over 1 321 trades. At a fixed 200 USD risk that is -19 740 USD, twice the account.
- At 2%, 7 of 47 months lost more than 20% and 13 lost more than 10%. The worst month is -42.9% (2023-08).
- One-year bootstrap of the OOS trades: P(drawdown of 50%+) is 75% at 2%, 14% at 1% and 0% at 0.5%. P(the year ends in loss) is 69%, 63% and 59%.
- **Elder's own brake.** His 6% monthly rule on top of 2% risk stops trading in 33 of 47 months and takes only 780 of the 1 991 trades. The result is 10 649 USD with a -62% drawdown. At 43 trades a month, three losses use up the month. The 2% rule was written for a system that trades a few times a month [I].

### 5.2 Where the money goes

| R units | Gross profit | Gross loss | Net | Costs inside | Before costs |
|---|---|---|---|---|---|
| Full | +882.3 | -851.7 | +30.6 | 55.4 (spread 22.2, commission 19.4, slippage 13.8) | +85.9 (t 1.17) |
| OOS | +648.4 | -659.0 | -10.7 | 49.9 | +39.3 (t 0.59) |
| IS | +233.7 | -192.2 | +41.5 | 5.4 | +46.9 (t 1.45) |

- **Cost per trade:** 0.20 USD/oz at the median. That is 0.028 R, 2.1% of the average win and 6.3% of gross profit. Against the stop distance it is 1.6% at the median, 2.8% on average, and above 6.3% for one trade in ten.
- **Stored sizing, USD:** gross profit 4 689, gross loss -3 804, net 885, costs 154.
- **Concentration:** the best 5 trades make +82.5 R; the other 1 986 make -52.0 R. 67 trades (3.4%) make half of the gross profit and 211 (10.6%) make 80%. The 68 trades of +3 R or more total +445.6 R; all the rest total -415 R.
- **Stop size.** The stop is the extreme of the last 80 bars. When price is already at that extreme, the stop is one bar away. The median distance is 13 USD, one in ten is under 3.1 USD, and the smallest are 0.5 USD. At 2% risk the median position is 4.1x equity, 435 trades (22%) exceed 10x, 10 exceed 50x and the largest is 87x. A move of 0.25% past the stop costs 5.4% of equity on the 95th-percentile trade and 21.8% on the largest.

### 5.3 Trade anatomy

- **Exit mix.** 631 stop-outs (31.7%) lose -645.9 R, -1.02 R each. 1 360 tide-flip exits make +676.5 R: 667 winners at +1.32 R and 693 losers at -0.30 R.
- **Time.** Losers last 3.0 hours at the median, winners 18.0 hours, and +3 R winners 42 hours. Trades closed within 12 hours (1 385, 70%) lose -620 R. Trades held longer (606) make +650 R. 300 stop-outs (48% of them) come within one hour of entry.
- **How far trades went (MFE, MAE).** 48% of all trades were up +0.5 R at some point, 31% up +1 R, 15% up +2 R. Among losers, 32% had been up +0.5 R and 16% up +1 R; 27% never reached +0.1 R. Winners went 0.27 R against us at the median; a quarter went 0.5 R against; 19 came within 0.1 R of the stop.
- **Exit efficiency.** Winners keep 55% of their best open profit. Trades that reached +2 R peaked at +4.77 R on average and closed at +2.04 R.
- **Would another exit fix it? No.** These checks use hindsight and are optimistic, and out of sample they are still negative: a fixed target of 0.5 to 8 R gives -11 to -40 R; moving the stop to entry after +1 R gives -20.7 R against -10.7 R; a tighter stop is worse. The exit is not the leak [I].
- **Stops on the fill bar.** 125 trades (6.3%; one stop-out in five) cost -129.6 R. The engine counts the whole fill bar against the stop. 32 of them are certain (the bar opened past the entry, or closed past the stop). 93 cannot be judged on 15m bars. Prod has 1m bars only since 2025-10-21. On those, 14 of 32 fill-bar stops were real and 18 were not (the stop level was touched only before the entry).
- **Losses beyond -1 R.** 54 trades are worse than -1.05 R; all are stop-outs; 33 are in 2023 and none in 2026. In 51 of them the stop was hit inside the bar and the excess is cost on a tiny stop (0.5 to 3 USD, where cost is 10% to 35% of the risk). Two opened just past the stop. One is a weekend gap.
- **The -1.86 R trade.** A short entered on Friday 2025-03-28 14:15 at 3080.03 with the stop at 3086.86, 6.83 away. Friday closed at 3085.17, 1.7 USD under the stop. Sunday 22:00 opened at 3092.55, a gap of +7.4 USD (+0.24%), already past the stop. It filled at 3092.67. The position was 9x equity at 2% risk, so it cost 3.72%. 162 positions were carried through a weekend or holiday gap; this is the only one gapped through its stop. Gaps in the data: median 0.09%, one in ten above 0.49%, largest 2.00% (2026-02-01).

### 5.4 Regimes

| Cut | Result (sum R, t) | Reading |
|---|---|---|
| Year | 2023 +32.8 (0.70); 2024 +7.5 (0.19); 2025 -49.2 (-1.82); 2026 +39.4 (1.32) | No year is significant. |
| Rolling 500 trades (about a year) | 42% of windows positive; median -13.5 R; the IS year is the best window | The development year was the luckiest. |
| Side, OOS | Long +73.4 (1.87); short -84.1 (-1.58) | Equal to gold's drift: +71.9 and -87.6 R expected for random trades of the same side and holding time. Drift-adjusted: +1.5 and +3.5 R. |
| Side, IS | Long +17.7; short +23.8 | Gold was flat that year (+1.3%), so drift explains nothing there. |
| With / against the 20-day trend | +31.0 (0.68) / -5.7 (-0.10) | No separation. |
| Daily ADX(14): below 20 / 20-25 / 25-35 / above 35 | -27.7 / -6.6 / +36.5 / +9.7; every t under 1 | No "trend against range" effect. The 20-day efficiency ratio shows none either. |
| Daily ATR as % of price: low / mid / high third | -103.3 (-2.73) / +83.1 (1.63) / +51.5 (1.39) | The only cut that holds under both fill rules: the strategy loses in quiet markets. The IS year had ATR 2.3% against 1.1% to 1.5% before. |
| Session of entry (UTC) | Asia +64.0 (1.36); London -20.9; New York -10.8; late New York -1.8 | Not significant. |
| Weekday | Tuesday -59.5 (-2.41), and -75.9 (-4.93) out of sample, but +16.4 in the IS year | Flips sign. Noise among many cuts; a cell with no big winner also shows a small sd and an inflated t. |
| Months | 27 of 47 positive; OOS 17 of 34; worst -27.6 R, best +30.3 R | Half the months lose. |

"Held over a weekend" shows +254 R (t 6.2). It is not a rule: long holding time is the result of winning, not a cause.

**What the screens add (replica, constant size, costs included).** Following the first screen alone, always in the market with the 4h MACD-histogram slope, makes +43.4% of notional out of sample (t 1.63). The full three screens make +26.9% (t 1.17). Gold itself rose about 119%. The second and third screens remove profit; they add none [V]. A circular-shift test on bar positions, before costs, gives p = 0.035 out of sample with constant size and p = 0.19 with equal-risk size. That is a faint timing effect that does not survive costs or the 2% sizing [I].

### 5.5 Why "proven and well-known" does not transfer

**Our implementation against Elder's rules** (canon as summarised in `kongming-261110-1218-triple-screen-canonical-gap.md` [S]; our code [V]: `src/pocketquant/core/domain/strategy/services/triple_screen_strategy_service.py`).

| Point | Elder | Ours | Effect measured today |
|---|---|---|---|
| Trading bar | Daily, with a weekly tide; a 5-minute chart is the shortest example | 15-minute entry bar, 1h oscillator, 4h tide | 517 trades a year against about 18 in my daily/weekly sketch |
| Entry trigger | Break of the previous trading (middle) bar | Break of the 15m entry bar, re-sent every bar (`:121-127`, `:142-147`) | The oscillator bar and the trigger bar differ by 4x |
| Stop | Beyond the last two trading bars | Extreme of 80 entry bars, no minimum (`:124`, `:128`, `:130`) | Stops from 0.5 USD; positions up to 87x equity at 2% |
| Money rules | 2% per trade and 6% per month | 2% (planned), no monthly brake | The brake would halt 33 of 47 months |
| Judgment | Discretionary; systems are "monitored and adjusted using individual judgment" [S] | Fully mechanical | Not measurable |

Sketches of the canonical rules on the same data (my replica; unreviewed; 15m execution; each one more trial):

| Sketch | OOS | IS year |
|---|---|---|
| 1h trading bar, 4h tide, tide-flip exit (the earlier lead, PF 1.48 in sample) | -44 R (t -0.51); 0 R with the optimistic fill | +96 R (t 1.48) |
| Daily trading bar, weekly tide (the book's timeframes) | +5.6 R on 50 trades (t 0.29) | +5.7 R on 18 trades |
| 4h trading bar, daily tide | +82 R (t 0.96); -62 R without the top 5 | +16 R |

The 1h/4h lead does not hold before its own year. The daily version trades too rarely to judge: 69 trades in 46 months.

**What evidence exists for Triple Screen.**

- **No peer-reviewed systematic test** was found (searches of 2026-11-10 and today) [V, absence].
- **QuanterLab, S&P 500 stocks, 2006-2025, daily bars, no costs** [V, page read]: the pure Triple Screen turned 1 USD into 0.86 USD with a -75% drawdown. No variant beat the equal-weight index (4.26 USD). The volume and trend screens did not help. The site is not peer-reviewed.
- **QuantifiedStrategies** has a backtest page that I could not open. A search snippet says its version earns less than buy and hold and has faded lately [S, unverified].
- The belief rests on books and courses, which report no trade lists.

**What systematic research says about rules of this kind.**

- Bajgrowicz & Scaillet 2012, 7 846 rules on the Dow, 1897-2011: an investor "would never have been able to select ex ante the future best-performing rules", and low costs remove the profit even in sample [V, abstract].
- Aronson 2006: of 6 402 rules on the S&P 500, none is significant after the data-mining correction [S].
- Intraday: a study of 5-minute gold futures in Shanghai, 2018-2021, finds nothing that holds out of sample and calls the predictability illusory; Neely & Weller find no intraday FX profit after realistic costs [S].
- Publication decay: 97 published stock predictors earn 26% less out of sample and 58% less after publication (McLean & Pontiff 2016) [S, abstract]. Triple Screen has been public for 40 years.
- Backtest against live: for 888 Quantopian algorithms the backtest Sharpe explains under 2.5% of live results, and more backtesting means a larger shortfall (Wiecki et al. 2016) [S]. For 215 bank strategies the median live Sharpe is 73% below the backtest (Suhonen et al. 2017) [S].
- Where trend evidence is strong: 1 to 12 month lookbacks on a basket of dozens of futures (Moskowitz, Ooi & Pedersen 2012; Hurst, Ooi & Pedersen 2017) [S]. That is months and many markets, not 15 minutes and one market.

**Selection on our side.** With 110 no-skill trials the best one is expected to show t = 2.56 [V, formula of Bailey & Lopez de Prado]. The chosen run shows t = 2.49 with stored sizing and 1.28 in R. The minimum-backtest-length theorem says that with five years of data no more than 45 independent configurations should be tried [V, paper text]. We tried about 110 on one year.

### 5.6 The engine rule that blurs the answer

A stop entry that fills inside a bar is counted as stopped out if that same bar's range touches the stop level, whatever the order was (`src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py:608-618`) [V].

| Fill-bar rule (replica) | OOS mean R (t) | OOS sum R | Full sum R | 10 000 USD at 2%, full window |
|---|---|---|---|---|
| Engine rule (pessimistic) | -0.007 (-0.16) | -10.9 | +30.3 | 6 875, drawdown -92% |
| Ambiguous stops survive (upper bound) | +0.058 (1.13) | +83.8 | +143.2 | 55 388, drawdown -73% |
| Upper bound, spread 0.168 and 0.3 bp slippage | +0.028 (0.55) | +40.6 | +94.9 | - |

- In the IS year the 1m replay equals the upper bound (+59.7 R).
- The whole gap sits in tiny-stop trades. For trades with a stop of at least a quarter of the daily ATR (about 975 of the OOS trades), the two rules agree: +0.008 R and +0.022 R per trade [V].
- With a real spread of 0.17 to 0.30, a stop 0.5 to 3 USD from entry would rarely survive live [I]. So the upper bound is too kind for 2023-2025.
- Even the upper bound fails the gates: t 1.13, a -73% drawdown at 2%, and a Kelly fraction of 1.75%, below 2%.

## 6. Next experiments

Ranked by decision value per unit of cost.

| # | Experiment | Cost | How it changes the decision |
|---|---|---|---|
| 0 | **Decide now:** no live trading of this config. Keep it paper-only. | None | Removes the 2% / 1:500 question for this strategy. |
| 1 | **Replay the 95 OOS fill-bar stops on 1m bars.** Needs 1m XAUUSD bars for 2023-01..2025-10. Try `scripts/backfill/provider_bars.py --interval 1m --dry-run` first; whether Exness serves 1m that far back is unverified. | One backfill of about 1.0M bars (check VPS disk first), then a 10-minute offline replay. No code change. | Fixes the OOS mean inside -0.007 to +0.058 R. At +0.03 R or less: archive the 15m Triple Screen for good. At +0.05 R or more: it still fails G3, but a redesign with a minimum stop earns one pre-registered test. |
| 2 | **Paper-incubate the frozen config.** The running paper subscription uses `stop_lookback` 5. Add one with 80, or accept that paper is testing another config. Owner decision. | No compute; 3 months. | It cannot prove the edge: t = 2 at +0.085 R needs about 1 500 trades, three years. It measures real fill-bar stops, entry spread and stop-order slippage, the inputs to G1 and G5 for every later backtest. |
| 3 | **Engine: fill resting stops and stops/targets on 1m bars inside the entry bar; add a minimum stop distance.** Needs a plan and owner approval. | About 1 to 2 days of code and tests; depends on the data from 1. | Makes G1 passable for every stop-entry strategy on bars of 15m or longer. Without it each such backtest carries an unknown bias; here it is worth up to 95 R. |
| 4 | **Benchmark and a literature-backed baseline:** on prod daily bars (gold since 2019-03), score "hold gold" and one fixed daily trend rule with the rubric. Offline. | About 1 to 2 hours. No prod load. | Sets the bar a gold strategy must beat: about +121% for holding gold in this window. If no timing rule beats it per unit of drawdown, change the goal from "time gold intraday" to "manage a long gold position" or "several markets". |
| 5 | **Change the hypothesis, not the parameters:** a slow trend rule over several uncorrelated markets, daily bars, few parameters. Needs multi-market history and swap modelling. | A plan; data import; days of work. | The only direction here with decades of published out-of-sample support. It can meet G2 and G3 by design. Swap becomes a first-order cost. |

**Not recommended [I].** More parameter or interval sweeps of Triple Screen on gold. About 142 configurations have been tried and none has an out-of-sample t of 2. The last untouched gold window, 15m bars 2022-05..2022-12, holds about 350 trades and can only confirm an edge above 0.18 R. Keep it for one pre-registered kill test.

## 7. What to avoid

- **Do not turn the long/short split into a long-only rule.** The long profit equals gold's drift. A long-only variant is a diluted "hold gold".
- **Do not filter by the regime tables** (skip Tuesdays, trade only high volatility). Each is a pattern found after the fact.
- **Do not trust the stored run's PF 1.23 or its -2.3% drawdown.** The size is one twenty-fifth of a 2% position and the window contains the selection year.
- **Do not size from the in-sample year.** Its Kelly fraction is 5.0%. Out of sample it is 0%.
- **Do not read a low PBO as "the strategy is good".** PBO ranks configurations against each other. Here the in-sample best beats the median out of sample and still loses money in 70% of splits.
- **Do not judge a stop-entry backtest on 15m or longer bars** before counting its fill-bar stops.

## 8. Method, limits and trial count

- **Data.** `.cache/oos/pull.txt` (trades, equity, 15m bars). Read-only prod pulls today: run metrics, 1h/4h/1d/1w bars, December 2022 15m bars for warm-up, 1m bars for 32 fill bars, and the paper subscriptions. My SSH key copy and the VPS `/tmp` files are removed.
- **Replica.** `.cache/km2/sim.py` re-implements the strategy and the paper broker on 15m bars. It reads only higher-timeframe bars that closed before the entry bar's start. It reproduces 1 990 of 1 991 engine trades to 1e-6 (the first trade differs by a warm-up window). That is why no prod backtest was needed: every variant a prod run could give is computed offline with zero VPS load.
- **Not reviewed.** The replica variants, the canonical sketches and the 1m replay are my own scripts. The canonical sketches are approximations of Elder's rules.
- **Trials.** About 110 before today. Today adds 32 strategy variants on the replica (5 lookbacks, market entry, long-only, short-only, tide-only, 6 canonical sketches, 17 grid cells) and about 20 hindsight re-pricings of the fixed trade list. Total about 142 configurations. None may be picked as a new candidate from this report.
- **DSR.** The cross-trial variance is replaced by the sampling variance of the chosen run under no skill. That is kind to the strategy. With the variance of the 50 stored sweep Sharpes, as the paper defines it, the DSR is under 0.2 even for N = 5.
- **PBO.** 24 configurations of one interval set, 46 months, 12 blocks, 924 splits. The paper asks for many more than 10 configurations; 24 is thin.
- **Risk of ruin.** The bootstrap treats trades as independent (the runs test supports that) and cannot produce a gap larger than the sample holds. The true tail is worse [I].
- **Not modelled.** Swap, spread widening at rollover and news, requotes, and the Exness account terms. The spread is the owner's 0.08; the measured median is 0.168.

## 9. Assumptions

| Assumption | Confidence | What would change the answer |
|---|---|---|
| The 2023-01..2025-11-08 trades are a fair out-of-sample test of the frozen config. | High: nothing was tuned on them before the run. | - |
| The truth for fill-bar stops lies between the two rules. | High | 1m bars for 2023-2025 (experiment 1). |
| Secondary summaries carry Elder's rules and the cited papers correctly. | Medium to high where several agree; lower for Davey's book thresholds, Tharp's bands and Pardo's 50%. | The book texts. |
| Rubric thresholds marked "ours" are reasonable defaults. | Medium | Owner preference; they are settings, not facts. |
| The owner's 2% stays the target. | Given | With an edge near +0.10 R proven out of sample, 2% would be about half Kelly. With today's evidence it is above full Kelly in every scenario. |

## 10. Unresolved questions

1. Owner: archive the 15m Triple Screen now, or first spend experiment 1 to fix the fill-bar uncertainty? Recommended: run experiment 1 only if 1m history is cheap to get; otherwise archive.
2. Owner: is the 2% risk a fixed requirement? If yes, a strategy needs about +0.10 R per trade proven out of sample before G4 can pass. If not, 0.5% is the ceiling this evidence allows, and only on paper.
3. Does the Exness history endpoint serve 1m bars back to 2023? Not checked.
4. Should the paper subscription move to `stop_lookback` 80, or stay at 5? They are different configs; neither has out-of-sample support.
5. Should section 3 move to `docs/`? A new file under `docs/` needs the owner's yes (documentation rules).
6. Real Exness terms (swap, stop-out, minimum lot, gold margin schedule) are still unverified, as in the earlier report.

## Sources

Read today in the original text [V]:

- Bailey & Lopez de Prado, "The Deflated Sharpe Ratio", Journal of Portfolio Management 2014: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
- Bailey, Borwein, Lopez de Prado & Zhu, "The Probability of Backtest Overfitting", Journal of Computational Finance 2017: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf
- Bailey, Borwein, Lopez de Prado & Zhu, "Pseudo-Mathematics and Financial Charlatanism", Notices of the AMS 2014 (preprint read): https://carmamaths.org/jon/backtest.pdf ; journal copy: https://www.ams.org/notices/201405/rnoti-p458.pdf
- Davey, "Building a trading strategy: after testing and optimization", Futures, October 2014: https://kjtradingsystems.com/WhatHappensAfterOptimization.pdf
- Martin, Ulcer Index and Ulcer Performance Index (author's page): https://www.tangotools.com/ui/ui.htm
- Bajgrowicz & Scaillet, "Technical trading revisited", Journal of Financial Economics 2012 (abstract): https://ideas.repec.org/a/eee/jfinec/v106y2012i3p473-491.html
- QuanterLab, "Elder's Triple Screen taken apart": https://quanterlab.com/research/elder-s-triple-screen-taken-apart-twenty-years-on-the-s-p-500-as-it-stood

From search summaries or secondary pages [S]:

- Harvey, Liu & Zhu, "... and the Cross-Section of Expected Returns", Review of Financial Studies 2016: https://academic.oup.com/rfs/article/29/1/5/1843824
- Harvey & Liu, "Backtesting", Journal of Portfolio Management 2015: https://www.cmegroup.com/education/files/backtesting.pdf
- White, "A Reality Check for Data Snooping", Econometrica 2000: https://www.researchgate.net/publication/2551052_A_Reality_Check_For_Data_Snooping ; Hansen, "A Test for Superior Predictive Ability", 2005: https://www.researchgate.net/publication/4724332_A_Test_for_Superior_Predictive_Ability
- Pardo, "The Evaluation and Optimization of Trading Strategies", chapter 11: https://onlinelibrary.wiley.com/doi/10.1002/9781119196969.ch11 ; TradeStation Walk-Forward Optimizer criteria: https://help.tradestation.com/09_01/tswfo/topics/walkforward_test_results.htm
- Davey, "Building Winning Algorithmic Trading Systems", chapter 7: https://onlinelibrary.wiley.com/doi/10.1002/9781118778944.ch7 ; review with thresholds: https://tradermarkus.com/kevin-j-davey-building-winning-algorithmic-trading-systems-review/
- Van Tharp, System Quality Number, bands as reproduced: https://www.pineconnector.com/blogs/pico-blog/system-quality-number-sqn ; https://strategyquant.com/forum/topic/3112-sqn-system-quality-number-error-calculation/
- Sweeney, "Maximum Adverse Excursion", Wiley 1997: https://www.wiley.com/en-us/Maximum+Adverse+Excursion:+Analyzing+Price+Fluctuations+for+Trading+Management-p-x000030303
- Calmar and MAR ratios: https://tradingwyckoff.com/en/algorithmic-trading/drawdown-trading-guide/
- Kelly sizing, fractional Kelly: https://matthewdowney.github.io/uncertainty-kelly-criterion-optimal-bet-size.html ; https://ryanoconnellfinance.com/kelly-criterion/
- Aronson, "Evidence-Based Technical Analysis", chapter review: https://www.cxoadvisory.com/technical-trading/evidence-based-technical-analysis-applying-the-scientific-method-and-statistical-inference-to-trading-signals-chapter-by-chapter-review/
- McLean & Pontiff, "Does Academic Research Destroy Stock Return Predictability?", Journal of Finance 2016: https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12365
- Wiecki, Campbell, Lent & Stauth, "All That Glitters Is Not Gold", Journal of Investing 2016: https://www.pm-research.com/content/iijinvest/25/3/69
- Suhonen, Lennkh & Perez, "Quantifying Backtest Overfitting in Alternative Beta Strategies", Journal of Portfolio Management 2017: https://jpm.pm-research.com/content/43/2/90
- Neely & Weller, "Intraday technical trading in the foreign exchange market", 2003: https://www.sciencedirect.com/science/article/abs/pii/S0261560602001018
- "Performance of intraday technical trading in China's gold market", 2021: https://www.sciencedirect.com/science/article/abs/pii/S1042443121001876
- Park & Irwin, "What do we know about the profitability of technical analysis?", 2007: https://ideas.repec.org/a/bla/jecsur/v21y2007i4p786-826.html
- Moskowitz, Ooi & Pedersen, "Time series momentum", 2012: https://www.trendfollowing.com/resources/time-series-momentum/ ; Hurst, Ooi & Pedersen, "A Century of Evidence on Trend-Following Investing", 2017: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2993026
- Elder's Triple Screen, origin and money rules: https://blog.bullsmart.in/elders-triple-screen-system-time-frame-trade/ ; QuantifiedStrategies page (not opened): https://www.quantifiedstrategies.com/alexander-elder-triple-screen-strategy/

Scratch: `.cache/km2/` (gitignored): `common.py`, `sim.py`, `d1.py` to `d6.py`, `sim2.py` to `sim6.py`, `fb.py`, `trials.py` and their `.txt` outputs.
