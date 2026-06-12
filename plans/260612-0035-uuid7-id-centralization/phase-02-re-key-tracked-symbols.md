---
phase: 2
title: "Re-key tracked_symbols"
status: in-progress
priority: P2
effort: "3h"
dependencies: []
---

# Phase 2: Re-key tracked_symbols

## Overview

`tracked_symbols._id` hiện là composite symbol string (`TrackedSymbol.to_mongo`: `"_id": self.symbol` — `core/domain/tracked_symbol/entities.py:29`). Re-key sang uuid7. Uniqueness chuyển hẳn sang unique index trên field `symbol` (entity docstring đã nói "Uniqueness enforced at the DB layer via index on composite symbol" — verify index này là UNIQUE trước, nếu chưa thì tạo unique index trong cùng migration). Không FK nào trỏ tới `tracked_symbols._id` — mọi lookup qua field `symbol` (`exists()`, `update()`, `delete()` filter `{"symbol": ...}` hoặc `{"_id": symbol}` — phải đổi hết sang `{"symbol": ...}`).

## Requirements

- Functional: `exists`/`upsert`/`update`/`delete`/`list_all` behavior y nguyên; seed boot-time (`seed_tracked_symbols`) idempotent như cũ.
- Non-functional: migration idempotent, re-run an toàn; snapshot diff rỗng.

## Architecture

1. Entity thêm `id: UUID = Field(default_factory=generate_id)` theo pattern `Bar`; `to_mongo` ghi `"_id": str(self.id)`; `from_mongo` đọc `UUID(doc["_id"])` (fallback `generate_id()` cho doc cũ chưa migrate — pattern `bar/entities.py:84`).
2. Repository: mọi filter theo symbol đổi sang field `symbol`; `upsert` dùng filter `{"symbol": ...}` + `$setOnInsert {"_id": str(generate_id())}`.
3. Migration boot-time `migrate_tracked_symbols_uuid_ids` trong `app/main_extensions.py`: docs có `_id == symbol` (string không phải uuid) → copy-delete với `_id` mới uuid7 (Mongo không cho update `_id` in-place). Idempotent: filter chỉ match docs mà `_id` không parse được thành UUID.
4. Unique index `symbol` tạo TRONG migration TRƯỚC khi re-key (giữ dedup guarantee xuyên suốt), rồi `ensure_indexes` của repo cũng khai báo nó.

## Related Code Files

Modify:
- `src/pocketquant/core/domain/tracked_symbol/entities.py` — add `id: UUID`; `to_mongo`/`from_mongo`.
- `src/pocketquant/core/infra/persistence/repositories/tracked_symbol_repository.py` — filters `_id` → `symbol` (`exists() :56` đang project `{"_id": 1}` — đổi filter sang `{"symbol": ...}`); `upsert()` `:20-32`; `ensure_indexes()` thêm unique index `symbol`.
- `src/pocketquant/app/main_extensions.py` — thêm `migrate_tracked_symbols_uuid_ids`.
- `src/pocketquant/app/main.py` — gọi migration trong lifespan (sau `migrate_subscription_desired_state`, trước `ensure_all_indexes`).

## Implementation Steps (TDD)

1. **Tests first:** extend `tests/core_test/infra/persistence/` (pattern `test_subscription_repository.py` — mongomock/real Mongo theo conftest hiện có): (a) seed doc shape CŨ (`_id == symbol`) → chạy migration → doc có `_id` uuid, `symbol` giữ nguyên, `created_at`/`seeded_from` giữ nguyên; (b) migration chạy 2 lần → không đổi gì thêm (idempotent); (c) `upsert` 2 lần cùng symbol → 1 doc; (d) 2 symbol khác nhau → 2 docs; (e) insert duplicate symbol trực tiếp → DuplicateKeyError (unique index). Chạy → FAIL.
2. Đổi entity + repository như Architecture.
3. Viết migration; wire vào lifespan.
4. Tests step 1 → PASS; full gates; baseline snapshot diff rỗng.

## Success Criteria

- [x] Migration idempotent test pass (chạy 2 lần).
- [x] Unique index `symbol` tồn tại; dedup test pass.
- [x] `seed_tracked_symbols` boot vẫn idempotent (boot smoke test).
- [x] Full gates xanh; snapshot diff rỗng.
- [ ] Pre-deploy: đếm docs trên VPS; post-deploy `11-verify.sh` HEALTHY; spot-check `mongosh`: mọi `tracked_symbols._id` match UUID regex.

## Risk Assessment

- **Index `symbol` hiện tại có thể chưa UNIQUE** — bước đầu migration: drop index thường (nếu có) rồi tạo unique; nếu prod có duplicate symbol (không thể vì `_id` từng là symbol) thì không xảy ra.
- **Race seed-vs-migration lúc boot** — migration chạy trước `seed_tracked_symbols` trong lifespan (thứ tự tường minh ở `main.py`), single process nên không có process thứ 2.
