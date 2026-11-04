---
title: Repair and backfill fold late 1m bars
date: 2026-11-04
summary: "sync_repair and sync_backfill re-cascade 7 days of 1m for every tracked symbol, and the REST repair fetches only 1m and 1w; one commit green in CI"
---

# Repair and backfill fold late 1m bars

## What happened
This is Phase 03 of `plans/261103-1741-1d-cascade-fold-and-small-fixes`. Commit `0b5a0608` is on `develop`, and CI run 41768197210 passed on it.

- The per-symbol cascade loop of `sync_1m` moved into `_cascade_all(lookback_minutes)`. `sync_1m` calls it with 100 minutes; `sync_repair` and `sync_backfill` call it with 7 days, so a 1m bar they write days back now reaches its 5m-1d buckets.
- `sync_repair` asks REST only for 1m and 1w. The cascade rebuilds 5m-1d, so prod stops rewriting 5000 REST 5m bars on gaps it cannot fill (E3).
- `sync_backfill` cascades even when its REST sync failed, then re-raises, the same rule as `sync_1m`.

## Measurements
Local Mongo was empty and was seeded with 8 days of 1m for BTCUSDT and ETHUSDT. `_cascade_all(10080)` took 12.70 s for one symbol cold and about 8.5 s per symbol with unchanged bars; cost grows linearly. An event-loop probe beside it saw at most 20 ms of lag, so the cascade does not stall `sync_1m`.

## Lessons
- Adding a keyword argument to `repair_integrity` calls broke every test fake that spelled out its parameters. Search the tests for monkeypatched fakes before changing a call signature.
- `_wire` in `test_sync_jobs_tracked.py` now stubs the cascade by default. Without it, repair and backfill tests run the real cascade against a `MagicMock` repository and only pass because the per-symbol error is caught.

## Next steps
Phase 04 adds the hourly 1d self-consistency check. Phase 05 must read both `sync_repair` and `sync_backfill` durations on prod; backfill now carries a 7-day cascade and was never timed there.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
