---
phase: 5
title: "Cleanup old GH secrets + docs sweep"
status: completed
priority: P2
effort: "1h"
dependencies: [4]
---

# Phase 5: Cleanup old GH secrets + docs sweep

## Overview

After smoke-test passes (Phase 4), delete the 5 obsolete GH Actions secrets (`DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `VPS_HOST`, `VPS_SSH_KEY`, `PROD_ENV`). Rewrite `docs/deployment.md` (remove the 3-secrets table — replace with the 1-deploy-key flow + bootstrap-gh.sh reference + Portainer access creds removed). Update `docs/project-changelog.md`. Repo-wide grep sweep for stale references.

## Requirements

- Functional:
  - `gh secret list --repo camping89/pocketquant` shows exactly 1 secret: `POCKETQUANT_CONFIG_DEPLOY_KEY`
  - `docs/deployment.md` GH Actions Secrets section lists only `POCKETQUANT_CONFIG_DEPLOY_KEY` + describes bootstrap-gh.sh
  - `docs/deployment.md` no longer mentions Portainer URL/password (per user decision: container stays, creds out of docs)
  - `docs/project-changelog.md` has a new entry for 2026-05-28 (or current date) describing the migration
  - Repo-wide grep for `VPS_HOST|VPS_SSH_KEY|PROD_ENV|DOCKERHUB_TOKEN.*secret|DOCKERHUB_USERNAME.*secret` returns zero matches in tracked code outside historical/archival paths (plans/, journals/, project-changelog historical entries)
- Non-functional:
  - 7 `/deploy` skill section headers preserved verbatim (Platform, Production URL, Deploy Command, Environment Variables, Custom Domain, Rollback, Troubleshooting)
  - No backward-compat shims (decisively switch to new model)

## Architecture

| Surface | Before | After |
|---|---|---|
| GH Secrets | `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `VPS_HOST`, `VPS_SSH_KEY`, `PROD_ENV` | `POCKETQUANT_CONFIG_DEPLOY_KEY` (1 total) |
| `docs/deployment.md` Prerequisites | "Add 5 GH secrets" table | "Run `bash pocketquant-config/scripts/bootstrap-gh.sh`" + 1-row secret table |
| `docs/deployment.md` Environment Variables | GH Actions secrets table + local-dev `.env` | Pointer to `pocketquant-config/vps/default/.env` (source of truth) + local-dev section unchanged |
| `docs/deployment.md` (Portainer mentions) | URL + password documented | Removed (operator looks up in `pocketquant-config/vps/default/portainer.env`) |
| `docs/project-changelog.md` | Latest entry: 2026-05-28 CI/CD via push (3 secrets) | New entry on top: deploy-key fetch migration |

## Related Code Files

- Modify: `docs/deployment.md`
- Modify: `docs/project-changelog.md`
- (No code-side modifications; pocketquant repo is already in target state from Phase 3 + 4 merge)

## Implementation Steps

1. **Merge throwaway smoke branch** (only after Phase 4 fully green):
   ```bash
   git checkout develop
   git merge feat/cicd-config-fetch-smoke   # OR open PR + merge
   # (alternatively cherry-pick the commit onto develop)
   ```
   `develop` push → triggers a real deploy (using the new config path). Verify green again before proceeding.
2. **Delete the 5 obsolete GH secrets** (verify-twice before deletion):
   ```bash
   gh secret list --repo camping89/pocketquant
   for s in DOCKERHUB_USERNAME DOCKERHUB_TOKEN VPS_HOST VPS_SSH_KEY PROD_ENV; do
     gh secret delete "$s" --repo camping89/pocketquant
   done
   gh secret list --repo camping89/pocketquant   # expect only POCKETQUANT_CONFIG_DEPLOY_KEY
   ```
3. **Rewrite `docs/deployment.md`:**
   - **Prerequisites** section: replace the 5-secret table with:
     ```markdown
     ## Prerequisites
     One-time setup via the bootstrap script in pocketquant-config:
     \`\`\`bash
     cd ../pocketquant-config
     bash scripts/bootstrap-gh.sh
     \`\`\`
     The script generates an ed25519 deploy key, attaches it to `camping89/pocketquant-config` (read-only), and pushes the private half as `POCKETQUANT_CONFIG_DEPLOY_KEY` in `camping89/pocketquant`. Idempotent — re-run anytime to rotate.

     Required GH Actions secrets in `camping89/pocketquant`:
     | Secret | Source |
     |---|---|
     | `POCKETQUANT_CONFIG_DEPLOY_KEY` | Set by bootstrap-gh.sh |
     ```
   - **Environment Variables** section: prod env now lives in `pocketquant-config/vps/default/.env`. Replace the "GitHub Actions secrets" subsection with a "Production config source-of-truth" subsection pointing at that file. Keep the local-dev `.env` table.
   - **Architecture** section: update the pipeline diagram to show "deploy job calls get-vps-config composite action → fetches from pocketquant-config".
   - Remove ALL Portainer URL + admin password lines. Keep the row in Port Map (PORTAINER_PORT is still a port) but drop access-creds documentation. Replace with a single line: "Portainer admin credentials → `pocketquant-config/vps/default/portainer.env`".
   - **Rollback** Emergency SSH command: update path to `pocketquant-config/vps/default/id_rsa` (was `pocketquant-config/vps/vultr`).
   - **Credentials & Config Layout** section: rewrite the file table to reflect new `vps/default/` structure.
   - **Deploy Command** section: keep "Push to develop or master" wording, just verify it's accurate.
4. **Add changelog entry** in `docs/project-changelog.md` (insert above the existing 2026-05-28 entry from plan 260528-1700):
   ```markdown
   ## [Unreleased] — 2026-05-28 — CI/CD: centralize config in pocketquant-config (REFACTOR)

   ### Changed
   - GH Actions secrets reduced 5 → 1: only `POCKETQUANT_CONFIG_DEPLOY_KEY` needed.
   - All config (VPS host, SSH key, prod .env, Docker Hub creds, Portainer creds) now lives in `pocketquant-config/vps/default/`.
   - New composite action `.github/actions/get-vps-config/` clones pocketquant-config at run time and emits config as job-scoped outputs (mask-safe).
   - Each of 4 jobs (build-api / build-web / cleanup-tags / deploy) re-fetches independently → parallel, no cross-job leak.
   - `pocketquant-config` restructured: flat layout → `vps/<vps-name>/` (current single VPS named `default`). Multi-VPS-ready.
   - `pocketquant-config/scripts/bootstrap-gh.sh` — idempotent setup + rotation.

   ### Removed
   - GH Actions secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `VPS_HOST`, `VPS_SSH_KEY`, `PROD_ENV`.
   - Portainer access creds from `docs/deployment.md` (creds source-of-truth is now `pocketquant-config/vps/default/portainer.env`; container still deployed unchanged).

   ### Operator action required
   - One-time: run `bash pocketquant-config/scripts/bootstrap-gh.sh` (creates deploy key + GH secret).
   - To rotate the deploy key: re-run the same script.
   - To change prod env: edit `pocketquant-config/vps/default/.env`, `git push`, then push a commit to pocketquant (or `gh workflow run cicd.yml`).
   ```
5. **Repo-wide stale-ref sweep:**
   ```bash
   grep -rnE "secrets\.(DOCKERHUB_USERNAME|DOCKERHUB_TOKEN|VPS_HOST|VPS_SSH_KEY|PROD_ENV)\b" \
     --include="*.md" --include="*.sh" --include="*.py" --include="*.yml" --include="*.toml" \
     --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=htmlcov --exclude-dir=journals --exclude-dir=plans . \
     | grep -v "project-changelog.md"
   ```
   Expected: zero matches.
6. **Verify 7 skill headers still present in `docs/deployment.md`:**
   ```bash
   grep -nE "^## (Platform|Production URL|Deploy Command|Environment Variables|Custom Domain|Rollback|Troubleshooting)$" docs/deployment.md | wc -l
   ```
   Expected: 7.
7. **Grep for Portainer URL/password leftover in docs:**
   ```bash
   grep -nE "PORTAINER_URL|PORTAINER_PASSWORD|portainer.*password|Portainer admin" docs/deployment.md
   ```
   Expected: only the single pointer line to `pocketquant-config/vps/default/portainer.env`.
8. **Commit + push to develop:**
   ```bash
   git add docs/deployment.md docs/project-changelog.md
   git commit -m "docs: rewrite deployment guide for deploy-key fetch model"
   git push origin develop
   ```
   This last push triggers another CI/CD run. Should be green (all phases now live). Confirm before declaring phase done.

## Success Criteria

- [ ] `gh secret list --repo camping89/pocketquant` shows exactly 1 secret (`POCKETQUANT_CONFIG_DEPLOY_KEY`)
- [ ] `docs/deployment.md` Prerequisites section references `bash scripts/bootstrap-gh.sh` and lists 1 GH secret
- [ ] `docs/deployment.md` no longer prints any Portainer URL or password
- [ ] `docs/deployment.md` Rollback's emergency-SSH command uses `pocketquant-config/vps/default/id_rsa`
- [ ] `docs/project-changelog.md` has new top entry for the migration
- [ ] Repo-wide grep for the 5 old secret names returns zero matches (outside `plans/`, `journals/`, historical changelog entries)
- [ ] 7 `/deploy` skill section headers preserved
- [ ] Final `git push origin develop` triggers a green CI/CD run

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Delete secrets BEFORE merge to develop → next push fails CI | Strict order in Implementation Steps: merge throwaway → confirm green → THEN delete old secrets. |
| Operator runs old `bash deploy/deploy.sh` (already deleted in prior plan) — irrelevant here | Plan 260528-1700 already deleted it. No-op for this plan. |
| Doc rewrite breaks `/deploy` skill detection of `docs/deployment.md` | Step 6 verifies 7 standard headers present. |
| Changelog entry collides with prior 2026-05-28 entry | Insert above prior entry. Two same-day entries are fine (semver `[Unreleased]` allows multiple). |
| Operator deletes `POCKETQUANT_CONFIG_DEPLOY_KEY` accidentally with the loop | Loop only deletes the 5 named old secrets. Re-check the list before running. |
| Final push triggers concurrent deploy with the smoke-test's merge | Concurrency group serializes; latest wins. Acceptable. |

## Next Steps

- (Optional) Future plan: add validate-on-push workflow IN pocketquant-config to catch typos before consumers fail. Out of scope this round.
