# Phase 5: Dockerfile Rewrite

**Priority:** High | **Status:** Complete | **Effort:** 30m

## Overview

Current Dockerfile copies `src/` and runs `src.main:app` -- completely broken for the monorepo. Rewrite as monorepo-aware multi-stage build using uv workspace.

## Current State (Broken)

```dockerfile
# Builder: uv pip install -e .  (monolith single-package)
# Runtime: COPY src/ src/
# CMD: python -m uvicorn src.main:app
```

## Files to Modify

- `Dockerfile` (full rewrite)

## New Dockerfile

```dockerfile
# ============================================
# Stage 1: Builder
# ============================================
FROM python:3.14-rc-slim AS builder

WORKDIR /app

# Install system deps for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy workspace definition + lock first (cache layer)
COPY pyproject.toml uv.lock README.md ./

# Copy all package pyproject.toml files (needed for dependency resolution)
COPY packages/pocketquant-core/pyproject.toml packages/pocketquant-core/
COPY packages/pocketquant-backtest/pyproject.toml packages/pocketquant-backtest/
COPY packages/pocketquant-trading/pyproject.toml packages/pocketquant-trading/
COPY packages/pocketquant-api/pyproject.toml packages/pocketquant-api/

# Copy all package source code
COPY packages/ packages/

# Install all workspace packages (locked, no dev deps)
RUN uv sync --frozen --no-dev

# ============================================
# Stage 2: Runtime
# ============================================
FROM python:3.14-rc-slim AS runtime

WORKDIR /app

# Install runtime deps (git needed for tvdatafeed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 appuser

# Copy venv from builder (uv sync creates .venv in workdir)
COPY --from=builder /app/.venv /app/.venv

# Set environment
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:41920/health || exit 1

EXPOSE 41920

CMD ["uvicorn", "pocketquant.api.main:app", "--host", "0.0.0.0", "--port", "41920"]
```

## Key Differences from Old Dockerfile

| Aspect | Old (Broken) | New |
|--------|-------------|-----|
| Install | `uv pip install -e .` | `uv sync --frozen --no-dev` |
| Source copy | `COPY src/ src/` | `COPY packages/ packages/` |
| Venv location | `/opt/venv` | `/app/.venv` (uv default) |
| CMD | `python -m uvicorn src.main:app` | `uvicorn pocketquant.api.main:app` |
| Layer caching | Single pyproject.toml | Workspace + package tomls first, then source |

## Design Decisions

- **`uv sync --frozen --no-dev`**: Uses lockfile, skips dev deps (ruff, pytest, etc.)
- **No separate source COPY in runtime**: `uv sync` installs packages as editable into `.venv`, so all source is accessible via the venv. Alternatively, if non-editable install is preferred, the packages are installed as proper packages in site-packages.
- **Layer caching**: pyproject.toml files copied before source so dependency layer is cached when only source changes.

## Implementation Steps

1. Rewrite `Dockerfile` with content above
2. Verify build: `docker build -t pocketquant:test .`
3. Verify run: `docker run --rm pocketquant:test python -c "from pocketquant.api.main import app; print('OK')"`

## Success Criteria

- [x] `docker build` succeeds
- [x] Container starts and `/health` responds
- [x] No `src/` references in Dockerfile
- [x] Uses `uv sync` for workspace-aware install
