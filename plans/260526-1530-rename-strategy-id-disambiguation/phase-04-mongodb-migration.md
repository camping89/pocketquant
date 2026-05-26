# Phase 04 — MongoDB migration at boot

**Priority:** Required before any user load. Blocks phases 5–8.
**Status:** ⏳ pending, blocked by 3

## Scope

Add an idempotent one-shot migration that runs once on app boot, BEFORE `rehydrate_strategies_from_subscriptions`. Two kinds of operations:

1. **Field renames** — per collection, `$rename` legacy `strategy_id` field to its new name.
2. **Collection rename** — `strategy_subscriptions` → `subscriptions` (the symbol/file rename in Phase 2 keeps `_collection_name = "strategy_subscriptions"` so old reads still work pre-migration; this phase flips it).
3. **Index renames** — drop legacy named indexes, let `ensure_indexes()` recreate the new ones.

## Migration matrix

### Field renames

| Collection (new name) | Rename `strategy_id` → | Drop legacy index |
|---|---|---|
| `subscriptions` (was `strategy_subscriptions`) | `strategy_code` | `ix_strategy_subscriptions_strategy_id` |
| `orders` | `subscription_id` | `ix_orders_strategy_id` |
| `positions` | `subscription_id` | `ix_positions_strategy_id` |
| `backtests` | `strategy_code` | `ix_backtests_strategy_id` + compound variants on `[("strategy_id",1),(metric,-1)]` |
| `optimizations` | `strategy_code` | matching legacy index |
| `backtest_orders` | `strategy_code` *or* `subscription_id` (verify in phase 3) | matching legacy index |
| `backtest_trades` | `strategy_code` *or* `subscription_id` (verify in phase 3) | matching legacy index |

### Collection rename

| From | To | Method |
|---|---|---|
| `strategy_subscriptions` | `subscriptions` | `await db["strategy_subscriptions"].rename("subscriptions")` |

**Ordering inside migration:** rename collection FIRST (so subsequent `$rename` of the field operates on the new collection name). Or equivalently: do field rename via the old collection name, THEN rename the collection. Pick one and document it; either works.

**Pre-check:** if a collection named `subscriptions` already exists, abort with a clear error message. (Defensive — Mongo will throw, but a friendly error is better.)

## Idempotence design

**Collection rename:**
1. Check if `strategy_subscriptions` exists in `db.list_collection_names()`.
2. If yes AND `subscriptions` doesn't exist → rename.
3. If no AND `subscriptions` exists → skip (already migrated).
4. If both exist → abort with explicit error (manual intervention required).

**Field renames (per collection, using NEW collection names):**
1. Check if ANY doc still has the legacy `strategy_id` field (`countDocuments({strategy_id: {$exists: true}})`).
2. If zero — skip; migration already ran.
3. Else: `update_many({strategy_id: {$exists: true}}, {$rename: {"strategy_id": "<new_name>"}})`.
4. Drop legacy indexes if they exist (catch IndexNotFound — safe).
5. Trust `ensure_all_indexes()` (called separately during boot) to recreate the new ones.

**Subscription repo's `_collection_name`:** after Phase 4 ships, update `SubscriptionRepository._collection_name = "subscriptions"`. This is a one-line code change that should land in the SAME commit/PR as the migration so the running app reads/writes the new collection name immediately post-migration. Document this dependency in the commit message.

## File to create

`packages/pocketquant-api/src/pocketquant/api/main_extensions.py` — add `migrate_strategy_id_fields(container)` function. Wire into `lifespan` in `main.py` **before** `rehydrate_strategies_from_subscriptions`.

Order in lifespan:
1. DI container created
2. `ensure_all_indexes()` (existing)
3. **`migrate_strategy_id_fields()` (NEW)**
4. `rehydrate_strategies_from_subscriptions()` (existing — will now read `strategy_code`)
5. `reconcile_orphan_jobs()`
6. `start_background_jobs()`

## Logging & observability

- Log per-collection: `mongo_migration.renamed`, fields={collection, modified_count}
- Log when skipping: `mongo_migration.skipped`, fields={collection, reason: "already migrated"}
- Log totals at end: `mongo_migration.completed`, fields={total_renamed}

## Implementation steps

1. Implement `migrate_strategy_id_fields(container)` with the matrix above. Two helpers inside:
   - `_rename_collection_if_needed(db, old, new)` — idempotent
   - `_rename_field_if_needed(db, collection, old_field, new_field)` — idempotent
2. Wire in `main.py` lifespan, ordering: `ensure_all_indexes` → `migrate_strategy_id_fields` → `rehydrate_strategies_from_subscriptions`.
3. Update `SubscriptionRepository._collection_name = "subscriptions"` in the same commit.
4. Write unit tests:
   - seed `strategy_subscriptions` with `{strategy_id: "hitnrun2", ...}` → after migration → collection `subscriptions` contains doc with `{strategy_code: "hitnrun2"}` and no `strategy_id` key.
   - Run migration twice → second run is a no-op.
   - Pre-existing `subscriptions` collection + present `strategy_subscriptions` → migration raises a clear error.
5. Smoke test on a fresh local Mongo with sample legacy docs.

## Acceptance criteria

- Unit tests pass (3 scenarios above).
- Running migration twice is a no-op (second run logs `skipped` for both collection rename + field renames).
- After boot, `ensure_indexes` creates the new index names. `db.subscriptions.getIndexes()` shows `ix_subscriptions_strategy_code` (or whatever phase 3 named it), no `ix_strategy_subscriptions_*`.
- App starts cleanly and rehydrate succeeds reading from `subscriptions` collection with `strategy_code` field.

## Rollback

If migration breaks: revert deploy. Original `strategy_id` data is preserved on the SECOND collection (post-rename it lives under `strategy_code`/`subscription_id`); a reverse migration is the symmetric `$rename`. Document the reverse command at the top of the migration file as a comment.

## Out of scope

- Data validation / cleanup beyond field renames
- Schema versioning machinery (overkill for this single migration)
