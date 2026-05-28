# Brainstorm — Centralize CI/CD config in pocketquant-config (deploy-key fetch)

**Date:** 2026-05-28
**Status:** Design proposed, awaiting approval
**Supersedes:** the 3-secrets-pasted-into-GH approach from `plans/260528-1700-cicd-deploy-into-github-actions/`

## Problem

Just-finalized plan stores VPS_HOST / VPS_SSH_KEY / PROD_ENV as 3 separate GitHub Actions secrets. Operator pastes them manually. Drift risk: file in `pocketquant-config/` ≠ GH paste. Rotate workflow: edit file → paste 3× → push. Doesn't scale.

User wants: ONE deploy key, all config fetched live from `pocketquant-config` at CI-run time. Pattern source: `/Users/admin/workspace/evolve/apps/eve-platform` (`get-secrets` composite action over private `eve-config` repo).

## Constraints (from scout)

- `pocketquant-config` is private GH repo (`camping89/pocketquant-config`, confirmed via gh api). Contains plaintext `.env` (42-line prod), `vps/vultr` (OpenSSH key), `vps/ssh`, `vps/secrets` (Docker Hub), `vps/portainer`. No `.gitignore`.
- pocketquant uses SSH-KEY auth to VPS (eve uses sshpass-password). Different shape: multi-line PEM needs handling.
- Current `pocketquant/.github/workflows/cicd.yml` uses 5 GH secrets (3 VPS + 2 Docker Hub).
- Single VPS, no staging/prod split. User: "no prod, just use vps name, consider this is prod". Folder name = `default`.
- 2 GH accounts on laptop; deploy keys are per-repo (no user binding) — preferred over PAT.

## Decisions (user-locked)

| # | Decision | Choice |
|---|---|---|
| 1 | Pattern | Adapt eve-platform's composite-action-fetches-config pattern |
| 2 | Source of truth | `pocketquant-config/` private repo |
| 3 | Scope: what moves there | ALL — VPS host, SSH key, prod .env, Docker Hub creds, Portainer access creds |
| 4 | SSH key storage in config repo | Separate file `vps/default/id_rsa` (renamed from `vultr`) |
| 5 | Folder structure | `vps/<vps-name>/...` with name `default` (single VPS now; allows multi-VPS later without refactor) |
| 6 | Auto-redeploy on config push | NO — push to config repo = update file only; redeploy needs pocketquant push |
| 7 | Portainer | Keep service container running; only remove access creds from pocketquant docs |
| 8 | Bootstrap | `pocketquant-config/scripts/bootstrap-gh.sh` — idempotent one-command setup + rotation |
| 9 | Cross-job mask | Re-invoke composite action IN EACH job that needs config (approach A). No cross-job output of secret values → `::add-mask::` automatic + faster wall-clock (parallel clones). Eve-platform pattern. |

## Final architecture

```
pocketquant-config/                          (private GH repo, source of truth)
├── README.md                                (update: new layout + bootstrap docs)
├── scripts/
│   └── bootstrap-gh.sh                      (NEW — generates deploy key, attaches to config repo, pushes secret)
├── .env.local                               (untouched — local-dev overrides)
└── vps/
    └── default/                             (single VPS, role=prod implicit)
        ├── .env                             (was: pocketquant-config/.env)
        ├── host                             (root@207.148.79.60 — 1 line; was: vps/ssh)
        ├── id_rsa                           (OpenSSH private key; was: vps/vultr)
        ├── id_rsa.pub                       (was: vps/vultr.pub)
        ├── docker-hub.env                   (DOCKERHUB_USERNAME / DOCKERHUB_TOKEN — KEY=val; was: vps/secrets)
        └── portainer.env                    (PORTAINER_URL / PORTAINER_PASSWORD — KEY=val; was: vps/portainer)

pocketquant/                                 (consumer)
├── .github/
│   ├── actions/
│   │   └── get-vps-config/                  (NEW composite action)
│   │       └── action.yml
│   └── workflows/
│       └── cicd.yml                         (rewrite: 5 GH secrets → 1 + per-job composite-action call)
├── docs/
│   ├── deployment.md                        (rewrite: GH secrets table → 1 deploy key + bootstrap)
│   └── project-changelog.md                 (new entry)
```

GH Actions secrets after migration:
- ADD: `POCKETQUANT_CONFIG_DEPLOY_KEY` (private half of deploy key)
- REMOVE: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `VPS_HOST`, `VPS_SSH_KEY`, `PROD_ENV`

## Composite action contract

`pocketquant/.github/actions/get-vps-config/action.yml`:

```yaml
inputs:
  vps:        { required: true, default: default }     # folder name under vps/
  deploy-key: { required: true }                       # SSH private key (passed from secret)

outputs:
  vps_host           # root@ip (1 line)
  env_content        # multi-line .env content
  ssh_key            # multi-line OpenSSH PEM
  dockerhub_username
  dockerhub_token
  portainer_url
  portainer_password
```

Steps inside the action:
1. `actions/checkout@v4` of `camping89/pocketquant-config` via `ssh-key:` input → `.pq-config/`.
2. Read `vps/<vps>/host` (head -1) → mask + output.
3. Read `vps/<vps>/.env` → for each `K=V` line, `::add-mask::$V`; emit whole file as heredoc `env_content`.
4. Read `vps/<vps>/id_rsa` → mask each line best-effort; emit as heredoc `ssh_key`.
5. `eval` `vps/<vps>/docker-hub.env` + `vps/<vps>/portainer.env` (after CRLF normalize); mask + output each var.
6. Cleanup `rm -rf .pq-config` (always: even on failure).

Normalization: `tr -d '\r'` + ensure trailing newline (otherwise heredoc EOF parsing breaks).

## Updated cicd.yml shape (approach A: re-fetch per job)

Every job that needs config calls the composite action at its top. No cross-job output of secret values → `::add-mask::` works automatically within each job. Parallel clones for build-api/build-web → no wall-clock penalty.

```
build-api / build-web (parallel; each clones pocketquant-config independently):
  - checkout
  - get-vps-config → dockerhub_username, dockerhub_token
  - docker login + buildx + push
  - image name = ${dockerhub_username}/pocketquant{-web}

cleanup-tags (needs: [build-api, build-web]):
  - checkout
  - get-vps-config → dockerhub_username, dockerhub_token
  - prune loop

deploy (needs: [build-api, build-web]):
  - checkout
  - get-vps-config → vps_host, env_content, ssh_key
  - write ssh_key → ~/.ssh/id_rsa (chmod 600); ssh-keyscan vps_host
  - write env_content → deploy/.env
  - rsync + ssh deploy.sh + ssh verify.sh + upload artifact
```

Concurrency: unchanged (`group: deploy, cancel-in-progress: true`).

### Clone overhead

4 jobs × ~3-5s clone each = 12-20s aggregate, but only ~3-5s on critical path (build-api + build-web clone in parallel). cleanup-tags + deploy run sequentially after builds, so their 3-5s clones add to wall-clock — total ~6-10s extra on a 5-min run (<5%).

No re-mask discipline needed: `::add-mask::` registered within composite action applies to the job that called it. Eve-platform pattern.

## Bootstrap script (one command for operator)

`pocketquant-config/scripts/bootstrap-gh.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
CONFIG_REPO="camping89/pocketquant-config"
CONSUMER_REPO="camping89/pocketquant"
KEY_PATH="$HOME/.ssh/pocketquant-config-deploy"
KEY_TITLE="pocketquant-cicd"
SECRET_NAME="POCKETQUANT_CONFIG_DEPLOY_KEY"

[[ -f "$KEY_PATH" ]] || ssh-keygen -t ed25519 -f "$KEY_PATH" -N "" -C "$KEY_TITLE"

# Delete any existing deploy key with same title (rotate-safe)
gh api repos/$CONFIG_REPO/keys --jq ".[] | select(.title==\"$KEY_TITLE\") | .id" \
  | xargs -I {} gh api -X DELETE repos/$CONFIG_REPO/keys/{} 2>/dev/null || true

gh repo deploy-key add "$KEY_PATH.pub" --repo "$CONFIG_REPO" --title "$KEY_TITLE"
gh secret set "$SECRET_NAME" --repo "$CONSUMER_REPO" --body "$(cat "$KEY_PATH")"
echo "Done. Rotate by re-running this script."
```

Idempotent. Rotation = one re-run.

## Implementation phases (preview for /ck:plan handoff)

| # | Phase | Effort |
|---|---|---|
| 1 | Restructure pocketquant-config: `git mv` files into `vps/default/`, rename `vultr`→`id_rsa`, split `ssh`→`host`, normalize `secrets`→`docker-hub.env`, normalize `portainer`→`portainer.env`. Update README. Add `scripts/bootstrap-gh.sh`. | 30m |
| 2 | Add `pocketquant/.github/actions/get-vps-config/action.yml`. | 1h |
| 3 | Rewrite `pocketquant/.github/workflows/cicd.yml`: drop 5-secret env block + inject `get-vps-config` composite-action call at top of build-api / build-web / cleanup-tags / deploy jobs. | 1h |
| 4 | Run bootstrap-gh.sh; smoke-test via `workflow_dispatch` on throwaway branch. Verify all 4 jobs green + verify-report artifact. | 30m |
| 5 | Cleanup: remove 5 old GH secrets via `gh secret delete`. Rewrite `docs/deployment.md` (drop 5-secrets section; drop Portainer URL/password lines; add bootstrap.sh + deploy-key flow). Add `docs/project-changelog.md` entry. | 1h |

Total: ~4h.

## Pros

- 1 GH secret instead of 5
- Config change = `git commit && git push` in pocketquant-config — no GH UI clicks
- Git log = audit trail (richer than GH audit)
- Multi-VPS-ready: add `vps/<new-name>/` folder + change action input
- Bootstrap = 1 command (also handles rotation)
- Mirrors eve-platform pattern (battle-tested at evolve)
- Removes Docker Hub creds from GH secrets too (centralized)

## Cons

- 4 clones per CI run (~6-10s extra on critical path; <5% of 5-min run). Eve-platform tolerates the same.
- Composite action logic duplicated in 4 job-top calls (DRY-ness trade-off for security + parallelism). Mitigated: composite action centralizes the actual fetch logic; jobs just invoke it.
- Typo in pocketquant-config breaks all 4 jobs (no validate-on-push gate IN config repo — out of scope this round)
- `eval` of `docker-hub.env` / `portainer.env` runs arbitrary shell if file is tampered. Threat = self-sabotage by operator. Acceptable. Alternative (awk parsing) is YAGNI.
- Restructure breaks any external consumer of pocketquant-config's current paths. Only consumer = pocketquant itself + operator brain. Safe.

## Risks / mitigations

| Risk | Mitigation |
|---|---|
| Deploy key leak → full pocketquant-config read access | Rotation = re-run `bootstrap-gh.sh`. Document cadence in README. |
| pocketquant-config typo → all CI fails | Add validate-on-push workflow IN config repo (Phase 2 / future). |
| Mask-via-output doesn't preserve across job boundaries | Approach A: design re-fetches in each job — values never cross job boundaries. `::add-mask::` registered by composite action stays valid within the same job. |
| Multi-line SSH key masking imperfect | Best-effort line-by-line `::add-mask::`. Short common strings (BEGIN/END markers) may slip through but no key material leaks. |
| Operator confused by new path | bootstrap.sh + updated README + `docs/deployment.md` rewrite explain end-to-end. |
| `id_rsa` filename clash with operator's SSH config | Bootstrap writes to `~/.ssh/pocketquant-config-deploy` (distinct from `id_rsa`); CI runner writes ephemeral `~/.ssh/id_rsa` inside isolated env. No collision. |
| pocketquant-config has `master` as default branch (not `main`) | Composite action sets `ref: master` explicitly. |

## Success criteria

1. Push to develop or master → all 4 jobs (build-api, build-web, cleanup-tags, deploy) green using ONLY the `POCKETQUANT_CONFIG_DEPLOY_KEY` secret.
2. `gh secret list --repo camping89/pocketquant` shows exactly 1 secret (post-cleanup).
3. Rotating deploy key = `bash pocketquant-config/scripts/bootstrap-gh.sh` then re-trigger deploy → green.
4. Editing `pocketquant-config/vps/default/.env` then `git push` (in config repo) + `gh workflow run cicd.yml` (in pocketquant repo) → VPS gets new env.
5. `docs/deployment.md` no longer mentions Portainer URL/password.
6. Mask working: `verify-report` artifact / job logs contain no plaintext SSH key, Docker Hub token, or `.env` values.

## Out of scope (this round)

- Validate-on-push workflow IN pocketquant-config (typo guard).
- Auto-redeploy via `repository_dispatch` from pocketquant-config (user explicitly declined).
- Multi-env (dev/stag/uat) split — single VPS only.
- Migration of `pocketquant-config/.env.local` (local-dev overrides — untouched).
- Renaming pocketquant-config branch from `master` to `main`.

## Open questions

None. Ready for /ck:plan.
