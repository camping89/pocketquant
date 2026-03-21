# Phase 4: Fix Config .env Path Resolution

## Overview
- **Priority:** P2
- **Status:** completed
- **Risk:** Low — isolated to single file, clear fallback chain

Replace fragile `Path(__file__).resolve().parents[5]` with pyproject.toml workspace discovery.

## File to Modify

### `packages/pocketquant-core/src/pocketquant/core/config.py`

**Before:**
```python
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[5] / ".env"
```

**After:**
```python
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root() -> Path:
    """Find workspace root by walking up to pyproject.toml with [tool.uv.workspace]."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        pyproject = parent / "pyproject.toml"
        if pyproject.exists() and "[tool.uv.workspace]" in pyproject.read_text():
            return parent
    if root := os.environ.get("POCKETQUANT_ROOT"):
        return Path(root)
    raise FileNotFoundError(
        "Cannot find project root. Set POCKETQUANT_ROOT env var or run from workspace."
    )


_ENV_FILE = _find_project_root() / ".env"
```

## Key Decisions
- **pyproject.toml discovery first**: Works out of the box for dev, tests, CI
- **Env var fallback**: For Docker/non-standard layouts where CWD may not be in workspace tree
- **`[tool.uv.workspace]` marker**: Unique to root pyproject.toml — won't match per-package pyproject.toml files

## Verification
```bash
# From project root
uv run python -c "from pocketquant.core.config import get_settings; print(get_settings().app_name)"

# From subdirectory
cd packages/pocketquant-core && uv run python -c "from pocketquant.core.config import get_settings; print(get_settings().app_name)"
```

## Todo
- [x] Replace _ENV_FILE resolution in config.py
- [x] Verify settings load from project root
- [x] Verify settings load from subdirectory
