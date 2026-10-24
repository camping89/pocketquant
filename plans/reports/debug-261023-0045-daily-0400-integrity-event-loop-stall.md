---
title: "Daily 04:00 UTC stall: sync_integrity blocks the event loop"
date: 2026-10-23
status: diagnosed, not fixed
plan: plans/archive/260921-1436-asset-class-index-futures (found during Phase 9)
---

# Daily 04:00 UTC stall: `sync_integrity` blocks the event loop

## Summary

Every day from 04:00 to about 04:07 UTC (11:00-11:07 Bangkok) the app stops doing
timely work. `sync_integrity` runs synchronous CPU work for about 7 minutes. The app has a
single asyncio event loop (one uvicorn worker), so every other job and the API wait behind
it. The work is the CME Globex calendar: `bar_start` is called about 91,000 times per
futures symbol, and each call re-runs pandas `iterrows()` over a window of the schedule.

Diagnosed read-only on 2026-10-22. No code changed yet.

## Impact

Facts:

- `sync_1m` runs once instead of about seven times between 04:00 and 04:07, for every
  symbol, crypto and Exness included. The runs due at 04:01-04:06 are dropped, because the
  04:00 run is still busy and `max_instances=1`.
- `data_lag_check` and `sync_verify_cascade` slow down by the same amount.

Inference (not measured):

- Live strategies receive their bars late in that window: today the paper subscriptions on
  BTCUSDT 1m, EURUSD 1h and ES1! 15m.
- HTTP requests in that window are slow too, since they share the loop.
- Today the risk is limited to paper trading because Exness live trading is off. With live
  trading on, it is a daily window of about 7 minutes in which orders and exits act on stale
  data.
- Bars are not lost. `sync_1m` fetches the last 100 1m bars, so the 04:07 run fills the gap.

## Evidence

`job_history` on prod, the same pattern on 2026-10-20, 10-21 and 10-22. Rows for 2026-10-22:

| Job | Started (UTC) | Duration | Normal duration |
|---|---|---|---|
| `sync_1m` | 03:59:02 | 9.2 s | about 9 s |
| `sync_integrity` | 04:00:00 | 418.6 s | — |
| `sync_verify_cascade` | 04:00:00 | 284.2 s | median 3.7 s |
| `sync_1m` (due 04:00:02) | 04:00:48 | 378.0 s | about 9 s |
| `data_lag_check` (due 04:00:30) | 04:00:48 | 94.1 s | about 0.1 s |
| `data_lag_check` | 04:03:09 | 94.5 s | about 0.1 s |
| `data_lag_check` | 04:05:51 | 67.2 s | about 0.1 s |
| `data_lag_check` | 04:07:30 | 0.1 s | about 0.1 s |

`sync_integrity` took 420.3 s on 10-21 and 429.3 s on 10-20. On all seven days from 10-16 to
10-22, the only `sync_verify_cascade` runs over 30 s are the 04:00 runs (147-284 s), each
followed by a single `sync_1m` run in the next six minutes. Saturday and Sunday look the
same, so this does not depend on the futures market being open.

**Why this is the event loop and not the TradingView scraper lock.** `data_lag_check` reads
only Redis and Mongo and never calls TradingView, yet it takes 94 s instead of 0.1 s. The
APScheduler jobs also start late (`sync_1m` due 04:00:02 starts 04:00:48), which happens
only when the loop cannot run its timers.

## Root cause

`_run_integrity` (`src/pocketquant/engine/market_data/app_services/sync_jobs.py:349-399`)
loops over every tracked symbol and over `SYNC_INTERVALS`. For each pair it calls
`check_integrity` (`src/pocketquant/engine/market_data/app_services/integrity_jobs.py:54`),
which has two loops:

- `_expected_instants` (`integrity_jobs.py:37-51`) calls `calendar.bar_start` once per
  trading minute in the last 7 days, for each interval.
- `is_bar_aligned` (`src/pocketquant/core/domain/bar/services/bar_builder_domain_service.py:37-47`)
  calls `calendar.bar_start` once per stored bar.

Neither loop awaits, so the loop gets no chance to run anything else until each
`check_integrity` call ends.

On the CME calendar each `bar_start` call is expensive
(`src/pocketquant/core/infra/calendars/cme_globex_calendar_adapter.py`):

- `bar_start` (line 170) calls `session_date` (line 112), and so does `session_open`.
- `session_date` calls `_window_rows` (line 216) up to twice.
- `_window_rows` runs `schedule.iterrows()` over the whole window, building a pandas Series
  per row, on every call.

The 24/7 calendar (`Continuous24x7Calendar.bar_start` delegates to `get_bar_start`) and the
Exness calendars do not have this cost.

## Measurements (local, Windows, Python 3.14)

`check_integrity` was run against an in-memory bar store holding a full 7-day grid.

| Calendar | 1m | 5m | 15m | 1h | 4h | 1d | 1w | Total |
|---|---|---|---|---|---|---|---|---|
| CME (ES) | 14.4 s | 8.4 s | 7.3 s | 7.6 s | 7.5 s | 0.05 s | 0.00 s | about 45 s |
| 24/7, Exness FX | — | — | — | — | — | — | — | 0.02-0.03 s per interval |

- Profile of one CME symbol: 91,367 calls to `bar_start`. Of 253 s under the profiler,
  `session_date` takes 196 s, `_window_rows` 133 s and pandas `iterrows` 129 s.
- Three futures symbols take about 2-3 minutes locally. On the 2-vCPU VPS the job takes
  about 7 minutes. Inference: the gap is the slower CPU.
- Experiment, not a fix: caching `_window_rows` by date dropped one CME symbol from 45.3 s
  to 17.5 s. The two runs also returned different 1m `missing_count`s (1 vs 0). They started
  45 s apart, so `now` and the in-progress cutoff moved between them. That comparison does
  not prove the results are equivalent.

## Related, smaller effect: the hourly verify at :00

`sync_verify_cascade` (HH:00:00) and `sync_1m` (HH:00:02) share the TradingView scraper lock
(`src/pocketquant/core/infra/tradingview/tvdatafeed_client.py:117`). Over 7 days, the :00
`sync_1m` finished its futures 13-20 s later (ES 17.0 s, NQ 26.3 s, YM 17.9 s, against
3.8 / 6.4 / 8.8 s at other minutes). Zero-insert syncs are fewer at :00 and more at :01, so
the bar is fetched one minute early rather than lost. No change is proposed for this.

## Fix options

1. **Make CME session lookup cheap (recommended).** Build the session table once as plain
   UTC `datetime` tuples and look sessions up by binary search, instead of running
   `iterrows()` on every call. This fixes the root cause and also speeds every other CME
   caller (`sync_1m` alignment, cascade, data lag). Inference: it should bring the job from
   minutes to seconds, but that is not measured yet.
2. **Run `check_integrity` in a worker thread** (`asyncio.to_thread`). The loop gets time
   slices again, but on two vCPUs and with the GIL the CPU cost stays and the loop still
   slows down. It treats the symptom.
3. **Move the cron time.** This changes nothing; the stall moves with it.

## Constraints

- Do not deploy before 2026-10-23 21:05 UTC (2026-10-24 04:05 Bangkok). A deploy restarts
  the Phase 9 measurements: 24 verify runs for row 11 and one CME session for G2.
- A fix must keep `check_integrity` results identical. Compare the old and new calendars
  call by call, with fixed instants rather than `now`, across DST changes, weekends and
  holidays.

## Verification after a fix

- Unit test: the old and new CME `session_date` and `bar_start` give identical results for
  every minute of a range that covers a DST change, a weekend and a holiday.
- Prod, the next 04:00 run: `sync_integrity` duration well under a minute, `data_lag_check`
  near 0.1 s, and `sync_1m` running every minute from 04:00 to 04:07.

## Decision

User, 2026-10-23: fix in a separate plan, later. The asset-class plan closes without it.

## Unresolved questions

- `_window_rows` may also make `sync_1m` slower on futures every minute (ES finishes 3.8 s
  after start, NQ 6.4 s, YM 8.8 s). How much of that is calendar CPU and how much is the
  scraper is not measured.
