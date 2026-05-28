---
phase: 4
title: "Bootstrap + smoke-test on throwaway branch"
status: pending
priority: P2
effort: "30m"
dependencies: [1, 2, 3]
---

# Phase 4: Bootstrap + smoke-test on throwaway branch

## Overview

Run `pocketquant-config/scripts/bootstrap-gh.sh` to create the deploy key + push `POCKETQUANT_CONFIG_DEPLOY_KEY` secret. Push pocketquant-config restructure to its `master`. Push pocketquant Phase 2+3 changes to a throwaway branch. Trigger CI/CD via `workflow_dispatch`. Validate all 4 jobs green + verify-report artifact uploaded + no secret values in logs.

## Requirements

- Functional:
  - `gh secret list --repo camping89/pocketquant` shows `POCKETQUANT_CONFIG_DEPLOY_KEY` (and the old 5 secrets still — Phase 5 removes them)
  - `gh api repos/camping89/pocketquant-config/keys --jq '.[].title'` includes `pocketquant-cicd`
  - pocketquant-config master branch contains the new `vps/default/` layout + `scripts/bootstrap-gh.sh`
  - pocketquant throwaway branch (e.g. `feat/cicd-config-fetch-smoke`) pushed with Phase 2+3 changes
  - `gh workflow run cicd.yml --ref feat/cicd-config-fetch-smoke` triggers all 4 jobs green
  - `verify-report` artifact downloadable from the run
- Non-functional:
  - Job logs contain ZERO plaintext SSH key lines, Docker Hub token, or `.env` values
  - No accidental push to `develop` / `master` during smoke-test

## Architecture

Order of operations is CRITICAL — secret + repo content must be in place BEFORE workflow runs:

```
1. (pocketquant-config) git push origin master       # Phase 1 restructure becomes live
2. (laptop) bash scripts/bootstrap-gh.sh             # creates deploy key + adds POCKETQUANT_CONFIG_DEPLOY_KEY
3. (pocketquant) git checkout -b feat/cicd-config-fetch-smoke
4. (pocketquant) git add .github/actions/get-vps-config .github/workflows/cicd.yml
5. (pocketquant) git commit + git push origin feat/cicd-config-fetch-smoke
6. (laptop) gh workflow run cicd.yml --ref feat/cicd-config-fetch-smoke
7. (laptop) gh run watch <run-id> → all 4 jobs green
8. (laptop) gh run view <run-id> --log | grep -i "BEGIN OPENSSH\|password=\|dockerhub_token=\|MONGO_PASSWORD" → expect ZERO hits (mask working)
9. (laptop) gh run download <run-id> -n verify-report → confirm artifact downloaded
```

## Related Code Files

(No code changes in this phase — this is a verification phase.)

- Read: `pocketquant-config/scripts/bootstrap-gh.sh` (Phase 1 product)
- Read: `pocketquant/.github/actions/get-vps-config/action.yml` (Phase 2 product)
- Read: `pocketquant/.github/workflows/cicd.yml` (Phase 3 product)

## Implementation Steps

1. **Push pocketquant-config restructure first** (must precede CI run, otherwise composite action reads stale layout):
   ```bash
   cd /Users/admin/workspace/_me/algo-trading/pocketquant-config
   git status   # verify Phase 1 changes staged
   git commit -m "refactor: restructure to vps/default/ + add bootstrap script"
   git push origin master
   ```
2. **Bootstrap deploy key + GH secret:**
   ```bash
   bash scripts/bootstrap-gh.sh
   ```
   Confirm output ends with "Done." + no error.
3. **Verify secret + deploy key exist:**
   ```bash
   gh secret list --repo camping89/pocketquant | grep POCKETQUANT_CONFIG_DEPLOY_KEY
   gh api repos/camping89/pocketquant-config/keys --jq '.[] | select(.title=="pocketquant-cicd") | .id'
   ```
   Both must return non-empty.
4. **Create throwaway branch in pocketquant + push:**
   ```bash
   cd /Users/admin/workspace/_me/algo-trading/pocketquant
   git checkout -b feat/cicd-config-fetch-smoke
   git add .github/actions/get-vps-config/action.yml .github/workflows/cicd.yml
   git commit -m "feat(cicd): fetch all config from pocketquant-config via deploy key"
   git push -u origin feat/cicd-config-fetch-smoke
   ```
5. **Trigger workflow:**
   ```bash
   gh workflow run cicd.yml --ref feat/cicd-config-fetch-smoke
   sleep 5
   gh run list --workflow=cicd.yml --branch=feat/cicd-config-fetch-smoke --limit=1
   ```
   Note the run ID.
6. **Watch the run:**
   ```bash
   gh run watch <run-id>
   ```
   Expect all 4 jobs (build-api, build-web, cleanup-tags, deploy) to finish green within ~5-6 min.
7. **Log scrub (CRITICAL — mask hygiene verification):**
   ```bash
   gh run view <run-id> --log > /tmp/smoke-cicd-log.txt
   # check no plaintext secrets leaked
   grep -E "(BEGIN OPENSSH PRIVATE KEY|MONGO_PASSWORD=[^*])" /tmp/smoke-cicd-log.txt && echo "LEAK!" || echo "Clean"
   grep -E "(dockerhub_token|PORTAINER_PASSWORD)=[^*]" /tmp/smoke-cicd-log.txt && echo "LEAK!" || echo "Clean"
   rm /tmp/smoke-cicd-log.txt
   ```
   Expected: "Clean" both times. (Mask renders values as `***` in logs.)
8. **Verify-report artifact:**
   ```bash
   gh run download <run-id> -n verify-report -D /tmp/verify-report
   ls /tmp/verify-report/  # expect a verify-*.md file
   cat /tmp/verify-report/verify-*.md | head -20
   rm -rf /tmp/verify-report
   ```
9. **Verify VPS is actually running new code** (deploy job actually deployed):
   ```bash
   ssh root@207.148.79.60 'docker ps --format "table {{.Names}}\t{{.Status}}" | grep pocketquant'
   ssh root@207.148.79.60 'docker exec pocketquant-app curl -s http://localhost:41920/health'
   ```
   Expected: 5 containers running + `/health` returns 200.
10. **Cleanup throwaway branch (after success):**
    ```bash
    git checkout develop
    git branch -D feat/cicd-config-fetch-smoke
    git push origin --delete feat/cicd-config-fetch-smoke
    ```

## Success Criteria

- [ ] pocketquant-config master contains `vps/default/` layout + `scripts/bootstrap-gh.sh`
- [ ] `gh secret list --repo camping89/pocketquant` includes `POCKETQUANT_CONFIG_DEPLOY_KEY`
- [ ] Throwaway-branch CI/CD run shows all 4 jobs green
- [ ] Log scrub finds zero plaintext secrets (SSH key, Docker Hub token, MongoDB password, Portainer password)
- [ ] `verify-report` artifact downloadable
- [ ] VPS `/health` returns 200 after the deploy
- [ ] Throwaway branch deleted (local + remote) after success

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Bootstrap script fails because operator authenticated as `vu-remote-dev-fdt` (not `camping89`) | Pre-check: `gh auth status` — switch to `camping89` first via `gh auth switch --user camping89`. |
| Smoke-test push to throwaway branch accidentally triggers branch-deploy due to old `if:` clause | New `if:` only matches `develop`, `master`, or `workflow_dispatch`. Throwaway branch `feat/*` is not matched → `deploy` job is skipped UNLESS triggered by `workflow_dispatch`. **For smoke test, MUST use `workflow_dispatch`** so the deploy job actually runs (push alone won't run it). |
| `gh workflow run` finds the workflow file with old name `ci.yml` | Phase 1 of plan 260528-1700 already renamed to `cicd.yml`. Verify with `gh workflow list --repo camping89/pocketquant`. |
| Concurrent deploys (smoke-test + a real push to develop) collide | Concurrency group `deploy / cancel-in-progress: true` cancels older. Smoke first, no concurrent push during. |
| `verify.sh` on VPS fails because env vars from new `PROD_ENV` payload differ from manual `.env` on VPS | `rsync` overwrites the VPS `.env` with content from `PROD_ENV` secret (= `pocketquant-config/vps/default/.env`). Must verify the file contains all required keys (Phase 1 step 8 covered this). |
| New deploy "succeeds" but app is broken (e.g. wrong DB connection) because `.env` got rewritten differently | `verify.sh` includes 19 checks — if app is broken at runtime, verify fails and job goes red. Pre-step: diff `pocketquant-config/vps/default/.env` vs current VPS `/opt/pocketquant/deploy/.env` before bootstrap, address any drift. |

## Next Steps

- Phase 5 deletes the 5 old GH secrets + rewrites docs.
