# PocketQuant Development Tasks
# Requires: just, docker, uv (https://docs.astral.sh/uv/)

# Set shell for Windows
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# Cross-platform python path
python := if os() == "windows" { ".venv/Scripts/python.exe" } else { ".venv/bin/python" }

default:
    @just --list

# Setup: create venv and install dependencies
install:
    uv venv
    uv pip install -e ".[dev]"

# Start infrastructure (MongoDB + Redis) - run app via VS Code F5
up:
    docker compose -f docker/compose.yml up -d

# Stop infrastructure
down:
    docker compose -f docker/compose.yml down

# Reset everything: stop containers and delete all data volumes
reset:
    docker compose -f docker/compose.yml down -v

# Check development environment (docker, mongodb, redis, auth)
check:
    {{python}} scripts/check_env.py
    {{python}} scripts/test_mongodb_auth.py
