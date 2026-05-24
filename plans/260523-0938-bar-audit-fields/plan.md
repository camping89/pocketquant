---
title: "Bar audit fields (created_at / updated_at / source) + diff-aware upsert"
description: "Add updated_at + source to bars collection; convert insert_many to upsert loop; module-level TTLCache for diff-aware writes; one-time backfill for legacy docs."
status: completed
priority: P2
effort: "1-2d"
branch: "feature/bar-audit-fields"
tags: [market-data, persistence, audit, bug-fix]
blockedBy: []
blocks: []
created: "2026-05-23T02:38:00.000Z"
createdBy: "ck:plan"
source: skill
brainstorm: ../../../pocketquant/plans/reports/brainstorm-260523-0914-bar-audit-fields.md
related:
  - plans/260508-2147-binance-sync-in-progress-bar-fix/  # same write-path area, completed; insert_many in-progress-bar fix superseded by diff-aware upsert here
---

# Bar audit fields + diff-aware upsert

**Brainstorm:** [`brainstorm-260523-0914-bar-audit-fields.md`](../../../pocketquant/plans/reports/brainstorm-260523-0914-bar-audit-fields.md)

## Goal

Đưa metadata audit (`created_at`, `updated_at`, `source`) lên bars collection để khi sync delay tái diễn có thể truy ngược timestamp + write path. Đồng thời sửa bug ngầm: `insert_many` (ordered=False) bỏ qua duplicate → bar 1m đang building không bao giờ được refresh; convert sang upsert loop. Tránh churn write từ cascade lặp lại bằng module-level TTLCache + diff-aware `updated_at` (chỉ bump khi OHLCV thay đổi).

## Scope

**Trong scope:**
- Bar entity Python: thêm `updated_at`, `source` (read-only, repo writes only).
- BarRepository: `cachetools.TTLCache` singleton, `upsert_bar(bar, *, source)`, `insert_many(records, *, source)` → upsert loop.
- Wire `source: str` qua: SyncSymbolCommand, sync_jobs (sync_1m/sync_backfill), integrity_jobs.repair_integrity, cascade_aggregator, tracked_symbols backfill handler.
- One-time idempotent migration script cho legacy docs.
- Test coverage: entity, cache hit/miss, diff detection, source propagation.

**Ngoài scope (defer):**
- Prometheus metric cho cache hit/miss (log đủ cho v1).
- Bulk_write optimize cho insert_many (YAGNI; chỉ làm nếu measure thấy chậm).
- `tick_count` change detection (system chưa real-time tick).

## Phases

| Phase | Name | Status | Blocks | Effort |
|-------|------|--------|--------|--------|
| 1 | [Bar entity audit fields](./phase-01-bar-entity-audit-fields.md) | completed | 2 | 1h |
| 2 | [BarRepository diff-aware upsert + TTLCache](./phase-02-barrepository-diff-aware-upsert-ttlcache.md) | completed | 3 | 3h |
| 3 | [Wire source through all callers](./phase-03-wire-source-through-all-callers.md) | completed | 4 | 2h |
| 4 | [Tests (unit + integration)](./phase-04-tests-unit-integration.md) | completed | 5 | 3h |
| 5 | [One-time migration script + deploy](./phase-05-one-time-migration-script-deploy.md) | completed | — | 2h |

## Implementation Notes (post-implementation)

- **Scope deviation**: Plan missed `BulkSyncCommand → SyncSymbolCommand` callsite at `sync_bulk/handler.py`. Added new constant `SOURCE_BULK_SYNC = "bulk_sync_api"` and hardcoded in BulkSyncHandler. Cleanest fix: external HTTP caller doesn't need to know about audit labels; handler labels itself.
- **Test environment**: Existing `Database()` signature mismatch in `test_tracked_symbol_repository.py` (6 errors) is pre-existing tech debt, unrelated to this plan.
- **Phase 5 deploy steps** (manual, post-merge):
  1. Backup: `mongodump --uri="$MONGODB_URL" --collection=bars --out /tmp/bars_backup_$(date +%s)`
  2. Copy: `scp scripts/one_time_backfill_bar_audit_fields.py root@<vps>:/tmp/`
  3. Exec: `docker cp /tmp/one_time_backfill_bar_audit_fields.py <api_container>:/tmp/ && docker exec <api_container> python /tmp/one_time_backfill_bar_audit_fields.py`
  4. Verify: `db.bars.countDocuments({source: {$exists: false}}) == 0`

## Key Decisions (from brainstorm)

1. **3 audit fields**: `created_at` (preserved), `updated_at` (NEW), `source` (NEW). Min viable for "khi nào + đường nào".
2. **Entity read-only**: `to_mongo()` KHÔNG serialize `updated_at`/`source` — repository là single writer cho audit. `from_mongo()` đọc về để admin/debug tools dùng.
3. **Diff-aware `updated_at`**: bump chỉ khi OHLCV thật sự khác. Tránh churn từ cascade cron mỗi phút × 5 tfs lặp lại cùng bar.
4. **TTLCache singleton** trong `BarRepository` (cachetools, maxsize=20_000, ttl=3600s). Skip cả read + write khi cascade re-process cùng value.
5. **`source: str`, KISS** — không Enum, không ContextVar. Module-level constants (`SOURCE_REST_SYNC_1M`, …) cho refactor safety.
6. **`SyncSymbolCommand` required `source`** — tất cả callers trong cùng commit, no external API consumer.
7. **`insert_many` → upsert loop** — bonus fix cho bug bar 1m đang building không update.
8. **One-time migration**: `updated_at ← created_at` (fallback now), `source = "one_time_legacy"`. Deploy lên VPS qua `docker exec`.

## Source Labels

| Caller | Constant | String |
|--------|----------|--------|
| `sync_1m` cron | `SOURCE_REST_SYNC_1M` | `rest_sync_1m` |
| `sync_backfill` cron | `SOURCE_REST_BACKFILL` | `rest_backfill` |
| `repair_integrity` (sync_repair) | `SOURCE_REST_REPAIR` | `rest_repair` |
| `cascade_for_symbol` | `SOURCE_CASCADE` | `cascade` |
| `tracked_symbols/backfill/handler` | `SOURCE_TRACKED_SYMBOL_BACKFILL` | `tracked_symbol_backfill` |
| Migration script | `SOURCE_ONE_TIME_LEGACY` | `one_time_legacy` |

## Success Criteria

1. Mongo `db.bars.findOne({datetime: <missing_bar>}, {created_at:1, updated_at:1, source:1})` cho biết timestamp + path → debug delay được.
2. `updated_at` chỉ thay đổi khi OHLCV diff — verify qua unit test.
3. `source` distribution trên prod sau 1 cron cycle có mặt `rest_sync_1m`, `cascade`, không còn doc thiếu field.
4. Migration script idempotent — rerun safe.
5. Toàn bộ unit + integration test pass.

## Dependencies

**Internal:** No blocking dependencies. Worktree `feature/bar-audit-fields` đã tạo từ `develop`.
**External libs:** Thêm `cachetools>=5.0.0` vào `pocketquant-core/pyproject.toml`.

## Risk Summary

| Risk | Phase | Mitigation |
|------|-------|------------|
| insert_many upsert loop chậm hơn bulk insert | 2 | Measure dev trước; fallback bulk_write nếu sync_1m latency tăng >X% |
| Cache cold-start window vài giây extra reads | 2 | Acceptable; TTL=1h tự warm-up sau ~5 cascade ticks |
| Migration script lâu trên DB lớn | 5 | Batch 1000 + progress log; idempotent → resumable |
| SyncSymbolCommand required `source` breaking change | 3 | Tất cả callers cùng commit; PR atomic |

## Workflow

- Worktree đã active: `C:\w\_me\pocketquant-bar-audit` (branch `feature/bar-audit-fields` từ `develop`).
- Conventional commits per phase: `feat(bar)`, `refactor(repo)`, `test(bar)`, `feat(scripts)`.
- Khi xong: push branch + `gh pr create --base develop`.
- Sau merge: deploy migration script qua `docker exec` (Phase 5).
- Cleanup worktree sau merge.
