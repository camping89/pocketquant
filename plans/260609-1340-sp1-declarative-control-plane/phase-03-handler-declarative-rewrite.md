---
phase: 3
title: "Handler Declarative Rewrite"
status: completed
priority: P1
effort: "5h"
dependencies: [1]
---

# Phase 3: Handler Declarative Rewrite

## Overview

Rewrite the run-state mutation path of the strategy handlers to write `desired_state` to Mongo instead of poking RAM directly. `start`/`stop` become pure DB writes (drop `StrategyAppService` dependency entirely). `add_symbol`/`remove_symbol`/`delete` keep instance lifecycle but set desired-state consistently. `list_symbols` reads `actual_state` from DB instead of RAM. This is the change that makes the 6 handlers SP3-ready (handler ↔ runtime boundary = Mongo only).

## Requirements

- Functional, per handler:
  - **start** (`StartStrategyHandler`): `sub_repo.update_desired_state(sub_id, "running")`. NO `start_strategy` call. Return True. If sub missing (modified_count==0) → raise `NotFoundError` (new behavior; currently start on unknown id raises ValueError from RAM — preserve a 404-ish failure).
  - **stop** (`StopStrategyHandler`): `sub_repo.update_desired_state(sub_id, "stopped")`. NO `stop_strategy`. Return True. Missing sub → `NotFoundError`.
  - **add_symbol** (`AddSymbolHandler`): keep tracked-symbol check + registry lookup + `load_strategy` (instance must exist for reconcile to start it). Persist sub with `desired_state` per **decision below**. Do NOT call `start_strategy` here — reconcile does it.
  - **remove_symbol** (`RemoveSymbolHandler`): unchanged cascade (cancel bt job, unload instance, delete backtest, delete sub). Deleting the sub row removes it from reconcile's view → no desired-state needed. Keep `unload_strategy` so RAM is freed immediately (don't wait a tick).
  - **delete** (`DeleteStrategyHandler`): unchanged cascade for all subs of a template.
  - **list_symbols** (`ListSymbolsHandler`): replace `_is_running` (RAM read) with `actual_state` from the sub doc. Add `desired_state` to the returned dict. Keep `is_running` key for FE back-compat, derived as `actual_state == "running"`.
- Non-functional:
  - start/stop handlers no longer import/inject `StrategyAppService` → fewer deps, SP3-clean.
  - Behavior parity for add/remove/delete cascades (characterization-locked).

## Architecture

### add_symbol desired_state decision

Current `add_symbol` loads the instance but the OLD code path relied on a separate `POST /start`. Two options:
- **(A) persist `desired_state="stopped"`** — add = subscribe only; human must Start. Matches old 2-step UX (add then start).
- **(B) persist `desired_state="running"`** — add = subscribe + auto-run on next reconcile tick.

**Plan picks (A) `stopped`** — preserves current two-step semantics (the start/stop endpoints exist and FE uses them), avoids surprise auto-trading on add. Flag to user if (B) preferred. This is independent of the *migration* default (running) which is a one-time backfill of pre-existing subs.

### start/stop dependency drop

`StartStrategyHandler.__init__` / `StopStrategyHandler.__init__` change from `(strategy_app_service)` to `(subscription_repository)`. Update the DI HandlerProvider wiring (Phase 4 verifies container resolves). Commands unchanged (`subscription_id`).

### list_symbols state source

`actual_state` is written by the reconcile loop (Phase 2). Between a desired-state write and the next reconcile tick (≤5s), `actual_state` lags `desired_state` — that's the correct "converging" signal. FE can show desired vs actual to render a transitional state (optional, FE work out of scope).

## Related Code Files

- Modify: `packages/pocketquant-trading/src/pocketquant/trading/handlers/strategy/start/handler.py`
- Modify: `packages/pocketquant-trading/src/pocketquant/trading/handlers/strategy/stop/handler.py`
- Modify: `packages/pocketquant-trading/src/pocketquant/trading/handlers/strategy/add_symbol/handler.py`
- Modify: `packages/pocketquant-trading/src/pocketquant/trading/handlers/strategy/list_symbols/handler.py`
- Keep (verify only): `remove_symbol/handler.py`, `delete/handler.py` (cascade unchanged)
- Modify: DI `packages/pocketquant-api/src/pocketquant/api/di/handlers.py` (start/stop constructor deps) — verify exact provider file in Phase 4.
- Create: `tests/trading_test/test_strategy_handlers_declarative.py`

## Implementation Steps

1. **TEST FIRST** — `tests/trading_test/test_strategy_handlers_declarative.py` (use container `settings` fixture + real `SubscriptionRepository`, fake/AsyncMock for scheduler + bt repo where needed):
   - `StartStrategyHandler.handle(StartStrategyCommand(sub_id))` on existing sub → `desired_state=="running"` in DB; no `start_strategy` invoked (handler has no strategy_service).
   - start on missing sub → `NotFoundError`.
   - `StopStrategyHandler` symmetric → `desired_state=="stopped"`.
   - `add_symbol` → sub persisted with `desired_state=="stopped"`, instance loaded (`get_strategy(sub.id)` not None), `start_strategy` NOT called.
   - `list_symbols` returns `desired_state` + `actual_state` + `is_running == (actual_state=="running")`, sourced from DB (set `actual_state="running"` via repo, assert reflected without any RAM instance running).
2. **Characterization lock** (behavior parity) — extend or add tests so remove/delete cascades still: cancel `bt:{id}` job, unload instance, delete backtest docs, delete sub row. Reuse existing `tests/trading_test/test_strategy_position_and_trade_handlers.py` patterns; add cases if cascade not already covered.
3. Rewrite `start/handler.py`: inject `SubscriptionRepository`; `update_desired_state(request.subscription_id, "running")`; raise `NotFoundError` if 0 modified; return True. Drop `StrategyAppService` import.
4. Rewrite `stop/handler.py`: symmetric with `"stopped"`.
5. Edit `add_symbol/handler.py`: construct `Subscription(..., desired_state="stopped", actual_state="stopped")`; keep load; ensure no `start_strategy`. (Subscription defaults already `stopped` from Phase 1 — can rely on defaults, but pass explicitly for readability.)
6. Edit `list_symbols/handler.py`: drop `_is_running` RAM read + `strategy_app_service` dep; return `desired_state`, `actual_state`, `is_running=sub.actual_state=="running"`. Removing the dep means dropping it from constructor + DI wiring — verify nothing else uses it.
7. Verify `remove_symbol` + `delete` unchanged (read, confirm cascade intact). No edit unless test reveals a gap.
8. Run `just test-pkg trading` → green. `just lint` + `just types`.

## Success Criteria

- [ ] start/stop handlers write `desired_state` only, no RAM call, no `StrategyAppService` dependency.
- [ ] start/stop on missing sub → `NotFoundError`.
- [ ] add_symbol persists `desired_state="stopped"`, loads instance, does not auto-start.
- [ ] list_symbols sources state from DB (`actual_state`); `is_running` derived; no RAM read.
- [ ] remove/delete cascades behavior-unchanged (characterization green).
- [ ] trading suite green; lint + types clean.

## Risk Assessment

- **start/stop now async-eventual, not immediate**: clicking Start returns before the strategy actually runs (reconcile converges ≤5s later). This is the declarative model by design. Document in handler docstring (WHY). FE already polls list_symbols, so it observes `actual_state` catch up.
- **Dropping `StrategyAppService` from list_symbols**: if any other consumer relied on its presence in that handler's DI, resolution breaks. Mitigation: grep for the provider, run full container resolution test in Phase 4.
- **add_symbol default (A) stopped vs migration default (running)**: intentional asymmetry — migration auto-resumes EXISTING running subs; new adds start stopped (no surprise). Documented; flag to user if they want new-adds to auto-run.
- **NotFoundError on start/stop is new**: old RAM path raised `ValueError("Strategy not found")` for unloaded ids. Switching to `NotFoundError` (maps to 404) is stricter/cleaner. Confirm exception handler maps it; locked by test.
