# PocketQuant — local dev tasks
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

# Reset everything: stop containers and delete all data volumes (clean slate)
reset:
    docker compose -f deploy/compose.local.yml --env-file .env down -v

# Start backend: full runtime (scheduler, WS feed, reconcile, backtest worker) + all API routes + SPA (port 41921).
# Single worker only — scheduler/WS/broker are in-process singletons; --workers N would duplicate them.
# Route iteration tip: ENABLE_JOBS=false just be — skips the trading runtime so --reload restarts stay light.
be:
    {{python}} -m uvicorn pocketquant.app.main:app --reload --host 0.0.0.0 --port 41921

# Start frontend dev server (vite proxies /api → app on 41921)
[working-directory: 'web']
fe:
    npm run dev

# Run tests
test:
    {{python}} -m pytest
