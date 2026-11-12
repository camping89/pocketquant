# Triple Screen: higher-timeframe SL/TP lookbacks, the entry offset X, and a pre-registered sweep

Date: 2026-11-12. Author: kongming (model Fable 5.2). Advisory only. No code in `src/` changed. No prod access of any kind in this session: every input was already in `.cache/` from the earlier pulls.

Labels: **[V]** = verified today (read in code, or computed from the local data). **[S]** = from a search summary or a secondary page, not read in the original. **[I]** = my inference.

Base data: XAUUSD:EXNESS 15m bars 2022-12-12..2026-11-11, 1h and 4h bars from 2022-05-01, costs as in the frozen run (spread 0.08, commission 3 bp, slippage 0.1 bp). The replica reproduces 1 990 of 1 991 trades of run `01a1c980` [V].

## 1. Short answer

- **Name of X.** The usual names are "breakout filter" or "penetration filter" (books), "entry buffer" or "breakout buffer" (practitioners), and "one tick above the high" (Elder). For our code I recommend `entry_offset_atr`: a multiple of the same ATR(14) on the top interval that `min_stop_atr` uses. I read the owner's X as an offset on the stop **entry**, not on the stop loss (section 2).
- **Design.** `stoploss_lookback` and `takeprofit_lookback` count middle-interval bars. Each is applied to the last `lookback x (middle / entry)` closed entry bars. TP is the farther of the swing level and `risk_reward x risk`, only under `exit_mode=sl_tp` (section 3).
- **Min stop.** The pre-registered rule picks `min_stop_atr = 0.5`. It cuts trades that 15m bars cannot judge from 4.7% to 1.1%, and the largest 2% position from 87x to 17.9x equity [V].
- **Sweep.** 77 configurations were run under a rule written down first (section 4). One configuration passes that rule: `stoploss_lookback=10, takeprofit_lookback=10, entry_offset_atr=0.1, min_stop_atr=0.5, exit_mode=sl_tp, risk_reward=1.0`. On the walk-forward test folds (2024-01..2026-11, 570 trades) it makes +0.148 R per trade, t 2.77, and the two fill bounds agree [V].
- **Verdict: no variant passes every gate.** The candidate fails G2 by the letter (Deflated Sharpe 0.71 to 0.88 at 219 trials, needs 0.95). None of the three new parameters passes its own fold test. The replica's SL/TP path has never been compared with the engine, swap is not charged, and the data are not untouched. It is the first config in this project with an out-of-sample t above 2, and it earns one frozen engine run and paper incubation. It does not earn real money.
- **Fakeout claim.** An offset of 0.10 ATR lowers stop-outs within one hour only a little (7.7% to 7.1% of trades at the base config). The minimum stop is what removes them (15.1% to 7.7%) [V].
- **Trial count:** about 221 (142 + 3 + 74 + 2 post-hoc). The 2022 holdout is untouched.

## 2. The term for X

| Term | Where it is used | Unit usually given |
|---|---|---|
| Breakout filter, penetration filter ("point or percent filter", "volatility filter") | Technical-analysis textbooks: price must clear the level by a set zone before the break counts [S] | Points, percent of price (the stock "3% rule"; 1 to 2% variants), or a multiple of ATR |
| Entry buffer, breakout buffer, volatility-adjusted buffer | Practitioner guides; one worked example uses 0.10 ATR over a 20-bar high [S] | Fraction of ATR |
| "One tick above the high", trailing buy-stop | Elder's third screen: the buy stop sits one tick above the previous bar's high and is lowered each bar until filled or the signal ends [S] | One tick |
| Entry offset | Common parameter name in trading code [I] | Ticks, price, or ATR fraction |

- **Recommended name: `entry_offset_atr`.** It says what it moves (the entry) and its unit, and it matches `min_stop_atr`. Gold's ATR(14, 4h) median went from 8.2 USD in 2023 to 37.2 USD in 2026 [V], so a fixed tick or USD value would mean a different thing each year. Percent of price is the second choice.
- **Same idea on the stop loss.** It exists and is called a stop buffer or stop cushion: the SL goes beyond the swing by a tick (Elder: "one tick below the low of the trade day or the previous day, whichever is lower" [V, quoted on a forum copy]) or by 0.1 to 1.0 ATR (vendor guides, no evidence given [S]). For a long the sign is minus (swing low - buffer).
- **My reading.** The owner wrote "long = stop + X, short = stop - X" and "taking position right in stop price". The sign fits the stop-entry price, not the stop loss. Confidence: high. `min_stop_atr` already does the stop-loss side of the job, so I add no SL buffer.
- **Question to confirm:** "X moves the entry order only (buy stop = bar high + X). The stop loss gets no extra buffer, because the minimum stop already keeps it away. Correct?"

## 3. Parameter design

### 3.1 Facts the design rests on [V]

- The strategy reads higher-timeframe bars that closed before the **start** of the entry bar (`strategy_app_service.py`, `_context_at`, the instant is the bar's start). At the 10:45 bar the newest 1h bar in context is 09:00-10:00. Up to four entry bars, the signal bar included, are newer than the context.
- `no-look-ahead-rules.md` allows a partial higher-timeframe value only when the strategy builds it from closed lower-timeframe bars.
- Unknown parameter keys are rejected when a subscription or backtest is submitted (`core/domain/strategy/services/__init__.py:50-52`). The strategy itself reads keys with `p.get(...)`, so an old key in a stored document is ignored without an error (`triple_screen_strategy_service.py:46`).
- A default typed `int` rejects a float value (`_type_matches`, `services/__init__.py:19-24`). `min_stop_atr` and `entry_offset_atr` must default to `0.0`, not `0`.
- The web form is generic: it renders the `DEFAULTS` the API returns (`strategy_query_service.py:41`, `web/src/components/controls/params-editor.tsx`). No test and no doc mentions `stop_lookback` (grep).
- Stored data: 47 of 67 backtest runs carry `stop_lookback` (pull of 14:10 today). No paper subscription carries it (pull of 14:32 today); they run on the default 5.

### 3.2 Definitions

Let `ratio = seconds(middle) / seconds(entry)` (4 for `15m,1h,4h`), `ATR` = Wilder ATR(14) on closed top-interval bars, and `high`, `low` the entry bar just closed.

| Step | Long | Short |
|---|---|---|
| 1. Entry (stop order) | `high + entry_offset_atr x ATR` | `low - entry_offset_atr x ATR` |
| 2. Swing stop | lowest low of the last `stoploss_lookback x ratio` closed entry bars | highest high of the same bars |
| 3. Minimum stop | `sl = min(swing, entry - min_stop_atr x ATR)` | `sl = max(swing, entry + min_stop_atr x ATR)` |
| 4. Risk | `entry - sl` | `sl - entry` |
| 5. TP, only when `exit_mode=sl_tp` | `max(highest high of the last takeprofit_lookback x ratio bars, entry + risk_reward x risk)` | `min(lowest low of those bars, entry - risk_reward x risk)` |

- **Which bars.** The window is the last `N x ratio` closed entry bars, signal bar included. It covers exactly N middle bars of time and uses no context bar. Closed middle bars alone are wrong for a swing stop: they miss up to four newer entry bars, so a fresh low would sit below the stop. A bucket-aligned version (N closed middle bars plus the partial one) gives the same levels except at bucket edges and costs more code [I].
- **TP already at or behind the entry.** It happens: across the grid the swing level is at or behind the entry on 1 to 19% of trades and under 1 R away on 17 to 82% (section 5.5). The `risk_reward` floor in step 5 removes the special case. No trade is skipped, and `takeprofit_lookback=0` gives today's TP exactly.
- **`exit_mode`.** `sl_tp`: the TP of step 5. `strategy`: no TP, the tide flip exits, and `takeprofit_lookback` is ignored. I tested a third mix (TP plus tide flip) and it is worse than either; do not add it.
- **Defaults.** `min_stop_atr=0.0`, `entry_offset_atr=0.0`, `takeprofit_lookback=0` keep today's behavior. `stoploss_lookback` cannot: today's default is 5 entry bars, which is 1.25 middle bars. Recommended default: 2 (Elder's two trading bars). The running paper subscriptions then change from 5 to 8 entry bars of lookback. Owner decision (section 9).
- **KISS check.** One deque sized to the larger of the two windows; one ATR with two callers. No new class or helper file.

### 3.3 Against Elder's rule [S]

| Point | Elder | This design |
|---|---|---|
| Entry | One tick beyond the previous bar of the trading timeframe, trailed each bar | Offset beyond the entry-interval bar, in ATR; trailed each bar (already so) |
| Stop | One tick beyond the extreme of the trade bar and the bar before | Extreme of N middle bars, floored by a minimum distance. `stoploss_lookback=2` is the nearest match. At that value 83% of stops are set by the 0.5 ATR floor, not by the swing [V] |
| Target | None fixed; exit by judgment or opposite signal | Swing level or R multiple, or the tide flip |

### 3.4 Rename and stored parameters

- **Code:** five lines in `triple_screen_strategy_service.py` (`:32, :46, :59, :62, :67`). Add tests; none exist for the old name.
- **Values change meaning:** entry bars become middle bars. 80 becomes 20, 40 becomes 10, 20 becomes 5. The old 10 and 5 have no exact new value.
- **Backtest runs:** leave the 47 stored runs alone. They record what ran. The form marks the old key as "not declared by the strategy". A re-run with the old key fails loudly as an unknown parameter, which is the right outcome.
- **Subscriptions:** before the release, count subscriptions whose parameters hold `stop_lookback`. Today the count is 0, so there is nothing to migrate. If it is not 0: `mongodump` the `subscriptions` collection first, then rename the key and divide the value by the ratio in one reviewed update. Keep no alias for the old key in code (CLAUDE.md: never deprecate and keep).

## 4. Sweep design (written to `.cache/km3/prereg.md` before any result)

- **Stage A, minimum stop (3 trials).** L=20, X=0, tide exit, m in {0.25, 0.5, 1.0}; m=0 is the frozen config. Rule: the smallest m with at most 2% of trades undecidable on the fill bar. Profit is not a criterion.
- **Stage B, grid at the chosen m (75 configs, 74 new).** `stoploss_lookback` L in {2, 5, 10, 20, 40} x offset X in {0, 0.10, 0.25} ATR x exit in {tide flip; sl_tp with P=10; sl_tp with P=40; TP plus tide flip with P=10; the same with P=40}. TP floor 1.0 R.
- **Walk-forward.** Anchored. Train from 2023-01-01 to the fold start. Six test folds by entry time: 2024-H1, 2024-H2, 2025-H1, 2025-H2, 2026-H1, 2026-07-01..2026-11-10. In each train window pick the config with the highest t of R under the pessimistic bound; price it in the test fold under both bounds.
- **Fill bounds.** Pessimistic = the engine rule. Optimistic = an undecidable fill-bar stop survives, and TP wins when SL and TP fall in one later bar.
- **Decision rule, a set.** Concatenated test folds: mean R above 0 and t at least 2.0 (pessimistic), same sign under the optimistic bound, PBO at most 0.5, the in-sample best loses out of sample in at most 50% of CSCV splits, and at 2% risk P(drawdown of 50% in a year) at most 10% with Kelly at least 4%.
- **Decision rule, one parameter.** Its paired difference against the baseline value (X=0, tide exit, L=20), over matched cells, is positive in at least 5 of 6 test folds under both bounds.
- **Fakeout claim.** Holds only if the share of stop-outs within one hour falls and mean R does not fall.
- **Deflation.** DSR of the best config with N = every trial so far (219). PBO by CSCV on monthly R, 46 months, 12 blocks.
- **Untouched.** 15m 2022-05..2022-12. No bar before 2022-12-12 was loaded.
- **Does the sweep need 1m fills first? No.** With the minimum stop, 1.1 to 2.3% of trades are undecidable and every figure is given under both bounds. 1m fills are needed for the one confirming engine run, not for the sweep [V for the shares, I for the conclusion].
- **Weakness I accept.** The window 2023-01..2026-11 was already used by about 142 earlier trials, and I designed the grid after diagnosing these same bars. The test folds are out of sample for this selection only.

## 5. Results

All [V], replica, costs included. R is the net result over the distance from the actual fill to the stop.

### 5.1 Stage A: minimum stop (L=20, X=0, tide exit, 2023-01..2026-11-10)

| `min_stop_atr` | Trades | Undecidable | Sum R, pess / opt | Stops widened | Stop USD: median / 1 in 10 under / smallest | Position at 2%, x equity: median / 1 in 10 over / largest | Over 10x | Stop-outs within 1 h (of trades) | P(DD 50% in a year), pess / opt | Kelly, pess / opt |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 (frozen) | 1 991 | 4.7% | +30.3 / +143.2 | 0% | 13.1 / 3.1 / 0.53 | 4.1 / 15.7 / 87.1 | 21.8% | 300 (15.1%) | 61% / 35% | 0.6% / 2.8% |
| 0.25 | 1 952 | 2.9% | +56.2 / +139.3 | 8.9% | 13.5 / 3.3 / 1.13 | 4.0 / 14.3 / 34.2 | 19.5% | 258 (13.2%) | 48% / 30% | 1.2% / 3.0% |
| **0.5** | 1 836 | **1.1%** | +95.2 / +109.1 | 22.8% | 15.8 / 4.7 / 2.17 | 3.6 / 9.6 / 17.9 | 8.6% | 141 (7.7%) | 19% / 17% | 3.1% / 3.5% |
| 1.0 | 1 703 | 0.2% | +48.0 / +48.9 | 44.7% | 19.1 / 7.9 / 4.33 | 2.9 / 5.2 / 9.0 | 0% | 57 (3.3%) | 8% / 7% | 2.9% / 3.0% |

- **The rule picks 0.5.** It is the smallest value under 2% undecidable. The gap between the fill bounds shrinks from 113 R to 14 R.
- With the minimum stop alone, no value reaches t 2 (best: 0.5, t 1.57 pessimistic), and Kelly stays below 4%. The minimum stop fixes the measurement and the position size. It does not create an edge.

### 5.2 Walk-forward (m = 0.5)

Every fold picked the same config: L=10, X=0.10, sl_tp, P=10.

| Test fold | Train t of the pick | Test n | Mean R, pess / opt | t, pess / opt | Sum R, pess / opt | Base (L=20, X=0, tide) sum R, pess | Configs positive, pess |
|---|---|---|---|---|---|---|---|
| 2024-H1 | 1.82 | 43 | +0.310 / +0.310 | 1.69 / 1.69 | +13.3 / +13.3 | +19.5 | 39 of 75 |
| 2024-H2 | 2.31 | 114 | +0.155 / +0.166 | 1.25 / 1.32 | +17.7 / +18.7 | +18.9 | 41 |
| 2025-H1 | 2.62 | 122 | +0.397 / +0.416 | 3.25 / 3.35 | +48.4 / +50.4 | +6.2 | 73 |
| 2025-H2 | 3.89 | 130 | -0.084 / -0.077 | -0.81 / -0.73 | -11.0 / -10.0 | -25.5 | 4 |
| 2026-H1 | 3.19 | 75 | +0.085 / +0.085 | 0.60 / 0.60 | +6.4 / +6.4 | +19.2 | 60 |
| 2026-07..11 | 3.22 | 86 | +0.112 / +0.112 | 0.83 / 0.83 | +9.7 / +9.7 | +25.8 | 70 |

| Concatenated test folds, 2024-01..2026-11 | n | Mean R (t), pess | Mean R (t), opt | Long / short sum R, pess | At 2%: max drawdown | P(DD 50% in a year) | Kelly | Longest under water |
|---|---|---|---|---|---|---|---|---|
| Walk-forward pick | 570 | +0.148 (2.77) | +0.156 (2.90) | +73.9 / +10.6 | -38% | 0% | 10.0% | 406 days |
| Base: min stop only | 1 331 | +0.048 (1.36) | +0.058 (1.60) | +75.3 / -11.2 | -55% | 14% (opt 11%) | 3.4% (opt 4.0%) | 626 days |
| Frozen, no min stop | 1 451 | -0.002 (-0.05) | +0.065 (1.38) | +59.8 / -62.5 | -84% | 60% (opt 31%) | 0% (opt 2.7%) | 832 days |

### 5.3 The candidate under scrutiny (L=10, X=0.10, sl_tp, P=10, m=0.5)

- **Shape.** 745 trades in 46 months (193 a year). 50.2% win. TP exits average +1.34 R and stop-outs -1.02 R. Median hold 14 hours, mean 38 hours; 18% of trades cross a weekend.
- **By year, pessimistic:** 2023 +36.8 R (t 1.82); 2024 +31.0 (1.91); 2025 +37.4 (1.82); 2026 +16.0 (1.02). No single year is significant.
- **Concentration.** The 2025-H1 fold gives 48.4 of the 84.5 R. Without it: +0.081 R, t 1.37. Without the 10 best trades the test folds still make +44.6 R.
- **Old selection year (2025-11-09 on):** +0.065 R, t 0.73. The earlier "good year" is this config's weakest stretch.
- **Neighbours (full window, pessimistic mean R):** X 0 / 0.10 / 0.25 = +0.094 / +0.163 / +0.041. L 5 / 10 / 20 = +0.009 / +0.163 / +0.196. P 10 / 40 = +0.163 / +0.160. All positive, far from flat. X=0.10 is a peak, not a plateau.
- **Cost stress (spread 0.168, slippage 0.3 bp):** test folds +0.148 R, t 2.76. Costs are 1.2% of the stop.
- **Placebo.** I shifted the signals in time against the prices (200 shifts, all 75 configs each). This keeps the exits, the side mix and gold's drift, and removes any link between signal and price. The best of 75 placebo configs reaches t 3.32 in 1% of shifts; its usual value is 1.23. The candidate minus its own placebo is +0.152 R per trade. The base config also beats its placebo (p 0.003). So the signal carries information on this data. It is the kind a trend filter carries in a market that rose 120%, and the test cannot say it will last [I].
- **Deflated Sharpe.** t 3.32 on the full window. With N = 219 the DSR is 0.71 to 0.88 (pessimistic) and 0.80 to 0.93 (optimistic), under 0.95. The DSR formula treats the 219 trials as independent and expects a best t of 2.80; the placebo shows the 75 correlated configs give 1.23. The DSR is therefore strict here, and the placebo covers only today's 75, not the earlier 142 [I].
- **PBO** 0.25 (optimistic 0.32). The in-sample best loses money out of sample in 18% of splits (13%).
- **Gap risk.** The worst trade is -6.09 R: a short entered on Friday 2023-10-06 with a 3.68 USD stop, opened 22 USD higher on Sunday. At 2% that is -12.2% of equity in one trade. Positions reach 13x equity in the test folds.
- **Post-hoc, 2 extra trials.** The same config with a plain 1 R target and no TP lookback: +0.073 R, t 2.04. With a plain 2 R target: +0.127 R, t 1.68. The swing-level TP adds profit through 85 trades that exit at +2.5 R on average. This was not pre-registered; read it as a hint.

### 5.4 Single parameters (paired, over the six test folds)

| Change | Folds positive, pess / opt | Matched cells positive, pess | Passes (needs 5 of 6) |
|---|---|---|---|
| X = 0.10 against 0 | 4 / 4 | 6 of 25 | No |
| X = 0.25 against 0 | 1 / 1 | 3 of 25 | No |
| sl_tp, P=10 against tide exit | 2 / 2 | 2 of 15 | No |
| sl_tp, P=40 against tide exit | 2 / 2 | 4 of 15 | No |
| TP plus tide flip, P=10 / P=40 | 3 / 3 | 6 and 0 of 15 | No |
| L = 10 against 20 | 4 / 4 | 14 of 15 | No |
| L = 2 or 5 against 20 | 3 / 3 | 13 and 11 of 15 | No |
| L = 40 against 20 | 3 / 3 | 4 of 15 | No |

- The tide-flip exit has the largest total R in the grid (mean +78 R per config against +39 R for sl_tp P=10), because it trades twice as often. sl_tp has the higher R per trade.
- The whole grid: 67 of 75 configs are positive (75 of 75 optimistic), median t 0.86, 4 configs at t 2 or more, 1 at t 3 or more.

### 5.5 Requested measurements

- **TP level invalid.** The swing level is at or behind the entry on 4 to 7% of sl_tp trades at X=0 (1 to 5% with the tide exit kept), and 7.7% for the candidate. It is less than 1 R away on 33% of trades at L=2, 43% at L=5 and 64 to 70% at L=10 or more with P=10; 21% to 68% with P=40. For the candidate, 67.7% of targets are the 1 R floor and 289 of 374 TP exits happened there.
- **Stop distance and size.** See 5.1. In the candidate the median stop is 19.7 USD (1.25 ATR), and the position at 2% is 2.6x equity at the median, 7.1x for one trade in ten, 13.3x at most (test folds).
- **Fakeouts.** Base config with m=0.5, stop-outs within one hour as a share of trades: X=0 7.7% (141 of 1 836), X=0.10 7.1% (112 of 1 587), X=0.25 6.4% (59 of 917). Mean R: +0.052, +0.044, +0.022. The share falls and so does mean R, so the claim fails at the base config. Averaged over the grid, X=0.10 raises mean R (+0.036 to +0.051) and X=0.25 lowers it (+0.025) while removing half the trades. Evidence for a small offset is mixed; for a large one it is negative.

### 5.6 Rubric view of the candidate (test folds, 2% risk)

| Item | Result | Reading |
|---|---|---|
| G1 honest backtest | 1.2% undecidable; both bounds agree. Swap not charged; SL/TP path of the replica not checked against the engine | Open |
| G2 trials deflated | DSR 0.71 to 0.93 at N = 219; quick check t 3.32 passes; placebo p 0.01 | **Fail by the DSR number** |
| G3 out-of-sample edge | +0.148 R, t 2.77, n 570, placebo-adjusted +0.152 R | Pass on walk-forward folds, not on untouched data |
| G4 survivable | P(DD 50%) 0%; Kelly 10%, so 2% is under half Kelly | Pass |
| G5 cost stress | +0.148 R | Pass |
| G6 incubation | Not started | Open |
| S1 to S10 | SQN-100 1.16 (0); PF 1.29 (2); walk-forward efficiency 80% (2); PBO 0.25 (1); plateau (1); concentration (2); 69% positive months, both sides positive (2); MAR 1.98 (1); Ulcer 15.4, 406 days under water (0); cost 1.2% of the stop (2) | 13 of 20 |

## 6. Verdict and what the plan should change

1. **No variant passes the gates.** State it this way to the owner. One candidate is frozen for testing; nothing is cleared for real money.
2. **Implement the parameters as designed in section 3**, all in phase 3, defaults off: rename to `stoploss_lookback`, add `takeprofit_lookback`, `entry_offset_atr`, `min_stop_atr`. This is the owner's request and the candidate needs all four. Rename the phase to match.
3. **Phase 4 runs, pre-registered, engine with 1m fills, 2024-05-01..2026-11-10 23:59 UTC.** All three are engine copies of configs already counted, so the trial count stays at about 221.
   - **A:** `stoploss_lookback=20`, `exit_mode=strategy`, stop entry (the frozen config). Replica on this window: 1 285 trades, +17.0 R pessimistic, +109.5 R optimistic.
   - **B:** A plus `min_stop_atr=0.5`. Replica: 1 168 trades, +82.6 / +94.8 R.
   - **C:** `stoploss_lookback=10, takeprofit_lookback=10, entry_offset_atr=0.1, min_stop_atr=0.5, exit_mode=sl_tp, risk_reward=1.0`, stop entry. Replica: 552 trades, +77.7 / +81.7 R, t 2.58 / 2.71.
   - **Check before reading any profit:** the engine's trade list for C must match `.cache/km3/candidate_trades.csv` on a window without 1m bars. A mismatch means my SL/TP replica is wrong and section 5 must be redone.
4. **Rule for C, fixed now.** C is dropped if the engine run with 1m fills gives a mean R at or below 0, or a t below 1.5, on 2024-05..2026-11. If it survives, it goes to paper incubation (G6) as the frozen config. No neighbour of C is run.
5. **2022 holdout.** Keep it for C, after step 4, as a kill test only: about 128 trades can confirm nothing below +0.24 R. Drop C if the holdout mean R is at or below 0.
6. **Honest horizon.** At 193 trades a year and sd 1.34 R, new data reach t 2 for a +0.15 R edge after about 320 trades, 20 months. Paper incubation of 3 to 6 months checks fills and behavior, not the edge.
7. **Swap.** C holds 38 hours on average. Model swap, or measure it in paper, before any sizing talk. It is a non-goal of the current plan; say so in the plan's risk list.
8. **`min_stop_atr`: 0.5.** Fork for the owner: 1.0 caps positions at 9x equity and makes the fill bounds equal, at the cost of widening 45% of stops. The rule said 0.5; I keep it. Evidence that would flip it: a paper or live stop slipping more than 0.25 R on stops under 5 USD.

## 7. What to avoid

- Do not tune around the candidate (X=0.08, L=12, another floor). Each step is a new trial on used data, and X=0.10 is already a peak.
- Do not adopt `entry_offset_atr=0.25`, the TP-plus-tide-flip mix, or `stoploss_lookback=40`: they are worse in most folds.
- Do not read "+0.148 R, Kelly 10%" as a licence for 2%. The -6 R gap trade exists, positions reach 13x equity, and 406 days under water appear at 2%.
- Do not keep an alias for `stop_lookback`.
- Do not use closed middle bars from the context for the swing stop.

## 8. Method, limits and trial count

- **Scripts** (gitignored scratch): `.cache/km3/prereg.md`, `sim_mtf.py` (replica with the new rules), `sweep.py` and `sweep.txt`, `check.py` and `check.txt`, `reality.py` and `reality.txt` (placebo), `final.py`, `candidate_trades.csv`.
- **Replica check.** With all new parameters off it gives the same 1 991 trades and +30.3 / +143.2 R as before. The TP path follows `paper_broker_adapter.py` `_check_sl_tp` (open past the TP fills at the open; SL before TP inside a bar; no TP on the fill bar). It is unreviewed and unverified against the engine.
- **Window.** The lookback window is a rolling count of entry bars. Weekend gaps make it span more clock time.
- **Bootstrap** treats trades as independent and cannot draw a gap worse than the sample holds.
- **Not modelled:** swap, spread widening, requotes, Exness terms.
- **Trials:** 142 before; 3 for the minimum stop; 74 new grid configs; 2 post-hoc. Total about 221. The placebo shifts are not configurations.
- **Web sources** are search summaries except Elder's stop rule, which I read on a forum copy. One textbook page could not be opened.

## 9. Assumptions

| Assumption | Confidence | What would change the answer |
|---|---|---|
| X is an offset on the stop entry, not on the stop loss. | High | The owner says it is the SL: then the sign flips and `min_stop_atr` covers most of it. |
| "Lookback of one higher timeframe" means the middle interval, counted in its bars. | High | The owner means the top interval: multiply by the 4h ratio instead; the grid values shift. |
| A rolling window of entry bars is an acceptable form of "N middle bars". | Medium to high | The owner wants bucket-aligned 1h candles as drawn on a chart: levels differ only at bucket edges. |
| TP floor at `risk_reward`, value 1.0 for the candidate. | Medium | The owner prefers to skip trades whose target is under 1 R: a new config, new trial. |
| No stored subscription holds `stop_lookback`. | High at 14:32 today | A subscription edited since then: run the count before release. |
| The fill truth lies between the two bounds. | High | 1m replay in phase 4. |

## 10. Unresolved questions

1. Owner: confirm X is the entry offset only (question in section 2).
2. Owner: default for `stoploss_lookback` after the rename, 2 (recommended) or 20? Either changes the running paper subscriptions, which use 5 entry bars today.
3. Owner: `min_stop_atr` 0.5 (recommended, by the rule) or 1.0 (smaller positions)?
4. Owner: may the 2022 holdout be spent on candidate C as a kill test, after the engine run?
5. Should a paper subscription for C start right after phase 3 ships, in parallel with phase 4? Recommended: yes, it costs nothing and starts the G6 clock.
6. Exness swap on gold for the account type is still unverified; it now matters more.
7. G2 wording: the rubric names both DSR 0.95 and a t 3.0 quick check. They disagree here. Which one binds?

## Sources

- Elder, third screen and stop rule, forum copy [V for the stop quote]: https://www.mql5.com/en/forum/178666 ; paraphrases [S]: https://forexfactory.com/showthread.php?t=382032 , https://practicaltechnicalanalysis.blogspot.com/2009/12/time-frames.html , https://www.incrediblecharts.com/trading/stop_loss_orders.php
- Breakout confirmation filters (point or percent, volatility), textbook chapter copy, not opened [S]: https://phantran.net/breakouts-in-technical-analysis/
- Percent and ATR penetration thresholds [S]: https://www.bit.com/helpcenter/articles/16538924 , https://tradingpedia.com/forex-trading-academy/technical-analysis/breakouts , https://finwiz.io/technical-analysis/breakout-trading , https://research.titanfx.com/technical-analysis/candlestick-chart/what-is-false-breakout
- ATR buffer over the level, 0.10 ATR example [S]: https://studio.kvants.ai/blog/how-to-avoid-false-breakouts
- Kaufman, "Trading Systems and Methods", band and volatility-breakout excerpts [S]: https://fliphtml5.com/lnym/jhdm/PERRY_KAUFMAN_-_TRADING_SYSTEMS_AND_METHODS/
- Stop buffer beyond a swing, 0.1 to 1.0 ATR, vendor guides without evidence [S]: https://www.luxalgo.com/library/concept/atr-based-stop-distance/ , https://darkbot.io/blog/stop-loss-placement , https://goldenviperea.com/blog/risk-money/stop-loss-gold-h4-swing-trades
- Deflated Sharpe Ratio and PBO: as cited in `docs/governance/strategy-assessment-rubric.md`.
