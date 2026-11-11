# Leveraged reanalysis: Triple Screen 15m,1h,4h stop, stop_lookback 80, at 1:500

Run `01a1c41f-dee3-7070-b7ac-086fbb5dacfc`, XAUUSD:EXNESS, 2025-11-09..2026-11-08, 10 000 USD start. This is an offline rescale of the 489 stored trades. No backtest was launched, no code changed, no prod write was made. Written 2026-11-11 by kongming (model Fable 5).

"Verified" means I read it in the code or computed it from prod data today. "Inference" and "Unverified" are labelled.

## TL;DR

- Rescaled to 2% risk per trade over the strategy stop, 10 000 USD ends at 18 808 closed (19 608 with the open short marked), about +88% to +96%. The price is a -27.8% end-of-day drawdown, a -13.3% worst day and three months worse than -8%.
- 1:500 leverage is not the constraint. Peak margin was 5.7% of equity and the lowest margin level was about 1 745%. No margin call or stop-out occurs. The risk is the risk percent and gaps, not margin.
- The edge is not statistically established. Under equal-risk sizing the mean trade is +0.085 R with t = 1.28, before any correction for the roughly 110 configurations tried. Five trades of 489 carry more than the whole profit. Twelve winners came within 1 USD of their stop.
- Recommendation: do not trade 2% at 1:500. Use 0.5% (ceiling 1%) with a notional cap of 5x equity, and treat the set as unproven until it passes an out-of-sample test. Prod has no 15m gold bars before 2025-10-21, so that test needs imported history.

## 1. What was checked first (verified)

| Claim | Result | Source |
|---|---|---|
| Triple Screen entries and exits do not depend on balance | True. The strategy reads only bars and its own position state. | `src/pocketquant/core/domain/strategy/services/triple_screen_strategy_service.py:98-183` |
| One position at a time | True. A stop entry is rejected while a position is open, and the broker refuses a stop fill while one is held. The 489 trades have 0 overlaps. | `src/pocketquant/engine/execution/risk_check.py:42-43`, `paper_broker_adapter.py:581-584`, trade data |
| Size uses realised balance, not equity | True (`balance.available_balance`). The rescale compounds on closed-trade balance. | `src/pocketquant/engine/strategy/strategy_app_service.py:857` |
| At 1:500 the 2% rule decides size | True for this run. The cap is 50x balance. It would bind only for a stop under about 1.6 USD; the smallest is 2.97. | `position_calculator_domain_service.py:44-46`, trade data |
| A resized trade list is unchanged | True with one condition: the account must stay above zero and the broker must not refuse fills. The current paper broker would refuse leveraged longs (section 6). | `paper_broker_adapter.py:365-378` |
| Realised loss can exceed planned risk | Not in this run. The worst trade is -1.026 R. All 144 stop-outs sit between -1.000 and -1.026 R (the excess is commission and slippage). The worst strategy exit is -0.874 R. | trade data |

Method of the rescale: for each trade, `D = |entry fill - sl_price|`, net per oz = `(pnl - commission) / quantity`, `R = net per oz / D`. New size = `balance * risk / D`. Intratrade equity uses the 23 540 prod 15m bars: bar low for longs, bar high + 0.08 for shorts, floored at the stop.

## 2. Leveraged equity path

### 2% of current equity (compounding), no lot rounding

| Month | Start USD | End USD | Change USD | Change % | Trades | Wins |
|---|---|---|---|---|---|---|
| 2025-11 | 10,000.00 | 9,119.29 | -880.71 | -8.81% | 30 | 10 |
| 2025-12 | 9,119.29 | 10,183.86 | +1,064.57 | +11.67% | 40 | 15 |
| 2026-01 | 10,183.86 | 11,681.83 | +1,497.97 | +14.71% | 40 | 16 |
| 2026-02 | 11,681.83 | 10,628.94 | -1,052.89 | -9.01% | 42 | 15 |
| 2026-03 | 10,628.94 | 12,188.18 | +1,559.24 | +14.67% | 37 | 13 |
| 2026-04 | 12,188.18 | 13,603.56 | +1,415.37 | +11.61% | 51 | 18 |
| 2026-05 | 13,603.56 | 13,916.33 | +312.77 | +2.30% | 43 | 17 |
| 2026-06 | 13,916.33 | 15,295.30 | +1,378.98 | +9.91% | 28 | 11 |
| 2026-07 | 15,295.30 | 16,207.15 | +911.84 | +5.96% | 50 | 21 |
| 2026-08 | 16,207.15 | 14,598.98 | -1,608.16 | -9.92% | 47 | 17 |
| 2026-09 | 14,598.98 | 15,722.38 | +1,123.40 | +7.70% | 36 | 14 |
| 2026-10 | 15,722.38 | 16,692.21 | +969.82 | +6.17% | 40 | 13 |
| 2026-11 | 16,692.21 | 18,808.36 | +2,116.16 | +12.68% | 5 | 4 |

Final: 18 808.36 on closed trades. The short still open at the end (entered 2026-11-05) adds about +800, giving 19 608.29 marked to market. Ten months up, three down. The stored run had twelve of thirteen up.

### Comparison of sizing rules

| Rule | Final closed | Final marked | Max drawdown, end of day | Worst intratrade drawdown | Worst day |
|---|---|---|---|---|---|
| Stored run (10% notional cap) | 10,601.54 | 10,619.05 | -0.84% | not computed | -29.83 USD |
| Fixed 200 USD risk | 18,268.30 | 18,693.61 | -18.11% | -27.35% (2025-12-15) | -1,412 USD |
| 2% compounding | 18,808.36 | 19,608.29 | -27.75% (2026-09-01) | -29.36% (2026-09-01) | -2,202 USD, -13.29% |
| 2% compounding, 1 oz lot step | 17,252.44 | 17,986.19 | -27.22% | -28.69% | -2,013 USD, -13.08% |
| 2% compounding, notional cap 5x equity | 19,026 | - | -21.19% (closed trades) | - | - |
| 1% compounding | 14,376.23 | 14,681.94 | -14.93% | -15.91% | -917 USD, -6.85% |
| 0.5% compounding | 12,139.44 | 12,268.51 | -7.75% | -8.29% | -406 USD, -3.48% |

Fixed-risk monthly ends (USD): 9,142 / 10,468 / 12,257 / 11,377 / 12,924 / 14,269 / 14,628 / 15,631 / 16,299 / 15,436 / 16,313 / 17,015 / 18,268.

The lowest equity in the 2% compounding path was 8 432 USD. The fixed-risk path fell to 8 376 USD in December 2025.

### Margin (verified arithmetic, 1:500, 2% compounding)

| Measure | Median | 95th percentile | Peak |
|---|---|---|---|
| Size (oz) | 7.9 | 38.5 | 62.3 |
| Notional / equity | 2.5x | 12.1x | 28.3x |
| Margin (USD) | 71 | 333 | 585 |
| Margin as % of equity | 0.51% | 2.42% | 5.65% |

The lowest margin level (worst intratrade equity divided by margin) was about 1 745%. A web search snippet of the Exness help centre gives a margin call at 60% (Standard) or 30% (Pro) and a stop-out at 0%, and says gold leverage drops to 1:200-1:1000 in high-margin periods. **Unverified** for the owner's account. Even at 1:200 the peak margin would be about 14% of equity. No margin call or stop-out occurs in this path under any of these levels. A leverage of 1:30 would have been enough for every trade.

## 3. Worst day, worst streak, largest loss (2% compounding)

- **Worst day:** 2026-08-24, -2 202 USD, -13.29%. It is seven stop-outs in a row on one day.
- **Worst losing streak in USD:** those same seven trades. The longest run of losers by count is nine trades.
- **Largest single loss:** -208 USD, -2.05% of equity (2026-01-06, 46 oz). No trade lost more than 1.03x the planned risk.
- **Largest single win:** +2 523 USD, +28.1% of equity. It is one short with a 3.53 USD stop that returned 14.07 R.
- **Gaps:** the data holds weekend gaps up to 97.97 USD (2.0%, 2026-01-30 to 02-01). 61 trades were held across a weekend and none was gapped through its stop. That is this sample's luck, not a property of the system (inference). A 1% gap through the stop at 2% risk would cost an extra 2.5% of equity at the median leverage, 12% at the 95th percentile and 28% at the peak leverage (arithmetic).

## 4. Risk of ruin

Method: bootstrap of the 489 per-trade R values, 20 000 paths of 489 trades (one year), equity multiplied by `1 + risk * R` per trade, drawdown measured on closed trades against the running peak. "Block" resamples runs of 10 consecutive trades to keep loss clustering. "Half edge" and "zero edge" subtract half or all of the mean R from every trade; they stand for an out-of-sample edge that is smaller than the in-sample one.

| Risk | Edge assumed | P(drawdown >= 20%) | P(>= 30%) | P(>= 50%) | P(year ends in loss) | Median final |
|---|---|---|---|---|---|---|
| 2% | in-sample | 98% | 70% | 12% | 15% | 1.85x |
| 2% | in-sample, block | 97% | 62% | 8% | 12% | 1.85x |
| 2% | half | 100% | 88% | 32% | 37% | 1.22x |
| 2% | zero | 100% | 97% | 57% | 64% | 0.80x |
| 1% | in-sample | 45% | 10% | 0.1% | 12% | 1.42x |
| 1% | half | 69% | 26% | 0.8% | 31% | 1.16x |
| 1% | zero | 87% | 50% | 5% | 57% | 0.94x |
| 0.5% | in-sample | 3% | 0% | 0% | 11% | 1.21x |
| 0.5% | half | 11% | 0.5% | 0% | 29% | 1.09x |
| 0.5% | zero | 29% | 4% | 0% | 54% | 0.99x |

Over three years at 2%: P(drawdown >= 50%) is 43% with the in-sample edge, 78% with half the edge and 96% with no edge.

The growth-optimal (Kelly) fraction is 4.9% on the in-sample trades and 2.2% if the true edge is half. So 2% is full Kelly under a mild haircut (computed; the haircut size is an assumption).

Limits of the method: it assumes future trades look like these 489. It cannot produce a gap loss larger than any in the sample, so the true tail is worse (inference).

## 5. Unmodelled costs at this size

Final closed equity at 2% compounding, base 18 808:

| Added cost | Final USD |
|---|---|
| Spread 0.168 instead of 0.08 (+0.088 per oz round trip) | 18,070 |
| +0.20 per oz round trip | 17,172 |
| +0.50 per oz round trip | 14,980 |
| +1.00 per oz round trip | 11,928 |
| Swap 0.30 per oz per night, longs only | 18,456 |
| Swap 0.70 per oz per night, longs only | 17,996 |
| Swap 0.70 per oz per night, both sides | 16,618 |
| +0.20 per oz and swap 0.50 long / 0.20 short | 16,265 |

- **Swap.** Exness gold swap rates and swap-free status are **unverified**. The range above is my assumption: 0.70 per oz per night is about 6% a year on 4 000 USD gold. Rollover is taken at 21:00 UTC, tripled on Wednesday. Mean hold is 14.2 hours and the median is 5.0 hours (verified), so most trades cross no rollover. Swap is a minor cost here.
- **Slippage at size.** Sizes are 8 oz at the median and 62 oz at the peak (0.08 and 0.62 lots if 1 lot is 100 oz; **unverified**). Market impact at that size is negligible (inference). Slippage comes from stop orders filling in fast bars, not from size.
- **Spread widening is the real exposure.** It does more than add cost: it moves stops. Twelve winning trades came within 1.00 USD of their stop, and eighteen within 2.00 USD (verified from 15m bars). If those had stopped out, the year's total falls from +41.3 R to +13.4 R (1 USD) or -9.6 R (2 USD). Counting shorts only, whose stop is on the ask, the totals are +18.4 R and -3.8 R. The best trade of the year (+14.07 R, 28% of equity at 2%) came within 0.91 USD of its 3.53 USD stop, entered at 23:30 UTC.
- **Lot step.** With a 1 oz step (0.01 lot, **unverified**), 2% gives 17 252. At 0.5% on 10 000 USD, 152 of 489 trades round to zero size. Small risk percentages need a larger account or a smaller minimum lot.

## 6. Will it survive out of sample?

Evidence against relying on it (verified numbers, my reading):

- **The sizing change weakens the edge.** The stored run trades a near-constant number of ounces, so wide-stop trades dominate the profit: the widest third of stops made 428 of the 602 USD. Under equal risk per trade the profit factor is 1.215, not 1.456.
- **Mean R is +0.085 with a standard deviation of 1.46: t = 1.28.** A bootstrap puts the chance that the true mean is zero or less at 10%, before selection.
- **Selection.** About 110 configurations were tried on this one window. The best of 110 no-edge strategies would be expected to show a t-statistic well above 1.28 (inference from order statistics; the runs are correlated, so the exact figure is unknown).
- **Concentration.** Without the five best trades the total is -4.1 R. Without the ten best it is -31.2 R. Win rate is 37.6%.
- **In favour:** the first half of the trades made +18.8 R and the second half +22.5 R; the PF rises smoothly across five lookbacks; longs (+17.5 R) and shorts (+23.8 R) both contribute.
- **Engine pessimism cuts the other way, by an unknown amount.** 39 trades were stopped on their fill bar and cost -32.2 R. The engine counts the whole fill bar's range against the stop. Some of those stops were hit before the entry and would not be losses live. The 15m bars cannot say how many. Prod holds 1m bars for the whole window, so a 1m replay of fill bars can settle it.

Out-of-sample options (coverage verified on prod today):

| Option | Data state | Value |
|---|---|---|
| Older XAUUSD 15m on prod | None. 15m and 1m start 2025-10-21. 1h starts 2023-10-31, 4h 2023-09-01. | Not possible without an import. |
| Import 2023-2025 gold 1m or 15m history, rerun this one frozen config | Needs a data source and a one-off import. Vendor price differences apply. | Best evidence. Two more years would add about 1 000 trades. |
| Same frozen config on BTCUSDT:BINANCE | 15m from 2024-05-08, 1h and 4h earlier. Runnable today. | Cheap robustness check. A different market, so a pass is weak support and a fail is a warning. |
| Forward paper | A `15m,1h,4h` paper subscription exists; its parameters were not checked today. | Catches execution mismatch. It cannot confirm the edge soon: at about 40 trades a month, t = 2 on a 0.085 R edge needs about 1 180 trades, more than two years. |

## 7. Recommendation

1. **2% at 1:500 is not sane for this evidence.** The in-sample path already shows -28% and a -13% day. If the edge is half as large, the chance of a 50% drawdown within a year is about one in three. Elder pairs the 2% rule with a 6% monthly loss limit (from memory of his books, not checked today); this path breaks that limit in three months.
2. **Use 0.5% per trade, 1% at most,** plus a notional cap of about 5x equity. In-sample, 0.5% gives about +21% with an -8% drawdown, and 1% gives +44% with -15%. The 5x cap bounds a 2% gap to a 10% loss. At 2% it cut the closed-trade drawdown from -27.3% to -21.2% and did not lower the result (19 026 against 18 808) in this sample.
3. **Leverage setting.** 1:500 is harmless as an account setting because margin never binds. It adds nothing either. The cap, not the leverage, should limit size.
4. **Before any live size:** (a) verify the Exness numbers on the real account: stop-out, gold margin periods, swap, minimum lot; (b) run the 1m fill-bar replay; (c) run one frozen out-of-sample test on imported gold history. Do not tune on the new data.
5. **Engine change for a true leveraged backtest (sketch only).**
   - Add `leverage`, `risk_per_trade` and `max_exposure_percent` to the backtest request and `BacktestConfig`; pass them as `RiskConfig` into the `StrategyConfig` built at `src/pocketquant/engine/backtest/backtest_execution_service.py:110`. `RiskConfig` and the calculator already support all three.
   - Fix `PaperBrokerAdapter._can_afford` (`paper_broker_adapter.py:365-378`). Today a BUY needs `price * quantity <= balance` and a SELL is never checked. With leverage on, every long above 1x notional would be refused while shorts pass, which would silently change the trade list. It needs `notional / leverage <= balance`, with the leverage given to the broker.
   - Optional: a stop-out rule when equity falls under the margin, and a lot step on the gold contract spec (`lot_step` is `None` on prod today).
   - This needs a plan and the owner's approval. The offline rescale above is exact for this run, so the engine change is only needed for new configurations.

## Assumptions

| Assumption | Confidence | What would change the answer |
|---|---|---|
| "Future/index" means the same XAUUSD CFD | Medium | A different instrument needs its own data and run; none exists in prod. |
| Exness stop-out 0%, margin call 60% or 30%, gold 1:200 in high-margin periods, 1 lot = 100 oz, minimum 0.01 lot | Low (search snippet only) | A stop-out of 50-100% still would not trigger here; a larger minimum lot would skip more trades. |
| Swap between 0 and 0.70 USD per oz per night | Low | Rates above about 2 USD per oz per night would matter. |
| Bars are bid prices and a short's stop triggers on bid + spread | High (`core/domain/backtest/config.py:20`, broker code) | - |
| Future trades resemble these 489 (Monte Carlo) | Low | This is the question the out-of-sample test answers. |

## Unresolved questions

1. Which instrument does "future/index" mean?
2. Is the owner willing to import 2023-2025 gold intraday history for one frozen out-of-sample run?
3. What are the real Exness account terms (stop-out, swap or swap-free, minimum lot, gold margin schedule)?
4. Does the owner accept 0.5-1% with a 5x notional cap in place of 2%?

Sources for the Exness figures (search snippets, not account-verified): [Exness help centre, margin call and stop-out](https://exnesshelpcenter1650503396.zendesk.com/hc/en-us/articles/10301367403804-What-margin-call-and-stop-out-levels-are-set-for-the-available-trading-account-types), [Exness help, commodities](https://get.exness.help/hc/en-us/articles/17854173039388-Commodities), [Exness professional accounts](https://www.exness.com/pro-accounts/).

Scratch used: `.cache/km/` (gitignored: `pull.txt`, `an2.py`, `an3.py`, `an4.py`). The SSH key copy and all temporary files on the VPS and in the `api` container were removed.
