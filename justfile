# PocketQuant Development Tasks
# Requires: just, uv, docker

default:
    @just --list

# Start everything: venv → deps → docker → server
start port="8000":
    #!/usr/bin/env bash
    set -e
    [ ! -d ".venv" ] && uv venv
    uv pip install -e ".[dev]" -q
    docker compose -f docker/compose.yml up -d
    .venv/bin/uvicorn src.main:app --reload --host 0.0.0.0 --port {{port}}

# Stop containers (data preserved)
stop:
    docker compose -f docker/compose.yml stop

# View container logs
logs service="":
    docker compose -f docker/compose.yml logs -f {{service}}
