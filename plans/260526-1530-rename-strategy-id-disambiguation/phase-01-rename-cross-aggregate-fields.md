# Phase 01 — Rename cross-aggregate fields → `subscription_id`

**Priority:** Foundation. Phase 3 (persistence) depends on this.
**Status:** ⏳ pending

## Scope

Rename the `strategy_id` field on Order, Position, Signal, and order/position events — because they actually carry `sub.id`, not a template code.

## Files to modify

- `packages/pocketquant-core/src/pocketquant/core/concepts/strategy/value_objects.py` — `Signal.strategy_id` → `Signal.subscription_id`
- `packages/pocketquant-core/src/pocketquant/core/domain/order/entities.py` — `Order.strategy_id` → `subscription_id` (incl. `__init__`, `to_mongo`, `from_mongo`, all event emissions that pass `strategy_id=self.strategy_id`)
- `packages/pocketquant-core/src/pocketquant/core/domain/order/events.py` — every event class with `strategy_id` field → `subscription_id`
- `packages/pocketquant-core/src/pocketquant/core/domain/position/entities.py` — same pattern as Order
- `packages/pocketquant-core/src/pocketquant/core/domain/position/events.py` — same
- All callers that construct `Order`/`Position`/`Signal` with kw `strategy_id=`:
  - `core/infrastructure/brokers/paper/paper_broker.py`
  - `trading/brokers/okx/okx_broker.py`
  - `trading/brokers/okx/okx_mapper.py`
  - `trading/app_services/order_app_service.py`
  - `trading/app_services/position_app_service.py`
  - `trading/app_services/strategy_app_service.py` (emits Signal)
  - `core/concepts/strategy/services/hitnrun2.py` (strategy emits Signal)
  - `core/concepts/strategy/events.py` (if any event holds it)

## Implementation steps

1. Update `Signal` value object — rename field, update `__post_init__`, `__repr__` if any.
2. Update `Order` entity — rename `strategy_id` field everywhere in the class body, in `to_mongo()` dict key, in `from_mongo()` lookup. Update every internal event emission (`OrderFilledEvent(... strategy_id=self.strategy_id ...)` → `subscription_id=self.subscription_id`).
3. Update `Order` events module — every event dataclass `strategy_id` → `subscription_id`.
4. Same for `Position` entity + events.
5. Update all callers — grep & replace kw arg name; this is mechanical and the typechecker will catch misses.
6. Run `just types` — no errors before moving on.

## Hash stability

The `Order.id` / `Position.id` schemes do **not** include `strategy_id` in their hash inputs (they use timestamps + uuid). Renaming the field is safe — no PK shifts.

## Acceptance criteria

- `just types --pkg core` passes
- `just types --pkg trading` passes
- No grep hits for `\.strategy_id` in Order/Position/Signal class bodies
- Existing repo methods still compile (they break in phase 3, expected)

## Out of scope this phase

- Mongo query keys (phase 3)
- Index renames (phase 3)
- Migration script (phase 4)
- API field names (phase 5)
