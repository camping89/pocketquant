# UUID7 Phase 5 — backtest_runs cache docs re-keyed, slot moves from `_id` to field

**Commit:** `a5bdf63` | **CI run:** 27418600558 | **Verify:** HEALTHY 20/20 | **Prod migration:** rekeyed=1

## What Shipped

`backtest_runs` was the last MIXED collection: 7 single-run docs already uuid7, 1 per-subscription cache doc with `_id == subscription_id` (16-hex). Now mọi `_id` đều uuid7; cache-slot semantics ("đúng 1 cache doc/sub") chuyển sang unique sparse index trên FIELD `subscription_id`.

- `find/upsert/save/delete_by_subscription` + `get_subscription_status(es)` + `find_doc_by_subscription`: filter theo `{subscription_id}` thay vì `{_id}`.
- `_upsert_cache_slot` chung: upsert + `$setOnInsert {_id: uuid7}` — slot `_id` cấp 1 lần, ổn định qua mọi overwrite; retry 3 lần `DuplicateKeyError` cho race window.
- Bỏ override `result.id = sub_id` trong `save_for_subscription` — doc giờ giữ CẢ run uuid của engine lẫn slot key. Side-effect-on-caller bug class chết hẳn, có regression test.
- `BacktestResult.id: str → UUID`; `str()` tại mongo/API boundaries (collector, repo, worker FE response, routes, optimizer FK).
- Boot migration `migrate_backtest_run_cache_ids`: index TRƯỚC, re-key delete-then-insert, idempotent qua `$expr {_id == subscription_id}`.

## The Hard Part — Slot Identity vs Run Identity

Cache doc cũ nhồi 2 vai trò vào `_id`: vừa là PK vừa là FK đến subscription. Gỡ ra mới thấy còn vai trò thứ 3 bị che: `result.id` bị GHI ĐÈ thành sub_id ngay trước serialize — nghĩa là run identity của engine bị vứt đi mỗi lần cache. Phase plan gọi đúng chỗ này từ brainstorm (deviation note: không thể flip `BacktestResult.id` ở Phase 1 vì override này còn sống). Thiết kế mới tách 3 vai trò: `_id` = slot identity (uuid7, stable), `subscription_id` = slot key (FK field), `to_mongo` giữ run uuid trong nội dung doc... nhưng `_upsert_cache_slot` pop `_id` khỏi `$set` — nếu không, `$set _id` conflict với `$setOnInsert _id` và Mongo reject. Chi tiết 1 dòng, dễ quên nhất bài.

Lesson: khi 1 field gánh nhiều vai trò, đếm đủ vai trò TRƯỚC khi tách — vai trò thứ 3 thường chỉ lộ ra ở dòng code override/mutate ngay trước boundary.

## Verification Chain

- TDD: 13 tests mới FAIL trước, PASS sau (9 repo slot semantics + 4 migration); full 617 passed; ruff/pyright/7 contracts clean; OpenAPI + route snapshot diff rỗng.
- Code review (subagent): DONE, 0 blocking. 3 non-blocking ghi vào phase file — đáng nhớ nhất: `$set` thay `replace_one` mất tính "purge stray fields"; doc 16-hex tái xuất sau migration (restore backup cũ) sẽ 500 vì `from_mongo` strict `UUID()`.
- Prod: pre-count 1 cache doc + mongodump backup; post-deploy 0 legacy, 0 non-uuid7 trên 8 docs; migration log `rekeyed=1`; smoke `GET /subscriptions/{id}/backtest` trả full metrics.

## Why This Matters

Phase 4 + 5 xong = `backtest_requests` và `backtest_runs` chỉ còn tham chiếu subscription qua FIELD, không qua `_id`. Phase 6 (re-key `subscriptions`, blast radius lớn nhất: 4 FK fields + RAM keys + `_SUB_ID_SHAPE` regex) giờ là bài rewrite field thuần — không còn collection nào derive `_id` từ sub_id.

## Next

Phase 6: re-key subscriptions + FK rewrite. Điểm chết người đã được plan gọi tên: `_SUB_ID_SHAPE` regex guard trong `strategy_reconcile_service.py` — quên đổi → orphan-unload thành silent no-op vĩnh viễn.
