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

# Run tests for a specific package (core, backtest, trading, app)
test-pkg pkg:
    {{python}} -m pytest tests/{{pkg}}_test/

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

# Start Redis only (when using remote MongoDB)
redis:
    docker compose -f deploy/compose.local.yml --env-file .env up -d redis

# Start backend dev server with hot reload
be:
    {{python}} -m uvicorn pocketquant.app.main:app --reload --host 0.0.0.0 --port 41920

# Start frontend dev server
[working-directory: 'packages/pocketquant-web']
fe:
    npm run dev
