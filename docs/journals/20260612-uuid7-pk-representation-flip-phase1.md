# 2026-06-12 — Phase 1: Flip entity PK types str → UUID (representation only)

## Việc đã làm

Thực hiện Phase 1 của plan `plans/260612-0035-uuid7-id-centralization/` — flip kiểu dữ liệu cho primary key từ `str` → `UUID` ở tầng entity/aggregate, nhưng **giữ representation ở API DTOs + DB storage là string** (giá trị trong MongoDB đã là UUID v7 strings, không cần data migration).

### Thay đổi code:

1. **Aggregates (Pydantic, coerce on `from_mongo`)**:
   - `OrderAggregate.id: str` → `UUID` (with `field_serializer("id", when_used="json-unless-none")` → str)
   - `PositionAggregate.id: str` → `UUID` (same pattern)

2. **Domain models (dataclasses, explicit conversion at boundaries)**:
   - `Fill.fill_id: str` → `UUID` (write to Mongo: `UUID().hex`, read from Mongo: `UUID(str_value)`)
   - `Order.order_id: str` → `UUID`
   - `Trade.trade_id: str` → `UUID`
   - `OptimizationResult.id: str` → `UUID`

3. **Foreign keys stay `str` (rule §12.6 applies to `_id` only — YAGNI)**:
   - `subscription_id`, `run_id`, `Fill.order_id`, `entry_order_id`, `exit_order_id`, `resulting_trade_id`, `broker_order_id`, `backtest_id` — all remain `str`

4. **API representation unchanged (DTOs coerce back to `str` at route boundary)**:
   - OpenAPI snapshots (6 route families) unchanged — id field stays `str` in JSON
   - Route handlers call `str(aggregate.id)` before DTO construction

### TDD thực hiện:

- **Test-first**: representation-lock tests viết trước flip
- **Test content**: `isinstance(agg.id, UUID)`, `to_mongo(agg)["_id"]` is `str`, round-trip fill/order/trade, legacy `str`-uuid doc read
- **Test files tạo**:
  - `tests/core_test/unit/domain/order/test_order_uuid_id.py`
  - `tests/core_test/unit/domain/position/test_position_uuid_id.py`
  - `tests/core_test/unit/domain/backtest/test_optimization_result_uuid_id.py`
  - `tests/core_test/unit/persistence/trade_test_uuid_id.py`
  - `tests/core_test/unit/persistence/fill_test_uuid_id.py`

### Danger class xử lý:

| Vấn đề | Điểm gặp | Giải pháp |
|--------|----------|----------|
| Dict-key str/UUID mixing | `paper_broker._orders`, `_pending_orders`, `_order_events`; `order_app_service` map; `result_collector._orders_by_id` | All keys forced `str` at write + read; keys(str), values(UUID) |
| structlog JSONRenderer không serialize UUID | Log kwargs trong signal events | Wrap UUID to `str()` trước wrap vào log |
| Fixture handles | Literal "o1"-style PKs không parse | Use `uuid5(NAMESPACE_OID, "handle_name")` → readable + parseable UUIDs |

### Code review (code-reviewer agent):

- ✅ DONE — 2 minor non-blocking comments (UUID() parse input narrowing, pre-existing unused optimization_id param)

### Gates:

- 574 passed / 5 skipped
- ruff clean
- pyright 0 errors
- import-linter 7/7 (incl. "No bson/ObjectId — UUID7 only" contract)

## Quyết định kỹ thuật

- **FK fields stay `str`**: Rule §12.6 từ code-standards "Primary keys are UUIDv7 only" áp dụng cho `_id` field, không áp dụng cho foreign keys. Thêm type conversion ở FK là premature hardening (YAGNI).
- **API DTO representation**: str ở route boundary → baseline snapshots không thay đổi, dễ review + phân tách concern (Domain = UUID, API = str).
- **Mongo to_mongo(): explicit `UUID().hex` + read `UUID(str_val)`**: Rõ ràng hơn relying on implicit coerce; catch domain bugs sớm (invalid UUID string sẽ raise ngay, không silent fail).
- **Fixture UUID from handle**: `uuid5(NAMESPACE_OID, deterministic_name)` → test ID vẫn readable (có thể trace từ handle), nhưng parse được, stable across runs.

## Deploy

- CI run `27387118602` — all jobs success (incl. 10-deploy.sh + 11-verify.sh)
- Single atomic push → 4 commits + 1 revert staging (false positive test fail)

## Deferred (per Phase plan):

- Phase 4: `BacktestRequest.id` flip
- Phase 5: `BacktestResult.id` flip (complex — `save_for_subscription` overrides id=subscription_id)
- Phase 6: `Subscription.id` flip

**Status:** DONE
