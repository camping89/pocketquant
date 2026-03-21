# Phase 8: Docker Compose Check

**Priority:** Medium | **Status:** Complete | **Effort:** 15m

## Overview

Verify `docker/compose.prod.yml` app service config is compatible with the rewritten Dockerfile.

## Depends On

- Phase 5 (Dockerfile must be rewritten first)

## Files to Review

- `docker/compose.prod.yml` -- production compose
- `docker/compose.yml` -- dev compose (infra only, no app service -- likely fine)

## Current State of `compose.prod.yml`

The app service uses:
```yaml
app:
  image: ghcr.io/${GITHUB_USER}/pocketquant:${IMAGE_TAG:-latest}
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:41920/health"]
```

This references a pre-built image (from `ghcr.io`), not a local build. The image is built separately (CI/CD or manual `docker build`). The compose file itself should be fine as long as:
1. Port 41920 matches the Dockerfile EXPOSE/CMD
2. Environment variables match what `pocketquant.core.config.Settings` expects

## Implementation Steps

1. Verify `compose.prod.yml` healthcheck port matches Dockerfile (41920 -- already correct)
2. Verify environment variables in compose match `Settings` field names
3. Check if any `build:` directives reference old paths (none expected -- uses pre-built image)
4. Verify `docker/compose.yml` (dev) has no app service that references old paths
5. (Optional) Test: `docker compose -f docker/compose.prod.yml config` to validate syntax

## Verification Commands

```bash
# Validate compose syntax
docker compose -f docker/compose.prod.yml config --quiet

# Validate dev compose
docker compose -f docker/compose.yml config --quiet
```

## Success Criteria

- [x] `compose.prod.yml` config validates without errors
- [x] Healthcheck port is 41920
- [x] No `src/` references in any compose file
- [x] Dev compose still works for local infra
