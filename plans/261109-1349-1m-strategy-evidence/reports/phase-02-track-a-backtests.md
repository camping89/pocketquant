# Phase 02 report: Track A Triple Screen 1m backtests

## Entry gate

- EG(1) `git status --porcelain -- src web deploy tests scripts docs .github`: empty.
- EG(2) HEAD equals origin/develop: `synced`.
- EG(3) `reports/phase-01-coverage-and-baseline.md` last line: `Result: PASS`.
- EG(4) `grep -c "^existing_sub "` on the Phase 01 report: `3`.
- WINDOW before r1: `window_ok=yes utc=13:45`.

## Runs

run=r1 set=ts-1m-5m-15m id=01a1c08f-12fd-75ab-977e-b45fc4833189
run=r1 set=ts-1m-5m-15m id=01a1c08f-12fd-75ab-977e-b45fc4833189 status=finished elapsed_s=1219 trades=36847 pf=0.6630988966404225 return=-0.3861175881957187 max_dd=-0.3862679040504075 win=0.27416071864737973 gate=fail error=None
free_after_run=r1 Mem:            3905        2754         347           1         804         883
run=r2 set=ts-1m-5m-15m id=01a1c0a6-6cf3-77cc-9c03-b5ae6b15f60b
run=r2 set=ts-1m-5m-15m id=01a1c0a6-6cf3-77cc-9c03-b5ae6b15f60b status=finished elapsed_s=1224 trades=14943 pf=0.7462300711017726 return=-0.1801642706692026 max_dd=-0.18250101956190143 win=0.19467309107943517 gate=fail error=None
free_after_run=r2 Mem:            3905        2613         386           1         905        1023
run=r3 set=ts-1m-15m-1h id=01a1c0bc-7d0a-7573-a893-b3a07953ba6c
run=r3 set=ts-1m-15m-1h id=01a1c0bc-7d0a-7573-a893-b3a07953ba6c status=finished elapsed_s=1191 trades=27265 pf=0.673485099307977 return=-0.3225762036108163 max_dd=-0.3228394913132313 win=0.27346414817531634 gate=fail error=None
free_after_run=r3 Mem:            3905        2560         439           1         906        1077
run=r4 set=ts-1m-15m-1h id=01a1c0d2-6302-765f-99c6-7b2bd5c12946
run=r4 set=ts-1m-15m-1h id=01a1c0d2-6302-765f-99c6-7b2bd5c12946 status=finished elapsed_s=1206 trades=7798 pf=0.7098467853326118 return=-0.1386534903863292 max_dd=-0.13969692001557693 win=0.13362400615542447 gate=fail error=None
free_after_run=r4 Mem:            3905        2508         440           1         956        1128

No run exceeded 1800 s, so no `cost_ask=` was needed.

## Run table

| # | set | intervals | entry_type | exit_mode | run id | elapsed_s | trades | total_return | profit_factor | max_drawdown | win_rate | gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r1 | ts-1m-5m-15m | 1m 5m 15m | market | sl_tp | 01a1c08f-12fd-75ab-977e-b45fc4833189 | 1219 | 36847 | -0.3861 | 0.6631 | -0.3863 | 0.2742 | fail |
| r2 | ts-1m-5m-15m | 1m 5m 15m | stop | strategy | 01a1c0a6-6cf3-77cc-9c03-b5ae6b15f60b | 1224 | 14943 | -0.1802 | 0.7462 | -0.1825 | 0.1947 | fail |
| r3 | ts-1m-15m-1h | 1m 15m 1h | market | sl_tp | 01a1c0bc-7d0a-7573-a893-b3a07953ba6c | 1191 | 27265 | -0.3226 | 0.6735 | -0.3228 | 0.2735 | fail |
| r4 | ts-1m-15m-1h | 1m 15m 1h | stop | strategy | 01a1c0d2-6302-765f-99c6-7b2bd5c12946 | 1206 | 7798 | -0.1387 | 0.7098 | -0.1397 | 0.1336 | fail |

https://pocketquant.xyz/backtest/compare?runs=01a1c08f-12fd-75ab-977e-b45fc4833189,01a1c0a6-6cf3-77cc-9c03-b5ae6b15f60b
https://pocketquant.xyz/backtest/compare?runs=01a1c0bc-7d0a-7573-a893-b3a07953ba6c,01a1c0d2-6302-765f-99c6-7b2bd5c12946

verdict: ts-1m-5m-15m fail r1:pf=0.6630988966404225,trades=36847,gate=fail r2:pf=0.7462300711017726,trades=14943,gate=fail
verdict: ts-1m-15m-1h fail r3:pf=0.673485099307977,trades=27265,gate=fail r4:pf=0.7098467853326118,trades=7798,gate=fail

## Existing subscriptions

SUBSCHECK after r4 returned the same three lines as Phase 01; SUBSDIFF output:

subs_unchanged

## Observations

All four Track A runs fail the gate on profit_factor (0.66-0.75, net of the seeded spec costs); every run has far more than 100 trades. Both Track A sets get verdict fail, so neither goes to paper in Phase 06. The .cache/ssh/vps_key copy was removed after the last prod call.

Advisory note (kongming estimate, not measured from `backtest_trades`): the 10% exposure cap likely binds at about 0.25 oz per trade, so the seeded round-trip cost is about 0.04 USD per trade against r1's net loss of about 0.105 USD per trade. If that holds, Track A fails on both cost drag and gross edge, and the 1m entry made profit_factor worse than the 5m sets of the earlier Phase 16 runs (0.66-0.75 against 0.78-0.79). This changes no owner decision and no Triple Screen logic.

Result: PASS
