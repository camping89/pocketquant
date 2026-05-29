# Fixed `filter_new_bars` Non-Contiguous DB Gap Handling

**Date**: 2026-05-07 15:30  
**Severity**: High  
**Component**: `market_data/sync_one/bar_filters.py`  
**Status**: Resolved  

## What Happened

Production monitor showed BINANCE:BTCUSDT stuck at 9985 gaps. Sync pipeline fetched 5000 bars, filtered 4997 as "existing," inserted 0. DB reality: only 220 1m bars present. The `filter_new_bars` heuristic died on scattered holes.

## The Brutal Truth

We shipped a filter that assumed DB contiguity. When Mongo had holes spanning 2026-04-30 to 2026-05-03, bars meant to *fill those gaps* got dropped before insert. Sync backfill was broken for any non-sequential data — a stupid assumption for a real system.

## Technical Details

**Root cause**: `latest - 3 intervals` cutoff in `bar_filters.py:45`. Calculated from last bar's timestamp, not actual DB state. Real DB had scattered missing ranges → set subtraction excluded everything.

**Impact metrics**: 1m gaps 9866→5080 (TV cap), 5m 84→0, 15m 28→0, 1h 7→0.

**Side discoveries**:
- `tracked_symbols` empty until 2026-05-07T01:38 (silent no-op for sync_repair before)
- Cascade aggregator doesn't update sync_status (false-stuck UX)

## What We Tried

**Option 1 (shipped)**: Replace heuristic with `bar_repo.find_datetimes(symbol, interval)`, coerce Mongo timestamps to tz-aware UTC, do actual set membership check.

**Option 2 (rejected)**: No filter, rely on dedup index. Rejected: doesn't handle non-contiguous correctly, O(K·log V) per doc vs O(log V + K) range scan.

## Root Cause Analysis

Heuristic born from assumption (contiguous data) that real production violated. No test covered scattered holes in Mongo. Deployed confidence in a wrong model.

## Lessons Learned

1. **Never assume data structure properties**: Contiguity must be proven, not assumed. Query actual DB state.
2. **Heuristics are debt**: They feel fast until they're wrong. Query-based filters cost less at scale.
3. **Silent failures are deadlier**: `tracked_symbols` empty broke sync_repair without noise. Monitor showed stuck, root was missing config.

## Next Steps

**Immediate**: Deploy merged to develop, CI green, VPS 207.148.79.60 running /integrity/repair. All gaps cleared except 1m (TV 5000-bar pagination limit — separate ticket).

**Follow-up tickets** (flagged, not part of this fix):
- Tracked_symbols initialization (sync_repair was silent no-op)
- Cascade aggregator sync_status update
- 1m date-paginated fetch for gaps spanning >5000 bars

**Code**: Commit fb1e8e2 on develop. 14/14 tests pass (4 unit scenarios, 7 edge cases, 3 integration with testcontainer Mongo).

---

**Status:** DONE
