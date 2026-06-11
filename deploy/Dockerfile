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

# Copy project definition + lock first (cache layer)
COPY pyproject.toml uv.lock README.md ./

# Copy source code
COPY src/ src/

# Install the package (locked, no dev deps)
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
    CMD curl -f http://localhost:41921/health || exit 1

EXPOSE 41921

# Single worker only — scheduler/WS feed/broker are in-process singletons;
# --workers N would duplicate the reconcile loop and live broker connection.
CMD ["uvicorn", "pocketquant.app.main:app", "--host", "0.0.0.0", "--port", "41921"]
