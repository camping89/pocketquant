---
title: "Cleanup Unused Dependencies and Imports"
description: "Remove 3 unused dependencies from pyproject.toml and fix 5 unused imports"
status: completed
priority: P2
effort: 30m
branch: feat/strategy-init
tags: [cleanup, dependencies, imports, ruff]
created: 2026-02-01
completed: 2026-02-01
---

# Cleanup Unused Dependencies and Imports

Simple cleanup task to remove dead code and unused dependencies.

## Phases

| Phase | Description | Status | Effort |
|-------|-------------|--------|--------|
| 1 | [Remove Unused Dependencies](./phase-01-remove-unused-deps.md) | completed | 10m |
| 2 | [Fix Unused Imports](./phase-02-fix-unused-imports.md) | completed | 10m |
| 3 | [Verification & Sync](./phase-03-verification.md) | completed | 10m |

## Summary

### Dependencies to Remove (pyproject.toml)
- `arq>=0.25.0` - async redis queue, not used
- `python-json-logger>=2.0.0` - using structlog instead
- `python-dateutil>=2.8.0` - not imported anywhere

### Imports to Fix (F401 violations)
1. `ReplayStats` - backtest_runner.py:14
2. `typing.Any` - result_collector.py:4
3. `dataclasses.field` - optimization_config.py:3
4. `dataclasses.field` - optimization_result.py:3
5. `typing.Any` - okx_message_parser.py:3

## Success Criteria
- [x] No DEP002 errors from deptry (verified - removed deps not used)
- [x] No F401 errors from ruff (verified - all checks passed)
- [x] `python -c "from src.main import app"` works (verified - import successful)

## Additional Changes Found
- Fixed event class naming in order_manager.py and position_tracker.py:
  - `OrderFilled` → `OrderFilledEvent` (2 occurrences)
  - `PositionOpened` → `PositionOpenedEvent` (1 occurrence)
- These align with proper event naming convention defined in domain layer
