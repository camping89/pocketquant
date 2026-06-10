# Lean Monorepo Restructure — Planning Session

**Date**: 2026-06-10 17:26  
**Severity**: Architecture  
**Component**: Package structure, mediator, core domains, routing  
**Status**: Plan Approved

## What Happened

Session 1 brainstorm + debate → plan validation → 5-phase TDD roadmap locked. User pushed back twice on package count ("defend 1 not 3") and mediator kill ("why delete working code"); evidence-based counter (distribution-package-graph vs runtime-module-graph, mediator zero pipeline features) flipped both to leaner option.

## Key Findings

**Package over-engineering verified (codebase audit)**
- 6 Python packages, zero distribution benefit (never published; single Docker image runs both processes)
- FastAPI leaked into 25 files in "library" packages (`backtest`, `trading`, `execution`) — package boundaries failed
- Mediator: 42-line dict dispatch, provides nothing beyond dishka DI decoupling (zero domain behavior)
- Dir-per-endpoint: ~30 endpoints × 3–4 files = 377 py files (121 `__init__.py`, 68 ≤20 LOC) for ~20.5k LOC
- `execution` became market_data CRUD dumping ground; `concepts/` vs `domain/` split arbitrary

## Decisions Locked

| Decision | Target | Rationale |
|----------|--------|-----------|
| Package count | 1 backend (`src/pocketquant`) + subpackages | runtime boundaries via import-linter not wheels; 6→1 eliminates cross-package entropy |
| Internal structure | `core/engine/backtest/trading/app/bff` subpackages | preserves DDD layers; domains + infra collocated |
| Core reshape | `domain/infra/common` (merge `concepts` into `domain`) | simplify taxonomy; 2-tier less arbitrary than 3 |
| Execution→Engine | Rename; backtest queue persists Mongo entities | verified: no class-path serialization; safe |
| Mediator delete | Kill 42-line dict, inject services via dishka | dishka already provides decoupling; 0 pipeline features lost |
| Handler routing | Routes/jobs inject via `FromDishka[Service]` | direct, testable; no dispatch table |
| Phase strategy | Incremental; live trading continues per phase, merge at end | minimize blocking; deploy only at final phase |

## One Interesting Moment

User debate #1 ("convince me 1 package, not 3"):
- I: "6 never gets published; you're building a runtime monolith, not a distribution suite."
- I: "Runtime modules (core, engine, backtest, trading) ≠ distribution packages. Wheels add cost (6 `setup.py`s, 6 version tracks, 6 changelogs) for zero customer benefit."
- Result: user agreed; confirmed 1 backend package with subpackages.

User debate #2 ("why kill a working mediator"):
- I: "42 lines; zero domain logic. Dishka already decouples handlers from services."
- I: "Mediator buys you *generic* message dispatch if you had multiple handler types (events, commands, queries). You don't. Routes + jobs are the only two, both injected directly."
- Result: user agreed; confirmed delete.

Both reversals driven by evidence, not conviction — good sign for buy-in during phases.

## Plan Structure

**5 TDD phases in `plans/260610-1726-lean-monorepo-restructure/`**
1. **Baseline Regression Net** — OpenAPI snapshot, route inventory, mediator registry contract, boot smoke test
2. **Package Merge** — 6 → 1; flatten hierarchy; all tests pass
3. **Core Reshape** — domain/infra/common; concepts merge; import-linter guards
4. **Mediator Kill + Handler Flatten** — delete mediator, flatten dir structure, inject via dishka
5. **FastAPI Containment + Docs Sync** — isolate FastAPI to `app/bff`, kill cross-package imports, update docs

**Validation interview**: 12 claims verified against codebase.
- **1 failed**: "root conftest seeds env" — actually per-package conftests do; fixed in plan.
- **11 passed**: engine rename safe (Mongo entities, no class-path serialization); hitnrun2 pure (no infra imports); FE clients hand-written; keep `*Command/*Query` names in Phase 4 (OpenAPI snapshot byte-identical).

## Emotional Reality

No frustration this session. Consensus felt earned, not coerced. User's pushback was legitimate ("why delete working code"); the fact that evidence flipped both decisions suggests buy-in is real. Planning was smooth; validation tightened one assumption (conftest sourcing) without affecting scope.

## Next Steps

1. Delegate to `code-reviewer` agent: baseline regression net (Phase 1) — characterization tests for current behavior before refactor
2. Per-phase implementation: merge → reshape → mediator kill → containment
3. Per-phase deploy: live trading continues; merge + test only at end of Phase 5
4. Docs sync: Phase 5 updates `CLAUDE.md`, `system-architecture.md` with new structure

---

**Status:** DONE  
**Summary:** User confirmed 1-package structure with 5-phase TDD roadmap. Two evidence-based debates flipped package count (3→1) and mediator deletion; baseline regression net (Phase 1) ready for implementation.
