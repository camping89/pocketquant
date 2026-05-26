# Phase 03 — Persistence layer: queries, methods, indexes

**Priority:** Bridges domain → DB. Blocks phases 4–5.
**Status:** ⏳ pending, blocked by 1+2

## Scope

Update every Mongo query string, repo method name, and index name to match the new field names.

## Renames

### `subscription_repository.py` (file renamed in Phase 2; class is `SubscriptionRepository`)
- Query keys: `{"strategy_id": x}` → `{"strategy_code": x}`
- Method: `list_by_strategy(strategy_id)` → `list_by_strategy_code(strategy_code)`
- Method: `delete_by_strategy(strategy_id)` → `delete_by_strategy_code(strategy_code)`
- Index: `ix_strategy_subscriptions_strategy_id` → `ix_subscriptions_strategy_code` (reflects new collection name set in Phase 4)
- Leave `_collection_name = "strategy_subscriptions"` UNCHANGED in this phase — Phase 4 flips it to `"subscriptions"` together with the Mongo collection rename so the running code stays consistent with disk state during deploy.

### `order_repository.py`
- Query keys: `{"strategy_id": x}` → `{"subscription_id": x}`
- Method: any `*_by_strategy()` → `*_by_subscription()`
- Index: `ix_orders_strategy_id` → `ix_orders_subscription_id`

### `position_repository.py`
- Query keys: `{"strategy_id": x}` → `{"subscription_id": x}`
- Methods: `get_by_strategy`, `find_open_by_strategy`, `find_closed_by_strategy` → `get_by_subscription`, `find_open_by_subscription`, `find_closed_by_subscription`
- Index: `ix_positions_strategy_id` → `ix_positions_subscription_id`

### `backtest_repository.py`
- Query keys: `{"strategy_id": x}` → `{"strategy_code": x}`
- Methods: `list_by_strategy(strategy_id)` → `list_by_strategy_code(strategy_code)`, `top_by_metric(strategy_id, ...)` → `top_by_metric(strategy_code, ...)`, `delete_by_strategy(strategy_id)` → `delete_by_strategy_code(strategy_code)`
- Compound indexes: `[("strategy_id", 1), ...]` → `[("strategy_code", 1), ...]` — drop/recreate, rename
- Single index: `ix_backtests_strategy_id` → `ix_backtests_strategy_code`
- `upsert_status(subscription_id, strategy_id=...)` → `upsert_status(subscription_id, strategy_code=...)`

### `backtest_order_repository.py`, `backtest_trade_repository.py`
- Whichever rule applies depending on what the field actually held — verify per file at implementation time. Likely: `strategy_id` → `strategy_code` (template-scoped reports) for these.

### `optimization_repository.py`
- Same pattern as backtest repository.

## Callers to update (search & replace)

- All handlers calling renamed repo methods (e.g. `list_symbols/handler.py`, `delete/handler.py`, `run_all_backtests/handler.py`, `get_positions/handler.py`, `get_trades/handler.py`, `get_order/handler.py`, `list_orders/handler.py`).

## Index migration note

Mongo will NOT auto-rename indexes. The phase 4 migration script must:
1. Drop the old index (e.g. `db.orders.dropIndex("ix_orders_strategy_id")`).
2. Re-run `ensure_indexes()` which creates the new ones.

Repos already have idempotent `create_index` — call sites are unchanged.

## Implementation steps

1. Per repo: update all query keys, method signatures, method bodies, index names.
2. Update all handler callers (grep `list_by_strategy\|find_open_by_strategy\|delete_by_strategy` etc.).
3. `just types` — green.
4. `just lint` — green.

## Acceptance criteria

- `just types && just lint` pass
- No grep matches for `"strategy_id":` inside any repo `.py` file's Mongo query (except in migration code from phase 4)
- All renamed method signatures consistent across repo + handler

## Out of scope this phase

- Actually migrating existing Mongo documents (phase 4)
- API route param names (phase 5)
