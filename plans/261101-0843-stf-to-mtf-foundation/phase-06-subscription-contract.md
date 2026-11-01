---
phase: 6
title: "Subscription contract: intervals, parameters, edit, defaults, reload"
status: pending
priority: P1
effort: 1.5d
dependencies: [5]
---

# Phase 06: Subscription contract: intervals, parameters, edit, defaults, reload

## Goal

A subscription stores an ordered `intervals` list (lowest = entry), strategy `parameters` validated by the strategy class, and a unique scalar `intervals_key`; it can be edited only while stopped and flat; strategies declare `DEFAULTS` that the api serves; and the reconcile loop reloads an edited, non-running instance (D1).

## Context

- C3: `intervals` replaces `interval`; uniqueness on `(strategy_code, symbol, intervals)`; each higher interval is a multiple of the entry interval; edit only while stopped. Verdicts (plan.md): Mongo stores `intervals_key` (comma-joined) written in `to_mongo` only, never an entity field; unique index `ix_subscriptions_dedup_intervals` on `(strategy_code, symbol, intervals_key)`, because a unique multikey index on the list would make `["15m","1h"]` and `["15m","4h"]` collide. One function `check_strategy_inputs(code, intervals, parameters)` beside the registry, used by create and edit here and by the backtest run in Phase 08; unsorted or duplicate lists are 422, never sorted. Defaults live on `IStrategyService.DEFAULTS: ClassVar[dict]`.
- D1: the reconcile loop may reload the config of a non-running instance whose `(intervals, parameters)` changed; its period, lease gating and load/unload ownership stay. The `manual_action` field and its reconcile step are not added here (Phase 11).
- No index-drop code and no legacy-document fallback go into `src`: Phase 15 migrates prod documents and drops `ix_subscriptions_dedup_triple` before D-2. Test databases are fresh containers (`tests/conftest.py:69-72`).
- Current code: `Subscription` `src/pocketquant/core/domain/subscription/entities.py:29-70` (`interval: Interval` `:34`, `to_mongo` `:40-50`, `from_mongo` `:52-70`), `SubscriptionAlreadyExistsError` `:19-25`. `SubscriptionRepository.add` `core/infra/persistence/repositories/subscription_repository.py:19-27`, `ensure_indexes` `:71-84` (old index `:79-83`); no update method exists. `StrategyConfig` `core/domain/strategy/value_objects.py:26-35` (`interval: str` `:30`). `IStrategyService` `core/domain/strategy/strategy_service_interface.py:16`. Registry `core/domain/strategy/services/__init__.py` (empty after Phase 05).
- Readers of the single interval: `engine/strategy/strategy_app_service.py:235-236,256,499`; `engine/backtest/backtest_execution_service.py:114` (builds `StrategyConfig` from `BacktestConfig.interval`, which stays until Phase 08); `engine/live/strategy_reconcile_app_service.py:144-155` (passes no `parameters`); `engine/strategy/strategy_command_service.py:48-89` (`add_symbol`, registry check `:58-59`); `engine/strategy/strategy_query_service.py:24-31` (`get_one`), `:35-57` (`list_symbols`, `interval` `:49`); `app/routes/strategy.py:13-16` (`CreateSubscriptionBody`), `:46-52` (create route).
- Reconcile skips any loaded instance (`strategy_reconcile_app_service.py:119-120`); `unload_strategy` drops paper positions (`engine/strategy/strategy_app_service.py:306-328`), so the edit must refuse a subscription with an open position or a pending order. `PositionRepository.find_open_by_subscription` (`core/infra/persistence/repositories/position_repository.py:25-32`); `OrderRepository.find_pending` (`order_repository.py:20-25`, statuses pending/submitted/partially_filled). Both repos are provided in DI (`app/di/infrastructure.py:70-71`); `StrategyCommandService` is auto-wired (`app/di/services.py:213`).
- Errors render as `{"error": {"code": ..., "message": ...}}` (`core/common/exceptions.py:37`). <!-- Red team 2026-11-01: #9 --> Only `AppError` and `ValueError` map to 4xx; any other exception, `TypeError` included, becomes 500 `INTERNAL_ERROR` (`:43-67`). A parameter of the wrong type (`{"min_bars": "3"}`) must therefore be caught by `check_strategy_inputs` as 422, and a float or bool where an int is due must not reach the trader, where every bar would log `strategy_on_bar_error`. `INTERVAL_SECONDS` (str keys, includes `1w`) is `core/common/constants.py:42-50`. With today's interval set every ascending pair is already a multiple; the multiple check still guards the contract, and its test patches `INTERVAL_SECONDS`.
- Rubric `scripts/rubric/static_audit.py:27,39-51` parses `_DEFAULTS` by AST; it reads `cls.DEFAULTS` instead and drops `_find_defaults` and `_literal` (only caller).
- `tests/app_test/integration/test_admin_token_guard.py:46` asserts 17 mutation routes; the new PATCH makes 18.
- `docs/code-standards.md:93,95` name the `(strategy_code, symbol, interval)` binding and the old index.
- Web is not touched here. The create dialog still posts `interval` and will get 422 until Phase 13; nothing deploys before Phase 15.

## Entry gate

Run from `D:/w/_me/algotrading/pocketquant`:

1. `git fetch -q origin && echo "dirty=$(git status --porcelain -- src web deploy tests scripts docs .github | wc -l | tr -d ' ') synced=$(test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo yes || echo no)"` prints `dirty=0 synced=yes`. On a resume, `dirty` may count only files from this phase's Files list, and `synced=no` passes only when `git rev-list --count HEAD..origin/develop` prints `0`.
2. `tail -1 plans/261101-0843-stf-to-mtf-foundation/reports/phase-05-delete-stf-code.md` prints `Result: PASS`.
3. `uv run python -c "from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY; print(len(STRATEGY_REGISTRY))"` prints `0`.
4. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok`.

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 06 after <UTC time>
```

## Files

- Modify src: `core/domain/strategy/value_objects.py`, `core/domain/strategy/strategy_service_interface.py`, `core/domain/strategy/services/__init__.py`, `core/domain/subscription/entities.py`, `core/infra/persistence/repositories/subscription_repository.py`, `engine/strategy/strategy_app_service.py` (the three readers only), `engine/backtest/backtest_execution_service.py` (`:114` only), `engine/live/strategy_reconcile_app_service.py`, `engine/strategy/strategy_command_service.py`, `engine/strategy/strategy_query_service.py`, `app/routes/strategy.py` (all under `src/pocketquant/`); `scripts/rubric/static_audit.py`; `docs/code-standards.md`.
- Create test: `tests/core_test/unit/domain/strategy/test_check_strategy_inputs.py`.
- Modify tests: `tests/strategy_doubles.py`; every `StrategyConfig(` and `Subscription(` site (`git grep -n -E "StrategyConfig\(|Subscription\(" -- tests`); `tests/core_test/unit/domain/subscription/test_subscription_desired_actual_state.py` (including the raw-doc test at `:42-52`); `tests/core_test/infra/persistence/test_subscription_repository.py`; `tests/engine_test/test_strategy_service.py` (including the hand-built `StrategyCommandService(...)` at `:158-162` and every `add_symbol(` call, `:140,165,169,182,197`); <!-- Red team 2026-11-01: #9 --> `tests/engine_test/test_strategy_reconcile_service.py`; `tests/app_test/integration/test_strategy_subscriptions_api.py`; `tests/app_test/integration/test_admin_token_guard.py`; `tests/scripts/rubric/test_static_audit.py`; test files that write raw `subscriptions` documents.

## Tasks

### Task 06.1 — Domain shape and one validation

**Goal:** the domain carries `intervals` and `parameters`, and one function validates code, intervals and parameters.

**Target files and symbols:** `StrategyConfig`, `IStrategyService.DEFAULTS`, `check_strategy_inputs` (in `core/domain/strategy/services/__init__.py`), `Subscription`, `SubscriptionAlreadyExistsError`, `ScriptedStrategy` (`tests/strategy_doubles.py`).

**Steps:**
1. Tests first, new `tests/core_test/unit/domain/strategy/test_check_strategy_inputs.py` with the `probe_registry` fixture: `test_an_unknown_code_is_not_found` (`NotFoundError`); `test_an_empty_list_is_invalid`, `test_an_unsorted_list_is_invalid` (`["1h","15m"]`), `test_a_duplicate_interval_is_invalid` (`["15m","15m"]`), `test_an_unknown_interval_is_invalid` (`["15m","2h"]`), `test_a_higher_interval_must_be_a_multiple_of_the_entry` (`monkeypatch.setitem(INTERVAL_SECONDS, "1h", 3500)`, then `["15m","1h"]`): each `DomainError` with `error_code == "INVALID_INTERVALS"` and `status_code == 422`; `test_an_unknown_parameter_is_invalid` (`{"x": 1}`) and `test_a_value_the_strategy_refuses_is_invalid` (`{"min_bars": -1}`): `INVALID_PARAMETERS`, 422; `test_valid_inputs_return_the_class` (`["15m","1h","4h"]`, `{"min_bars": 3}` returns `ScriptedStrategy`). <!-- Red team 2026-11-01: #9 --> Type tests: `test_a_value_of_the_wrong_type_is_invalid`, parametrized over `{"min_bars": "3"}`, `{"min_bars": True}` and `{"min_bars": 2.5}`: each `INVALID_PARAMETERS`, 422, and never `TypeError`; `test_a_float_default_takes_an_int_but_not_a_bool` (`monkeypatch.setattr(ScriptedStrategy, "DEFAULTS", {"min_bars": 0, "ratio": 1.0})`: `{"ratio": 2}` returns the class, `{"ratio": True}` is `INVALID_PARAMETERS`). In `tests/core_test/unit/domain/subscription/test_subscription_desired_actual_state.py`, build subscriptions with `intervals=(Interval.MINUTE_15, Interval.HOUR_1)`; rewrite the raw doc of `test_from_mongo_legacy_doc_without_keys_defaults_stopped` (`:42-52`) to carry `"intervals": ["5m"]` and `"parameters": {}` instead of `"interval"`, rename it `test_from_mongo_doc_without_state_keys_defaults_stopped` and keep its two state assertions (`from_mongo` has no interval fallback by design); add `test_to_mongo_writes_the_joined_intervals_key` (`intervals == ["15m","1h"]`, `intervals_key == "15m,1h"`, `parameters == {}`) and make the round-trip tests carry `parameters={"min_bars": 2}`; rename `test_already_exists_error_carries_code_and_triple` to `test_already_exists_error_carries_code_symbol_and_intervals`. Run `uv run python -m pytest tests/core_test/unit/domain -q 2>&1 | tail -1`; expected red (`ImportError` / `TypeError`).
2. `StrategyConfig.interval: str` becomes `intervals: list[str]` (entry = `intervals[0]`). `IStrategyService` gains `DEFAULTS: ClassVar[dict] = {}`.
3. `check_strategy_inputs(strategy_code: str, intervals: list[str], parameters: dict) -> type[IStrategyService]`: `NotFoundError(f"Strategy template '{strategy_code}' not found in registry.")` for an unknown code; `DomainError(..., error_code="INVALID_INTERVALS", status_code=422)` when the list is empty, has a value not in `INTERVAL_SECONDS`, is not strictly ascending by seconds, or has a higher interval whose seconds are not a multiple of the entry's; `INVALID_PARAMETERS` (422) for keys not in `cls.DEFAULTS`; for a value whose type does not match its default's type (a `bool` default takes only `bool`; an `int` default takes `int` but not `bool`; a `float` default takes `int` or `float` but not `bool`; a `str` default takes `str`; a `list` default takes `list`), with a `#` comment that a wrong type would otherwise reach the trader or surface as a 500; or when `cls(StrategyConfig(id="check", name=strategy_code, symbol="CHECK", intervals=list(intervals), parameters=dict(parameters)))` raises `ValueError` or `TypeError`. Allowed values of a `str` parameter (an enum such as `entry_type`) stay checked by the strategy constructor's `ValueError`. <!-- Red team 2026-11-01: #9 --> A `#` comment says why it never sorts: an unsorted list is a client error, and silently sorting would change which interval is the entry.
4. `Subscription`: `interval` becomes `intervals: tuple[Interval, ...]`; add `parameters: dict = field(default_factory=dict)` last; `to_mongo` writes `"intervals": [i.value for i in self.intervals]`, `"intervals_key": ",".join(...)` and `"parameters": dict(self.parameters)`; `from_mongo` reads `doc["intervals"]` and `doc["parameters"]` (no fallback); the class comment says uniqueness is the index on the joined key. `SubscriptionAlreadyExistsError(strategy_code, symbol, intervals_key)`. Reword the comments that say "triple" (`entities.py:17-18,28`, `subscription_repository.py:17-18,77-78`) to name the code, symbol and intervals key.
5. `ScriptedStrategy` gains `DEFAULTS: ClassVar[dict] = {"min_bars": 0}` and raises `ValueError` when `min_bars < 0`.

**Success criteria:** the domain tests pass.

**Verify:** `uv run python -m pytest tests/core_test/unit/domain -q 2>&1 | tail -1` contains `passed` and not `failed` or `error`.

### Task 06.2 — Repository key, index and config update

**Goal:** Mongo enforces one subscription per `(strategy_code, symbol, intervals_key)`, and a stopped subscription's config can be replaced.

**Target files and symbols:** `SubscriptionRepository.add`, `ensure_indexes`, new `update_config(sub: Subscription) -> int`; `tests/core_test/infra/persistence/test_subscription_repository.py` (`:57-104`).

**Steps:**
1. Tests first: update the round-trip and duplicate tests to `intervals`; rename `test_dedup_triple_unique_index_exists` (`:99`) to `test_dedup_intervals_unique_index_exists` asserting name `ix_subscriptions_dedup_intervals`, keys `[("strategy_code", 1), ("symbol", 1), ("intervals_key", 1)]`, `unique`; add `test_two_interval_sets_sharing_the_entry_interval_coexist` (`["15m","1h"]` and `["15m","4h"]` both add), `test_update_config_changes_only_a_stopped_subscription` (stopped: returns 1 and `get` shows the new intervals and parameters; `desired_state="running"`: returns 0 and nothing changes) and `test_update_config_onto_an_existing_set_conflicts` (`SubscriptionAlreadyExistsError`). Run the file; expected red.
2. `add` maps `DuplicateKeyError` to `SubscriptionAlreadyExistsError(sub.strategy_code, sub.symbol, doc["intervals_key"])` where `doc = sub.to_mongo()`.
3. `ensure_indexes`: the unique index becomes `[("strategy_code", 1), ("symbol", 1), ("intervals_key", 1)]`, name `ix_subscriptions_dedup_intervals`; the comment says the key is a scalar because a unique index on the list would be multikey and reject two lists that share one interval.
4. `update_config(sub)`: `update_one({"_id": str(sub.id), "desired_state": "stopped", "actual_state": "stopped"}, {"$set": {"intervals": ..., "intervals_key": ..., "parameters": ...}})` from `sub.to_mongo()`, returning `matched_count`; `DuplicateKeyError` maps as in `add`.

**Success criteria:** the repository tests pass.

**Verify:** `uv run python -m pytest tests/core_test/infra/persistence/test_subscription_repository.py -q 2>&1 | tail -1` contains `passed` and not `failed` or `error`.

### Task 06.3 — Engine and api: create, edit, defaults, list

**Goal:** create and edit take intervals and parameters, the template endpoint serves defaults, and every engine reader uses the entry interval.

**Target files and symbols:** `StrategyAppService` (`:235-236,256,499`), `BacktestExecutionService.run` (`:114`), `StrategyReconcileAppService._ensure_instances` (`:144-155`), `StrategyCommandService.__init__`, `add_symbol`, new `edit`, `StrategyQueryService.get_one`, `list_symbols`, `app/routes/strategy.py` (`CreateSubscriptionBody`, new `EditSubscriptionBody`, new `PATCH /subscriptions/{sub_id}`).

**Steps:**
1. Tests first. `tests/engine_test/test_strategy_service.py` (helper `_cmd_svc` passes `position_repository` and `order_repository` mocks; calls pass `["1h"]`): `test_add_symbol_rejects_an_unsorted_interval_list`, `test_add_symbol_rejects_an_unknown_parameter`, `test_add_symbol_returns_intervals_and_parameters`, `test_edit_404_when_the_subscription_is_missing`, `test_edit_refuses_a_running_subscription` (`SUBSCRIPTION_RUNNING`, 409), `test_edit_refuses_an_open_position` and `test_edit_refuses_a_pending_order` (`SUBSCRIPTION_HAS_EXPOSURE`, 409), `test_edit_writes_the_new_config`, `test_get_one_serves_the_default_parameters` (`parameters == {"min_bars": 0}`). <!-- Red team 2026-11-01: #9 --> In the same file, the hand-built service of `test_add_symbol_accepts_exness_only_while_the_trader_flag_is_on` (`:158-162`) also passes `position_repository=MagicMock()` and `order_repository=MagicMock()`, and every existing `add_symbol(` call (`:140,165,169,182,197`) passes a list and `{}`, for example `add_symbol("probe", "XAUUSD:EXNESS", ["5m"], {}, broker="exness")`. `tests/app_test/integration/test_strategy_subscriptions_api.py`: `_STRATEGY_CODE = "probe"` with the fixture, a tracked `BTCUSDT:BINANCE` upserted through `TrackedSymbolRepository` from the dishka container; `test_two_interval_sets_sharing_the_entry_interval_both_create` (201, 201, then 409 `SUBSCRIPTION_ALREADY_EXISTS`), `test_create_rejects_an_unsorted_interval_list` (422, `error.code == "INVALID_INTERVALS"`), `test_create_rejects_a_parameter_of_the_wrong_type` (`{"min_bars": "3"}`: 422, `error.code == "INVALID_PARAMETERS"`, never 500), `test_edit_changes_a_stopped_subscription` (PATCH 200 with the new `intervals`), `test_the_template_serves_its_default_parameters` (`GET /api/v1/strategies/probe`); the unknown-broker test posts `intervals: ["1h"]`. `test_admin_token_guard.py:46` becomes `18`.
2. Engine readers: `Interval(config.intervals[0])`, `INTERVAL_SECONDS[config.intervals[0]]`, `"interval": config.intervals[0]`, `strategy.config.intervals[0] != interval`; backtest `intervals=[config.interval]`; reconcile `intervals=[i.value for i in sub.intervals], parameters=dict(sub.parameters)`.
3. Command service: inject `PositionRepository` and `OrderRepository`. `add_symbol(strategy_id, symbol, intervals: list[str], parameters: dict, broker="paper")` keeps the tracked check, calls `check_strategy_inputs` instead of the registry check, keeps the broker check, builds `intervals=tuple(Interval(i) for i in intervals)`; the comment "Duplicate triples are rejected" (`:70`) names the intervals key instead. `edit(sub_id, intervals, parameters)`: missing → `NotFoundError`; desired or actual not `stopped` → `DomainError(..., error_code="SUBSCRIPTION_RUNNING", status_code=409)`; an open position or a `find_pending()` order with this `subscription_id` → `SUBSCRIPTION_HAS_EXPOSURE` (409), with a comment that unloading drops a paper position; `check_strategy_inputs`; `update_config(dataclasses.replace(sub, ...))`, and `0` → `SUBSCRIPTION_RUNNING`. Both return one shared `_sub_dict(sub)` (`id, strategy_code, symbol, intervals, parameters, created_at, broker`).
4. Query: `get_one` adds `"parameters": dict(cls.DEFAULTS)`; `list_symbols` returns `intervals` (values) and `parameters` instead of `interval`.
5. Routes: `CreateSubscriptionBody{symbol: str, intervals: list[str], parameters: dict = Field(default_factory=dict), broker}`; `EditSubscriptionBody{intervals: list[str], parameters: dict = Field(default_factory=dict)}`; `@subscription_router.patch("/{sub_id}")` calls `cmd_svc.edit(sub_id, body.intervals, body.parameters)`.
6. Update every remaining `StrategyConfig(` and `Subscription(` site in `tests/` and every raw `subscriptions` document a test writes (`git grep -n "\"interval\":" -- tests`, keep those that are bars, backtests or requests) to `intervals` (and `intervals_key`, `parameters` for raw documents).

**Success criteria:** no src reader of a single subscription or strategy interval remains; engine, app and backtest tests pass.

**Verify:** <!-- Red team 2026-11-01: #9 --> the reader grep covers only the subscription and strategy paths; the market-data routes (`app/routes/market_data.py:109,125`) read an unrelated request `body.interval` and stay unchanged. `echo "readers=$(git grep -n -E "config\.interval\b|sub\.interval\b|body\.interval\b|doc\[\"interval\"\]" -- src/pocketquant/app/routes/strategy.py src/pocketquant/engine/strategy src/pocketquant/engine/live src/pocketquant/core/domain/strategy src/pocketquant/core/domain/subscription src/pocketquant/core/infra/persistence/repositories/subscription_repository.py | wc -l | tr -d ' ') tests=$(uv run python -m pytest tests/engine_test tests/app_test tests/backtest_test -q 2>&1 | tail -1)"` prints `readers=0` and a `tests=` line with `passed` and no `failed` or `error` (the tzset red lives under `tests/core_test`, outside this set).

### Task 06.4 — Reload an edited instance, rubric defaults, docs

**Goal:** an edit reaches the trader without a restart, the rubric counts declared defaults, and the docs name the new binding.

**Target files and symbols:** `StrategyReconcileAppService._ensure_instances` (`:115-161`); `scripts/rubric/static_audit.py` (`audit_strategy`, `_find_defaults`, `_literal`); `docs/code-standards.md:93,95`; `tests/engine_test/test_strategy_reconcile_service.py`; `tests/scripts/rubric/test_static_audit.py`.

**Steps:**
1. Tests first in `test_strategy_reconcile_service.py`: `_FakeStrategy` gains `config`; `_FakeStrategyService.load(sub, running)` takes the `Subscription` and stores `SimpleNamespace(intervals=[i.value for i in sub.intervals], parameters=dict(sub.parameters))`; `load_strategy` stores the given config; update the 9 `svc.load(...)` calls (`:118,133,147,161,212,213,268,283,309`) to pass the sub; `_sub` takes `intervals=(Interval.MINUTE_5,)`. Add `test_an_edited_stopped_subscription_reloads_its_config` (loaded stopped with `min_bars` 0, document now `{"min_bars": 2}`: one `unload_calls`, one `load_calls`, the new config carries `{"min_bars": 2}`) and `test_a_running_subscription_is_never_reloaded` (same drift while running: no unload, no load). In `test_static_audit.py` add `test_degrees_of_freedom_count_the_declared_defaults` with the fixture: `audit_strategy("probe")` has `degrees_of_freedom == 1` and `params == ["min_bars"]`. <!-- Red team 2026-11-01: #15 --> This is the only rubric test for declared defaults; no later phase adds a second one for a real strategy, and no test pins the registry contents. Run both files; expected red.
2. `_ensure_instances`: read `existing = self._strategy_service.get_strategy(sub_id)`; `continue` when it exists and is running or its `(config.intervals, config.parameters)` equals `([i.value for i in sub.intervals], dict(sub.parameters))`; otherwise, inside the existing per-sub `try` and before `load_strategy`, `await self._strategy_service.unload_strategy(sub_id)` when `existing` is not `None`. Comment the WHY: an edit is allowed only while stopped and flat, so dropping the stale instance loses nothing.
3. `static_audit.py`: `defaults = dict(cls.DEFAULTS)`; delete `_find_defaults` and `_literal`.
4. `docs/code-standards.md:93`: "`subscription_id` is the UUIDv7 of one `(strategy_code, symbol, intervals)` binding. It keys the in-memory strategy instance, orders, positions and trades." `:95`: "The only duplicate guard for a subscription is the unique index on the joined `intervals_key` (`SubscriptionRepository.ensure_indexes`). A unique index on the `intervals` list itself would be multikey and reject two lists that share one interval. The index is case-sensitive, so `add_symbol` upper-cases `symbol` before it stores it. No test pins that upper-case. Do not remove it."

**Success criteria:** reconcile and rubric tests pass; the doc names no old index.

**Verify:** `echo "doc=$(git grep -n -i -E "dedup_triple|strategy_code, symbol, interval\)|triple" -- docs/code-standards.md src/pocketquant/core/domain/subscription src/pocketquant/core/infra/persistence/repositories/subscription_repository.py src/pocketquant/engine/strategy/strategy_command_service.py | wc -l | tr -d ' ') tests=$(uv run python -m pytest tests/engine_test/test_strategy_reconcile_service.py tests/scripts -q 2>&1 | tail -1)"` prints `doc=0` and a `tests=` line with `passed` and no `failed`.

### Task 06.5 — CLOSE

**Goal:** the contract is on `develop` with green gates and CI.

**Target files and symbols:** all files of this phase.

**Steps:**
1. GATES (plan.md Conventions); FULLSUITE.
2. `git add -A src tests scripts docs && git commit -m "feat(subscription): ordered intervals and strategy parameters"`; push with the Ops recipe; wait for CI.

**Success criteria:** CI on HEAD concludes `success`.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.status) \(.conclusion) \(.headSha)"'` prints `completed success <sha>` with `<sha>` equal to `git rev-parse HEAD` (poll until `completed`).

## Rollback

`git revert <sha>` and push. No prod change happens before D-2 (Phase 15 migrates documents and the index); a revert after Phase 15 is covered by Phase 15's rollback.

## Report

`reports/phase-06-subscription-contract.md`: the red outputs of each test-first step; the Verify outputs of Tasks 06.1-06.4; the number of `StrategyConfig(` and `Subscription(` sites changed; GATES and FULLSUITE tail lines; the CI run id; any ratchet raise. Last line `Result: PASS`.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same failure evidence to the user. Never continue by self-reasoning.
