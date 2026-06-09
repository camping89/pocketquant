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
COPY packages/pocketquant-infrastructure/pyproject.toml packages/pocketquant-infrastructure/
COPY packages/pocketquant-execution/pyproject.toml packages/pocketquant-execution/
COPY packages/pocketquant-backtest/pyproject.toml packages/pocketquant-backtest/
COPY packages/pocketquant-trading/pyproject.toml packages/pocketquant-trading/
COPY packages/pocketquant-app/pyproject.toml packages/pocketquant-app/
COPY packages/pocketquant-bff/pyproject.toml packages/pocketquant-bff/

# Copy all package source code
COPY packages/ packages/

# Install all workspace packages (locked, no dev deps)
RUN uv sync --frozen --no-dev --no-editable

# ============================================
# Stage 2: Runtime
# ============================================
FROM python:3.14-rc-slim AS runtime

WORKDIR /app

# Install runtime deps (curl needed for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 appuser

# Copy venv from builder (uv sync creates .venv in workdir)
COPY --from=builder /app/.venv /app/.venv

# Copy one-time migration scripts so deploy.sh can run them inside the container
COPY scripts/ scripts/

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

CMD ["uvicorn", "pocketquant.app.main:app", "--host", "0.0.0.0", "--port", "41920"]
