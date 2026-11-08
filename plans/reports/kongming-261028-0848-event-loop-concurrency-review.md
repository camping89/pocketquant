---
title: "Event-loop concurrency review: what blocks the loop, and the smallest safe fix"
date: 2026-10-28
status: advisory, no code changed
inputs: plans/reports/debug-261023-0045-daily-0400-integrity-event-loop-stall.md, prod job_history (read-only, 7 days to 2026-10-28 08:50 UTC), local micro-benchmarks
---

# Event-loop concurrency review

## TL;DR

The loop is blocked by one thing: CME calendar lookups that cost about 0.5 ms each and are
called tens of thousands of times per job. Prod data shows the stall is not one daily
7-minute window but three: `sync_repair` at 00:00 and 12:00 UTC blocks the loop for
**25-49 minutes** (median 1,527 s, max 2,947 s over 14 runs), and `sync_integrity` at 04:00
for 7 minutes. Fix the calendar (precomputed session table + bisect), add an event-loop lag
probe, and fix the broken skip listener. Do not add threads, processes, or workers: on a
2-vCPU GIL build they only spread the same wasted CPU around, and each one adds a live-trading
risk the calendar fix does not have.

## Reframed problem

The question is not "how to parallelise" but "what must a single asyncio loop never do while
real money is on the line". Requirements: bar closes, order submissions and exits must not be
delayed; no duplicated orders; keep the single-process invariants (one scheduler, one
scraper socket, one broker connection). Non-goal: making the integrity work faster for its
own sake. Constraint: 2 vCPU, 3.9 GB RAM (about 2 GB available), Python 3.14 with the GIL.

## 1. What runs synchronous or blocking work on the loop, ranked

Facts come from prod `job_history` (7 days), local micro-benchmarks (Windows, Python 3.14.6;
VPS is roughly 2-3x slower per the earlier report), and code.

| # | Path | Blocking work | Measured impact | Verdict |
|---|------|---------------|-----------------|---------|
| 1 | `sync_repair` 00:00 and 12:00 UTC (`sync_jobs.py:436-470`) | `repair_integrity` runs `check_integrity` twice per (symbol, interval) (`integrity_jobs.py:140,181`), then `sync_one(n_bars=5000, skip_filter=True)` whose `drop_misaligned_bars` calls CME `bar_start` once per bar (`bar_filters.py:77` -> `bar_builder_domain_service.py:45`) | **Prod: median 1,527 s, max 2,947 s.** In the 15 min after 00:00 on 10-27, `sync_1m` ran 4 times instead of 15, one run lasting 1,463 s; `data_lag_check` 88 s. 12:00 UTC is 07:00 Chicago, inside CME RTH | Top. Missed by the earlier diagnosis |
| 2 | `sync_integrity` 04:00 UTC (`sync_jobs.py:380-411`) | one `check_integrity` per (symbol, interval): ~91k `bar_start` calls per CME symbol | Prod: median 419 s over 7 runs (already diagnosed) | Same root cause |
| 3 | Every-minute CME calendar calls on the loop: `drop_misaligned_bars` on 100 bars x 3 futures; `has_aligned_bar` (`provider_fetch.py:174`); TV adapter cutoff `bar_start` (`tradingview_adapter.py:75`); `is_open`/`previous_close` gate (`sync_jobs.py:230`); cascade `compute_boundaries` + `trading_minutes` per bucket (`cascade_aggregator.py:142-145,197`); `data_lag` `trading_minutes` over 4 days (`data_lag_service.py:84`); `add_tick` 7x `bar_start` per TV quote (`bar_app_service.py:102`) | Local: `bar_start` 0.59 ms, `is_open` 0.39 ms, `trading_minutes`(4 days) 2.7 ms, cascade calendar work 34 ms per futures symbol, 7x `bar_start` 4.2 ms | Inference: under 1 s per minute locally, under 3 s on the VPS. Not a stall, but it is why ES/NQ/YM `sync_1m` finish 4-9 s after start. Disappears with the same fix |
| 4 | `sync_backfill` 03:00 UTC (`sync_jobs.py:373`) | 5000 bars x 7 intervals x 3 futures through `drop_misaligned_bars` and `stamp_calendar` (`calendar_stamp.py:111`, `session_date` per 1d/1w bar); plus `frame.iterrows()` over 5000 rows on the loop in `tvdatafeed_client.py:164` | Prod: median 158 s, but the 03:00 windows show 15 `sync_1m` runs in 15 min and nothing over 20 s, so the time is mostly scraper I/O (in `to_thread`) | Low; shrinks with the fix |
| 5 | Binance `@aggTrade` hot path | per tick: one unthrottled Redis `SET` (`quote_app_service.py:71`), `add_tick` under one global lock for all symbols (`bar_app_service.py:90`), and 2-3 `logger.debug` calls that run the full structlog chain including `JSONRenderer` before stdlib drops them (`logging/setup.py:49-80`: `wrapper_class=structlog.stdlib.BoundLogger`, no `filter_by_level`) | Prod snapshot: app container at 3.6% CPU, so quiet today. 50-500 ticks/s/symbol at peak per the adapter's own comment (`binance_websocket_adapter.py:198`) | Steady-state cost that scales with market activity. Cheap to trim; not the cause of the stalls |
| 6 | APScheduler `_process_jobs` | runs on the loop thread (`AsyncIOScheduler.wakeup` -> `call_later`) and does sync `pymongo.MongoClient` round trips through `MongoDBJobStore` (`get_due_jobs`, `update_job`, `get_next_run_time`): at least 2 wakeups/min x 3 calls | Milliseconds on the compose network | Low. A Mongo pause would freeze the loop, which `data_lag_check` and the lag probe below would show |
| 7 | Backtests via `POST /backtest/run` | in-process task (`routes/backtest.py:68`), yields every 10 bars (`backtest_app_service.py:140-141`); strategy and paper-broker handlers are pure Python; report maths is numpy, one shot | Not measured in prod. Latency added to other tasks is bounded by 10 bars; CPU is shared for the run's duration | Low. Fine for one run at a time |
| 8 | Live strategy bar handling and brokers | `EventBus.publish` awaits handlers sequentially (`event_bus.py:38-42`); strategies are pure Python; paper broker in-memory; Exness and Binance use `httpx.AsyncClient`, Mongo is `AsyncMongoClient`, Redis is `redis.asyncio` (verified in `persistence/mongodb.py:46`, `persistence/redis.py:9`, `exness_client.py:203`) | No blocking I/O found | OK |
| 9 | TradingView scraper | `get_hist` and construction run in `asyncio.to_thread` under one `asyncio.Lock` (`tvdatafeed_client.py:117-136,192`) | Correct; only the lock contention matters (section 3) | OK |

Prod environment, verified today: 2 vCPU; Python **3.14.0rc3**, `Py_GIL_DISABLED=0`,
`sys._is_gil_enabled() == True` (the Dockerfile pins `python:3.14-rc-slim`, `deploy/Dockerfile:4,28`);
local is 3.14.6, same GIL build. So no free-threading anywhere, and threads cannot run Python
code in parallel.

## 2. Options on 2 vCPU with the GIL

| Option | Fixes | Costs | Live-trading risk |
|---|---|---|---|
| **A. Make CME lookups cheap** (session table as UTC datetimes, `bisect`) | The cause: rows 1-4 shrink from minutes to seconds; row 3 vanishes | One adapter rewrite plus an equivalence test. Semantic drift is the only risk | None new. The lowest-risk option because nothing changes in scheduling, threading or process shape |
| B. `asyncio.to_thread` for the integrity loops | Timers keep firing; `sync_1m` runs each minute | The GIL hands the loop thread a slice every 5 ms, so ticks and orders see roughly half a core for the whole 25-49 min; the scraper lock contention stays; `check_integrity` is async (Mongo awaits), so only the pure loops can move, and the shared calendar singletons would be read from two threads (`lru_cache` on methods, `cme_globex_calendar_adapter.py:61,193`; safe under the GIL, but it is a new invariant to keep) | Medium: orders are slower but not stuck. Treats the symptom; the CPU is still 99% waste |
| C. `ProcessPoolExecutor` | True parallelism for the pure loops | Second interpreter (~150-300 MB; the VPS has ~2 GB available, Mongo already holds 893 MB), `spawn` start method, pickling the docs list and a calendar that wraps a pandas object, shutdown handling in lifespan | Low on orders, but the second core is shared with Mongo and Redis, and the complexity buys nothing once A is done |
| D. Separate worker process/container for APScheduler | Full isolation of jobs from the API and strategies | The TV scraper would run in two processes (the API polls ES/NQ/YM quotes every 60 s, `tradingview_quote_adapter.py:167`; the worker runs `sync_1m`), which is exactly the "two sockets, one chart session" corruption and ban risk the client docstring names (`tvdatafeed_client.py:6-17`); `enable_jobs` gates scheduler, reconcile loop and live collector together (`main_extensions.py:224-238`) and would need splitting; another ~300 MB; compose, CI and healthcheck changes | Medium during the migration (two schedulers if a flag is wrong). Right shape only if a genuinely heavy job appears later |
| E. Multiple uvicorn workers | Nothing here | Duplicates the scheduler (the Mongo jobstore is "first update wins", not a lock), strategies, brokers, the quote feed (double-counted ticks) and SSE state; CLAUDE.md forbids it | High: duplicated orders |
| F. `await asyncio.sleep(0)` every N iterations | Timers keep firing | Total CPU unchanged, the loop sits at 100% for the same 25-49 min, each tick waits N x 0.6 ms, scraper lock still held | Medium, and it hides the problem from the duration metrics |

## 3. Concurrency correctness risks, today and after a fix

1. **Dropped runs are invisible, and the listener that should record them is broken.**
   Verified: zero `missed` or `skipped_max_instances` rows in 7 days, although 11 `sync_1m`
   ticks were dropped in one 15-minute window. Two causes. First, `JobScheduler._on_skip`
   reads `event.scheduled_run_time` (`scheduler.py:98-99`), but `EVENT_JOB_MAX_INSTANCES` is a
   `JobSubmissionEvent` whose attribute is `scheduled_run_times` (a list; APScheduler 3.11.2
   `events.py`), so the listener raises `AttributeError` and APScheduler only logs it.
   Second, `coalesce=True` collapses the backlog to the newest run time before the grace check
   (`BaseScheduler._process_jobs`: `run_times[-1:] if job.coalesce`), so coalesced ticks never
   produce `EVENT_JOB_MISSED`. Also, `_dispatch_skip` drops the future from
   `run_coroutine_threadsafe` (`scheduler.py:132`), so a failing `record_skip` is silent.
2. **Scraper lock convoy during `sync_repair`.** The resync fetches 5000 bars per interval per
   futures symbol under the one lock (`tvdatafeed_client.py:117`), and the ES/NQ/YM quote
   pollers (`tradingview_quote_adapter.py:167`) plus `sync_1m` queue behind it. Combined with
   the CPU stall, the ES 15m paper strategy gets its bar closes late for up to 49 minutes
   twice a day. Inference: with option A the resync itself drops to seconds of CPU, but the
   5000-bar fetches still hold the lock for a few seconds each; acceptable.
3. **Bar pipeline is serialised behind one lock and publishes inline.** `add_tick` holds
   `BarAppService._lock` for every symbol while `BarCompletedEvent` handlers run
   (`bar_app_service.py:90,162`), and the strategy handler submits orders inside that chain
   (`strategy_app_service.py:258-261,380`). An Exness `openPosition` call is bounded by
   `_HTTP_TIMEOUT_S = 10` (`exness_client.py:66`), so a venue hang freezes bar building for
   all symbols for up to 10 s. With one live subscription this is harmless; it matters once
   several symbols trade live. Not a blocker for go-live; note it.
4. **Thread-safety if B or C is chosen.** `BarAppService._bars`, `StrategyAppService`
   dictionaries, broker state and the Dishka container are loop-only. Only pure functions of
   (docs, calendar) may move off the loop. The calendar adapters are APP singletons with
   method-level `lru_cache`; CPython's C `lru_cache` is safe, pandas reads of a shared
   `DataFrame` are safe in practice, but this is an invariant nobody will remember.
5. **Sync jobs vs strategies.** Strategies get bars from the tick feed, not from Mongo, so
   `sync_1m` writes do not race them. `sync_repair` deletes misaligned bars
   (`integrity_jobs.py:144`); a backtest streaming the same range sees the gap. Minor.
6. **Catch-up at boot.** `enqueue_missed_catchups` (`sync_jobs.py:650`) can start `sync_repair`
   or `sync_integrity` seconds after a deploy, so today a restart during live trading can be
   followed by a 25-minute stall. Harmless once A is done.
7. **Exits are safer than entries.** Exness stops live at the venue (`exness_broker_adapter.py:239-242`),
   so a stall delays entries and strategy-driven exits, not stop-losses. Paper SL/TP are
   synthetic and loop-dependent.

## 4. Recommendation: smallest combination, in order

1. **Calendar table + bisect in `CmeGlobexCalendarAdapter`.** Build, lazily and cached per
   year range, a sorted list of `(open_utc, close_utc, session_date)` from
   `pandas_market_calendars`, and answer `session_date`, `is_open`, `previous_close`,
   `sessions`, `trading_minutes` and `bar_start` from it with `bisect`. Keep the port
   unchanged. Delete `_window_rows` and `_row`. Expected (inference): `bar_start` from
   ~0.5 ms to a few microseconds; `sync_integrity` from 7 min to about 5-10 s, mostly Mongo;
   `sync_repair` from 25-49 min to well under a minute plus scraper time.
   Equivalence test: for every minute of a range that covers 2026-03-08 and 2026-11-01 (DST),
   a weekend, Good Friday and the Juneteenth early close, compare the new answers against the
   raw `mcal.schedule()` rows (the source of truth, so no dead adapter code survives as an
   oracle). The existing `tests/core_test/infra/calendars/test_cme_globex_calendar.py`
   stays as the behaviour spec.
2. **Event-loop lag probe** (about 30 lines in lifespan): a task that sleeps 1 s and records
   `loop.time()` overshoot; keep the max per minute; log one WARNING per stall with the max;
   expose `event_loop_lag_max_s` in `/health`. This is the metric that proves the fix and
   catches the next regression, and it is cheaper and more honest than job durations, which
   coalesce hides.
3. **Fix the skip listener**: read `scheduled_run_times[-1]` for submission events and
   `scheduled_run_time` for execution events; attach a done-callback that logs a failed
   `record_skip`. Add a unit test that fires a real `EVENT_JOB_MAX_INSTANCES` through
   `AsyncIOScheduler` and asserts the row.
4. **Before Exness go-live, a stale-bar entry guard** in `StrategyAppService._on_bar_completed`:
   if `now - (bar_start + interval)` exceeds `max(60 s, interval / 2)`, log and skip the
   entry (exits still run). This turns any future stall from "trade on stale data" into
   "skip the signal". Product decision; recommended default on.
5. Optional, after the probe shows steady-state lag: `structlog.stdlib.filter_by_level` as the
   first processor, and throttle the `quote:latest` write like `bar:current` is.

One deploy for 1-3 is fine; CI is lint plus pytest and every push to master deploys.
Avoid deploying across 00:00, 04:00 or 12:00 UTC so the first post-fix runs are clean.

## What to avoid

- Threads, process pools or a worker container as the fix for this problem: they move
  waste, they add a scraper-socket or thread-safety invariant, and on a GIL build with
  2 vCPU they cannot give the loop its core back.
- `sleep(0)` chunking inside the integrity loops: it makes the durations look fine while
  the loop is still saturated.
- Moving crons: the stall moves with them (already concluded in the earlier report).
- Free-threaded Python (`3.14t`): the ecosystem (pandas, pymongo, numpy wheels) is not
  the place to experiment with real money, and after step 1 there is no CPU problem left.
- Multiple uvicorn workers, for the reasons in CLAUDE.md and section 2E.

## Verification in prod

After the next 00:00, 04:00 and 12:00 UTC runs: `sync_repair` under 60 s, `sync_integrity`
under 30 s, 15 `sync_1m` runs per 15 min around each cron, `data_lag_check` at ~0.1 s,
`event_loop_lag_max_s` under 1 s for the whole day, and `skipped_max_instances` rows
appearing when a run is genuinely dropped. Also grep the app log for APScheduler's
"Error notifying listener" line: present today (inference), gone after step 3.

## Side finding

Prod runs Python 3.14.0rc3 because the Dockerfile pins `python:3.14-rc-slim`. Move to
`python:3.14-slim` in a separate change (local is 3.14.6). Not related to the stall.

## Assumptions

- The VPS is 2-3x slower per call than the local machine (high; consistent with 45 s local vs
  7 min prod for the same job across three symbols).
- `sync_repair`'s time beyond two integrity passes is the 5000-bar resyncs under the scraper
  lock and their per-bar alignment checks (medium; inferred from code and the 25-49 min
  spread, not profiled on prod). If a prod profile shows Mongo instead, option A still
  removes the per-bar CPU but the resync fetches would need their own fix.
- The quote tick rate is low today (app at 3.6% CPU in one snapshot) (medium; one sample).
- The missing `skipped_max_instances` rows are caused by the attribute mismatch (high for the
  mechanism; the prod log line was not fetched).
- The user wants real-money safety over job throughput, so the stale-bar guard is proposed
  even though it skips some valid signals during a stall (medium; a decision for the user).
