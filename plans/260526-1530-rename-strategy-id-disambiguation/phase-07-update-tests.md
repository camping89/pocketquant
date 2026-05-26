# Phase 07 — Update backend tests

**Priority:** Test suite must reflect new naming. Blocks verification.
**Status:** ⏳ pending, blocked by 3+5

## Scope

Update ~12 test files to use new field names + new API routes.

## Files (per package)

### pocketquant-backtest
- `tests/domain/test_value_objects_roundtrip.py`
- `tests/engine/test_backtest_app_service_persistence.py`
- `tests/engine/test_hitnrun2_backtest.py`
- `tests/engine/test_paper_broker_limit_orders.py` — Order fields
- `tests/engine/test_paper_broker_order_events.py` — event fields
- `tests/engine/test_result_collector_fifo.py`
- `tests/persistence/test_backtest_repository_slimmed.py` — repo method names
- `tests/persistence/test_order_repository.py` — repo method names + Order fields
- `tests/persistence/test_trade_repository.py`

### pocketquant-core
- `tests/unit/concepts/strategy/test_hitnrun2.py` — Signal field
- `tests/unit/infrastructure/brokers/test_paper_broker_sl_tp_fill.py` — Order field

### pocketquant-trading
- `tests/test_add_symbol_handler_autoload.py` — command field name + request shape; also import `Subscription` (not `StrategySubscription`)
- `tests/test_stale_recovery.py`
- `tests/test_strategy_position_and_trade_handlers.py`
- `tests/test_strategy_subscription_repository.py` — **rename file** → `test_subscription_repository.py`; update method names + Mongo doc shape + class import
- `tests/test_subscription_deterministic_id.py` — assert hash STABILITY (same inputs → same id); update import to `Subscription`

### pocketquant-api integration
- `tests/integration/test_concurrent_run_all.py`
- `tests/integration/test_run_all_backtest_cascade.py`
- `tests/integration/test_strategy_subscriptions_api.py` — URL paths!

## Pattern

For each file:
1. Replace `strategy_id=` kwargs in entity/event/command constructors with the right new name (`subscription_id` or `strategy_code` per phase 1/2 matrix).
2. Replace `.strategy_id` field access on entities/responses.
3. Replace class imports: `StrategySubscription` → `Subscription`, `StrategySubscriptionRepository` → `SubscriptionRepository`.
4. Replace repo method names (`list_by_strategy` → `list_by_strategy_code`, etc.).
5. Integration tests: rewrite URL paths to new shape (POST `/strategies/{code}/subscriptions`, POST `/subscriptions/{id}/start`, etc.).
6. Mongo seed data in fixtures: rename keys + use new collection name `subscriptions`.

## Specific subtleties

- **`test_subscription_deterministic_id.py`** — add an explicit "back-compat" assertion: `deterministic_id("hitnrun2", "BTCUSDT:BINANCE", "1m")` must produce the SAME id as before the rename. This locks in the hash-stability contract from phase 2.
- **Tests that hit Mongo via testcontainers/fakemongo** — the migration script does NOT run automatically. Each test's setup must use new field names directly. Add one dedicated test for the migration script itself (phase 4 deliverable).

## Implementation steps

1. Work through each file methodically.
2. Run per-package tests: `just test-pkg core`, `just test-pkg trading`, `just test-pkg backtest`, `just test-pkg api`.
3. Fix any drift.

## Acceptance criteria

- `just test` exits 0 across all packages
- Integration tests pass against a fresh Mongo (no legacy docs)
- Migration test (phase 4) passes against a seeded-legacy Mongo
- Hash stability test passes (locks the rename contract)

## Out of scope

- New tests for behavior not covered before
- FE tests (none exist for this surface; out of scope per user instruction)
