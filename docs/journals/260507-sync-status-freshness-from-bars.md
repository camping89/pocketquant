# Sync Status Freshness — Derive from Bars (Cluster A)

**Date**: 2026-05-07 16:27
**Severity**: High
**Component**: GetSyncStatusHandler, GetSymbolSyncStatusHandler, sync_jobs.py
**Status**: Resolved

## What Happened

Cascade aggregator writes 5m/15m/1h/4h/1d directly to bars without touching sync_status. sync_status.last_bar_at lagged reality by up to 1 hour, triggering false-STUCK badges within 15 min after sync_backfill. GetSymbolSyncStatusHandler also had silent bug: is_stuck field never populated (defaulted False).

## Solution: Compose from Both Sources

API now derives freshness from bars (data truth) + sync_status (semantic "last command"). Chose over cascade-write approach (N×5 writes/min bookkeeping) because range-scan O(log V + K) << per-doc O(K · log V) at scale.

## Changes

- 2 handlers refactored, is_stuck bug fixed
- no_tracked_symbols bumped to WARNING (was buried at INFO, undetected for hours)
- 12 unit tests: cascade-fresh-not-stuck, all-stuck, exception isolation, last_sync_at preservation
- ruff + pyright clean

## Verification

Post-deploy: API bar_count + last_bar_at match Mongo aggregation. 5m last_bar_at: 03:00 (stale) → 09:20 (real). False STUCK eliminated. WARN log correctly fired on tracked_symbols deletion.

Bonus: Detected real 1m outage (stuck=True after delete) that pre-fix would've missed. Correctness win, not just UX polish.

**Status**: DONE
