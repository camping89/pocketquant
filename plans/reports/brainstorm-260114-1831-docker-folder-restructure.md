# Brainstorm: Docker Folder Restructure

**Date:** 2026-01-14
**Status:** Agreed

## Problem Statement

Root directory contains Docker-related files mixed with project config. Goal: organize Docker infra into dedicated folder for cleaner project structure.

## Current State

```
pocketquant/
├── docker-compose.yml      # Docker orchestration
├── scripts/
│   └── mongo-init.js       # MongoDB init (Docker-only)
├── justfile                # Task runner
├── TODO.md
├── .env.example
└── pyproject.toml
```

## Evaluated Approaches

### Option A: Minimal Move (docker-compose.yml only)
- Move just `docker-compose.yml` to `docker/`
- Keep `scripts/` separate

**Pros:** Minimal changes
**Cons:** `scripts/` only has Docker-related content anyway

### Option B: Full Docker Consolidation ✓ SELECTED
- Create `docker/` folder
- Move `docker-compose.yml` → `docker/compose.yml`
- Move `scripts/mongo-init.js` → `docker/mongo-init.js`
- Delete empty `scripts/`
- Update `justfile` paths

**Pros:** All Docker infra in one place, cleaner root
**Cons:** Minor breaking change for manual docker-compose users

### Option C: Infrastructure folder
- Create `infra/` with subfolders: `infra/docker/`, `infra/k8s/`, etc.

**Pros:** Future-proof for Kubernetes/Terraform
**Cons:** YAGNI - over-engineering for current needs

## Final Agreed Solution

**Option B: Full Docker Consolidation**

### Target Structure
```
pocketquant/
├── docker/
│   ├── compose.yml         # renamed (modern naming)
│   └── mongo-init.js       # moved from scripts/
├── justfile                # updated paths
├── TODO.md                 # stays
├── .env.example            # stays
└── pyproject.toml          # stays
```

### Implementation Checklist

1. [ ] Create `docker/` directory
2. [ ] Move `docker-compose.yml` → `docker/compose.yml`
3. [ ] Move `scripts/mongo-init.js` → `docker/mongo-init.js`
4. [ ] Update `docker/compose.yml` volume mount: `./scripts/` → `./docker/`
5. [ ] Update `justfile` docker commands to use `-f docker/compose.yml`
6. [ ] Update `README.md` deployment section
7. [ ] Delete empty `scripts/` directory
8. [ ] Test with `just start`

### Key Decisions
- **justfile at root:** Yes - central task runner
- **TODO.md:** Stays at root
- **Backward compatibility:** Not needed - use justfile

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Manual `docker-compose up` breaks | Document in README, use justfile |
| CI/CD pipelines using old path | Update pipeline configs if any |

## Success Criteria

- [ ] `just start` works correctly
- [ ] `just stop` works correctly
- [ ] `just logs` works correctly
- [ ] Root directory visually cleaner
- [ ] No orphan files

## Next Steps

Implement via `/plan` if approved.
