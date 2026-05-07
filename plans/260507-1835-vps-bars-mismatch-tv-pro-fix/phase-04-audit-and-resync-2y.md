# Phase 04 — Audit + 2y re-sync from Binance (all canonical tfs)

## Context links

- Brainstorm Phase 4: [`brainstorm-260507-1835-vps-bars-mismatch-tv-pro-fix.md`](../reports/brainstorm-260507-1835-vps-bars-mismatch-tv-pro-fix.md) §"Phase 4 — Audit"
- Audit query skeleton: [`researcher-02-volume-and-audit.md`](./research/researcher-02-volume-and-audit.md) §"MongoDB Audit Query Patterns"
- Existing backfill (extend): `pocketquant/scripts/backfill_1m_from_binance.py`
- Phase 01 deliverable: `BinanceClient`
- Phase 03 deliverable: production wired with Binance only

## Overview

- **Priority:** P1 — final fix step
- **Status:** pending
- **Effort:** 6h
- **Description:** Two scripts. (1) `audit_bar_quality.py` — measure flat-bar / zero-volume contamination across last 2 years across all tfs, save Markdown report. (2) `resync_2y_from_binance.py` — for each tracked symbol: delete bars in `[now-2y, now-1m]` window across **all canonical tfs** (1m, 5m, 15m, 1h, 4h, 1d), re-fetch 1m from `BinanceClient`, then cascade-build higher tfs from clean 1m source.

## Key insights

- Re-sync window: `[now - 2y, now - 1m]` per symbol — `now - 1m` floor avoids touching WS in-progress bar
- Volume: 50 symbols × 2y × 1440 1m bars/day ≈ **52.5M bars**; ~52,500 REST calls × 100ms ≈ 88 min sustained
- Wall time budget: 90-120 min single-run; resumable checkpoint enables multi-day execution if rate-limits surface
- Cleanup scope: delete ALL canonical tfs (1m, 5m, 15m, 1h, 4h, 1d) within window, then cascade-rebuild higher tfs from refetched 1m source — prevents legacy contaminated bars surviving
- Audit runs **before** re-sync to capture baseline contamination metric for changelog
- Cascade re-aggregation reuses existing `cascade_aggregator.py` (math-only, no extra API calls)
- Idempotent: re-running re-sync = no duplicate bars (unique index dedup)
- Mongo snapshot before destructive delete — recovery insurance

## Requirements

### Functional — Audit script
- CLI: `audit_bar_quality.py [--days N=730] [--symbol BTCUSDT --exchange BINANCE] [--output PATH]`
- Per (symbol, exchange, interval): count `total`, `flat_bars` (O==H==L==C), `zero_volume`, `abnormal_volume`
- Compute percentages
- Output: Markdown table to `plans/reports/audit-{date}-bar-quality.md`
- Exit code 0 on success, 1 on Mongo connection failure

### Functional — Re-sync script
- CLI: `resync_2y_from_binance.py [--days N=730] [--symbols A,B,C] [--dry-run] [--no-cascade]`
- Default: ALL tracked symbols from `tracked_symbols` collection (BINANCE exchange only — non-Binance skipped with warning)
- Per (symbol, exchange):
  1. Delete bars in `[now-2y, now-1m]` for **all canonical tfs**: `[1m, 5m, 15m, 1h, 4h, 1d]`
  2. Fetch 1m bars via `BinanceClient.fetch_ohlcv` (chunked 1000)
  3. `bar_repo.insert_many(ordered=False)` for 1m
  4. Run `cascade_aggregator` to rebuild 5m, 15m, 1h, 4h, 1d from clean 1m
- Resumable checkpoint: per-symbol completion state in `/tmp/resync-checkpoint.json`; restart skips done symbols
- Per-symbol progress logging: `resync.symbol_progress symbol=BTCUSDT pct=37.4 bars_inserted=971280 elapsed_s=42`
- Rate limit: 100ms inter-call sleep + Binance 1200 weight/min cap
- Dry-run: prints plan + estimated calls/wall time, no DB writes
- Multi-day execution: `--symbols` filter + checkpoint allows operator to split work across multiple runs (e.g., 25 symbols Day 1, 25 Day 2)

### Non-functional
- Audit script <2 min wall time via compound index `(symbol, exchange, interval, datetime)`
- Re-sync `--days` arg parameterizable (allows future 30d/90d top-ups)
- Both scripts: structlog output, MongoDB URL via env (`MONGODB_URL`)
- Total LOC budget per script: ≤200 (split helpers if needed)

## Architecture

```
audit_bar_quality.py
        │
        ▼
MongoDB aggregation pipeline (compound index → group by interval)
        │
        ▼
plans/reports/audit-{YYYYMMDD}-bar-quality.md  ◄── markdown table


resync_2y_from_binance.py
        │
        ├── Read tracked_symbols (filter exchange=BINANCE)
        ├── Compute window: end = now.floor(1m) - 1s; start = end - 730d
        │
        ├── For each symbol (skip if checkpoint=done):
        │     ├── pre-snapshot: mongodump (manual; documented)
        │     ├── DELETE bars where exchange=BINANCE, symbol=<sym>,
        │     │     interval IN [1m,5m,15m,1h,4h,1d], datetime IN [start,end]
        │     ├── BinanceClient.fetch_ohlcv(symbol, BINANCE, 1m,
        │     │     n_bars≈1,051,200)  (chunked 1000, ~1052 calls)
        │     ├── bar_repo.insert_many(ordered=False)
        │     ├── cascade_aggregator.run(symbol, BINANCE, [5m,15m,1h,4h,1d])
        │     ├── checkpoint.write({symbol: "done"})
        │     └── log progress: % completed across symbol set
        │
        └── Save audit-after report (re-run audit, compare metrics)
```

## Related code files

**Create:**
- `pocketquant/scripts/audit_bar_quality.py` (≤200 LOC) — pymongo aggregation per research-02
- `pocketquant/scripts/resync_2y_from_binance.py` (≤200 LOC) — orchestrates delete + fetch + insert + cascade
- `pocketquant/tests/scripts/test_audit_bar_quality.py` — unit test pipeline construction
- `pocketquant/tests/scripts/test_resync_2y_from_binance.py` — unit test orchestration (mock BinanceClient + bar_repo)

**Read for reference / reuse:**
- `pocketquant-api/src/pocketquant/api/market_data/app_services/cascade_aggregator.py`
- `pocketquant-core/src/pocketquant/core/persistence/repositories/bar_repository.py`
- `pocketquant-core/src/pocketquant/core/persistence/repositories/tracked_symbol_repository.py`

**Possibly modify:**
- `BarRepository` — add `delete_many_by_range(symbol, exchange, intervals: list[Interval], start, end) -> int` accepting list of intervals (≤30 LOC, unit test)

**Output (deliverable, not code):**
- `plans/reports/audit-260507-bar-quality.md` (pre-resync)
- `plans/reports/audit-260507-bar-quality-post.md` (post-resync, success metric)

## Implementation steps

1. Audit Mongo indexes — confirm compound `(symbol, exchange, interval, datetime)` exists; create if missing in `BarRepository.ensure_indexes`.
2. Write `audit_bar_quality.py`:
   - Parse args; connect Mongo via Settings
   - Aggregation pipeline; group per (symbol, exchange, interval)
   - Render Markdown table: symbol, exchange, interval, total, flat_pct, zero_vol_pct, abnormal_vol_count
   - Save to `plans/reports/audit-{date}-bar-quality.md`
3. Add `BarRepository.delete_many_by_range`:
   ```python
   async def delete_many_by_range(self, symbol, exchange,
                                   intervals: list[Interval],
                                   start_dt, end_dt) -> int:
       result = await coll.delete_many({
           "symbol": symbol, "exchange": exchange,
           "interval": {"$in": [i.value for i in intervals]},
           "datetime": {"$gte": start_dt, "$lt": end_dt}})
       return result.deleted_count
   ```
4. Write `resync_2y_from_binance.py`:
   - Parse args; load tracked symbols (filter exchange=BINANCE)
   - Compute window: `end = now.floor("1min") - timedelta(seconds=1)`; `start = end - timedelta(days=730)`
   - Per-symbol loop (resumable via `/tmp/resync-checkpoint.json`):
     - Delete: `bar_repo.delete_many_by_range(symbol, BINANCE, [1m,5m,15m,1h,4h,1d], start, end)`
     - Fetch 1m: `BinanceClient.fetch_ohlcv(symbol, BINANCE, MINUTE_1, n_bars≈1_051_200)` (internal chunking)
     - Insert: `bar_repo.insert_many(ordered=False)`
     - Cascade: `cascade_aggregator.run(symbol, BINANCE, [5m,15m,1h,4h,1d])`
     - Checkpoint write + progress log
   - Print summary: per-symbol fetched/inserted/cascade counts, total wall time
5. Unit tests both scripts (mock httpx + mock Mongo collection).
6. **Production run sequence (manual, in script docstring):**
   - `mongodump --uri=$MONGODB_URL --db=pocketquant --collection=bars --out=/backup/{date}` (snapshot)
   - `python scripts/audit_bar_quality.py --days 730` → save pre-report
   - `python scripts/resync_2y_from_binance.py --days 730 --dry-run` → verify plan + estimated wall time
   - `python scripts/resync_2y_from_binance.py --days 730` → execute (90-120 min)
   - **Multi-day option:** `--symbols BTCUSDT,ETHUSDT,...` (split set across days; checkpoint persists)
   - `python scripts/audit_bar_quality.py --days 730` → save post-report
   - Compare pre/post; commit both reports

## Todo list

- [ ] Confirm/create Mongo compound index `(symbol, exchange, interval, datetime)`
- [ ] `audit_bar_quality.py` script
- [ ] Add `BarRepository.delete_many_by_range` accepting interval list (with unit test)
- [ ] `resync_2y_from_binance.py` script with checkpoint + per-symbol progress logging
- [ ] Unit tests for both scripts
- [ ] Document production run procedure (single-day + multi-day) in script docstring
- [ ] Execute pre-audit on production VPS
- [ ] Execute mongodump snapshot
- [ ] Execute re-sync (dry-run → live)
- [ ] Execute post-audit; commit reports to `plans/reports/`

## Success criteria

- Pre-audit report saved to `plans/reports/audit-260507-bar-quality.md`
- Post-resync all canonical tfs: flat_pct ≤ 5%, zero_vol_pct ≤ 5% (from ~100%/~100%)
- Higher tfs (5m/15m/1h/4h/1d) derived from clean 1m source — no legacy bars in window (spot-check 5 bars/tf vs Binance website)
- Integrity check `POST /api/v1/market-data/integrity/check` reports `missing_count: 0` for last 2y
- Resync idempotent: 2nd run inserts 0 (deduped)
- Re-sync wall time 90-120 min for 50 symbols × 2y × 1m (single-day execution); multi-day execution supported via `--symbols` filter
- No file >200 LOC

## Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Mongo `delete_many` deletes more than intended (filter typo) | Low | Critical | Mandatory `--dry-run` first; mongodump snapshot pre-run; explicit interval-list filter |
| Binance IP ban during ~52,500 calls | Medium | High | 100ms sleep × 52,500 ≈ 88 min sustained, well under 1200 weight/min cap; resumable checkpoint enables split runs; abort on 429 with progressive backoff (2/3/5 min) |
| Aggregation pipeline OOM on 52.5M bars collection | Low | Medium | `allowDiskUse=True`; compound index ensures `$match` uses index (not COLLSCAN); audit per-symbol if needed |
| Cascade aggregator math drift on edge bars (UTC midnight, year boundaries) | Low | Low | Existing cascade_aggregator unit tests cover boundaries; spot-check post-run |
| Re-sync overwrites WS in-progress bars | Medium | Medium | Window ends at `now - 1m` (last full bar only). Implementation: `end_dt = now.floor("1min") - timedelta(seconds=1)` |
| Production cron `sync_1m` races with re-sync | Medium | Low | Insert uses `ordered=False` + unique index → safe dedup; both writers idempotent |
| Wall-time creep (Binance latency spikes) blows past single-day | Medium | Medium | Multi-day via `--symbols` filter + checkpoint; runbook |
| Disk space exhaustion (52.5M bar docs) | Low | High | Pre-flight `df -h /var/lib/mongo` ≥ 50GB; runbook |

## Security considerations

- Mongo URL via env, never CLI flag in production (avoid shell history leak)
- Snapshot stored in restricted-access volume; rotated after 7 days
- Audit Markdown report contains symbol list — non-sensitive (already public via API)

## Next steps

- Phase 05 documents the audit/resync runbook in `deployment-guide.md`.
- If contamination % spikes again post-fix, escalate root cause (likely cascade aggregator regression).

## Unresolved questions

1. Per-symbol vs single-pass deletion order? **Answer:** Per-symbol — checkpoint resumability outweighs batch atomicity.
2. Re-sync triggers cascade for which intervals? **Answer:** All canonical (5m, 15m, 1h, 4h, 1d) — same set as cron sync_1m cascade.
3. Integrity check post-resync auto-run? **Answer:** No — keep concerns separate; runbook step.
4. Auto-throttle to multi-day if >2h estimated? **Recommendation:** No — operator controls via `--symbols`. YAGNI.
