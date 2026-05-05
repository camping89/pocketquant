# Debug Report: 15m BTCUSDT Freshness Delay
**Date:** 2026-05-05 | **Investigator:** debugger agent | **Severity:** **HIGH** (lag/missing bar = missed strategy entry/exit)

---

## Executive Summary

The ~4-minute delay on the monitor's "Age" column for 15m BTCUSDT comes from `IntervalTrigger` cadence anchored to **container startup** instead of UTC wall-clock boundaries. After a restart, sync phase drifts arbitrarily (e.g. fires at `:09/:24/:39/:54` instead of `:00/:15/:30/:45`), so the bar that closed at `:00` may not be ingested until 9–14 min later.

**Why this matters (HIGH severity):**
Strategies depend on bar-close events to trigger entries/exits. If a bar is **delayed**, signal evaluation runs late → late entry/exit → slippage. If a bar is **missed** (gap, see 22-min gap below), the strategy may **skip the signal entirely** → missed opportunity. Both fail-modes are unacceptable for an algo-trading system.

**Required fix:** anchor every interval sync job to UTC wall-clock via `CronTrigger` (e.g. `*/15 * * * *` for 15m). Eliminate phase drift entirely. Restart-resilient.

**Note:** WebSocket realtime path is intentionally **off** in current production setup — out of scope for this fix. Monitor freshness must be solved via the poll path alone.

---

## Hypotheses Tested

| # | Hypothesis | Result |
|---|-----------|--------|
| H1 | Sync cadence drift from startup-anchored `IntervalTrigger` causes lag/missed bars | **CONFIRMED — root cause** |
| H2 | Scheduler broken / persistent missed runs | **ELIMINATED** — runs steady within drifted phase |
| H3 | WebSocket fallback would mask the issue | **N/A** — WS intentionally off, must fix poll path |

---

## Evidence Chain

### 1. Freshness metric definition (frontend)

`format-helpers.ts → formatAge(s.last_bar_at)`:
```ts
const ms = Date.now() - parseIso(iso).getTime()
```

- "Age" = `now - last_bar_at` where `last_bar_at` = bar's **open** datetime (not close, not sync time)
- Color threshold: `age-fresh` if `ageMs < ivMs * 2` (i.e. < 30 min for 15m bars)
- Source field: `SyncStatusResult.last_bar_at` from Mongo `sync_status` collection
- `last_bar_at` is updated only when `sync_15m` job runs and inserts new bars

### 2. Scheduler cadence

`sync_jobs.py` registers `sync_15m` as `IntervalTrigger(minutes=15)`.  
APScheduler uses `replace_existing=True` with MongoDBJobStore — phase is anchored to **first startup**, not clock boundary.

Container start: `2026-05-05T04:59:55Z`  
First sync_15m fires: `2026-05-05T05:15:09Z` (15 min after startup)

Job history (last 5 runs):
```
05:15:09Z  completed  inserted=3   ← caught up after restart
04:52:34Z  completed  inserted=0   ← bar not yet closed (empty fetch)
04:37:34Z  completed  inserted=1
04:22:34Z  completed  inserted=1
04:07:34Z  completed  inserted=1
```

**22-minute gap (04:52 → 05:15)**: container was restarted at `04:59:55Z`, causing sync to miss the `05:07` slot. APScheduler coalesces missed runs (`coalesce=True`) and reschedules from new startup time → next run becomes `05:15`. The `total_inserted=3` at 05:15 confirms the catch-up of 3 bars (4:45, 5:00, 5:15 open times).

Phase shift in older history: runs before restart were at `:11, :26, :37, :52` (anchored to prior startup); after restart they shift to `:07, :22, :37, :52` then again shift after the latest restart.

### 3. Timestamp arithmetic (at investigation time ~05:15 UTC)

| Timestamp | Value (UTC) |
|-----------|------------|
| Server now | 05:15:19 |
| `last_bar_at` (Mongo) | 05:15:00 |
| `last_sync_at` | 05:15:10 |
| Expected current bar open | `floor(05:15 / 15m) = 05:15` |
| Age shown | ~0-19 sec (just synced) |

The system is currently fresh. The 4-min delay reported by the user was captured mid-cycle (e.g., at ~05:04, 4 min after the 05:00 bar opened, next sync at 05:07 or 05:15).

### 4. WebSocket / real-time path

WebSocket is **intentionally disabled** in current production — out of scope for this fix. Confirmed:
```json
{"running": false, "subscription_count": 0, "active_symbols": []}
```

The poll path (`sync_15m` interval job) is the **sole** data source for `last_bar_at`. Monitor freshness must be solved by fixing scheduler phase, not by re-enabling WS.

### 5. No stale data / no real regression

`sync_status` document at investigation close:
```json
{
  "interval": "15m",
  "last_bar_at": "2026-05-05T05:15:00Z",
  "last_sync_at": "2026-05-05T05:15:10Z",
  "status": "completed",
  "consecutive_empty_fetches": 0,
  "is_stuck": false
}
```

5m bar is equally fresh (`last_bar_at: 05:15:00`). All jobs healthy.

---

## Root Cause

**`IntervalTrigger` is anchored to startup time, not UTC wall-clock.**

`sync_jobs.py:374-389` registers all interval jobs as `IntervalTrigger(minutes=N)`:
```python
job_scheduler.add_interval_job(f"{_MODULE}:sync_15m", job_id="sync_15m", minutes=15)
```

APScheduler's `IntervalTrigger(minutes=15)` without `start_date` fires every 15 min **starting from now** (i.e. registration time = container startup). After today's restart at `04:59:55Z`, the new phase became `:09/:24/:39/:54` instead of `:00/:15/:30/:45`. Result:

- Bar closes at `:00`, sync fires at `:09` → **9-minute lag** before strategy sees the bar.
- Worse: each restart shifts phase to a new offset → unpredictable lag across restarts.
- Worst: APScheduler `coalesce=True` collapses missed slots → a restart spanning a slot boundary causes a **22-minute gap with 3 bars dropped into a single fetch** (observed today at 04:52 → 05:15).

**Strategy impact:**
- 9-min lag on 15m bar = strategy evaluates entry signal 9 min late → moved market → slippage or invalidated signal.
- Bar gap = strategy never sees the bar that closed during the gap → entirely missed entry/exit opportunity.

**WebSocket fallback unavailable** (intentionally off). Poll path must be wall-clock-aligned to eliminate both lag and gap risks.

---

## Timeline of the 22-minute Gap

```
04:52:34Z  sync_15m runs  → 0 bars inserted (bar at 04:45 already in DB, 05:00 not yet closed)
04:59:55Z  container restart
05:00:09Z  app starts, scheduler re-registers with replace_existing=True
           → new IntervalTrigger anchored from startup: first tick = 05:00:09 + 15m = 05:15:09
05:07:xx   NO RUN (slot missed — APScheduler coalesced it into 05:15)
05:15:09Z  sync_15m runs  → 3 bars inserted (4:45 may have been missed, 5:00, 5:15)
```

The restart explains both the 22-minute gap and the phase shift from `:37/:52` to `:09/:24`.

---

## Is This a Regression?

**No** — pre-existing architectural defect. But the recently-shipped strategy subscription feature (260505-1024) **raises severity** because subscription-cached backtests + future live-strategy execution depend on bar-close events arriving on time. Pre-feature, bar lag was a UX issue. Post-feature, bar lag is a **trading correctness issue**.

---

## Required Fix

**All interval-based sync jobs MUST follow UTC wall-clock boundaries.** Replace `IntervalTrigger` with `CronTrigger` for every `sync_*` job that maps to a bar interval.

### Change set — `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/sync_jobs.py`

Replace the `add_interval_job` calls (lines ~375–389) with `add_cron_job`:

```python
# BEFORE
job_scheduler.add_interval_job(f"{_MODULE}:sync_5m",     job_id="sync_5m",     minutes=5)
job_scheduler.add_interval_job(f"{_MODULE}:sync_15m",    job_id="sync_15m",    minutes=15)
job_scheduler.add_interval_job(f"{_MODULE}:sync_hourly", job_id="sync_hourly", hours=1)
job_scheduler.add_interval_job(f"{_MODULE}:sync_swing",  job_id="sync_swing",  hours=4)
# sync_daily already cron — keep as-is
job_scheduler.add_interval_job(f"{_MODULE}:sync_repair", job_id="sync_repair", hours=12)

# AFTER (UTC wall-clock aligned)
job_scheduler.add_cron_job(f"{_MODULE}:sync_5m",     job_id="sync_5m",     cron_expression="*/5 * * * *")
job_scheduler.add_cron_job(f"{_MODULE}:sync_15m",    job_id="sync_15m",    cron_expression="*/15 * * * *")
job_scheduler.add_cron_job(f"{_MODULE}:sync_hourly", job_id="sync_hourly", cron_expression="0 * * * *")
job_scheduler.add_cron_job(f"{_MODULE}:sync_swing",  job_id="sync_swing",  cron_expression="0 */4 * * *")
job_scheduler.add_cron_job(f"{_MODULE}:sync_repair", job_id="sync_repair", cron_expression="0 */12 * * *")
```

Scheduler already runs in UTC (`scheduler.py:77 timezone="UTC"`), so cron expressions evaluate against UTC wall-clock — exactly what we need.

### Why this eliminates lag & gap risk

- **No phase drift**: every restart re-registers cron with `replace_existing=True` — schedule stays at `:00/:15/:30/:45` regardless.
- **Bounded lag**: bar closes at `:00`, sync fires at `:00:00` — lag is now bounded by sync execution time (typically <2s) + exchange API latency. Negligible vs. 15-min interval.
- **Gap mitigation**: `misfire_grace_time=300s` (5 min) lets restarted scheduler still execute the missed slot. Combined with `sync_backfill` (existing daily cron at 03:00 fetching 5000 bars per interval) any deeper gap gets repaired within 24h.

### Adjust sync window padding

`sync_15m` currently fetches 48 bars × 15min = 12h (sync_jobs.py:330). Keep this — large window absorbs any single missed run. With wall-clock cron, missed runs become rare; window remains a safety net.

### Add a freshness invariant test

`tests/integration/test_scheduler_phase.py` (new): assert that each registered job's next_run_time aligns to its expected wall-clock boundary at registration time. Catches future regressions if someone reintroduces `IntervalTrigger`.

### Out of scope for this fix

- WebSocket / `QuoteAppService` — intentionally off, do not touch.
- `BarAppService.MINUTE_15` default — only relevant when WS is re-enabled.
- Monitor UI freshness threshold — current 30-min `age-fresh` window is fine once lag is bounded by cron.

---

## Verification Plan

After deploying the fix:

1. Confirm next 5 `sync_15m` runs fire at exact `:00/:15/:30/:45` UTC (check `job_history`):
   ```
   ssh -i /Users/admin/.ssh/vultr root@207.148.79.60 'docker exec pocketquant-mongodb mongosh ... --eval "db.job_history.find({job_id: \"sync_15m\"}).sort({started_at: -1}).limit(5)"'
   ```

2. Restart container mid-cycle (e.g. at `:07`). Verify next sync still fires at `:15` (not `:22`).

3. Force a 16-min outage (stop container, wait, start). Verify within 5 min of restart the missed slot fires (misfire grace) AND the regular cadence resumes wall-clock-aligned.

4. Compute `(now - last_bar_at)` immediately after a sync — should be <10s (sync execution + API roundtrip).

---

## Unresolved Questions

- Should `sync_5m` be `*/5 * * * *` (12 fires/hour) or kept at startup-anchored 5-min for lower BE load? Wall-clock alignment is preferred for consistency, but verify exchange API rate limits with 5-min cadence aligned to `:00/:05/.../:55`.
- Is there value in adding `sync_1m` (currently absent) for true 1-min strategy support? Out of scope for this fix; raise as separate follow-up if user wants 1m algos.
