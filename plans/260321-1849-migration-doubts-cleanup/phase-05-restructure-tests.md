# Phase 5: Restructure Tests Per-Package

## Overview
- **Priority:** P2
- **Status:** completed
- **Risk:** Medium — most files touched, conftest sharing needs care

Move root `tests/` into per-package test directories. All current tests are core package tests.

## Current Test Layout

```
tests/
├── conftest.py                          → core fixtures (Settings, Mediator, EventBus)
├── unit/
│   ├── common/
│   │   ├── test_event_bus.py            → core
│   │   └── test_mediator.py             → core
│   ├── domain/
│   │   ├── test_domain_purity.py        → core
│   │   └── test_value_objects.py         → core
│   └── infrastructure/
│       └── tradingview/
│           └── test_websocket.py         → core
└── integration/
    └── tradingview/
        └── test_websocket_integration.py → core
```

## Target Layout

```
packages/pocketquant-core/tests/
├── conftest.py
├── unit/
│   ├── common/
│   │   ├── test_event_bus.py
│   │   └── test_mediator.py
│   ├── domain/
│   │   ├── test_domain_purity.py
│   │   └── test_value_objects.py
│   └── infrastructure/
│       └── tradingview/
│           └── test_websocket.py
└── integration/
    └── tradingview/
        └── test_websocket_integration.py
```

Empty test scaffolds for other packages (created but no tests yet):
```
packages/pocketquant-backtest/tests/conftest.py
packages/pocketquant-trading/tests/conftest.py
packages/pocketquant-api/tests/conftest.py
```

## Steps

### 1. Create per-package test directories
```bash
mkdir -p packages/pocketquant-core/tests/unit/common
mkdir -p packages/pocketquant-core/tests/unit/domain
mkdir -p packages/pocketquant-core/tests/unit/infrastructure/tradingview
mkdir -p packages/pocketquant-core/tests/integration/tradingview
mkdir -p packages/pocketquant-backtest/tests
mkdir -p packages/pocketquant-trading/tests
mkdir -p packages/pocketquant-api/tests
```

### 2. Move test files
```bash
# Move all core tests
mv tests/conftest.py packages/pocketquant-core/tests/
mv tests/unit/common/test_event_bus.py packages/pocketquant-core/tests/unit/common/
mv tests/unit/common/test_mediator.py packages/pocketquant-core/tests/unit/common/
mv tests/unit/domain/test_domain_purity.py packages/pocketquant-core/tests/unit/domain/
mv tests/unit/domain/test_value_objects.py packages/pocketquant-core/tests/unit/domain/
mv tests/unit/infrastructure/tradingview/test_websocket.py packages/pocketquant-core/tests/unit/infrastructure/tradingview/
mv tests/integration/tradingview/test_websocket_integration.py packages/pocketquant-core/tests/integration/tradingview/
```

### 3. Update test imports
Test files use `from pocketquant.core.*` imports — these should work unchanged since packages are installed via uv workspace.

`test_domain_purity.py` uses `ast` + `os` to scan files — update the path scanning to use package-relative paths instead of `src/` prefix.

### 4. Update pyproject.toml files

**Root `pyproject.toml`:** Remove `testpaths = ["tests"]` or change to discover per-package:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["packages/pocketquant-core/tests", "packages/pocketquant-backtest/tests", "packages/pocketquant-trading/tests", "packages/pocketquant-api/tests"]
markers = [
    "integration: marks tests as integration tests (require network)",
]
```

**Each package `pyproject.toml`** — no change needed; `uv run --package X pytest` will use root config.

### 5. Create scaffold conftest for other packages

Each gets a minimal conftest.py:
```python
"""Pytest configuration for {package_name} tests."""
```

### 6. Clean up old test directory
```bash
rm -rf tests/
```

### 7. Update `docs/migration-doubts-and-notes.md`
Mark item "Tests Not Migrated" as resolved.

## Verification
```bash
# Run all tests from root
uv run pytest

# Run per-package
uv run pytest packages/pocketquant-core/tests/
```

## Todo
- [x] Create per-package test directories
- [x] Move all test files to pocketquant-core/tests/
- [x] Create scaffold conftest.py for backtest, trading, api
- [x] Update root pyproject.toml testpaths
- [x] Fix test_domain_purity.py path scanning if needed
- [x] Remove old tests/ directory
- [x] Run all tests — verify pass
- [x] Update migration-doubts-and-notes.md — mark all items resolved
