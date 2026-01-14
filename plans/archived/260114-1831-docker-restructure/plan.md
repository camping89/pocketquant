---
title: Docker Folder Restructure
description: Consolidate Docker and initialization files into dedicated docker/ directory
status: completed
priority: high
effort: 1h
branch: master
tags: [docker, infrastructure, restructure]
created: 2026-01-14
completed: 2026-01-14
---

# Plan: Docker Folder Restructure

**Date:** 2026-01-14
**Status:** DONE (completed 2026-01-14)
**Brainstorm:** `plans/reports/brainstorm-260114-1831-docker-folder-restructure.md`

## Overview

Move all Docker-related files from root and scripts/ into dedicated `docker/` folder.

## Current → Target

```
BEFORE                          AFTER
─────────────────────────────   ─────────────────────────────
pocketquant/                    pocketquant/
├── docker-compose.yml          ├── docker/
├── scripts/                    │   ├── compose.yml
│   └── mongo-init.js           │   └── mongo-init.js
├── justfile                    ├── justfile (updated)
└── ...                         └── ...
```

## Implementation Steps

### Step 1: Create docker/ and move files

```bash
mkdir -p docker
mv docker-compose.yml docker/compose.yml
mv scripts/mongo-init.js docker/mongo-init.js
rmdir scripts
```

### Step 2: Update compose.yml volume mount

**File:** `docker/compose.yml`

Change line 16:
```yaml
# FROM
- ./scripts/mongo-init.js:/docker-entrypoint-initdb.d/mongo-init.js:ro

# TO
- ./docker/mongo-init.js:/docker-entrypoint-initdb.d/mongo-init.js:ro
```

### Step 3: Update justfile docker commands

**File:** `justfile`

All docker commands need `-f docker/compose.yml`:

```just
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
```

### Step 4: Update README.md

**File:** `README.md`

Update deployment section (around line 232):
```bash
# FROM
docker-compose up -d

# TO
docker compose -f docker/compose.yml up -d
```

### Step 5: Verify

```bash
# Stop any running containers first
docker compose down 2>/dev/null || true

# Test commands
just start  # Should start containers and server
# Ctrl+C to stop server
just stop   # Should stop containers
just logs   # Should show logs
```

## Files Changed

| File | Action |
|------|--------|
| `docker/compose.yml` | Created (moved + edited) |
| `docker/mongo-init.js` | Created (moved) |
| `justfile` | Modified |
| `README.md` | Modified |
| `docker-compose.yml` | Deleted |
| `scripts/` | Deleted |

## Validation Checklist

- [ ] `docker/` directory exists with both files
- [ ] `scripts/` directory removed
- [ ] `docker-compose.yml` removed from root
- [ ] `just start` successfully starts MongoDB and Redis
- [ ] `just stop` successfully stops containers
- [ ] `just logs` shows container output
- [ ] MongoDB init script runs (check logs for "Creating user")

## Rollback

If issues occur:
```bash
mv docker/compose.yml docker-compose.yml
mkdir -p scripts
mv docker/mongo-init.js scripts/mongo-init.js
rmdir docker
git checkout justfile README.md
```

## Notes

- Using modern `docker compose` (V2) not legacy `docker-compose`
- Compose file renamed to `compose.yml` (modern convention)
- No backward compatibility - users should use justfile
