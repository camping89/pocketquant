---
phase: 3
title: "Documentation + reference sweep"
status: completed
priority: P2
effort: "1.5h"
dependencies: [1, 2]
---

# Phase 3: Documentation + reference sweep

## Overview

Rewrite `docs/deployment.md` to reflect the CI/CD model: "push to deploy" instead of "operator runs wrapper". Drop operator-wrapper sections, drop env vars that no longer exist (`VPS_HOST`/`VPS_SSH_KEY`/`WAIT_FOR_CI`/`GITHUB_TOKEN`/`GITHUB_REPO`/`CI_*` from `deploy.conf`). Add GH Actions secrets setup. Sweep other docs for stale references.

## Requirements

- Functional:
  - `docs/deployment.md` describes the push-to-deploy flow as the primary path
  - Lists exactly 3 GH secrets to add: `VPS_HOST`, `VPS_SSH_KEY`, `PROD_ENV`
  - Emergency SSH rollback documented (key from `pocketquant-config/vps/`)
  - Revert-commit-and-push documented as the standard rollback flow
- Non-functional:
  - No stale references to `deploy/deploy.sh`, `deploy/deploy.conf`, `deploy.conf.example`, `WAIT_FOR_CI`, `GITHUB_TOKEN`, `GITHUB_REPO` in any tracked file (excluding `docs/journals/` + historical `project-changelog.md` entries)
  - `/deploy` skill still finds the file (preserves top-level Platform / Production URL / Deploy Command / Environment Variables / Custom Domain / Rollback / Troubleshooting section headers)

## Architecture

`docs/deployment.md` keeps two-layer shape:
1. **Top (skill-compatible)**: Platform, Production URL, **Deploy Command** (now: "Push to master or develop, or `gh workflow run cicd.yml`"), Environment Variables, Custom Domain, Rollback, Troubleshooting.
2. **Bottom (operator runbook)**: Architecture, Prerequisites (GH secrets setup), First Deploy, Updating, VPS Migration Runbook (historical), Gap Repair, Local-Dev-Pointing-at-Prod, Firewall, etc.

## Related Code Files

- Modify: `docs/deployment.md` (significant rewrite)
- Modify: `scripts/README.md` — adjust the deploy-related cross-ref (line 4) to drop the `deploy/deploy.sh` mention
- Modify: `README.md` — verify Backend Quick Start section doesn't reference the deleted wrapper
- Modify (optional, log only): `docs/project-changelog.md` — add a 2026-05-28 entry documenting the CI/CD migration

## Implementation Steps

1. **Rewrite `docs/deployment.md` — Deploy Command section** (the heart of the change):

   Replace the current "bash deploy/deploy.sh" centric content with:
   ```markdown
   ## Deploy Command

   Push to `master` or `develop`:
   ```bash
   git push origin develop
   ```
   GitHub Actions handles everything: builds images, syncs files, ssh deploys, verifies. Watch the run on the Actions tab.

   Manual trigger from UI:
   ```bash
   gh workflow run cicd.yml --ref develop
   # or: GitHub repo → Actions → CI/CD → Run workflow
   ```

   **What runs:** 4 jobs in sequence
   1. `build-api` + `build-web` (parallel, ~3-5 min)
   2. `cleanup-tags` (prune old Docker Hub SHA tags)
   3. `deploy`: setup SSH → write `.env` from `PROD_ENV` secret → rsync compose/.env/vps → ssh deploy → ssh verify → upload report

   **Verify report:** download from the run's artifacts (`verify-report`, retained 30 days).
   ```

2. **Rewrite Environment Variables section**:
   - DROP entirely: `WAIT_FOR_CI`, `GITHUB_TOKEN`, `GITHUB_REPO`, `CI_BRANCH`, `CI_WORKFLOW`, `VPS_HOST`/`VPS_SSH_KEY` (these now live as GH secrets, not as local files)
   - REPLACE with GH secrets table:
   ```markdown
   ### GitHub Actions secrets

   Add via repo Settings → Secrets and variables → Actions → New repository secret.

   | Secret | Content | Notes |
   |---|---|---|
   | `VPS_HOST` | `root@<vps-ip>` | The user@host string |
   | `VPS_SSH_KEY` | Paste full contents of `pocketquant-config/vps/vultr` | Multi-line; GH preserves newlines |
   | `PROD_ENV` | Paste full contents of your prod `.env` | Multi-line; this becomes `deploy/.env` on the VPS each deploy |
   | `DOCKERHUB_USERNAME` | (already configured) | |
   | `DOCKERHUB_TOKEN` | (already configured) | |
   ```
   - KEEP local `.env` section but reframe as "local dev only" — Pydantic Settings reads it for `just be` / `just fe`. On the VPS, the same content lives at `/opt/pocketquant/deploy/.env`, regenerated each deploy from `PROD_ENV` secret.

3. **Rewrite Rollback section**:
   ```markdown
   ## Rollback

   ### Standard: revert commit + push
   ```bash
   git revert <bad-sha>
   git push origin develop  # or master
   ```
   CI/CD runs from the reverted HEAD. ~5-8 min from push to VPS healthy on old code.

   ### Emergency: manual SSH (when CI/CD is down or unavailable)
   ```bash
   ssh -i pocketquant-config/vps/vultr root@<vps-ip>
   cd /opt/pocketquant
   IMAGE_TAG=sha-<last-good-short> bash deploy/vps/deploy.sh
   bash deploy/vps/verify.sh
   ```
   CI tags every push as both `:latest` and `:sha-<short>`. Pick the SHA of a known-good commit.

   ### Database rollback
   (unchanged — restore from `pocketquant-mongodb` mongodump archive)
   ```

4. **Add "Prerequisites — GH Actions secrets setup" subsection** under "Operator Runbook → Prerequisites". Replace the laptop-side `.env` setup with the secrets setup.

5. **Drop or trim sections that no longer apply**:
   - "Loads `deploy/deploy.conf`..." pipeline description → replace with "GitHub Actions runs cicd.yml..." pipeline
   - The "First Deploy" and "Updating" sections collapse into: "Set 3 secrets once. Then push to develop / master."
   - "VPS Migration Runbook" (idempotent block) → KEEP, it's a historical doc for existing installs

6. **Update `scripts/README.md` line 4**:
   - Current: `> For deployment & VPS scripts, see deploy/ (deploy/deploy.sh operator wrapper + deploy/vps/ VPS-side scripts).`
   - New: `> For deployment, see .github/workflows/cicd.yml (CI/CD pipeline) + deploy/vps/ (VPS-side scripts called by the pipeline).`

7. **Sweep `README.md`**:
   ```bash
   grep -n "deploy/deploy.sh\|deploy/.env.example\|deploy/deploy.conf" README.md
   ```
   If any matches, replace per the new model.

8. **Repo-wide stale-ref sweep** (excluding historical):
   ```bash
   grep -rn "deploy/deploy\.sh\|deploy/deploy\.conf\|WAIT_FOR_CI\|GITHUB_TOKEN.*deploy\|GITHUB_REPO.*deploy" \
     --include="*.md" --include="*.sh" --include="*.py" --include="*.yml" --include="*.toml" \
     --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=htmlcov --exclude-dir=journals \
     | grep -v project-changelog.md
   ```
   Expected: zero matches. Fix any that surface.

9. **(Optional) Add changelog entry** to `docs/project-changelog.md`:
   ```markdown
   ## [Unreleased] — 2026-05-28 — CI/CD: deploy moves into GitHub Actions (BREAKING for VPS deploys)

   ### Changed
   - Workflow file renamed: `.github/workflows/ci.yml` → `cicd.yml`. Adds `deploy` job that SSHes to VPS after builds succeed.
   - Push to `master` or `develop` now auto-deploys. No more `bash deploy/deploy.sh` from laptop.

   ### Removed
   - `deploy/deploy.sh` (operator wrapper)
   - `deploy/deploy.conf.example` and `deploy/deploy.conf` (operator config)
   - `WAIT_FOR_CI` / `GITHUB_TOKEN` / `GITHUB_REPO` env handling — no longer needed.

   ### Operator action required
   - Add 3 GH repo secrets: `VPS_HOST`, `VPS_SSH_KEY`, `PROD_ENV`. See `docs/deployment.md`.
   ```

## Success Criteria

- [ ] `docs/deployment.md` "Deploy Command" section says "Push to master or develop" as primary
- [ ] `docs/deployment.md` lists exactly 3 new GH secrets to add
- [ ] `docs/deployment.md` Rollback section documents both revert-commit and emergency SSH
- [ ] `scripts/README.md` line 4 updated to point at `.github/workflows/cicd.yml`
- [ ] Repo-wide grep for `deploy/deploy.sh|deploy/deploy.conf|WAIT_FOR_CI` returns zero matches in tracked files (outside `journals/` + `project-changelog.md` historical entries)
- [ ] `docs/deployment.md` still has the 7 skill-recognized section headers (Platform, Production URL, Deploy Command, Environment Variables, Custom Domain, Rollback, Troubleshooting)
- [ ] (Optional) Changelog entry added for 2026-05-28

## Risk Assessment

| Risk | Mitigation |
|---|---|
| `/deploy` skill stops detecting `docs/deployment.md` after rewrite | Preserve top-level section headers verbatim; `grep -n "^## " docs/deployment.md` to verify the 7 standard headers are present |
| Operator reads doc, follows OLD instructions, runs `bash deploy/deploy.sh` (which doesn't exist after Phase 2) | Big bold banner near top: "Deploy is now via GitHub Actions push. The old `bash deploy/deploy.sh` was removed on 2026-05-28." |
| Forgot to update root README Backend Quick Start | Explicit grep in Step 7 + sweep in Step 8 catches it |
| Doc + reality drift later | This phase is the last + uses grep-based verification — if grep returns matches, fix before declaring phase done |

