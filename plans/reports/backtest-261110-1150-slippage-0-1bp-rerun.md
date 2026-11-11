# Rerun of the four 1m backtests at 0.1 bp slippage

Commit `481fafe3` lowered the default slippage from 0.5 bp to 0.1 bp for backtests and paper. It was released to master on 2026-11-10, and master CI passed. The four runs of the closed plan `plans/archive/261109-1349-1m-strategy-evidence/` were rerun on prod with the same parameters. Spread stayed at 0.08 and commission at 0.035 per oz per side. The run names end in `slippage_bps=0.1`.

All four runs still fail the gate (net `profit_factor >= 1.2` and `total_trades >= 100`).

| Run | Set | Old PF (0.5 bp) | New PF (0.1 bp) | Trades | New win rate | New return | New max DD | New run id |
|---|---|---|---|---|---|---|---|---|
| r1 | ts-1m-5m-15m market/sl_tp | 0.663 | 0.843 | 36 847 | 29.0% | -17.6% | -17.7% | 01a1c371-2049-7008-b633-495e51b166a8 |
| r2 | ts-1m-5m-15m stop/strategy | 0.746 | 0.885 | 14 943 | 21.1% | -7.6% | -8.1% | 01a1c389-d69b-76f4-a6a8-f64d8f8d1a36 |
| r3 | ts-1m-15m-1h market/sl_tp | 0.673 | 0.834 | 27 265 | 28.8% | -15.7% | -15.8% | 01a1c3a0-31b6-74b1-b710-fde5f248eeff |
| r4 | ts-1m-15m-1h stop/strategy | 0.710 | 0.811 | 7 798 | 13.8% | -8.3% | -8.5% | 01a1c3b7-14d8-722f-bdf8-690bb6b12285 |

Trade counts match the old runs exactly, so only fill prices changed.

The diagnosis in `kongming-261110-0915-1m-strategy-failure-diagnosis.md` estimated a zero-slippage PF of 0.902 for r1 and 0.928 for r2. The new values fall between the old runs and those estimates, which is what a 0.1 bp slippage predicts (inference).

The runs did not follow the closed plan's backtest window rule (decision D8), on the owner's instruction. They ran one at a time. All temporary scripts were removed from the VPS and the api container.

## Unresolved questions

- Whether 0.08 (seeded Raw spread) or 0.168 (the measured median ask-bid on the prod account) is the right gold spread.
- The next strategy direction, since no set clears the gate even at lower cost.
