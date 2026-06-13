# UUID7 Phase 6 — subscriptions re-keyed, dedup chuyển từ hash-PK sang compound index. PLAN HOÀN TẤT.

**Commit:** `2cd9813` | **CI run:** 27452404345 | **Verify:** HEALTHY 20/20 | **Prod migration:** rekeyed=1, FK rewritten orders=5/backtest_runs=1/backtest_requests=1

## What Shipped

Phase cuối, blast radius lớn nhất của plan. `subscriptions._id` từ sha256 16-hex (`deterministic_id`) → uuid7; `deterministic_id` xóa hẳn khỏi codebase (grep = 0).

- Dedup `(strategy_code, symbol, interval)` chuyển từ hash-PK sang unique compound index `ix_subscriptions_dedup_triple` — index tạo TRƯỚC khi codepath mất hash-PK (trong migration, dòng đầu), đóng race window.
- `SubscriptionAlreadyExistsError` nhận triple thay vì id — id random không nói gì về duplicate nào.
- `_SUB_ID_SHAPE` regex (`strategy_reconcile_service.py`): `^[0-9a-f]{16}$` → uuid7 shape. Đây là điểm chết người plan gọi tên từ đầu: quên đổi → orphan-unload silent no-op vĩnh viễn. TDD lock: test "unload XẢY RA với uuid7 key" viết trước, fail đỏ cho tới khi regex đổi.
- Migration `migrate_subscription_uuid_ids` — map-based, khác 5 phases trước vì 4 collections tham chiếu `_id` này: map collection `_id_migration_map` persist `{old_id, new_id, payload}` TRƯỚC khi đụng doc nào; mọi rewrite idempotent từ map; verify-trước-khi-drop-map; residue → giữ map, log error, boot tiếp (không chặn app).
- `Subscription.id: str → UUID`, `str()` tại mọi boundary (reconcile, rehydrate, query service, backtest dispatch).

## The Hard Part — Payload Trong Map, Không Phải Log Line

Các phase trước dùng delete-then-insert với log-before-delete làm safety net: crash giữa 2 ops mất 1 doc, recover bằng tay từ log. Phase 6 không chấp nhận nổi trade-off đó — subscription là user data, và FK rewrite phụ thuộc new_id ổn định qua crash. Giải pháp: nhét luôn payload vào map entry. Crash giữa delete/insert → re-run đọc payload từ map, insert đúng doc với ĐÚNG new_id đã cấp (`$setOnInsert` giữ new_id qua re-run, id không bao giờ fork). Reviewer xác nhận đây là pattern mạnh nhất trong 6 boot-migrations của file, và chỉ ra blind spot: verify step không check new-doc existence — nếu payload thiếu thì mất doc êm ru. Fix cùng push: `logger.error payload_missing` (unreachable hiện tại, nhưng corruption phải loud).

Lesson: khi migration có FK consumers, "crash-safe" nghĩa là new_id + payload đều phải persist trước op đầu tiên — log line chỉ đủ cho collection không ai tham chiếu.

## Verification Chain

- TDD: reconcile guard 4 cases (unload-fires/synthetic-skip/legacy-16hex-skip/live-doc-no-unload) + dedup concurrent (gather 2 → 1 doc + 1 error, real Mongo) + migration 6 tests (2 crash-resume seams: map-only, half-FK). Fail đỏ trước, pass sau. Full 612 passed; ruff/pyright/7 contracts clean.
- E2E local: seed 16-hex sub + 4 FK docs → boot → migration rekeyed=1, FK all rewritten, map dropped → add duplicate triple → 400 SUBSCRIPTION_ALREADY_EXISTS → remove → orphan-unload log với uuid7 key.
- Code review subagent: DONE_WITH_CONCERNS, 0 blocking. Applied: `from None`, `payload_missing` log. Non-blocking ghi vào phase file (map name generic, boot-race theoretical).
- Prod: mongodump full 66M trước deploy; migration log đúng từng FK count dự đoán (orders=5 — 7 docs còn lại là synthetic/template ids, không phải sub FK); smoke stop→start converge qua reconcile, run-all → cache refresh.

## Plan Closed

6/6 phases deployed + HEALTHY. End-state: mọi `_id` ta own là uuid7, exception duy nhất `apscheduler_jobs` (library-owned, rule §12.6). Uniqueness/idempotency sống ở secondary unique indexes, `_id` chỉ còn 1 vai trò: PK. Docs đã AS-IS hóa (5 files, grep "deterministic" = 0). Todo cũ 260530 superseded, archive vào plan dir.
