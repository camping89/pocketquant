# Scout: backend evidence for the STF-to-MTF foundation

Date 2026-11-01 (Asia/Bangkok). Repo `D:/w/_me/algotrading/pocketquant`, branch `develop` @ `e4a998b8`. Read-only scout. Paths are relative to `src/pocketquant/` unless they start with `tests/`, `scripts/`, `docs/` or `.github/`. Everything is verified by reading the file or running grep, `lint-imports` or `scripts/code_metrics.py`, unless it is marked [INFERENCE].

## 0. Traps the advice report does not mention (read first)

1. **A unique index on an array field does not mean "unique list".** MongoDB enforces a unique multikey index per element across documents (https://www.mongodb.com/docs/manual/core/index-unique/, section "Unique Constraint Across Separate Documents", fetched 2026-11-01). With a unique `(strategy_code, symbol, intervals)` index, `["15m","1h"]` and `["15m","4h"]` for the same code and symbol collide on `(code, symbol, "15m")`. [INFERENCE] Store a scalar key derived from the ordered list (for example `"15m,1h,4h"`) and put the unique index on that key.
2. **Changing the index under the same name fails.** `core/infra/persistence/repositories/subscription_repository.py:79-83` creates `ix_subscriptions_dedup_triple` on `(strategy_code, symbol, interval)`. [INFERENCE] Calling `create_index` again with that name and other keys raises an IndexKeySpecsConflict error at startup (`app/main_extensions.py:114-117` gathers every `ensure_indexes`). The precedent for drop-then-create is `core/infra/persistence/repositories/job_history_repository.py:322-341`. `tests/core_test/infra/persistence/test_subscription_repository.py:99-104` asserts the old name and keys.
3. **The backtest sandbox cannot read Mongo today.** `engine/backtest/backtest_sandbox_app_service.py:125-139` builds the sandbox `StrategyAppService` with `bar_repository=NoStoredBars()` (`:58-60`, which has only `find()` and returns `[]`) and `calendar_factory=Continuous24x7CalendarFactory()` (`:68-70`). Advice item 5 is right that `_on_bar_completed` is the one code path, but in a backtest its `_bar_repository` and `_calendar_factory` are stubs. `build_backtest_sandbox()` has one caller, `engine/backtest/backtest_execution_service.py:120`, and that service already holds the real `self._bar_repo` and `self._calendar_factory` (`:59,63`).
4. **20 test fixtures build `StrategyAppService` with `NoStoredBars()`.** Any new `BarRepository` method that `_on_bar_completed` or `start_strategy` calls breaks them unless the stub gains that method (see the grep list in item 3). `tests/engine_test/test_strategy_warm_up.py:40-52` has its own `_StoredBars` stub with only `find`.
5. **In a backtest the position tracker never runs.** The sandbox does not call `PositionAppService.start()` (comment at `backtest_sandbox_app_service.py:120-124`), so `self._position_app_service.get(sid)` returns `None` in a backtest. The risk check at `strategy_app_service.py:545-552` therefore always sees "no position" in a backtest. An EXIT path that reads the quantity from `PositionAppService` gets nothing in a backtest. The paper broker (`_positions`, keyed `f"{subscription_id}:{symbol}"`, `paper_broker_adapter.py:76,332`) is the only source of positions there.
6. **Simulation time in a backtest is the bar start, not its end.** `engine/backtest/backtest_app_service.py:109` sets `set_simulation_time(bar.datetime)`, and the event has no `bar_end` (`core/domain/bar/events.py:7,19`). [INFERENCE] A closed-before filter that uses `get_current_time()` is one entry bar early in a backtest. The filter instant must be `bar_start + INTERVAL_SECONDS[entry]`.
7. **The code-metric ratchet has no headroom.** `uv run python scripts/code_metrics.py --json` gives `tiny_share 0.4809` and `delegations 73`, against the ceilings `max_tiny_share = 0.4810` and `max_delegations = 73` (`pyproject.toml:130-132`). One new one-line forwarding method fails CI. `docs/code-standards.md:148-151` allows a modest raise in its own commit, with the owner told.
8. **The admin-guard test counts mutation routes.** `tests/app_test/integration/test_admin_token_guard.py:46` has `assert len(routes) == 17`. Each new POST, PATCH or DELETE (edit, close, cancel) changes that number. The guard itself is automatic: `app/main_extensions.py:332-336` puts `Depends(verify_admin_token)` on the whole `api` router.
9. **A paper position with no SL and no TP is dropped on takeover.** `strategy_app_service.py:157-165` logs `paper_position_dropped_no_exits` and drops the row. [INFERENCE] A strategy-exit-only position (no SL/TP) is lost on every trader restart unless this rule changes.
10. **The reconcile loop loads every subscription, stopped ones too, and never reloads.** `engine/live/strategy_reconcile_app_service.py:115-161` (`_ensure_instances`) skips a sub whose instance exists (`:119-120`), whatever its `desired_state`. [INFERENCE] "Edit while stopped" leaves the stale `StrategyConfig` in RAM unless the edit forces an unload (for example by comparing the config, or through `unload_strategy`, `strategy_app_service.py:306-328`).
11. **The engine never reads `Signal.entry_price`.** Orders are priced at `event.close` (`strategy_app_service.py:542,589`). `_create_order` (`:633-651`) maps every non-LONG direction to SELL (`:640`) and always uses `OrderType.MARKET` (`:646`). An EXIT on a short would become a SELL today.
12. **Exness rejects a second order while a position is held.** `_submit_open` returns "position already open for subscription" (`core/infra/brokers/exness/exness_broker_adapter.py:238-239`). An EXIT cannot go through `submit_order`.
13. **STF code outside src and tests.** `scripts/rubric/static_audit.py:12,16,44` imports `STRATEGY_REGISTRY` and parses each strategy's `_DEFAULTS` by AST. `tests/scripts/rubric/test_static_audit.py:7-36` parametrizes the three STF codes and asserts DoF 4/5/6. `docs/swing-pivot-key-level.md` (16 lines) describes the engulfing strategy and goes stale on delete; its only inbound link is `web/src/lib/indicators/engulfing.ts:65`.
14. **There are two golden fixtures, not one shared file.** `tests/core_test/unit/domain/strategy/patterns/engulfing_golden_fixture.json` and `web/src/lib/indicators/__fixtures__/engulfing_golden_fixture.json` are byte-identical (`cmp`). The Python test reads its own copy (`test_engulfing_detector.py:13`). The mirror comment is `web/src/lib/indicators/engulfing.ts:4-6`.

## 1. Subscription

- Entity `core/domain/subscription/entities.py`:
  - `RunState = Literal["running","stopped"]` `:13`; `BROKERS = ("paper","exness")` `:14`.
  - `SubscriptionAlreadyExistsError(strategy_code, symbol, interval)` `:19-25` (409, `SUBSCRIPTION_ALREADY_EXISTS`).
  - `@dataclass(frozen=True) Subscription` `:29-38`, fields `id: UUID, strategy_code: str, symbol: str, interval: Interval, created_at: datetime, desired_state="stopped", actual_state="stopped", broker="paper"`. It has **no `parameters` field**.
  - `to_mongo` `:40-50` (writes `"interval": self.interval.value`); `from_mongo` `:52-70` (unknown broker raises `ValueError`).
  - Re-exported by `core/domain/subscription/__init__.py:1-7`.
- Repository `core/infra/persistence/repositories/subscription_repository.py`, collection `subscriptions` `:15`:
  - `add` `:19-27`, which maps `DuplicateKeyError` to `SubscriptionAlreadyExistsError(sub.strategy_code, sub.symbol, sub.interval.value)` `:25-27`.
  - `get` `:29`; `list_by_strategy_code` `:36`; `list_by_symbol` `:41`; `list_all` `:45`.
  - `update_desired_state` `:50-57` and `update_actual_state` `:59-63` return `matched_count`.
  - `delete` `:65-69`.
  - `ensure_indexes` `:71-84` creates `ix_subscriptions_strategy_code` and the unique `ix_subscriptions_dedup_triple` on `[("strategy_code",1),("symbol",1),("interval",1)]` `:79-83`. There is no generic `update`/`replace` method.
- DTOs: none. The request body is `CreateSubscriptionBody(symbol: str, interval: str, broker: Literal["paper","exness"]="paper")` in `app/routes/strategy.py:13-16`. The services return plain dicts.
- Routes `app/routes/strategy.py`:
  - `strategy_router` `/strategies` `:21`: `GET /` `:28-32` (`response_model=list[StrategyTemplateResponse]`, `:24-25`, field `strategy_code` only), `GET /{strategy_code}` `:35-43`, and `POST /{strategy_code}/subscriptions` (201) `:46-52`, which calls `cmd_svc.add_symbol(strategy_code, body.symbol, body.interval, body.broker)`.
  - `subscription_router` `/subscriptions` `:57-59`: `GET /` `:62-67`, `POST /{sub_id}/start` `:70-76`, `POST /{sub_id}/stop` `:79-85`, `GET /{sub_id}/positions` `:88-93`, `GET /{sub_id}/trades` `:96-102`, `GET /{sub_id}/metrics` `:105-110` (`LiveMetricsQueryService`), `DELETE /{sub_id}` (204) `:113-119`.
  - **No edit/update route exists** (no PATCH/PUT on subscriptions).
  - The routers are mounted at `app/main_extensions.py:299,355-356`.
- Command service `engine/strategy/strategy_command_service.py` (`StrategyCommandService`, deps `SubscriptionRepository, TrackedSymbolRepository, SafeguardsRepository`):
  - `start(subscription_id)` `:34-38` and `stop` `:40-44` write `desired_state` only and raise `NotFoundError` on 0 matches.
  - `add_symbol(self, strategy_id: str, symbol: str, interval: str, broker: str = "paper") -> dict` `:48-89`. It uppercases the symbol, checks tracked (`SYMBOL_NOT_TRACKED`) `:52-56`, checks the code is in `STRATEGY_REGISTRY` `:58-59`, and checks the exness flag through `safeguards_repo.load_live_trading()` (`BROKER_DISABLED`) `:61-66`. It builds `Subscription(... interval=Interval(interval) ...)` `:71-80` and returns a dict `:82-89`. It **never instantiates the strategy class, so it validates no parameters**.
  - `remove_symbol(sub_id) -> int` `:91-92`: a plain delete. It does not check running state, open position or pending order.
- Query service `engine/strategy/strategy_query_service.py`:
  - `get_all` `:21-22` returns registry codes; `get_one` `:24-31` returns only `class_name`, **no parameter defaults are exposed**.
  - `list_symbols` `:35-57` returns `interval: sub.interval.value` `:49` and `is_running`.
  - `get_positions` `:59-73` and `get_trades` `:76-91` read `PositionRepository`.
- Callers of `add_symbol`/`remove_symbol`: `app/routes/strategy.py:52,118`; `engine/market_data/tracked_symbols_service.py:120-140` (`remove()` calls `stop` then `remove_symbol` per sub and deletes Redis key patterns `:130-139`).
- Reconcile (`engine/live/strategy_reconcile_app_service.py`):
  - `StrategyConfig` is built at `:144-155` with `id, name=sub.strategy_code, symbol, interval=sub.interval.value, contract_spec, broker, risk`. It passes **no `parameters`**.
  - Risk selection `:137-143`.
  - Unknown code is logged once (`reconcile.unknown_template`) `:121-130`; a load failure is logged once (`reconcile.load_failed`) `:158-161`. A bad-parameter `ValueError` from the strategy `__init__` lands here.
  - `bootstrap` `:48-60`, `_reconcile` `:77-111`, `_unload_orphans` `:166-178`, `_converge_one` `:182-193`.
  - DI: `app/di/services.py:156-173`.
- Other `sub.interval` readers: `strategy_query_service.py:49`, `strategy_command_service.py:86`, `subscription_repository.py:26`, `strategy_reconcile_app_service.py:149`.
- Tests:
  - `tests/core_test/unit/domain/subscription/test_subscription_desired_actual_state.py`: `test_defaults_are_stopped` :30, `test_to_mongo_writes_both_state_keys` :36, `test_from_mongo_legacy_doc_without_keys_defaults_stopped` :42, `test_from_mongo_preserves_running_desired_state` :55, `test_to_from_mongo_roundtrip_stable_with_states` :62, `test_replace_state_keeps_id_stable` :67, `test_to_from_mongo_roundtrip` :75, `test_already_exists_error_carries_code_and_triple` :90.
  - `tests/core_test/infra/persistence/test_subscription_repository.py`: `test_add_get_delete_round_trip` :57, `test_add_same_triple_different_id_raises` :75, `test_concurrent_add_same_triple_one_doc_one_error` :86, `test_dedup_triple_unique_index_exists` :99, `test_list_by_strategy_code_filters_correctly` :108, plus 4 desired/actual-state tests :130-163.
  - `tests/engine_test/test_strategy_service.py` (15 tests): `test_add_symbol_persists_stopped_state` :132, `test_add_symbol_accepts_exness_only_while_the_trader_flag_is_on` :151, `test_add_symbol_404_when_symbol_not_tracked` :175, `test_add_symbol_404_when_unknown_template` :187, `test_remove_symbol_deletes_subscription` :207, `test_get_all_returns_registry_codes` :223, `test_list_symbols_derives_is_running_from_actual_state` :254, …
  - `tests/engine_test/test_strategy_reconcile_service.py` (17 tests, :114-318; `_STRATEGY` :20, "must be in STRATEGY_REGISTRY").
  - `tests/engine_test/test_subscription_broker_selection.py` (8 tests, :42-153).
  - `tests/app_test/integration/test_declarative_subscription_state_api.py` (`test_start_writes_desired_state_only` :27, `test_serves_seeded_read` :60).
  - `tests/app_test/integration/test_tracked_symbol_cascade_delete_api.py::test_delete_cascades_all_symbol_data_and_spares_other_symbols` :142.
  - `tests/app_test/integration/test_admin_token_guard.py` (the create path uses `/strategies/engulfing/subscriptions` :27; route count :46).
  - `Subscription(` is built in 12 test sites across 10 files (git grep -c).

## 2. Strategy contracts, registry, STF footprint

- `core/domain/strategy/value_objects.py`:
  - `@dataclass(frozen=True) Signal` `:9-23`: `symbol, direction: Direction, confidence: float, timestamp: datetime, subscription_id: str, entry_price=None, stop_loss_price=None, take_profit_price=None, entry_logic=""`; `__post_init__` checks `0<=confidence<=1`.
  - `@dataclass StrategyConfig` `:26-35`: `id, name, symbol, interval: str, broker="paper", parameters: dict = {}, risk: RiskConfig = RiskConfig(), contract_spec = LINEAR_SPEC`.
- `core/domain/strategy/enums.py:4-8`: `Direction` has `LONG, SHORT, EXIT ("exit"), FLAT`. **`EXIT` already exists.** `src` has no `Direction.EXIT`/`FLAT` reader except the rejection at `engine/execution/risk_check.py:25`.
- `core/domain/strategy/strategy_service_interface.py`:
  - `FilledOrder` Protocol `:11-14`.
  - `IStrategyService(ABC)` `:16`; `__init__(config)` sets `config, id, _is_running, _open_direction`.
  - Methods: `is_running` property, `on_start`, `restore_direction(direction)` `:30`, `on_stop`, abstract `async on_bar_completed(bar: dict) -> Signal | None` `:37` (**the only decision hook**), `on_order_filled(order, fill_price)` `:39`, `on_order_rejected(reason)` `:42`.
- Registry `core/domain/strategy/services/__init__.py:11-15`: `STRATEGY_REGISTRY: dict[str, type] = {"engulfing", "engulfing_pullback30_touch"}`; `__all__` `:17-22`.
- Every importer of `STRATEGY_REGISTRY`:
  - src: `app/routes/backtest.py:9,43`; `engine/backtest/backtest_execution_service.py:9,103,107`; `engine/live/strategy_reconcile_app_service.py:7,121`; `engine/strategy/strategy_command_service.py:8,58`; `engine/strategy/strategy_query_service.py:3,22,25`.
  - scripts: `scripts/rubric/static_audit.py:12,16,18`.
  - tests: `tests/app_test/integration/test_app_standalone_runtime.py:77,84`; `tests/app_test/integration/test_trader_lifespan_handover.py:28,139`; `tests/backtest_test/engine/test_engulfing_backtest.py:18,189,231`; `tests/backtest_test/engine/test_engulfing_pullback30_touch_backtest.py:21,215,258`; `tests/backtest_test/test_backtest_single_run_direct_task.py:15,171,269`; `tests/engine_test/test_live_trade_collector_integration.py:15,103,134`; `tests/engine_test/test_reconcile_restart_resume_integration.py:16,80`.
- How parameters are declared and validated: each strategy has a module-level `_DEFAULTS` dict (`engulfing_strategy_service.py:16-21`, `engulfing_pullback30_touch_strategy_service.py:19`). `__init__` reads `config.parameters or {}` with `p.get(key, _DEFAULTS[key])` and raises `ValueError` on bad values (for example `engulfing_strategy_service.py:27-48`). Unknown keys are ignored silently. There is no class-level schema or defaults accessor, and no endpoint exposes defaults.
- Instantiation sites (where a bad parameter surfaces): `engine/strategy/strategy_app_service.py:199-200` (live load, via reconcile) and `engine/backtest/backtest_execution_service.py:129` (backtest; caught by `execute_and_persist` :80-82, which marks the run failed).
- STF files: `engulfing_strategy_service.py` 151, `engulfing_pullback30_touch_strategy_service.py` 203, `core/domain/strategy/patterns/engulfing_detector.py` 59, `patterns/__init__.py` 6, `services/__init__.py` 22.
- `git grep -c -E "engulfing" -- src tests` (per file):
  - src: `patterns/__init__.py` 3, `patterns/engulfing_detector.py` 2, `services/__init__.py` 6, `engulfing_pullback30_touch_strategy_service.py` 4, `engulfing_strategy_service.py` 3. Nothing outside `core/domain/strategy`.
  - Delete with STF (unit, behaviour-bound): `tests/core_test/unit/domain/strategy/test_engulfing.py` 7 (14), `test_engulfing_pullback30_touch.py` 9 (13), `patterns/test_engulfing_detector.py` 6 (2) + `patterns/engulfing_golden_fixture.json` 1; `tests/backtest_test/engine/test_engulfing_backtest.py` 10 (3), `test_engulfing_pullback30_touch_backtest.py` 3 (3).
  - Import an STF class directly, so a rewrite is needed: `tests/backtest_test/test_backtest_single_run_direct_task.py` 9 (needs an engulfing class that produces trades: `_engulfing_bars` :76, :269 `STRATEGY_REGISTRY["engulfing"](live_cfg)`).
  - Use a code as a registry key that must resolve: `tests/engine_test/test_live_trade_collector_integration.py` 1 (:38), `tests/engine_test/test_reconcile_restart_resume_integration.py` 1 (:43), `tests/engine_test/test_strategy_reconcile_service.py` 1 (:20), `tests/engine_test/test_strategy_service.py` 5 (:140-261), `tests/app_test/integration/test_app_standalone_runtime.py` 1 (:30), `tests/app_test/integration/test_trader_lifespan_handover.py` 2, `tests/backtest_test/test_backtest_dispatch_contract_spec.py` 1 (:57), `tests/core_test/test_core_layout_contract.py` 1 (:11, module path in `NEW_MODULES`).
  - Use a code as an opaque string only: `test_admin_token_guard.py` 1, `test_backtest_name_api.py` 1, `test_backtest_orders_api.py` 2, `test_backtest_verdict_api.py` 1, `test_declarative_subscription_state_api.py` 1, `tests/backtest_test/test_backtest_result_verdict.py` 1, `tests/core_test/infra/brokers/test_paper_broker_spread.py` 1, `tests/core_test/infra/persistence/backtest/test_backtest_repository_slimmed.py` 8, `test_subscription_desired_actual_state.py` 5, `tests/engine_test/market_data/test_tracked_symbols_service.py` 1, `tests/engine_test/test_contract_spec_wiring.py` 2, `tests/engine_test/test_subscription_broker_selection.py` 1.
  - Rubric: `tests/scripts/rubric/test_dedup.py` 6, `test_persist_shape.py` 1, `test_renderers.py` 6 (string data), `test_static_audit.py` 6 (imports the registry through `scripts/rubric/static_audit.py`).
  - Manual files: `tests/http/backtest/list-results.bru` 1, `run-backtest.bru` 1, `tests/manual/api-test.http` 3.
- `StrategyConfig(` is built in 29 sites (2 src, 27 tests across 22 files). Every one passes `interval=`.

## 3. `StrategyAppService` (`engine/strategy/strategy_app_service.py`, 684 lines)

- Constants: `_FALLBACK_SL_PCT` `:41`, `_STALE_AFTER_S` `:43`, `_WARMUP_BARS = 500` `:45` (no test references it), `_WARMUP_READY_SECOND = 20` `:47`.
- `__init__` `:57-102`: keyword-only `bar_repository: BarRepository, calendar_factory: TradingCalendarFactory, trade_repository` stored as `_bar_repository` `:76` and `_calendar_factory` `:77`. State: `_strategies, _brokers, _broker_pool, _configs, _signal_tasks, _last_bar_start, _running_bar_handlers, _sending, trading_until`.
- DI (live): `app/di/services.py:122-153`. Sandbox: `engine/backtest/backtest_sandbox_app_service.py:128-137` (stubs, see trap 3).
- `start` `:110-119` subscribes `BarCompletedEvent`, `OrderCancelledEvent`, `OrderFilledEvent`. The paper broker subscribes later at `connect()` (`paper_broker_adapter.py:106-111`), so a strategy sees the bar before the SL/TP check.
- `take_over` `:144-186`: loads pending orders and open positions, restores the paper brokers, drops paper rows without SL/TP `:157-165`, and restores directions `:171-177`.
- `load_strategy(config, strategy_class)` `:188-215`.
- `start_strategy(strategy_id)` `:219-283` (65 lines, listed over 60 by the metrics script):
  - `interval = Interval(config.interval)`, `step` `:235-236`; calendar `:237`; `_closed_bars(...)` `:238`; waits until second 20 `:240-248`.
  - Replays every stored bar through `strategy.on_bar_completed(dict)` `:252-264`; a replay signal is answered with `on_order_rejected("warmup")` `:265-266`.
  - Sets `_last_bar_start` `:267-270`; restores direction `:271`; `strategy.warmup_incomplete` warning `:273-281`.
- `_closed_bars(symbol, interval, step, now)` `:285-289`: `self._bar_repository.find(symbol, interval, end_date=now, limit=_WARMUP_BARS)`, reversed to ascending, keeping `b.datetime + step <= now`. **This is the only "closed before instant" filter in the codebase.**
- `stop_strategy` `:291-300`. `unload_strategy` `:306-328`: paper drops positions and disconnects an unshared broker; a venue logs `strategy_unloaded_venue_position_kept`.
- `inject_prepared_strategy(sid, strategy, broker, config)` `:334-347`: registers, connects and calls `on_start()` under `_lock`. **No warm-up replay.** Callers: `backtest_execution_service.py:130`, and the tests `tests/backtest_test/engine/test_*_backtest.py` (:205/:232/:259), `tests/backtest_test/test_backtest_single_run_direct_task.py:270`, `tests/engine_test/strategy_injection_roundtrip_characterization_test.py:88-145`, `tests/engine_test/test_order_filled_event_routing.py:96-138`.
- `_on_bar_completed(event)` `:363-432`:
  - Loops `self._find_strategies(event.symbol, event.interval)` `:367` and skips a seen bar (`bar_start <= last`) `:369-373`.
  - The successor check runs only when `event.bar_end is not None` (live), using `calendar.trading_minutes` `:375-378`.
  - **The bar dict** `:380-389` has the keys `symbol, interval, open, high, low, close, volume, timestamp=event.bar_start`. The warm-up dict at `:253-263` has the same keys, built a second time (DRY candidate).
  - Calls `on_bar_completed` `:391`. Skip reasons `stale` / `gap` / `inflight` `:398-421`. Paper runs `_process_signal` inline; a venue runs it as a task `:422-430`.
- `_find_strategies(symbol, interval)` `:492-502`: filters on `is_running`, `config.symbol == symbol` and `config.interval == interval`. Called only at `:367`.
- `_process_signal` `:505-631`:
  - Checks `trading_until` and the deadline `:514-534`, then `broker.get_balance()` `:543`.
  - Position comes from `self._position_app_service.get(strategy.id)` `:545`; risk validate `:547-560`; fallback SL `:562-566`.
  - Sizing with `PositionCalculatorDomainService.calculate` `:568-580`; `normalize_quantity` `:582-587`.
  - `_create_order` `:589`; `order_app_service.submit(order, broker, deadline)` `:591-599`; `live.signal_latency` INFO `:608-628`.
- **Signals become orders** in `_create_order(strategy, signal, size, current_price)` `:633-651`: `side = BUY if LONG else SELL` `:640`, `order_type=OrderType.MARKET` `:646`, `price=current_price` (= `event.close`), `sl_price=signal.stop_loss_price`, `tp_price=signal.take_profit_price`.
- Tests on these paths:
  - `tests/engine_test/test_strategy_warm_up.py` (4): :156, `test_a_replayed_signal_sends_nothing` :169, `test_a_long_mirror_row_restores_direction_long` :180, `test_a_hole_after_the_stored_bars_warns_once_and_gap_skips` :191.
  - `tests/engine_test/test_strategy_entry_guards.py` (11): `test_stale_budget` :163, `test_a_gap_flagged_bar_skips_the_entry` :181, `test_a_non_successor_bar_skips_the_entry` :192, `test_paper_sl_still_fills_on_a_stale_bar` :205, `test_a_backtest_event_never_skips` :231, `test_a_seen_bar_is_ignored` :240, the standby/drain/lease tests :253-294, `test_one_latency_line_per_live_signal` :307.
  - `tests/engine_test/test_concurrent_opens.py` (6, calls `engine._on_bar_completed` directly :173,:242).
  - `tests/engine_test/test_strategy_reject_delivery.py` (6), `tests/engine_test/test_paper_position_lifecycle.py` (5, incl. `test_an_opposite_signal_keeps_the_paper_position` :166), `tests/engine_test/test_paper_restore.py`, `tests/engine_test/test_trader_fence.py`, `tests/engine_test/strategy_injection_roundtrip_characterization_test.py`.
- Fixtures that build `StrategyAppService(bar_repository=NoStoredBars(), calendar_factory=Continuous24x7CalendarFactory())` (20 sites):
  - `tests/backtest_test/engine/test_{engulfing,engulfing_pullback30_touch}_backtest.py`, `tests/backtest_test/test_backtest_single_run_direct_task.py:255`.
  - `tests/engine_test/{strategy_injection_roundtrip_characterization_test,test_async_broker_fill_wiring,test_concurrent_opens,test_contract_spec_wiring (x2),test_live_trade_collector_integration,test_order_filled_event_routing,test_paper_position_lifecycle,test_paper_restore,test_reconcile_restart_resume_integration,test_strategy_entry_guards,test_strategy_reject_delivery,test_subscription_broker_selection,test_trader_fence}.py`.
  - `test_strategy_warm_up.py:95,127` uses `_StoredBars`.

## 4. Signal to order, risk, brokers, position store

- `OrderType` `core/domain/order/enums.py:4-8`: `MARKET, LIMIT, STOP_LIMIT, STOP_MARKET ("stop_market")`. `STOP_MARKET` appears only in `OrderAggregate.create` validation (`core/domain/order/entities.py:68-69`, which requires `stop_price`). No entry path creates it.
- `OrderStatus` `enums.py:16-36`: `PENDING, SUBMITTED, PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED, EXPIRED`; `is_terminal`, `is_active` (SUBMITTED, PARTIALLY_FILLED).
- `OrderAggregate` `core/domain/order/entities.py:23-49` has fields including `stop_price`, `sl_price`, `tp_price`, `broker_order_id`. Transitions `:43-49`: PENDING→SUBMITTED/REJECTED; SUBMITTED→PARTIALLY_FILLED/FILLED/CANCELLED. `create(...)` `:51-82`; `submit`, `fill`, `cancel`, `reject` follow.
- `RiskCheckHandler.validate(signal, account, position, config=None) -> tuple[bool, str]` `engine/execution/risk_check.py:15-46`:
  - Balance check `:22-23`; rejects any direction other than LONG/SHORT `:25-26`; a missing or closed position passes `:28-29`.
  - Rejects an opposite position (`"opposite position open"`) `:31-32`; equity check `:34-35`; max exposure `:37-44`. The comment `:12-14` states "exits are SL/TP only".
  - Tests `tests/engine_test/test_risk_check.py`: `test_an_entry_signal_passes` :35, `test_exit_and_flat_signals_are_rejected` :40, `test_zero_equity_with_an_open_position_is_rejected` :47, `test_an_opposite_entry_is_rejected` :59, `test_a_same_side_entry_still_reaches_the_exposure_check` :69.
- Broker port `core/domain/brokers/broker_port.py:14-69`: `fills_async`, `inflight_count`, `connect/disconnect`, `normalize_quantity`, `submit_order(order, *, deadline)`, `cancel_order(broker_order_id) -> bool`, `get_positions`, `get_balance`, `subscribe_order_updates`, `subscribe_trades`. It has **no close-position or pending-order method**.
- Paper `core/infra/brokers/paper/paper_broker_adapter.py` (593 lines):
  - `submit_order` `:119-140` calls `_handle_market` `:142-222` (81 lines). That method **rejects non-MARKET** with `"paper broker fills market orders only"` / `REASON_UNSUPPORTED_ORDER_TYPE` `:146-165`, fills at `order.price` + spread + slippage `:167-183`, checks affordability, and runs `_execute_fill_with_commission`.
  - `cancel_order` returns True as a no-op (`:224-226`): "a paper order is terminal when submit_order returns". **There are no pending orders in paper.**
  - `_execute_fill` `:329-362`: an opposite-side fill reduces or closes the live position and emits a `TradeClosedEvent`. [INFERENCE] A MARKET order on the opposite side for the full quantity is a working paper close.
  - `drop_positions` `:230-234`; `restore` `:237-246`.
  - `_on_bar_completed` `:472-503` acts only on the finest interval per symbol (`:473-477`), skips positions opened on this bar (`fresh`, `:479`), calls `_check_sl_tp` `:505-526` (gap-open fills at open; SL wins when both hit) and `_fire_synthetic_exit` `:528-586` (MARKET exit, publishes `OrderFilledEvent` itself `:576-586`), then marks to market `:500-503`. [INFERENCE] This is where a pending stop-trigger check would fit.
  - Reasons are in `core/domain/brokers/events.py:14-20` (`submit, market_fill, auto_sl, auto_tp, insufficient_balance, no_market_price, unsupported_order_type`).
  - Tests `tests/core_test/infra/brokers/`: `test_paper_broker_sl_tp_fill.py` (25), `test_paper_broker_spread.py` (8), `paper_broker_futures_accounting_test.py` (10), `paper_broker_commission_test.py` (6), `test_paper_broker_contract_spec.py` (6); `tests/backtest_test/engine/test_paper_broker_{order_events (5),signal_bar (1),trade_emission (6)}.py`.
- Exness broker: the order logic is in **`core/infra/brokers/exness/exness_broker_adapter.py`** (809 lines), not in `core/infra/exness/exness_adapter.py`, which is the market-data candle adapter (72 lines).
  - The header `:1-6` says "market orders only … Positions close only by venue SL/TP or a broker stop-out".
  - `submit_order` `:209-214` rejects non-MARKET (`"exness adapter supports market orders only"`). `_submit_open(order, deadline)` `:216-286` (71 lines) checks: entries paused `:221-236`, held position `:238-239`, inflight `:240-243`, presubmit `:244-246`, SL required `:247-248`, loss cap, lot grid. The body is `instrument, side, volume, stop_loss_price[, take_profit_price]` `:264-271`.
  - `_send_tracked` `:385-428` calls `openPosition` with `idempotency_key=rid`; the ack `operation_id` becomes `broker_order_id`. `_watch_operation` `:430-452` polls `getOperationStatus`; `_recover_fill` `:454`.
  - Events: `_on_transaction` `:547-572` (an inflight rid looks only for an `open` deal `:555-557`; `close` deals go to `_on_broker_close` `:568-570`). `_on_broker_close` `:574-591` (supports partial units). `_close_missing` `:529-545`.
  - `cancel_order` `:750-752` logs `exness.cancel_unsupported` and returns False.
  - Tests `tests/core_test/infra/brokers/exness/`: `test_exness_broker_adapter.py` (34; :227 pins "market orders only" for LIMIT), `test_exness_open_path.py` (10), `test_exness_broker_factory.py` (3); `tests/engine_test/test_exness_clamp_fill_position.py`, `tests/engine_test/test_async_broker_fill_wiring.py`.
- Exness client `core/infra/exness/exness_client.py` (388 lines):
  - `_ENDPOINTS` `:28-45`; the only order op is `"openPosition": ("POST", "/v1/trading/accounts/{account_id}/positions")` `:44`. **There is no close (DELETE position) or create-order (POST orders) endpoint.**
  - `_ORDER_OPS = frozenset({"openPosition"})` `:46`; `_PRIORITY_OPS` `:47`. `order_request_interval` `:110-120` lists `("openPosition","getOperationStatus")` at `:115`.
  - `call(op, *, path_params, params, json_body, idempotency_key, deadline)` `:219-255`.
  - Tests: `tests/core_test/infra/exness/test_exness_client.py` (:284 asserts `LIVE_TRADING_DISABLED`).
- **Live flag check points**:
  - (1) `core/infra/exness/exness_client.py:231-232`: any `op in _ORDER_OPS` raises `LIVE_TRADING_DISABLED` while `settings.exness_live_trading` is false. A new order op must join `_ORDER_OPS` to be fenced.
  - (2) `core/infra/brokers/broker_factory.py:59-63`: the factory refuses to build the exness broker unless `safeguards.live_trading` is set.
  - (3) `engine/strategy/strategy_command_service.py:61-66`: the api reads the trader's stored flag (`SafeguardsRepository.load_live_trading`, `core/infra/persistence/repositories/safeguards_repository.py:20-25`; the trader writes it at `app/roles.py:197-198`).
  - Setting: `core/config.py:70` `exness_live_trading: bool = False`. Test: `tests/app_test/integration/test_exness_live_trading_off.py:60`.
- Position store:
  - `engine/execution/position_app_service.py` keeps an in-memory `_positions: dict[subscription_id, PositionAggregate]` `:28`. `load_open_positions` `:38-42`, `drop` `:44-47`, `_on_order_filled` `:49-118` (open / add / reduce-or-close by side; 70 lines), `get` `:120-121`.
  - Repo `core/infra/persistence/repositories/position_repository.py`: `save, get, find_open, find_open_by_subscription, delete_open_by_subscription, find_closed_by_subscription`; indexes `ix_positions_subscription_id/is_closed/symbol` `:52-56`.
  - `PositionAggregate` `core/domain/position/entities.py:20` (`reduce_quantity` :124, `close` :192).
- Orders store: `engine/execution/order_app_service.py` `submit` `:27-120` (94 lines; PENDING→SUBMITTED→FILLED for an immediate fill `:57-66`), `on_order_update` `:129-165` (FILLED/CANCELLED for async brokers), `load_pending_orders` `:167-172`. Repo `core/infra/persistence/repositories/order_repository.py:20-25` `find_pending` = status in `pending|submitted|partially_filled`; indexes `:29-31`.
- **Close paths today**: (a) paper SL/TP synthetic exit `paper_broker_adapter.py:472-586`; (b) Exness venue close via the events stream `exness_broker_adapter.py:568-591`; (c) Exness close found after an absence `:529-545`; (d) paper unload drops the position without a trade (`strategy_app_service.py:315-320`); (e) the paper takeover drop of a row with no SL/TP (`:157-165`). There is no strategy-initiated or manual close, and no cancel of a real pending order.
- Docs that state SL/TP-only: `docs/system-architecture.md:12` ("Exits are SL/TP only…") and `:37-48` ("One take-profit per entry, closed in full" table, which names `PaperBrokerAdapter._check_sl_tp/_fire_synthetic_exit` at :45).

## 5. Backtest

- `core/domain/backtest/config.py:10-28` `@dataclass BacktestConfig`: `strategy_code, symbol, interval: str, start_date, end_date, initial_capital, slippage_bps, commission_bps, spread, parameters: dict, name, contract_spec`.
- Request DTO `RunBacktestCommand` `engine/backtest/backtest_command_service.py:17-42` (`strategy_id, symbol, interval, start_date, end_date, initial_capital, slippage_bps, commission_bps, spread, parameters: dict | None, name`). `BacktestCommandService.run` `:51-67` builds the config payload dict (`"interval"` `:56`) and saves `BacktestResult.started(run_id, config)`.
- `engine/backtest/backtest_execution_service.py`:
  - `_config_from_dict` `:32-46`; `run(config_payload, run_id)` `:97-145`; registry lookup `:103-108`.
  - `StrategyConfig(id=config.strategy_code, name, symbol, interval=config.interval, broker="paper", parameters={**config.parameters}, contract_spec)` `:110-118`.
  - `build_backtest_sandbox()` `:120`; broker `:122-128`; strategy instance `:129`; `inject_prepared_strategy` `:130-132`; `BacktestAppService(... bar_repository=self._bar_repo, calendar=await self._calendar_factory.for_symbol(...))` `:134-142`.
- `engine/backtest/backtest_app_service.py` `run` `:56-184` (129 lines):
  - Streams **one interval**: `self._bar_repo.stream(config.symbol, Interval(config.interval), config.start_date, config.end_date)` `:103-105`; `set_simulation_time(bar.datetime)` `:109`.
  - Publishes `BarCompletedEvent(interval=config.interval, bar_start=bar.datetime, …, occurred_at=bar.datetime)` with no `bar_end` `:110-123`; `_mtm_on_bar` `:81-85`.
- `BarRepository.stream(symbol, interval, start_datetime, end_datetime) -> AsyncIterator[Bar]` `core/infra/persistence/repositories/bar_repository.py:130-151`: ascending, `$gte`/`$lte` inclusive, cursor closed in `finally`.
- `config.interval` is also read by `backtest_report_app_service.py:308-316` (`calendar.periods_per_year(interval)` for Sharpe/Sortino) and `:336,359` (persisted `interval`). [INFERENCE] Keep the entry interval (lowest) as the annualization interval.
- Result entity `core/domain/backtest/entities.py:25-27,51,64,96` has a top-level `interval: str`. Index `ix_backtests_strategy_symbol_interval_started` on `(strategy_code, symbol, interval, started_at -1)` `core/infra/persistence/repositories/backtest_repository.py:125-128`; `list_by_strategy_code(..., interval=None)` `:34-51`.
- Routes `app/routes/backtest.py`: `GET /backtest/strategies` `:41-43` (registry keys); `POST /backtest/run` (202) `:48-60`; `GET /{run_id}` `:63`; `PATCH /{run_id}/verdict` `:72`; `PATCH /{run_id}/name` `:82`; `GET /{run_id}/equity|trades|trade-markers|stats|orders`; `GET /strategy/{strategy_id}` `:157-196`, which takes an `interval` query and returns `interval` and `parameters` per run. `ListBacktestsQuery` `engine/backtest/backtest_query_service.py:18-23`.
- Sandbox `engine/backtest/backtest_sandbox_app_service.py`: in-memory order/position repos `:24-55`, stubs `:58-70`, `_SingleBrokerFactory` `:75-80`, `create_broker` `:88-110`, `aclose` `:112-117`, `build_backtest_sandbox()` `:125-139` (no arguments).
- Tests `tests/backtest_test/`: `test_backtest_single_run_direct_task.py` (4: :135, :163, :182, `test_backtest_sandbox_does_not_leak_to_live_engine` :275), `test_backtest_dispatch_contract_spec.py` (1, passes `bar_repository=None`), `test_backtest_execution_heartbeat.py` (1), `test_backtest_result_verdict.py` (2), `test_backtest_stats_service.py` (4), `engine/test_backtest_app_service_persistence.py` (2), `engine/test_result_collector_mark_to_market.py` (5), `engine/test_report_annualization_source.py` (3); API: `tests/app_test/integration/test_backtest_{name,orders,verdict}_api.py`; repo: `tests/core_test/infra/persistence/backtest/test_backtest_repository_slimmed.py`.

## 6. Market data (advice item 6), line numbers re-verified on `e4a998b8`

- `engine/market_data/app_services/cascade_aggregator.py`:
  - `CASCADE_TFS` `:18-24` (5m, 15m, 1h, 4h, 1d); `_INTRADAY_CASCADE_TFS` `:26-31`; comment `:34-37`; `cascade_tfs(calendar)` `:38-41`; `CALENDAR_CRYPTO_24_7` import `:10`.
  - `tf_seconds` `:44-56` has no `WEEK_1`.
  - `compute_boundaries` `:86-113`; partial-bucket comment `:116-118`; `cascade_for_symbol(symbol, lookback_minutes, bar_repo, calendar)` `:119-180+` iterates `cascade_tfs(calendar)` `:132`; `expected_count = len(calendar.trading_minutes(boundary, bucket_end))` `:141`; `bar_repo.find(... limit=expected_count + 5)` `:143-149`; `Bar(... session_date=... if DAY_1)` `:163-174`.
  - **All advice line numbers hold.**
- Users of `cascade_tfs`/`CASCADE_TFS`: `cascade_aggregator.py:132`; `scripts/backfill/binance_bars.py:29,360` (`CASCADE_TFS` only, unaffected); `tests/app_test/market_data/test_cascade_aggregator.py:17,20,267,513-520`; `tests/app_test/market_data/test_cascade_calendar_golden.py:19,64`; comment refs `sync_jobs.py:56`, `tracked_symbols_backfill.py:83`, `tests/engine_test/market_data/test_backfill_daily_mode.py:2`.
- `engine/market_data/tracked_symbols_backfill.py`: `CALENDAR_CRYPTO_24_7` import `:10`; `_CASCADE_DEFAULT_TFS` `:22-29` (already holds `DAY_1`); `resolved_mode` `:59-62`; the DAY_1 direct-mode override with its comment is `:80-102` (holds).
- `engine/market_data/app_services/sync_jobs.py`: the comment `:48-56` holds; `SYNC_INTERVALS` from `:57`; `sync_integrity` `:440`; `sync_1m` `:388` with cascade `:408-421`; cron `sync_1m` `:734-740` (`second=12`). `sync_verify_cascade` `:578-631` compares only 5m REST against cascade (log `no_cascade_5m_bars_in_window` `:605-607`), so the 1d cascade does not touch it.
- `core/infra/exness/exness_adapter.py:39-43,60`: `cutoff = exness_bar_start(now, interval)` and `b.datetime < cutoff` (holds). `exness_session_calendar_adapter.py:8-9` (grid comment), `:84-89` (`exness_bar_start`, 1w = Sunday), `:170-171` (`session_date` = UTC date), `:180-183` (`session_open` = midnight). All hold.
- `BarRepository.find(self, symbol: str, interval: Interval, start_date=None, end_date=None, limit: int = 5000) -> list[Bar]` `bar_repository.py:100-128`: inclusive `$gte`/`$lte`, **sorted descending** with a limit.
  - `get_latest` `:162`; `upsert_bar(bar, *, source)` `:42-98`.
  - Indexes `:233-246`: unique `ix_ohlcv_symbol_interval_datetime` `(symbol, interval, datetime)`, which covers an HTF `find`/`stream` by range; sparse `ix_ohlcv_symbol_interval_session_date`.
- Calendar helpers for "closed before instant t":
  - Port `core/domain/market_data/trading_calendar_port.py:13-44`: `calendar_id, is_open, session_date, session_open, session_close, previous_close, sessions, trading_minutes, bar_start(instant, interval), periods_per_year`. It has **no bucket-end method**.
  - Every bucket has a fixed length. `get_bar_start` `core/domain/bar/services/bar_builder_domain_service.py:13-34` uses 1d = UTC midnight and 1w = Monday; `exness_bar_start` uses 1w = Sunday. So bucket end = `bar.datetime + INTERVAL_SECONDS[interval]`, and "closed before t" ⇔ `bar.datetime + step <= t`, the test `_closed_bars` already uses (`strategy_app_service.py:289`).
  - There are two `INTERVAL_SECONDS` maps: `core/common/constants.py:42-50` (str keys, used by the engine) and `core/domain/shared/value_objects.py` (Interval keys, used by domain).
  - The calendar factory is `core/infra/calendars/trading_calendar_factory.py:42` `for_symbol(composite)`.
- Tests:
  - `tests/app_test/market_data/test_cascade_aggregator.py` (544 lines; `CALENDAR = Continuous24x7Calendar()` :25, `EURUSD, XAUUSD, _ = EXNESS_CALENDARS` :26): class `TestCascadeTimeframesDependOnTheCalendar` `:511-544` (holds), with `test_a_continuous_market_cascades_its_daily_bar` :512, `test_a_session_market_fetches_its_daily_bar_instead` :516 and `test_a_session_symbol_never_upserts_a_cascaded_daily_bar` :523.
  - `tests/engine_test/market_data/test_backfill_daily_mode.py`: header `:1-3`; `test_session_calendar_daily_backfill_goes_direct` :73, `test_crypto_daily_backfill_still_cascades` :84, `test_an_explicit_cascade_is_overridden_audibly` :97, `test_auto_mode_is_overridden_silently` :114 (holds). After the delete, the import `CALENDAR_EXNESS_FX` `:16` may become unused.
- Not re-verified by this scout: `integrity_jobs.py:58-62,79-95,131-154` (advice references).

## 7. Redis (trader to Redis to api)

- `Cache` `core/infra/persistence/redis.py` (109 lines): `connect`, `get_client` `:39`, `get(key)` `:44-57` (JSON), `mget` `:59-64`, `set(key, value, ttl)` `:66-85` (JSON, `ex=ttl`), `delete` `:87`, `delete_pattern` `:93`, `exists` `:107`. It has **no list/ring helpers** (LPUSH/LTRIM). [INFERENCE] A bounded ring needs `get_client()` or a new method.
- Key templates `core/common/constants.py:20-32`: `CACHE_KEY_QUOTE_LATEST="quote:latest:{symbol}"` `:22`, `CACHE_KEY_BAR_CURRENT="bar:current:{symbol}:{interval}"` `:23`, `CACHE_KEY_OHLCV` `:24`, `CACHE_KEY_DATA_LAG` `:25`; TTLs `:28-32`.
- Writers:
  - Trader: `bar:current` by `engine/market_data/app_services/bar_app_service.py:365-379` (flush throttled, adds `last_update`). It is gated by `publishes_current`, set False in standby at `app/roles.py:165`.
  - Trader: `quote:latest` by `engine/market_data/app_services/quote_app_service.py:57-58`.
  - Worker: `data_lag` by `sync_jobs.py:670-672`.
- Readers (api):
  - `BarAppService.get_current_bar` `bar_app_service.py:381-395` (Redis, then Mongo `get_latest` fallback), used by SSE `app/routes/market_data.py:195-206` through `poll_stream` (`app/common/sse_poll.py:15`) and by `app/routes/market_data_quotes.py:39-47`.
  - `quote:latest` read directly from an injected `Cache` in the route `market_data_quotes.py:74-78`.
  - `engine/market_data/quotes_service.py:43-44`; `engine/market_data/data_lag_service.py:163`.
- Live subscription state reaches the api through Mongo only (`actual_state` written by the reconcile loop, `strategy_reconcile_app_service.py:99-100`). There is no strategy or subscription key in Redis today. `StrategyAppService` has no `Cache` dependency (`app/di/services.py:122-153`).
- Cleanup precedent: `TrackedSymbolService.remove` deletes the Redis patterns per symbol (`engine/market_data/tracked_symbols_service.py:130-139`). [INFERENCE] A per-subscription snapshot key needs deleting in `remove_symbol` or through a TTL.
- [INFERENCE] Routes only write Mongo and the trader owns the brokers (`strategy_reconcile_app_service.py:20-23`). A manual close or cancel from the api therefore needs an api-to-trader command channel (for example a desired-action field in Mongo read by the reconcile loop). The api process cannot call the broker.

## 8. Quality gates

- import-linter `pyproject.toml:73-127`, **6 contracts**, all KEPT (`uv run lint-imports`, 234 files, 1123 deps):
  1. layers app > engine > core;
  2. `core.domain` must not import `core.infra`;
  3. `engine.backtest` and `engine.live` independent;
  4. `engine.strategy`, `engine.execution`, `engine.market_data` must not import `engine.backtest` or `engine.live`;
  5. no `fastapi` in core or engine;
  6. no `bson`.
  - [INFERENCE] By contract 4, a shared HTF cache used by live and backtest belongs in `engine.strategy` or `engine.market_data`.
- Code metrics: `pyproject.toml:130-132` `max_tiny_share = 0.4810`, `max_delegations = 73`. Current values are 0.4809 and 73 (trap 7). The definitions are in `scripts/code_metrics.py` (long-function threshold `_LONG_FUNCTION_LINES = 60` `:12`); tests in `tests/scripts/test_code_metrics.py`. `docs/code-standards.md:144` says done = tests, Ruff, Pyright, import-linter and the ratchet pass (Ruff and Pyright are not in CI).
- justfile: `test` `:64-65` runs `{{python}} -m pytest`; `test-tz` `:70-75` runs the suite under UTC, Asia/Ho_Chi_Minh and America/Chicago.
- CI `.github/workflows/cicd.yml`:
  - Triggers on push to master/develop, ignoring docs, plans and `*.md` `:3-11`.
  - Job `tests` uses the `ubuntu-24.04` TZ matrix `:20-30`, then: `uv sync --frozen` `:40-41`, zone check `:45-47`, `uv run lint-imports` `:49-50`, `uv run python scripts/code_metrics.py --ratchet` `:52-53`, `uv run pytest tests/ -q` `:55-56`.
  - Then build-app, build-web, prune, and deploy to the VPS (`deploy/vps/10-deploy.sh`, `11-verify.sh` `:239-247`).
- pytest config `pyproject.toml:62-71`: `asyncio_mode="auto"`, `--import-mode=importlib`, `testpaths=["tests"]`.
- Tests layout: `tests/{app_test/{integration,market_data,unit},backtest_test/{domain,engine},core_test/{infra/{binance,brokers/exness,calendars,exness,market_data,persistence/backtest,scheduling},unit/domain/{backtest,bar,market_data,order,position,risk,shared,strategy/patterns,subscription,sync_status,trading},unit/common},engine_test/market_data,scripts/rubric,http,manual}`.
- Fixtures:
  - `tests/conftest.py` puts the workspace on `sys.path` `:19-22`, has the prod-host guard `207.148.79.60` `:25,47-56`, seeds env defaults `:32-44`, and starts session-scoped `mongo_container` (`mongo:7.0`) `:69-72` and `redis_container` (`redis:7.2-alpine`) `:75-78`. Docker is required.
  - Per suite: `tests/core_test/conftest.py` (`host_timezone` :26, `settings` :58, `event_bus` :83, `database` :88, `cache` :108), `tests/backtest_test/conftest.py` (`settings` :14, `database` :39), `tests/engine_test/conftest.py` (`settings` :11), `tests/app_test/conftest.py` (`settings` :11), `tests/app_test/integration/conftest.py` (`app_client` :15).

## Unresolved questions

1. What scalar shape should the unique key take (`intervals_key` string or another form)? It is needed because of trap 1. This is the owner's or planner's call.
2. How does a manual close or cancel travel from the api to the trader (Mongo command field, a new collection, or something else)? The repo has no channel today.
3. How should EXIT size in a backtest, given that `PositionAppService` is not started there (trap 5)? Options are to read the paper broker's positions or to start the tracker in the sandbox.
4. Should the takeover rule that drops paper positions without SL/TP (`strategy_app_service.py:157-165`) change for exit-only strategies?
5. Should `docs/swing-pivot-key-level.md` and the rubric script be deleted, or kept with the web Engulf overlay?
