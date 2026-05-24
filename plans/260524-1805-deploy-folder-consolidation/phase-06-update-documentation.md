---
phase: 6
title: "Update documentation"
status: completed
priority: P2
effort: "45m"
dependencies: [3, 4, 5]
---

# Phase 6: Update documentation

## Overview

Replace every reference to `docker/`, root `deploy.sh`/`verify.sh`/`Dockerfile`/`.env` with the new `deploy/`-prefixed paths in active docs. Add changelog entry flagging breaking change for VPS layout. Update root `README.md` and `scripts/README.md` clarifications.

## Requirements

- Functional: every active doc accurately reflects new layout. Historical journals stay as-is (point-in-time records).
- Non-functional: keep edits tightly scoped to path corrections + the changelog entry; no rewrites.

## Related Code Files

- Modify: `docs/deployment-guide.md` (~12 path refs — bulk of work; VPS migration block added in Phase 7)
- Modify: `docs/project-overview-pdr.md` (any layout refs)
- Modify: `docs/project-changelog.md` (NEW entry)
- Modify: `docs/system-architecture.md` (if layout refs present)
- Modify: `README.md` (root — quickstart examples)
- Modify: `scripts/README.md` (clarify these are data-ops, point at `deploy/scripts/patches/` for migrations)
- Skip (historical): `docs/journals/strategy-subscriptions-cached-backtest-260505.md`
- Skip (completed plans): any `plans/26050*-*/` references

## Implementation Steps

### `docs/deployment-guide.md` (excluding VPS migration runbook — Phase 7)

1. Line 3 footer: `**CD:** Manual via deploy.sh` → `**CD:** Manual via deploy/deploy.sh`
2. Line 13: `VPS: deploy.sh pulls image` → `VPS: deploy/deploy.sh pulls image`
3. Replace all `scp -i $KEY deploy.sh verify.sh` → `scp -i $KEY deploy/deploy.sh deploy/verify.sh`
4. Replace all `scp -i $KEY docker/compose.prod.yml` → `scp -i $KEY deploy/compose.prod.yml`
5. Replace all `scp -i $KEY .env ${VPS}:/opt/pocketquant/docker/.env` → `scp -i $KEY deploy/.env ${VPS}:/opt/pocketquant/deploy/.env`
6. Replace all VPS invocations:
   - `bash deploy.sh` → `bash deploy/deploy.sh`
   - `bash verify.sh` → `bash deploy/verify.sh`
   - `sed -i 's/\r$//' /opt/pocketquant/deploy.sh` → `sed -i 's/\r$//' /opt/pocketquant/deploy/deploy.sh`
7. Replace direct compose invocations on VPS:
   - `docker compose -f docker/compose.prod.yml --env-file docker/.env` → `docker compose -f deploy/compose.prod.yml --env-file deploy/.env` (CWD = `/opt/pocketquant`)
8. Add a note near the top: "**Breaking change (2026-05-24):** Layout reorganized — see [VPS migration runbook](#vps-migration-runbook) before deploying."

### `docs/project-overview-pdr.md`

1. Grep for `docker/`, `deploy.sh`, `verify.sh`, `Dockerfile` — update each ref or remove if stale.
2. If a layout diagram exists, update to reflect `deploy/` consolidation.

### `docs/system-architecture.md`

1. Same grep treatment as PDR; update or skip per relevance.

### `docs/project-changelog.md`

Add new entry at top:

```markdown
## [Unreleased] — 2026-05-24

### Refactor — Deployment layout consolidation (BREAKING for VPS deploys)

- **Consolidated** all deployment assets into `deploy/`:
  - Moved: `Dockerfile`, `deploy.sh`, `verify.sh`, `.env`, `.env.example` (from root)
  - Moved: `compose.yml`, `compose.prod.yml`, `mongo-init.js` (from `docker/`)
  - Moved: `cleanup.sh`, `server-setup.sh` (from `docker/scripts/`)
  - **Deleted:** `docker/` folder (empty after moves)
- **New folder:** `deploy/scripts/patches/` for future one-time `one_time_*` migrations
- **Removed** stale `python -m scripts.one_time_purge_legacy_strategies` invocation from `deploy.sh` (script no longer exists)
- **Updated:** `justfile` compose paths, `scripts/check_env.py`, `.github/workflows/ci.yml` (added `file: deploy/Dockerfile`), `.run/` IntelliJ configs
- **Unchanged:** `.dockerignore` (stays at root), `scripts/` data-ops Python (not deployment), `packages/pocketquant-web/Dockerfile` (lives with package)

### Migration Required

- **Local dev:** `mv .env deploy/.env` after pulling this change
- **VPS:** see `docs/deployment-guide.md` § "VPS Migration Runbook" — requires one-time `mv` on `/opt/pocketquant`
```

### `README.md`

1. Grep root README for `docker/compose`, `deploy.sh`, `Dockerfile` examples.
2. Update `just up`, `just check`, `just dev` quickstart blocks if they show explicit compose paths.
3. Likely zero changes if README only uses `just` recipes (which abstract the path).

### `scripts/README.md`

Add a 2-line preamble at top:

```markdown
> **Scope:** Data-ops scripts (audit, backfill, resync). NOT deployment.
> For deployment & VPS migration scripts, see `deploy/scripts/`.
```

## Success Criteria

- [ ] `grep -rn "docker/compose\|docker/.env\|docker/scripts" docs/ README.md scripts/README.md` returns zero matches (excluding journals/old-plans)
- [ ] `grep -rn "bash deploy.sh\|bash verify.sh" docs/` returns only `bash deploy/deploy.sh` / `bash deploy/verify.sh` matches
- [ ] `docs/project-changelog.md` top entry documents the move with VPS migration warning
- [ ] `scripts/README.md` clearly delineates data-ops vs deployment
- [ ] No edits to `docs/journals/` (historical) or `plans/260507-*` through `plans/260524-1602-*` (completed plans)

## Risk Assessment

- **Risk:** Missed ref in a doc users will hit (e.g., README quickstart). **Mitigation:** Phase 8 final grep treats docs/ as scope and surfaces orphans.
- **Risk:** Changelog entry undersells the VPS breakage. **Mitigation:** explicit "BREAKING" label + cross-link to runbook in Phase 7.
- **Risk:** PDR / system-architecture have layout diagrams that go stale silently. **Mitigation:** explicit grep step in implementation.
