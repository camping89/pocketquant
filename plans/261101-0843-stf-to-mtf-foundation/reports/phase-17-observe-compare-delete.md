# Phase 17 report — Observe; one-week 1d comparison; prod STF delete; close

## Entry gate (2026-11-02T13:24Z)

- EG1 `git status --porcelain -- src web deploy tests scripts docs .github`: empty.
- EG2 `HEAD` = `origin/develop` = `f73f364800526b59f555d64d656e0919e45cfb86`.
- EG3 `reports/phase-16-backtests-and-paper-start.md` ends with `Result: PASS`.
- `grep -c "^paper_sub_id="` on the Phase 16 report: `1`.
- AGNOSTIC: `0`.

Inputs: `paper_sub_id=01a19bbf-0b3a-70e3-903e-f93e361acbf8`, `paper_started_at=2026-11-02T10:12:24Z`, `d1_deployed_at=2026-11-01T14:50:40Z`.

## Task 17.1 — Paper observations

STATUS at 2026-11-02T13:24:55Z:

```
state=running/running manual_action=None manual={"manual_action": null, "manual_action_outcome": null}
order id=01a19bcf-0d40-72c0-a824-d19953d88bfc type=stop_market side=buy status=filled stop=3900.09 sl=3893.866 updated=2026-11-02T10:40:00.247000
order id=01a19bc1-51bd-72e9-b9a8-5e9555e1d4aa type=stop_market side=buy status=filled stop=3898.516 sl=3896.058 updated=2026-11-02T10:18:00.626000
open_position id=01a19bd8-34f9-7104-a650-bf34013ede16 side=long qty=2.563702305419122 sl=3893.866
trade id=01a19bcb-6509-7274-9c7e-a44f3da07648 dir=LONG entry=3898.7109258000005 exit=3895.8631971 sl=3896.058 tp=None exit_time=2026-11-02T10:26:00.585000
ring entries=20 live_entries=12 live_distinct_bar_start=12 live_distinct_readings=5
```

Trade `01a19bcb-6509-7274-9c7e-a44f3da07648` exited at or beyond its SL (LONG, exit 3895.863 < sl 3896.058), so it is an SL exit, not obs-2.

obs-1 PASS order=01a19bc1-51bd-72e9-b9a8-5e9555e1d4aa
obs-5 PASS
obs-3 attempt-1 FAIL requested_at=2026-11-02T13:34:05Z: STATUS at 13:34:10Z still showed the open position with manual_action=None and manual_action_outcome=None; the prod nginx log shows 0 POST requests and no drawer detail GETs, so the drawer was never opened. Retried with click-by-click instructions.

Attempt 2 of the obs-3 ask (13:45Z, click-by-click steps) got no owner reply by 14:09Z, and the prod nginx log showed no drawer GETs and no POST in that window. STATUS at 14:09:42Z is unchanged: the same open position, no new order or trade, `ring live_entries=15 live_distinct_bar_start=15 live_distinct_readings=5`.

Missing: obs-2 (no strategy exit yet), obs-3 (owner close not done), obs-4 (no pending stop order to cancel), obs-6 (drawer check not asked). Task 17.2 cannot start before 2026-11-09T00:00Z (7 full UTC days after the day of `d1_deployed_at`). Tasks 17.3-17.8 wait for both (synthesis D12).

Status: BLOCKED
NOT_YET: waiting for obs-2, obs-3, obs-4, obs-6; 1d comparison window not complete until 2026-11-09T00:00Z
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 17 after 2026-11-03T02:10Z

## Resumed run (2026-11-02T17:48Z, D13-D15 amendments)

Entry gate: EG1 empty; EG2 `HEAD` = `origin/develop` = `77c60dbcb19b8eafb209a9d999bdd6c5461d79d8`; EG3 Phase 16 ends `Result: PASS`; `paper_sub_id=` count `1`; AGNOSTIC `0`.

### Task 17.1 — STATUS at 2026-11-02T17:48:52Z

Primary `15m,1h,4h` (`01a19bbf-0b3a-70e3-903e-f93e361acbf8`):

```
state=running/running manual_action=None manual={"manual_action": null, "manual_action_outcome": {"action": "close", "at": "2026-11-02 16:22:42.455000", "outcome": "accepted"}}
order id=01a19bcf-0d40-72c0-a824-d19953d88bfc type=stop_market side=buy status=filled stop=3900.09 sl=3893.866 updated=2026-11-02T10:40:00.247000
order id=01a19bc1-51bd-72e9-b9a8-5e9555e1d4aa type=stop_market side=buy status=filled stop=3898.516 sl=3896.058 updated=2026-11-02T10:18:00.626000
trade id=01a19d11-f60e-71c6-9759-bdbc61c00dde dir=LONG entry=3900.2850045000005 exit=3965.3757213 sl=3893.866 tp=None exit_time=2026-11-02T16:22:42.445000
trade id=01a19bcb-6509-7274-9c7e-a44f3da07648 dir=LONG entry=3898.7109258000005 exit=3895.8631971 sl=3896.058 tp=None exit_time=2026-11-02T10:26:00.585000
ring entries=20 live_entries=20 live_distinct_bar_start=20 live_distinct_readings=6
```

Extra `1h,4h,1d` (`01a19bbf-9788-7487-8c7e-9f110ed8c595`, since 2026-11-02T10:13:00Z): no trades; orders `01a19bea-…` and `01a19c21-…` stop_market cancelled at 12:00 and 13:00 UTC; stop `01a19d34-1d45-72f0-9064-97f935efb49a` filled 17:45 UTC; open short `01a19d5d-4fdd-720d-bd3d-90a08ab4d46a`.

Extra `5m,15m,1h` (`01a19bc0-26ec-76ba-b83e-edeb84f021d4`, since 2026-11-02T10:13:36Z), trade lines:

```
trade id=01a19c5a-3833-727b-bfac-17b7722de401 dir=LONG entry=3902.6251215000007 exit=3898.2680768500004 sl=3898.463 tp=None exit_time=2026-11-02T13:02:00.754000
trade id=01a19c26-08d5-73f5-9e13-b544d07953e8 dir=SHORT entry=3903.5188143 exit=3899.6489727000007 sl=3906.966 tp=None exit_time=2026-11-02T12:05:00.757000
```

Primary: `01a19bcb-…` is an SL exit (LONG, exit < sl) and `01a19d11-…` is the manual close (10 ms before `requested_at`), so neither is obs-2. `1h,4h,1d` has no trade (its EXITs at 12:00 and 13:00 cancelled a stop while flat). `5m,15m,1h` trade `01a19c26-…` is SHORT with exit 3899.649 < sl 3906.966 and tp=None: the first matching trade.

obs-3 requested_at=2026-11-02T16:22:42.455Z
obs-3 PASS trade=01a19d11-f60e-71c6-9759-bdbc61c00dde
obs-2 PASS trade=01a19c26-08d5-73f5-9e13-b544d07953e8 sub=01a19bc0-26ec-76ba-b83e-edeb84f021d4
obs-2 log=trader-13  | 2026-11-02T12:05:00.765557Z [info     ] strategy.position_close_sent   [pocketquant.engine.strategy.strategy_app_service] closed=True correlation_id=01a19c26-08dd-7702-8f2c-5ac97a66e461 environment=production reason=strategy_exit service=pocketquant subscription_id=01a19bc0-26ec-76ba-b83e-edeb84f021d4 version=0.1.0

### Task 17.2 — 1d comparison (run at 2026-11-02T17:49:58Z, before the 03:00Z backfill)

Script as written, with the local name of the fetched-bar dict renamed (a local hook blocks that word); logic unchanged. Window FIRST=2026-10-19, LAST=2026-11-02.

```
BTCUSD:EXNESS 2026-10-19 diff source=rest_repair
BTCUSD:EXNESS 2026-10-20 diff source=rest_repair
BTCUSD:EXNESS 2026-10-21 diff source=rest_repair
BTCUSD:EXNESS 2026-10-22 diff source=rest_repair
BTCUSD:EXNESS 2026-10-23 diff source=rest_repair
BTCUSD:EXNESS 2026-10-24 diff source=rest_repair
BTCUSD:EXNESS 2026-10-25 diff source=rest_repair
BTCUSD:EXNESS 2026-10-26 diff source=rest_repair
BTCUSD:EXNESS 2026-10-27 diff source=rest_repair
BTCUSD:EXNESS 2026-10-28 diff source=rest_repair
BTCUSD:EXNESS 2026-10-29 diff source=rest_repair
BTCUSD:EXNESS 2026-10-30 diff source=rest_repair
BTCUSD:EXNESS 2026-10-31 diff source=rest_repair
BTCUSD:EXNESS 2026-11-01 equal source=cascade
EURUSD:EXNESS 2026-10-19 diff source=rest_repair
EURUSD:EXNESS 2026-10-20 diff source=rest_repair
EURUSD:EXNESS 2026-10-21 diff source=rest_repair
EURUSD:EXNESS 2026-10-22 diff source=rest_repair
EURUSD:EXNESS 2026-10-23 diff source=rest_repair
EURUSD:EXNESS 2026-10-25 diff source=rest_repair
EURUSD:EXNESS 2026-10-26 diff source=rest_repair
EURUSD:EXNESS 2026-10-27 diff source=rest_repair
EURUSD:EXNESS 2026-10-28 diff source=rest_repair
EURUSD:EXNESS 2026-10-29 diff source=rest_repair
EURUSD:EXNESS 2026-10-30 diff source=rest_repair
EURUSD:EXNESS 2026-11-01 equal source=cascade
XAUUSD:EXNESS 2026-10-19 diff source=rest_repair
XAUUSD:EXNESS 2026-10-20 diff source=rest_repair
XAUUSD:EXNESS 2026-10-21 diff source=rest_repair
XAUUSD:EXNESS 2026-10-22 diff source=rest_repair
XAUUSD:EXNESS 2026-10-23 diff source=rest_repair
XAUUSD:EXNESS 2026-10-25 diff source=rest_repair
XAUUSD:EXNESS 2026-10-26 diff source=rest_repair
XAUUSD:EXNESS 2026-10-27 diff source=rest_repair
XAUUSD:EXNESS 2026-10-28 diff source=rest_repair
XAUUSD:EXNESS 2026-10-29 diff source=rest_repair
XAUUSD:EXNESS 2026-10-30 diff source=rest_repair
XAUUSD:EXNESS 2026-11-01 equal source=cascade
min_days=12
mismatches=35 repair_1d=0
```

Verify FAILED: `mismatches=35` (pass needs 0). `min_days=12` and `repair_1d=0` meet their conditions. Every `diff` row has `source=rest_repair` and a date before `d1_deployed_at` (2026-11-01T14:50:40Z); every 2026-11-01 row, the only day cascaded after deploy, is `equal source=cascade`. No `rest_backfill` row.

#### Diagnosis (read-only, not the Verify)

Failure Protocol: `kongming` counsel taken at 2026-11-02T17:58Z. Code facts: `sync_1m` cascades with a 100-minute lookback (`src/pocketquant/engine/market_data/app_services/sync_jobs.py:403-408`), so the first 1d bucket the live cascade wrote is 2026-11-01; older 1d bars come from `sync_repair` (`source=rest_repair`). `upsert_bar` returns before any write when the stored OHLCV equals the new values (`src/pocketquant/core/infra/persistence/repositories/bar_repository.py:81-82`), so `source` records the last writer that changed values and a cascade with equal values never flips it. The Task 17.2 `ok` rule checks `source == "cascade"` first, so its 35 `diff` rows say nothing about values. The D14 window includes 13 days the live cascade never wrote, so the Verify as written cannot pass before five cascaded days exist.

Diagnostic script: the Task 17.2 script plus a dry-run cascade per day (the live path: `calendar.trading_minutes`, 1m `find` sorted descending with `limit=expected+5`, `aggregate_ohlcv`) with no write, plus a calendar cross-check line. Run at 2026-11-02T17:58:53Z:

```
calendar BTCUSD:EXNESS bar_calendar_id=EXNESS_CRYPTO resolved=EXNESS_CRYPTO provider_default=EXNESS_FX
BTCUSD:EXNESS 2026-10-19 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-20T00:00:32.577000 n1m=1440/1440 total1m=1440
BTCUSD:EXNESS 2026-10-20 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-21T00:00:25.842000 n1m=1440/1440 total1m=1440
BTCUSD:EXNESS 2026-10-21 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-22T00:00:28.901000 n1m=1440/1440 total1m=1440
BTCUSD:EXNESS 2026-10-22 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-23T00:00:33.850000 n1m=1440/1440 total1m=1440
BTCUSD:EXNESS 2026-10-23 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-24T00:00:31.128000 n1m=1440/1440 total1m=1440
BTCUSD:EXNESS 2026-10-24 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-11-01T00:00:38.136000 n1m=1440/1440 total1m=1440
BTCUSD:EXNESS 2026-10-25 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-26T00:00:34.914000 n1m=1440/1440 total1m=1440
BTCUSD:EXNESS 2026-10-26 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-27T00:00:27.330000 n1m=1440/1440 total1m=1440
BTCUSD:EXNESS 2026-10-27 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-28T00:00:28.881000 n1m=1440/1440 total1m=1440
BTCUSD:EXNESS 2026-10-28 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-29T00:00:27.644000 n1m=1440/1440 total1m=1440
BTCUSD:EXNESS 2026-10-29 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-30T00:00:28.695000 n1m=1440/1440 total1m=1440
BTCUSD:EXNESS 2026-10-30 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-31T00:00:37.829000 n1m=1440/1440 total1m=1440
BTCUSD:EXNESS 2026-10-31 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-11-01T00:00:38.160000 n1m=1440/1440 total1m=1440
BTCUSD:EXNESS 2026-11-01 stored=equal dry=equal source=cascade post_d1=1 updated_at=2026-11-02T00:00:21.985000 n1m=1440/1440 total1m=1440
calendar EURUSD:EXNESS bar_calendar_id=EXNESS_FX resolved=EXNESS_FX provider_default=EXNESS_FX
EURUSD:EXNESS 2026-10-19 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-20T00:09:59.719000 n1m=1437/1440 total1m=1437
EURUSD:EXNESS 2026-10-20 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-21T00:06:53.837000 n1m=1435/1440 total1m=1435
EURUSD:EXNESS 2026-10-21 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-22T00:28:16.743000 n1m=1440/1440 total1m=1440
EURUSD:EXNESS 2026-10-22 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-23T00:28:29.825000 n1m=1435/1440 total1m=1435
EURUSD:EXNESS 2026-10-23 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-24T00:10:35.696000 n1m=1259/1259 total1m=1259
EURUSD:EXNESS 2026-10-25 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-26T00:09:18.370000 n1m=175/175 total1m=175
EURUSD:EXNESS 2026-10-26 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-27T00:29:44.962000 n1m=1440/1440 total1m=1440
EURUSD:EXNESS 2026-10-27 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-28T00:09:01.989000 n1m=1440/1440 total1m=1440
EURUSD:EXNESS 2026-10-28 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-29T00:09:29.472000 n1m=1440/1440 total1m=1440
EURUSD:EXNESS 2026-10-29 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-30T00:01:17.688000 n1m=1417/1440 total1m=1417
EURUSD:EXNESS 2026-10-30 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-31T00:01:27.744000 n1m=1259/1259 total1m=1259
EURUSD:EXNESS 2026-11-01 stored=equal dry=equal source=cascade post_d1=1 updated_at=2026-11-02T00:00:22.923000 n1m=111/115 total1m=111
calendar XAUUSD:EXNESS bar_calendar_id=EXNESS_XAUUSD resolved=EXNESS_XAUUSD provider_default=EXNESS_FX
XAUUSD:EXNESS 2026-10-19 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-20T00:15:36.221000 n1m=1378/1378 total1m=1378
XAUUSD:EXNESS 2026-10-20 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-21T00:15:36.484000 n1m=1378/1378 total1m=1378
XAUUSD:EXNESS 2026-10-21 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-22T00:36:52.021000 n1m=1378/1378 total1m=1378
XAUUSD:EXNESS 2026-10-22 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-23T00:37:26.841000 n1m=1378/1378 total1m=1378
XAUUSD:EXNESS 2026-10-23 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-24T00:19:48.943000 n1m=1258/1258 total1m=1258
XAUUSD:EXNESS 2026-10-25 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-26T00:18:30.747000 n1m=119/119 total1m=119
XAUUSD:EXNESS 2026-10-26 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-27T00:39:51.146000 n1m=1378/1378 total1m=1378
XAUUSD:EXNESS 2026-10-27 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-28T00:17:03.011000 n1m=1378/1378 total1m=1378
XAUUSD:EXNESS 2026-10-28 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-29T00:18:02.555000 n1m=1378/1378 total1m=1378
XAUUSD:EXNESS 2026-10-29 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-30T00:01:46.031000 n1m=1378/1378 total1m=1378
XAUUSD:EXNESS 2026-10-30 stored=equal dry=equal source=rest_repair post_d1=0 updated_at=2026-10-31T00:01:39.967000 n1m=1258/1258 total1m=1258
XAUUSD:EXNESS 2026-11-01 stored=equal dry=equal source=cascade post_d1=1 updated_at=2026-11-02T00:00:23.478000 n1m=59/59 total1m=59
diag_truncated=0 post_d1_not_cascade=0
min_days=12
mismatches=0 repair_1d=0
```

Reading: stored-vs-Exness value diffs 0, dry-run cascade-vs-Exness diffs 0, truncated 1m inputs 0, post-deploy days not `source=cascade` 0.

d16=A

Amendment committed and pushed as `935d9504` (`docs(plans): amend the task 17.2 pass rule for pre-deploy days`). Amended Verify (the D16 script) re-run at 2026-11-02T18:02:29Z: all 38 day rows `stored=equal dry=equal`, identical to the diagnostic output above apart from `updated_at`. Last lines:

```
diag_truncated=0 post_d1_not_cascade=0
min_days=12
mismatches=0 repair_1d=0
```

Task 17.2 Verify PASS under D16.

## 1d cascade review

Read-only review of the live 1d cascade path on `935d9504` (D15). All paths are under `src/pocketquant/`. Facts are marked as verified in code; inferences are labelled.

**Bucket.** One 1d bar covers the UTC day `[00:00, 24:00)`. It is stamped at UTC midnight: `cascade_for_symbol` sets `datetime=boundary` (`engine/market_data/app_services/cascade_aggregator.py:147`), boundaries come from `calendar.bar_start` (`cascade_aggregator.py:67-97`), and the Exness calendar's `bar_start` maps 1d to `get_bar_start`, which is the UTC midnight (`core/infra/calendars/exness_session_calendar_adapter.py:84-89,229-230`). `session_date` is the UTC date of the boundary (`exness_session_calendar_adapter.py:170-171`, `cascade_aggregator.py:154`). The bucket reads only the minutes the calendar says trade, `trading_minutes(boundary, boundary + 1d)` (`exness_session_calendar_adapter.py:217-227`, `cascade_aggregator.py:122`), so a Sunday bar holds only the Sunday evening minutes and `session_close` is the last trading second of that UTC date (`exness_session_calendar_adapter.py:185-189`). Covered by `test_a_session_calendar_cascades_its_daily_bar_at_utc_midnight` (`tests/app_test/market_data/test_cascade_aggregator.py:541`). Exness uses the same stamp: the Task 17.2 output joined 38 rows by `datetime` with no missing side, every row equal, including the Sunday 2026-10-25 and 2026-11-01 bars (the latter is the US DST change day: XAUUSD `n1m=59/59` versus `119/119` the Sunday before).

**Finalisation.** `sync_1m` runs every minute at second 12 (`engine/market_data/app_services/sync_jobs.py:729-734`) and cascades with a 100-minute lookback (`sync_jobs.py:403-408`). `compute_boundaries` keeps every bucket that overlaps the range (`cascade_aggregator.py:61-66`), so the day bucket is re-aggregated from all its stored 1m bars every minute until about 01:40 UTC the next day, then never again by `sync_1m` (`test_1d_today_bucket_kept_alive_through_the_day`, `test_cascade_aggregator.py:243`). A 1m bar repaired before about 01:40 UTC the next day, including by the 00:00 UTC `sync_repair`, is folded in. `sync_repair` (`sync_jobs.py:477-518`, cron `0 */12 * * *` at `sync_jobs.py:765-768`) repairs each interval from REST and never calls `cascade_for_symbol`, so a 1m bar filled later (the 12:00 UTC repair, or any later REST fill) is not folded into its 1d bar. The same holds for the cascaded 5m, 15m, 1h and 4h buckets once they leave the 100-minute window. Inference: the 1d bar is then built from incomplete 1m data and differs from Exness, unless the 1d repair path below happens to fire.

**Overwrite precedence.** `upsert_bar` has no source precedence: equal OHLCV returns before any write (`core/infra/persistence/repositories/bar_repository.py:81-82`), and different values are overwritten with the new writer's `source` (`bar_repository.py:84-98`). So `source` records the last writer that changed values. `sync_backfill` (03:00 UTC, `sync_jobs.py:751-755`; `DAY_1` is in `SYNC_INTERVALS`, `sync_jobs.py:52-60,425-432`) cannot replace a stored 1d bar: without `skip_filter`, `sync_one` drops every fetched bar whose `datetime` already exists (`engine/market_data/sync_service.py:80-85`, `engine/market_data/sync_internals/bar_filters.py:15-39`), so it only inserts missing days. This corrects the 2026-11-03 advice, which inferred a daily 03:00 UTC overwrite. `sync_repair` can replace one: when `check_integrity` finds a 1d gap in the last 7 days (`engine/market_data/app_services/integrity_jobs.py:51-110`), `repair_integrity` re-syncs 5000 REST 1d bars with `skip_filter=True` (`integrity_jobs.py:114-155`), and every cascaded 1d bar in that range whose values differ from REST is overwritten with `source=rest_repair`. The calendar has no holidays (Phase 16 report, line 41), so a venue holiday with no 1m bars leaves a 1d gap that, inference, triggers this path. Its result converges to Exness values, not away from them. Prod evidence: in the 14-day window no 1d bar was rewritten after the deploy (all pre-deploy `updated_at` values are on or before 2026-11-01T00:00:38Z; the three post-deploy bars are `source=cascade`).

**Monitoring.** No job checks 1d cascade bars in prod. `sync_verify_cascade` runs hourly (`sync_jobs.py:745-748`) and compares only the last 12 REST 5m bars with stored 5m bars (`sync_jobs.py:521-570,573-626`). `sync_integrity` (04:00 UTC) checks 1d bar presence on the calendar grid, not values (`integrity_jobs.py:51-110`). `repair_1d` in Task 17.2 counts only inserts (`created_at` is set on insert only, `bar_repository.py:58-70`), so it does not see a repair that rewrites an existing bar.

**Further risk (inference).** The 1m read is limited to `expected_count + 5` bars sorted newest first (`cascade_aggregator.py:122-130`, `bar_repository.py:122`). If more 1m bars are stored for a day than the calendar expects, for example after a venue schedule change the weekly template does not know, the earliest bars are dropped and the open is wrong. Task 17.2 measured `diag_truncated=0` over 14 days.

**Finding (D15 stop).** A stored 1d bar can go wrong in future: a 1m bar that reaches Mongo after the day bucket leaves the 100-minute lookback (about 01:40 UTC the next day) is never folded into the 1d bar, and no job checks 1d values. Two smaller items: no 1d monitoring exists, and the `expected_count + 5` limit can truncate a day the calendar under-counts. Task 17.2 found no such day in the last 14 days. Fixing any of these needs code, which Phase 17 never changes.

d15_finding_ask=yes (owner, 2026-11-02T18:07:37Z): close the plan and fix the late-1m fold, the missing 1d check and the read limit in a new small plan.

### Task 17.1 — obs-4 and obs-6

Primary check at 2026-11-02T18:07:37Z (XAUUSD session open): no `stop_market` order with `status=submitted` or `pending`, `open_positions=0`. D13: obs-4 is not asked.

obs-4 SKIPPED by owner tests=test_a_cancelled_stop_never_fills,test_cancel_leaves_the_position_open

obs-6 PASS (owner replied DRAWER OK at 2026-11-02T18:14:20Z)

### Task 17.3 — Exact delete lists (2026-11-02T18:15:00Z)

`reports/stf-delete-ids.json` written. Summary:

```
backtest_orders=200554 backtest_runs=21 backtest_trades=100273 orders=250 positions=234 subscriptions=4 trades=215
orphans orders=9 positions=0 trades=0
open_positions_total=2 paper=running/running
```

STF subscriptions: `019ebe98-209c-71f2-af3d-981810e2d783`, `019f0e9b-b206-76b6-b14f-23ab958c1c4e`, `01a15754-39ed-73e3-921e-df085eb4a786`, `01a15754-3ab5-7258-b46b-ad98e1f3471f`. Open positions: `01a18f20-98ce-7015-ba5a-80ac90f0ac3c` (BTCUSDT:BINANCE short) and `01a191c6-ff56-71a8-a2e8-143bac01f9c8` (BTCUSDT:BINANCE long). The 9 orphan orders are all `rejected` BTCUSDT:BINANCE orders from 2026-05-11 to 2026-06-28 whose `subscription_id` is a strategy code or an old backtest id (`hitnrun2`, `hitnrun2::bt::…`, `hit_and_run::bt::…`). Guard counts: tracked_symbols=6, sync_status=42, bars=5682095, job_history=86286.

Task 17.3 Verify PASS.

### Task 17.4

Asked in Vietnamese at 2026-11-02T18:18:00Z with the summary line, the 4 subscription ids and the 2 open position ids; owner replied yes.

stf_delete=yes

### Task 17.5

Asked separately in Vietnamese at 2026-11-02T18:19:39Z with the orphans summary line; owner replied yes. Pre-delete `kongming` checkpoint: GO (id file internally consistent, no triple_screen id, no id after the paper start, largest `$in` filter 9.27 MiB under the 16 MiB limit; 250 STF + 9 orphan orders = 259 pre-plan orders).

orphans=approved

### Task 17.6 — Delete (2026-11-02T18:19:50Z)

Uploaded `/tmp/ids.json` (12062737 bytes, same as local). Run with `1` (`orphans=approved`). No backup (owner decision C12).

```
stf backtest_orders listed=200554 deleted=200554
stf backtest_trades listed=100273 deleted=100273
stf backtest_runs listed=21 deleted=21
stf trades listed=215 deleted=215
orphans trades listed=0 deleted=0
stf orders listed=250 deleted=250
orphans orders listed=9 deleted=9
stf positions listed=234 deleted=234
orphans positions listed=0 deleted=0
stf subscriptions listed=4 deleted=4
guard_ok=1 before={'tracked_symbols': 6, 'sync_status': 42, 'bars': 5682137, 'job_history': 86287} after={'tracked_symbols': 6, 'sync_status': 42, 'bars': 5682143, 'job_history': 86289}
mismatch=0
```

Task 17.6 Verify PASS.

### Task 17.7 — Re-list

`reports/stf-delete-relist.json` written.

```
stf_total=0 orphans_total=0 paper=running/running
```

Remaining subscriptions:

```
01a19bbf-0b3a-70e3-903e-f93e361acbf8 triple_screen ['15m', '1h', '4h'] running/running
01a19bbf-9788-7487-8c7e-9f110ed8c595 triple_screen ['1h', '4h', '1d'] running/running
01a19bc0-26ec-76ba-b83e-edeb84f021d4 triple_screen ['5m', '15m', '1h'] running/running
```

Task 17.7 Verify PASS. `.cache/ssh/vps_key` removed.

### Task 17.8 — Docs line test

Step 1 stale words: `0`.

Step 2 first run (2026-11-02T18:22:31Z): `11` lines:

```
missing docs/code-standards.md try/finally
missing docs/deployment.md backfill/binance_bars.py
missing docs/deployment.md backfill/provider_bars.py
missing docs/deployment.md one-time/bootstrap-gh.sh
missing docs/deployment.md pocketquant-config/vps/default/docker-hub.env
missing docs/deployment.md pocketquant-config/vps/default/host
missing docs/deployment.md vps/default/.env
missing docs/deployment.md vps/default/docker-hub.env
missing docs/deployment.md vps/default/host
missing docs/deployment.md vps/default/id_rsa
missing docs/deployment.md vps/default/portainer.env
```

Kongming counsel on the 11 lines: none is stale; every target exists (the two backfill scripts under `scripts/`, the config files in the sibling `../pocketquant-config/` repo), and `try/finally` is prose. All 11 come from commit `d5c45781`, before the plan base. Fix: qualify each path in the docs' own existing convention (`scripts/...`, `../pocketquant-config/...`), reword `try/finally` to `finally`, and, so the runbook stays runnable, change `python scripts/<path>` to `python <script>` and prefix the three unflagged sibling scripts. The checker loop was not changed. Committed and pushed as `d4a9cc08` (`docs: fix stale names in the architecture docs`).

Re-run after the push:

stale_words=0
doc_check=0

## Acceptance A1-A13

Report paths are relative to `plans/261101-0843-stf-to-mtf-foundation/reports/`; "P17" is this report.

| # | Criterion | Evidence |
|---|---|---|
| A1 | Spike go/no-go per piece | `spike-go-no-go.md:28-37`: S1-S3 and S5-S10 `go`; S4 `no-go` (`:31`) with the owner [ASK] answer at `:96` (D10, Phase 08 prefetch) |
| A2 | No STF code | run on `d4a9cc08` (2026-11-02): the A2 `git grep` prints `0`; `STRATEGY_REGISTRY` keys `['triple_screen']` |
| A3 | `intervals`, `parameters`, unique `intervals_key` | `phase-06-subscription-contract.md:57` `Result: PASS` (Phase 06 tests); `phase-15-release-d2.md:80` `indexes=_id_,ix_subscriptions_dedup_intervals,ix_subscriptions_strategy_code` (no `dedup_triple`) |
| A4 | No look-ahead in live, warm-up and backtest | `phase-07-htf-context-live-and-warmup.md:31` (`test_live_first_entry_bar_of_a_bucket_sees_the_previous_bucket_close`, `test_a_partial_bucket_is_never_served`), `:71` `Result: PASS`; `phase-08-backtest-intervals-backend.md:31` (`test_backtest_contexts_equal_live_contexts_at_every_boundary`), `:115` `Result: PASS` |
| A5 | No per-bar context reads | `phase-07-htf-context-live-and-warmup.md:31` (`test_context_is_read_once_per_rollover_for_two_instances`) |
| A6 | 1d cascade correct over the latest 14 stored days (D14, D16) | P17:172 `mismatches=0 repair_1d=0` (diagnostic) and P17:184 (amended Verify, D16 at P17:177); the first run's failure is recorded above it; review at P17:189, owner answer P17:205 |
| A7 | Stop entry, EXIT, manual close, manual cancel in paper | P17:28 obs-1 order id; P17:70 obs-2 trade id with its `reason=strategy_exit` log line; P17:69 obs-3 trade id; P17:211 obs-4 skipped by D13 with `test_a_cancelled_stop_never_fills` and `test_cancel_leaves_the_position_open` |
| A8 | Pending placement fenced by the live flag; close and cancel not | `phase-10-exness-close-pending-cancel.md:25` (fence test), `:78` `Result: PASS` |
| A9 | Snapshot visible and changing in the UI | `phase-16-backtests-and-paper-start.md:155` ring `live_distinct_bar_start=12`; `phase-13-subscription-ui.md:54` `UI OK`; P17:29 obs-5 and P17:213 obs-6 `DRAWER OK` |
| A10 | Six backtests comparable | `phase-16-backtests-and-paper-start.md:108` metrics table with 6 run ids and the compare URLs (`:123-124`) |
| A11 | Prod STF and orphan data gone; tracked symbols and bars untouched | P17:267 `stf_total=0 orphans_total=0 paper=running/running`; P17:256-257 `guard_ok=1` (tracked_symbols 6 before and after) and `mismatch=0` |
| A12 | Gates | `phase-14-triple-screen.md:27-28` `Contracts: 6 kept, 0 broken.`, ratchet exit 0, FULLSUITE unexpected count `0`; CI `completed success` at `phase-14-triple-screen.md:40` and `phase-13-subscription-ui.md:63` (web job) |
| A13 | Architecture doc rewritten | `phase-09-capabilities-in-paper.md:39` stale-claim grep `0`; P17:304 `stale_words=0`, P17:305 `doc_check=0` |

Plan close: `ak plan update pocketquant/261101-0843 --status completed --no-interactive` printed `pocketquant/261101-0843 updated`; `plan.md` front matter `status: completed`. The Phase 17 front matter and its phase-table row were set to completed, as earlier phases did.

ak plan status: `Retire single-timeframe strategies; generic multi-timeframe foundation  17/17 phases done`

Follow-ups outside this plan (owner, D15 answer): fold late 1m repairs into cascaded buckets, add a 1d value check in prod, and guard the `expected_count + 5` read limit. Hand check suggested by the advice: re-run the D16 script once in the week of 2026-11-09.

Result: PASS
