---
name: phase03-fold-go-and-cost-baseline
description: 2026-11-04 GO on plan 261103-1741 Phase 03 (repair/backfill re-cascade 7 days); local cost 12.7 s/symbol first run, 8.3 s unchanged (Binance 24x7, 11520 1m bars); window-edge nit accepted
metadata:
  type: project
---

Phase 03 of `plans/261103-1741-1d-cascade-fold-and-small-fixes` got GO on 2026-11-04: `_cascade_all(lookback)` with three callers (`sync_1m` 100, `sync_repair` and `sync_backfill` `_REPAIR_DAYS * 1440` = 10080); repair REST-touches only 1m and 1w.

Local cost baseline (one symbol, BTCUSDT:BINANCE, 8 days of 1m = 11520 bars, local Docker Mongo): first `_cascade_all(10080)` 12.70 s, second run on unchanged bars 8.28 s; bucket counts 5m 2017, 15m 673, 1h 169, 4h 43, 1d 8. Exness `bar_start` is arithmetic (`exness_bar_start`), so session calendars should not cost more (inference, unmeasured).

Accepted nit (no action): the repair window is `now_repair - 7d` per symbol and the cascade window is `now_cascade - 7d` after the whole loop, so a 1m bar repaired in the first ~1-2 min of the 7-day edge can miss its 5m/15m fold. Bars that old are rarely repaired; 1d/4h buckets still cover them because `compute_boundaries` floors `range_start`.

**Why:** Phase 05 Task 05.4 item 2 reads prod `duration_ms` for `sync_repair`/`sync_backfill` with a 600 s ceiling (R1); the local baseline says ~10 s per symbol, so expect low minutes for ~6 symbols. The last five prod `sync_repair` runs before this change took 57-106 s ([[sync-repair-stall-and-skip-listener-bug]]).

**How to apply:** If Phase 05 shows a repair over ~5 min, look at symbol count and Mongo round trips, not the calendar. If the D16 dry run reports mismatches only on 5m/15m at the 7-day edge, cite the accepted nit before suspecting the fold.
