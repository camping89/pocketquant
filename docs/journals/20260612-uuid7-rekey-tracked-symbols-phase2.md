# 2026-06-12 — Phase 2: Re-key tracked_symbols._id sang uuid7

## Việc đã làm

Thực hiện Phase 2 của plan `plans/260612-0035-uuid7-id-centralization/` — re-key `tracked_symbols._id` từ composite symbol string (`BTCUSDT:BINANCE`) sang uuid7. Uniqueness của symbol chuyển hẳn sang unique index trên field `symbol`.

### Thay đổi code:

1. **Entity** (`core/domain/tracked_symbol/entities.py`): thêm `id: UUID = Field(default_factory=generate_id)` theo pattern `Bar`; `to_mongo()` ghi `"_id": str(self.id)`; `from_mongo()` parse UUID với fallback `generate_id()` cho legacy doc (catch `ValueError` — khác `Bar` vì legacy `_id` LÀ string không phải UUID, không thể raise).
2. **Repository**: chỉ đổi docstring — mọi filter đã symbol-based từ trước, `upsert` đã dùng `$setOnInsert` cho `_id`, unique index `ix_tracked_symbols_symbol` đã được declare trong `ensure_indexes`. Plan ước lượng nhiều việc hơn thực tế.
3. **Migration** (`app/main_extensions.py` → `migrate_tracked_symbols_uuid_ids`): ensure unique index TRƯỚC (dedup guarantee giữ xuyên suốt), rồi copy-delete từng legacy doc (Mongo không cho update `_id` in-place). Idempotent — doc có `_id` parse được thành UUID bị skip.
4. **Lifespan** (`app/main.py`): migration chạy sau `migrate_subscription_desired_state`, trước `ensure_all_indexes` và `seed_tracked_symbols`.

### Tests (TDD — viết trước, fail trước):

- `tests/core_test/infra/persistence/test_tracked_symbol_repository.py` (6 tests): upsert idempotent + stable `_id`, uuid7 version check, dedup qua DuplicateKeyError, round-trip, exists/update/delete by symbol.
- `tests/app_test/unit/test_tracked_symbols_uuid_migration.py` (6 tests): re-key preserve fields, idempotent, uuid docs untouched, unique index, index-conflict replacement, empty no-op.

## Bài học

1. **Mongo error code cho index conflict**: handler ban đầu chỉ catch code 85 (`IndexOptionsConflict`). Test cho branch này (viết theo recommendation của code-reviewer) phát hiện Mongo 7 thực tế raise **code 86 (`IndexKeySpecsConflict`)** khi index cùng tên khác options. Handler giờ cover cả 85 và 86. Bài học kép: (a) đừng tin error-code từ trí nhớ, (b) "untested branch" finding của reviewer đáng làm ngay — test đó bắt được bug thật.
2. **pymongo trả BSON date naive UTC**: assertion `== datetime(..., tzinfo=UTC)` fail vì pymongo default decode về naive datetime. Test phải so sánh naive.
3. **Crash-window của copy-delete**: delete-then-insert (bắt buộc — insert trước sẽ đụng unique index symbol). Process chết giữa 2 ops mất 1 doc; symbol auto-seed được seeder tái tạo, symbol admin-added thì log full doc trước khi delete để khôi phục từ log.

## Trạng thái

- Full gates xanh: 586 passed, ruff/pyright/import-linter clean, baseline snapshot diff rỗng.
- Code review: DONE, không có finding critical/high; 2 recommendation non-blocking đã apply (per-doc log + index-conflict test).
- Commit `5950b0d` push lên `develop` — CI deploy đang chạy, còn checklist post-deploy (đếm docs VPS, `11-verify.sh`, spot-check `_id` UUID regex qua `mongosh`).
