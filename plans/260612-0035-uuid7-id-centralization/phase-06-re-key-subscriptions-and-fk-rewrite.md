---
phase: 6
title: "Re-key subscriptions and FK rewrite"
status: completed
priority: P1
effort: "1.5d"
dependencies: [4, 5]
---

# Phase 6: Re-key subscriptions and FK rewrite

## Overview

Phase risk cao nhất, chạy CUỐI sau khi Phase 4-5 đã gỡ mọi coupling `_id ← sub_id`. Re-key `subscriptions._id` từ sha256 16-hex (`Subscription.deterministic_id`) sang uuid7; dedup chuyển sang unique compound index `(strategy_code, symbol, interval)`; rewrite 4 FK fields; đổi `_SUB_ID_SHAPE` regex guard; xóa `deterministic_id`.

Blast radius còn lại (verified): FK fields `orders.subscription_id`, `positions.subscription_id`, `backtest_runs.subscription_id`, `backtest_requests.sub_id`; RAM instance keys (rehydrate tự nhận id mới sau restart — container restart sẵn khi deploy); `_SUB_ID_SHAPE` (`strategy_reconcile_service.py:43`); FE chỉ echo id từ list response → không sửa FE code, bookmarks cũ break (ACCEPTED từ 30/05, re-confirm 2026-06-12).

## Requirements

- Functional: (a) add_symbol trùng triple → `SubscriptionAlreadyExistsError` → 409 như cũ; (b) 2 add_symbol đua nhau → đúng 1 doc (DB-enforced); (c) orphan-unload hoạt động với UUID keys; (d) orders/positions/backtest data của sub cũ truy cập được qua id mới; (e) synthetic backtest RAM keys (`{code}::bt::{sub_id}`) không bao giờ bị orphan-unload nhầm (giữ invariant hiện có).
- Non-functional: migration map-based, crash-safe, idempotent; OpenAPI snapshot diff rỗng (id schema vẫn `string`).

## Architecture

Thứ tự TRONG migration (1 hàm `migrate_subscription_uuid_ids`, chạy boot-time TRƯỚC `rehydrate_strategies_from_subscriptions`):

1. **Unique compound index trước:** `ix_subscriptions_dedup_triple` trên `(strategy_code, symbol, interval)` unique — tạo TRƯỚC khi codepath mất hash-PK, đóng race window.
2. **Build map crash-safe:** docs có `_id` KHÔNG parse được UUID → ghi `{old_id, new_id: generate_id_str()}` vào collection tạm `_id_migration_map` (upsert theo `old_id` — re-run giữ map cũ, không sinh new_id khác).
3. **Rewrite từ map (idempotent):** với mỗi map entry: (a) copy-delete subscription doc sang `_id = new_id`; (b) `update_many` `orders.subscription_id`, `positions.subscription_id`, `backtest_runs.subscription_id`, `backtest_requests.sub_id`: `{field: old_id} → {field: new_id}`. Mỗi bước re-run an toàn (filter theo old value, sau rewrite không match nữa).
4. **Verify rồi xóa map:** mọi old_id không còn xuất hiện ở `_id` lẫn 4 FK fields → drop `_id_migration_map`. Nếu còn → log error, GIỮ map, boot tiếp (đợt boot sau retry) — không chặn app.

Code changes (cùng push):
- `Subscription.id: UUID` + xóa `deterministic_id` + xóa docstring "deterministic" (`entities.py:34,46-64`); `to_mongo`/`from_mongo` boundary str↔UUID.
- `strategy_command_service.py:131` — `sub_id = generate_id()`; bỏ pre-computed dedup; `SubscriptionAlreadyExistsError` message đổi từ id sang triple (id mới không nói gì về duplicate nào).
- `subscription_repository.py:27-33` — `add()` vẫn bắt `DuplicateKeyError` (giờ từ compound index thay vì `_id`); `ensure_indexes :87` thêm compound unique.
- `_SUB_ID_SHAPE` → UUID regex (`^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}$`); synthetic keys `{code}::bt::{sub_id}` vẫn không match (có `::`).
- `SubscriptionAlreadyExistsError.__init__` (`entities.py:21`) — nhận triple thay vì sub_id.

## Related Code Files

Modify:
- `src/pocketquant/core/domain/subscription/entities.py` — id type, xóa `deterministic_id`, error message.
- `src/pocketquant/core/infra/persistence/repositories/subscription_repository.py` — indexes, docstring PK `:21`.
- `src/pocketquant/engine/strategy_command_service.py` — add_symbol `:131`.
- `src/pocketquant/engine/app_services/strategy_reconcile_service.py` — `_SUB_ID_SHAPE :43` + docstrings `:20,:40-41,:157-165`.
- `src/pocketquant/engine/app_services/strategy_app_service.py` — docstring `:209-210`.
- `src/pocketquant/app/main_extensions.py` + `main.py` — migration, wire TRƯỚC rehydrate.

## Implementation Steps (TDD)

1. **Tests first — reconcile guard (HIGH risk #1):** extend `tests/engine_test/test_strategy_reconcile_service.py` + `test_reconcile_instance_lifecycle.py`: (a) instance key = uuid7 string, sub doc tồn tại → KHÔNG unload; (b) instance key = uuid7, sub doc đã xóa → unload XẢY RA (test này FAIL trước khi đổi regex — chính là lock chống silent no-op); (c) synthetic key `{code}::bt::{uuid}` → không bao giờ unload; (d) key 16-hex cũ (sót RAM sau migration) → không unload nhầm lẫn crash (define: old-shape keys không match regex mới → bị BỎ QUA — chấp nhận, restart xóa RAM).
2. **Tests — dedup:** extend `tests/engine_test/test_add_symbol_handler_pure_declarative.py` + `tests/core_test/infra/persistence/test_subscription_repository.py`: (a) add trùng triple → `SubscriptionAlreadyExistsError`; (b) concurrent add (gather 2) → 1 doc + 1 error; (c) id mới là uuid7.
3. **Tests — migration:** seed: 2 subs 16-hex + orders/positions/backtest_runs/backtest_requests trỏ tới chúng + 1 sub đã uuid → migration → mọi FK đổi đúng theo map, sub uuid cũ untouched, map collection bị xóa; re-run idempotent; crash-resume: map tồn tại + rewrite nửa chừng → re-run hoàn tất đúng.
4. Chạy tests 1-3 → FAIL. Implement: migration + index; code changes (entity, command service, repo, regex).
5. Tests → PASS; full gates; OpenAPI + route inventory diff rỗng.
6. E2E local: add_symbol → start → restart app (rehydrate với uuid id) → reconcile tick sạch → remove_symbol → orphan-unload log xác nhận.

## Success Criteria

- [x] Reconcile tests (a)-(d) pass — đặc biệt (b): unload xảy ra với UUID shape (test_unloads_orphan_instance_when_sub_deleted fail đỏ trước khi đổi regex, pass sau).
- [x] Dedup: trùng triple → SubscriptionAlreadyExistsError → HTTP 400 (DomainError mapping, không phải 409 — verified test_strategy_subscriptions_api.py note); concurrent gather(2) → 1 doc + 1 error (real Mongo). `deterministic_id` = 0 references (grep).
- [x] Migration tests + crash-resume pass (map-only resume, half-FK resume); map collection tự dọn sau verify.
- [x] `mongosh` local E2E: mọi `subscriptions._id` + 4 FK fields match uuid7 regex, 0 bad; map dropped; `ix_subscriptions_dedup_triple` UNIQUE.
- [x] Pre-deploy: VPS counts (1 sub 16-hex, 12 orders, 0 positions, 1 backtest_run, 1 backtest_request), mongodump full DB 66M (`pre-phase6-subscriptions-rekey-260613-0124.archive.gz`). Post-deploy run 27452404345: migration rekeyed=1 (old eef73dffbd77a20b → new 019ebe98-209c-71f2-af3d-981810e2d783), FK rewritten orders=5/backtest_runs=1/backtest_requests=1; `11-verify.sh` HEALTHY 20/20; list → id uuid7; stop/start converge qua reconcile; run-all → 202, cache refresh (last_run_at mới, trades=1).
- [x] Docs re-check: `code-standards.md` (ID table + dedup invariant thay hash-stability), `system-architecture.md` (subscriptions = uuid7, 1 exception duy nhất apscheduler_jobs), `system-relationship-map.md`, `service-and-route-conventions.md` (example code), `project-overview-pdr.md`. Grep "deterministic" trong docs = 0.

## Code Review Outcome (post-implementation)

Reviewer: DONE_WITH_CONCERNS, 0 blocking. Applied trong cùng push: `from None` trên DuplicateKeyError re-raise; `logger.error("subscription_uuid_migration.payload_missing")` khi map entry thiếu payload (unreachable hiện tại nhưng loud-on-corruption). Non-blocking ghi nhận, không sửa:

- `_id_migration_map` tên generic — future migration tái dùng tên này sẽ insert payload lạ vào `subscriptions`. Nếu cần migration map-based khác: dùng tên scoped (vd `_subscription_id_migration_map`).
- Verify step chỉ check old_id residue, không check new-doc existence.
- 2 boots đua migration: không fork id ($setOnInsert), nhưng 1 boot có thể crash DuplicateKeyError → restart resume sạch. Theoretical với single-instance deploy.
- Dedup index case-sensitive trên `symbol` — normalization `.upper()` trong `add_symbol` là load-bearing (đã ghi vào docs/code-standards.md).

## Risk Assessment

- **Quên `_SUB_ID_SHAPE` → orphan-unload silent no-op vĩnh viễn** (HIGH) — test step 1(b) viết TRƯỚC, fail đỏ cho tới khi regex đổi. Checklist item riêng.
- **Migration kill giữa chừng → FK nửa cũ nửa mới** (MED) — map-based rewrite (Architecture 2-4): map persist trước, mọi rewrite idempotent từ map, verify-trước-khi-xóa-map. Test step 3 crash-resume lock.
- **2 add_symbol đua nhau sau khi mất hash-PK** (MED) — compound unique index tạo TRƯỚC codepath change (cùng migration, thứ tự trong hàm); concurrent test lock.
- **RAM keys cũ sau migration nhưng trước restart** — không xảy ra: migration chạy boot-time, RAM trống tại thời điểm đó; rehydrate đọc id mới.
- **FE bookmarks break** — ACCEPTED (user confirm 2x).
