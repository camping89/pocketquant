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

# Start ONLY local Redis (for remote-db-local-redis.env: prod Mongo + local Redis).
# Redis is a hard startup dependency — bring it up before `just be` or the app crashes on boot.
redis:
    docker compose -f deploy/compose.local.yml --env-file .env up -d redis

# Stop infrastructure
down:
    docker compose -f deploy/compose.local.yml --env-file .env down

# Reset everything: stop containers and delete all data volumes (clean slate)
reset:
    docker compose -f deploy/compose.local.yml --env-file .env down -v

# Start backend on port 41921 with the roles in APP_ROLES (default api: routes only).
# Never --workers N: the worker and the trader act only while they hold their Mongo lease.
# Full runtime on a local database: APP_ROLES=api,worker,trader in .env (all-local profile only).
be:
    # The app asserts a UTC process timezone at startup, so pin it here too.
    TZ=UTC {{python}} -m uvicorn pocketquant.app.main:app --reload --host 127.0.0.1 --port 41921

# Forward prod Mongo -> localhost:27017, Redis -> localhost:6379, Portainer -> localhost:$PORTAINER_PORT.
# Prod binds them to 127.0.0.1. Keep this running while debugging; Ctrl+C closes it.
tunnel:
    #!/usr/bin/env bash
    set -euo pipefail
    cfg=../pocketquant-config/vps/default
    port() { grep "^$1=" "$cfg/.env" | cut -d= -f2 | tr -d '\r '; }
    mkdir -p .cache/ssh
    tr -d '\r' < "$cfg/id_rsa" > .cache/ssh/tunnel_key
    chmod 600 .cache/ssh/tunnel_key
    trap 'rm -f .cache/ssh/tunnel_key' EXIT
    ssh -i .cache/ssh/tunnel_key -N -o ExitOnForwardFailure=yes \
      -L "27017:localhost:$(port MONGO_PORT)" \
      -L "6379:localhost:$(port REDIS_PORT)" \
      -L "$(port PORTAINER_PORT):localhost:$(port PORTAINER_PORT)" \
      "$(head -1 "$cfg/host" | tr -d '\r')"

# Start frontend dev server (vite proxies /api → app on 41921)
[working-directory: 'web']
fe:
    npm run dev

# Run tests
test:
    {{python}} -m pytest

# Run the unit suite under three host timezones — catches host-zone leakage.
# Each non-UTC leg first proves the zone resolved; an unresolvable zone falls
# back to UTC rather than failing, which would silently re-run the UTC suite.
test-tz:
    TZ=UTC {{python}} -m pytest -q
    TZ=Asia/Ho_Chi_Minh {{python}} -c "import time,sys; sys.exit(0 if time.timezone != 0 else 1)"
    TZ=Asia/Ho_Chi_Minh {{python}} -m pytest -q
    TZ=America/Chicago {{python}} -c "import time,sys; sys.exit(0 if time.timezone != 0 else 1)"
    TZ=America/Chicago {{python}} -m pytest -q
