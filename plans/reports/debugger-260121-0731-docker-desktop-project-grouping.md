# Docker Desktop Project Grouping Investigation

**Date:** 2026-01-21 07:31
**Issue:** Containers grouped under "docker" instead of "pocketquant" in Docker Desktop
**Status:** Root cause identified
**Work Context:** D:/w/_me/pocketquant

## Root Cause

Docker Compose derives project name from **parent directory of compose file**, not repository root.

**Current structure:**
```
pocketquant/              # Repository root
└── docker/               # Compose file directory ← Docker uses THIS name
    └── compose.yml
```

When running `docker compose -f docker/compose.yml up`, Docker:
1. Resolves working directory to `D:\w\_me\pocketquant\docker`
2. Uses parent directory name "docker" as project name
3. Labels containers: `com.docker.compose.project=docker`
4. Docker Desktop groups by this label

**Evidence:**
- `docker compose ls` output: `NAME=docker, CONFIG FILES=D:\w\_me\pocketquant\docker\compose.yml`
- Container labels: `com.docker.compose.project=docker`
- Resolved config: `"name": "docker"`
- Network names: `docker_default`
- Volume names: `docker_mongodb_data`, `docker_redis_data`

## Solutions (3 Options)

### Option 1: Add `name:` to compose.yml (RECOMMENDED)
**Best practice, explicit control, works from any directory**

```yaml
# docker/compose.yml
name: pocketquant  # Add this at top level

services:
  mongodb:
    # ... rest unchanged
```

**Pros:**
- Explicit project name in compose file
- Works regardless of execution directory
- Survives directory renames
- Compose v2 standard approach

**Cons:** None

**Migration:**
```bash
# Stop & remove old "docker" project
docker compose -f docker/compose.yml down

# Start with new name
docker compose -f docker/compose.yml up -d
```

### Option 2: Set COMPOSE_PROJECT_NAME env var
Add to `.env` or shell environment:
```bash
COMPOSE_PROJECT_NAME=pocketquant
```

**Pros:** No compose file changes

**Cons:**
- Must be set in every environment
- Easy to forget/misconfigure
- Not visible in compose file

### Option 3: Move compose.yml to root
```
pocketquant/
├── compose.yml       # Move here
└── docker/
    └── mongo-init.js
```

**Pros:** Automatic "pocketquant" project name

**Cons:**
- Breaks existing directory organization
- Less clean root directory
- Requires path updates in compose file

## Recommendation

**Use Option 1** - add `name: pocketquant` to top of `docker/compose.yml`:

1. **Explicit** - project name declared in compose file
2. **Portable** - works from any directory
3. **Standard** - Compose v2 best practice
4. **Safe** - preserves existing directory structure
5. **Migrates cleanly** - single down/up cycle

## Migration Steps

```bash
# 1. Stop existing containers
docker compose -f docker/compose.yml down

# 2. Add name: pocketquant to docker/compose.yml (top level, before services:)

# 3. Start with new project name
docker compose -f docker/compose.yml up -d

# 4. Verify
docker compose ls  # Should show NAME=pocketquant
docker ps --format "{{.Names}}\t{{.Label \"com.docker.compose.project\"}}"
```

**Expected result:**
- Docker Desktop shows "pocketquant" parent group
- Container labels: `com.docker.compose.project=pocketquant`
- Network: `pocketquant_default`
- Volumes: `pocketquant_mongodb_data`, `pocketquant_redis_data`

## Side Effects

**Volume data preservation:**
Old volumes `docker_mongodb_data` / `docker_redis_data` won't be auto-deleted. Two approaches:

**A) Fresh start (data loss acceptable):**
```bash
docker compose -f docker/compose.yml down -v  # Remove old volumes
docker compose -f docker/compose.yml up -d    # New volumes created
```

**B) Migrate data (preserve existing data):**
```bash
# Copy data to new volumes before starting
docker volume create pocketquant_mongodb_data
docker volume create pocketquant_redis_data

# Manual data migration (or let services reinitialize)
```

For dev environment, Option A (fresh start) is typically fine - MongoDB reinitializes from `mongo-init.js`.

## Unresolved Questions

None - root cause clear, solution straightforward.
