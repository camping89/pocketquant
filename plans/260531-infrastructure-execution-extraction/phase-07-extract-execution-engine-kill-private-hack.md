---
phase: 7
title: "Extract execution engine + kill private hack"
status: done
priority: P1
effort: "1.5d"
dependencies: [6]
---

# Phase 7: Extract execution engine + kill private hack

## Overview

The pivotal phase that breaks the backtest↔trading cycle. Move the shared strategy-execution engine (`StrategyAppService`, `OrderAppService`, `PositionAppService`, `RiskCheckHandler`) into `pocketquant-execution`. Move the backtest-RUN orchestration (`backtest_jobs`, `backtest_strategy_loader`, `run_all_backtests` handler) out of trading into the backtest package. Replace all 3 private-member injection hacks with a public execution-service API.

## Requirements
- Functional: `backtest` and `trading` import neither each other. Both import `pocketquant.execution.*` for the engine. No `# pyright: ignore[reportPrivateUsage]` remains on the strategy-injection path (3 sites eliminated). Strategy-injection round-trip characterization test green via the NEW public method. Full suite + api boot green.
- Non-functional: identical runtime behavior — synthetic-id scoping (C2 concurrency fix), TOCTOU re-checks (M1), status semantics (C1) preserved exactly.

## Architecture

**Engine → execution package:**
- `execution/app_services/{strategy_app_service.py,order_app_service.py,position_app_service.py}`
- `execution/handlers/risk/check_risk/handler.py` (RiskCheckHandler) — or `execution/risk/`; confirm against how api DI + strategy service consume it.
- Engine imports: ports from `core.domain.brokers`, repos (`OrderRepository`, `PositionRepository`) from `infrastructure.persistence` — both legal (execution → core + infrastructure).

**Public injection API (kills the hack):** the two WRITE sites do MORE than dict-assignment — under the SAME `_lock` they also connect the broker and start the strategy (a comment at the sites mandates "do both in one critical section"). The public method MUST preserve that atomicity, or it silently regresses: strategies injected but never started, brokers never connected (empty/zero-trade backtests), or a lock-split race with `unload_strategy`. Add to `StrategyAppService`:
```
async def inject_prepared_strategy(self, sid: str, strategy: IStrategy, broker: IBroker, config: StrategyConfig) -> None:
    async with self._lock:
        self._strategies[sid] = strategy
        self._brokers[sid] = broker
        self._configs[sid] = config
        if not broker.is_connected:
            await broker.connect()
        await strategy.on_start()   # connect + on_start INSIDE the lock — matches both hack sites

def get_config(self, sid: str) -> StrategyConfig | None:
    return self._configs.get(sid)
```
**Two distinct concerns — do NOT conflate into one accessor's keyspace:**
- The two WRITE sites (`run/handler.py:100-109`, `backtest_strategy_loader.py:118-126`) write under a **synthetic_id** and need the full inject+connect+on_start sequence above. Replace with `inject_prepared_strategy`.
- The third "hack" site (`backtest_jobs.py:101`) is a READ — `_configs.get(strategy_code)` keyed by the **live strategy_code** (config pre-loaded via `load_strategy`), NOT a synthetic_id. `get_config(strategy_code)` covers it, but it is a separate, smaller change (read accessor) — do NOT route it through `inject_prepared_strategy`. The `sid` param name is generic; the caller must pass `strategy_code` here. If `get_config` returns `None`, the existing guard (`backtest_jobs.py:102-103` "config not in memory" → `ValueError`) must behave identically to today's `._configs.get(strategy_code)`.

Verify connect/on_start preservation and the read-vs-write split against the Phase 1 round-trip characterization test (which now asserts `on_start()` fired + broker connected).

**Backtest-RUN orchestration → backtest package** (it runs backtests; belongs with the engine, and trading must not host it):
- `trading/jobs/backtest_jobs.py` → `backtest/jobs/subscription_backtest_jobs.py`
- `trading/jobs/backtest_strategy_loader.py` → `backtest/jobs/backtest_strategy_loader.py`
- `trading/handlers/strategy/run_all_backtests/` → `backtest/handlers/run_all_backtests/` (or keep route in api; logic in backtest)
- APScheduler job string `pocketquant.trading.jobs.backtest_jobs:run_subscription_backtest` → `pocketquant.backtest.jobs.subscription_backtest_jobs:run_subscription_backtest` (update `run_all_backtests` handler `_JOB_MODULE` at `handler.py:11`). **This is a runtime string contract on persisted jobs.** `bt:{sub.id}` jobs are stored as pickled text refs in `MongoDBJobStore` (`scheduler.py:59-75,257-283`). VERIFIED BEHAVIOR (apscheduler 3.11.2): a stale job whose text ref no longer resolves does NOT crash the scheduler and does NOT leave a stuck subscription — `MongoDBJobStore._get_jobs` reconstitutes each job inside `try/except BaseException`; `ref_to_obj` raises `LookupError` for the renamed path, and the store auto-`delete_many`s the failed job on load (self-healing). `status="running"` is written to the BacktestRepository result doc only INSIDE the job at step 3 (`backtest_jobs.py:88`), so a job dropped before execution writes no `running` doc. Existing boot recovery (`recover_stale_backtests`→`mark_stale_running_as_failed`, `main_extensions.py:236`) already flips any genuinely-stuck `running` doc to `failed`.
  - **Residual:** a `bt:*` job enqueued pre-deploy but not yet executed references the OLD func path. apscheduler would silently drop it on load (self-healing, no crash) — but then the requested backtest never runs.
  - **Mitigation (BINDING — user-chosen, runs on the server/VPS):** add an idempotent boot step that, for each persisted `bt:*` job whose func ref points at the OLD `pocketquant.trading.jobs.backtest_jobs:run_subscription_backtest` path, **deletes the stale job and re-creates it with the NEW `pocketquant.backtest.jobs.subscription_backtest_jobs:run_subscription_backtest` func ref** (same job id, trigger, args/kwargs) so the in-flight fan-out actually executes after deploy. Active re-key, not a passive purge. No doc note, no log entry required for this. Do NOT add subscription-status reset — no subscription field carries `running`. Must run in the server boot path (`main_extensions.py` startup), not only locally.
- `api/main.py:30,49` `set_backtest_container` import path → new backtest module (currently imported from `trading.jobs.backtest_jobs`).

**Trading→backtest coupling is 7 import sites, not 4** — enumerate ALL before claiming the cycle is severed:
- 4 result-reader handlers importing `BacktestRepository` (`handlers/strategy/{get_subscription_backtest,list_symbols,delete,remove_symbol}/handler.py:3`) — STAY in trading, now import the repo from `infrastructure.persistence` (Phase 5), not from the backtest package.
- `trading/jobs/backtest_jobs.py:63-64` imports `BacktestAppService` + `BacktestRepository` — file MOVES to backtest package (orchestration).
- `trading/jobs/backtest_strategy_loader.py:10` imports `BacktestConfig` from `pocketquant.backtest.optimization.models.backtest_config` — this is the 5th distinct edge (a config, NOT a result repo; it does NOT disappear by moving repos to infra). File MOVES to backtest package; `BacktestConfig` stays in backtest. Verify no OTHER trading code imports `BacktestConfig`/`backtest.optimization` (grep `backtest.optimization.models.backtest_config` across all packages before the move).

Result: "trading doesn't import backtest" is true only after all 7 sites are handled (4 re-pointed to infra, 3 relocated). Do NOT trust the Phase-3 `backtest.domain` consumer enumeration for this — the coupling is via `backtest.persistence` + `backtest.optimization`, not `backtest.domain`.

## Related Code Files
- Create: `execution/app_services/*`, `execution/handlers/risk/check_risk/handler.py`, `execution/__init__.py`
- Move: trading `app_services/{strategy,order,position}_app_service.py` → execution; `handlers/risk/` → execution; trading backtest-run jobs/handler → backtest package
- Delete: trading `app_services/` (now empty), `handlers/risk/`, `jobs/backtest_jobs.py`, `jobs/backtest_strategy_loader.py`, `handlers/strategy/run_all_backtests/`
- Modify: backtest `handlers/run/handler.py` (use `inject_prepared_strategy`, import engine from execution), `engine/backtest_app_service.py` (no change to engine import if it doesn't use StrategyAppService — verify); api `di/trading.py` → split into `di/execution.py` (engine) + `di/trading.py` (OKX broker, subscription repo wiring); `di/handlers.py:58` (RunAllBacktestsHandler path); `main.py` set_container path
- Modify: the 4 trading result-reader handlers — import `BacktestRepository` from `infrastructure.persistence` (already done Phase 5; verify no residual `backtest.persistence` import)
- Move tests: `tests/trading_test/` engine tests → `tests/execution_test/`; backtest-run job tests → `tests/backtest_test/`

## Implementation Steps
1. Write test-first: unit test for `inject_prepared_strategy` + `get_config` on `StrategyAppService` (in `tests/execution_test/`), asserting the Phase-1 round-trip contract INCLUDING `on_start()` invoked + broker connected after injection, and `get_config(unknown) is None`.
2. Move the 4 engine modules → execution; fix imports (ports from core, repos from infra). Move RiskCheckHandler.
3. Add `inject_prepared_strategy` (with connect + on_start inside the lock) + `get_config`; replace the 2 WRITE hack sites with `inject_prepared_strategy`; replace the READ site `backtest_jobs.py:101` with `get_config(strategy_code)` (separate, in-place; verify None-guard behavior unchanged). Remove the 3 `reportPrivateUsage` ignores.
4. Move backtest-run orchestration (jobs + loader + run_all_backtests handler) into the backtest package; update internal imports to execution engine + infra repos. Confirm `BacktestConfig` (the 5th edge) resolves within backtest, no residual trading import.
5. Update APScheduler job-module string (`_JOB_MODULE` at run_all_backtests `handler.py:11`) + `set_container` wiring + api DI (`di/execution.py`, `di/trading.py`, `di/handlers.py:58`, `main.py:30,49`).
6. Handle the renamed persisted-job ref (BINDING — runs on server boot): add an idempotent startup step (in the server boot path, `main_extensions.py`) that scans `MongoDBJobStore` for `bt:*` jobs whose func ref is the OLD `pocketquant.trading.jobs.backtest_jobs:run_subscription_backtest`, DELETES each, and RE-CREATES it with the NEW `pocketquant.backtest.jobs.subscription_backtest_jobs:run_subscription_backtest` func ref (preserve job id, trigger, args/kwargs). This re-keys in-flight fan-out jobs so they still run post-deploy — apscheduler's lazy auto-drop is NOT relied upon. No doc/log entry needed. Do NOT reset subscription status — no subscription field carries `running`. Verify it executes on the VPS startup, not just local dev.
7. Verify the 4 trading result-reader handlers import only `infrastructure.persistence` (no `pocketquant.backtest` import anywhere in trading).
8. Grep assert BOTH directions: `grep -r "pocketquant.trading" backtest/src` → 0 AND `grep -r "pocketquant.backtest" trading/src` → 0. Grep `backtest.optimization.models.backtest_config` across all packages → only inside backtest pkg.
10. Commit: `refactor: extract shared strategy engine to pocketquant-execution; move backtest-run orchestration to backtest; remove private-member injection hacks`.

## Success Criteria
- [ ] `grep -r "pocketquant.trading" backtest/src` → 0 AND `grep -r "pocketquant.backtest" trading/src` → 0 (both directions).
- [ ] `inject_prepared_strategy` connects broker + calls `on_start()` inside `_lock`; Phase 1 round-trip test asserting this is green.
- [ ] No `reportPrivateUsage` ignores remain repo-wide on strategy injection.
- [ ] Persisted-job-path rename handled by an idempotent server-boot step that DELETES stale `bt:*` jobs (old func ref) and RE-CREATES them with the new func ref (active re-key, runs on VPS startup). No subscription-status reset added; no doc/log entry required.
- [ ] Engine lives in execution; both backtest + trading consume it.
- [ ] Strategy-injection + full suite + api boot green.

## Risk Assessment
- Risk: **APScheduler persisted-job path change** — `bt:*` jobs in MongoDBJobStore reference the old `trading.jobs.backtest_jobs:...` text path. VERIFIED (apscheduler 3.11.2): the store auto-drops a job whose ref no longer resolves on load (`_get_jobs` try/except + `delete_many`), so NO scheduler crash and NO stuck subscription (`running` lives on the backtest result doc, written only inside a running job; existing `recover_stale_backtests` boot sweep covers genuine stragglers). Residual: an in-flight fan-out's queued job references the old func path. Mitigation is BINDING (step 6): a server-boot step deletes the stale `bt:*` job and re-creates it with the new func ref so it still runs (active re-key — we do NOT rely on apscheduler's lazy drop, which would silently lose the job). Severity is Medium — no crash, but the re-key must land on the VPS boot path to avoid dropping a queued backtest.
- Risk: RiskCheckHandler placement — it's a CQRS-style handler but used directly by the engine. Mitigation: place under execution; confirm api DI + mediator registration still resolve it.
- Risk: circular import execution↔infra if a repo imports the engine. Mitigation: repos never import app-services; one-directional execution→infra holds.
- Risk: `di/trading.py` split introduces a missed binding. Mitigation: api boot smoke exercises full DI graph resolution.
