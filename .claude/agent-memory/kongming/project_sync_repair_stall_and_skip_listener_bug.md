---
name: sync-repair-stall-and-skip-listener-bug
description: Prod 00:00/12:00 UTC sync_repair blocks the loop 25-49 min (bigger than the 04:00 integrity stall); job_history skip listener never records max_instances drops
metadata:
  type: project
---

`sync_repair` (cron `0 */12`) is the largest event-loop stall in prod: median 1,527 s, max
2,947 s over 14 runs (7 days to 2026-10-28). The earlier diagnosis report
(`debug-261023-0045-...`) only covered the 04:00 `sync_integrity` stall (~7 min). Same root
cause: CME calendar `iterrows()` per `bar_start` call.

Also found: `JobScheduler._on_skip` reads `event.scheduled_run_time`, but
`EVENT_JOB_MAX_INSTANCES` events carry `scheduled_run_times` (list), so no
`skipped_max_instances` row was ever written; `coalesce=True` hides misfires too.

**Why:** Measured read-only on prod on 2026-10-28; advisory report
`plans/reports/kongming-261028-0848-event-loop-concurrency-review.md` recommends calendar
table + bisect, an event-loop lag probe, and the listener fix; no threads/processes.

Update 2026-10-28: 7-day prod logs show Exness and Binance WS reconnects clustering in the
00h and 12h UTC hours (the stall windows) and 72 "Error notifying listener" lines, which
confirms the listener bug fires on every dropped run. The bisect fix was dropped on
2026-10-28 because TradingView (and so the CME calendar) is deprecated; see
[[parallel-exness-only-direction]].

**How to apply:** When anyone asks about job drops or stalls, check 00:00/12:00 UTC windows
too, and do not trust job_history skip rows until the listener is fixed. Prod Python is
3.14.0rc3 (GIL build) from `python:3.14-rc-slim`.

Update 2026-11-01 (read-only prod job_history): the last five `sync_repair` runs (10-30 to
11-01) finished in 57-106 s and `sync_integrity` in 5 s, so the 25-49 min stall no longer
shows. Inference, not verified: the TradingView/CME symbols were removed, which took the
`iterrows()` calendar out of the loop. Treat the stall numbers above as history.
