---
phase: 9
title: "Finalize layered contracts + docs + full sweep"
status: done
priority: P1
effort: "0.5d"
dependencies: [8]
---

# Phase 9: Finalize layered contracts + docs + full sweep

## Overview

Lock the new graph in CI and bring docs to match the as-is system. Rewrite the import-linter contracts for the 6-package layered architecture, update CLAUDE.md + docs to describe the new structure, and run the whole-repo verification sweep.

## Requirements
- Functional: `uv run lint-imports` passes with contracts enforcing `core ◁ infrastructure ◁ execution ◁ {backtest, trading} ◁ api` and forbidding sibling backtest↔trading edges. Full suite + api boot green. Docs describe the 6-package layout as-is (no changelog/migration narrative per Documentation Policy).
- Non-functional: contracts use layered (not just forbidden) checks where it tightens enforcement.

## Architecture

New import-linter contracts (replace the current 3 forbidden sibling contracts + keep bson):
- **Layered contract** (`type = "layered"`): `pocketquant.api` (top) → `pocketquant.backtest`, `pocketquant.trading` (same layer, independent) → `pocketquant.execution` → `pocketquant.infrastructure` → `pocketquant.core` (bottom). Mark backtest/trading as independent (siblings cannot import each other).
- **Forbidden**: `core` may not import infrastructure/execution/backtest/trading/api; `infrastructure` may not import execution/backtest/trading/api; `execution` may not import backtest/trading/api.
- Keep the `bson`/ObjectId forbidden contract (now runnable thanks to Phase 1 `include_external_packages`).

Docs to update (as-is, in place — no "what changed" sections):
- `CLAUDE.md` — Monorepo Structure (5→6 packages), dependency graph, package-imports examples, DI providers list (new ExecutionProvider), "Backtest repos in backtest package" decision now wrong → update to "all repos in infrastructure".
- `docs/system-architecture.md`, `docs/codebase-summary.md` — package boundaries.
- `pyproject.toml` workspace comment if any references 4 Python packages.

## Related Code Files
- Modify: `pyproject.toml` (`[tool.importlinter]` contracts)
- Modify: `CLAUDE.md`, `docs/system-architecture.md`, `docs/codebase-summary.md`, any doc naming the package count/graph
- Modify (Interval consolidation): drop the `Interval` re-export from `core/domain/shared/value_objects.py:3-5` (keep `INTERVAL_SECONDS`, which is NOT in `enums.py`); repoint the ~22 `from pocketquant.core.domain.shared.value_objects import Interval` sites to `...shared.enums import Interval` (grep list: bar/sync_status repos, data_provider, backtest engine, trading loader, and ~15 api market_data handlers/routes). `INTERVAL_SECONDS` imports stay on `value_objects`.
- No other production code changes expected (verification phase) — fix any straggler the sweep finds

## Implementation Steps
1. Rewrite import-linter contracts (layered + forbidden + bson). Run `uv run lint-imports` → must PASS.
2. Whole-plan / whole-repo grep sweep for stragglers: `core.persistence`, `core.infrastructure`, `core.common.{database,cache,jobs}`, `trading.persistence`, `backtest.persistence`, cross-sibling imports, residual `reportPrivateUsage` on injection. All zero.
2b. Consolidate `Interval` to a single import path: remove the `value_objects.Interval` re-export, repoint all `value_objects import Interval` sites to `enums import Interval` (leave `INTERVAL_SECONDS` on `value_objects`). Grep `shared.value_objects import.*Interval\b` → zero after. Pure import-path change (same enum object); deterministic-ID golden test must stay green.
3. Update CLAUDE.md + docs to the 6-package as-is state. Remove the now-false "Backtest repos in backtest package" claim; update DI provider list; fix package-imports examples to new paths.
4. Run full `uv run pytest` (unit + integration), `uv run lint-imports`, `uv run pyright` (type check across moved modules), api boot smoke.
5. Update HTTP test collateral if any path/route changed (`tests/http/*` — likely unaffected; verify backtest run-all-backtests route unchanged for clients).
6. Commit: `refactor: enforce 6-package layered import contracts; sync docs to new architecture`.

## Success Criteria
- [ ] `uv run lint-imports` passes with layered 6-package contracts.
- [ ] Grep sweep: zero stragglers (old paths, sibling edges, private-usage ignores).
- [ ] Full suite + pyright + api boot green.
- [ ] CLAUDE.md + docs describe 6 packages as-is; no false claims (e.g. "backtest repos in backtest").
- [ ] Single `Interval` import path: `grep -rn "shared.value_objects import.*Interval\b" packages/` → 0 (only `INTERVAL_SECONDS` remains on `value_objects`); deterministic-ID golden green.

## Risk Assessment
- Risk: layered contract too strict and flags a legitimate edge (e.g. api → execution directly). Mitigation: api is top layer, may import all lower — layered contract allows downward; verify api's direct execution imports are permitted.
- Risk: pyright surfaces type errors masked during incremental moves. Mitigation: run pyright as an explicit gate here; fix before close.
- Risk: docs drift re-introduced. Mitigation: follow Documentation Policy — state end-state as if always true; no migration/changelog sections.
