---
phase: 3
title: "Promote persisted entities to core"
status: done
priority: P1
effort: "1d"
dependencies: [2]
---

# Phase 3: Promote persisted entities to core

## Overview

Move every persisted domain entity that currently lives OUTSIDE core into core's domain tree, so their repositories can later live in infrastructure (which cannot import backtest/trading domain). This is the "repo follows entity" enabler. No repos move yet — only entities + their import sites re-point.

## Requirements
- Functional: `BacktestResult`, `OptimizationResult` + all backtest VOs (`BacktestMetrics`, `EquityPoint`, `Fill`, `OpenLot`, `OptimizationResultEntry`, `Order`, `Trade`) and `Subscription` (+ `SubscriptionAlreadyExistsError`) live under `pocketquant.core.domain.*`. All consumers import from core. Behavior identical (deterministic-ID characterization test from Phase 1 still green).
- Non-functional: backtest **services** (`performance_calculator.py`, numpy-only, NOT persisted) STAY in the backtest package — only persisted entities/VOs promote.

## Architecture

Target core domain placement (follow existing three-tier DDD layout in CLAUDE.md):
- `core/domain/backtest/` — new top-level domain folder: `entities.py` (BacktestResult, OptimizationResult), `value_objects.py` (Fill, OpenLot, EquityPoint, Trade, Order, BacktestMetrics, OptimizationResultEntry). **Consolidate the current `backtest/domain/value_objects/*.py` per-file split into a SINGLE `value_objects.py` (user decision — overrides the >200 LOC modularization guideline for this module; ~340 LOC in one file is accepted). Do NOT create a `value_objects/` dir.**
- `core/domain/subscription/` — new top-level: `entities.py` (Subscription), with `SubscriptionAlreadyExistsError` (subclass of `core.common.exceptions.DomainError` — already its base, clean).

Coupling notes from scout:
- `backtest/domain/value_objects/order.py:17` imports `OrderEvent` from `core.infrastructure.brokers.events`. After Phase 4 `OrderEvent` lives in core DTOs; in THIS phase keep importing from current location (still `core.infrastructure...`) to avoid coupling two moves — Phase 4 re-points it. Document the temporary import.
- `fill.py:9`, `order.py:16` already import `core.domain.order.enums` — stays valid (moving up into core, same-or-shorter path).
- `Subscription` imports `core.common.exceptions.DomainError` + `core.domain.shared.enums.Interval` — both already in core. Clean promotion.

## Related Code Files
- Create: `packages/pocketquant-core/src/pocketquant/core/domain/backtest/{__init__.py,entities.py,value_objects.py}` (single `value_objects.py`, not a dir)
- Create: `packages/pocketquant-core/src/pocketquant/core/domain/subscription/{__init__.py,entities.py}`
- Delete: `packages/pocketquant-backtest/src/pocketquant/backtest/domain/entities.py`, `domain/value_objects/*` (persisted VOs) — keep `domain/services/performance_calculator.py` and `domain/services/__init__.py`
- Delete: `packages/pocketquant-trading/src/pocketquant/trading/domain/subscription.py`
- Modify (re-point imports): backtest `engine/*` (`collected_results.py:11`, `backtest_app_service.py:4`, `metrics_builder.py:11`, `result_collector.py:20`), backtest `persistence/*` repos, `domain/value_objects/order.py` consumers; trading `persistence/subscription_repository.py:5`, `domain/__init__.py`, `handlers/strategy/add_symbol/handler.py`; api DI + handlers referencing these.
- Move test dirs: `tests/backtest_test/domain/` → `tests/core_test/unit/domain/backtest/`; add `tests/core_test/unit/domain/subscription/`.

## Implementation Steps
1. Create `core/domain/backtest/` and `core/domain/subscription/`. Port entity + VO source verbatim EXCEPT: (a) module-internal import paths change (`pocketquant.backtest.domain.value_objects.X` → `pocketquant.core.domain.backtest.value_objects` / relative); (b) scrub plan/phase references from ported docstrings — `backtest/domain/entities.py:12-14` carries "After Phase 4 of the storage refactor, fills go to `backtest_orders.fills[]`…" which (i) violates the repo's no-plan-refs-in-code rule and (ii) collides ambiguously with THIS plan's Phase 4. Rewrite to describe the current storage layout as a stable fact. (c) Keep `Subscription` importing `Interval` from `pocketquant.core.domain.shared.enums` (the canonical source). NOTE: `core.domain.shared.value_objects.Interval` is only a `# noqa: F401` re-export of the same enum object — there is ONE enum, not two, so the move carries no `_id`-rekey risk. The full consolidation to a single import path (drop the re-export, repoint ~22 sites) is done in Phase 9; do not introduce NEW `value_objects.Interval` imports here.
2. Keep `backtest/domain/services/performance_calculator.py` in place; update its import `from pocketquant.backtest.domain import BacktestMetrics, EquityPoint, Trade` → `from pocketquant.core.domain.backtest import ...`.
3. Grep every consumer of `pocketquant.backtest.domain` and `pocketquant.trading.domain.subscription` (scout found: 20 internal backtest files, trading add_symbol handler, both repos). Re-point each to `pocketquant.core.domain.backtest` / `core.domain.subscription`.
4. Update `backtest/domain/__init__.py` to re-export from core (transitional shim) OR delete and fix consumers directly — prefer direct fix (DRY, no shim debt). Same for `trading/domain/__init__.py`.
5. Leave `OrderEvent` import in `core/domain/backtest/value_objects.py` pointing at `core.infrastructure.brokers.events` for now (Phase 4 moves OrderEvent into core DTOs and re-points). NOTE: `backtest/domain/value_objects/__init__.py:17` re-exports `OrderEvent` in `__all__` (documented public path `from pocketquant.backtest.domain import OrderEvent`, `order.py:4-6`). **BINDING (user decision — Direct fix, DRY): do NOT carry an `OrderEvent` alias re-export into `core.domain.backtest`.** Grep `from pocketquant.backtest.domain import` (capturing the `OrderEvent` alias) across all packages + tests and re-point every consumer to the true source directly. The alias path breaks at this phase's module deletion independent of Phase 4's re-point, so all alias consumers must be fixed here. No shim/re-export debt.
6. Move the backtest domain tests to `tests/core_test/unit/domain/backtest/`; add subscription entity tests. Update test imports.
7. Run Phase 1 deterministic-ID characterization test → must still pass (golden literal unchanged). Run full `uv run pytest`. Run `uv run lint-imports` (sibling violations from backtest↔trading may shift but entities-in-core is legal).
8. Commit: `refactor: promote backtest + subscription persisted entities to core domain`.

## Success Criteria
- [ ] `pocketquant.core.domain.backtest` and `core.domain.subscription` hold all promoted entities/VOs.
- [ ] No remaining `pocketquant.backtest.domain.entities` / `trading.domain.subscription` modules.
- [ ] `performance_calculator.py` still in backtest package, imports from core.
- [ ] Deterministic-ID golden test green; full suite green.

## Risk Assessment
- Risk: `Order` VO name collides with `core.domain.order.OrderAggregate` concepts — they're distinct (backtest `Order` is a result-record VO). Mitigation: keep `Order` under `core.domain.backtest` namespace; do NOT merge into `core.domain.order`.
- Risk: circular import if `core.domain.backtest.value_objects` imports `core.infrastructure...OrderEvent` while infrastructure isn't fully separated. Mitigation: OrderEvent currently lives in core (`core.infrastructure.brokers.events`) — same package, no cycle; resolved cleanly in Phase 4.
- Risk: missed consumer import → ImportError at boot. Mitigation: grep sweep + full suite + api boot smoke.
