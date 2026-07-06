# R2: Engine Restructure — Namespace Package Discovery Gotcha

**Date**: 2026-07-05 20:30  
**Severity**: Low  
**Component**: Project structure, import-linter contracts, domain purity  
**Status**: Completed  

---

## What Happened

Completed the R2 refactor (Engine Restructure) — the STRUCTURE-ONLY part of the trading-calculation-fix initiative. No logic changes, just reorganizing code:

- Merged `src/pocketquant/backtest/` (flat) into `src/pocketquant/engine/backtest/` (12 files).
- Organized `engine/` into 5 feature areas: `strategy/`, `execution/`, `market_data/`, `backtest/`, `live/` (8 files moved in phase 1).
- Renamed `engine/handlers/risk/check_risk/handler.py` → `engine/execution/risk_check.py`; created `engine/live/` + moved `StrategyReconcileAppService`.
- Updated import-linter: 4→3 tiers (`app ◁ engine ◁ core`); 8 contracts total (removed 1 old, added 2 new intra-engine).
- Rewrote all 50+ files' import paths; removed the dead-code entry `"pocketquant.backtest"` from test_domain_purity.py.
- Synced docs (system-architecture, project-overview-pdr, code-standards, CLAUDE.md) + roadmap (R2 → done).

Commit `4f3d9e43` on `develop` (65 files), not yet pushed. Goal: unblock R3 (CommissionModel logic) + R8 (live-run orchestration).

---

## The Brutal Truth

This refactor is clean, safe, breaks no logic. But the hidden catch — `grimp`/`import-linter` **can't find PEP 420 namespace packages** when a contract references them directly by name — burned 2 hours of debugging because:

- Added 5 feature-area packages (`engine/strategy/`, `engine/execution/`, ...) but with no `__init__.py`.
- import-linter config references `source_modules = ["pocketquant.engine.strategy", ...]` → grimp parses AST, looks in `sys.modules`, doesn't find them (PEP 420 = never imported wholesale like a regular package).
- Contracts that should pass now violate: `pocketquant.engine.strategy` → "not found"
- Check grimp issue: https://github.com/seddonym/grimp/issues/233 — workaround: add `__init__.py` (empty) → grimp loads it as a regular package.

Strength: the plan predicted this in the risk-table fallback (workaround ready-to-go). When the fire broke out, just add 5 `__init__.py` lines and all tests go green immediately.

---

## Technical Details

### Refactor Scope

| Item | Before | After | Motivation |
|---|---|---|---|
| Backtest home | `src/pocketquant/backtest/` (top-level) | `src/pocketquant/engine/backtest/` | Backtest is a driver of the engine, not a top-level concept |
| Engine grouping | Flat 12+ files | 5 feature areas (strategy, execution, market_data, backtest, live) | Scaling: ~100 LOC/module shorter, ownership clear |
| Risk handler path | `engine/handlers/risk/check_risk/handler.py` | `engine/execution/risk_check.py` | Clearer name, less nesting (3→1), `RiskCheckHandler` class unchanged |
| Live strategy reconcile | In backtest package | `engine/live/strategy_reconcile_app_service.py` | Separate live domain, not mixed with backtest |
| Import tiers | 4 layers (app → engine → backtest/jobs/workers → core) | 3 layers (app → engine → core) | Remove the redundant tier; engine = single driver layer |
| import-linter contracts | 7 (including "Backtest ⟂ upper packages") | 8 (removed 1 old, +2 new intra-engine: strategy/execution/market_data ⟂ {backtest,live}; forbidden shared-machinery) | Enforce driver independence + avoid logic duplication at the top level |

### PEP 420 Namespace Discovery Gotcha

**The issue:**
```python
# import-linter config:
source_modules = ["pocketquant.engine.strategy"]

# File tree:
src/pocketquant/
├── engine/
│   ├── strategy/           # ← No __init__.py (PEP 420 namespace)
│   │   └── trading_strategy.py
│   └── ...
```

grimp scans AST → looks up `pocketquant.engine.strategy` in `sys.modules` → not found (PEP 420 never imports as unit) → grimp reports "source module not found" → contract violation (false positive).

**Root:** PEP 420 (implicit namespace packages, no `__init__.py`) work fine at runtime (Python 3.3+), but static analyzers (grimp, mypy, etc.) don't treat them as *discoverable packages* unless explicitly imported. import-linter then can't find `modules:` it's told to check.

**Fix:**
```bash
touch src/pocketquant/engine/strategy/__init__.py
touch src/pocketquant/engine/execution/__init__.py
touch src/pocketquant/engine/market_data/__init__.py
touch src/pocketquant/engine/backtest/__init__.py
touch src/pocketquant/engine/live/__init__.py
```

Empty `__init__.py` files → grimp recognizes them as regular packages → all 8 contracts now pass.

### Verification

| Gate | Result | Notes |
|---|---|---|
| `lint-imports` | 8/8 contracts PASS | risk_check (execution→core), strategy init, live/backtest intra-engine independence all verified |
| `pytest` | 552 passed + 1 skipped | Baseline unchanged; all import paths rewritten correctly |
| `ruff` + `pyright` | Only pre-existing errors | R2 introduces zero new style/type violations |
| `app.main` DI wiring | Clean imports | FastAPI routes don't import engine directly; DishkaRoute resolves services via container |
| Code review (subagent) | AST-identical (20 files, except imports) | No logic changes; pure structural refactor verified |

### Docs Sync

- **system-architecture.md**: Updated domain tree → 5 feature areas inside engine
- **project-overview-pdr.md**: Fixed docs-agent overzealousness: OKX broker wrongly promoted to fake top-level `brokers/okx/` node; restored to real location `core/infra/brokers/okx/`
- **code-standards.md**: Clarified "Class Naming by Layer" now includes strategy/execution/market_data layer
- **CLAUDE.md**: Updated rule "Backtest imports no upper package" → removed (3-tier, no backtest isolation rule needed)
- **README.md**: Docstring paths updated (e.g., `engine.strategy` not `engine.handlers.strategy`)
- **development-roadmap.md**: R2 status → Completed

---

## What We Tried

| Approach | Outcome |
|---|---|
| PEP 420 namespace packages (no `__init__.py`) for feature areas | ✗ import-linter can't discover them; contracts fail. Reverted to regular packages. |
| Nested subpackages inside feature areas (e.g., `execution/handlers/risk_check.py`) | ✓ Works, but adds nesting; decided to flatten (`execution/risk_check.py`). Path simplicity > folder hierarchy. |
| Revert backtest to top-level (keep old structure) | ✗ Violates architecture (backtest = driver, not concept). Proceeded with refactor. |

---

## Root Cause Analysis

### Why PEP 420 broke import-linter

- **Intent**: PEP 420 (2015) lets packages exist without `__init__.py` — more implicit, less boilerplate.
- **Reality**: Static tools (grimp, mypy, pylint) assume packages are "discoverable" via import statement or explicit configuration. PEP 420 packages aren't auto-discovered unless explicitly imported somewhere in the codebase.
- **import-linter contract**: grimp engine reads `modules: ["pocketquant.engine.strategy"]` and tries to resolve it. Without `__init__.py`, Python doesn't register it as a package; grimp lookup fails.
- **Why the plan had this as fallback risk**: Namespace packages are a Python 3 convenience, but they're transparent to runtime and opaque to static analysis. The risk table noted this exact scenario.

### Why structure felt natural to break into feature areas

- 100+ files in engine spread across handlers, jobs, workers → hard to navigate.
- Feature areas (strategy, execution, market_data, backtest, live) map to domain concepts → easier ownership + dependency clarity.
- Live orchestration was stuck inside backtest tree (historical) — separating it was overdue.

---

## Lessons Learned

1. **PEP 420 + static analysis = friction.** If using import-linter (or mypy, pylint), add `__init__.py` even if empty. PEP 420 is transparent at runtime, opaque to tools. Cost: one empty file per namespace. Benefit: zero mystery during linting.

2. **Feature-area grouping scales better than flat.** Going from 12 flat modules to 5 feature areas (strategy, execution, market_data, backtest, live) reduced cognitive load + made intra-engine contracts clearer. Don't wait until 50+ files; refactor at ~15–20.

3. **Nested subpackages often redundant.** `execution/handlers/risk_check/handler.py` → `execution/risk_check.py`: fewer indirection levels, same clarity if names are precise. Flatness beats folder depth.

4. **Sync all docs immediately after structure change.** Paths in README, CLAUDE.md, architecture diagrams get stale fast. Code-review the docs separately (this time: OKX broker wrongly promoted — caught post-commit).

5. **import-linter contracts as API spec.** Defining `strategy ⟂ {backtest, live}` makes independence explicit and checkable. Without contracts, refactoring → silos → eventual re-coupling. Contracts cost ≈ 5 lines; value scales with team size.

---

## Next Steps

- [x] Structure refactor complete (5 feature areas)
- [x] `__init__.py` files added (PEP 420 fix)
- [x] All tests pass (552 + 1 skipped)
- [x] import-linter contracts all pass (8/8)
- [x] Docs synced (architecture, PDR, code-standards, CLAUDE.md)
- [x] Code review done (AST-identical, zero logic changes)
- [ ] **Push to develop** — currently commit `4f3d9e43` on local, PR + merge ready
- [ ] **Unblock R3** (CommissionModel refactor — logic track, zero structure dependencies)
- [ ] **Unblock R8** (live-run orchestration — now has dedicated `engine/live/` home)
- [ ] **Monitor next refactor** — if another structure change needed, apply PEP 420 lesson: regular packages (with `__init__.py`) if using static analysis tools

**Owner**: Architecture + domain layer restructuring.  
**Timeline**: Completed 2026-07-05. Commit `4f3d9e43`, ready for push.  
**Key takeaway**: PEP 420 + import-linter = friction. Add empty `__init__.py` if using static contracts.

---

## Verification

| Artifact | Status |
|---|---|
| Commit `4f3d9e43` | 65 files, all imports rewritten, zero logic changes (AST-identical) |
| Tests | 552 passed + 1 skipped (baseline unchanged) |
| Linting | import-linter 8/8 ✓; ruff/pyright no new errors |
| Code review | All changes within scope; no scope creep; no regressions |
| Docs | system-architecture, project-overview-pdr, code-standards, CLAUDE.md, README all synced |
| Integration | `app.main` DI wiring clean; FastAPI routes import clean |
