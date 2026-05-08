---
phase: 2
title: "Backfill regression window"
status: completed
priority: P1
effort: "2h"
dependencies: [1]
---

# Phase 2: Backfill regression window

## Overview

Backfill bars bị corrupt từ 2026-05-08 07:30 UTC (lúc 2y resync của plan trước hoàn thành) đến lúc deploy Phase 1. Delete partial bars + re-sync via fixed code path + re-cascade higher tfs.

## Context Links

- Phase 01 (must be deployed first)
- Predecessor migration's audit/resync script: `plans/260507-1835-vps-bars-mismatch-tv-pro-fix/phase-04-audit-and-resync-2y.md`
- Debug report: `plans/reports/debugger-260508-2116-binance-bar-mismatch.md`

## Requirements

**Functional:**
- Detect tất cả bars corrupt trong window `[2026-05-08T07:30:00Z, deploy_time)`.
- Delete partial 1m bars + downstream cascade outputs (5m, 15m, 1h, 4h, 1d) cho cùng window.
- Re-sync 1m từ Binance qua fixed `BinanceClient` (Phase 1).
- Re-cascade higher tfs từ clean 1m source.
- Idempotent: chạy lại không gây hại.

**Non-functional:**
- mongodump backup trước khi delete.
- Pause `sync_1m` cron để tránh race với backfill.
- Rate limit safe: ~7h window × 60 phút/h × 6 tracked symbols = ~2520 bars 1m → 3 calls @ 1000 bars/call/symbol = ~18 calls. Trong budget.

## Architecture

```
1. Pause sync_1m cron on VPS (or set ENABLE_JOBS=false temporarily on backfill instance)
2. mongodump --uri "$MONGODB_URL" --collection bars --out /tmp/pq-backup-260508-backfill/
3. For each tracked_symbol:
   a. Delete bars where datetime ∈ [07:30 UTC, now] AND interval ∈ {1m, 5m, 15m, 1h, 4h, 1d}
   b. Call Mediator: SyncSymbolCommand(symbol, exchange, MINUTE_1, n_bars=500)
      → fetch via fixed BinanceClient (Phase 1)
      → bar_repo.insert_many fresh bars
   c. cascade_for_symbol(symbol, exchange, lookback_minutes=500, bar_repo)
      → re-aggregate clean 1m → 5m/15m/1h/4h/1d
4. Verify: query DB sample bar at 09:30 UTC; compare with Binance REST → must match
5. Resume sync_1m cron
```

**Choice point:** Make this a one-shot Python script (`scripts/backfill_regression_window.py`) — không phải migration tool persisted. KISS, run once và xoá. Không add CLI flag/cron job.

## Related Code Files

**Create:**
- `scripts/backfill_regression_window.py` — one-shot backfill script (deletable after success)

**Read for context:**
- `packages/pocketquant-core/src/pocketquant/core/persistence/repositories/bar_repository.py` — for `delete_many` (or add if missing) + `insert_many`
- `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/cascade_aggregator.py` — `cascade_for_symbol` reuse
- `packages/pocketquant-api/src/pocketquant/api/market_data/handlers/sync/sync_one/handler.py` — how SyncSymbolCommand executes
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/scheduling/scheduler.py` — for pause/resume

**Modify (if needed):**
- `bar_repository.py` — add `delete_in_range(symbol, exchange, interval, start, end) -> int` method nếu chưa có

## Implementation Steps

1. **Pre-flight check:** Verify Phase 1 deployed on VPS (curl `/health` shows fixed git SHA, hoặc ssh + grep code).
2. **Backup:**
   ```bash
   ssh -i pocketquant-config/sandbox/vultr root@207.148.79.60 \
     'mongodump --uri "mongodb://pocketquant:****@localhost:52017/pocketquant?authSource=admin" \
       --collection bars --out /tmp/pq-backup-260508-backfill/'
   ```
3. **Pause cron:** Set `ENABLE_JOBS=false` in VPS .env, restart container OR call `JobScheduler.pause_job("sync_1m")` via admin endpoint.
4. **Add `delete_in_range` to BarRepository** nếu chưa có:
   ```python
   async def delete_in_range(
       self, symbol: str, exchange: str, interval: Interval,
       start: datetime, end: datetime,
   ) -> int:
       result = await self._collection.delete_many({
           "symbol": symbol.upper(),
           "exchange": exchange.upper(),
           "interval": interval.value,
           "datetime": {"$gte": start, "$lt": end},
       })
       return result.deleted_count
   ```
5. **Write `scripts/backfill_regression_window.py`:**
   - Resolve container, get repos + mediator
   - Read tracked_symbols
   - For each (symbol, exchange):
     - Delete in range across 6 intervals
     - Send `SyncSymbolCommand(MINUTE_1, n_bars=500)` (covers 8h+ buffer)
     - Call `cascade_for_symbol(lookback_minutes=500)`
   - Log summary: deleted_count per tf, inserted_count per tf, time taken
6. **Test locally** với 1 symbol nhỏ (BTCUSDT only) trước khi chạy full.
7. **Run on VPS:**
   ```bash
   ssh -i ... 'cd /app && /app/.venv/bin/python scripts/backfill_regression_window.py --start 2026-05-08T07:30:00Z'
   ```
8. **Verify:** Query DB sample bars (1m, 5m, 15m at 09:30 UTC, 12:00 UTC) → must match Binance REST tuyệt đối O/H/L/C, volume sai số < 0.001.
9. **Resume cron:** Set `ENABLE_JOBS=true`, restart container hoặc resume_job.
10. **Smoke test:** Đợi 2 cron cycles (2 phút), verify new bars được tạo đúng (not partial).
11. **Cleanup:** Sau 24h ổn định, xoá `/tmp/pq-backup-260508-backfill/` và `scripts/backfill_regression_window.py` (one-shot, không cần persist).

## Todo List

- [ ] Verify Phase 1 deployed on VPS
- [ ] mongodump backup `bars` collection
- [ ] Pause `sync_1m` cron
- [ ] Add `BarRepository.delete_in_range` if missing
- [ ] Write `scripts/backfill_regression_window.py`
- [ ] Test với BTCUSDT only locally
- [ ] Run full backfill on VPS for all tracked symbols
- [ ] Verify sample bars match Binance API
- [ ] Resume cron + smoke test 2 cycles
- [ ] Cleanup script + backup after 24h validation

## Success Criteria

- [ ] mongodump backup tồn tại trên VPS, có thể restore được
- [ ] Backfill chạy không lỗi cho tất cả tracked symbols
- [ ] Sample 1m bar at 09:30 UTC: O/H/L/C match Binance REST với precision 0.01 USD, volume sai số < 0.001
- [ ] Cascade 15m, 1h bars at 09:30 UTC match Binance REST
- [ ] 0 bar có `tick_count < 50` cho BTCUSDT/ETHUSDT 1m sau backfill
- [ ] Cron resume; 2 cycles tiếp theo tạo bars đúng
- [ ] No data loss: count bars trong window post-backfill ≥ pre-backfill (tính cả delete + insert net)

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Mongodump fail / disk full trên VPS | Check `df -h` trước; backup ~50MB/day data, dư |
| Race với cron sync_1m chưa pause kịp | Verify pause via `JobScheduler.list_jobs` hoặc `db.apscheduler_jobs.find({_id: "sync_1m"})` trước khi delete |
| Delete quá rộng (sai datetime range) | Range guard chặt: `start = 2026-05-08T07:30:00Z` literal; `end = datetime.now(UTC)`; log count trước delete |
| Re-sync trả ít bar hơn delete (data gap) | Compare counts post-resync; nếu thiếu, re-run với larger n_bars |
| Cascade window không cover hết regression range | `lookback_minutes=500` ≈ 8.3h, đủ cho window 7h. Nếu deploy chậm, tăng. |
| WS @aggTrade đang push partial bars vào Redis trong lúc backfill | WS không write Mongo → không ảnh hưởng. Sau backfill, WS overwrite Redis với data mới đúng. |

## Security Considerations

- mongodump cần MongoDB credentials → đọc từ `.env.prod`, không log.
- Không expose backup folder ra public.
- Cleanup backup sau validation.

## Next Steps

→ Phase 03: Harden verify cron (deploy SAU khi backfill ổn định, tránh alert spam)
