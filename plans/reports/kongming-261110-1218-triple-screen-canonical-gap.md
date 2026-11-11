# Triple Screen: canonical rules against our implementation (XAUUSD:EXNESS)

Date: 2026-11-10. Advisory only. No code changed, no engine backtest started, no prod write.
Runtime: kongming on Fable 5.2. Angle: Triple Screen only.

Labels used below: **Measured** = read from prod or code today. **Sourced** = from a cited page. **Inference** = my reasoning, not verified.

## TL;DR

- The premise "published and used, so it should win" does not hold as stated. Triple Screen is a discretionary framework from 1986. I found no published, reproducible backtest that shows a mechanical edge (Sourced: absence in the searches listed; the one backtest page I found could not be fetched).
- Our strategy is not the system Elder describes. Elder trades the **middle** timeframe: the entry trigger is a break of the previous middle bar and the stop sits beyond the last two middle bars. Ours takes the trigger and the stop from the **entry** bar (1m), re-enters every entry bar, and by default enters at market with no trigger at all.
- A sketch simulation of the canonical trigger and stop on the same data (my own script, not the engine, not reviewed) moves the 1m sets from PF 0.84-0.89 to about 1.0, and gives PF 1.48 for a 1h trading bar with a 4h trend (431 trades, weekly bootstrap 95% range 1.09-2.01). Neighbouring variants range from 0.58 to 1.32, and I tried 16. This is a lead to test, not a result.
- Below a 15m trading bar there is no edge to recover in this window: the raw signal moves price by about 0.08 USD in 5 minutes against a 0.24 USD round-trip cost.
- The brief's "gold trended strongly up" is false for the window (+1.2% net). Equal long and short PF needs no explanation.

## 1. Canonical rules

All sources are secondary summaries of Elder's books. I could not open the book text itself (the one book-text host refused the connection). Treat wording as paraphrase.

| Rule | Canon | Source |
|---|---|---|
| Timeframes | The timeframe you want to trade is the **intermediate** one. The long-term chart is 5 times longer; the short-term one 5 times shorter. Summaries give the factor as 5, or 4 to 6. | [joshchua summary of The New Trading for a Living ch. 38-41](https://joshchuasg.wixsite.com/mysite/post/trading-systems); search summaries of [tradingstrategyguides](https://tradingstrategyguides.com/alexander-elder-trading-strategy-the-triple-screen/), [substack](https://tradingwriters.substack.com/p/elders-triple-screen-trading-system) |
| Intended charts | Swing: weekly and daily. Day-trading example: 25 or 30-minute trend chart, 5-minute trading chart (an 8-minute / 39-minute pair is also given). The shortest chart named anywhere is a 2-minute chart, as the optional short-term screen. | joshchua summary (same link) |
| Screen 1 (tide) | Slope of the weekly MACD-histogram (1993 book): the last two bars define the slope. Later books: slope of the weekly EMA, or the Impulse system. Best buy signals come when the slope turns up from below the centre line. | [roboforex](https://roboforex.com/blog/education/triple-screen-trading-system-how-to/), joshchua summary |
| Screen 2 (wave) | An oscillator on the trading chart moving against the tide. 2-bar EMA of Force Index below zero for a buy, and not at a new multi-week low. Alternatives: Elder-ray, Stochastic (below 30 / above 70), RSI. | joshchua summary |
| Screen 3 (entry) | No indicator. A buy stop one tick above the **previous day's** high, lowered each day to one tick above the latest bar's high, until filled or until the weekly trend reverses. Shorts mirror. Later books add: a limit order below the EMA by the average penetration, or timing on 25 and 5-minute charts. Elder notes the breakout entry suffers when the bar before it is very wide (wide stop) or very narrow (stop inside noise). | [forexfactory thread](https://www.forexfactory.com/thread/382032-third-screen-strategy-dr-alexander-elder) (search summary; fetch failed), joshchua summary |
| Initial stop | One tick beyond the low of the trade day or the previous day, whichever is lower (two bars of the trading chart). Later books: SafeZone (not confirmed by any page I could open). | forexfactory thread (search summary) |
| Targets, exits | Targets come from the long-term chart (its value zone, or a channel on the trading chart); stops from the trading chart. Reward to risk above 2:1 is a filter for taking the trade, not a fixed target. | joshchua summary |
| Sizing | 2% rule: no trade risks more than 2% of equity. 6% rule: stop trading for the month when month losses plus open risk reach 6%. | [quantstrategy.io](https://quantstrategy.io/blog/alexander-elders-risk-management-essentials-the-2percent/) (search summary) |
| Published backtests | None found with numbers for Triple Screen on gold or intraday. [quantifiedstrategies.com](https://www.quantifiedstrategies.com/alexander-elder-triple-screen-strategy/) has a backtest page; it returned a bot check, so I cite no figure from it. | searches of 2026-11-10 |

Not verified: Elder's own words on day-trading cost and difficulty, and the SafeZone rule. No page I could open carried them.

## 2. Deviations in our code

File: `src/pocketquant/core/domain/strategy/services/triple_screen_strategy_service.py` (HEAD 481fafe3). Tests: `tests/core_test/unit/domain/strategy/test_triple_screen.py`.

| # | Our behaviour | Where | Canon | Verdict |
|---|---|---|---|---|
| V1 | The stop-entry price is the high or low of the **entry** bar. | `:121-127`; test `test_a_stop_entry_rests_at_the_entry_bar_high` (line 141) | Previous bar of the **trading (middle)** chart | Deviation. With a 1m entry the trigger is a 1-minute high, 5 or 15 times finer than the bar the oscillator reads. |
| V2 | The SL is the extreme of the last 5 **entry** bars, signal bar included, with no minimum distance. | `:32, :67, :99, :124, :128` | Two bars of the trading chart | Deviation. Measured median SL distance 1.25 USD (r1) and 2.19 (r2); the canonical distance in my sketch is 4.1 (5m bar) and 7.3 (15m bar). |
| V3 | Default entry is a market order at the close of every entry bar on which the setup holds. | `:26, :123, :127, :147` | Breakout stop, or a limit below value | Deviation. A market entry removes the third screen. |
| V4 | Any flat bar with the setup enters again. Nothing remembers a stop-out. | `:113-147` | One order per trading bar | Deviation. Measured: 22 073 of 26 033 r1 stop-outs re-enter within one minute; 17 865 of 19 341 in r3. |
| V5 | The entry interval is 1m and the sets are 1m/5m/15m (ratios 5 and 3) and 1m/15m/1h (ratios 15 and 4). | run configs | Factor about 5; shortest example is a 5-minute trading chart | Outside the intended use. See section 3. |
| V6 | Tide is the sign of the last change of the MACD-histogram on the top interval. | `:82-89, :103` | Same in the 1993 book | Matches the 1993 rule. It ignores the later EMA-slope and Impulse forms and the "from below the centre line" preference. |
| V7 | Wave is the 2-bar EMA of Force Index below or above zero. | `:91-95, :104-105` | Same, plus "not a new multi-week low" | Matches, without the multi-week-low filter. Volume is the Exness tick count (Measured: a stored bar has `volume` equal to `tick_count`), not traded volume. |
| V8 | A resting stop is re-sent each bar at the newest entry-bar extreme and cancelled when the setup is gone, which includes Force Index crossing back over zero. | `:142-149`; tests `test_the_stop_is_sent_again_each_bar_while_the_setup_holds`, `test_exit_when_the_setup_is_gone_with_a_stop_armed` | Trail until filled or the tide reverses | The trailing matches in form. The cancel rule is stricter than canon. |
| V9 | No tick offset on the stop-entry price or the SL. | `:123-128` | One tick beyond | Small. |
| V10 | Exit is a fixed 2R target (`sl_tp`) or a tide flip (`strategy`). | `:33, :114-116, :137-140` | Target from the long-term chart; stop on the trading chart | Deviation. The tide-flip exit is the closer of the two. |
| V11 | Size is `min(2% risk / stop distance, 10% of balance / price)`. The 10% cap sets every size (earlier diagnosis). No monthly 6% rule. | `core/domain/risk/services/position_calculator_domain_service.py:15-16, :44-46` | 2% and 6% rules | Deviation in risk taken, not in PF. Each trade risks far less than 2%. |

Read this table with care: V1-V4 are one deviation seen from four sides. Elder's system makes one decision per trading bar, with a trigger and a stop sized to that bar. Ours makes one decision per minute, with a trigger and a stop sized to a minute.

## 3. Are the timeframes within the intended use?

Measured on prod bars and stored trades, 2026-11-10. Raw output of the section 4 runs is in `.cache/ts_out2.txt` and `.cache/ts_out3.txt` (git-ignored). The raw output of the first run (gold path, stored-run decomposition, raw signal) was deleted by my own cleanup mistake; its figures in this report were copied from it before that. The scripts and the SSH key copy were removed as instructed, so repeating any figure means rewriting the script from the rules stated here.

**Gold in the window.** First 1m close 4006.5, last 4055.5, high 5593.1, low 3870.6. Net change +1.2%. Mean drift per 1m bar 0.00014 USD. The window is a round trip, not an uptrend.

**Raw signal, no execution model.** For every 1m bar where the setup held, the signed price move after it:

| Set | Setup bars | After 1 min | After 5 min | After 15 min | After 60 min |
|---|---|---|---|---|---|
| 1m/5m/15m | 146 912 | +0.013 USD (t 2.7) | +0.076 (t 3.1) | +0.100 (t 1.7) | +0.220 (t 1.5) |
| 1m/15m/1h | 158 595 | -0.004 (t -0.6) | -0.032 (t -1.2) | -0.091 (t -1.3) | -0.135 (t -0.6) |

t is computed across days. I looked at four horizons per set, so one t near 3 is weak evidence. The current round-trip cost is about 0.24 USD per oz (spread 0.08, commission 0.07, slippage 0.1 bp twice). The best 5-minute drift is a third of that. The 15m/1h set shows no drift.

**Judgement.**
- 1m/5m/15m: the 1m-to-5m ratio is canonical, the 5m-to-15m ratio (3) is not, and the trigger and stop sit on 1m, below anything Elder describes. Fact: the signal's drift is smaller than the cost. Inference: no rule change on a 1m or 5m trading bar will clear the 1.2 gate at this cost.
- 1m/15m/1h: the entry is 15 times finer than the oscillator bar. It is not a Triple Screen ratio, and its raw signal has no drift.

**What the older sets say.** Less than they seemed to.

- The six Phase 16 runs of 2026-11-02 (`plans/261101-0843-stf-to-mtf-foundation/reports/phase-16-backtests-and-paper-start.md`) stored `commission_bps: 3.0`, no per-contract fee, `spread: 0.0`, `slippage_bps: 0.5`. Measured median cost: 3.09 USD per oz per round trip, about 13 times today's 0.24. Their PF of 0.78-0.79 for the 5m set is mostly that fee.
- Re-priced at today's cost with the trade list fixed (an accounting estimate, not a re-run):

| Set | market + sl_tp: bid-to-bid / at today's cost | stop + strategy: bid-to-bid / at today's cost | Trades |
|---|---|---|---|
| 5m/15m/1h | 0.920 / 0.849 | 0.863 / 0.816 | 8516 / 3585 |
| 15m/1h/4h | 1.009 / 0.966 | 1.208 / 1.172 | 2479 / 933 |
| 1h/4h/1d | 0.844 / 0.826 | 0.703 / 0.694 | 707 / 275 |

- The coordinator's 2026-11-07 runs at 0.5 bp (0.754/0.748, 0.895/1.118, 0.803/0.676) agree with this in order and size.
- So the older sets do not show "longer is better". 15m/1h/4h is the best, 1h/4h/1d the worst, on 275 to 933 trades. Inference: with our rules the result depends on the set more than on the timeframe length, which is what noise looks like.

## 4. Sketch test of the canonical rules

I wrote a small simulation in the read-only prod script. It is not the engine and nobody has reviewed it. Rules: decide once at each close of the trading (middle) bar; tide from top bars closed by then; Force Index on the trading bar; stop order one tick beyond that bar's extreme, valid for the next trading bar only; SL one tick beyond the lower of that bar's low and the low seen before the fill; exit at 2R or on a tide flip; orders, stops and targets executed on 1m bars, SL first inside a 1m bar; 1 oz per trade; today's cost. Window 2025-11-09 to 2026-11-08.

| Trading bar / tide bar | Exit 2R: PF net (trades) | Exit tide flip: PF net (trades) | Median risk, USD |
|---|---|---|---|
| 5m / 15m | 0.977 (5548) | 1.017 (5143) | 4.1 |
| 5m / 30m | 0.910 (6441) | 0.918 (4723) | 4.2 |
| 5m / 1h | 0.925 (6712) | 0.951 (3732) | 4.2 |
| 15m / 1h | 0.926 (2031) | 0.909 (1781) | 7.2 |
| 15m / 4h | 0.948 (2300) | 1.317 (1099) | 7.4 |
| 1h / 4h | 1.096 (512) | 1.477 (431) | 15.0 |
| 1h / 1d | 0.851 (565) | 0.581 (305) | 15.8 |
| 4h / 1d | 1.072 (140) | 1.121 (112) | 28 |

Facts from this table:
- The canonical trigger and stop on a 5m bar give PF 0.98-1.02, against 0.843 and 0.885 for r1 and r2 on the same data and cost. The deviation costs about 0.1-0.15 of PF, and removing it still leaves no edge at 5m.
- 1h/4h with the tide-flip exit: PF 1.477, long 1.64, short 1.33, both halves 1.48, 10 of 13 months positive. Resampling weeks 2000 times gives a 95% range of 1.09-2.01; 0.3% of resamples fall under 1.0 and 9.5% under 1.2.
- 15m/4h with the tide-flip exit: PF 1.317; 95% range 1.03-1.66; 23% of resamples under 1.2.
- 1h/1d with the same rules gives 0.581.

Supporting measurement: the raw 1h/4h signal has a positive signed drift over a longer sample (2023-12 to 2026-11, 7478 setup bars): +0.36 USD after 1 bar (t 3.1), +1.51 after 10 bars (t 2.3). The 4h/1d signal is negative over the same span (t -2.3 after 1 bar).

How far to trust it (inference): I ran 16 variants and am pointing at the best two. The 1h/1d neighbour fails badly. One 12-month window. The weekly bootstrap does not correct for picking the best of 16. I would put the chance that 1h/4h holds up out of sample well below what its bootstrap suggests. It earns a proper test, nothing more.

A side finding (Measured): when the same rules are executed on trading bars instead of 1m bars, with a stop assumed whenever the fill bar also touches the SL, 1h/4h tide falls from 1.477 to 1.054 and a third of all trades become fill-bar stops. The engine uses that same assumption on the entry interval. So any engine backtest whose entry interval is 15m or longer under-reports stop entries. This is the earlier diagnosis's B3, and it is large at these bar sizes.

## 5. Ranked deviations and cheap tests

Ranked by expected effect on PF. "Effect" figures are from section 4 unless marked.

| Rank | Deviation | Expected effect | Evidence |
|---|---|---|---|
| 1 | Trading bar too short for the cost (V5) | Decides pass or fail. No fix below 15m. | Signal drift 0.08 against cost 0.24; sketch 5m PF about 1.0 |
| 2 | Trigger and stop taken from the entry bar instead of the trading bar (V1, V2) | About +0.1 to +0.15 PF at 5m; larger at 1h (sketch 1.48 against the engine's 1h/4h/1d runs, which are not the same set) | Sketch table; r1 SL 1.25 against canonical 4.1 |
| 3 | Re-entry every entry bar (V4) | Multiplies trades and cost; no change to gross edge in r1 (gross PF 1.008 first entries, 1.004 re-entries), worse in r3 and r4 (0.990 against 0.950; 0.919 against 0.813) | Measured |
| 4 | Market entry with no trigger (V3) | Mixed: stop entry is better in r1 to r2 (0.843 to 0.885) and at 15m/1h/4h (0.966 to 1.172), worse in r3 to r4 and at 1h/4h/1d | Measured |
| 5 | Fixed 2R target instead of a trend exit (V10) | Tide flip beats 2R in 6 of 8 sketch pairs | Sketch |
| 6 | Engine fill-bar stop rule at long entry bars | Hides up to 0.4 PF on a 1h entry | Sketch on trading bars against 1m |
| 7 | Tick volume, missing multi-week-low filter, cancel on Force Index recross, no tick offset (V7-V9) | Unknown, expected small | Not measured |
| 8 | Sizing (V11) | None on PF | Earlier diagnosis |

### Tests that need parameters only

Run one at a time on prod with the existing window and cost. Gate as before: net PF at least 1.2, at least 100 trades. Write down the prediction before each run.

| # | Run | Tests | Prediction | Kills the idea when |
|---|---|---|---|---|
| T1 | `15m,1h,4h`, `entry_type=stop`, `exit_mode=strategy`, current cost, 0.1 bp | Whether the best old set clears the gate at today's cost | PF 1.15-1.20 (re-pricing gave 1.172) | PF under 1.1 |
| T2 | Same set with `stop_lookback` 2, 5, 10 | V2: stop distance | Flat or rising with lookback | PF moves by more than 0.15 between neighbours, which means noise |
| T3 | `1m,5m,15m`, `stop`, `strategy`, `stop_lookback=10` and `30` | V2 at 1m: a stop as wide as two 5m or two 15m bars | PF rises from 0.885 toward 1.0, stays under 1.1 | PF does not rise: the stop is not the 1m problem |
| T4 | `1h,4h,1d` and `5m,15m,1h`, `stop`, `strategy`, current cost | Fresh numbers for the two other old sets at today's cost | About 0.69 and 0.82 | Either above 1.1 would contradict the re-pricing |
| T5 | T1 on a second window, 2025-10-22 to 2026-04-30 and 2026-05-01 to 2026-11-08 | Stability | Both halves above 1.0 | One half under 0.9 |

T1 and T2 are the only parameter-only runs that can pass the gate. T3 and T4 are confirmations.

### Hypotheses that need code (not implemented)

| # | Change | Test | Pass |
|---|---|---|---|
| H1 | Decide once per middle bar: stop entry one tick beyond the previous middle bar, SL beyond the last two middle bars, order valid for one middle bar. Keep 1m bars for fills only. | `1m,1h,4h` and `1m,15m,4h` with the tide-flip exit, engine backtest | PF within 0.15 of the sketch (1.48 and 1.32). A miss means the sketch is wrong; find out why before going on. |
| H2 | No new entry in the same middle bar after a stop-out | r1 and r3 re-run | Trade count falls by more than half; PF does not fall |
| H3 | A second, untouched data span for the H1 winner | Needs 1m bars before 2025-10-21 | PF above 1.2 there as well |

H1 fits in the existing strategy file. The engine already hands a 1m-entry strategy its higher-timeframe context and fills resting stops on the finest bar.

## What to do

1. Stop testing Triple Screen on a 1m or 5m trading bar. The signal is smaller than the cost there.
2. Run T1 and T2 now. They are cheap and need no code.
3. If the owner wants to keep the strategy, build H1 and test exactly two pre-named sets: 1h trading bar with 4h tide, and 15m with 4h. Name them before the run. Do not sweep.
4. Treat any pass as provisional until H3 or 30 paper days agree.

## What to avoid

- Do not read "published" as "has an edge". No source I could open gives a mechanical result.
- Do not cite the Phase 16 PF figures as evidence about timeframes. They were charged about 3 USD per oz.
- Do not pick a set from the sketch table by its PF. Sixteen variants were tried.
- Do not trust an engine backtest with stop entries on a 15m or longer entry bar without knowing how many trades were stopped on their fill bar.
- Do not tune `stop_lookback`, MACD periods and `risk_reward` together on this one window.

## Assumptions

| Assumption | Confidence | What would change it |
|---|---|---|
| Secondary summaries carry Elder's rules correctly. | Medium-high; several agree | The book text |
| My sketch simulation has no bug or look-ahead. | Medium; it was not reviewed and its results differ a lot between neighbours | H1 in the engine |
| Cost is 0.24 USD per oz per round trip. | Medium | A spread of 0.168 (the measured prod median) makes every figure worse; hardest on the short-bar sets |
| One 12-month round-trip window is representative. | Low | H3 |
| Re-pricing old trades at a new cost approximates a re-run. | Medium; a spread moves short-side triggers | T1 and T4 |

## Unresolved

1. Is the 1h/4h result real or the best of 16? Only H1 plus H3 or paper answers it.
2. Can 1m bars before 2025-10-21 be loaded for XAUUSD:EXNESS? Without them there is no second span for a 1m-filled test.
3. Which spread is right, 0.08 or 0.168?
4. Does the owner want to keep Triple Screen at all? Recommended default: yes for one more step (T1, T2, then H1 on two named sets), then stop if neither passes.
