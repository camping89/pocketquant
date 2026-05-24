---
phase: 2
title: "Move files (git mv)"
status: completed
priority: P1
effort: "20m"
dependencies: [1]
---

# Phase 2: Move files (git mv)

## Overview

Pure mechanical move. Use `git mv` to preserve file history. Create `deploy/scripts/patches/` placeholder. Delete now-empty `docker/` folder.

## Requirements

- Functional: every file lands at target path; git records as renames (not delete+add) so blame survives.
- Non-functional: single commit per move-group for clean revert.

## Architecture

```
ROOT → deploy/                     docker/* → deploy/*
  Dockerfile                         compose.yml
  deploy.sh                          compose.prod.yml
  verify.sh                          mongo-init.js
  .env                               scripts/cleanup.sh → deploy/scripts/cleanup.sh
  .env.example                       scripts/server-setup.sh → deploy/scripts/server-setup.sh
```

## Related Code Files

- Create: `deploy/` (dir), `deploy/scripts/` (dir), `deploy/scripts/patches/` (dir), `deploy/scripts/patches/README.md` (placeholder)
- Move (git mv):
  - `Dockerfile` → `deploy/Dockerfile`
  - `deploy.sh` → `deploy/deploy.sh`
  - `verify.sh` → `deploy/verify.sh`
  - `.env` → `deploy/.env` (LOCAL ONLY — file is git-ignored; copy manually, do not commit)
  - `.env.example` → `deploy/.env.example`
  - `docker/compose.yml` → `deploy/compose.yml`
  - `docker/compose.prod.yml` → `deploy/compose.prod.yml`
  - `docker/mongo-init.js` → `deploy/mongo-init.js`
  - `docker/scripts/cleanup.sh` → `deploy/scripts/cleanup.sh`
  - `docker/scripts/server-setup.sh` → `deploy/scripts/server-setup.sh`
- Delete: `docker/` (entire folder, after moves leave it empty)

## Implementation Steps

1. **Create target directories first** (avoid `git mv` failures on missing parent):
   ```powershell
   mkdir deploy, deploy/scripts, deploy/scripts/patches
   ```
2. **Write `deploy/scripts/patches/README.md`** (placeholder explaining the convention — see content below).
3. **Move tracked files via `git mv`**:
   ```powershell
   git mv Dockerfile deploy/Dockerfile
   git mv deploy.sh deploy/deploy.sh
   git mv verify.sh deploy/verify.sh
   git mv .env.example deploy/.env.example
   git mv docker/compose.yml deploy/compose.yml
   git mv docker/compose.prod.yml deploy/compose.prod.yml
   git mv docker/mongo-init.js deploy/mongo-init.js
   git mv docker/scripts/cleanup.sh deploy/scripts/cleanup.sh
   git mv docker/scripts/server-setup.sh deploy/scripts/server-setup.sh
   ```
4. **Handle `.env` (git-ignored)**: copy manually (don't `git mv` — not tracked):
   ```powershell
   Move-Item .env deploy/.env
   ```
5. **Verify `docker/` is empty**, then remove:
   ```powershell
   Remove-Item docker -Recurse
   ```
   (Or `rmdir docker` if PowerShell complains.)
6. **DO NOT edit file contents in this phase** — only move. Path-content updates land in phases 3–6.
7. **Single commit per logical group**: one commit for moves + delete `docker/`. Message: `refactor(deploy): move deployment assets into deploy/ folder`.

### `deploy/scripts/patches/README.md` content

```markdown
# Deploy Patches

One-time idempotent migration scripts run during `deploy.sh`.

## Convention

- Name: `one_time_<descriptive-snake-case>.py` (Python) or `one_time_<...>.sh` (shell)
- Must be **idempotent** — safe to re-run on already-migrated data (no-op after first success)
- Invoked from `deploy/deploy.sh` after app container becomes healthy
- Removed from this folder only after all environments have run them at least once

## Pattern

```bash
docker compose -f deploy/compose.prod.yml --env-file deploy/.env exec -T app \
  python -m deploy.scripts.patches.<script_name> || true
```

Note: requires `COPY deploy/scripts/patches/ deploy/scripts/patches/` in `deploy/Dockerfile` if the migration runs inside the container, OR mount the folder via compose. Default: run via mount, not bake into image.
```

## Success Criteria

- [ ] `deploy/` contains all 9 moved files at correct paths
- [ ] `deploy/scripts/patches/README.md` exists
- [ ] `docker/` folder is gone
- [ ] `git log --follow deploy/Dockerfile` shows pre-move history (rename detected)
- [ ] No file content modified in this phase (`git diff --stat` shows only renames + 1 new README)

## Risk Assessment

- **Risk:** `git mv` on Windows with CRLF can confuse rename detection. **Mitigation:** verify with `git status` — should show `renamed:` not `deleted/new file:`. If not detected, `git add -A` after move + rely on git's automatic rename detection (`git config diff.renames true`).
- **Risk:** `.env` accidentally committed. **Mitigation:** verify `.gitignore` covers `deploy/.env` (likely `.env` glob already does; confirm). If not, add `deploy/.env` to `.gitignore`.
- **Risk:** Path-content updates (phases 3–6) reference files that don't exist yet. **Mitigation:** this phase must complete before 3–6 start (enforced by dependency chain).
