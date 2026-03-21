---
phase: 5
title: "Validation, Tests, and CI"
status: pending
priority: P1
effort: 3h
---

# Phase 5: Validation, Tests, and CI

## Overview

Final validation: migrate tests, enforce boundaries with import-linter, update CI, update docs.

## Steps

### 5.1 Migrate Tests

Move tests to mirror package structure:

```
tests/
├── core/              ← tests for pocketquant-core
│   ├── domain/
│   ├── common/
│   ├── persistence/
│   └── infrastructure/
├── backtest/          ← tests for pocketquant-backtest
│   ├── domain/
│   ├── engine/
│   └── handlers/
├── trading/           ← tests for pocketquant-trading
│   ├── app_services/
│   ├── brokers/
│   └── handlers/
├── api/               ← tests for pocketquant-api
│   ├── di/
│   ├── market_data/
│   └── integration/
└── conftest.py
```

Update test imports to match new package paths.

### 5.2 Update import-linter Contracts

```toml
[tool.importlinter]
root_packages = ["pocketquant"]

[[tool.importlinter.contracts]]
name = "Core has zero sibling dependencies"
type = "forbidden"
source_modules = ["pocketquant.core"]
forbidden_modules = ["pocketquant.backtest", "pocketquant.trading", "pocketquant.api"]

[[tool.importlinter.contracts]]
name = "Backtest depends only on Core"
type = "forbidden"
source_modules = ["pocketquant.backtest"]
forbidden_modules = ["pocketquant.trading", "pocketquant.api"]

[[tool.importlinter.contracts]]
name = "Trading depends only on Core"
type = "forbidden"
source_modules = ["pocketquant.trading"]
forbidden_modules = ["pocketquant.backtest", "pocketquant.api"]
```

### 5.3 Run Full Validation

```bash
# All packages sync
uv sync

# Type checking
uv run pyright packages/

# Import boundary enforcement
uv run lint-imports

# All tests pass
uv run pytest tests/ -v

# Server starts
uv run --package pocketquant-api uvicorn pocketquant.api.main:create_app --factory --port 8765 &
curl http://localhost:8765/health
```

### 5.4 Update CI/CD

Update GitHub Actions (if exists) to use workspace commands:

```yaml
- run: uv sync
- run: uv run pyright packages/
- run: uv run lint-imports
- run: uv run pytest tests/
```

### 5.5 Update Documentation

Update these docs to reflect new structure:
- `docs/system-architecture.md` — package diagram, dependency graph
- `docs/codebase-summary.md` — new directory structure
- `docs/code-standards.md` — import conventions per package
- `CLAUDE.md` — update domain structure section

### 5.6 Update CLAUDE.md

Key changes:
- Domain imports: `from pocketquant.core.domain.bar import Bar`
- Backtest imports: `from pocketquant.backtest.domain.entities import BacktestResult`
- DI container: `from pocketquant.api.di.container import create_container`
- Package boundary rules

## Todo

- [ ] Migrate test files to new structure
- [ ] Update test imports
- [ ] Update import-linter contracts for new package paths
- [ ] Run lint-imports — all contracts pass
- [ ] Run pyright — 0 errors
- [ ] Run pytest — all tests pass
- [ ] Server starts and health check passes
- [ ] Update CI config
- [ ] Update docs/system-architecture.md
- [ ] Update docs/codebase-summary.md
- [ ] Update CLAUDE.md
- [ ] Final commit

## Success Criteria

- All tests pass
- import-linter: 0 violations
- pyright: 0 errors
- Server starts, all endpoints respond
- Docs reflect new structure
- CI pipeline green
