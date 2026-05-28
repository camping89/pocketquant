# Brainstorm — Move Deploy + Verify into GitHub Actions (CI/CD)

**Date:** 2026-05-28
**Status:** Design approved, ready for `/ck:plan`

## Problem

Current state: deploy runs from operator laptop via `bash deploy/deploy.sh` (SSH + delta-scp + ssh deploy + ssh verify). Multiple `gh` CLI accounts on laptop cause friction. Operator wants deploy + verify to live as one atomic unit inside GitHub Actions — push triggers everything.

## Constraints (from scout + discovery)

- Monorepo: 4 Python uv workspace + 1 Node SPA.
- Existing CI (`.github/workflows/ci.yml`): `build-api`, `build-web`, `cleanup-tags`. Builds 2 Docker images, tags both `:latest` and `:sha-<short>`, pushes to Docker Hub.
- VPS-side scripts already work: `deploy/vps/deploy.sh` (pull + compose up + 60s health gate), `deploy/vps/verify.sh` (19 checks → markdown report).
- Single VPS (Vultr root@207.148.79.60). Master and develop both deploy to the same VPS — operator confirms they will never push both simultaneously.

## Decisions

| # | Decision | Choice | Reason |
|---|---|---|---|
| 1 | Architecture | GH-hosted runner + SSH | Simplest for single-VPS scale. Self-hosted runner reserved for future multi-VPS need. |
| 2 | Trigger branches | Both `master` and `develop` | Matches existing CI behavior. Single VPS, operator confirms no race risk. |
| 3 | Safety net | Concurrency control only | `concurrency: deploy` cancels in-flight when new push arrives. No GH Environment approval (would break atomic). No Slack webhook (GH email enough). |
| 4 | Rollback | Revert commit + push | Git is the only rollback mechanism. No `workflow_dispatch` image_tag input. Accepts 5-8 min rebuild time. |
| 5 | File layout | Rename `ci.yml` → `cicd.yml`, add `deploy` job in same file | One workflow run shows build + deploy together. Cleaner than cross-workflow `workflow_run` trigger. Rename reflects new CI/CD scope. |
| 6 | Operator wrapper fallback | Delete `deploy/deploy.sh` + `deploy.conf.example` entirely | CI is the only path. Emergency SSH still possible from `pocketquant-config/vps/` if needed. |

## Final architecture

```
push to master or develop
  │
  ├── .github/workflows/cicd.yml
  │     ├── build-api      (build + push Docker image)
  │     ├── build-web      (build + push Docker image)
  │     ├── cleanup-tags   (prune old SHA tags)
  │     │
  │     └── deploy         (needs: [build-api, build-web])
  │           ├── checkout
  │           ├── setup SSH (key from secret)
  │           ├── write deploy/.env from PROD_ENV secret
  │           ├── rsync deploy/compose.prod.yml + .env + vps/ → VPS:/opt/pocketquant/
  │           ├── ssh VPS → bash deploy/vps/deploy.sh    (pull, compose up, health)
  │           ├── ssh VPS → bash deploy/vps/verify.sh    (19 checks)
  │           └── upload verify report as artifact
```

Concurrency: `concurrency: { group: deploy, cancel-in-progress: true }`.

## GitHub Actions secrets to add

| Secret | Content |
|---|---|
| `VPS_HOST` | `root@207.148.79.60` (user@ip) |
| `VPS_SSH_KEY` | Full private key contents (paste of `pocketquant-config/vps/vultr`) |
| `PROD_ENV` | Full prod `.env` file content (single multi-line secret) |
| `DOCKERHUB_USERNAME` | (already exists) |
| `DOCKERHUB_TOKEN` | (already exists) |

## Files to change

| File | Action |
|---|---|
| `.github/workflows/ci.yml` | Rename to `cicd.yml`, add `deploy` job, change top-level `name:` to `CI/CD`, add `concurrency:` block |
| `deploy/deploy.sh` | Delete |
| `deploy/deploy.conf.example` | Delete |
| `.gitignore` | Remove `deploy/deploy.conf` line |
| `docs/deployment.md` | Rewrite: replace operator-wrapper flow with "push to deploy" flow. New GH Actions secrets table. Update Rollback section (revert commit). Drop `WAIT_FOR_CI` / `GITHUB_TOKEN` / `CI_*` references. |
| `scripts/README.md` | Update reference to `deploy/` (drop wrapper mention) |
| `README.md` | Update Backend Quick Start if it mentions deploy |

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| `PROD_ENV` secret drift from VPS `.env` | Single source = GH secret. Manual `.env` on VPS is overwritten every deploy. Document this. |
| SSH known_hosts race on first run | Use `ssh-keyscan` in setup step before any ssh command. |
| Verify fails but containers running broken | `verify.sh` exits non-zero → job fails → red badge. Operator sees failure. Containers stay broken until manual fix or rollback push. |
| Push to master/develop concurrently | Concurrency group cancels older run. Newer wins. Operator confirmed no race in practice. |
| Multi-line `PROD_ENV` secret format | GH secrets preserve newlines. `printf '%s\n' "$PROD_ENV" > deploy/.env` handles correctly. |
| Need urgent rollback during incident | SSH key still in `pocketquant-config/vps/`. Manual: `ssh vps "IMAGE_TAG=sha-<x> bash deploy/vps/deploy.sh"`. Document this escape hatch. |

## Success criteria

1. Push commit to `develop` (or `master`) → within ~3-5 min, VPS is running new code.
2. CI run shows 4 jobs (build-api, build-web, cleanup-tags, deploy) all green.
3. `verify.sh` report uploaded as GH Actions artifact, accessible from run page.
4. Two simultaneous pushes → only latest deploys (older cancelled by concurrency).
5. Operator never opens a terminal for normal deploys.

## Out of scope (this round)

- Self-hosted runner on VPS (future, if SSH-from-CI becomes a security concern).
- GH Environment with required reviewer (would break atomic property; operator chose not to add).
- Slack/webhook notifications (GH email is enough).
- `workflow_dispatch` with `image_tag` input for rollback (rejected — revert commit is the rollback flow).
- Staging environment (single VPS, no separate staging deployment).

## Next steps

Hand off to `/ck:plan` to break into implementation phases. Implementation will touch ~6 files, no application code changes — all infra/CI.
