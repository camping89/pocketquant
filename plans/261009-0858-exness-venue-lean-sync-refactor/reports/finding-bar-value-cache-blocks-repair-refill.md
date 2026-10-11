# Finding: a warm bar value cache stops repair from refilling a deleted bar

**Severity:** low (inference, see the last section). Production code was not changed, because Phase 02 is test-only.

## Symptom
In the Phase 02 sync pipeline characterization test (T2.4 step e), a 1m bar is deleted with `BarRepository.delete_many_by_ids` and `sync_repair` runs. The job logs `upserted=100` and finishes `completed`, but the deleted bar is not written back. The test then fails with `assert 0 == 1` on the count of the deleted datetime.

## Cause (verified)
- `src/pocketquant/core/infra/persistence/repositories/bar_repository.py:83-85`: `upsert_bar` returns without any DB IO when the module-level `_BAR_VALUE_CACHE` (`TTLCache(maxsize=20_000, ttl=3600)`) already holds the same OHLCV for `(symbol, interval, datetime)`.
- `integrity_jobs.py:98-105`: `repair_integrity` resyncs through `sync_one(..., skip_filter=True)`. That flag skips only the existing-bar filter, so the bars still pass through `_persist_bars`, then `insert_many`, then `upsert_bar`.
- `bar_repository.py:51-54`: `insert_many` counts every `upsert_bar` call that does not raise, so a bar the cache skipped still counts as upserted.
- `delete_many_by_ids` and `delete_many_by_range` do not evict cache keys.
- Evidence: the unchanged test with one added `_BAR_VALUE_CACHE.clear()` before `sync_repair` passes (a) through (h). kongming verified this with a throwaway copy, and I verified it again in the committed test.

## Test handling
Before running `sync_repair`, the characterization test clears `_BAR_VALUE_CACHE`. This models a process restart or TTL expiry. The plan's (e) assertions are kept exactly as written. The unit test `tests/core_test/infra/persistence/test_bar_repository_upsert_cache.py` (`TestCacheHit`) already pins the cache-hit skip itself.

## Candidate fix (not applied)
Evict the cache keys in `delete_many_by_ids` and `delete_many_by_range`, or let the repair path bypass the cache. The fix needs its own test and belongs outside this plan, because no phase of this plan edits `bar_repository.py`.

## Severity rationale (inference)
A deleted bar cannot be refilled only while its cache entry is still warm, which lasts up to 3600 s after the last write to that key. After the entry expires, the next `sync_1m` or `sync_repair` refills the bar. The severity would rise if some production path deleted recent bars and expected the same process to refill them right away, for example a resync that calls `delete_many_by_range` and then syncs immediately. No such path was checked.
