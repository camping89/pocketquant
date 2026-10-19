---
name: deploy-pipeline-auto-prod-on-master
description: CI/CD auto-deploys to prod VPS (live trading) on EVERY master push; develop pushes run tests only
metadata:
  type: project
---

`.github/workflows/cicd.yml`: push to `master` → tests → build images → **auto-deploy to prod VPS** (`deploy/vps/10-deploy.sh` via SSH). There is no staging. A push to `develop` runs `tests` only; build, tag cleanup and deploy are gated on `refs/heads/master`.

**Why:** single-operator project; but the system trades live money (OKX broker).

**How to apply (reviews):**
- Any multi-commit restructure plan landing on `master` must state whether intermediate commits are push-safe -- each master push is a prod deploy. Mid-plan code/compose mismatches = prod outage.
- `deploy/vps/11-verify.sh` (since 2026-06-11 single-process merge) probes `/api/v1/market-data/symbols` inside pocketquant-app -- closes the old "routeless backend passes /health" hole. Single backend on :41921; no bff container.
- Rollback path is `IMAGE_TAG=sha-<short>` re-run of 10-deploy.sh (10-deploy.sh:9) -- image-only; compose topology rolls back only via git revert + full CI. Flag any plan that changes compose topology without a coordinated rollback note.
- compose project `pocketquant-prod`; 10-deploy.sh:50 already runs `up -d --remove-orphans`.
