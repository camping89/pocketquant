# Phase 16 report: prod backtests, live set, paper start

## Entry gate (2026-11-02 ~09:00Z)

- EG1 `git status --porcelain -- src web deploy tests scripts docs .github`: empty.
- EG2 HEAD = origin/develop = `3df5ec91465ff41b9b12a00773599167e6e3ed91`.
- EG3 `reports/phase-15-release-d2.md` ends with `Result: PASS`.
- `grep -c "^d2_pushed_at=" reports/phase-15-*.md`: `1`.
- AGNOSTIC: `0`.

## Task 16.1 coverage check

```
first_1m=2025-10-21 bar_calendar=EXNESS_XAUUSD
5m expected=71748 covered=7699 pct=10.73 extra=0 before=0
15m expected=23916 covered=5900 pct=24.67 extra=0 before=0
1h expected=5979 covered=5887 pct=98.46 extra=0 before=11859
4h expected=1611 covered=1591 pct=98.76 extra=0 before=3470
1d expected=311 covered=310 pct=99.68 extra=0 before=2053
worst_pct=10.73
```

Verify: FAILED (`worst_pct=10.73 < 99.00`). No backtest was run.

Read-only diagnostic (per-month coverage %, same calendar-expected set):

```
1m 2025-11:99 2025-12:95 2026-01:95 2026-02:99 2026-03:100 2026-04:95 2026-05:99 2026-06:99 2026-07:99 2026-08:100 2026-09:99 2026-10:100
5m 2025-11:0 ... 2026-08:0 2026-09:27 2026-10:100
15m 2025-11:0 ... 2026-07:0 2026-08:96 2026-09:100 2026-10:100
1h 2025-11:99 2025-12:95 2026-01:95 2026-02:100 2026-03:100 2026-04:95 2026-05:100 2026-06:99 2026-07:99 2026-08:100 2026-09:100 2026-10:100
4h 2025-11:99 2025-12:96 2026-01:96 2026-02:100 2026-03:100 2026-04:96 2026-05:100 2026-06:99 2026-07:99 2026-08:100 2026-09:100 2026-10:100
first_5m=2026-09-23T00:25:00
first_15m=2026-08-03T15:30:00
```

Stored 5m bars start 2026-09-23 and stored 15m bars start 2026-08-03; 1m, 1h and 4h are present across the range with 95 % months in Dec, Jan and Apr.

## Failure Protocol counsel (kongming, 2026-11-02)

Two failures stack in one Verify. Backtests read stored bars at the entry interval (`engine/backtest/backtest_app_service.py:103-105`), and the stored 5m and 15m bars only exist from the 2026-09 REST backfill because the live cascade looks back 100 minutes. The Exness calendar is a weekly template with no holidays (`core/infra/calendars/exness_session_calendar_adapter.py:54-77`), so a flat 99 % against the calendar cannot pass for sub-daily intervals. Counsel: a read-only per-date diagnostic, then one owner [ASK] for a full-range `cascade_for_symbol` and a 1m-anchored pass rule.

Per-date diagnostic (read-only):

```
missing_1m_total=5990 of 358169 dates=99
missing_1m_top=2025-12-25:1329 2026-01-01:1323 2026-04-03:1258 2025-12-24:268 2026-06-19:238 2026-07-03:238 2025-11-28:177 2026-01-19:151 2026-09-07:151 2025-11-27:149 2026-02-16:149 2026-05-25:149 2026-04-02:120 2025-12-31:60 2025-12-07:30
missing_1m_small_dates=85 minutes=230
missing_1h_by_date=2025-11-27:2 2025-11-28:2 2025-12-24:4 2025-12-25:22 2025-12-31:1 2026-01-01:22 2026-01-19:2 2026-02-16:2 2026-04-02:2 2026-04-03:21 2026-05-25:2 2026-06-19:4 2026-07-03:4 2026-09-07:2
5m {'rest_backfill': 4954, 'cascade': 2866}
15m {'rest_backfill': 4985, 'cascade': 956}
1h {'rest_backfill': 17517, 'cascade': 240}
```

The missing 1m minutes sit on US market holidays and early closes, plus 230 scattered minutes over 85 dates. These are venue closures, not sync holes.

coverage_ask=yes (owner, 2026-11-02 ~09:10Z, asked in Vietnamese): (1) back up the `XAUUSD:EXNESS` bars, then run one `cascade_for_symbol("XAUUSD:EXNESS")` from 2025-10-21 to now in the api container as its own process, re-deriving 5m, 15m, 1h, 4h and 1d from the stored 1m bars; (2) amend the Task 16.1 pass rule: expected = the buckets of the minutes that have a stored 1m bar, every interval `pct >= 99.9`, with the calendar `cal_pct` still printed and the holiday dates recorded.

Backup before the cascade: `/opt/pocketquant/backups/backup-xauusd-exness-bars-pre-cascade-20261102T0914.archive` (19.4 MB, mongodump of `bars` filtered to `symbol=XAUUSD:EXNESS`, written with `--gzip`, so restore needs `mongorestore --gzip --archive=...`).

Cascade (`cascade_for_symbol("XAUUSD:EXNESS", lookback_minutes=543434)` run detached in the api container, script `/tmp/cascade.py`):

```
cascade_start=2026-11-02T09:14:46.761423+00:00 lookback_minutes=543434
cascade_counts=5m:73081 15m:24367 1h:6097 4h:1650 1d:323 elapsed_s=983
free_after_cascade=Mem:            3905        2138         411           1        1356        1488
```

## Task 16.1 re-run with the amended pass rule

```
first_1m=2025-10-21 bar_calendar=EXNESS_XAUUSD
5m expected=70575 covered=70575 pct=100.00 cal_pct=98.37 extra=0 before=2383
15m expected=23531 covered=23531 pct=100.00 cal_pct=98.39 extra=0 before=795
1h expected=5887 covered=5887 pct=100.00 cal_pct=98.46 extra=0 before=11859
4h expected=1591 covered=1591 pct=100.00 cal_pct=98.76 extra=0 before=3470
1d expected=310 covered=310 pct=100.00 cal_pct=99.68 extra=0 before=2053
min_1m_cal_pct=98.33
worst_pct=100.00
```

Verify (amended): PASS. `first_1m=2025-10-21 <= 2025-11-03`, `bar_calendar=EXNESS_XAUUSD`, every `pct >= 99.9`, `worst_pct=100.00`, and `before` for 1h, 4h and 1d is 11859, 3470 and 2053 (all at least 36), so no set start is shifted. The calendar coverage gap (`cal_pct` 98.3-99.7) is the missing 1m dates listed above: venue holidays and early closes.

## Task 16.2 backtests
run=1 id=01a19b9a-7ccf-76af-847a-52b2b29062af
run=1 id=01a19b9a-7ccf-76af-847a-52b2b29062af status=finished elapsed_s=234 trades=8516 return=-0.4735615467132248 pf=0.7945436385568514 max_dd=-0.47415764163160534 sharpe=-29.268528759787774 win=0.2841709722874589 error=None
free_after_run=1 Mem:            3905        2310         327           1        1268        1317
run=2 id=01a19b9f-6f8f-775d-8557-a5bbfc582b0d
run=2 id=01a19b9f-6f8f-775d-8557-a5bbfc582b0d status=finished elapsed_s=273 trades=3585 return=-0.259205221134776 pf=0.7794151551323449 max_dd=-0.2595285364002453 sharpe=-13.099406118758662 win=0.22845188284518828 error=None
free_after_run=2 Mem:            3905        2337         300           1        1268        1289
run=3 id=01a19ba4-36bc-7729-8c42-35e009be2822
run=3 id=01a19ba4-36bc-7729-8c42-35e009be2822 status=finished elapsed_s=85 trades=2479 return=-0.15662191951819113 pf=0.9315255714384646 max_dd=-0.15925441265351648 sharpe=-8.226453237997724 win=0.29850746268656714 error=None
free_after_run=3 Mem:            3905        2328         315           1        1262        1299
run=4 id=01a19ba6-2f0e-73e6-9a2e-22ea60e177c7
run=4 id=01a19ba6-2f0e-73e6-9a2e-22ea60e177c7 status=finished elapsed_s=84 trades=933 return=-0.03239126422352947 pf=1.1421289978180587 max_dd=-0.03336852247672756 sharpe=-1.189856252716386 win=0.2497320471596999 error=None
free_after_run=4 Mem:            3905        2296         356           1        1253        1331
run=5 id=01a19ba8-20a9-72ff-b416-38a86326157a
run=5 id=01a19ba8-20a9-72ff-b416-38a86326157a status=finished elapsed_s=21 trades=707 return=-0.07547608564180865 pf=0.8108784958388617 max_dd=-0.07790019610697746 sharpe=-3.724267505780358 win=0.26732673267326734 error=None
free_after_run=5 Mem:            3905        2316         332           1        1256        1310
run=6 id=01a19ba8-aa56-70b6-8012-7e3e04317a06
run=6 id=01a19ba8-aa56-70b6-8012-7e3e04317a06 status=finished elapsed_s=20 trades=275 return=-0.052095016077114635 pf=0.6856476899668138 max_dd=-0.053110814804122754 sharpe=-2.295091514646561 win=0.20363636363636364 error=None
free_after_run=6 Mem:            3905        2328         319           1        1258        1298

No run of the `5m,15m,1h` set exceeded 1800 s (run 1: 234 s, run 2: 273 s), so no `cost_ask` was needed.

Task 16.2 Verify: `6` finished lines, `6` free_after_run lines (see below).

## Task 16.3 metrics table and compare views

Range `2025-11-03..2026-10-30`, `XAUUSD:EXNESS`, Triple Screen, defaults except `entry_type` and `exit_mode`.

| # | intervals | entry_type | exit_mode | run id | elapsed_s | trades | total_return | profit_factor | max_drawdown | sharpe | win_rate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5m 15m 1h | market | sl_tp | 01a19b9a-7ccf-76af-847a-52b2b29062af | 234 | 8516 | -0.4736 | 0.7945 | -0.4742 | -29.27 | 0.2842 |
| 2 | 5m 15m 1h | stop | strategy | 01a19b9f-6f8f-775d-8557-a5bbfc582b0d | 273 | 3585 | -0.2592 | 0.7794 | -0.2595 | -13.10 | 0.2285 |
| 3 | 15m 1h 4h | market | sl_tp | 01a19ba4-36bc-7729-8c42-35e009be2822 | 85 | 2479 | -0.1566 | 0.9315 | -0.1593 | -8.23 | 0.2985 |
| 4 | 15m 1h 4h | stop | strategy | 01a19ba6-2f0e-73e6-9a2e-22ea60e177c7 | 84 | 933 | -0.0324 | 1.1421 | -0.0334 | -1.19 | 0.2497 |
| 5 | 1h 4h 1d | market | sl_tp | 01a19ba8-20a9-72ff-b416-38a86326157a | 21 | 707 | -0.0755 | 0.8109 | -0.0779 | -3.72 | 0.2673 |
| 6 | 1h 4h 1d | stop | strategy | 01a19ba8-aa56-70b6-8012-7e3e04317a06 | 20 | 275 | -0.0521 | 0.6856 | -0.0531 | -2.30 | 0.2036 |

Compare views (each set with both settings, then each setting across sets):

https://pocketquant.xyz/backtest/compare?runs=01a19b9a-7ccf-76af-847a-52b2b29062af,01a19b9f-6f8f-775d-8557-a5bbfc582b0d
https://pocketquant.xyz/backtest/compare?runs=01a19ba4-36bc-7729-8c42-35e009be2822,01a19ba6-2f0e-73e6-9a2e-22ea60e177c7
https://pocketquant.xyz/backtest/compare?runs=01a19ba8-20a9-72ff-b416-38a86326157a,01a19ba8-aa56-70b6-8012-7e3e04317a06
https://pocketquant.xyz/backtest/compare?runs=01a19b9a-7ccf-76af-847a-52b2b29062af,01a19ba4-36bc-7729-8c42-35e009be2822,01a19ba8-20a9-72ff-b416-38a86326157a
https://pocketquant.xyz/backtest/compare?runs=01a19b9f-6f8f-775d-8557-a5bbfc582b0d,01a19ba6-2f0e-73e6-9a2e-22ea60e177c7,01a19ba8-aa56-70b6-8012-7e3e04317a06

## Task 16.4 owner pick

live_set=15m,1h,4h
live_set_owner_answer=all three sets on paper (owner, 2026-11-02 ~10:05Z, asked in Vietnamese; English rendering): 15m,1h,4h | 1h,4h,1d | 5m,15m,1h, one paper subscription per set, each entry_type=stop exit_mode=strategy; amends D4 (one paper subscription). Primary for the Task 16.5-16.6 and Phase 17 contracts: 15m,1h,4h, the recommended set (run 4 has the highest profit_factor, 1.142 over 933 trades, among the entry_type=stop, exit_mode=strategy runs with at least 30 trades); the owner added the other two without naming a primary.

The three subscriptions share one pooled paper broker and so one paper account balance (`strategy_app_service.py:812,856-857`, `paper_broker_adapter.py` keys positions by `subscription_id:symbol`). Positions and resting stops are isolated per subscription; account-level risk is up to three times one subscription's, and paper results per set must be read from per-subscription trades (`trades.run_id`), not account equity.

## Task 16.5 paper subscriptions

The Task 16.5 script ran once per set, primary first.

paper_started_at=2026-11-02T10:12:24Z
paper_sub_id=01a19bbf-0b3a-70e3-903e-f93e361acbf8
state=running/running broker=paper intervals_key=15m,1h,4h parameters={"entry_type": "stop", "exit_mode": "strategy"}
extra_paper_sub=1h,4h,1d id=01a19bbf-9788-7487-8c7e-9f110ed8c595 started_at=2026-11-02T10:13:00Z
extra_state=1h,4h,1d state=running/running broker=paper intervals_key=1h,4h,1d parameters={"entry_type": "stop", "exit_mode": "strategy"}
extra_paper_sub=5m,15m,1h id=01a19bc0-26ec-76ba-b83e-edeb84f021d4 started_at=2026-11-02T10:13:36Z
extra_state=5m,15m,1h state=running/running broker=paper intervals_key=5m,15m,1h parameters={"entry_type": "stop", "exit_mode": "strategy"}
free_after_paper_start=Mem:            3905        2322         318           1        1265        1305

Task 16.5 Verify: PASS for the primary and both extras.

## Task 16.6 snapshot rings (2026-11-02 13:19Z)

The wait ran to 13:16Z, the latest of the three `started_at + 3 x <entry interval> + 2 min` (the `1h,4h,1d` set).

entries=20 live_entries=12 live_distinct_bar_start=12
{"bar_start": "2026-11-02T13:00:00+00:00", "decision": {"action": "hold", "reason": "position held"}, "interval": "15m", "outcome": "no_signal", "pending": null, "readings": [{"interval": "4h", "name": "macd_hist_slope", "ok": true, "value": 2.133867328405316}, {"interval": "1h", "name": "force_index", "ok": false, "value": 3079.725041910404}, {"interval": "15m", "name": "trigger", "ok": false, "v
extra_ring=1h,4h,1d entries=20 live_entries=2 live_distinct_bar_start=2
extra_ring=5m,15m,1h entries=20 live_entries=20 live_distinct_bar_start=20

Last live entries of the extras (first 400 characters):

```
1h,4h,1d: {"bar_start": "2026-11-02T12:00:00+00:00", "decision": {"action": "exit", "reason": "setup gone"}, "interval": "1h", "outcome": "sent", "pending": null, "readings": [{"interval": "1d", "name": "macd_hist_slope", "ok": true, "value": -2.5083351682013983}, {"interval": "4h", "name": "force_index", "ok": false, "value": -28192.85335755811}, {"interval": "1h", "name": "trigger", "ok": true, "value": n
5m,15m,1h: {"bar_start": "2026-11-02T13:10:00+00:00", "decision": {"action": "hold", "reason": "position held"}, "interval": "5m", "outcome": "no_signal", "pending": null, "readings": [{"interval": "1h", "name": "macd_hist_slope", "ok": true, "value": 0.006618375289107803}, {"interval": "15m", "name": "force_index", "ok": true, "value": -2366.9834201804083}, {"interval": "5m", "name": "trigger", "ok": false,
```

Task 16.6 Verify: PASS. The primary line matches the regex with 12 distinct live `bar_start` values, and both `extra_ring=` lines show at least 2. The primary and the `5m,15m,1h` subscription already hold a position, and the `1h,4h,1d` subscription sent a strategy EXIT on its 12:00 bar; Phase 17 collects the order and trade ids.

`.cache/ssh/vps_key` removed.

Result: PASS
