---
phase: 4
title: "Re-key backtest_requests drop bt prefix"
status: completed
priority: P2
effort: "6h"
dependencies: []
---

# Phase 4: Re-key backtest_requests drop bt prefix

## Overview

Gỡ coupling `_id ← bt:{sub_id}`. Hiện tại: run-all enqueue `id=f"bt:{sub.id}"` (`backtest_command_service.py:177`) + `replace_one({"_id": id}, upsert)` (`backtest_request_repository.py:34`) = dedup concurrent run-all + bound 1 doc/sub. Single-run đã uuid7 (`:124`).

Target: mọi request `_id` = uuid7. Dedup chuyển sang **partial unique index** `(sub_id)` với `partialFilterExpression {status: "pending"}` — DB-level guarantee "tối đa 1 pending request/sub". Storage profile đổi: done/failed docs tích lũy thay vì bị overwrite → cleanup-on-enqueue (xóa done/failed docs cũ của sub đó khi enqueue mới — chốt over TTL vì không cần thêm index + giữ doc lịch sử gần nhất cho debug tới lần enqueue kế).

Đây là tiền đề Phase 6: sau phase này `backtest_requests` chỉ còn tham chiếu sub qua FIELD `sub_id`, không qua `_id`.

## Requirements

- Functional: (a) run-all concurrent 2 lần → vẫn chỉ 1 pending/sub; (b) re-enqueue khi đã có pending → reset/giữ 1 pending (idempotent như `replace_one` cũ); (c) FE flow không đổi — `job_ids` trả về giờ là uuid strings (FE chỉ echo, không parse — verified brainstorm); (d) `delete_by_subscription`/`delete_by_strategy_code` vẫn đúng (đã filter theo field, không theo `_id` — `:91,:96`).
- Non-functional: OpenAPI schema không đổi (id vẫn `string`); migration idempotent.

## Architecture

Thứ tự TRONG phase (quan trọng — giữ dedup guarantee xuyên suốt):
1. **Index trước:** migration tạo partial unique index `ix_backtest_requests_pending_sub` trên `sub_id`, partial `{status: "pending", sub_id: {"$type": "string"}}` (sub_id null ở single-kind không được đụng index).
2. **Re-key data:** docs có `_id` prefix `bt:` → copy-delete sang `_id = generate_id_str()` (giữ fields). Idempotent: filter `{"_id": {"$regex": "^bt:"}}`.
3. **Đổi enqueue codepath:** `run_all` tạo `id=generate_id_str()`; repo `enqueue` đổi từ `replace_one({"_id": ...})` sang upsert theo `(sub_id, status="pending")` cho kind=subscription: `update_one({"sub_id": ..., "status": "pending"}, {"$set": {...}, "$setOnInsert": {"_id": new_id}}, upsert=True)` + bắt `DuplicateKeyError` race (2 enqueue đua nhau qua upsert window) → retry-read hoặc swallow (cả 2 outcome đều = 1 pending). Single-kind enqueue: insert thuần (id uuid mới mỗi lần — behavior hiện tại qua replace_one với id mới tương đương insert).
4. **Cleanup-on-enqueue:** trước khi upsert pending mới cho sub: `delete_many({"sub_id": sub_id, "status": {"$in": ["done", "failed"]}})`.
5. **`BacktestRequest.id: UUID`** — flip type theo pattern Phase 1 (giờ mọi giá trị đã uuid).

## Related Code Files

Modify:
- `src/pocketquant/backtest/backtest_command_service.py` — `run_all` `:176-186` bỏ `bt:` prefix, dùng `generate_id()`.
- `src/pocketquant/core/infra/persistence/repositories/backtest_request_repository.py` — `enqueue` `:24-35` upsert mới + cleanup; `ensure_indexes` `:121` thêm partial unique index.
- `src/pocketquant/core/domain/backtest/request.py` — `id: UUID`; `to_mongo`/`from_mongo` boundary.
- `src/pocketquant/app/main_extensions.py` + `main.py` — migration `migrate_backtest_request_ids` (index + re-key).
- Worker `backtest_request_worker.py` — `request.id` interpolation vào log/`mark_*` → wrap `str()` nơi cần.

## Implementation Steps (TDD)

1. **Tests first:** extend `tests/backtest_test/test_backtest_request_queue.py` + `test_backtest_request_service.py`: (a) run-all 1 sub → request `_id` là uuid (không prefix `bt:`); (b) run-all 2 lần liên tiếp khi request đầu còn pending → vẫn 1 pending doc cho sub; (c) concurrent enqueue (asyncio.gather 2 enqueue cùng sub) → 1 pending, không exception thoát ra ngoài; (d) enqueue mới sau khi request cũ done → done doc bị cleanup, 1 pending mới; (e) single-kind: 2 lần run → 2 docs riêng (không dedup); (f) migration: seed doc `_id="bt:abc123"` → re-key uuid, fields giữ nguyên; chạy 2 lần idempotent; (g) claim→done flow nguyên vẹn (worker happy path). Chạy → FAIL.
2. Migration (index + re-key) trong `main_extensions.py`; wire lifespan.
3. Đổi `enqueue` + `run_all` + cleanup-on-enqueue.
4. Flip `BacktestRequest.id: UUID`; sửa call sites (`worker`, route DTO nếu có).
5. Tests → PASS; full gates; OpenAPI + route inventory snapshot diff rỗng.

## Success Criteria

- [x] Toàn bộ tests step 1 pass (600 passed, 5 skipped full suite; pyright 0 errors; ruff clean; 7 import contracts kept).
- [x] Partial unique index tồn tại (`ensure_pending_sub_unique_index` — single source, 85/86 conflict handler); concurrent run-all test chứng minh 1 pending/sub (`test_concurrent_run_all_no_duplicate_requests`, `test_concurrent_enqueue_single_pending_no_exception`).
- [x] Không còn literal `bt:` trong `src/` cho request id (chỉ còn migration regex `^bt:` + docstrings; synthetic RAM key `{code}::bt::{sub_id}` giữ nguyên — RAM key, không phải `_id`).
- [x] Deploy verify (run 27413343487, 260612): `11-verify.sh` HEALTHY 20/20; prod Mongo: `^bt:` docs = 0, index `ix_backtest_requests_pending_sub` đúng spec (unique + partial). Concurrent run-all smoke: 2 calls đồng thời → CÙNG 1 uuid, 1 doc duy nhất — dedup PASS.
- [x] Follow-up fix (commit `b73270e`, run 27414355552): smoke đầu bị worker mark `failed` do bug PRE-EXISTING — dispatch `get_config(strategy_code)` cần template-keyed config nhưng rehydrate/reconcile chỉ register theo `sub.id` → mọi run-all fail sau restart. Fix: fallback template-key → sub-key → strategy-class defaults. Re-smoke sau deploy: request `done`, `GET /subscriptions/{id}/backtest` trả metrics đầy đủ.

## Risk Assessment

- **Upsert race → DuplicateKeyError leak ra route 500** — bắt trong repo, map về outcome thành công (1 pending đã tồn tại = mục tiêu đạt). Test (c) lock. ✅ resolved.
- **Partial index không cover docs sub_id=null** — partialFilterExpression thêm `sub_id: {"$type": "string"}`; test (e) lock single-kind không bị dedup. ✅ resolved.
- **Done-docs growth giữa 2 enqueue xa nhau** — chấp nhận (LOW, brainstorm risk table); cleanup-on-enqueue bound về 1 thế hệ docs/sub.
- **`recover_stale_backtests`/`reclaim_stale_running` (`:100`) đụng docs mới** — code-review phát hiện collision THẬT: flip stale running → pending khi đã có pending mới hơn cùng sub → DuplicateKeyError mỗi tick, queue stall vĩnh viễn. Fixed: reclaim per-doc, collision → mark stale doc failed (newer pending supersedes); worker tách reclaim khỏi drain để sweep lỗi không chặn queue. Test `test_reclaim_with_newer_pending_marks_stale_failed` lock.
- **Rollback hazard (code-review M1):** index `ix_backtest_requests_pending_sub` tồn tại sau deploy; code cũ (`replace_one` không bắt DuplicateKeyError) sẽ 500 trên run-all nếu rollback khi có pending doc uuid-keyed. Rollback runbook PHẢI kèm: `db.backtest_requests.dropIndex("ix_backtest_requests_pending_sub")`.
- **Mixed-version window (LOW):** instance code cũ chạy song song sau migration có thể ghi doc `bt:` mới → worker mới claim rồi `UUID()` ValueError → doc cycle 10-phút. Tự hết khi instance cũ dừng; single-process deploy hiện tại không đụng.
