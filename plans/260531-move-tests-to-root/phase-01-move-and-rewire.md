---
phase: 1
title: "Move and Rewire"
status: completed
priority: P2
effort: "30m"
dependencies: []
---

# Phase 1: Move and Rewire

## Overview

`git mv` the 4 package test trees to root `tests/<pkg>_test/`, then update the 6
touchpoints that reference the old paths. No file contents change except path
strings in config/docs.

## Requirements

- Functional: every test file + its `conftest.py` + `__init__.py` + nested
  subdirs land under the new path. api's `integration/` package structure stays
  intact (relative imports `from .app_factory import make_test_app`).
- Non-functional: git history preserved (`git mv`, not delete+add). Zero edits to
  test logic or `src/`.

## Architecture

Target layout:

```
tests/
├── conftest.py              # existing — workspace root → sys.path (UNCHANGED)
├── core_test/               # ← packages/pocketquant-core/tests/
├── backtest_test/           # ← packages/pocketquant-backtest/tests/
├── trading_test/            # ← packages/pocketquant-trading/tests/
├── api_test/                # ← packages/pocketquant-api/tests/
│   └── integration/         #   __init__.py + app_factory.py preserved
├── scripts/  manual/  http/ # existing (UNTOUCHED)
```

`--import-mode=importlib` (already set) disambiguates duplicate subdir names
(`unit/`, `integration/`) across the now-unique top-level `*_test/` roots.

## Related Code Files

- Move (`git mv`):
  - `packages/pocketquant-core/tests` → `tests/core_test`
  - `packages/pocketquant-backtest/tests` → `tests/backtest_test`
  - `packages/pocketquant-trading/tests` → `tests/trading_test`
  - `packages/pocketquant-api/tests` → `tests/api_test`
- Modify:
  - `pyproject.toml` — `[tool.pytest.ini_options] testpaths` → `["tests"]`
  - `pyrightconfig.json` — `include` (4 entries) + `executionEnvironments` (4 roots)
  - `justfile` — `test-pkg` recipe path
  - `.github/workflows/cicd.yml` — pytest path (api smoke only)
  - `docs/code-standards.md:595` — backward-compat test path ref
  - `docs/system-architecture.md:533` — domain purity test path ref

## Implementation Steps

1. **Pre-clean stale caches** (avoid ghost collection from old `__pycache__`):
   ```bash
   find packages tests -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null; true
   ```
2. **Baseline count** — record for parity check in Phase 2:
   ```bash
   uv run pytest --collect-only -q 2>/dev/null | tail -1
   ```
3. **Move trees** (run from workspace root):
   ```bash
   git mv packages/pocketquant-core/tests     tests/core_test
   git mv packages/pocketquant-backtest/tests tests/backtest_test
   git mv packages/pocketquant-trading/tests  tests/trading_test
   git mv packages/pocketquant-api/tests      tests/api_test
   ```
4. **`pyproject.toml`** — replace the 5-entry `testpaths` list with:
   ```toml
   testpaths = ["tests"]
   ```
   (root `tests/` globs all subtrees including `scripts/`; collection unchanged.)
5. **`pyrightconfig.json`** — in `include`, swap the 4
   `packages/pocketquant-<pkg>/tests` entries for `tests/<pkg>_test`. In
   `executionEnvironments`, swap the 4 `root` values likewise (keep
   `reportPrivateUsage: none` on each).
6. **`justfile`** — `test-pkg` recipe:
   ```
   test-pkg pkg:
       {{python}} -m pytest tests/{{pkg}}_test/
   ```
7. **`.github/workflows/cicd.yml`** — change
   `uv run pytest packages/pocketquant-api/tests/ -v` →
   `uv run pytest tests/api_test/ -v` (CI scope stays api-only smoke per decision).
8. **Docs** — update the two hard-coded paths:
   - `code-standards.md:595` `packages/pocketquant-trading/tests/test_subscription_deterministic_id.py`
     → `tests/trading_test/test_subscription_deterministic_id.py`
   - `system-architecture.md:533` `core/tests/unit/domain/test_domain_purity.py`
     → `tests/core_test/unit/domain/test_domain_purity.py`

## Success Criteria

- [x] 4 `tests/<pkg>_test/` dirs exist; `packages/*/tests/` gone.
- [x] `git status` shows renames (R), not delete+add, for moved files. (71 R, 0 D)
- [x] `pyproject.toml`, `pyrightconfig.json`, `justfile`, `cicd.yml` reference new paths only.
- [x] No remaining grep hit for `packages/pocketquant-.*tests` in toml/json/yml/justfile/docs. (also fixed 3 doc + 1 conftest-docstring refs beyond the plan's 2)

## Risk Assessment

- **Relative imports break** → mitigated: `__init__.py` travels with `git mv`; dir
  stays a package. Verified in Phase 2 by collect + run.
- **`git mv` rename-detection threshold** → low risk for whole-dir move; confirm via
  `git status` rename markers.
- **Missed reference** → final grep sweep in step success criteria + Phase 2 collect.
