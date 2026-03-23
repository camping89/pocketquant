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
RUN uv sync --frozen --no-dev --no-editable

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
