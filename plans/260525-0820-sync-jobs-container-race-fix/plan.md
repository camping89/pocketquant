---
title: "Fix sync_jobs container init race during container restart"
status: in_progress
priority: P1
branch: develop
tags: [bugfix, scheduler, deploy]
created: 2026-05-25T01:35:00Z
---

# Fix sync_jobs container init race during container restart

## Context

Observed in prod `job_history`:
- 2026-05-23T04:00:00Z: `sync_integrity` failed with `sync_jobs container not initialized`
- 2026-05-25T01:30:02Z (during my redeploy): `sync_1m` failed with same error; 01:31:02 recovered

Prior fix `45e2d7f` hoisted `set_sync_container(container)` BEFORE `await container.get(JobScheduler)` inside `start_background_jobs()`. Race narrowed but not closed: a prior `await` (`container.get(Settings)`) yields control after Dishka's lifespan has already resolved JobScheduler (via `rehydrate_strategies_from_subscriptions` → StrategyAppService deps, or other earlier `container.get(...)` chains). Once the scheduler is started, persisted MongoDBJobStore jobs whose `next_run_time` is within `misfire_grace_time` dispatch and crash on the unwired `_container`.

## Fix

Hoist `set_sync_container(container)` AND `set_backtest_container(container)` to the **first lines of `lifespan()`** in `main.py` — before ANY `await`. Wiring is synchronous (just `global _container = container`), so no risk of yielding.

This guarantees: regardless of when/where JobScheduler is first resolved by Dishka, the sync_jobs module-level container is already non-None when any persisted job dispatches.

## Scope

- Modify: `packages/pocketquant-api/src/pocketquant/api/main.py` — add early imports + call at top of `lifespan()`
- Modify: `packages/pocketquant-api/src/pocketquant/api/main_extensions.py` — remove now-redundant `set_*_container` calls in `start_background_jobs()`; keep `register_sync_jobs` flow

## Steps

1. Add module-top imports in `main.py`: `set_container as set_sync_container` from `sync_jobs`, `set_container as set_backtest_container` from `backtest_jobs`.
2. In `lifespan()`, after `container = app.state.dishka_container`, add:
   ```python
   set_sync_container(container)
   set_backtest_container(container)
   ```
   (Before the `try:` block. Synchronous — no awaits.)
3. In `main_extensions.py:start_background_jobs()`:
   - Remove the lazy imports of `set_backtest_container` and `set_sync_container`
   - Remove the calls (already done at lifespan top)
   - Keep `register_sync_jobs(...)` and the `enable_jobs` gate
4. Add a 1-line comment in `lifespan()` explaining the WHY ("must happen before any await — JobScheduler can resolve + start during Dishka container.get() chains, racing persisted MongoDBJobStore dispatches").

## Validation

- `pyright` on `pocketquant-api` package — no new errors
- Local app boot smoke (skip — env not configured for full app boot locally)
- Post-deploy: query `job_history` for `sync_jobs container not initialized` during the restart window — must be ZERO
- Run a second redeploy after fix lands to stress-test the race

## Success Criteria

- [ ] `set_sync_container` + `set_backtest_container` invoked before any `await` in `lifespan`
- [ ] `start_background_jobs` no longer contains those calls
- [ ] pyright clean
- [ ] Deploy succeeds; verify.sh HEALTHY
- [ ] No `sync_jobs container not initialized` error in `job_history` in the 5min post-redeploy window

## Risks

- **Circular import:** unlikely — `main.py` already imports from `pocketquant.api.market_data...` chain; `sync_jobs.py` doesn't import from `main`.
- **Test breakage:** `test_sync_jobs_phase.py` may directly call `set_container`; should be unaffected (function unchanged).
