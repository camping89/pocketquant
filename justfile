# PocketQuant Development Tasks
# Requires: just, docker, uv (https://docs.astral.sh/uv/)

set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

python := if os() == "windows" { ".venv/Scripts/python.exe" } else { ".venv/bin/python" }

default:
    @just --list

# Setup: create venv and install dependencies
install:
    uv sync

# Start infrastructure (MongoDB + Redis)
# --env-file .env: same single source the app reads, so container creds/ports
# always match. Without it compose looks for deploy/.env (absent locally).
up:
    docker compose -f deploy/compose.local.yml --env-file .env up -d

# Stop infrastructure
down:
    docker compose -f deploy/compose.local.yml --env-file .env down

# Reset everything: stop containers and delete all data volumes
reset:
    docker compose -f deploy/compose.local.yml --env-file .env down -v

# Run all tests
test:
    {{python}} -m pytest

# Regenerate baseline regression snapshots (OpenAPI, route inventory)
baseline:
    BASELINE_UPDATE=1 {{python}} -m pytest tests/baseline/ -q

# Run tests for a specific subpackage (core, engine, backtest, app, bff)
test-pkg pkg:
    {{python}} -m pytest tests/{{pkg}}_test/

# Lint check
lint:
    uv run ruff check .

# Format code
fmt:
    uv run ruff format .

# Type check
types:
    uv run pyright

# Run lint + format + type check
qa: lint fmt types

# Start Redis only (when using remote MongoDB)
redis:
    docker compose -f deploy/compose.local.yml --env-file .env up -d redis

# Start headless runtime: scheduler, WS feed, strategies, reconcile, backtest worker (port 41920, /health only)
be:
    {{python}} -m uvicorn pocketquant.app.main:app --reload --host 0.0.0.0 --port 41920

# Start FE gateway: stateless API serving web/ SPA + DB read/write (port 41921)
bff:
    BFF_PORT=41921 {{python}} -m uvicorn pocketquant.bff.main:app --reload --host 0.0.0.0 --port 41921

# Start frontend dev server (vite proxies /api → bff on 41921)
[working-directory: 'web']
fe:
    npm run dev

# Check import-linter contracts (layered/forbidden contracts incl. bff isolation)
lint-imports:
    uv run lint-imports
