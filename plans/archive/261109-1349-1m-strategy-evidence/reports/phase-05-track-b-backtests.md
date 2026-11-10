# Phase 05 report: Track B hitnrun2 backtests

## Entry gate

- EG(1) `git status --porcelain -- src web deploy tests scripts docs .github`: empty.
- EG(2) HEAD equals origin/develop: `synced` (HEAD `e9b7e443`).
- EG(3) `reports/phase-04-release-hitnrun2.md` last line: `Result: PASS`.
- EG(4) `grep -c "^prod_has_hitnrun2=yes"` on the Phase 04 report: `1`.

## Lower min_profit_pct

min_profit_low=0.005
source: owner decision D7 (validation 2026-11-09)

## Runs

WINDOW before r5: `window_ok=yes utc=00:47`.

run=r5 set=hitnrun2-1m id=01a1c2ed-2cc3-77e1-bfb5-2184fdae5ffc
run=r5 set=hitnrun2-1m id=01a1c2ed-2cc3-77e1-bfb5-2184fdae5ffc status=finished elapsed_s=78 trades=344 pf=0.784388706700011 return=-0.03003009010356509 max_dd=-0.03578802033335869 win=0.15988372093023256 gate=fail error=None
free_after_run=r5 Mem:            3905        2149         658           1        1098        1487
run=r6 set=hitnrun2-1m id=01a1c2ef-21f3-727d-b733-6485b0b65c23
run=r6 set=hitnrun2-1m id=01a1c2ef-21f3-727d-b733-6485b0b65c23 status=finished elapsed_s=82 trades=668 pf=0.8811049737211203 return=-0.01814244448718928 max_dd=-0.029485044729614086 win=0.35479041916167664 gate=fail error=None
free_after_run=r6 Mem:            3905        2180         625           1        1100        1457

No run exceeded 1800 s, so no `cost_ask=` was needed.

## Run table

| # | set | intervals | min_profit_pct | run id | elapsed_s | trades | total_return | profit_factor | max_drawdown | win_rate | gate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| r5 | hitnrun2-1m | 1m | 0.02 | 01a1c2ed-2cc3-77e1-bfb5-2184fdae5ffc | 78 | 344 | -0.0300 | 0.7844 | -0.0358 | 0.1599 | fail |
| r6 | hitnrun2-1m | 1m | 0.005 | 01a1c2ef-21f3-727d-b733-6485b0b65c23 | 82 | 668 | -0.0181 | 0.8811 | -0.0295 | 0.3548 | fail |

https://pocketquant.xyz/backtest/compare?runs=01a1c2ed-2cc3-77e1-bfb5-2184fdae5ffc,01a1c2ef-21f3-727d-b733-6485b0b65c23

verdict: hitnrun2-1m fail r5:pf=0.784388706700011,trades=344,gate=fail r6:pf=0.8811049737211203,trades=668,gate=fail

## Existing subscriptions

SUBSCHECK after r6 returned the same three lines as Phase 01; SUBSDIFF output:

subs_unchanged

## Observations

Both hitnrun2 runs fail the gate on profit_factor (0.78 and 0.88, net of the seeded spec costs); both clear 100 trades (344 and 668). The `hitnrun2-1m` set gets verdict fail, so it does not go to paper in Phase 06. The lower `min_profit_pct=0.005` roughly doubled the trade count and raised the win rate from 0.16 to 0.35, but profit_factor stays below 1.2. Each run took about 80 s, far below the 1800 s ask. The .cache/ssh/vps_key copy was removed after the last prod call.

Advisory note (kongming go/no-go after the phase, inference, not measured): each run took about 80 s against about 1200 s for Triple Screen; the cause was not measured (one interval instead of three and far fewer trades are candidates). If the position size is about 0.25 oz as estimated in Phase 02, the round-trip cost is about 0.04 USD per trade against a net loss of about 0.87 (r5) and 0.27 (r6) per trade, so the fail is gross edge rather than cost. Risk R4 did not occur: both runs clear 100 trades and fail on profit_factor alone. With all three sets at verdict fail, Phase 06 takes its no-passing-set path (`paper_plan=none`); AC6 is last measured here and AC7 in Phase 04.

Result: PASS
