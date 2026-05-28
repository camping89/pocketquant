---
phase: 1
title: "Add CI/CD deploy job to cicd.yml"
status: completed
priority: P2
effort: "2h"
dependencies: []
---

# Phase 1: Add CI/CD deploy job to cicd.yml

## Overview

Rename `.github/workflows/ci.yml` → `cicd.yml`, add a `deploy` job that runs after `build-api` + `build-web` succeed. Deploy SSHes into the VPS, syncs `compose.prod.yml` + `.env` + `deploy/vps/*`, runs `deploy.sh` + `verify.sh`, uploads verify report as an artifact.

## Requirements

- Functional:
  - Push to `master` or `develop` → 4 jobs run: `build-api`, `build-web`, `cleanup-tags`, `deploy`.
  - `deploy` only runs if both builds succeed (`needs:` chain).
  - `deploy` skipped on non-master/develop branches unless `workflow_dispatch` was used.
  - Verify report uploaded as `verify-report` artifact, retained 30 days.
  - Concurrency: at most 1 deploy at any time; new push cancels in-flight.
- Non-functional:
  - No secrets logged. Use `env:` block, not interpolation in shell.
  - Job total < 5 min from build-complete to deploy-done.

## Architecture

```
.github/workflows/cicd.yml
├── name: CI/CD
├── on: { push: [master, develop], workflow_dispatch }
├── concurrency: { group: deploy, cancel-in-progress: true }
├── env: { DOCKERHUB_USERNAME: ${{ secrets.DOCKERHUB_USERNAME }} }
└── jobs:
    ├── build-api          (unchanged)
    ├── build-web          (unchanged)
    ├── cleanup-tags       (unchanged, needs: [build-api, build-web])
    └── deploy             (NEW, needs: [build-api, build-web])
        ├── if: develop|master push OR workflow_dispatch
        ├── env: { VPS_HOST: ${{ secrets.VPS_HOST }}, REMOTE_ROOT: /opt/pocketquant }
        └── steps: checkout → setup SSH → write .env → rsync → ssh deploy → ssh verify → upload artifact
```

## Related Code Files

- Rename: `.github/workflows/ci.yml` → `.github/workflows/cicd.yml`
- Modify: same file — change `name:`, add `concurrency:`, append `deploy` job

## Implementation Steps

1. `git mv .github/workflows/ci.yml .github/workflows/cicd.yml`
2. Edit `cicd.yml`:
   - Top: `name: CI` → `name: CI/CD`
   - Below `on:` block, add:
     ```yaml
     concurrency:
       group: deploy
       cancel-in-progress: true
     ```
3. Append `deploy` job at end of `jobs:` block. Full skeleton:
   ```yaml
   deploy:
     runs-on: ubuntu-latest
     needs: [build-api, build-web]
     if: github.ref == 'refs/heads/develop' || github.ref == 'refs/heads/master' || github.event_name == 'workflow_dispatch'
     env:
       VPS_HOST: ${{ secrets.VPS_HOST }}
       REMOTE_ROOT: /opt/pocketquant
     steps:
       - uses: actions/checkout@v4

       - name: Setup SSH
         env:
           VPS_SSH_KEY: ${{ secrets.VPS_SSH_KEY }}
         run: |
           mkdir -p ~/.ssh
           printf '%s\n' "$VPS_SSH_KEY" > ~/.ssh/id_rsa
           chmod 600 ~/.ssh/id_rsa
           VPS_IP="${VPS_HOST#*@}"
           ssh-keyscan -H "$VPS_IP" >> ~/.ssh/known_hosts 2>/dev/null

       - name: Write prod .env from secret
         env:
           PROD_ENV: ${{ secrets.PROD_ENV }}
         run: |
           printf '%s\n' "$PROD_ENV" > deploy/.env

       - name: Sync compose + .env + VPS scripts
         run: |
           ssh "$VPS_HOST" "mkdir -p $REMOTE_ROOT/deploy/vps/patches"
           rsync -avz \
             deploy/compose.prod.yml deploy/.env \
             "$VPS_HOST:$REMOTE_ROOT/deploy/"
           rsync -avz \
             deploy/vps/ \
             "$VPS_HOST:$REMOTE_ROOT/deploy/vps/"

       - name: Deploy on VPS
         run: ssh "$VPS_HOST" "cd $REMOTE_ROOT && bash deploy/vps/deploy.sh"

       - name: Verify on VPS
         run: ssh "$VPS_HOST" "cd $REMOTE_ROOT && bash deploy/vps/verify.sh"

       - name: Fetch verify report
         if: always()
         run: |
           mkdir -p reports
           REPORT=$(ssh "$VPS_HOST" "ls -t $REMOTE_ROOT/deploy/reports/verify-*.md 2>/dev/null | head -1" || true)
           if [ -n "$REPORT" ]; then
             scp "$VPS_HOST:$REPORT" reports/
           fi

       - name: Upload verify report
         if: always()
         uses: actions/upload-artifact@v4
         with:
           name: verify-report
           path: reports/
           retention-days: 30
           if-no-files-found: warn
   ```
4. Lint YAML locally: `yq eval '.' .github/workflows/cicd.yml > /dev/null` (or any YAML linter).
5. Verify operator has added the 3 secrets (`VPS_HOST`, `VPS_SSH_KEY`, `PROD_ENV`) before merging this phase. CI run will fail at the `Setup SSH` step otherwise.
6. Manual test: push to a throwaway branch with the workflow only (no app changes), trigger via `workflow_dispatch`. Observe full run on GH Actions UI.

## Success Criteria

- [ ] `.github/workflows/cicd.yml` exists; `ci.yml` does not
- [ ] `name: CI/CD` at top of file
- [ ] `concurrency: deploy / cancel-in-progress: true` configured
- [ ] `deploy` job has `needs: [build-api, build-web]`
- [ ] `deploy` job has `if:` clause gating to master/develop/workflow_dispatch
- [ ] Workflow YAML passes lint (no syntax errors)
- [ ] Operator confirms 3 secrets exist in repo settings
- [ ] First `workflow_dispatch` run on develop completes all 4 jobs green
- [ ] `verify-report` artifact downloadable from completed run

## Risk Assessment

| Risk | Mitigation |
|---|---|
| SSH key newline corruption from secret | `printf '%s\n'` preserves multi-line; never use `echo` |
| `ssh-keyscan` warns on first run polluting logs | Redirect stderr `2>/dev/null` |
| `PROD_ENV` secret missing → step fails mid-run | Add a pre-check that fails fast with clear error if `$PROD_ENV` empty |
| `rsync` not available on ubuntu-latest | It is — pre-installed on GH runners |
| Concurrent push race | `concurrency` group cancels in-flight; latest wins |
| Verify fails but containers half-running | Verify step `exits 1` → job red → operator must investigate. Containers stay until manual fix or revert+push. |

