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

# Copy dependency files and README (required by pyproject.toml)
COPY pyproject.toml uv.lock README.md ./

# Create venv and install deps (locked for reproducibility)
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache -e .

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
    CMD curl -f http://localhost:41920/health || exit 1

EXPOSE 41920

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "41920"]
