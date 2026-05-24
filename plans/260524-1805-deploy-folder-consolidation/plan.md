---
title: "Consolidate deployment assets into deploy/ folder"
description: "Move Dockerfile, deploy.sh, verify.sh, docker/* (compose+mongo-init+scripts), .env, .env.example into single deploy/ folder. Delete docker/. Update CI, justfile, check_env.py, docs. Write VPS migration runbook."
status: pending
priority: P2
branch: "develop"
tags: [deploy, refactor, devops, docs]
blockedBy: []
blocks: []
created: "2026-05-24T11:05:53.354Z"
createdBy: "ck:plan"
source: skill
---

# Consolidate deployment assets into deploy/ folder

## Overview

Refactor: consolidate all deployment assets into a single `deploy/` folder. Drives clearer ownership, less root clutter, predictable VPS layout. Mechanical scope — design pre-approved in brainstorm. Critical risk: existing prod VPS at `/opt/pocketquant` has old layout; new layout requires one-time VPS migration.

**Brainstorm context:** `../reports/brainstorm-260524-1741-deploy-folder-consolidation.md`

## End-State Layout

```
pocketquant/
├── deploy/
│   ├── Dockerfile, deploy.sh, verify.sh
│   ├── compose.yml, compose.prod.yml, mongo-init.js
│   ├── .env, .env.example
│   └── scripts/
│       ├── cleanup.sh, server-setup.sh
│       └── patches/README.md       # future one_time_* migrations
├── scripts/                        # UNCHANGED — data-ops Python
├── .dockerignore                   # stays at root
├── packages/pocketquant-web/Dockerfile  # stays
└── ...
```

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Pre-flight cleanup & audit](./phase-01-pre-flight-cleanup-audit.md) | Pending |
| 2 | [Move files (git mv)](./phase-02-move-files-git-mv.md) | Pending |
| 3 | [Update shell scripts](./phase-03-update-shell-scripts.md) | Pending |
| 4 | [Update Docker build & CI](./phase-04-update-docker-build-ci.md) | Pending |
| 5 | [Update dev tooling](./phase-05-update-dev-tooling.md) | Pending |
| 6 | [Update documentation](./phase-06-update-documentation.md) | Pending |
| 7 | [Write VPS migration runbook](./phase-07-write-vps-migration-runbook.md) | Pending |
| 8 | [Local validation](./phase-08-local-validation.md) | Pending |

## Phase Dependencies

- 1 → 2 (audit confirms scope before moving)
- 2 → 3, 4, 5 (files must exist at new paths before updating refs to them)
- 3, 4, 5 → 6 (code refs settled before documenting)
- 6 → 7 (runbook lives inside deployment-guide; runbook content depends on doc structure)
- 1–7 → 8 (validation last)

## Dependencies

None. No active plans overlap (only unfinished plan is `260511-1408-backtest-analysis-panel` — unrelated domain).

## Success Criteria (Plan-level)

- [ ] `docker/` folder deleted; `deploy/` folder is single source of truth for deployment
- [ ] `just up`, `just down`, `just check`, `just dev` all work
- [ ] `docker build -f deploy/Dockerfile .` succeeds locally
- [ ] CI green: both API and Web images build & push
- [ ] All references to old paths (`docker/compose`, root `deploy.sh`, root `Dockerfile`, root `.env`) removed from active code/config
- [ ] `docs/deployment-guide.md` accurate end-to-end including VPS migration runbook
- [ ] `docs/project-changelog.md` documents the reorg as a breaking change

## Divergence Protocol (READ BEFORE IMPLEMENTING)

**Rule:** Stick to the plan. If reality diverges from a phase's assumptions, **improvise to preserve the plan's intent** — do NOT pause for clarification mid-implementation unless the deviation is destructive (data loss, prod outage risk, irreversible change).

**Logging:** Every divergence, judgement call, or new question MUST be appended to:
```
plans/260524-1805-deploy-folder-consolidation/reports/implementation-questions.md
```

**Entry format (one block per item):**
```markdown
## [phase-N] <short title> — <date HH:MM>
**Context:** what the plan said vs what was found
**Decision:** what was done (and why it preserves plan intent)
**Question for review:** [Y/N] does the user need to confirm?
```

**At session end:** print a one-line summary to the user pointing at `implementation-questions.md` for review. Example:
> 3 divergences logged during implementation — review at `plans/260524-1805-deploy-folder-consolidation/reports/implementation-questions.md`

**What counts as a divergence worth logging:**
- A file expected by the plan doesn't exist (or vice versa)
- A path ref count differs from the plan's estimate (e.g., 14 hits where 12 expected)
- A tool/command behaves unexpectedly and a workaround was used
- A step was skipped because it became unnecessary
- A new file/dir was created that wasn't in the phase's "Related Code Files"

**What does NOT need logging:**
- Routine path replacements that match the plan exactly
- Cosmetic edits (whitespace, comment phrasing)
- Pure mechanical execution that matches the phase verbatim

---

## Resolved Questions (user clarifications 2026-05-24 18:35)

1. ✅ `COPY scripts/ scripts/` in Dockerfile — **KEEP** (needed on VPS for in-container script invocations).
2. ✅ Web Dockerfile — **STAYS** in `packages/pocketquant-web/`.
3. ✅ No staging VPS — accept prod risk; **local prod-stack simulation REQUIRED** before push (Phase 8). Runbook includes rollback.
4. ✅ All `.env.*` files → `deploy/`. Currently only `.env` and `.env.example` exist; both already in Phase 2 scope. Policy: any future `.env.*` also lives in `deploy/`.
