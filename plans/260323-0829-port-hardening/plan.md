---
status: pending
branch: feat/strategy-init
created: 2026-03-23
---

# Port Hardening — Obscure Ports + Remote Access

## Summary

Replace hardcoded/well-known ports with env-var-driven obscure ports across dev and prod. Expose MongoDB, Redis, Portainer for remote access. Internal container ports unchanged.

## Port Map

| Service | Env Var | Dev Default | Prod Default | Container Port |
|---------|---------|-------------|--------------|----------------|
| API | — | 41920 (local uvicorn) | `APP_PORT` (58921) | 41920 |
| MongoDB | `MONGO_PORT` | 52017 | 52017 | 27017 |
| Redis | `REDIS_PORT` | 53679 | 6379 | 6379 |
| Portainer | `PORTAINER_PORT` | 54900 | 54900 | 9000 |
| Mongo Express | `MONGOEXPRESS_PORT` | 58081 | — | 8081 |

**API port stays 41920 for local dev** (uvicorn runs on host, not in Docker). Only prod compose maps `APP_PORT → 41920`.

## Phase 1: Infrastructure Files

**Status:** pending

### Files to Modify

| # | File | Change |
|---|------|--------|
| 1 | `docker/compose.yml` | Use env vars with obscure defaults for all port mappings |
| 2 | `.env.example` | Add port vars to dev section, update MONGODB_URL/REDIS_URL with new defaults |
| 3 | `docker/compose.prod.yml` | Already correct — no changes needed |
| 4 | `Dockerfile` | No change (internal port 41920) |
| 5 | `deploy.sh` | No change (already validates port env vars) |

### compose.yml Changes

```yaml
# Before                          # After
- "27018:27017"                   - "${MONGO_PORT:-52017}:27017"
- "6379:6379"                     - "${REDIS_PORT:-53679}:6379"
- "8081:8081"                     - "${MONGOEXPRESS_PORT:-58081}:8081"
```

### .env.example Changes

```env
# Add to dev section:
MONGO_PORT=52017
REDIS_PORT=53679
MONGOEXPRESS_PORT=58081

# Update URLs:
MONGODB_URL=mongodb://pocketquant:pocketquant_dev@localhost:52017/pocketquant?authSource=admin
REDIS_URL=redis://localhost:53679/0

# Prod section — add defaults:
# APP_PORT=58921
# MONGO_PORT=52017
# REDIS_PORT=53679
# PORTAINER_PORT=54900
```

## Phase 2: Code & Dev Tools

**Status:** pending

| # | File | Change |
|---|------|--------|
| 1 | `main.py:86` | No change (41920 is internal container port, acceptable) |
| 2 | `justfile:56` | No change (local dev runs uvicorn directly on host) |
| 3 | `.vscode/launch.json:13` | No change (local debugger) |
| 4 | `tests/manual/api-test.http` | Keep 41920 (local dev testing) |
| 5 | `tests/http/environments/local.bru` | Keep 41920 (local dev testing) |

**Rationale:** Local dev tools connect to uvicorn on host (port 41920) and to Docker services via their mapped ports. Only Docker port mappings change.

## Phase 3: Documentation Updates

**Status:** pending

| # | File | Change |
|---|------|--------|
| 1 | `README.md` | Update port refs (27018→52017, 6379→53679) |
| 2 | `docs/deployment-guide.md` | Minor — already env-var driven, verify consistency |
| 3 | `docs/system-architecture.md:3` | Remove `Port: 41920` from header (not relevant to architecture) |
| 4 | `docs/codebase-summary.md:3` | Remove `Port: 41920` from header |
| 5 | `docs/code-standards.md:3,714` | Remove port from header, update MONGODB_URL |
| 6 | `docs/project-overview-pdr.md:3,492,499` | Remove port from header, update uvicorn examples |
| 7 | `docs/handler-pipelines.md:3` | Remove port from header |
| 8 | `docs/architecture-visual-map.md:3,67,342` | Remove port from header, update ASCII diagrams |
| 9 | `docs/README.md:5,344` | Remove port refs |
| 10 | `docs/debug-audit-order-execution.md:302,327` | Update mongosh port, infra table |
| 11 | `CLAUDE.md` | No change (no port refs) |

## Phase 4: Commit & Push

**Status:** pending

- Stage all changed files
- Commit: `refactor: use env-var-driven obscure ports for all services`
- Push to `feat/strategy-init`

## Success Criteria

- [ ] `docker compose -f docker/compose.yml up -d` starts services on obscure ports
- [ ] `.env.example` documents all port env vars
- [ ] MongoDB accessible at `localhost:52017` (or custom MONGO_PORT)
- [ ] Redis accessible at `localhost:53679` (or custom REDIS_PORT)
- [ ] All docs updated, no stale port references
- [ ] `just dev` still works on 41920 (local uvicorn unchanged)

## Risk

- **Existing .env files** on user machines will have old port values → must update manually after pulling
- **Running containers** need `just down && just up` to pick up new ports
