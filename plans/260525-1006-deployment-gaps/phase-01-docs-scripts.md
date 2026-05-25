---
phase: 1
title: "Docs + scripts"
status: completed
priority: P2
effort: "45m"
dependencies: []
---

# Phase 1: Docs + scripts

## Overview

Single-pass doc + script edits to close 6 deployment runbook gaps. No new abstractions; targeted additions only.

## Requirements

- Functional:
  - Operator on Windows + Git Bash can follow `docs/deployment-guide.md` end-to-end without grepping `pocketquant-config/sandbox/`.
  - `deploy/verify.sh` exits non-zero when web container fails to serve `/`, `/strategies`, or `/monitor`.
  - `deploy/deploy.sh` rejects `.env` missing `WEB_PORT`.
- Non-functional:
  - Doc additions stay under +120 lines.
  - No restructuring of existing sections — additive only.

## Architecture

Three artefacts touched:
- `docs/deployment-guide.md` — add 3 sections, edit 2 existing.
- `deploy/verify.sh` — add web-route check block (after API /health check).
- `deploy/deploy.sh` — add `WEB_PORT` to REQUIRED_VARS.

## Related Code Files

Modify:
- `docs/deployment-guide.md`
- `deploy/verify.sh`
- `deploy/deploy.sh`

Create / Delete: none.

## Implementation Steps

### Step 1 — `docs/deployment-guide.md` → add "Credentials & Config Layout"

Insert after "Prerequisites" (currently around line 130), before "SSH Session Variables":

```markdown
## Credentials & Config Layout

All operator-side credentials live OUTSIDE this repo, in a sibling
`pocketquant-config/` directory. None of these files should ever be
committed here.

| File | Purpose |
|------|---------|
| `pocketquant-config/sandbox/vultr` | OpenSSH private key for the VPS (`root@<vps-ip>`) |
| `pocketquant-config/sandbox/vultr.pub` | Matching public key |
| `pocketquant-config/sandbox/ssh` | Plain-text: VPS IP + SSH usage snippets (PowerShell + Git Bash + Linux) |
| `pocketquant-config/sandbox/portainer` | Portainer URL + admin password |
| `pocketquant-config/sandbox/secrets` | `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` for image pulls |
| `pocketquant-config/sandbox/plans/` | Operator-side ops journals (not implementation plans) |

Set `$KEY` and `$VPS` from these files (see next section).
```

### Step 2 — `docs/deployment-guide.md` → extend "SSH Session Variables" with Git Bash recipe

Append after the existing PowerShell block:

```markdown
### Git Bash on Windows

`icacls` is PowerShell-only. From Git Bash, copy the key out of the (read-only,
CRLF-tainted) config directory and fix line endings + perms:

```bash
mkdir -p ~/.ssh-pq
cp /d/w/_me/algo-bot/pocketquant-config/sandbox/vultr ~/.ssh-pq/vultr_key
sed -i 's/\r$//' ~/.ssh-pq/vultr_key
chmod 600 ~/.ssh-pq/vultr_key

export KEY=~/.ssh-pq/vultr_key
export VPS=root@207.148.79.60
```

Adjust the source path if your checkout lives elsewhere. Verify with:

```bash
ssh -i "$KEY" "$VPS" 'echo OK'
```
\```
```

### Step 3 — `docs/deployment-guide.md` → "Port Map" table — add `WEB_PORT`

Edit the existing table (currently lists 4 services). Add row:

```markdown
| Web (SPA + reverse proxy to API) | `WEB_PORT` | 80 |
```

### Step 4 — `docs/deployment-guide.md` → "First Deploy → Step 1: Prepare .env" — add `WEB_PORT`

In the `.env` example block, add `WEB_PORT=58922` (or note the dev default of `80`) under the other port lines.

### Step 5 — `docs/deployment-guide.md` → "Updating (2nd+ Deploy)" — add CI wait + git-status rule

Replace the existing one-liner "(check GitHub Actions tab)" with:

```markdown
After pushing code (CI triggers on `master` and `develop`):

```bash
# 0. Verify working tree is clean for the slice you're pushing.
#    Anything still showing in `git status` will NOT be in the deploy.
git status

# 1. Wait for CI to push images. Grab the run ID and watch:
RUN_ID=$(gh run list --workflow=ci.yml --branch=develop --limit=1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status

# 2. Pull and restart on VPS:
ssh -i "$KEY" "$VPS" "cd /opt/pocketquant && bash deploy/deploy.sh"
```
\```
```

### Step 6 — `deploy/deploy.sh` — add `WEB_PORT` to REQUIRED_VARS

Single-line change at line ~36:

```diff
-REQUIRED_VARS="DOCKERHUB_USERNAME MONGO_PASSWORD APP_PORT MONGO_PORT REDIS_PORT PORTAINER_PORT"
+REQUIRED_VARS="DOCKERHUB_USERNAME MONGO_PASSWORD APP_PORT WEB_PORT MONGO_PORT REDIS_PORT PORTAINER_PORT"
```

### Step 7 — `deploy/verify.sh` — add web-route smoke block

Insert after the existing "API /health" check, before MongoDB ping:

```bash
# ─── Web container: SPA routes ──────────────────────────────
WEB_PORT_VAL="${WEB_PORT:-80}"
for path in "/" "/strategies" "/monitor"; do
  http=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${WEB_PORT_VAL}${path}" || echo "000")
  if [ "$http" = "200" ]; then
    check "Web ${path}" "$PASS" "HTTP 200"
  else
    check "Web ${path}" "$FAIL" "HTTP ${http}"
  fi
done
```

Source `.env` at top of `verify.sh` if not already (check existing pattern — likely already does via deploy.sh-style `set -a; source .env; set +a`).

## Success Criteria

- [x] `docs/deployment-guide.md` contains "Credentials & Config Layout" section listing all 5 files under `pocketquant-config/sandbox/`.
- [x] `docs/deployment-guide.md` "SSH Session Variables" includes a "Git Bash on Windows" subsection.
- [x] `docs/deployment-guide.md` Port Map table has a `WEB_PORT` row.
- [x] `docs/deployment-guide.md` "Updating" section names `gh run watch --exit-status` and `git status` pre-check.
- [x] `deploy/deploy.sh` REQUIRED_VARS includes `WEB_PORT`.
- [x] `deploy/verify.sh` runs 3 additional checks (web `/`, `/strategies`, `/monitor`) that fail if HTTP != 200.
- [ ] `bash deploy/verify.sh` on VPS still exits 0 (now 18 checks instead of 15). *(verify on next VPS deploy — not runnable locally)*

## Risk Assessment

- **Risk:** `WEB_PORT` default differs across envs (compose default `80`, prod `.env.example` `80`, live VPS `58922`). Adding it to REQUIRED_VARS makes existing `.env`s that omit it fail validation. **Mitigation:** `.env.example` already declares `WEB_PORT=80`; operators following the guide already have it set. Live VPS `.env` already has `WEB_PORT=58922` (verified during 2026-05-25 deploy). Net impact: zero on current deployments.
- **Risk:** `verify.sh` web checks could false-fail during cold start before web container's healthcheck completes. **Mitigation:** `compose.prod.yml` already has `depends_on: app: condition: service_healthy`; `deploy.sh` waits for `pocketquant-web Healthy` before exiting. Smoke checks run AFTER deploy.sh finishes — should be stable.
- **Risk:** Docs become stale if `pocketquant-config/sandbox/` layout changes. **Mitigation:** layout is small + slow-changing; an annual review is enough.

## Security Considerations

- No secrets added to repo.
- Docs reference `pocketquant-config/sandbox/secrets` by name only — file content remains operator-side and outside this repo.

## Next Steps

After merge:
- One-shot `bash deploy/verify.sh` on VPS to confirm 18/18 PASS.
- No code redeploy required (docs + verify-only changes).
