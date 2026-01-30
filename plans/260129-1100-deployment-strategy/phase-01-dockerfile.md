# Phase 01: Create Dockerfile

## Context

- **Parent:** [plan.md](plan.md)
- **Dependencies:** None
- **Docs:** [codebase-summary.md](../../docs/codebase-summary.md)

## Overview

| Field | Value |
|-------|-------|
| Priority | P1 |
| Status | ⏳ Pending |
| Effort | 30m |

Create multi-stage Dockerfile for Python 3.14 FastAPI application.

## Key Insights

- Project uses `uv` for dependency management
- tvdatafeed requires git installation (pip install from git)
- Python 3.14 required
- Final image should be < 300MB

## Requirements

### Functional
- Build Python application with all dependencies
- Support both production and development builds
- Include health check

### Non-functional
- Image size < 300MB
- Build time < 3 minutes (cached)
- Security: non-root user

## Architecture

```dockerfile
# Stage 1: Builder (install deps + compile)
FROM python:3.14-slim AS builder
  - Install git, build tools
  - Install uv
  - Copy pyproject.toml
  - Install dependencies

# Stage 2: Runtime (minimal image)
FROM python:3.14-slim AS runtime
  - Copy venv from builder
  - Copy source code
  - Create non-root user
  - Set entrypoint
```

## Related Code Files

### Files to Create
- `Dockerfile` (root)
- `.dockerignore` (root)

### Files to Reference
- `pyproject.toml` - Dependencies
- `src/main.py` - Entry point

## Implementation Steps

### Step 1: Create .dockerignore
```
.git
.venv
__pycache__
*.pyc
.env
.env.*
*.md
tests/
.pytest_cache/
.mypy_cache/
.ruff_cache/
docker/
docs/
plans/
```

### Step 2: Create Dockerfile

```dockerfile
# ============================================
# Stage 1: Builder
# ============================================
FROM python:3.14-slim AS builder

WORKDIR /app

# Install system deps for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml .

# Create venv and install deps
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache -e .

# ============================================
# Stage 2: Runtime
# ============================================
FROM python:3.14-slim AS runtime

WORKDIR /app

# Install runtime deps (git needed for tvdatafeed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 appuser

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv

# Copy source code
COPY src/ src/

# Set environment
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Step 3: Build and Test Locally

```bash
# Build
docker build -t pocketquant:local .

# Test run
docker run --rm -it \
  -e MONGODB_URL=mongodb://localhost:27017/test \
  -e REDIS_URL=redis://localhost:6379/0 \
  pocketquant:local

# Check size
docker images pocketquant:local
```

## Todo List

- [ ] Create `.dockerignore`
- [ ] Create `Dockerfile`
- [ ] Build locally and verify size < 300MB
- [ ] Test health check works
- [ ] Verify app starts without errors

## Success Criteria

- [ ] `docker build` succeeds
- [ ] Image size < 300MB
- [ ] Container starts and health check passes
- [ ] Non-root user (appuser)

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Python 3.14 image không available | High | Fallback to 3.13 |
| tvdatafeed build fails | Medium | Pre-install git |
| Image too large | Low | Use slim base, multi-stage |

## Security Considerations

- Non-root user `appuser`
- No secrets in image
- Minimal base image (slim)
- Regular security updates via rebuild

## Next Steps

After completion → [Phase 02: Production Compose](phase-02-compose-prod.md)
