# PocketQuant Development Tasks
# Requires: just, docker
# Auto-installs: uv (faster pip alternative)

# Set shell for Windows
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# Cross-platform executable paths
python := if os() == "windows" { ".venv/Scripts/python.exe" } else { ".venv/bin/python" }
pip := if os() == "windows" { ".venv/Scripts/pip.exe" } else { ".venv/bin/pip" }
uvicorn := if os() == "windows" { ".venv/Scripts/uvicorn.exe" } else { ".venv/bin/uvicorn" }
ruff := if os() == "windows" { ".venv/Scripts/ruff.exe" } else { ".venv/bin/ruff" }
mypy := if os() == "windows" { ".venv/Scripts/mypy.exe" } else { ".venv/bin/mypy" }

default:
    @just --list

# Cross-platform system Python
sys_python := if os() == "windows" { "py -3" } else { "python3" }

# Setup: install uv, create venv, install dependencies
install:
    {{sys_python}} -m pip install uv --quiet
    {{sys_python}} -m venv .venv
    {{pip}} install -e ".[dev]"

# Start docker + server (run `just install` first if needed)
# Port configurable via API_PORT env var (default: 8765)
start:
    docker compose -f docker/compose.yml up -d
    {{python}} -m src.main

# Stop containers (data preserved)
stop: 
    docker compose -f docker/compose.yml stop

# View container logs
logs service="":
    docker compose -f docker/compose.yml logs -f {{service}}

# Reset everything: stop containers and delete all data volumes
reset:
    docker compose -f docker/compose.yml down -v

# Check development environment (docker, mongodb, redis)
check:
    {{python}} scripts/check_env.py

# Test MongoDB authentication (sync and async)
test-mongo:
    {{python}} scripts/test_mongodb_auth.py

# Lint code (add --fix to auto-fix)
lint *args:
    {{ruff}} check . {{args}}

# Format code
format:
    {{ruff}} format .

# Type check
typecheck:
    {{mypy}} src/
