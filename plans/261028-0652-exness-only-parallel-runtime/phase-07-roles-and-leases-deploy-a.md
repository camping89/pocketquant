---
phase: 7
title: "Roles and leases inside one process (Deploy A)"
status: pending
priority: P1
effort: "2d code + 1 deploy (D-4) + 11 min prod probe"
dependencies: [1, 6]
---

# Phase 07: Roles and leases inside one process (Deploy A)

## Goal

Ship every role mechanism while prod still runs one `app` container with all three roles: `APP_ROLES` replaces `enable_jobs`; the worker runs the scheduler only while it holds the Mongo `worker` lease; the trader warms up in standby, takes the `trader` lease, then connects brokers, and on SIGTERM drains at a 1m boundary before it releases. Prove it in CI with the real lifespan, in prod (D-4), and with a second trader and a second worker started beside it (D17). Deploy B (Phase 08) then stops this `app`, which drains and hands both leases to the new containers.

## Context (verified on `develop` @ 453e8e90; Phases 02-06 shift line numbers, so find each symbol by name)

- Lifespan order today: `recover_orphan_backtests` `src/pocketquant/app/main.py:61`, `recover_orphan_jobs` `:62`, `bootstrap_live_instances` `:63`, `start_quote_feed` `:65`, `start_jobs` `:66`; `finally` at `:76-86`. Phase 02 adds `start_loop_lag_probe(app)` right after `assert_utc_runtime()` and `await stop_loop_lag_probe(app)` as the first `finally` statement, and `/health` reads `getattr(app.state, "loop_lag_max_s", 0.0)` (`health_check` is a closure over `app`). Phase 05 starts the bar close timer inside `start_quote_feed`. Phase 06 adds `await (await container.get(StrategyAppService)).take_over()` right after `bootstrap_live_instances`.
<!-- Red team 2026-10-28: #4 #5 #12 -->
- Names from Phase 06 (`engine/strategy/strategy_app_service.py`): `trading_until: datetime | None` (default far future; `None` = no new entries), `_signal_tasks: dict[str, asyncio.Task[None]]` (venue signal tasks), `_running_bar_handlers` (bar handlers running inline, such as paper fills), `start_strategy` connects a broker only while `trading_until` is in the future, `_process_signal` logs `strategy.signal_discarded` when `trading_until is None` with a reason the engine switches (starts `standby` at DEBUG; `take_over()` switches it to `drain`, `cancel_pending_signals()` to `lease`, both at INFO) and WARNING `strategy.entry_skipped reason=lease` when `now >= trading_until`, `cancel_pending_signals() -> int` cancels the signal tasks that have not reached the send, `stop(timeout_s)` (the timeout is required on every call) gathers `_signal_tasks` bounded by it before disconnecting brokers, `take_over()` reloads pending orders and positions, restores paper brokers and directions, connects the brokers of running strategies and logs `strategy_engine.took_over`. `StrategyAppService` requires `bar_repository`, `calendar_factory` and `trade_repository`. Its tests `test_standby_discards_the_signal` and `test_an_expired_lease_skips_the_entry` (`tests/engine_test/test_strategy_entry_guards.py`) already cover the order fence; this phase adds the lease that drives `trading_until`.
- Seams from Phases 04-05 (use these names; add no second seam):
  - Phase 04: `submit_order(order, *, deadline=...)` on the port, paper, Exness and `OrderAppService.submit`; the engine passes `trading_until` as the deadline, re-checked after `_open_lock` and after the pacer wait right before the send, with no resend past it. This phase only sets `trading_until`.
  - Phase 05: `BarAppService.last_closed_boundary` (every bar of boundary B published and the publish returned; the drain waits for `>= B`) and `BarAppService.publishes_current` (defaults `True` for the single-process build; the trader sets it `False` in standby, `True` at takeover, `False` after release or loss).
- `enable_jobs: bool = True` at `src/pocketquant/core/config.py:64`; settings ignore unknown keys (`extra="ignore"`, `config.py:44`). With `extra` not `forbid`, pydantic-settings 2.12 still copies unknown `.env` keys into the input data (`DotEnvSettingsSource.__call__`); unknown process environment keys are not copied, so the retired-key check reads `os.environ` as well.
- The DI scheduler provider starts the scheduler when `enable_jobs` (`src/pocketquant/app/di/infrastructure.py:95-105`). `JobScheduler.shutdown` is a no-op before `initialize` (`src/pocketquant/core/infra/scheduling/scheduler.py:137-141`); `scheduler.started` is logged at `scheduler.py:93`. `JobScheduler` has no `pause` today.
- `start_jobs` registers sync jobs, starts `LiveTradeCollector` and the reconcile task (`src/pocketquant/app/main_extensions.py:211-238`); boot sweeps at `main_extensions.py:132-141` and `:144-158`; `/health` at `main_extensions.py:372-380` returns 200 whatever its body says; `_REPO_TYPES` at `:109`; `_cancel` at `:175-182`. `_tracked` (`src/pocketquant/engine/market_data/app_services/sync_jobs.py:149-183`) catches only `Exception`, so a cancelled job leaves its `job_history` row `running`.
- `StrategyReconcileAppService.bootstrap` loads instances only (`src/pocketquant/engine/live/strategy_reconcile_app_service.py:75-88`).
- Exness drain state: `_inflight` `exness_broker_adapter.py:116`, `_pending_ack` `:117`, `_needs_snapshot` `:122`; `fills_async` on the port at `src/pocketquant/core/domain/brokers/broker_port.py:23`.
- Backtest runs: `execute_and_persist` at `src/pocketquant/engine/backtest/backtest_execution_service.py:71-90`; sweep `mark_orphaned_started_as_failed` at `src/pocketquant/core/infra/persistence/repositories/backtest_repository.py:92-107` fails every `started` row; the start field is `started_at` (`core/domain/backtest/entities.py:28`).
<!-- Red team 2026-10-28: #5 #10 -->
- `enable_jobs` callers: `infrastructure.py:100,104`, `main_extensions.py:169,214,224,394`, `strategy_reconcile_app_service.py:79`, `core/config.py:64`, `tests/app_test/conftest.py:37`, `tests/backtest_test/conftest.py:40`, `tests/core_test/conftest.py:94`, `tests/core_test/infra/market_data/conftest.py:26`, `tests/engine_test/conftest.py:38`, `tests/app_test/integration/app_factory.py:4,40`, `tests/app_test/integration/test_declarative_subscription_state_api.py:5`, `justfile:36`. Task 7.1 edits all of them so its Verify can pass. Docs and `README.md` mentions move in Phase 09.
- Config files: `../pocketquant-config/vps/default/.env:31` (`ENABLE_JOBS=true`), `local/remote-db.env:42`, `local/remote-db-local-redis.env:3,47`, `local/all-local.env:34`, `README.md:83` of that repo.
- uvicorn waits for open connections (SSE) before lifespan shutdown unless `--timeout-graceful-shutdown` is set (researcher report Q3); the `app` command has no such flag today (`deploy/compose.prod.yml:64`). Without it the drain never runs before SIGKILL, so Task 7.6 adds it.
- `restart: unless-stopped` on `app` (`deploy/compose.prod.yml:61`) brings a process back after a self-SIGTERM.
- Prod logs use `LOG_FORMAT=console` (`../pocketquant-config/vps/default/.env:27`), rendered by `ConsoleRenderer(colors=True, exception_formatter=structlog.dev.plain_traceback)` (`src/pocketquant/core/common/logging/setup.py:71`; Phase 02 Task 2.6 removed the traceback locals): lines read `event_name key=value` wrapped in ANSI colour codes. Every prod log grep below first strips them with `sed 's/\x1b\[[0-9;]*m//g'`.
- On the VPS the compose file and `.env` live in `/opt/pocketquant/deploy` (`.github/workflows/cicd.yml:229-240`, `deploy/vps/10-deploy.sh:12-14`); `10-deploy.sh:61-62` prints a 30-line log tail into the public Actions log on a failed health wait.
<!-- Red team 2026-10-28: #2 -->
- OOM rule (D31, plan.md Conventions): `reports/machine-baseline.md` holds one line `oom_baseline=<boot_id> <oom_kill>`. A reading stops the plan when the boot id differs, the `oom_kill` counter is higher, or `docker inspect -f '{{.State.OOMKilled}}' pocketquant-app` is `true`. Before Phase 08 the check runs inline (the helper set does not exist yet). Memory, swap and loop lag are recorded only.
- Lease parameters (plan consensus): collection `leases`, UUIDv7 `_id`, unique `name`, TTL 30 s, renew 10 s, standby poll 0.5 s, order margin 5 s, owner `hostname:pid` (a container's hostname is its short id, `docker inspect -f '{{.Config.Hostname}}'`). Drain (shared contract): shutdown start S = the first statement of the lifespan `finally`; B = the next 1m boundary after S; release only when `last_closed_boundary >= B` and `inflight_count() == 0`, polled from B until B+30 s; one retry at the next boundary; hard deadline S+150 s; `engine.stop()` bounded by S+160 s; trader grace 180 s (SIGTERM + 10 s uvicorn graceful + 160 s < 180 s).

## Entry gate

Run from `D:/w/_me/algotrading/pocketquant`:

1. `git status --porcelain -- src web deploy tests scripts docs` prints nothing.
2. `grep -c "^Result: PASS$" plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-tick-sessions.md` prints `1`.
   - If the file holds `Result: FAIL`, read its `Owner fallback:` line (Phase 01 Task 1.5 step 4 wrote it). With `Owner fallback: pending (...)`: ask the owner (below), then exit with the NOT_YET block (`NOT_YET: spike FAIL, owner fallback pending`). With `Owner fallback: second-account`: exit with the NOT_YET block (`NOT_YET: spike FAIL, owner chose second-account; this plan needs a revision for the standby feed before Phase 07`); do not ask again.
     > Recommended: dùng một tài khoản Exness thứ hai cho feed của trader standby (D24) — spike cho thấy hai phiên ticks trên cùng một key làm nhiễu prod. Câu hỏi: Spike ở Phase 01 trả về FAIL. Anh chọn phương án dự phòng nào trước Phase 07: (1) tài khoản Exness thứ hai cho trader standby, hay (2) phương án khác (xin ghi rõ)?
   - If the file is missing: Phase 01 has not run; exit with the NOT_YET block.
3. `git fetch origin -q && git grep -c "async def take_over" origin/master -- src/pocketquant/engine/strategy/strategy_app_service.py` prints `origin/master:src/pocketquant/engine/strategy/strategy_app_service.py:1`.
4. `test "$(GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --workflow cicd.yml --limit 1 --json conclusion,headSha -q '.[0].conclusion + " " + .[0].headSha')" = "success $(git rev-parse origin/master)" && echo deployed` prints `deployed`.
<!-- Red team 2026-10-28: #2 #4 #10 -->
5. `grep -c "trading_until\|_signal_tasks" src/pocketquant/engine/strategy/strategy_app_service.py` prints a number `>= 2`; `git grep -l "last_closed_boundary" -- src/pocketquant/engine/market_data/app_services/bar_app_service.py | wc -l` prints `1`; `grep -c "^oom_baseline=" plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md` prints `1`.

On any miss: edit nothing, spawn no `kongming`, leave the phase pending, run `rm -f .cache/ssh/vps_key`, and end with exactly:
```
Status: BLOCKED
NOT_YET: <which gate line missed>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261028-0652-exness-only-parallel-runtime --from 07 after <UTC time>
```
**Resume rule.** On a resumed run, run each task's Verify first; a task whose Verify already passes is done and is skipped.

## Files to create/modify

<!-- Red team 2026-10-28: #3 #4 #7 -->
Create: `src/pocketquant/core/infra/persistence/repositories/lease_repository.py`, `src/pocketquant/app/roles.py`, `tests/core_test/unit/common/test_settings_app_roles.py`, `tests/core_test/infra/persistence/test_lease_repository.py`, `tests/app_test/unit/test_roles.py`, `tests/app_test/unit/test_trader_drain.py`, `tests/app_test/integration/test_worker_role.py`, `tests/app_test/integration/test_trader_role.py`, `tests/app_test/integration/test_trader_lifespan_handover.py`, `tests/app_test/integration/test_health_role_fields.py`, `tests/engine_test/test_trader_fence.py`, `tests/backtest_test/test_backtest_execution_heartbeat.py`, `plans/261028-0652-exness-only-parallel-runtime/reports/deploy-a-roles-and-leases.md`.

Modify: `src/pocketquant/core/config.py`, `src/pocketquant/core/common/constants.py`, `src/pocketquant/core/infra/scheduling/scheduler.py`, `src/pocketquant/app/di/infrastructure.py`, `src/pocketquant/app/main.py`, `src/pocketquant/app/main_extensions.py`, `src/pocketquant/engine/live/strategy_reconcile_app_service.py`, `src/pocketquant/engine/strategy/strategy_app_service.py`, `src/pocketquant/core/domain/brokers/broker_port.py`, `src/pocketquant/core/infra/brokers/exness/exness_broker_adapter.py`, `src/pocketquant/engine/backtest/backtest_execution_service.py`, `src/pocketquant/core/infra/persistence/repositories/backtest_repository.py`, `src/pocketquant/engine/market_data/app_services/sync_jobs.py`, the five conftests and `tests/app_test/integration/app_factory.py`, `tests/app_test/integration/test_declarative_subscription_state_api.py`, `tests/core_test/infra/persistence/test_stale_recovery.py`, `tests/backtest_test/test_backtest_single_run_direct_task.py`, `tests/engine_test/test_strategy_reconcile_service.py`, `tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py`, `justfile`, `CLAUDE.md`, `deploy/Dockerfile`, `deploy/compose.prod.yml`, `deploy/vps/10-deploy.sh`; in `../pocketquant-config`: `vps/default/.env`, `local/remote-db.env`, `local/remote-db-local-redis.env`, `local/all-local.env`, `README.md`.

## Tasks

<!-- Added 2026-10-29 after the Phase 06 checkpoint -->
**Corrections (2026-10-29).** Verified on `develop` @ d10c1c3d after Phase 06 (deployed as 3905ff6b). Apply these over the Context and Tasks below.

Line numbers (find by name when they drift again): `main.py` lifespan body is `:55-74` (`recover_orphan_backtests :65`, `recover_orphan_jobs :66`, `bootstrap_live_instances :67`, `take_over :68`, `register_health_checks :69`, `start_quote_feed :70`, `start_jobs :71`), `finally :81-92`; `enable_jobs: bool = True` is `config.py:57`, `extra="ignore"` is `:37`; `get_job_scheduler` is `infrastructure.py:95-105`; `JobScheduler.shutdown` is `scheduler.py:150-154`, `scheduler.started` is logged at `:90`; `start_jobs` is `main_extensions.py:242-269`, `/health` is `:392-401`; `_inflight :121`, `_pending_ack :122`, `_needs_snapshot :127` in `exness_broker_adapter.py`; `fills_async` is `broker_port.py:24`; the Dockerfile comment is `deploy/Dockerfile:56-57` and `CMD` is `:58` (Task 7.6 step 2); the formatter line is `setup.py:74`. `enable_jobs` callers in `main_extensions.py` are `:169` (docstring), `:245-246` (docstring), `:255` (`if not settings.enable_jobs`), `:415` (comment); Task 7.1 step 3 uses these.

Phase 06 facts the tasks rely on: `_process_signal(strategy, signal, event, signal_at, published_at)` takes five arguments; `cancel_pending_signals()` itself logs INFO `strategy.signal_discarded reason=lease` once per cancelled task; `take_over()` holds the engine `_lock` for its whole body and sets `_discard_reason = "drain"` before `_take_over` arms `trading_until`, so one `reason=drain` discard may be logged during a takeover; the DI generator already calls `engine.stop(timeout_s=5.0)` on container close (`services.py:162-163`), and `stop()` returns at once when the engine is not running, so `hand_over` and `_on_lost` may stop the engine first. Entry-guard tests that cover the fence: `test_standby_discards_the_signal`, `test_a_drained_engine_discards_at_info`, `test_the_order_deadline_is_trading_until`, `test_an_expired_lease_skips_the_entry` (`tests/engine_test/test_strategy_entry_guards.py`); their harness is `_engine()` (`_AlwaysLong`, `_Factory`, `_DeadlineBroker(PaperBrokerAdapter)`, `_Repo`, `NoStoredBars`, `NoClosedTrades`).

Task 7.1 step 7: verified with pydantic-settings 2.12.0 that an unknown `.env` key reaches a `mode="before"` validator while an unknown process-environment key does not; the `os.environ` read stays.

Task 7.3 step 4: `_tracked` registers `task = asyncio.current_task()` and adds it only when not `None`, so pyright stays at its baseline.

Task 7.4 step 2 (optional): `start_strategy` may connect on `self.trading_until is not None` alone; the order fence is at the send.

Task 7.4 step 4, `_take_over`: call `await collector.start()` before `await engine.take_over()`. `take_over()` connects the paper brokers, whose `connect` subscribes their SL/TP handler to bars, and keeps awaiting afterwards; a paper exit on a bar closing in that window would publish a `TradeClosedEvent` with no collector subscribed. The collector only records closed trades, so starting it first changes nothing else. Keep the `trader.takeover` log, `bars.publishes_current = True`, then `collector.start()`, then `engine.take_over()`, then the reconcile task, then `trading_until`.

Task 7.4 step 5: remove the now-unused `StrategyAppService` import from `main.py` with the `take_over()` line (ruff F401).

Task 7.4 step 9, `test_trader_role.py`: the fixture drops `leases`, `orders`, `positions` and `trades` before the foreign lease doc is inserted, or the three count assertions in `test_standby_trader_does_not_trade` see rows left by other app tests.

Task 7.4 step 9, `test_trader_lifespan_handover.py`: `pocketquant.app.main` builds the app at import (`main.py:121`, `app = create_app()` → `get_settings()`), and neither the local checkout nor the CI test job has a `.env`, so a top-level import fails collection. Inside the test, before anything else: `monkeypatch.setenv` every required `Settings` field from the `settings` fixture (`APP_NAME`, `APP_VERSION`, `ENVIRONMENT`, `MONGODB_URL`, `MONGODB_DATABASE`, `MONGODB_MIN_POOL_SIZE`, `MONGODB_MAX_POOL_SIZE`, `REDIS_URL`, `REDIS_CACHE_TTL`, `LOG_LEVEL`, `LOG_FORMAT`), call `get_settings.cache_clear()`, then `main = importlib.import_module("pocketquant.app.main")` and patch `main.get_settings` as written. Two more facts for the same test: a `hitnrun2` instance never signals from one live bar with no stored warm-up, so `monkeypatch.setitem(STRATEGY_REGISTRY, "hitnrun2", _AlwaysLong)` (copy `_AlwaysLong` from the entry-guard harness) before the lifespans are entered, and publish the triggering `BarCompletedEvent` with `bar_end` within 10 s of real wall time (the lease uses `datetime.now(UTC)`, so this test cannot use simulation time). The simplest `SlowAsyncFillBroker` subclasses `PaperBrokerAdapter` and overrides only `fills_async = True`, `submit_order` and `inflight_count`, so `get_balance`, `normalize_quantity`, `subscribe_trades` and `subscribe_order_updates` come for free.

Task 7.4 step 9, `test_trader_fence.py::test_standby_engine_connects_no_broker_on_start`: the copied `_engine()` helper calls `start_strategy` with the default `trading_until`; build the engine, set `trading_until = None`, then `load_strategy` and `start_strategy` (give the helper a `trading_until` parameter or inline the three calls).

Task 7.8 Verify: `docker logs --since 15m` counts only lines newer than 15 min; run the Verify within 15 min of the container start printed by `docker inspect -f '{{.State.StartedAt}}' pocketquant-app`, or widen `--since` to that start time.

Task 7.9: the compose project is `pocketquant-prod` (`deploy/compose.prod.yml:1`), so `--network pocketquant-prod_backend` is right. If the prod `app` loses its lease during the probe window, the probe trader takes over, trades paper until its 600 s timeout, drains and releases, and the restarted `app` takes the lease back; `app_lost=0` in the Verify is what proves this did not happen.


### Task 7.1 — `APP_ROLES` replaces `enable_jobs`

**Goal:** one setting names the roles a process runs, its default runs no lease-holding role, and a leftover `ENABLE_JOBS` stops startup; `enable_jobs` is gone.
**Target files and symbols:** `Settings` in `core/config.py`; `get_job_scheduler` in `app/di/infrastructure.py`; `bootstrap_live_instances`, `start_jobs` and the `list_jobs` comment in `main_extensions.py`; `StrategyReconcileAppService.bootstrap` docstring; the conftests, `app_factory.py`, `test_declarative_subscription_state_api.py`, `justfile`.
**Steps:**
<!-- Red team 2026-10-28: #5 -->
1. In `core/config.py` delete `enable_jobs: bool = True` and add, in its place, a module constant `APP_ROLE_NAMES = ("api", "worker", "trader")` (above the class) and:
   - field `app_roles: str = "api"` with a comment: "Roles this process runs: api (routes, backtests), worker (scheduler and jobs under the worker lease), trader (quote feed, strategies, brokers under the trader lease). The default takes no lease, so a copied local profile never contends for a prod lease; compose sets the roles per service."
   - a `@field_validator("app_roles")` classmethod (import `field_validator`, `model_validator` from `pydantic`) that splits on commas, strips blanks, raises `ValueError("APP_ROLES must list api, worker or trader; got ...")` when the set is empty or holds a name outside `APP_ROLE_NAMES`, and returns `",".join(r for r in APP_ROLE_NAMES if r in names)` (canonical order).
   - a `@model_validator(mode="before")` classmethod `_refuse_retired_job_switch(cls, data)`: when `"enable_jobs"` is a key of `data` (lower-cased; `.env` extras arrive here) or of `os.environ` (lower-cased), raise `ValueError("ENABLE_JOBS is retired; set APP_ROLES (api, worker, trader) instead")`; else return `data`. Comment: "A silently ignored ENABLE_JOBS=false would let a local process take a prod lease."
   - `@property def roles(self) -> frozenset[str]: return frozenset(self.app_roles.split(","))`.
2. `get_job_scheduler`: drop the `settings` argument and both `if settings.enable_jobs` blocks; it builds `JobScheduler(history_repo=history_repo)`, yields it, then calls `scheduler.shutdown(wait=True)` (a no-op when never started or already shut down). Comment: "The worker role starts the scheduler after it takes the worker lease."
<!-- Red team 2026-10-28: #5 #10 -->
3. The five other `src` callers (moved here from Task 7.4 so this Verify passes; Task 7.4 deletes `start_jobs`):
   - `main_extensions.py:169` (`bootstrap_live_instances` docstring): replace the last sentence with "Runs in the trader role only."
   - `main_extensions.py:214`: "All three run only in the worker role, so the test/CLI profile (`APP_ROLES=api`) runs none of them."; `:224`: `if "worker" not in settings.roles:`. Until Task 7.4 removes `start_jobs` nothing starts the scheduler; no deploy happens in between.
   - `main_extensions.py:394` comment → "and the route works in every role".
   - `strategy_reconcile_app_service.py:79`: drop "— even when the reconcile loop is gated off (``enable_jobs=false``) —" so the sentence reads "Runs once at startup, so instances exist before the first tick and it never logs spurious ``missing_instance`` warnings."
4. In the five conftests replace `enable_jobs=False,` with `app_roles="api",`.
5. Docstrings: `app_factory.py:4` → "e.g. with other `app_roles`"; `:40` → "background jobs belong to the worker role and do not run here"; `test_declarative_subscription_state_api.py:5` → "``app_roles="api"`` so no reconcile loop is live".
6. `justfile:34-36` comments become: "# Start backend on port 41921 with the roles in APP_ROLES (default api: routes only)." / "# Never --workers N: the worker and the trader act only while they hold their Mongo lease." / "# Full runtime on a local database: APP_ROLES=api,worker,trader in .env (all-local profile only)."
7. Write `tests/core_test/unit/common/test_settings_app_roles.py` (builds `Settings(_env_file=None, ...)` with the required fields used in `tests/core_test/conftest.py:80-94`, plain strings, no containers):
   - `test_app_roles_default_is_api_only`: `roles == frozenset({"api"})` and `app_roles == "api"`.
   - `test_app_roles_parses_a_comma_list`: `"worker, api"` → `app_roles == "api,worker"`.
   - `test_app_roles_rejects_an_unknown_role`: `"api,bogus"` raises `pydantic.ValidationError`.
   - `test_app_roles_rejects_an_empty_list`: `" , "` raises `pydantic.ValidationError`.
   - `test_retired_job_switch_in_the_environment_fails`: `monkeypatch.setenv("ENABLE_JOBS", "false")` → `pydantic.ValidationError` whose text names `APP_ROLES`.
   - `test_retired_job_switch_in_the_env_file_fails`: a `tmp_path` `.env` with the required keys plus `ENABLE_JOBS=false`, `Settings(_env_file=str(path))` → `pydantic.ValidationError`.
**Success criteria:** `enable_jobs`/`ENABLE_JOBS` appear in `src`, `tests` and `justfile` only in the retired-key guard and its test; the six tests pass.
**Verify:** `git grep -l -i --untracked "enable_jobs" -- src tests justfile; uv run python -m pytest tests/core_test/unit/common/test_settings_app_roles.py -q 2>&1 | tail -1` → exactly the two lines `src/pocketquant/core/config.py` and `tests/core_test/unit/common/test_settings_app_roles.py`, then a line starting with `6 passed`.

### Task 7.2 — `LeaseRepository`

**Goal:** one conditional upsert takes or renews a named lease; the unique `name` index lets only one contender win.
**Target files and symbols:** new `core/infra/persistence/repositories/lease_repository.py` (`LeaseRepository`); `COLLECTION_LEASES` in `core/common/constants.py`; `_REPO_TYPES` in `main_extensions.py`; `InfrastructureProvider` in `app/di/infrastructure.py`.
**Steps:**
1. `constants.py`: add `COLLECTION_LEASES = "leases"` after `COLLECTION_SAFEGUARDS`.
2. Create the repository, with the module-level `logger = get_logger(__name__)` that `trade_repository.py:15` uses (module docstring: "One document per role name says which process may act. Acquire and renew are one conditional upsert; the unique name index makes a second insert fail, so two contenders never both win. Wall-clock time: all roles share one host clock."):
   ```python
   class LeaseRepository(BaseRepository):
       _collection_name = COLLECTION_LEASES

       async def acquire(self, name: str, owner: str, ttl_s: float) -> datetime | None:
           now = datetime.now(UTC)
           expires_at = now + timedelta(seconds=ttl_s)
           try:
               await self._collection().update_one(
                   {"name": name, "$or": [{"expires_at": {"$lt": now}}, {"owner": owner}]},
                   {"$set": {"owner": owner, "expires_at": expires_at, "renewed_at": now},
                    "$setOnInsert": {"_id": generate_id_str()}},
                   upsert=True,
               )
           except DuplicateKeyError:
               return None
           return expires_at

       async def release(self, name: str, owner: str) -> None:
           now = datetime.now(UTC)
           result = await self._collection().update_one(
               {"name": name, "owner": owner}, {"$set": {"expires_at": now, "released_at": now}})
           if result.modified_count:
               logger.info("lease.released", name=name, owner=owner)

       async def get(self, name: str) -> dict[str, Any] | None:
           return await self._collection().find_one({"name": name})

       async def ensure_indexes(self) -> None:
           await self._collection().create_index("name", unique=True, name="ux_leases_name")
   ```
3. Add `LeaseRepository` to `_REPO_TYPES` and `lease_repository = provide(LeaseRepository, scope=Scope.APP)` beside `safeguards_repository` in `infrastructure.py`.
4. Write `tests/core_test/infra/persistence/test_lease_repository.py` (`pytestmark = pytest.mark.integration`, fixture as in `test_stale_recovery.py:20-28`, dropping `leases` first):
   - `test_two_contenders_one_acquires`: `asyncio.gather` of `acquire("trader","a",30)` and `acquire("trader","b",30)` → exactly one non-`None`; `count_documents({"name":"trader"}) == 1`.
   - `test_holder_renews_with_a_later_expiry`: two acquires by `a` → second expiry > first.
   - `test_expired_lease_goes_to_the_other_owner`: `a` with `ttl_s=0.2`, `await asyncio.sleep(0.3)`, `b` → non-`None`, doc `owner == "b"`.
   - `test_release_sets_released_at_and_lets_the_other_in`: `a` acquires, `release("trader","a")` inside `structlog.testing.capture_logs()` logs exactly one `lease.released` with `name == "trader"` and `owner == "a"`, doc `released_at` is not `None`, `b` acquires non-`None`.
   - `test_release_by_a_non_owner_changes_nothing`: `a` acquires, `release("trader","b")` logs no `lease.released`, `b` acquire → `None`.
   - `test_document_has_uuid7_id_and_unique_name_index`: `UUID(doc["_id"]).version == 7`; `index_information()["ux_leases_name"]["unique"] is True`.
**Success criteria:** six tests pass against the test Mongo.
**Verify:** `docker ps >/dev/null && uv run python -m pytest tests/core_test/infra/persistence/test_lease_repository.py -q 2>&1 | tail -1` → starts with `6 passed`.

### Task 7.3 — `hold_lease` and the worker role

**Goal:** one function holds a lease for any role and reports `held` only after the takeover succeeded; the worker starts the scheduler only after it holds the `worker` lease and, on stop, lets running jobs finish before it releases.
**Target files and symbols:** new `app/roles.py` (`hold_lease`, `start_worker`, `stop_worker`, constants); `JobScheduler.pause`; `_tracked`, `wait_running_jobs` and the `register_sync_jobs` docstring in `sync_jobs.py`.
**Steps:**
<!-- Red team 2026-10-28: #4 -->
1. Create `app/roles.py` with module docstring "Lease-holding roles. The worker runs the scheduler and the trader sends orders, each only while it holds its Mongo lease; a second copy waits in standby." Module constants `LEASE_TTL_S = 30.0`, `LEASE_RENEW_S = 10.0`, `LEASE_RETRY_S = 1.0`, `LEASE_POLL_S = 0.5`, `ORDER_MARGIN_S = 5.0`, `DRAIN_WINDOW_S = 30.0`, `DRAIN_DEADLINE_S = 150.0`, `STOP_DEADLINE_S = 160.0`, `WORKER_STOP_S = 90.0` (the last four count from shutdown start; comment: "trader grace 180 s and worker grace 120 s include up to 10 s of uvicorn graceful shutdown"), and `_sleep = asyncio.sleep` (tests replace it).
<!-- Red team 2026-10-28: #5 #14 -->
2. `hold_lease(repo, name, owner, state, on_acquired, on_lost, on_renewed)` — all parameters required; `on_acquired(expires)` takes the first expiry only (the trader closure computes the handover gap itself); `state` is `app.state.lease_state`:
   ```python
   state[name] = "standby"
   expires = await _try_acquire(repo, name, owner)        # None when another owner holds it or on error (WARNING lease.acquire_failed)
   if expires is None:
       logger.info("lease.waiting", name=name, owner=owner)
       while expires is None:
           await _sleep(LEASE_POLL_S)
           expires = await _try_acquire(repo, name, owner)
   logger.info("lease.acquired", name=name, owner=owner)
   try:
       # A takeover that outlives the order margin would act on a lease another copy may take.
       await asyncio.wait_for(on_acquired(expires), LEASE_TTL_S - ORDER_MARGIN_S)
   except Exception:
       state[name] = "lost"
       logger.error("lease.takeover_failed", name=name, owner=owner, exc_info=True)
       with contextlib.suppress(Exception):
           await repo.release(name, owner)
       await on_lost()
       return
   state[name] = "held"                                   # only now: /health and wait_lease see a working holder
   delay = LEASE_RENEW_S
   while True:
       await _sleep(delay)
       try:
           renewed = await repo.acquire(name, owner, LEASE_TTL_S)
           taken = renewed is None
       except Exception:
           logger.warning("lease.renew_failed", name=name, exc_info=True)
           renewed, taken = None, False
       if renewed is not None:
           expires, delay = renewed, LEASE_RENEW_S
           on_renewed(expires)
           continue
       delay = LEASE_RETRY_S
       if taken or expires - datetime.now(UTC) <= timedelta(seconds=ORDER_MARGIN_S):
           state[name] = "lost"
           logger.error("lease.lost", name=name, owner=owner)
           await on_lost()
           return
   ```
   `on_renewed` stays required: the trader extends `trading_until` with it; dropping it would freeze the order fence at the first expiry minus 5 s. The worker passes `lambda _expires: None`.
3. `JobScheduler.pause()` in `scheduler.py`: `if self._scheduler is not None: self._scheduler.pause()`, docstring "Stop starting new runs; running jobs continue."
4. `sync_jobs.py`: module set `_RUNNING: set[asyncio.Task[None]] = set()`; `_tracked` adds `asyncio.current_task()` as its first statement and discards it in a `finally` around the body; new `async def wait_running_jobs(timeout_s: float) -> int` ("Wait until running jobs finish or the timeout passes; return how many still run."): `if _RUNNING: await asyncio.wait(set(_RUNNING), timeout=max(0.0, timeout_s))`; `return len(_RUNNING)`. Docstring at `:646-649`: "Assumes `scheduler.start()` has already run: the worker role starts the scheduler after it takes the worker lease and only then registers the jobs."
5. `start_worker(container, app, owner) -> None` creates `app.state.worker_lease_task = asyncio.create_task(hold_lease(repo, "worker", owner, app.state.lease_state, on_acquired, on_lost, lambda _expires: None))` where `on_acquired(expires)` runs `recover_orphan_jobs(container)`, `scheduler.initialize(settings)`, `scheduler.start()`, `register_sync_jobs(container=container, job_scheduler=scheduler)` (import `register_sync_jobs` at module level so tests can replace it), and `on_lost` runs `scheduler.shutdown(wait=False)` then `os.kill(os.getpid(), signal.SIGTERM)`.
<!-- Red team 2026-10-28: #4 -->
6. `stop_worker(container, app, owner, started)`: return if no `worker_lease_task`; if `lease_state.get("worker") != "held"`: `await _cancel(task)` (import `_cancel` from `main_extensions`) and return. Else: `scheduler.pause()`; `left = await wait_running_jobs((started + timedelta(seconds=WORKER_STOP_S) - get_current_time()).total_seconds())`; WARNING `worker.jobs_still_running count=left` when `left`; then `await _cancel(task)` (renewal runs until here; stopping it before the release keeps a late renewal from taking the released lease back), `scheduler.shutdown(wait=False)`, `await repo.release("worker", owner)`, state `"released"`, INFO `worker.lease_released running=left`.
7. Write `tests/app_test/unit/test_roles.py` with an in-memory `FakeLeaseRepo` (`acquire` returns `None` when another owner holds an unexpired entry, raises `RuntimeError` when its `fail_renew` flag is set for the holder; `release` expires the entry and records the call), constants shrunk with `monkeypatch.setattr(roles, ...)` (`LEASE_TTL_S=1.0`, `LEASE_RENEW_S=0.1`, `LEASE_RETRY_S=0.1`, `LEASE_POLL_S=0.05`, `ORDER_MARGIN_S=0.5`, `WORKER_STOP_S=0.3`):
   - `test_only_one_of_two_contenders_acquires`: two tasks, after 0.3 s exactly one `on_acquired` call; states `{"held","standby"}` in separate dicts.
   - `test_waiting_contender_acquires_after_release`: cancel the holder, `release`, second `on_acquired` within 0.3 s.
   - `test_renewal_taken_by_another_owner_calls_on_lost_once`: overwrite the entry with owner `"thief"` → `on_lost` called once within 0.3 s, state `"lost"`, one `lease.lost` event (`structlog.testing.capture_logs`).
   - `test_failed_renewals_until_the_margin_call_on_lost_once`: set `fail_renew` after the first renewal → `on_lost` once within 1.0 s, `lease.renew_failed` at least once.
   - `test_on_renewed_gets_each_new_expiry`: three renewals → three strictly increasing values.
   - `test_state_is_held_only_after_on_acquired_returns`: `on_acquired` waits on an `asyncio.Event` → state stays `"standby"` while it waits; after `set()` it is `"held"` within 0.1 s.
   - `test_failed_takeover_releases_and_runs_on_lost`: `on_acquired` raises `RuntimeError` → one `lease.takeover_failed` at level `error` with `exc_info`, state `"lost"`, the repo recorded one `release`, `on_lost` called once, no `acquire` call after the failure within 0.3 s.
   - `test_slow_takeover_fails_before_the_order_margin`: `on_acquired` sleeps 2 s → `lease.takeover_failed` and `on_lost` within 0.7 s.
   - `test_worker_stop_waits_for_a_running_job_then_releases`: state `"worker": "held"`, a fake scheduler recording `pause`/`shutdown`, a task added to `sync_jobs._RUNNING` that sleeps 0.1 s then records `job_done` and removes itself → recorded order `pause, job_done, shutdown, release`, one `worker.lease_released`.
   - `test_worker_stop_releases_when_a_job_outlives_the_bound`: the job never ends → `release` within 0.5 s of `started`, one `worker.jobs_still_running` with `count == 1`.
8. Write `tests/app_test/integration/test_worker_role.py::test_second_worker_starts_scheduler_only_after_the_first_releases`: two containers from `create_container(settings)`, `register_sync_jobs` replaced by an async no-op via `monkeypatch.setattr(roles, "register_sync_jobs", ...)`, two `SimpleNamespace(state=SimpleNamespace(lease_state={}))` apps, owners `"w1:1"` and `"w2:1"`; assert after 1 s: worker 2 state `"standby"` and its `JobScheduler._scheduler is None`, exactly one `scheduler.started` captured; `stop_worker(..., get_current_time())` on worker 1 → within 2 s worker 2 state `"held"` and `_scheduler is not None`. Teardown: `stop_worker` on both, `container.close()`.
**Success criteria:** 10 unit tests and 1 integration test pass.
**Verify:** `uv run python -m pytest tests/app_test/unit/test_roles.py tests/app_test/integration/test_worker_role.py -q 2>&1 | tail -1` → starts with `11 passed`.

### Task 7.4 — Trader standby, takeover, drain; health fields

**Goal:** the trader warms up before `yield`, takes the lease, trades with `trading_until = expires_at - 5 s`, and on SIGTERM drains at a boundary once that boundary's bars are published; `/health` shows `role`, `lease` and `lease_renewed_age_s`.
**Target files and symbols:** `app/roles.py` (`start_trader_standby`, `start_trader_lease`, `drain_trader`, `hand_over`); `StrategyAppService.inflight_count`; `IBrokerPort.inflight_count`; `ExnessBrokerAdapter.inflight_count`; `StrategyReconcileAppService.bootstrap`; `health_check` in `register_routes`; `main.py` lifespan.
**Steps:**
<!-- Red team 2026-10-28: #4 -->
1. `broker_port.py`: add a property `inflight_count -> int` returning `0`, docstring "Orders sent and not yet settled; a trader hands over only at 0." `ExnessBrokerAdapter` overrides it: `len(self._inflight) + len(self._pending_ack)`. `_needs_snapshot` is not counted (a swallowed reconcile error would hold every drain for 150 s); the next trader's takeover snapshot covers it.
2. `StrategyAppService`: add `def inflight_count(self) -> int`, docstring "Venue signal tasks and bar handlers still running plus orders the brokers have not settled; the trader hands over at 0.", returning `sum(not t.done() for t in self._signal_tasks.values()) + self._running_bar_handlers + sum(b.inflight_count for b in set(self._brokers.values()))`. `take_over()` stays as Phase 06 wrote it.
3. `StrategyReconcileAppService.bootstrap`: after `_ensure_instances(subs)`, for each sub with `desired_state == "running"` call `await self._strategy_service.start_strategy(str(sub.id))` inside `try/except Exception` (ERROR `reconcile.sub_failed`); never write `actual_state` here. Docstring: "Runs in the trader role before the lease: loads and warms every running subscription; brokers stay disconnected until the lease is held."
4. `roles.py` (`bars` = `BarAppService` from the container, `engine` = `StrategyAppService`):
<!-- Red team 2026-10-28: #12 -->
   - `start_trader_standby(container, app)`: `engine.trading_until = None`; `bars.publishes_current = False` (only the trader lease holder writes or deletes `bar:current`); `await bootstrap_live_instances(container)`; INFO `trader.standby` with `warmup_s` (seconds since lifespan start, passed in or measured from a `time.monotonic()` taken first) and `strategies=len(engine.loaded_strategy_ids())`.
<!-- Red team 2026-10-28: #1 #14 -->
   - `start_trader_lease(container, app, owner)`: `waiting_since = datetime.now(UTC)`; `app.state.trader_lease_task = asyncio.create_task(hold_lease(repo, "trader", owner, app.state.lease_state, _take_over, _on_lost, _on_renewed))` with closures:
     - `_take_over(expires)`:
       ```python
       t0 = time.monotonic()
       doc = await repo.get("trader")
       released = doc.get("released_at") if doc else None
       # Empty when the previous holder lost the lease instead of releasing it.
       gap_ms = (round((datetime.now(UTC) - released).total_seconds() * 1000)
                 if released and released >= waiting_since else None)
       logger.info("trader.takeover", handover_gap_ms=gap_ms)
       bars.publishes_current = True
       await engine.take_over()
       await collector.start()                # LiveTradeCollector
       app.state.reconcile_task = asyncio.create_task(reconcile.run())
       engine.trading_until = expires - timedelta(seconds=ORDER_MARGIN_S)
       logger.info("trader.takeover_complete", takeover_ms=round((time.monotonic() - t0) * 1000))
       ```
     - `_on_renewed(expires)`: `if engine.trading_until is not None: engine.trading_until = expires - timedelta(seconds=ORDER_MARGIN_S)` (a drained or lost trader is never re-armed).
<!-- Red team 2026-10-28: #5 #12 -->
     - `_on_lost()`: `engine.trading_until = None`; `engine.cancel_pending_signals()` right after it (later discards log `reason=lease`); `bars.publishes_current = False`; `await stop_reconcile_loop(app)`; `await engine.stop(ORDER_MARGIN_S)` (a send already under way gets 5 s for its ACK); `os.kill(os.getpid(), signal.SIGTERM)`.
<!-- Red team 2026-10-28: #4 -->
   - `drain_trader(engine, bars, started) -> tuple[int, datetime]` uses `get_current_time()` (`core.common.time.simulation`) and `_sleep`:
     ```python
     deadline = started + timedelta(seconds=DRAIN_DEADLINE_S)
     boundary = started.replace(second=0, microsecond=0) + timedelta(minutes=1)
     for attempt in (1, 2):
         await _sleep(max(0.0, (boundary - get_current_time()).total_seconds()))
         window_end = min(boundary + timedelta(seconds=DRAIN_WINDOW_S), deadline)
         while get_current_time() < window_end:
             closed = bars.last_closed_boundary          # every bar of the boundary published
             if closed is not None and closed >= boundary and engine.inflight_count() == 0:
                 engine.trading_until = None   # same step as the check: nothing new starts
                 return 0, boundary
             await _sleep(0.2)
         if attempt == 1:
             logger.info("trader.drain_retry", boundary=boundary.isoformat(), inflight=engine.inflight_count())
             boundary += timedelta(minutes=1)
     inflight = engine.inflight_count()
     engine.trading_until = None
     logger.error("trader.drain_timeout", boundary=boundary.isoformat(), inflight=inflight)
     return inflight, boundary
     ```
     A signal that arrives after the release decision is discarded with INFO `strategy.signal_discarded reason=drain` (`take_over()` set that reason).
   - `hand_over(container, app, owner, started)`: return if no `trader_lease_task`; if `lease_state.get("trader") != "held"`: `await _cancel(task)` and return (standby or lost: a lost lease skips the wait). Else, with the lease task still renewing:
     ```python
     inflight, boundary = await drain_trader(engine, bars, started)
     await stop_reconcile_loop(app)
     stop_by = started + timedelta(seconds=STOP_DEADLINE_S)
     await engine.stop(max(0.0, (stop_by - get_current_time()).total_seconds()))   # bounded gather
     bars.publishes_current = False
     await _cancel(task)   # renewal ran until here; cancelled before the release so it cannot take the lease back
     await repo.release("trader", owner)
     app.state.lease_state["trader"] = "released"
     logger.info("trader.lease_released", inflight=inflight, boundary=boundary.isoformat(),
                 offset_s=round((get_current_time() - boundary).total_seconds(), 3))
     ```
5. `main.py` lifespan:
   - Before `try`: `owner = f"{socket.gethostname()}:{os.getpid()}"`; `app.state.lease_state = {}`; `roles = settings.roles`; log `application_starting` with `roles=settings.app_roles`.
   - In `try`: `assert_utc_runtime()`, `start_loop_lag_probe(app)`, `database`/`cache`, `init_backtest_tasks`, `ensure_all_indexes`, `register_health_checks`; then `if "trader" in roles: await start_trader_standby(container, app); await start_quote_feed(container, app); start_trader_lease(container, app, owner)`; then `if "worker" in roles: start_worker(container, app, owner)`; INFO `application_started`; `yield`. Delete from the lifespan the calls to `recover_orphan_backtests`, `recover_orphan_jobs`, `bootstrap_live_instances`, the Phase 06 `take_over()` line and `start_jobs`, and any import left unused.
<!-- Red team 2026-10-28: #4 -->
   - `finally`: `started = get_current_time()` first (every drain and stop deadline counts from here); `await stop_loop_lag_probe(app)`; `results = await asyncio.gather(stop_worker(container, app, owner, started), hand_over(container, app, owner, started), return_exceptions=True)` and log ERROR `application.stop_failed` with `exc_info` for each exception in `results` (worker and trader stop together, so the next worker starts while the trader drains and neither eats the other's grace); `await drain_backtest_tasks(app)`; `await stop_reconcile_loop(app)`; `if "trader" in roles: await stop_quote_feed(container, app)`; `await container.close()`; INFO `application_stopped`.
6. `main_extensions.py`: delete `start_jobs` and `recover_orphan_backtests`; rewrite the module docstring to "Helpers for main.py. A process runs the roles in APP_ROLES; see roles.py."
<!-- Red team 2026-10-28: #5 -->
7. `health_check` (a closure over `app`, like the Phase 02 lag field; add `lease_repo: FromDishka[LeaseRepository]`): after `environment` add `result["role"] = settings.app_roles`; `states = getattr(app.state, "lease_state", {})`; `result["lease"] = "none" if not states else ("held" if all(v == "held" for v in states.values()) else "standby")`; `result["lease_renewed_age_s"]` = the largest `now - renewed_at` in seconds (one decimal) over the lease documents of the names whose state is `"held"`, `None` when none is held or the read fails (a stale value means renewals stopped).
8. `app_factory.py`: drop the `recover_orphan_backtests` and `start_jobs` imports and calls.
9. Tests:
   - `tests/app_test/unit/test_trader_drain.py` (fake engine with `trading_until` and `inflight_count()` and fake `bars` with `last_closed_boundary`, both driven by a schedule on simulated time; `monkeypatch.setattr(roles, "_sleep", fake)` where `fake` advances `set_simulation_time` by its argument then `await asyncio.sleep(0)`; start `T0 = 2026-10-28T10:00:20Z`, so `B = 10:01:00Z`; the boundary bars publish at B+0.6 s and at every later boundary + 0.6 s unless a test says otherwise; clear simulation time in teardown):
     - `test_idle_trader_releases_once_the_boundary_bars_are_published` (returns `(0, B)`, `0.6 <= now-B <= 0.8`, `trading_until is None`).
     - `test_release_waits_for_late_boundary_bars` (idle, bars of B publish at B+3 s → `3.0 <= now-B <= 3.2`).
     - `test_inflight_open_delays_release_until_it_settles` (busy until B+5 s → `(0, B)`, `5.0 <= now-B <= 5.2`).
     - `test_busy_window_retries_once_at_the_next_boundary` (busy until B+40 s → `(0, B+60 s)`, one `trader.drain_retry`).
     - `test_never_idle_logs_drain_timeout_within_150_s_of_shutdown_start` (always 1 → `inflight == 1`, one `trader.drain_timeout` at level `error`, `now - T0 <= 150.2 s`, `trading_until is None`).
<!-- Red team 2026-10-28: #1 #12 -->
   - `tests/app_test/integration/test_trader_role.py` (real Mongo; container from `create_container(settings)`; app = `SimpleNamespace(state=SimpleNamespace(lease_state={}))`; a foreign doc `{"_id": generate_id_str(), "name": "trader", "owner": "other:1", "expires_at": now+60 s}` inserted first; teardown cancels `trader_lease_task`, `stop_reconcile_loop`, `container.close()`):
     - `test_standby_trader_does_not_trade` (after 1 s: state `"standby"`, `engine.trading_until is None`, `bars.publishes_current is False`, no `reconcile_task`, `orders`/`positions`/`trades` counts 0).
     - `test_trader_takes_over_after_release_and_logs_both_takeover_events` (`release("trader","other:1")` → within 2 s state `"held"`, `abs((doc["expires_at"] - engine.trading_until).total_seconds() - 5.0) < 0.01`, `reconcile_task` running, `bars.publishes_current is True`; captured logs hold `lease.acquired`, then `trader.takeover` with an integer `handover_gap_ms >= 0`, then `trader.takeover_complete` with an integer `takeover_ms >= 0`, in that order).
     - `test_takeover_after_a_lost_holder_logs_an_empty_gap` (set the foreign doc's `expires_at` to now-1 s instead of releasing → `trader.takeover` with `handover_gap_ms is None`, then `trader.takeover_complete`).
     - `test_lost_renewal_stops_trading_and_signals_exit` (`LEASE_RENEW_S=0.1`, `os.kill` replaced by a recorder; after takeover set the doc owner to `"thief:1"` and `expires_at` to now+60 s → within 1 s `trading_until is None`, `bars.publishes_current is False`, `engine.is_running is False`, recorder holds `(os.getpid(), signal.SIGTERM)`).
<!-- Red team 2026-10-28: #3 -->
   - `tests/app_test/integration/test_trader_lifespan_handover.py::test_sigterm_mid_open_drains_releases_and_the_next_trader_takes_over` (the real `main.lifespan`; real Mongo/Redis from the `app_test` fixtures; `trader_settings = settings.model_copy(update={"app_roles": "trader"})`; it runs 20-80 s of real time because the drain waits for a real 1m boundary):
     - Setup: `monkeypatch.setattr(main, "get_settings", lambda: trader_settings)`; `monkeypatch.setattr(RoutingRealtimeQuoteAdapter, "run_forever", <async def that awaits asyncio.Event().wait()>)` so no venue socket opens while the Phase 05 bar close timer still runs; `monkeypatch.setattr(BrokerFactory, "create", ...)` returning a new `SlowAsyncFillBroker` per call (defined in the test file, kept in a list: `fills_async = True`, `connect`/`disconnect` no-ops, `submit_order(order, *, deadline)` adds one order to its in-flight set, awaits until `ack_at`, records `acked_at`, then settles it — the delayed ACK; `inflight_count` = size of the in-flight set); insert one running paper subscription (`hitnrun2`, `BTCUSDT:BINANCE`, 1m, as in `test_declarative_subscription_state_api.py`, `desired_state="running"`).
     - Two apps `FastAPI(lifespan=main.lifespan)`, each with `setup_dishka(create_container(trader_settings), app)` and `register_routes(app, trader_settings)`; patch `main.socket.gethostname` to return `"trader-a"`, enter A (`cm_a = main.lifespan(app_a); await cm_a.__aenter__()`), wait until A's `lease_state["trader"] == "held"`; patch it to `"trader-b"`, enter B, wait until B's state is `"standby"`.
     - Sleep until 3 s before the next whole minute B. Set each fake's `ack_at = B + 5 s` and start one open through A's engine venue signal path for the subscription, the way Phase 06's entry-guard tests drive a venue signal (it registers in `_signal_tasks`). After 0.2 s `engine_a.inflight_count() >= 1`.
     - Simulate SIGTERM: `stop = asyncio.create_task(cm_a.__aexit__(None, None, None))` (uvicorn runs lifespan shutdown on SIGTERM after its graceful wait).
     - Within 75 s: `stop` is done; captured logs (`structlog.testing.capture_logs`) hold exactly one `trader.lease_released` with `inflight == 0` and `5.0 <= offset_s <= 6.5` and zero `trader.drain_timeout`; the fake's `acked_at` is before the release; within 3 s of the release B's state is `"held"` and its logs hold `trader.takeover` with an integer `handover_gap_ms` followed by `trader.takeover_complete` with an integer `takeover_ms`; `GET /health` on B through `httpx.AsyncClient(transport=ASGITransport(app=app_b))` returns `lease == "held"` and `0 <= lease_renewed_age_s < 11`.
     - Teardown: exit B's lifespan.
<!-- Red team 2026-10-28: #5 -->
   - `tests/app_test/integration/test_health_role_fields.py::test_health_reports_role_and_no_lease_for_api_only` (fixture `app_client`): `GET /health` → 200, `role == "api"`, `lease == "none"`, `lease_renewed_age_s is None`.
   - `tests/engine_test/test_trader_fence.py` (harness copied from `tests/engine_test/test_strategy_entry_guards.py`, with a broker whose `connect` records calls and whose `inflight_count` is settable): `test_standby_engine_connects_no_broker_on_start` (`trading_until = None`; `load_strategy` + `start_strategy` → `connect` never called; set `trading_until` to now + 25 s and call `take_over()` → `connect` called once); `test_inflight_count_counts_signal_tasks_bar_handlers_and_broker_orders` (one running signal task, `_running_bar_handlers = 1`, broker `inflight_count` 2 → `4`; all finished → `0`). The fence itself is covered by the two Phase 06 tests named in Context.
   - `tests/engine_test/test_strategy_reconcile_service.py::test_bootstrap_starts_running_subscriptions_without_writing_actual_state` (reuse that file's fakes): running sub → instance `is_running`; stopped sub → not running; `update_actual_state` never called.
   - `tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py::test_inflight_count_counts_opens_and_acks_not_a_pending_snapshot` (reuse the file's adapter harness): fresh → `0`; one `_inflight` entry, one `_pending_ack` id, `_needs_snapshot=True` → `2`.
**Success criteria:** all listed tests pass; `grep -c "start_jobs\|recover_orphan_backtests" src/pocketquant/app/main.py src/pocketquant/app/main_extensions.py` totals 0.
**Verify:** `uv run python -m pytest tests/app_test/unit/test_trader_drain.py tests/app_test/integration/test_trader_role.py tests/app_test/integration/test_trader_lifespan_handover.py tests/app_test/integration/test_health_role_fields.py tests/engine_test/test_trader_fence.py tests/engine_test/test_strategy_reconcile_service.py tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py -q 2>&1 | tail -1` → contains `passed` and contains neither `failed` nor `error`.

### Task 7.5 — Heartbeat backtest sweep

**Goal:** a running backtest refreshes `heartbeat_at`; a worker job fails only `started` runs whose heartbeat is older than 60 s (D18).
**Target files and symbols:** `BacktestExecutionService.execute_and_persist`; `BacktestRepository.touch_heartbeat`, `mark_orphaned_started_as_failed`; new job `backtest_orphan_sweep` in `sync_jobs.py`.
**Steps:**
1. Repository: add `touch_heartbeat(run_id)` (`$set heartbeat_at: datetime.now(UTC)` on `{"_id": run_id, "status": "started"}`); add module constant `_ORPHAN_AFTER = timedelta(seconds=60)`; `mark_orphaned_started_as_failed()` filters `{"status": "started", "$or": [{"heartbeat_at": {"$lt": cutoff}}, {"heartbeat_at": {"$exists": False}, "started_at": {"$lt": cutoff}}]}` with `cutoff = now - _ORPHAN_AFTER`; docstring "Fail runs whose task stopped refreshing its heartbeat; a live run refreshes every 15 s." Keep the `error_message` and log name.
2. `backtest_execution_service.py`: module constant `_HEARTBEAT_S = 15.0`; `execute_and_persist` starts `beat = asyncio.create_task(self._heartbeat(run_id))` before the `try` and cancels it in a `finally`; `_heartbeat` loops `touch_heartbeat` then `await asyncio.sleep(_HEARTBEAT_S)`, logging WARNING `backtest_execution.heartbeat_failed` on an exception and continuing.
3. `sync_jobs.py`: add `async def backtest_orphan_sweep()` that resolves `BacktestRepository` from `_get_container()` and runs `mark_orphaned_started_as_failed()` inside `_tracked("backtest_orphan_sweep", body)`; register it in `register_sync_jobs` with `job_id="backtest_orphan_sweep"`, `cron_expression="*/5 * * * *"`, `second=40`, `misfire_grace_time=300`; docstring count "6" → "7".
4. Tests: rewrite `tests/core_test/infra/persistence/test_stale_recovery.py` (module docstring states the 60 s heartbeat rule): `test_stale_heartbeat_is_marked_failed` (heartbeat now-61 s → failed, `error_message == "interrupted_by_restart"`), `test_fresh_heartbeat_survives` (now-5 s → still `started`), `test_missing_heartbeat_falls_back_to_started_at` (no heartbeat, `started_at` now-61 s → failed; now-5 s → started), `test_sweep_is_idempotent`, `test_finished_and_failed_docs_untouched` (stale timestamps, status unchanged). In `test_backtest_single_run_direct_task.py` rename `test_orphan_started_swept_to_failed_on_boot` to `test_orphan_started_with_stale_start_is_swept_to_failed` and set `started_at` to now-61 s before the sweep. New `tests/backtest_test/test_backtest_execution_heartbeat.py::test_heartbeat_refreshes_while_running_and_stops_after` (fake repo counting `touch_heartbeat`; `_HEARTBEAT_S=0.05`; `run` replaced by a 0.2 s sleep → at least 3 touches; no new touch in the next 0.2 s).
**Success criteria:** tests pass; the job is registered.
**Verify:** `grep -c 'job_id="backtest_orphan_sweep"' src/pocketquant/engine/market_data/app_services/sync_jobs.py; uv run python -m pytest tests/core_test/infra/persistence/test_stale_recovery.py tests/backtest_test/test_backtest_single_run_direct_task.py tests/backtest_test/test_backtest_execution_heartbeat.py -q 2>&1 | tail -1` → first line `1`; last line contains `passed` and neither `failed` nor `error`.

### Task 7.6 — Rule text, compose `app`, deploy script, logging check, config repo

**Goal:** the single-worker rule describes leases; the `app` container runs all roles explicitly and drains within its grace period; public deploy logs carry no log tails or traceback locals; local profiles never contend for the prod lease.
**Target files and symbols:** `CLAUDE.md:15`; `deploy/Dockerfile:61-62`; `deploy/compose.prod.yml` `app` (`:53-64`, `:73-74`, `:81-86`); `deploy/vps/10-deploy.sh:61-62,72`; `../pocketquant-config` files. `src/pocketquant/core/common/logging/setup.py:71` is not edited here: Phase 02 Task 2.6 already set the plain traceback formatter, and the Verify below only asserts it is still present.
**Steps:**
1. `CLAUDE.md:15` becomes: `- **One lease-holding trader and one lease-holding worker** — APP_ROLES picks a process's roles; the trader (quote feed, strategies, brokers, reconcile loop) and the worker (scheduler, jobs) act only while they hold their Mongo lease, so a second copy waits in standby. Never run \`--workers N\`.`
2. `Dockerfile:61-62` and `compose.prod.yml:62-63` comments become: "One uvicorn worker per container; the worker and trader roles act only while they hold their Mongo lease." `compose.prod.yml:53-57` comment: "Backend with all roles (APP_ROLES below). Migrations and indexes run before yield; the trader warms up in standby before yield, so healthy means warm."
<!-- Red team 2026-10-28: #5 -->
3. `app` service: add `APP_ROLES: "api,worker,trader"` under `environment:` after `TZ` (the default is `api`); append `"--timeout-graceful-shutdown", "10"` to `command`; add `stop_grace_period: 180s` with comment "SSE close (10 s) + trader drain at a 1m boundary and bounded stop (up to 160 s) + release"; healthcheck `start_period: 180s`.
<!-- Red team 2026-10-28: #7 -->
4. `10-deploy.sh:61-62` → `f=/opt/pocketquant/logs/failed-app-$(date -u +%Y%m%dT%H%M%SZ).log; mkdir -p /opt/pocketquant/logs; docker logs "$container" --tail 30 > "$f" 2>&1 || true` and `echo "--- log tail saved on the VPS: $f ---"` (the Actions log is public); `:72` → `wait_health pocketquant-app 41921 240`.
5. Config repo: delete `ENABLE_JOBS=true` from `vps/default/.env` (the new image refuses to start while it is there; CI materializes this file on the D-4 deploy); `local/remote-db.env:42`, `local/remote-db-local-redis.env:47`, `local/all-local.env:34` → `APP_ROLES=api`; `local/remote-db-local-redis.env:3` → `# APP_ROLES=api => no worker => zero bar writes to prod Mongo.`; `README.md:83` → "`APP_ROLES=api` so the local process never contends for the prod worker or trader lease". Then `git -C ../pocketquant-config add vps/default/.env local/remote-db.env local/remote-db-local-redis.env local/all-local.env README.md && git -C ../pocketquant-config commit -m "chore(env): replace ENABLE_JOBS with APP_ROLES" && git -C ../pocketquant-config push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant-config.git" HEAD`. If the gitignored local `.env` in this repo holds `ENABLE_JOBS`, delete that line too.
**Success criteria:** rule rewritten; compose values set; no log tail printed by the deploy script; the Phase 02 plain traceback formatter is still in `setup.py`; config pushed.
**Verify:** `grep -c "Single uvicorn worker only" CLAUDE.md; uv run python -c "import yaml; a=yaml.safe_load(open('deploy/compose.prod.yml'))['services']['app']; assert a['stop_grace_period']=='180s' and a['healthcheck']['start_period']=='180s' and a['command'][-2:]==['--timeout-graceful-shutdown','10'] and a['environment']['APP_ROLES']=='api,worker,trader'; print('ok')"; grep -c "wait_health pocketquant-app 41921 240" deploy/vps/10-deploy.sh; grep -c "last 30 log lines" deploy/vps/10-deploy.sh; grep -c "exception_formatter=structlog.dev.plain_traceback" src/pocketquant/core/common/logging/setup.py; git -C ../pocketquant-config grep -n -i enable_jobs | wc -l; git -C ../pocketquant-config status -sb | head -1` → `0`, `ok`, `1`, `0`, `1`, `0`, and a branch line without `ahead`.

### Task 7.7 — Gates, commit, push `develop`

**Goal:** CI is green on the role code.
**Target files and symbols:** whole repo.
**Steps:**
1. `docker ps` (start Docker Desktop if it fails, retry after 10 s). Run `uv run ruff check src tests`, `uv run lint-imports`, `uv run python scripts/code_metrics.py --ratchet`. If the ratchet fails, raise the exceeded value under `[tool.code-metrics]` in `pyproject.toml` alone and commit it as `chore(metrics): raise the code-metrics ceilings for the role runtime`; record it in the report.
2. Full suite: `uv run python -m pytest tests/ -q > .cache/pytest-full.txt 2>&1`.
3. `git add -A src tests justfile CLAUDE.md deploy && git commit -m "feat(runtime): run api, worker and trader roles under Mongo leases"`.
4. `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`; then in background mode `sleep 15 && GH_TOKEN=$(gh auth token --user camping89) gh run watch "$(GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --workflow cicd.yml --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status`.
**Success criteria:** local gates as below; CI run succeeds.
**Verify:** `uv run lint-imports | tail -1; uv run python scripts/code_metrics.py --ratchet >/dev/null; echo "ratchet=$?"; grep -E "^(FAILED|ERROR) " .cache/pytest-full.txt | grep -vcE "test_utc_runtime_guard|test_cron_trigger_timezone"; tail -1 .cache/pytest-full.txt; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` → `Contracts: 6 kept, 0 broken.`, `ratchet=0`, `0`, a line starting `4 failed` and containing `4 errors`, `pushed`; and the background `gh run watch` exited 0.

### Task 7.8 — Deploy D-4 and verify

**Goal:** prod `app` runs all roles under leases, each lease owned by the `app` container itself.
**Target files and symbols:** prod VPS; `reports/deploy-a-roles-and-leases.md`.
**Steps:**
1. SSH key: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`.
<!-- Red team 2026-10-28: #11 -->
2. Check the time is inside the **Deploy window** of plan.md Conventions (Mon-Fri 06:00-11:20 or 12:50-19:30 UTC; the Phase 02 deploy window command prints `WINDOW_OK`); if not, exit with the NOT_YET block (Resume at the next window start).
3. [ASK] (only an explicit yes counts):
   > Recommended: đồng ý — Deploy A chỉ thêm role và lease bên trong container `app` hiện tại; live trading vẫn tắt nên không lệnh thật nào bị ảnh hưởng. Câu hỏi: Cho phép đẩy `develop:master` để deploy bản role/lease (Deploy A) lên VPS prod ngay bây giờ (<UTC time>)? Lần deploy này khởi động lại `app` một lần (paper gián đoạn vài phút, lần cuối có gián đoạn).
<!-- Red team 2026-10-28: #2 -->
4. Record before (report section "free -m before"): `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'free -m'`, then the OOM check (one command; prints `OOM_OK` or `OOM_STOP ...`): `B=$(sed -n 's/^oom_baseline=//p' plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md); HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); N=$(ssh -i .cache/ssh/vps_key "$HOST" 'echo "$(cat /proc/sys/kernel/random/boot_id) $(awk "/^oom_kill /{print \$2}" /proc/vmstat) $(docker inspect -f "{{.State.OOMKilled}}" pocketquant-app)"'); set -- $B $N; if [ "$1" = "$3" ] && [ "$4" -le "$2" ] && [ "$5" = false ]; then echo OOM_OK; else echo "OOM_STOP baseline=$B now=$N"; fi`. On `OOM_STOP` the plan stops (D31): record it, `rm -f .cache/ssh/vps_key`, and exit with the NOT_YET block (`NOT_YET: OOM_STOP <values>; owner decides`).
5. `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop develop:master && git fetch origin`; then in background mode the same `gh run watch` as Task 7.7 with `--branch master`.
6. Record after (the step 4 `free -m` and OOM check again) under "free -m after".
**Success criteria:** deploy run succeeded; both leases held by the one `app` and owned by its hostname; one takeover, one scheduler start; `OOM_OK` after the deploy.
<!-- Red team 2026-10-28: #1 #2 #5 -->
**Verify:** the step 4 OOM check command, then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'L=$(docker logs --since 15m pocketquant-app 2>&1 | sed "s/\x1b\[[0-9;]*m//g"); for e in "trader\.takeover( |$)" "trader\.takeover_complete" "scheduler\.started" "lease\.acquired" "lease\.lost" "lease\.takeover_failed" "trader\.standby"; do printf "%s=%s\n" "$e" "$(printf "%s\n" "$L" | grep -cE "$e")"; done; H=$(docker exec pocketquant-app curl -s http://localhost:41921/health); echo "$H" | grep -o "\"role\":\"[^\"]*\""; echo "$H" | grep -o "\"lease\":\"[^\"]*\""; echo "$H" | grep -o "\"lease_renewed_age_s\":[0-9.]*"; docker exec -i pocketquant-app python -c "from datetime import UTC, datetime; from pymongo import MongoClient; from pocketquant.core.config import get_settings; s=get_settings(); db=MongoClient(str(s.mongodb_url), tz_aware=True)[s.mongodb_database]; n=datetime.now(UTC); d=sorted(db.leases.find(), key=lambda x: x[\"name\"]); print(len(d), \",\".join(x[\"name\"] for x in d), sum(x[\"expires_at\"] > n for x in d), \",\".join(sorted({x[\"owner\"].split(\":\")[0] for x in d})))"; echo app_host=$(docker inspect -f "{{.Config.Hostname}}" pocketquant-app)'` → `OOM_OK`; `trader\.takeover( |$)=1`, `trader\.takeover_complete=1`, `scheduler\.started=1`, `lease\.acquired=2`, `lease\.lost=0`, `lease\.takeover_failed=0`, `trader\.standby=1`, `"role":"api,worker,trader"`, `"lease":"held"`, `"lease_renewed_age_s":` with a value below `11`; then `2 trader,worker 2 <h>` and `app_host=<h>` with the same `<h>` (one owner, and it is this container).

### Task 7.9 — D17 probes: a second trader and a second worker for 10 minutes

**Goal:** a second copy of each leased role waits in standby on prod and does nothing a lease holder does, and no probe container can outlive the probe.
**Target files and symbols:** prod VPS; the report.
**Steps:**
1. Record "owners before": the lease one-liner and `app_host` line from Task 7.8 Verify, run once.
<!-- Red team 2026-10-28: #6 -->
2. Start the probes detached (the SSH session returns at once; each probe stops itself after 600 s and is removed on exit): `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'set -e; IMG=$(docker inspect -f "{{.Config.Image}}" pocketquant-app); mkdir -p /opt/pocketquant/logs; docker rm -f pq-probe-trader pq-probe-worker 2>/dev/null || true; for r in trader worker; do docker run -d --rm --name pq-probe-$r --label pq-probe=1 --stop-timeout 180 --network pocketquant-prod_backend --env-file /opt/pocketquant/deploy/.env -e TZ=UTC -e APP_ROLES=$r -e EXNESS_RATE_FRACTION=0.05 -e EXNESS_LIVE_TRADING=false "$IMG" sh -c "exec timeout -s TERM 600 uvicorn pocketquant.app.main:app --host 0.0.0.0 --port 41921" >/dev/null; nohup docker logs -f pq-probe-$r > /opt/pocketquant/logs/probe-$r.log 2>&1 < /dev/null & done; docker ps --filter label=pq-probe=1 --format "{{.Names}}" | sort | tr "\n" " "'` → `pq-probe-trader pq-probe-worker `.
3. Completion poll in background mode (about 11 minutes, at most 15): `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); for i in $(seq 90); do n=$(ssh -i .cache/ssh/vps_key "$HOST" 'docker ps -aq --filter label=pq-probe=1 | wc -l'); [ "$n" = 0 ] && echo probes-done && break; sleep 10; done`. Wait for its completion notice; it must print `probes-done`. If it does not, run `ssh ... 'docker stop pq-probe-trader pq-probe-worker'` and treat the task as failed (Failure Protocol).
4. Record "owners after" and the Verify output in the report; append the line `Result: PASS` only when every Verify condition here and in Task 7.8 held.
5. `rm -f .cache/ssh/vps_key`.
**Success criteria:** probe trader logged standby and none of the holder events; probe worker never started a scheduler; prod `app` lost no lease; owners unchanged and equal to the `app` hostname; no `pq-probe` container left.
**Verify:** `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/logs; for e in trader.standby lease.waiting lease.acquired trader.takeover exness.order_submitted position_opened position_closed orphan_backtest_recovery backtest_orphan_recovery orphan_jobs_recovered scheduler.started; do echo "$e trader=$(sed "s/\x1b\[[0-9;]*m//g" probe-trader.log | grep -c "$e") worker=$(sed "s/\x1b\[[0-9;]*m//g" probe-worker.log | grep -c "$e")"; done; echo app_lost=$(docker logs --since 15m pocketquant-app 2>&1 | sed "s/\x1b\[[0-9;]*m//g" | grep -c "lease\.lost"); echo probes_left=$(docker ps -aq --filter label=pq-probe=1 | wc -l)'` → `trader.standby trader=` a number `>= 1`; `lease.waiting` both numbers `>= 1`; every other event `trader=0 worker=0` (`trader.takeover` also covers `trader.takeover_complete`); `app_lost=0`; `probes_left=0`; and "owners before" equals "owners after" in the report, with the owner host equal to `app_host`.

## Rollback

- Before D-4: `git revert` the phase commits on `develop` and push `develop`; revert the `pocketquant-config` commit with `git -C ../pocketquant-config revert HEAD` and push it.
- After D-4: keep the `pocketquant-config` commit. The Phase 06 image defaults `enable_jobs` to `True` and ignores `APP_ROLES` (`git show 3905ff6b:src/pocketquant/core/config.py:37,57`), so it runs without `ENABLE_JOBS`; putting `ENABLE_JOBS` back would make the next deploy of this phase's image refuse to start (corrected 2026-10-29 after the pre-deploy review). `git revert` the phase commits, [ASK] (Vietnamese, `Recommended: ...`) and push `develop:master` inside the **Deploy window** of plan.md Conventions. The Phase 06 image ignores `leases` and `heartbeat_at`; its boot sweep fails every `started` run once. Drop the `leases` collection afterwards only after an [ASK].
- A probe that outlives Task 7.9: `ssh ... 'docker rm -f $(docker ps -aq --filter label=pq-probe=1)'`; with `--rm` and `timeout` it removes itself after 600 s anyway.
- Record `free -m` before and after a rollback deploy in the report.
- Image guard rule (from Phase 08 on): never pin `IMAGE_TAG` to an image older than this phase under the split compose; the Phase 08 guard refuses it.

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
