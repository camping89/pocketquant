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
- The live strategy takes its broker from `StrategyConfig.broker` (`core/domain/strategy/value_objects.py:84`, default `"paper"`) via `load_strategy` → `_get_or_create_broker(config.broker, config.contract_spec)` (`engine/strategy/strategy_app_service.py:121`).
- Reconcile builds every live `StrategyConfig` without a broker (`engine/live/strategy_reconcile_app_service.py:167-173`) and loads stopped subscriptions too (`_ensure_instances`, `:138-181`).
- `Subscription` has no broker field (`core/domain/subscription/entities.py:32-73`; `to_mongo` `:50-59`, `from_mongo` `:61-73`).
- Create path: `CreateSubscriptionBody` (`app/routes/strategy.py:19-26`) → `create_subscription` (`:56-66`) → `StrategyCommandService.add_symbol` (`engine/strategy/strategy_command_service.py:60-97`). List: `StrategyQueryService.list_symbols` (`engine/strategy/strategy_query_service.py:56-68`).
- `StrategyCommandService` is auto-wired (`app/di/services.py:247`); `Settings` is in the container. One direct construction: `_cmd_svc` (`tests/engine_test/test_strategy_service.py:38-51`).
- Unique index on `(strategy_code, symbol, interval)` (`core/infra/persistence/repositories/subscription_repository.py:102-106`): a paper and an `exness` subscription cannot share a triple; Phase 11 deletes the paper one first.
- B9: pool key `(broker_type, contract_spec)` (`strategy_app_service.py:64,465`). Only the paper branch of `BrokerFactory.create` reads `contract_spec` (`core/infra/brokers/broker_factory.py:48-66`).
- Dead code: `Settings.default_broker` (`core/config.py:135`), `BrokerFactory.get_available_types` (`broker_factory.py:103-105`, called only by the test `test_exness_is_not_an_available_type`, `tests/core_test/infra/brokers/exness/test_exness_broker_factory.py:40-41`).
- The pool reuses a broker only while a loaded strategy holds it (`strategy_app_service.py:466-469`); `unload_strategy` never disconnects it (`:169-178`). So deleting the last `exness` subscription leaves its adapter connected, and the next `exness` load would build a second one.
- `Interval(doc["interval"])` in `from_mongo` already raises on an unknown value; reconcile catches a failed tick and logs `reconcile.failed` (`engine/live/strategy_reconcile_app_service.py:86-98`).

## Gates in this phase
None. The `develop` push (Task 2.8) is authorized by the plan.

## Entry gate
Run first. On a miss: edit nothing, spawn no `kongming`, leave the phase pending, and end with:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pq-develop/plans/261019-1957-exness-go-live --from 02 after <UTC time>
```
- `docker ps` exits 0 (start Docker Desktop and retry once after 10 s; still failing → `NOT_YET: Docker Desktop is not running`).
- `git status --porcelain -- src web deploy tests scripts docs` prints nothing (else `NOT_YET: uncommitted code changes`).

## Tasks

### Task 2.1 — `broker` on the subscription
- Goal: a subscription stores its broker; old documents read `paper`; any other stored value fails the load.
- Target files and symbols: `src/pocketquant/core/domain/subscription/entities.py` → `Subscription`, `to_mongo`, `from_mongo`.
- Steps: add `broker: str = "paper"`; `to_mongo` writes it; `from_mongo` reads `doc.get("broker", "paper")` and raises `ValueError(f"unknown broker {broker!r}")` unless it is `paper` or `exness`. A document written straight into Mongo with another value then fails reconcile closed (`reconcile.failed` each tick) instead of loading an unknown broker.
- Success criteria: no migration needed.
- Verify: no verification needed (Task 2.6).

### Task 2.2 — Create and list carry `broker`
- Goal: the API accepts `paper`/`exness` and refuses `exness` while live trading is off.
- Target files and symbols: `app/routes/strategy.py` → `CreateSubscriptionBody`, `create_subscription`; `engine/strategy/strategy_command_service.py` → `__init__`, `add_symbol`; `engine/strategy/strategy_query_service.py` → `list_symbols`; `tests/engine_test/test_strategy_service.py` → `_cmd_svc`.
- Steps:
  1. `CreateSubscriptionBody.broker: Literal["paper", "exness"] = "paper"` (unknown value → 422); pass `body.broker` to `add_symbol`.
  2. `add_symbol(strategy_id, symbol, interval, broker="paper")`: when `broker == "exness"` and `not self._settings.exness_live_trading`, raise `DomainError("exness broker is disabled: EXNESS_LIVE_TRADING is false", error_code="BROKER_DISABLED")` (400). Store `broker` on the `Subscription` and return it in the response dict.
  3. The constructor gains `settings: Settings`; update `_cmd_svc`.
  4. `list_symbols` adds `"broker": sub.broker`.
- Success criteria: create and list round-trip `broker`.
- Verify: no verification needed (Task 2.6).

### Task 2.3 — Reconcile passes the broker
- Goal: an `exness` subscription loads with the `exness` broker.
- Target files and symbols: `engine/live/strategy_reconcile_app_service.py:167-173`.
- Steps: add `broker=sub.broker` to the `StrategyConfig(...)` call.
- Success criteria: one keyword added.
- Verify: no verification needed (Task 2.6).

### Task 2.4 — One venue adapter per broker type
- Goal: two `exness` subscriptions on different instruments share one adapter.
- Target files and symbols: `engine/strategy/strategy_app_service.py` → `_get_or_create_broker`, `_broker_pool` annotation.
- Steps:
  1. `key = (broker_type, contract_spec if broker_type == "paper" else None)`; annotate the pool key as `ContractSpec | None`.
  2. The reuse check becomes one condition: `if broker is not None and (broker_type != "paper" or any(b is broker for b in self._brokers.values())): return broker`. A pooled venue broker is reused even when no strategy holds it.
  3. Replace the comment above it with two lines: only paper prices fills by contract spec and retires with its last holder; a venue broker is one account, so one instance and one event stream per process.
- Success criteria: the key ignores the spec for non-paper brokers; a venue broker is built once per process.
- Verify: no verification needed (Task 2.6).

### Task 2.5 — Delete dead code
- Goal: no unused broker settings remain.
- Target files and symbols: `core/config.py:135` (`default_broker`); `core/infra/brokers/broker_factory.py:103-105` (`get_available_types`); the whole test function `test_exness_is_not_an_available_type` in `tests/core_test/infra/brokers/exness/test_exness_broker_factory.py:40-41` (its `def` line, its body and the blank lines before it).
- Steps: delete all three. Deleting only line 41 would leave a function with no body and break the module.
- Success criteria: no reader left.
- Verify: `grep -rn "default_broker\b\|get_available_types" src/pocketquant tests` prints nothing.

### Task 2.6 — Tests
- Goal: broker selection and pooling are pinned.
- Target files and symbols: create `tests/engine_test/test_subscription_broker_selection.py`; add one case to `tests/engine_test/test_strategy_service.py`.
- Steps — cases:
  1. `Subscription` round-trips `broker`; a document without it reads `"paper"`; a document with `"broker": "okx"` raises `ValueError`.
  2. `add_symbol(..., broker="exness")` raises `BROKER_DISABLED` with the flag false and persists `broker="exness"` with it true.
  3. The route returns 422 for `"broker": "okx"`.
  4. Reconcile with a stub `StrategyAppService` passes `config.broker == "exness"` for an `exness` subscription.
  5. With a stub factory, two `load_strategy` calls with `broker="exness"` and two different `ContractSpec`s call `create` once and `subscribe_order_updates` once; two `paper` loads with different specs call `create` twice.
  6. With a stub factory: load one `exness` strategy, `unload_strategy` it, then load another `exness` strategy; `create` was called once.
- Success criteria: six cases with behaviour names.
- Verify: `uv run python -m pytest tests/engine_test tests/app_test/integration/test_strategy_subscriptions_api.py tests/app_test/integration/test_declarative_subscription_state_api.py tests/core_test/infra/brokers -q` exits 0.

### Task 2.7 — Docs
- Goal: the architecture doc matches.
- Target files and symbols: `docs/system-architecture.md:164`, `:179`, `:187`.
- Steps:
  1. `:164` → "Exness account events, one per process (one pooled adapter)".
  2. `:179` → "Simulation; the default broker of a subscription."
  3. In `:187`, replace "No route sets a broker per subscription..." with "`POST /strategies/{code}/subscriptions` takes `broker` (`paper` default, `exness` only while live trading is on)."
- Success criteria: three lines changed.
- Verify: `grep -c "one pooled adapter" docs/system-architecture.md` prints `1`.

### Task 2.8 — Full suite, gates, push
- Goal: green on `origin/develop`.
- Target files and symbols: whole repo.
- Steps: `just test 2>&1 | tail -n 15`; ruff and pyright on `src` and touched tests; `uv run lint-imports`; `uv run python scripts/code_metrics.py --ratchet`; commit; `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin` (never print the token).
- Success criteria: the only red is the expected Windows set.
- Verify: the pytest summary shows exactly `4 failed` and `4 errors`, and every failing test id is in `test_utc_runtime_guard.py` or `test_cron_trigger_timezone.py`; ruff `All checks passed!`; pyright `0 errors`; lint-imports `Contracts: 8 kept, 0 broken.`; ratchet exits 0; `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.

## Risk
- Reverting this phase reads every subscription as `paper` (M/H while live). Rollback first follows the "Restart while live" runbook in `docs/deployment.md` and flattens.
- A venue adapter stays connected after its last subscription is deleted (L/L): it is the one account stream, so a venue SL close is still recorded.
- OKX instances pool per type (L/L). No OKX subscription exists; OKX ignores `contract_spec` (`broker_factory.py:68-83`).
- `DEFAULT_BROKER=paper` stays in prod `.env`; harmless (`extra="ignore"`, `docs/deployment.md:76`).

## Rollback
Revert the commit. Documents that gained `broker` keep it; old code ignores it. In prod, deploy the revert only through the "Restart while live" runbook (`docs/deployment.md`).

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.
