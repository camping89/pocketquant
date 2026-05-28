---
title: "Move deploy + verify into GitHub Actions (CI/CD)"
description: ""
status: completed
priority: P2
branch: "develop"
tags: []
blockedBy: []
blocks: []
created: "2026-05-28T09:28:01.903Z"
completed: "2026-05-28T10:00:00.000Z"
createdBy: "ck:plan"
source: skill
---

# Move deploy + verify into GitHub Actions (CI/CD)

## Overview

Move VPS deploy + verify from operator laptop into GitHub Actions. After this plan, every push to `master`/`develop` triggers an atomic build → deploy → verify pipeline. No more `bash deploy/deploy.sh` on the laptop.

Source design: [brainstorm-cicd-deploy.md](./brainstorm-cicd-deploy.md).

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Add CI/CD deploy job to cicd.yml](./phase-01-add-ci-cd-deploy-job-to-cicd-yml.md) | Completed |
| 2 | [Remove operator-side wrapper artifacts](./phase-02-remove-operator-side-wrapper-artifacts.md) | Completed |
| 3 | [Documentation + reference sweep](./phase-03-documentation-reference-sweep.md) | Completed |

## Key decisions (locked by brainstorm)

- Architecture: GH-hosted ubuntu-latest runner + SSH to VPS.
- Trigger: push to `master` or `develop`, plus `workflow_dispatch`.
- Safety net: `concurrency: deploy` with `cancel-in-progress: true`. No required-reviewer environment.
- Rollback: revert commit + push only. No `workflow_dispatch` image_tag input.
- File layout: rename `ci.yml` → `cicd.yml`, add `deploy` job inside same file.
- Operator wrapper deleted entirely. Emergency SSH still possible from `pocketquant-config/vps/`.

## Operator prerequisites (before Phase 1 merges)

3 GitHub repo secrets must exist:
- `VPS_HOST` = `root@207.148.79.60`
- `VPS_SSH_KEY` = full contents of `pocketquant-config/vps/vultr`
- `PROD_ENV` = full contents of the prod `.env` file (laptop's filled `.env` with `ENVIRONMENT=production`, `LOG_FORMAT=json`)

`DOCKERHUB_USERNAME` + `DOCKERHUB_TOKEN` already exist from current CI.

## Dependencies

None. No cross-plan blocking.

## Out of scope

- Self-hosted runner on VPS.
- GitHub Environment with manual approval.
- Slack / webhook notifications on failure (GH email is enough).
- `workflow_dispatch` input for `image_tag` rollback.
- Staging environment separation.
