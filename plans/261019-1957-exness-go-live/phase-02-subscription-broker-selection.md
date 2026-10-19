---
phase: 2
title: "Broker per subscription, one Exness adapter per process (B6, B9)"
status: pending
priority: P1
effort: 0.5d
dependencies: []
---

# Phase 02: Broker per subscription, one Exness adapter per process (B6, B9)

## Context
- The live strategy takes its broker from `StrategyConfig.broker` (`core/domain/strategy/value_objects.py:84`, default `"paper"`) through `load_strategy` → `_get_or_create_broker(config.broker, config.contract_spec)` (`engine/strategy/strategy_app_service.py:121`).
- Reconcile builds every live `StrategyConfig` without a broker (`engine/live/strategy_reconcile_app_service.py:167-173`). It loads an instance for every subscription, stopped ones included (`_ensure_instances`, `:138-181`).
- `Subscription` has no broker field (`core/domain/subscription/entities.py:32-73`). Its document mapping is `to_mongo` (`:50-59`) and `from_mongo` (`:61-73`), which already defaults missing fields.
- Create path: `CreateSubscriptionBody` (`app/routes/strategy.py:19-26`) → `create_subscription` (`:56-66`) → `StrategyCommandService.add_symbol` (`engine/strategy/strategy_command_service.py:60-97`). The list path is `StrategyQueryService.list_symbols` (`engine/strategy/strategy_query_service.py:56-68`).
- `StrategyCommandService` is auto-wired (`app/di/services.py:247`). `Settings` is in the container, and `QuoteAppService` already takes it (`engine/market_data/app_services/quote_app_service.py:9,25`). There is one direct construction, the test helper `_cmd_svc` (`tests/engine_test/test_strategy_service.py:38-51`).
- The unique index is on `(strategy_code, symbol, interval)` (`core/infra/persistence/repositories/subscription_repository.py:102-106`). A paper and an `exness` subscription therefore cannot share a triple, and Phase 05 deletes the paper one first.
- B9: the pool key is `(broker_type, contract_spec)` (`strategy_app_service.py:64,465`). Only the paper branch of `BrokerFactory.create` reads `contract_spec` (`core/infra/brokers/broker_factory.py:48-66`); the OKX and Exness branches ignore it (`:68-98`). Prod has only paper subscriptions, because no broker field exists before this phase.
- Dead code: `Settings.default_broker` (`core/config.py:135`) has no reader in `src`, and `BrokerFactory.get_available_types` (`broker_factory.py:103-105`) is called only by `tests/core_test/infra/brokers/exness/test_exness_broker_factory.py:41`.

## Files
- Modify: `src/pocketquant/core/domain/subscription/entities.py`, `src/pocketquant/app/routes/strategy.py`, `src/pocketquant/engine/strategy/strategy_command_service.py`, `src/pocketquant/engine/strategy/strategy_query_service.py`, `src/pocketquant/engine/live/strategy_reconcile_app_service.py`, `src/pocketquant/engine/strategy/strategy_app_service.py`, `src/pocketquant/core/config.py`, `src/pocketquant/core/infra/brokers/broker_factory.py`, `tests/engine_test/test_strategy_service.py`, `tests/core_test/infra/brokers/exness/test_exness_broker_factory.py`, `docs/system-architecture.md` (`:164`, `:179`, `:187`)
- Create: `tests/engine_test/test_subscription_broker_selection.py`

## Steps
1. `Subscription`: add `broker: str = "paper"`. `to_mongo` writes it, and `from_mongo` reads `doc.get("broker", "paper")`, so existing documents need no migration.
2. `CreateSubscriptionBody.broker: Literal["paper", "exness"] = "paper"`, so an unknown value returns 422. The route passes `body.broker` to `add_symbol`.
3. `add_symbol(strategy_id, symbol, interval, broker="paper")`: when `broker == "exness"` and `not self._settings.exness_live_trading`, raise `DomainError("exness broker is disabled: EXNESS_LIVE_TRADING is false", error_code="BROKER_DISABLED")` (400). This blocks an `exness` subscription that reconcile would fail to load every 5 s. Store the broker on the `Subscription` and return it in the response dict. The constructor gains `settings: Settings`; update `_cmd_svc`.
4. `list_symbols`: add `"broker": sub.broker`.
5. Reconcile: `StrategyConfig(..., broker=sub.broker, ...)`.
6. B9: in `_get_or_create_broker`, set `key = (broker_type, contract_spec if broker_type == "paper" else None)` and change the `_broker_pool` annotation to `ContractSpec | None`. Add a one-line comment: only paper prices fills by contract spec, and a venue broker is one account, so one instance with one event stream.
7. **Only if D1 = B:** add an optional `max_exposure_percent: float | None = None` to the body and the `Subscription` (same mapping as step 1), and in reconcile pass `risk=RiskConfig(max_exposure_percent=...)` when it is set. `RiskConfig` validates `0 < x <= 1.0` (`core/domain/risk/value_objects.py:21`). Skip this step for any other D1 option.
8. Delete `Settings.default_broker`, `BrokerFactory.get_available_types` and its assertion at `test_exness_broker_factory.py:41`. Reword `docs/system-architecture.md:179` to "Simulation; the default broker of a subscription."
9. Tests in `test_subscription_broker_selection.py`, plus a new case in `test_strategy_service.py`:
   - a `Subscription` round-trips `broker`, and a document without `broker` reads as `"paper"`;
   - `add_symbol(..., broker="exness")` raises `BROKER_DISABLED` when the flag is false and persists `broker="exness"` when it is true;
   - the route returns 422 for `"broker": "okx"`;
   - reconcile with a stub `StrategyAppService` receives `config.broker == "exness"` for an `exness` subscription;
   - with a stub factory, two `load_strategy` calls with `broker="exness"` and two different `ContractSpec`s call `create` once and `subscribe_order_updates` once; two `paper` loads with different specs still call `create` twice.
10. Docs, `docs/system-architecture.md`: `:164` becomes "Exness account events, one per process (one pooled adapter)". In `:187`, replace "No route sets a broker per subscription..." with "`POST /strategies/{code}/subscriptions` takes `broker` (`paper` default, `exness` only while live trading is on)."

## Validation
- `uv run python -m pytest tests/engine_test tests/app_test/integration/test_strategy_subscriptions_api.py tests/app_test/integration/test_declarative_subscription_state_api.py tests/core_test/infra/brokers -q` exits 0.
- `just test 2>&1 | tail -n 15`: the only failures are the 4 known Windows `time.tzset` tests.
- ruff, pyright (src + touched tests), `lint-imports` (`8 kept, 0 broken`) and the ratchet pass.
- `grep -rn "default_broker\b\|get_available_types" src/pocketquant/core` prints nothing.
- Ship: `git push origin develop`.

## Risk
- Reverting this phase reads every subscription as `paper` (M/H while live). Rollback first stops `exness` subscriptions and flattens their positions.
- OKX instances are now pooled per type (L/L). No OKX subscription exists in prod, and OKX ignores `contract_spec` [V `broker_factory.py:68-83`].
- Deleting `default_broker` leaves `DEFAULT_BROKER=paper` in the prod `.env`. That is harmless, because Settings uses `extra="ignore"` (`docs/deployment.md:76`).

## Rollback
Revert the commit. Documents that gained `broker` keep it, and the old code ignores the field.
