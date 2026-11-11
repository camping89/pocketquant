# 1m strategy failure diagnosis (r1-r4, XAUUSD:EXNESS)

Date: 2026-11-10. Advisory only. No code changed, no backtest started, no prod write.
Runtime: kongming on Fable 5.2.

## TL;DR

- The four runs fail because the strategies have no raw edge on this window, not because the engine misprices them. Measured bid-to-bid (no spread, no slippage, no commission) the Triple Screen runs have PF 1.009 / 1.005 / 0.975 / 0.894.
- Triple Screen 1m then pays about 0.59 USD per oz per round trip on a median stop distance of 1.1 USD, 27 000 to 37 000 times. That turns a PF near 1.0 into 0.66-0.75.
- Two engine assumptions are pessimistic and material, but neither rescues a run: the 0.5 bp slippage default (75% of r1's total cost, not part of the plan's 0.15 cost model) and the "stop-loss first" rule inside one bar. With slippage removed and every ambiguous bar resolved in the strategy's favour, the best run reaches PF 1.14, still under the 1.2 gate.
- No look-ahead, fill-price, spread-side or sizing defect was found.

## How the numbers were produced

- Code reading at HEAD f0d00dd3 (file:line below).
- Two read-only scripts run in the prod `api` container on 2026-11-10 against `backtest_runs`, `backtest_trades` and `bars`. Raw output: `.cache/diag.txt` and `.cache/diag2.txt` (not committed). The first script is no longer on disk; the second is `.cache/f.py`.
- Sanity check: the per-trade reconstruction reproduces the stored net PnL to the cent for all four runs (r1 -3861.18 vs -3861.18).
- The cost variants below hold the stored trade list fixed and re-price it. They are an accounting split, not a re-simulation. Slippage never moves a trigger, so the "no slippage" variant is close to what a re-run would give. Removing the spread would move short-side triggers, so "frictionless" is an approximation.

## Verified engine facts (code)

| Fact | Where |
|---|---|
| Bars are bid. A BUY fills at `bid + spread`, then slippage is applied against the trader on every fill, entries and SL/TP/strategy exits alike. | `core/infra/brokers/paper/paper_broker_adapter.py:206-207, 356-359, 728` |
| Slippage is 0.5 bp unless the request sends one. The four runs stored `slippage_bps: 0.5`, `spread: 0.08`, `commission_per_contract: 0.035`. | `engine/backtest/backtest_command_service.py:25`, `backtest_execution_service.py:40`; r1 `config_snapshot` |
| Stored `pnl` is the price move between fill prices, so it already contains spread and slippage. "PF before commission" is not a gross figure. | `core/domain/position/entities.py:145-147`, `core/domain/trading/value_objects.py:103-107` |
| A market entry fills at the signal bar close. SL/TP are checked from the next bar. | `backtest_app_service.py:106`, `paper_broker_adapter.py:530-538` |
| A bar that opens past a level fills at the open. When SL and TP are both inside one bar, SL wins. | `paper_broker_adapter.py:698-719` |
| A short's SL and TP trigger on the ask (`bid + spread`). | `paper_broker_adapter.py:711-718` |
| A resting stop entry fills on a later bar at `max(ask open, stop)` or `min(open, stop)`. On the fill bar the SL is checked and assumed to come after the fill. | `paper_broker_adapter.py:546-618` |
| Size is `min(2% risk / stop distance, 10% of balance / price)`. | `core/domain/risk/services/position_calculator_domain_service.py:44-46` |
| Higher-timeframe context holds only bars with `start + step <= entry bar start`. | `engine/strategy/strategy_app_service.py:69-70, 408-420` |
| Sharpe is annualized from per-bar mark-to-market returns with the calendar's 1m periods per year. | `engine/backtest/backtest_report_app_service.py:303-317`, `core/domain/trading/performance_calculator_domain_service.py:70-73` |
| Triple Screen re-enters on any bar where it is flat and the setup holds. The stop is the 5-bar extreme including the signal bar, with no minimum distance. | `triple_screen_strategy_service.py:113-147` |

## Measured facts (prod, 2026-11-10)

Market data: 353 818 one-minute bars; median bar range 1.97 USD (p25 1.33, p75 3.01); median close 4390. Slippage at that price is 0.22 USD per oz per fill, 0.44 per round trip.

### Cost split (PF, trade list fixed)

| Run | As run | Spread + commission, no slippage | Spread only | Bid to bid |
|---|---|---|---|---|
| r1 | 0.663 | 0.902 | 0.950 | 1.009 |
| r2 | 0.746 | 0.928 | 0.963 | 1.005 |
| r3 | 0.673 | 0.884 | 0.925 | 0.975 |
| r4 | 0.710 | 0.840 | 0.865 | 0.894 |

r1 net loss of 3861 USD splits into slippage 2945 (76%), spread 528, commission 462, and a raw edge of +74.
Mean cost per oz per trade as run: 0.59 (r1), against the 0.15 the plan stated (plan.md A2 and "Facts").

### Stop distance against cost (Triple Screen)

| | r1 | r3 | r2 | r4 |
|---|---|---|---|---|
| SL trigger distance p25 / p50 / p75, USD | 0.49 / 1.13 / 2.35 | 0.53 / 1.22 / 2.68 | 1.40 / 2.06 / 3.13 | 1.45 / 2.21 / 3.50 |
| Cost / SL distance, median | 0.53 | 0.48 | 0.29 | 0.27 |
| Trades with SL distance under 0.55 | 27.5% | 25.7% | 1.0% | 1.2% |
| Trades whose TP distance is under the cost | 9.9% | 9.0% | n/a | n/a |

r1 by SL distance: under 0.5 USD, 8828 trades, net win rate 13.8%, net PF 0.062, loss 1035. From 1 USD up the bid-to-bid PF is 1.00-1.08 and the net win rate is 32-35%.

### Win rate against a zero-edge benchmark (market + sl_tp runs)

| | r1 | r3 |
|---|---|---|
| TP rate expected from trigger distances for a driftless walk | 30.8% | 30.9% |
| Actual TP rate | 29.4% | 29.1% |
| TP exits that still lost money net | 711 | 467 |
| TP rate LONG / SHORT | 30.5 / 28.3 | 29.9 / 28.3 |

The benchmark is an approximation: it ignores bar discreteness and gaps.

### Intrabar ordering

- r1: 4564 SL exits (12.4% of all trades) happened on a bar that also touched the TP. r3: 3313 (12.2%).
- Upper bound, every such bar counted as a TP: r1 PF 0.725 as run, 0.996 without slippage. r3 0.734 and 0.973.
- r2: 2695 trades (18%) were stopped out on their fill bar and carry 1370 of the 1802 USD net loss. r4: 1446 trades, 806 of 1387.
- Upper bound, those trades removed: r2 PF 0.925 as run, 1.142 without slippage. r4 0.855 and 1.004.

### Checks that came back clean

- Market entry price equals the entry bar close plus spread and slippage: 36 847 / 36 847 (r1), 27 265 (r3). No mismatch.
- SL exit price equals `min(open, sl)` (long) or `max(ask open, sl)` (short): 26 034 / 26 034 (r1), 19 342 (r3). Gap-through exits: 839 (r1), 626 (r3).
- Market runs with an exit on the entry bar: 0.
- Look-ahead: the setup recomputed from closed higher-timeframe bars agrees with the trade direction on 2632 / 2632 sampled r1 trades and 2727 / 2727 r3 trades. Recomputed with the still-open bucket it agrees on 818 and 982. The engine did not read open buckets.
- Quantity p10 / p50 / p90 is 0.15 / 0.17 / 0.22 oz (r1): the 10% exposure cap sets every size, so sizing does not shape PF or win rate.

### Churn

- r1: after an SL exit the strategy re-entered within one minute 22 073 times out of 26 033 (85%), 99% of them in the same direction. r3: 17 865 of 19 341 (92%).

## Ranked hypotheses

### A. Strategy has no edge

| # | Hypothesis | Status | Evidence |
|---|---|---|---|
| A1 | Triple Screen on a 1m entry has no raw edge in this window. | Confirmed (fact) | Bid-to-bid PF 1.009, 1.005, 0.975, 0.894. TP rate 1.5 points under the zero-edge benchmark. |
| A2 | The stop sits inside one bar's noise and inside the cost, so cost per trade is large against the distance traded. | Confirmed (fact) | Median SL distance 1.13 vs median bar range 1.97 and cost 0.59. 27.5% of r1 trades have an SL distance under the cost; 9.9% cannot profit even at TP. |
| A3 | The strategy re-enters the same setup right after a stop, which multiplies the trade count and the cost. | Confirmed (fact) | 85-92% re-entry within one minute, 99% same direction; 36 847 trades in 12 months. |
| A4 | The short side loses a little more because its SL is a bid high but triggers on the ask. | Consistent, small (inference) | TP rate 28.3% short vs 30.5% long in r1. Not isolated from other causes. |

### B. Engine or model makes a possibly-fine strategy look worse

| # | Hypothesis | Status | Evidence |
|---|---|---|---|
| B1 | The 0.5 bp slippage default is the largest cost and was not in the plan's cost model. | Confirmed (fact). Whether 0.5 bp is realistic for Exness gold is unverified. | 76% of r1's loss. Applied to TP fills too, which are limit orders at a real venue. |
| B2 | "SL first" inside one bar under-counts TP exits. | Confirmed as a bias, bounded (fact) | 12% of r1/r3 trades. Best case PF 0.996 (r1) without slippage. |
| B3 | Stop entries are assumed stopped out when the fill bar also touches the SL. | Confirmed as a bias, bounded (fact) | 18-19% of r2/r4 trades, 58-76% of their net loss. Best case PF 1.142 (r2) without slippage. |
| B4 | Sharpe of -24 overstates how bad the run is. | Inference | Per-minute annualization of a steady small loss gives a large negative ratio. The formula was read, not re-derived on the data. |
| B5 | Higher-timeframe context lags by up to one minute at a bucket boundary. | Confirmed, small (fact); PnL effect not measured | A bucket that closes with the entry bar is first visible one bar later. Recomputing with it changes the setup on 1.4-5% of sampled trades. Live uses the same rule. |

### Killed

| Hypothesis | Killed by |
|---|---|
| Look-ahead in entries | 100% agreement on closed bars, 31-36% with the open bucket |
| Wrong fill price or spread on the wrong side | Entry and SL exit prices match the engine rule on every trade |
| Same-bar entry and exit on market runs | 0 trades |
| Stop-entry fill price | Rule read at `paper_broker_adapter.py:568-575`; 7.6-7.9% of fills at the open (gap through the stop), the rest at the stop |
| Position sizing | Exposure cap binds on every trade |
| Commission | 462 USD of 3861 in r1 |
| Multi-interval alignment | Same check as look-ahead |

### What no tested assumption changes

With real costs kept (spread and commission) and both pessimistic rules fully reversed, the best PF is 1.142 (r2). No run reaches 1.2. Reaching it needs zero cost, which is not an engine question.

## Verification plan (cheapest first)

Steps 1-9 need no new backtest. I ran steps 2-9 today; the owner can repeat them from `.cache/f.py`.

| # | Measure | Where | Pass / fail | Confirms or kills | New run |
|---|---|---|---|---|---|
| 1 | Slippage, spread and commission the run used | `backtest_runs.config_snapshot` of each run id | `slippage_bps` equals what the owner meant to charge. Found 0.5, not in the plan's 0.15 model. | B1 | No |
| 2 | Reconstructed net PnL against stored | `backtest_trades`: invert spread and slippage per `paper_broker_adapter.py:206-207` | Sums equal to the cent. If not, every later step is void. | Validates the method | No |
| 3 | PF bid to bid, spread only, spread + commission, as run | Same trades | Bid-to-bid PF at or above 1.2 means an edge exists and cost hides it. Found 0.89-1.01. | A1 vs B1 | No |
| 4 | SL distance and TP distance against cost per oz | `entry_price`, `sl_price`, `tp_price` | Fail when over 10% of trades have an SL distance under the cost. Found 26-28% in r1/r3, 1% in r2/r4. | A2 | No |
| 5 | Actual TP rate against the driftless rate `a / (a + b)` | Same trades, trigger distances | Within 2 points means no edge. More than 2 above means edge. Found 1.5 below. | A1 | No |
| 6 | Entry price against entry bar close; SL exit against `min(open, sl)` | `backtest_trades` joined to `bars` 1m on `entry_time` and `exit_time` | 100% match. Found 100%. | Kills fill-model defects | No |
| 7 | SL exits whose bar also touched TP; PF with all of them as TP | Same join | Bound under 1.2 kills B2 as a rescue. Found 0.996 without slippage. | B2 | No |
| 8 | Stop-run trades with `duration_seconds == 0` and `auto_sl`; PF without them | `backtest_trades` r2, r4 | Bound under 1.2 kills B3 as a rescue. Found 1.142 without slippage. | B3 | No |
| 9 | Setup recomputed from closed bars, from the just-closed bucket, and from the open bucket | `bars` 5m, 15m, 1h and a trade sample | Closed-bar agreement 100% and open-bucket agreement well under it. Found 100% vs 31-36%. | Kills look-ahead; sizes B5 | No |
| 10 | Minutes from an SL exit to the next entry, and its direction | `backtest_trades` sorted by `entry_time` | Over 50% within one minute confirms churn. Found 85-92%. | A3 | No |
| 11 | Re-run r1 and r2 with `slippage_bps: 0` in the request body | `POST /api/v1/backtest/run`, plan WINDOW rule | PF within 0.02 of 0.902 and 0.928 confirms the cost split. | B1, validates step 3 | Yes, 2 runs |
| 12 | Real slippage per fill | Exness demo or live fills, once any exist | Median adverse slippage per fill against 0.22 USD. No fills exist today. | B1 realism | No run; needs fills |
| 13 | True order of SL and TP inside ambiguous bars | Tick or sub-minute history for a sample of the 4564 r1 bars | Share of TP-first bars. The repo stores nothing finer than 1m. | B2, B3 exact size | No run; needs data the repo lacks |

Steps 12 and 13 refine the size of B1-B3. Their bounds are already known, and the bounds fail the gate, so neither step can change the verdict on these four runs.

## What to avoid

- Do not read "PF before commission" as gross. It contains spread and slippage.
- Do not treat the best-case bounds as estimates. Removing fill-bar stops also removes real losses.
- Do not tune slippage down to pass a gate. Change it only on fill evidence (step 12).
- Do not compare the 5m PF of 0.78-0.79 with these runs as proof of anything about 1m signals. I did not decompose the 5m runs; a lower cost-to-distance ratio there is my inference.

## Assumptions

| Assumption | Confidence | What would change it |
|---|---|---|
| Exness charges spread 0.08 and 0.035 per oz per side on gold, as seeded. | Medium | The seed comment says the prod account's own median spread measured 0.168. At 0.168 every PF above is lower. |
| The driftless-walk TP rate is a fair zero-edge benchmark. | Medium | A re-simulation with random entry direction on the same bars would replace it. That needs code and is outside this brief. |
| Slippage of 0.5 bp is pessimistic for 0.2 oz market orders and for TP limits. | Low | Step 12. |
| One 12-month window is representative. | Low | The owner accepted this risk in the archived plan (R8). |

## Unresolved

1. What slippage should a gold backtest charge? Recommended default: keep 0.5 bp until real fills exist, and report PF with and without it. Real fills flip this.
2. Which spread is right, 0.08 or the measured 0.168?
3. `/tmp/f.py` (the read-only script, no secrets) remains inside the prod `api` container; the in-container `rm` was refused. A redeploy removes it.
