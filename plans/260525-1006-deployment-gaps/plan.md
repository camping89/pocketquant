---
title: "Document deployment gaps surfaced during 2026-05-25 deploy"
description: "Close 6 doc/script gaps surfaced by the symbol-selector VPS deploy on 2026-05-25"
status: completed
priority: P2
branch: "develop"
tags: [docs, deployment]
blockedBy: []
blocks: []
created: "2026-05-25T03:07:23.635Z"
createdBy: "ck:plan"
source: skill
---

# Document deployment gaps surfaced during 2026-05-25 deploy

## Overview

Six operational steps used during the 2026-05-25 VPS deploy are missing or under-specified in `docs/deployment-guide.md` and `deploy/` scripts. Close the gaps so the next operator (or me, next month) has a runnable, end-to-end runbook from `git push` → live VPS → smoke-pass.

Source: `plans/reports/deploy-260525-0850-vps-symbol-selector.md` → "Steps NOT Documented".

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Docs + scripts](./phase-01-docs-scripts.md) | Completed |

## Gaps Being Closed

| # | Gap | Current State | Fix |
|---|-----|---------------|-----|
| 1 | SSH key prep on Git Bash (Windows) | only PowerShell `icacls` in docs; Linux/Git-Bash recipe lives in untracked `pocketquant-config/sandbox/ssh` | add Git Bash subsection to docs |
| 2 | Credential layout under `pocketquant-config/sandbox/` | unmapped; only one inline `$KEY=` example | add "Credentials & Config Layout" section |
| 3 | CI wait command | docs say "check Actions tab" | document `gh run watch --exit-status <id>` recipe |
| 4 | Web-route smoke test | not in `verify.sh` or docs | extend `verify.sh` with 3 curl checks (`/`, `/strategies`, `/monitor`) |
| 5 | `WEB_PORT` env var | in `.env.example` but missing from docs Port Map + `deploy.sh` REQUIRED_VARS | add to both |
| 6 | Pre-deploy `git status` discipline | not documented | one-line rule in "Updating" section |

## Dependencies

None.

## Out of Scope

- Refactoring `deploy.sh` or `verify.sh` beyond the targeted additions.
- Adding new credentials or rotating existing ones.
- Touching `pocketquant-config/` (operator-side, not in this repo).
