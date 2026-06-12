---
phase: 3
title: "Re-key job_history legacy ObjectId"
status: pending
priority: P2
effort: "2h"
dependencies: []
---

# Phase 3: Re-key job_history legacy ObjectId

## Overview

`job_history` hiện mixed: docs mới đã uuid7 (`record_start :39`, `record_skip :94` dùng `generate_id_str()` — `job_history_repository.py`), docs cũ còn Mongo ObjectId. Append-only log, không FK, chỉ phục vụ dashboard stats (24h/7d/30d) — user quyết giữ lịch sử → re-key copy-delete thay vì xóa.

## Requirements

- Functional: dashboard stats trước/sau migration giống nhau (cùng số docs, cùng aggregates); code đường ghi mới không đổi.
- Non-functional: migration idempotent; thời lượng chấp nhận được (đếm docs prod pre-deploy — unresolved Q2 của brainstorm).

## Architecture

Migration boot-time `migrate_job_history_uuid_ids` trong `app/main_extensions.py`: filter docs có `_id` kiểu `ObjectId` (`{"_id": {"$type": "objectId"}}`) → mỗi doc: insert bản copy với `_id = generate_id_str()` (giữ nguyên mọi field khác) → delete doc cũ. Batch theo cursor để không giữ toàn bộ collection trong RAM. Idempotent tự nhiên: sau lần chạy đầu, filter `$type: objectId` không match gì.

Crash giữa chừng: copy-delete per-doc — worst case 1 doc bị copy nhưng chưa delete → lần boot sau doc cũ (ObjectId) vẫn match filter, copy lần nữa → DUPLICATE bản ghi. Mitigation: trước khi insert copy, check tồn tại doc nào cùng `(job_id, started_at)` đã uuid → skip insert, chỉ delete. (Hoặc: ghi `_migrated_from: <old_id>` vào copy và check trước insert — chọn khi implement, cách nào rẻ hơn theo shape thật của docs.)

## Related Code Files

Modify:
- `src/pocketquant/app/main_extensions.py` — thêm `migrate_job_history_uuid_ids`.
- `src/pocketquant/app/main.py` — wire vào lifespan cạnh các migration khác.

KHÔNG đổi: `job_history_repository.py` (đường ghi đã uuid7 sẵn).

## Implementation Steps (TDD)

1. **Tests first:** extend `tests/core_test/infra/persistence/test_job_history_repository.py`: (a) seed mix docs — 2 docs `_id: ObjectId()`, 1 doc `_id` uuid7 → migration → cả 3 docs còn nguyên fields, mọi `_id` parse được UUID, count không đổi; (b) chạy migration lần 2 → no-op, count không đổi; (c) giả lập crash: doc copy đã insert + doc cũ chưa delete → re-run → không duplicate (count đúng). Chạy → FAIL.
2. Viết migration theo Architecture; wire lifespan.
3. Tests → PASS; full gates; snapshot diff rỗng (không đụng API).

## Success Criteria

- [ ] Test mixed-ids + idempotent + crash-resume pass.
- [ ] Dashboard stats endpoint trả số liệu y nguyên (so sánh trước/sau trên local data).
- [ ] Pre-deploy: `mongosh` đếm `{"_id": {"$type": "objectId"}}` trên VPS (ước lượng thời lượng); post-deploy `11-verify.sh` HEALTHY; count check: tổng docs không đổi, ObjectId docs = 0.

## Risk Assessment

- **Collection lớn làm chậm boot** — batch cursor + log progress; nếu prod count quá lớn (biết sau pre-deploy count), cân nhắc cap per-boot batch và để migration hoàn tất qua vài lần boot (filter idempotent cho phép).
- **Duplicate khi crash-resume** — mitigation dedup-check ở Architecture; test (c) lock behavior này.
