---
name: phase16-coverage-calendar-holiday-blind-and-5m15m-gap
description: Phase 16 Task 16.1 (2026-11-02) failed - Exness calendar has no holiday table so 99% sub-daily coverage is unattainable; prod 5m/15m XAUUSD bars exist only from 2026-09-23/08-03 (REST 5000-bar backfill), never cascaded over history
metadata:
  type: project
---

Phase 16 Task 16.1 coverage check failed on 2026-11-02: 5m 10.73 %, 15m 24.67 %, 1h 98.46 %, 4h 98.76 %, 1d 99.68 % against the calendar-expected bar set for 2025-11-03..2026-10-31.

Two separate causes:
1. `ExnessSessionCalendarAdapter` is a weekly template only (no holiday dates). 1h missing 92 bars = 4 x 23 bars/day, matching Dec 25, Jan 1, Good Friday Apr 3 plus partial days. Any sub-daily interval measured against this calendar tops out near 98.5 % even with perfect data, so a flat 99 % threshold is wrong (inference from arithmetic; per-date listing of missing 1h bars confirms it).
2. Stored 5m/15m XAUUSD:EXNESS bars come only from a `sync_backfill` 5000-bar REST fetch (~2026-09-23 for 5m, ~2026-08-03 for 15m). Live cascade (`cascade_for_symbol`, lookback 100 min from now) never backfills history; `sync_repair` covers 7 days; the backfill route caps 1m at 5000 bars. No repo tool cascades a range; `cascade_for_symbol(symbol, lookback_minutes=<minutes back to 2025-10-21>, repo, calendar)` from a one-off script in the api container is the no-code-change route (re-upserts all five cascade TFs, deterministic).

**Why:** backtests stream the entry interval from stored bars (`backtest_app_service.py`) and preload higher intervals with `find` on stored bars; nothing aggregates from 1m at backtest time.

**How to apply:** advised an [ASK] bundling (a) one-off full-range cascade and (b) amend the Task 16.1 pass rule to a 1m-anchored expected set (coverage relative to stored 1m minutes) plus a listing of missing-1m dates. Exness REST keeps limited history (`docs/deployment.md`), so a direct 5m/15m REST backfill of a year is not reliable.
