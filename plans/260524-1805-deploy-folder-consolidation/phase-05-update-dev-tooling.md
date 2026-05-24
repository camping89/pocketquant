---
phase: 5
title: "Update dev tooling"
status: completed
priority: P1
effort: "20m"
dependencies: [2]
---

# Phase 5: Update dev tooling

## Overview

Local dev workflow uses `just` recipes, `scripts/check_env.py`, and possibly JetBrains `.run/` configs. All hard-code `docker/compose.yml`. Update to `deploy/compose.yml`.

## Requirements

- Functional: `just up`, `just down`, `just reset`, `just redis`, `just check` all work after the move.
- Non-functional: no behavior change beyond path resolution.

## Related Code Files

- Modify: `justfile` (4 occurrences of `docker/compose.yml`)
- Modify: `scripts/check_env.py` (line 50)
- Modify: `.run/*.xml` or `.run/*.run.xml` (JetBrains run configs — audit + update)

## Implementation Steps

### `justfile`

1. Line 17 (`up`): `docker compose -f docker/compose.yml up -d` → `docker compose -f deploy/compose.yml up -d`
2. Line 21 (`down`): `docker compose -f docker/compose.yml down` → `docker compose -f deploy/compose.yml down`
3. Line 25 (`reset`): `docker compose -f docker/compose.yml down -v` → `docker compose -f deploy/compose.yml down -v`
4. Line 56 (`redis`): `docker compose -f docker/compose.yml up -d redis` → `docker compose -f deploy/compose.yml up -d redis`
5. Verify `just check` recipe still calls `{{python}} scripts/check_env.py` — no change (scripts/ stays at root).

### `scripts/check_env.py`

1. Line 50: replace `"docker/compose.yml"` → `"deploy/compose.yml"` in the subprocess `["docker", "compose", "-f", "docker/compose.yml", "ps", "--format", "json"]` call.
2. Grep the file for any other `docker/` refs; fix if present.

### `.run/` audit (JetBrains)

1. `ls .run/` — enumerate run config XML files.
2. `grep -l "docker/\|Dockerfile\|deploy.sh\|verify.sh\|\.env" .run/*.xml` — find hits.
3. For each match: open and update:
   - `docker/compose.yml` → `deploy/compose.yml`
   - `docker/compose.prod.yml` → `deploy/compose.prod.yml`
   - Working-dir refs that anchor to project root: unchanged
   - Dockerfile path: `Dockerfile` → `deploy/Dockerfile` (if explicitly referenced)
4. If `.run/` has no relevant configs, skip; document `n/a` in commit.

### Optional: `README.md`

1. If `README.md` references `docker/compose.yml` (it likely does via `just up` examples), Phase 6 handles docs; spot-check here and defer full update to Phase 6.

## Success Criteria

- [ ] `grep -rn "docker/compose" justfile scripts/check_env.py .run/` returns zero matches
- [ ] `just up` actually starts mongodb + redis containers
- [ ] `just check` succeeds (or fails with the SAME pre-existing reason, not a new path error)
- [ ] `.run/` configs (if any) verified opened in IDE without "file not found" warnings — defer to Phase 8 if IDE not at hand

## Risk Assessment

- **Risk:** `.run/` is JetBrains-specific; CLI-only contributors won't notice errors there. **Mitigation:** document in changelog "IDE users may need to refresh run configs"; Phase 8 includes IDE smoke check if available.
- **Risk:** `check_env.py` has other hard-coded paths beyond line 50. **Mitigation:** grep success criterion above.
- **Risk:** `justfile` working-dir directive (`[working-directory: 'packages/pocketquant-web']` on `fe` recipe) interacts oddly. **Mitigation:** that recipe doesn't touch deploy; no change needed.
