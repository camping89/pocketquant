# Phase 02 — Rename Subscription / Backtest fields → `strategy_code`

**Priority:** Foundation, parallel to phase 1.
**Status:** ⏳ pending

## Scope

Two intertwined renames:

**A) Field rename `strategy_id` → `strategy_code` on:**
- `Subscription` (was `StrategySubscription`) — the field that holds `"hitnrun2"`
- `BacktestResult`
- `OptimizationResult`
- backtest value objects (`order.py`, `trade.py` — if they carry it)

Also rename the `deterministic_id()` first parameter from `strategy_id` → `strategy_code` so the call sites read truthfully.

**B) Symbol rename:**
- Class `StrategySubscription` → `Subscription`
- Class `StrategySubscriptionRepository` → `SubscriptionRepository`
- File `trading/persistence/strategy_subscription_repository.py` → `subscription_repository.py`

(The Mongo collection rename `strategy_subscriptions` → `subscriptions` happens in Phase 4.)

## Files to modify

**Domain:**
- `packages/pocketquant-trading/src/pocketquant/trading/domain/subscription.py` — class rename + field rename + docstring
- `packages/pocketquant-trading/src/pocketquant/trading/domain/__init__.py` — re-export `Subscription` instead of `StrategySubscription`
- `packages/pocketquant-backtest/src/pocketquant/backtest/domain/entities.py`
- `packages/pocketquant-backtest/src/pocketquant/backtest/domain/value_objects/order.py`
- `packages/pocketquant-backtest/src/pocketquant/backtest/domain/value_objects/trade.py`

**Persistence (class + file rename only — query/index changes are Phase 3):**
- Move file: `packages/pocketquant-trading/src/pocketquant/trading/persistence/strategy_subscription_repository.py` → `subscription_repository.py`
- Rename class inside: `StrategySubscriptionRepository` → `SubscriptionRepository`
- Update collection-name constant: keep `_collection_name = "strategy_subscriptions"` (collection rename in Phase 4)
- Update all `StrategySubscription` references in the file → `Subscription`

**Callers passing `strategy_id=` or importing `StrategySubscription[Repository]`:** (~50 grep hits combined across the 2 symbols)
- `trading/handlers/strategy/add_symbol/handler.py`
- `trading/handlers/strategy/delete/handler.py`
- `trading/handlers/strategy/list_symbols/handler.py`
- `trading/handlers/strategy/remove_symbol/route.py` & handler
- `trading/handlers/strategy/get_subscription_backtest/handler.py`
- `trading/handlers/strategy/run_all_backtests/handler.py`
- `api/main_extensions.py` (rehydrate)
- `api/di/*` providers (DI registration of repo class)
- `trading/jobs/backtest_jobs.py`
- `trading/jobs/backtest_strategy_loader.py`
- `backtest/engine/backtest_app_service.py`
- `backtest/engine/result_collector.py`
- `backtest/optimization/grid_optimization_app_service.py`
- `backtest/optimization/models/backtest_config.py`, `optimization_config.py`

## Hash stability (CRITICAL)

The `deterministic_id` formula:

```python
raw = f"{strategy_code}|{symbol.upper()}|{interval_val}"
```

The hash input is the **value** ("hitnrun2"), not the field name. Renaming the parameter does NOT change existing PKs. Mark this in the docstring so a future contributor doesn't "improve" it.

## Implementation steps

1. Update `subscription.py`:
   - Rename class `StrategySubscription` → `Subscription`
   - Rename field `strategy_id: str` → `strategy_code: str`
   - Rename `to_mongo()` dict key `"strategy_id"` → `"strategy_code"`
   - Rename `from_mongo()` lookup
   - Rename `deterministic_id(strategy_id, ...)` → `deterministic_id(strategy_code, ...)`
   - Update class docstring + module docstring (top of file)
2. Update `trading/domain/__init__.py` re-export list.
3. Move + rename `strategy_subscription_repository.py` → `subscription_repository.py`:
   - `git mv` the file (preserves history)
   - Rename class `StrategySubscriptionRepository` → `SubscriptionRepository`
   - Update class docstring
   - Update internal `StrategySubscription` references to `Subscription`
4. Update DI providers in `api/di/` to register `SubscriptionRepository` (single class swap).
5. Update `BacktestResult`, `OptimizationResult` entity fields + serialization (`to_mongo`/`from_mongo` / `to_dict`/`from_dict`).
6. Update all callers — mechanical replace `StrategySubscription` → `Subscription`, `StrategySubscriptionRepository` → `SubscriptionRepository`, kwarg `strategy_id=` → `strategy_code=` where the value is a template code.
7. Run `just types` — green before moving on.

## Acceptance criteria

- `just types` passes for core, trading, backtest packages
- No grep hits for `sub.strategy_id` or `subscription.strategy_id`
- No grep hits for `StrategySubscription\b` or `StrategySubscriptionRepository\b` in source code (test file names may still contain it until phase 7)
- File `subscription_repository.py` exists; `strategy_subscription_repository.py` does not
- Existing tests still **compile** (they may fail at runtime — fixed in phase 7)
- Hash formula docstring explicitly notes the input is the **value**, not the field name

## Out of scope this phase

- Mongo query strings still reference `"strategy_id"` (phase 3)
- Mongo doc data still has `strategy_id` key + collection still called `strategy_subscriptions` (phase 4 migrates both)
- Test file renames (phase 7)
