# Code Review: Move deploy + verify into GitHub Actions

**Date:** 2026-05-28 | **Reviewer:** code-reviewer | **Plan:** `260528-1700-cicd-deploy-into-github-actions`

## Verdict: APPROVED

## Acceptance Criteria — All Pass

1. `cicd.yml` exists, `ci.yml` gone (`ls .github/workflows/` → `cicd.yml`).
2. `name: CI/CD`, `concurrency: {group: deploy, cancel-in-progress: true}` — verified by YAML parse.
3. `deploy.needs: [build-api, build-web]`, `deploy.if` covers develop + master + workflow_dispatch.
4. Secrets used: `VPS_HOST`, `VPS_SSH_KEY`, `PROD_ENV`, `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` — all five present, no others.
5. `ls deploy/` → `Dockerfile compose.prod.yml compose.yml vps/` exactly.
6. `.gitignore` no longer mentions `deploy/deploy.conf` (verified).
7. `docs/deployment.md`: Deploy Command says "Push to master or develop", lists 3 new GH secrets (`VPS_HOST`, `VPS_SSH_KEY`, `PROD_ENV`), Rollback documents both revert-commit + emergency SSH paths.
8. Repo-wide grep for `deploy/deploy.sh|deploy/deploy.conf|WAIT_FOR_CI|CI_BRANCH|CI_WORKFLOW`: zero hits outside (a) `plans/`, (b) `journals/`, (c) `docs/project-changelog.md` line 15 (historical entry), (d) `docs/deployment.md` historical VPS Migration Runbook block at lines 5, 277, 291 (line 5 is the "removed on 2026-05-28" notice — acceptable as it documents the removal; lines 277/291 are inside the historical migration runbook as expected).

## YAML / Security Audit

- YAML parses cleanly; jobs map exactly to plan (build-api, build-web, cleanup-tags, deploy).
- SSH key handling: `VPS_SSH_KEY` flows via step-scoped `env:` then `printf '%s\n' "$VPS_SSH_KEY"` — newline-safe, no shell interpolation of the secret value, chmod 600 applied. Good.
- `PROD_ENV` same pattern — `env:` block + `printf '%s\n'`. No `echo` (which would mangle backslashes). Good.
- `ssh-keyscan -H "$VPS_IP"` swallows stderr — TOFU pinning happens once per runner; acceptable for ephemeral GH runners.
- `VPS_HOST` is exposed via job-level `env:` (not step-level). Acceptable since it's a connection string, not a credential.
- `bash deploy/vps/deploy.sh` and `bash deploy/vps/verify.sh` invocation unchanged — public contract preserved.
- `Fetch verify report` step uses `if: always()` + `|| true` on the ssh — won't mask deploy failure since the deploy step ran earlier and its non-zero exit already fails the job.

## Docs Skill Compatibility

7 standard `/deploy` skill headers all present verbatim in `docs/deployment.md`: Platform (L9), Production URL (L17), Deploy Command (L23), Environment Variables (L50), Custom Domain (L90), Rollback (L99), Troubleshooting (L126).

## Minor Observations (non-blocking)

- `docs/deployment.md` line 113 emergency rollback uses `<VPS_HOST>` as a placeholder while the workflow uses `$VPS_HOST` — convention is consistent within docs (angle brackets = "fill in").
- `deploy/vps/deploy.sh` line 5 stale wrapper comment cleanly updated to reference CI/CD.
- Changelog entry at top of `project-changelog.md` is concise and lists the BREAKING operator action.
- `scripts/README.md` line 4 now correctly points at `cicd.yml` + `deploy/vps/`.
- Concurrency `group: deploy` with `cancel-in-progress: true` means a rapid second push will cancel an in-flight `build-*` job mid-image-push. Docker Hub tag is content-addressed by SHA so no corruption risk; the cancelled `:latest` tag may briefly point at the prior build until the newer run finishes — acceptable per plan ("newest wins").

## Unresolved Questions

None.
