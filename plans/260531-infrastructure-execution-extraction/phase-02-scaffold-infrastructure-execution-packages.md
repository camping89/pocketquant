---
phase: 2
title: "Scaffold infrastructure + execution packages"
status: pending
priority: P1
effort: "0.5d"
dependencies: [1]
---

# Phase 2: Scaffold infrastructure + execution packages

## Overview

Create the two new empty workspace packages with correct `pyproject.toml`, namespace layout, and uv/hatch wiring — before any code lands in them. Inert phase: nothing imports them yet, so the tree stays green.

## Requirements
- Functional: `uv sync` resolves with 6 workspace members; `pocketquant.infrastructure` and `pocketquant.execution` importable (empty namespace). `uv run pytest` unchanged-green.
- Non-functional: match the existing package conventions exactly (PEP 420 namespace — no `__init__.py` at `pocketquant/` level; hatchling build; `pocketquant-core = { workspace = true }` source).

## Architecture

New packages mirror the existing structure (`packages/pocketquant-<name>/src/pocketquant/<name>/`). Dependency declarations encode the target graph:
- `pocketquant-infrastructure` deps: `pocketquant-core` + the heavy adapter libs that will move OUT of core (pymongo, redis, apscheduler, websockets, httpx, cachetools). Core's `pyproject.toml` keeps these for now (removed in Phase 5/6 once nothing in core needs them).
- `pocketquant-execution` deps: `pocketquant-core` + `pocketquant-infrastructure`.

Root `[tool.uv.workspace] members = ["packages/*"]` already globs the new dirs — no root edit needed except the import-linter contracts (Phase 9).

## Related Code Files
- Create: `packages/pocketquant-infrastructure/pyproject.toml`
- Create: `packages/pocketquant-infrastructure/src/pocketquant/infrastructure/` (namespace dir; no top-level `__init__.py` at `pocketquant/`)
- Create: `packages/pocketquant-execution/pyproject.toml`
- Create: `packages/pocketquant-execution/src/pocketquant/execution/`
- Create: `tests/infrastructure_test/`, `tests/execution_test/` (empty dirs + conftest if pattern requires)
- Modify: none in core/backtest/trading/api yet

## Implementation Steps
1. Copy `packages/pocketquant-backtest/pyproject.toml` as the template for both new packages (it's the simplest: hatchling + core workspace source). Adjust `name`, `description`, `dependencies`, `[tool.hatch.build.targets.wheel] packages = ["src/pocketquant"]`.
2. infrastructure `pyproject.toml` deps: `["pocketquant-core", "pymongo>=4.16.0", "redis>=5.0.0", "apscheduler>=3.10.0", "websockets>=12.0", "httpx>=0.26.0", "cachetools>=5.0.0"]` + `[tool.uv.sources] pocketquant-core = { workspace = true }`.
3. execution `pyproject.toml` deps: `["pocketquant-core", "pocketquant-infrastructure"]` + both workspace sources.
4. Create the `src/pocketquant/<name>/` dirs. Add a placeholder module (e.g. `_placeholder.py` or leave the namespace dir with a single `py.typed`) so the wheel target is non-empty; remove placeholder once real modules land.
5. Mirror test scaffolding: create `tests/infrastructure_test/` and `tests/execution_test/` matching the `tests/<pkg>_test/` convention; copy a minimal `conftest.py` only if the suite needs per-package fixtures (check `tests/backtest_test/conftest.py`).
6. Run `uv sync` → expect 6 members resolved. Run `uv run pytest` → unchanged green. Run `uv run lint-imports` → unchanged from Phase 1 (new packages have no imports yet).
7. Commit: `chore: scaffold pocketquant-infrastructure + pocketquant-execution packages`.

## Success Criteria
- [ ] `uv sync` resolves 6 workspace members.
- [ ] `python -c "import pocketquant.infrastructure, pocketquant.execution"` succeeds.
- [ ] `uv run pytest` green; `lint-imports` state unchanged from Phase 1.

## Risk Assessment
- Risk: empty wheel target fails hatchling build. Mitigation: placeholder module / `py.typed` until real code lands.
- Risk: PEP 420 namespace broken by stray `__init__.py` at `pocketquant/`. Mitigation: verify no `pocketquant/__init__.py` exists in new packages (match core's layout).
- Risk: duplicate dep versions drift from core. Mitigation: copy exact version pins from `packages/pocketquant-core/pyproject.toml`.
