---
name: verify-cascade-newest-bucket-race
description: sync_verify_cascade (HH:00:00) compares the newest stored 5m bucket 2 s before sync_1m (HH:00:02) stores its last minute, so one bucket per run diverges on volume; lag-independent (crypto too); diagnosed 2026-10-22, fix deferred as follow-up
metadata:
  type: project
---

Diagnosed 2026-10-22 while closing plan `260921-1436-asset-class-index-futures` (Phase 8, row 11). Counsel: `D:/w/_me/algotrading/pocketquant/plans/reports/archive/kongming-261022-1745-phase8-row10-row11-failures.md`.

- `sync_verify_cascade` fires at HH:00:00, `sync_1m` at HH:00:02; the verify compares every matched REST 5m bucket including the newest stored one, which the cascade built without its last minute (the adapter drops the vendor frontier bar; the cascade silently persists short buckets). REST side is complete. Result: ~1 of 11-12 compared buckets diverges (volume always, close sometimes) in most hourly runs, for futures and crypto alike. Measured 2026-10-22: ES 5 alerts / 1 ok / 2 vendor failures in 8 runs.
- Recorded in the plan as "Fail as worded, cascade correct on every completed bucket, verify-job defect". Fix was NOT made (phase was no-code; user focus is Exness).
- Follow-up spec: skip the newest matched bucket in `_verify_one_symbol` (~4 lines + 1 test); re-word metric 11 to skip runs where the vendor returned no series (scraper drops ~2/8 fetches at :00). Alternative: delete the job. Possibly also move the cron off :00 if `no_progress` clusters there (uncounted).
- Row 10 lesson: a weekend `sync_backfill` legitimately inserts the closed `1w` bar on Saturday 03:00Z; a "no backfill insert on the weekend" pass clause is wrong.

**Why:** The defect is in a read-only monitoring job, so it is easy to misread as cascade corruption or as a delayed-feed problem; a lag-based exclusion is the tempting wrong fix.

**How to apply:** If asked about cascade divergence alerts, `sync_verify_cascade`, or metric 11, start from this diagnosis and check whether the follow-up landed (`grep -n "newest" src/pocketquant/engine/market_data/app_services/sync_jobs.py`). See also [[exness-cook-prod-and-gate-quirks]].
