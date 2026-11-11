# Why the "valid" strategies lose: synthesis of two advisors

Sources: `kongming-261110-1218-triple-screen-canonical-gap.md` (A), `kongming-261110-1218-gold-timeframe-edge.md` (C), and the earlier `kongming-261110-0915-1m-strategy-failure-diagnosis.md`.

## Answer

The owner's premise, "these strategies are valid", fails for two different reasons. Triple Screen is a different strategy from the one its name suggests, and the 1m timeframe has no edge large enough to pay the cost.

1. **Timeframe (C, measured).** Gold returns in 2025-11..2026-11 look like a random walk at every horizon from 1m to 1d. On 1m the round-trip cost (about 0.24 USD/oz) is 12% of a median bar. Only 1 of 7 generic trend rules beats cost on 1m, against 7 of 7 on 1h. Published trend evidence sits at 1-12 month lookbacks.
2. **Triple Screen is not Elder's system (A, code verified).** Our code takes the stop-entry trigger and the stop from the entry bar (`triple_screen_strategy_service.py:121-128`, `stop_lookback` 5) and re-enters on every flat bar while the setup holds. It defaults to market entry, which drops the third screen. Elder's rules use the middle bar for trigger and stop, with one decision per middle bar. A's own canonical sketch lifts the 5m set from PF 0.84-0.89 to about 1.0: still no edge.

The window itself is a round trip: 4006 to 4055 (+1.2%), high about 5590, low about 3870. Equal long and short PF follows from that. An earlier brief that called it "a strong uptrend" was wrong.

## Leads (hypotheses, not results)

All of them come from about 60 variants tried on one 12-month window, so a pass on the same window proves little.

| Lead | Source | Number | Status |
|---|---|---|---|
| Triple Screen `15m,1h,4h` stop/strategy at today's cost | A, C (accounting re-price of a stored run) | PF about 1.17 | Parameter-only engine rerun possible |
| Canonical Triple Screen, 1h trading bar, 4h tide, tide-flip exit | A (own unreviewed sketch) | PF 1.48, 431 trades, bootstrap 1.09-2.01 | Needs code |

## Agreed next steps

1. Stop testing any strategy with a 1m or 5m signal bar.
2. Run the parameter-only check first: `15m,1h,4h`, `entry_type=stop`, `exit_mode=strategy`, at today's cost, plus `stop_lookback` 2, 5 and 10. Below PF 1.1 kills the lead. A swing of more than 0.15 between neighbours means noise.
3. Any code lead is pre-registered with every number fixed in advance. It is tested on data not used here: older bars (1h history starts 2023-10-31; 1m starts 2025-10-21) or forward paper.
4. Gate on spread 0.08 (owner decision, 2026-11-10).

## Unresolved questions

- Is a code change for canonical Triple Screen (middle-bar trigger and stop, one decision per middle bar) in scope?
