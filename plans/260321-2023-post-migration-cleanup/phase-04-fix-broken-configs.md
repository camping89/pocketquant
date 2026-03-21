# Phase 4: Fix Broken Configs

**Priority:** Critical | **Status:** Complete | **Effort:** 30m

## Overview

6 config files reference the old monolith `src/` structure. Fix all to work with the 4-package monorepo.

## Depends On

- Phase 2 (TOML audit may reveal additional issues)
- Phase 3 (justfile refs scripts that moved)

## Files to Modify

### 1. `scripts/check_env.py`

**Problem:** `from src.config import get_settings` -- old monolith import.

**Fix:**
```python
# OLD
from src.config import get_settings
# NEW
from pocketquant.core.config import get_settings
```

Two occurrences (lines 15 and 35). Both need updating.

---

### 2. `pyrightconfig.json`

**Problem:** `"include": ["src", "tests"]` -- neither path exists at root.

**Fix:**
```json
{
  "include": [
    "packages/pocketquant-core/src",
    "packages/pocketquant-backtest/src",
    "packages/pocketquant-trading/src",
    "packages/pocketquant-api/src",
    "packages/pocketquant-core/tests",
    "packages/pocketquant-backtest/tests",
    "packages/pocketquant-trading/tests",
    "packages/pocketquant-api/tests"
  ],
  "venvPath": ".",
  "venv": ".venv",
  "pythonVersion": "3.14",
  "typeCheckingMode": "standard",
  "reportMissingImports": "error",
  "reportMissingModuleSource": "error",
  "reportUnusedImport": "error",
  "reportUnusedVariable": "error",
  "reportMissingTypeStubs": "none",
  "reportPrivateUsage": "error",
  "executionEnvironments": [
    {
      "root": "packages/pocketquant-core/tests",
      "reportPrivateUsage": "none"
    },
    {
      "root": "packages/pocketquant-api/tests",
      "reportPrivateUsage": "none"
    },
    {
      "root": "packages/pocketquant-backtest/tests",
      "reportPrivateUsage": "none"
    },
    {
      "root": "packages/pocketquant-trading/tests",
      "reportPrivateUsage": "none"
    }
  ]
}
```

Note: Root `pyproject.toml` already has `[tool.pyright]` section. The `pyrightconfig.json` takes precedence for `include`/`executionEnvironments` which can't go in pyproject.toml. Keep both -- they complement each other.

---

### 3. `.vscode/settings.json`

**Problem:** `"python.analysis.extraPaths": ["${workspaceFolder}/src"]` -- `src/` doesn't exist.

**Fix:** Remove extraPaths entirely. With `uv sync`, all packages are installed editable in `.venv`, so Pylance resolves imports via the venv. No extra paths needed.

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/Scripts/python.exe",
  "python.analysis.typeCheckingMode": "standard",
  "python.analysis.diagnosticMode": "workspace",
  "python.analysis.autoSearchPaths": true
}
```

---

### 4. `.vscode/launch.json`

**Problem:** `"args": ["src.main:app", ...]` -- old monolith path, wrong port.

**Fix:**
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: FastAPI",
      "type": "debugpy",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "pocketquant.api.main:app",
        "--reload",
        "--host", "0.0.0.0",
        "--port", "41920"
      ],
      "cwd": "${workspaceFolder}",
      "envFile": "${workspaceFolder}/.env"
    },
    {
      "name": "Python: Current File",
      "type": "debugpy",
      "request": "launch",
      "program": "${file}",
      "cwd": "${workspaceFolder}",
      "console": "integratedTerminal",
      "envFile": "${workspaceFolder}/.env"
    }
  ]
}
```

Changes:
- `src.main:app` -> `pocketquant.api.main:app`
- Port `8765` -> `41920` (matches Dockerfile/compose healthcheck)

---

### 5. `justfile`

**Problem:** `uv pip install -e ".[dev]"` (monolith install), refs nonexistent `test_mongodb_auth.py`.

**Fix:**
```just
# PocketQuant Development Tasks
# Requires: just, docker, uv (https://docs.astral.sh/uv/)

set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

python := if os() == "windows" { ".venv/Scripts/python.exe" } else { ".venv/bin/python" }

default:
    @just --list

# Setup: create venv and install all workspace packages
install:
    uv sync

# Start infrastructure (MongoDB + Redis)
up:
    docker compose -f docker/compose.yml up -d

# Stop infrastructure
down:
    docker compose -f docker/compose.yml down

# Reset everything: stop containers and delete all data volumes
reset:
    docker compose -f docker/compose.yml down -v

# Check development environment (docker, mongodb, redis)
check:
    {{python}} scripts/check_env.py

# Run all tests
test:
    {{python}} -m pytest

# Run tests for a specific package (core, backtest, trading, api)
test-pkg pkg:
    {{python}} -m pytest packages/pocketquant-{{pkg}}/tests/

# Lint check
lint:
    ruff check .

# Format code
fmt:
    ruff format .

# Type check
types:
    pyright

# Run lint + format + type check
qa: lint fmt types

# Start dev server with hot reload
dev:
    uvicorn pocketquant.api.main:app --reload --host 0.0.0.0 --port 41920
```

Changes:
- `uv pip install -e ".[dev]"` -> `uv sync`
- Removed `test_mongodb_auth.py` ref from `check`
- Added `test`, `test-pkg`, `lint`, `fmt`, `types`, `qa`, `dev` recipes

---

### 6. `packages/pocketquant-api/pyproject.toml` (script entry)

**Problem:** `[project.scripts] pocketquant = "pocketquant.api.main:run"` -- `run()` function does not exist.

**Fix options (pick one):**

**Option A (recommended):** Add a `run()` function to `main.py`:
```python
def run() -> None:
    """CLI entrypoint for `pocketquant` command."""
    import uvicorn
    uvicorn.run("pocketquant.api.main:app", host="0.0.0.0", port=41920)
```

**Option B:** Remove the `[project.scripts]` section entirely.

Recommend Option A -- it enables `pocketquant` CLI command after install, useful for Docker CMD.

## Implementation Steps

1. Fix `scripts/check_env.py` imports
2. Rewrite `pyrightconfig.json`
3. Fix `.vscode/settings.json`
4. Fix `.vscode/launch.json`
5. Rewrite `justfile`
6. Add `run()` to `packages/pocketquant-api/src/pocketquant/api/main.py`
7. Run `uv sync` to verify install works
8. Run `just check` to verify check_env.py works

## Success Criteria

- [x] `scripts/check_env.py` imports from `pocketquant.core.config`
- [x] `pyrightconfig.json` includes all 4 package source dirs
- [x] `.vscode/settings.json` has no `extraPaths`
- [x] `.vscode/launch.json` uses `pocketquant.api.main:app`
- [x] `justfile` uses `uv sync`, no dead refs
- [x] `pocketquant` CLI command works (if Option A chosen)
- [x] `just check` runs without import errors
