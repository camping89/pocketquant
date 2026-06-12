---
phase: 5
title: "Re-key backtest_runs cache docs"
status: pending
priority: P2
effort: "5h"
dependencies: []
---

# Phase 5: Re-key backtest_runs cache docs

## Overview

`backtest_runs` đang MIXED: single-run docs `_id` = uuid7 (`backtest_app_service.py:71` `run_id = generate_id_str()`); per-subscription cache docs `_id` = sub_id 16-hex (`backtest_repository.py` — `save_for_subscription :112-127` override `result.id = sub_id`, `find_by_subscription :75` và `upsert_status :97` filter `{"_id": sub_id}`).

Target: mọi `_id` uuid7; cache-slot semantics ("đúng 1 cache doc/sub") chuyển sang field `subscription_id` + partial unique index. Sau phase này `backtest_runs` chỉ tham chiếu sub qua FIELD — tiền đề Phase 6 (FK rewrite chỉ cần update field).

Cuối phase: flip `BacktestResult.id: UUID` (deferred từ Phase 1 — giờ không còn chỗ nào gán 16-hex vào `result.id`).

## Requirements

- Functional: (a) `find_by_subscription` trả đúng cache doc; (b) `save_for_subscription` overwrite cache cũ của sub (vẫn 1 doc/sub); (c) `upsert_status` running/failed flow nguyên; (d) single-run docs không bị đụng; (e) FE poll `/subscriptions/{id}/backtest` trả data như cũ.
- Non-functional: migration idempotent; OpenAPI snapshot diff rỗng.

## Architecture

Thứ tự trong phase:
1. **Index trước:** partial unique index `ix_backtest_runs_subscription_cache` trên `subscription_id`, partial `{subscription_id: {"$type": "string"}}` — single-run docs không có field này (verify: `to_mongo` của `BacktestResult` không ghi `subscription_id`; chỉ `save_for_subscription`/`upsert_status` set nó) → index chỉ ràng cache docs.
2. **Re-key data:** docs có `subscription_id == _id` (cache docs) → copy-delete `_id = generate_id_str()`, giữ nguyên `subscription_id` + mọi field. Idempotent: filter `{"$expr": {"$eq": ["$_id", "$subscription_id"]}}`.
3. **Đổi repo codepath:** `find_by_subscription` filter `{"subscription_id": sub_id}`; `save_for_subscription` + `upsert_status` upsert theo `{"subscription_id": sub_id}` với `$setOnInsert {"_id": generate_id_str()}`; BỎ override `result.id = sub_id` — `result.id` giữ run uuid của engine (nội dung doc giàu hơn: vừa có run id thật vừa có subscription_id slot key). Chú ý: `_assemble_single_response` và FE-facing `run_id` đọc từ `result.id` — sau đổi, cache doc `_id` ≠ doc cũ nhưng FE không dùng `_id` của cache doc (poll qua sub endpoint) — verify khi viết test (e).
4. **Flip `BacktestResult.id: UUID`** + construction site `backtest_app_service.py:71` → `generate_id()`; `result_collector.py:364-365` nhận `run_id` — đổi type dây chuyền hoặc convert tại boundary; `OptimizationResult` đã flip Phase 1.

## Related Code Files

Modify:
- `src/pocketquant/core/infra/persistence/repositories/backtest_repository.py` — `find_by_subscription :72`, `upsert_status :80`, `save_for_subscription :112`, `ensure_indexes :247` (+partial unique index), `delete_by_subscription`-tương-đương nếu có filter `_id=sub_id` (grep thêm).
- `src/pocketquant/core/domain/backtest/entities.py` — `BacktestResult.id: UUID`; `to_mongo :45` `str()`; `from_mongo :62` `UUID()`.
- `src/pocketquant/backtest/engine/backtest_app_service.py:71` — `generate_id()`.
- `src/pocketquant/backtest/engine/result_collector.py` — `run_id` param type + `:364` finalize.
- `src/pocketquant/backtest/workers/backtest_dispatch.py:212` — caller `save_for_subscription` (không đổi signature, chỉ confirm).
- `src/pocketquant/backtest/workers/backtest_request_worker.py` — `result.id` interpolation (`"run_id": result.id :155`) → `str()`.
- `src/pocketquant/app/main_extensions.py` + `main.py` — migration `migrate_backtest_run_cache_ids`.

## Implementation Steps (TDD)

1. **Tests first:** extend `tests/core_test/infra/persistence/backtest/`: (a) `save_for_subscription` 2 lần cùng sub → 1 cache doc, content = lần 2, `_id` uuid và KHÔNG đổi giữa 2 lần save (slot giữ identity) hoặc đổi — CHỐT semantics: dùng `$setOnInsert` nên `_id` giữ nguyên — assert giữ nguyên; (b) `find_by_subscription` sau save → đúng doc; (c) `upsert_status` rồi `save_for_subscription` → vẫn 1 doc; (d) single-run save + cache save cùng strategy → 2 docs độc lập, single-run không có `subscription_id`; (e) migration: seed cache doc shape cũ (`_id == subscription_id == "abc123def4567890"`) + 1 single-run doc uuid → migration chỉ re-key cache doc; chạy 2 lần idempotent; (f) `BacktestResult` round-trip `to_mongo`/`from_mongo` với `id: UUID`. Chạy → FAIL.
2. Migration (index + re-key); wire lifespan.
3. Đổi 3 repo methods; bỏ `result.id = sub_id` override.
4. Flip `BacktestResult.id: UUID` + construction/consumption sites.
5. Tests → PASS; full gates; snapshot diff rỗng; backtest E2E local: run-all → poll sub backtest endpoint → kết quả hiển thị.

## Success Criteria

- [ ] Tests step 1 pass; cache-slot semantics giữ (1 doc/sub, DB-enforced).
- [ ] Migration idempotent; single-run docs untouched (count + spot-check).
- [ ] Không còn chỗ nào gán non-uuid vào `BacktestResult.id` (grep `result.id =`).
- [ ] Pre-deploy: đếm cache docs (`$expr _id==subscription_id`) trên VPS; post-deploy `11-verify.sh` HEALTHY; FE backtest overlay smoke OK.

## Risk Assessment

- **Quên 1 callsite filter `{"_id": sub_id}`** — grep toàn repo `find_one({"_id"` + `update_one({"_id"` trong backtest repo + dispatch trước khi xong; test (b)/(c) lock 2 đường chính.
- **Old cache doc + new cache doc cùng tồn tại sau crash giữa copy-delete** — unique index trên `subscription_id` (tạo TRƯỚC re-key) làm insert bản copy thứ 2 fail → re-run migration phải dedup-check trước insert (pattern Phase 3 crash-resume); test idempotent (e) phải cover seed "copy đã insert, doc cũ chưa xóa".
- **`upsert_status` chạy khi chưa có cache doc → tạo doc mới thiếu fields của full result** — behavior hiện tại đã vậy (lightweight status doc); không đổi semantics, chỉ đổi key. Test (c) lock.
