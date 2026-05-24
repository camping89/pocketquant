---
phase: 5
title: "One-time migration script + deploy"
status: pending
priority: P2
effort: "2h"
dependencies: [4]
---

# Phase 5: One-time migration script + deploy

## Overview

Backfill audit metadata cho bars cũ (chèn trước plan này). Mỗi doc thiếu `updated_at` hoặc `source` sẽ được set: `updated_at ← created_at` (fallback `now` nếu `created_at` cũng thiếu), `source = SOURCE_ONE_TIME_LEGACY`. Idempotent — chạy lại lần nữa là no-op (vì filter `$exists:false`). Deploy qua `docker exec` lên VPS prod, verify bằng Mongo count query.

## Requirements

**Functional:**
- Standalone Python script `scripts/one_time_backfill_bar_audit_fields.py`.
- Đọc `MONGODB_URI` từ env (đã có trong API container).
- Batch update 1000 docs/lần dùng `bulk_write([UpdateOne...])`.
- Filter: docs thiếu `source` (`{source: {$exists: false}}`).
- Set: `updated_at = created_at` (fallback now); `source = "one_time_legacy"`.
- Progress log mỗi 10k docs processed.
- Summary log cuối: tổng docs scanned / docs updated / runtime.
- Idempotent: rerun → 0 docs match filter → no work.

**Non-functional:**
- Không có dependency mới ngoài motor + cấu hình hiện có.
- Có thể chạy interrupted + resumed (filter tự re-include unprocessed docs).
- File pattern theo `scripts/backfill_regression_window.py` đã có (consistency).

## Architecture

### Script structure

```python
# scripts/one_time_backfill_bar_audit_fields.py
"""One-shot: backfill updated_at + source for legacy bars.

Plan: plans/260523-0938-bar-audit-fields/phase-05-one-time-migration-script-deploy.md

Action per doc with no `source` field:
  - $set source = "one_time_legacy"
  - $set updated_at = existing created_at (fallback datetime.now(UTC))

Run inside the prod container:
  docker cp scripts/one_time_backfill_bar_audit_fields.py pocketquant-app:/tmp/
  docker exec pocketquant-app python /tmp/one_time_backfill_bar_audit_fields.py

Idempotent: filter $exists=false → rerun is a no-op when complete.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

from pocketquant.core.common.constants import COLLECTION_BARS
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import SOURCE_ONE_TIME_LEGACY

logger = get_logger("one_time_backfill_bar_audit_fields")

BATCH_SIZE = 1000
LOG_EVERY = 10_000


async def main() -> int:
    uri = os.environ.get("MONGODB_URI")
    db_name = os.environ.get("MONGODB_DB", "pocketquant")
    if not uri:
        logger.error("migration.missing_mongodb_uri")
        return 2

    client = AsyncIOMotorClient(uri)
    collection = client[db_name][COLLECTION_BARS]

    total_matched = await collection.count_documents({"source": {"$exists": False}})
    logger.info("migration.started", total_to_update=total_matched)

    if total_matched == 0:
        logger.info("migration.no_work")
        return 0

    cursor = collection.find(
        {"source": {"$exists": False}},
        {"_id": 1, "created_at": 1},
        no_cursor_timeout=True,
        batch_size=BATCH_SIZE,
    )

    started = datetime.now(UTC)
    ops: list[UpdateOne] = []
    processed = 0
    updated = 0

    try:
        async for doc in cursor:
            ts = doc.get("created_at") or datetime.now(UTC)
            ops.append(
                UpdateOne(
                    {"_id": doc["_id"]},
                    {"$set": {"updated_at": ts, "source": SOURCE_ONE_TIME_LEGACY}},
                )
            )
            processed += 1

            if len(ops) >= BATCH_SIZE:
                result = await collection.bulk_write(ops, ordered=False)
                updated += result.modified_count
                ops = []

            if processed % LOG_EVERY == 0:
                logger.info(
                    "migration.progress",
                    processed=processed, updated=updated,
                    total=total_matched,
                )

        if ops:
            result = await collection.bulk_write(ops, ordered=False)
            updated += result.modified_count
    finally:
        await cursor.close()

    duration = (datetime.now(UTC) - started).total_seconds()
    logger.info(
        "migration.completed",
        processed=processed, updated=updated,
        total=total_matched, duration_sec=round(duration, 2),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

### Deploy steps (manual, post-merge)

```bash
# 1. From local machine
scp -i <key> scripts/one_time_backfill_bar_audit_fields.py root@207.148.79.60:/tmp/

# 2. SSH to VPS
ssh -i <key> root@207.148.79.60

# 3. Identify API container
docker ps --format '{{.Names}}' | grep pocketquant

# 4. Copy + exec
docker cp /tmp/one_time_backfill_bar_audit_fields.py <api_container>:/tmp/
docker exec <api_container> python /tmp/one_time_backfill_bar_audit_fields.py

# 5. Verify — should return 0
docker exec <api_container> python -c "
import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient
async def check():
    c = AsyncIOMotorClient(os.environ['MONGODB_URI'])
    db = c[os.environ.get('MONGODB_DB', 'pocketquant')]
    print(await db.bars.count_documents({'source': {'\$exists': False}}))
asyncio.run(check())
"

# 6. Spot-check source distribution
docker exec <api_container> python -c "
import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient
async def dist():
    c = AsyncIOMotorClient(os.environ['MONGODB_URI'])
    db = c[os.environ.get('MONGODB_DB', 'pocketquant')]
    pipeline = [{'\$group': {'_id': '\$source', 'count': {'\$sum': 1}}}]
    async for d in db.bars.aggregate(pipeline):
        print(d)
asyncio.run(dist())
"
```

Expected output sau migration + 1 cron cycle:
```
{'_id': 'one_time_legacy', 'count': <large>}    # legacy bars
{'_id': 'rest_sync_1m', 'count': <small, growing>}  # new 1m bars
{'_id': 'cascade', 'count': <small, growing>}       # new cascade outputs
```

### Pre-flight checks

- Backup `bars` collection trước khi chạy: `mongodump --uri="$MONGODB_URI" --collection=bars --out /tmp/bars_backup_$(date +%s)`.
- Free disk: bulk_write ổn nhưng cursor `no_cursor_timeout=True` giữ resource — ensure DB không bị OOM trong giờ rush.
- Cron không cần pause: script + sync_1m không conflict (filter `$exists:false` excludes new docs).

## Related Code Files

**Create:**
- `scripts/one_time_backfill_bar_audit_fields.py`

**Reference (for consistency):**
- `scripts/backfill_regression_window.py` (style template)
- `scripts/audit_bar_quality.py` (cursor + logging pattern)

## Implementation Steps

1. Verify `motor.motor_asyncio.AsyncIOMotorClient` import path khớp với codebase hiện tại (grep usage).
2. Write `scripts/one_time_backfill_bar_audit_fields.py` theo skeleton trên.
3. Smoke test local với Mongo dev: chèn 5 docs không có `source`, chạy script, verify 5 docs updated, rerun → 0 updated.
4. Document deploy steps trong PR body + link Phase 5.
5. Sau merge: thực hiện deploy steps (manual). Capture output logs vào plan reports.

## Todo List

- [ ] Verify motor import path
- [ ] Write migration script
- [ ] Local smoke test (5 dummy docs)
- [ ] Idempotency test (rerun → 0 updates)
- [ ] PR includes deploy commands in description
- [ ] Post-merge: mongodump backup
- [ ] Post-merge: scp + docker exec
- [ ] Post-merge: verify count = 0 + source distribution

## Success Criteria

- [ ] Local smoke test: 5 dummy legacy docs → 5 updated, rerun → 0 updated.
- [ ] Script exit code 0.
- [ ] Sau deploy trên prod: `db.bars.countDocuments({source: {$exists: false}})` = 0.
- [ ] Source distribution sau 5 phút có `rest_sync_1m`, `cascade`, `one_time_legacy`.
- [ ] No regression trong cron job history (sync_1m/sync_backfill vẫn complete).

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Script chạy lâu trên DB lớn (1M+ docs) | Batch 1000 + progress log; tolerate 5-10 phút runtime. mongodump backup trước. |
| Cursor timeout giữa chừng | `no_cursor_timeout=True` + bulk_write idempotent filter cho phép resume sau Ctrl-C. |
| Race với sync_1m ghi doc mới đúng lúc script đang chạy | Filter `$exists:false` excludes new docs (Phase 3 đảm bảo writer mới luôn set source). |
| `MONGODB_DB` env name khác trên prod | Default `"pocketquant"`; verify với `docker exec env \| grep MONGO`. |
| pymongo version skew (`bulk_write` signature) | Codebase đã dùng motor 3.x + pymongo 4.x; UpdateOne signature stable. |

## Next Steps

- Sau Phase 5 done + merged: deploy steps thủ công lên VPS.
- Sau verify thành công: cleanup worktree (`git worktree remove ../pocketquant-bar-audit` từ main repo).
- Sau ~1 tuần production: query `db.bars.find({source: "rest_sync_1m", updated_at: {$gt: ISODate(...)}})` để xác nhận audit field giúp diagnose nếu delay tái diễn.
