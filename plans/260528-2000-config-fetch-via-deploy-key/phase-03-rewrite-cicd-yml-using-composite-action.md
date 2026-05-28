---
phase: 3
title: "Rewrite cicd.yml using composite action"
status: completed
priority: P2
effort: "1h"
dependencies: [1, 2]
---

# Phase 3: Rewrite cicd.yml using composite action

## Overview

Wire `get-vps-config` (Phase 2) into all 4 jobs of `.github/workflows/cicd.yml`. Each job (build-api, build-web, cleanup-tags, deploy) calls the composite action at its top to fetch what it needs. Drop the workflow-level `env: DOCKERHUB_USERNAME: ${{ secrets.* }}` since the value now comes from the action. Drop references to `${{ secrets.VPS_HOST }}`, `${{ secrets.VPS_SSH_KEY }}`, `${{ secrets.PROD_ENV }}`, `${{ secrets.DOCKERHUB_USERNAME }}`, `${{ secrets.DOCKERHUB_TOKEN }}` — replace with `${{ steps.cfg.outputs.* }}`.

Approach A: each job re-fetches. Parallel clones. Auto-mask. No cross-job leak.

## Requirements

- Functional:
  - Single GH Actions secret referenced anywhere in `cicd.yml`: `POCKETQUANT_CONFIG_DEPLOY_KEY`
  - `build-api` + `build-web` use `cfg.outputs.dockerhub_username` + `cfg.outputs.dockerhub_token` for `docker/login-action` + image tags
  - `cleanup-tags` uses `cfg.outputs.dockerhub_username` + `cfg.outputs.dockerhub_token` for the prune loop
  - `deploy` uses `cfg.outputs.vps_host` + `cfg.outputs.ssh_key` + `cfg.outputs.env_content` for SSH setup + `.env` write + rsync/ssh commands
  - Top-level `env:` block removed (no longer needed)
  - Concurrency block unchanged: `group: deploy / cancel-in-progress: true`
  - `if:` clause on `deploy` job unchanged: `develop || master || workflow_dispatch`
- Non-functional:
  - YAML lints cleanly (yaml.safe_load)
  - No `${{ secrets.DOCKERHUB_* }}`, `${{ secrets.VPS_* }}`, `${{ secrets.PROD_ENV }}` references anywhere
  - SSH key written to `~/.ssh/id_rsa` via `env:` block (not direct `${{ }}` in script body, to avoid value appearing in step-log preamble)

## Architecture

```yaml
name: CI/CD
on:
  push: { branches: [master, develop] }
  workflow_dispatch:

concurrency:
  group: deploy
  cancel-in-progress: true

jobs:
  build-api:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - id: cfg
        uses: ./.github/actions/get-vps-config
        with:
          deploy-key: ${{ secrets.POCKETQUANT_CONFIG_DEPLOY_KEY }}
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          username: ${{ steps.cfg.outputs.dockerhub_username }}
          password: ${{ steps.cfg.outputs.dockerhub_token }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ steps.cfg.outputs.dockerhub_username }}/pocketquant
          tags: |
            type=raw,value=latest
            type=sha,prefix=sha-,format=short
      - uses: docker/build-push-action@v5
        with:
          context: .
          file: deploy/Dockerfile
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  build-web:
    # same shape; images: ${{ steps.cfg.outputs.dockerhub_username }}/pocketquant-web
    # context: ./packages/pocketquant-web

  cleanup-tags:
    runs-on: ubuntu-latest
    needs: [build-api, build-web]
    steps:
      - uses: actions/checkout@v4
      - id: cfg
        uses: ./.github/actions/get-vps-config
        with:
          deploy-key: ${{ secrets.POCKETQUANT_CONFIG_DEPLOY_KEY }}
      - name: Prune old Docker Hub tags
        env:
          DH_U: ${{ steps.cfg.outputs.dockerhub_username }}
          DH_T: ${{ steps.cfg.outputs.dockerhub_token }}
        run: |
          TOKEN=$(curl -s -H "Content-Type: application/json" \
            -X POST -d "{\"username\":\"$DH_U\",\"password\":\"$DH_T\"}" \
            https://hub.docker.com/v2/users/login/ | jq -r .token)
          # ... rest of prune loop using $DH_U
          # (refer to current cicd.yml lines 90-112 for full loop; substitute env vars)

  deploy:
    runs-on: ubuntu-latest
    needs: [build-api, build-web]
    if: github.ref == 'refs/heads/develop' || github.ref == 'refs/heads/master' || github.event_name == 'workflow_dispatch'
    env:
      REMOTE_ROOT: /opt/pocketquant
    steps:
      - uses: actions/checkout@v4
      - id: cfg
        uses: ./.github/actions/get-vps-config
        with:
          deploy-key: ${{ secrets.POCKETQUANT_CONFIG_DEPLOY_KEY }}
      - name: Setup SSH
        env:
          SSH_KEY: ${{ steps.cfg.outputs.ssh_key }}
          VPS_HOST: ${{ steps.cfg.outputs.vps_host }}
        run: |
          mkdir -p ~/.ssh
          printf '%s' "$SSH_KEY" > ~/.ssh/id_rsa
          chmod 600 ~/.ssh/id_rsa
          ssh-keyscan -H "${VPS_HOST#*@}" >> ~/.ssh/known_hosts 2>/dev/null
      - name: Write prod .env
        env:
          ENV_CONTENT: ${{ steps.cfg.outputs.env_content }}
        run: printf '%s' "$ENV_CONTENT" > deploy/.env
      - name: Sync + deploy + verify
        env:
          VPS_HOST: ${{ steps.cfg.outputs.vps_host }}
        run: |
          ssh "$VPS_HOST" "mkdir -p $REMOTE_ROOT/deploy/vps/patches"
          rsync -avz deploy/compose.prod.yml deploy/.env "$VPS_HOST:$REMOTE_ROOT/deploy/"
          rsync -avz deploy/vps/ "$VPS_HOST:$REMOTE_ROOT/deploy/vps/"
          ssh "$VPS_HOST" "cd $REMOTE_ROOT && bash deploy/vps/deploy.sh"
          ssh "$VPS_HOST" "cd $REMOTE_ROOT && bash deploy/vps/verify.sh"
      - name: Fetch verify report
        if: always()
        env:
          VPS_HOST: ${{ steps.cfg.outputs.vps_host }}
        run: |
          mkdir -p reports
          REPORT=$(ssh "$VPS_HOST" "ls -t $REMOTE_ROOT/deploy/reports/verify-*.md 2>/dev/null | head -1" || true)
          [ -n "$REPORT" ] && scp "$VPS_HOST:$REPORT" reports/
      - name: Upload verify report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: verify-report
          path: reports/
          retention-days: 30
          if-no-files-found: warn
```

## Related Code Files

- Modify: `.github/workflows/cicd.yml` (rewrite all 4 jobs)

## Implementation Steps

1. Open `.github/workflows/cicd.yml`. Capture exact current `build-api` / `build-web` / `cleanup-tags` shape (image names, tags, cache settings, context paths) so the rewrite preserves them.
2. **Top-level changes:**
   - Remove the `env: DOCKERHUB_USERNAME: ${{ secrets.DOCKERHUB_USERNAME }}` block entirely.
   - Keep `name: CI/CD`, `on:`, `concurrency:` unchanged.
3. **build-api job:**
   - Add `- id: cfg / uses: ./.github/actions/get-vps-config / with: { deploy-key: ${{ secrets.POCKETQUANT_CONFIG_DEPLOY_KEY }} }` immediately after `- uses: actions/checkout@v4`.
   - Replace `${{ env.DOCKERHUB_USERNAME }}` → `${{ steps.cfg.outputs.dockerhub_username }}` in `docker/login-action` username + `images:` line.
   - Replace `${{ secrets.DOCKERHUB_TOKEN }}` → `${{ steps.cfg.outputs.dockerhub_token }}` in `docker/login-action` password.
   - Replace "Verify pushed images" `echo "Repository: ${{ env.DOCKERHUB_USERNAME }}/pocketquant"` — note this echoes the username. Use `env: { DH_U: ${{ steps.cfg.outputs.dockerhub_username }} }` + `echo "Repository: $DH_U/pocketquant"` so masking applies.
4. **build-web job:** same as build-api but image name `pocketquant-web` + context `./packages/pocketquant-web`.
5. **cleanup-tags job:**
   - Add the `- id: cfg / uses: ./.github/actions/get-vps-config / with: ...` step.
   - Inside the "Prune old Docker Hub tags" step, set `env: { DH_U: ${{ steps.cfg.outputs.dockerhub_username }}, DH_T: ${{ steps.cfg.outputs.dockerhub_token }} }`.
   - Replace `${{ env.DOCKERHUB_USERNAME }}` → `$DH_U` and `${{ secrets.DOCKERHUB_TOKEN }}` → `$DH_T` in the shell body.
6. **deploy job:**
   - Replace the existing `env: { VPS_HOST: ${{ secrets.VPS_HOST }}, REMOTE_ROOT: /opt/pocketquant }` block with just `env: { REMOTE_ROOT: /opt/pocketquant }`. VPS_HOST will come from action outputs.
   - Add `- id: cfg / uses: ./.github/actions/get-vps-config / with: ...` step immediately after `- uses: actions/checkout@v4`.
   - Replace "Setup SSH" step: drop `env: { VPS_SSH_KEY: ${{ secrets.VPS_SSH_KEY }} }`; use `env: { SSH_KEY: ${{ steps.cfg.outputs.ssh_key }}, VPS_HOST: ${{ steps.cfg.outputs.vps_host }} }`. Body unchanged except `printf '%s\n' "$VPS_SSH_KEY"` → `printf '%s' "$SSH_KEY"` (composite action already ensures trailing newline via normalize()).
   - Replace "Write prod .env from secret" step: drop `env: { PROD_ENV: ${{ secrets.PROD_ENV }} }`; use `env: { ENV_CONTENT: ${{ steps.cfg.outputs.env_content }} }`. Body: `printf '%s' "$ENV_CONTENT" > deploy/.env`.
   - Each subsequent step that uses `$VPS_HOST` now needs `env: { VPS_HOST: ${{ steps.cfg.outputs.vps_host }} }` because the job-level `VPS_HOST` env was removed. Apply to: "Sync compose...", "Deploy on VPS", "Verify on VPS", "Fetch verify report".
7. Run YAML lint: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/cicd.yml'))"` (use skills venv if standard python lacks yaml).
8. Grep for any remaining stale secret references:
   ```bash
   grep -nE "secrets\.(DOCKERHUB_USERNAME|DOCKERHUB_TOKEN|VPS_HOST|VPS_SSH_KEY|PROD_ENV)" .github/workflows/cicd.yml
   ```
   Expected: zero matches.
9. Grep that `POCKETQUANT_CONFIG_DEPLOY_KEY` is the only secret referenced:
   ```bash
   grep -oE "secrets\.[A-Z_]+" .github/workflows/cicd.yml | sort -u
   ```
   Expected: exactly `secrets.POCKETQUANT_CONFIG_DEPLOY_KEY`.
10. Do NOT push yet — Phase 4 smoke-tests first.

## Success Criteria

- [ ] `cicd.yml` parses as valid YAML
- [ ] `grep -c 'secrets\.POCKETQUANT_CONFIG_DEPLOY_KEY' cicd.yml` returns 4 (one per job)
- [ ] `grep -E 'secrets\.(DOCKERHUB_USERNAME|DOCKERHUB_TOKEN|VPS_HOST|VPS_SSH_KEY|PROD_ENV)' cicd.yml` returns zero matches
- [ ] All 4 jobs have an `- id: cfg / uses: ./.github/actions/get-vps-config` step after their checkout
- [ ] Top-level `env:` block (with DOCKERHUB_USERNAME) removed
- [ ] `concurrency:` block intact
- [ ] `deploy.if:` clause intact (develop/master/workflow_dispatch)
- [ ] No `${{ secrets.X }}` reference appears in any `run:` script body (only via `env:` block then `$VAR`)

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Workflow runs before `POCKETQUANT_CONFIG_DEPLOY_KEY` secret exists in repo | Phase 4 (bootstrap) MUST run before any push that triggers this workflow. Document in Phase 4 implementation steps. |
| `actions/checkout@v4` of pocketquant-config fails with key issue | Composite action surfaces clear `Permission denied (publickey)` error. Re-run bootstrap-gh.sh. |
| Existing CI consumers (e.g. branch protection rules) reference old job names | Job names unchanged (build-api, build-web, cleanup-tags, deploy). |
| `ssh_key` output line-by-line masking causes `add-mask` log entries that betray key length | GH masks the mask-add log line itself. Acceptable info leak (key length is not secret). |
| First step of action prints the deploy-key in caller's step log | GH auto-masks `${{ secrets.X }}` values everywhere. Verify in smoke-test. |
| `tr -d '\r'` on `id_rsa` corrupts a legitimately-CRLF key | OpenSSH keys are always LF; CRLF would already be corrupt. Safe. |

## Next Steps

- Phase 4 runs bootstrap-gh.sh + smoke-tests on a throwaway branch.
