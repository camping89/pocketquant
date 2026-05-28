---
phase: 1
title: "Restructure pocketquant-config layout + bootstrap script"
status: completed
priority: P2
effort: "30m"
dependencies: []
---

# Phase 1: Restructure pocketquant-config layout + bootstrap script

## Overview

Restructure `pocketquant-config/` so each VPS lives under `vps/<name>/` as a self-contained bundle: `.env`, `host`, `id_rsa`, `id_rsa.pub`, `docker-hub.env`, `portainer.env`. Add idempotent `scripts/bootstrap-gh.sh` (handles initial setup + rotation in one command). Update README.

## Requirements

- Functional:
  - `pocketquant-config/vps/default/` contains 6 files (env, host, id_rsa, id_rsa.pub, docker-hub.env, portainer.env)
  - `docker-hub.env` + `portainer.env` are valid KEY=value shell-source-able files
  - `host` is a single-line `user@ip` string (no extra notes/comments mixed in)
  - `id_rsa` is plain OpenSSH private key (PEM); same content as old `vps/vultr`
  - `scripts/bootstrap-gh.sh` is executable + idempotent (re-run = rotate the deploy key)
  - README documents new layout + bootstrap usage
- Non-functional:
  - File rename done via `git mv` so git history follows
  - `.env.local` untouched
  - No external consumer breakage (only consumers: pocketquant repo + operator)

## Architecture

Before → After:

```
pocketquant-config/                    pocketquant-config/
├── README.md                          ├── README.md                       (updated)
├── .env.local                         ├── .env.local                      (unchanged)
├── .env                          →    ├── scripts/
└── vps/                               │   └── bootstrap-gh.sh              (NEW, executable)
    ├── ssh                            └── vps/
    ├── vultr                              └── default/
    ├── vultr.pub                              ├── .env                    (was: ../.env)
    ├── secrets                                ├── host                    (was: ../vps/ssh, 1-line only)
    └── portainer                              ├── id_rsa                  (was: ../vps/vultr)
                                                ├── id_rsa.pub             (was: ../vps/vultr.pub)
                                                ├── docker-hub.env         (was: ../vps/secrets, reformatted KEY=val)
                                                └── portainer.env          (was: ../vps/portainer, reformatted KEY=val)
```

## Related Code Files

(All paths under `pocketquant-config/`, sibling repo at `/Users/admin/workspace/_me/algo-trading/pocketquant-config/`)

- Create: `scripts/bootstrap-gh.sh`
- Move + rename: `.env` → `vps/default/.env`
- Move + rename: `vps/ssh` → `vps/default/host` (and trim to single `user@ip` line)
- Move + rename: `vps/vultr` → `vps/default/id_rsa`
- Move + rename: `vps/vultr.pub` → `vps/default/id_rsa.pub`
- Move + reformat: `vps/secrets` → `vps/default/docker-hub.env` (ensure `DOCKERHUB_USERNAME=...` + `DOCKERHUB_TOKEN=...` KEY=value)
- Move + reformat: `vps/portainer` → `vps/default/portainer.env` (ensure `PORTAINER_URL=...` + `PORTAINER_PASSWORD=...` KEY=value)
- Modify: `README.md` (document new layout + bootstrap script)

## Implementation Steps

1. `cd /Users/admin/workspace/_me/algo-trading/pocketquant-config`
2. Inspect current contents of `vps/secrets` + `vps/portainer` + `vps/ssh` to determine current shape (might already be KEY=value, might be 2-line plain).
3. `mkdir -p vps/default scripts`
4. Move files preserving history:
   ```bash
   git mv .env              vps/default/.env
   git mv vps/vultr         vps/default/id_rsa
   git mv vps/vultr.pub     vps/default/id_rsa.pub
   git mv vps/ssh           vps/default/host
   git mv vps/secrets       vps/default/docker-hub.env
   git mv vps/portainer     vps/default/portainer.env
   ```
5. Trim `vps/default/host` to a single line `user@ip` (e.g. `root@207.148.79.60`). Remove the "SSH Guide" comment block.
6. Reformat `vps/default/docker-hub.env` so each line is `KEY=value` (no extra prose). Expected keys: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`.
7. Reformat `vps/default/portainer.env` to `KEY=value`. Expected keys: `PORTAINER_URL`, `PORTAINER_PASSWORD`.
8. Verify `vps/default/.env` still starts with the production header comment (`# PocketQuant Production Configuration (VPS: 207.148.79.60)`). Add `ENVIRONMENT=production` + `LOG_FORMAT=json` if missing.
9. Verify `vps/default/id_rsa` is unchanged (same OpenSSH private key).
10. Create `scripts/bootstrap-gh.sh` (content below). `chmod +x scripts/bootstrap-gh.sh`.
11. Update `README.md` Layout section to reflect the new tree, plus a "Bootstrap" section showing how to run `scripts/bootstrap-gh.sh`. Drop the misleading "Sensitive subfolders should be gitignored locally" line (the repo IS the secret store, no `.gitignore`).
12. `git status` → expected: 6 renames + 1 new file (`scripts/bootstrap-gh.sh`) + 1 modified (`README.md`). No untracked.
13. Do NOT push yet — Phase 4 will push after pocketquant CI/CD is ready.

### bootstrap-gh.sh content

```bash
#!/usr/bin/env bash
# One-time setup + idempotent rotation: generate deploy key, attach to
# camping89/pocketquant-config (read-only), push private half as
# POCKETQUANT_CONFIG_DEPLOY_KEY secret in camping89/pocketquant.
#
# Re-run to rotate. Old deploy key with same title is deleted first.
set -euo pipefail

CONFIG_REPO="camping89/pocketquant-config"
CONSUMER_REPO="camping89/pocketquant"
KEY_PATH="$HOME/.ssh/pocketquant-config-deploy"
KEY_TITLE="pocketquant-cicd"
SECRET_NAME="POCKETQUANT_CONFIG_DEPLOY_KEY"

command -v gh >/dev/null || { echo "gh CLI required"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "gh not authenticated"; exit 1; }

if [[ ! -f "$KEY_PATH" ]]; then
  echo "Generating ed25519 key at $KEY_PATH"
  ssh-keygen -t ed25519 -f "$KEY_PATH" -N "" -C "$KEY_TITLE"
else
  echo "Reusing existing key at $KEY_PATH"
fi

echo "Removing any existing deploy key with title '$KEY_TITLE' on $CONFIG_REPO"
gh api "repos/$CONFIG_REPO/keys" --jq ".[] | select(.title==\"$KEY_TITLE\") | .id" 2>/dev/null \
  | while read -r kid; do
      [[ -n "$kid" ]] && gh api -X DELETE "repos/$CONFIG_REPO/keys/$kid"
    done

echo "Adding deploy key to $CONFIG_REPO (read-only)"
gh repo deploy-key add "$KEY_PATH.pub" --repo "$CONFIG_REPO" --title "$KEY_TITLE"

echo "Pushing private half to $CONSUMER_REPO as $SECRET_NAME"
gh secret set "$SECRET_NAME" --repo "$CONSUMER_REPO" --body "$(cat "$KEY_PATH")"

echo "Done. Re-run this script anytime to rotate."
```

### README "Bootstrap" addition (excerpt)

```markdown
## Bootstrap (one-time + rotation)

Set up — or rotate — the GitHub Actions deploy key used by `pocketquant`'s CI/CD:

\`\`\`bash
bash scripts/bootstrap-gh.sh
\`\`\`

Idempotent. Re-running deletes the old key + generates + uploads a new one.

Prereqs:
- `gh` CLI authenticated as a user with admin on both `camping89/pocketquant-config` and `camping89/pocketquant`.
```

## Success Criteria

- [ ] `ls vps/default/` shows exactly: `.env  docker-hub.env  host  id_rsa  id_rsa.pub  portainer.env`
- [ ] `cat vps/default/host` outputs exactly 1 line `user@ip` (no comments, no extra blank lines)
- [ ] `bash -n vps/default/docker-hub.env` exits 0 + `grep -q '^DOCKERHUB_USERNAME='` + `grep -q '^DOCKERHUB_TOKEN='`
- [ ] `bash -n vps/default/portainer.env` exits 0 + `grep -q '^PORTAINER_URL='` + `grep -q '^PORTAINER_PASSWORD='`
- [ ] `grep -q '^ENVIRONMENT=production' vps/default/.env`
- [ ] `grep -q '^LOG_FORMAT=json' vps/default/.env`
- [ ] `head -1 vps/default/id_rsa` starts with `-----BEGIN OPENSSH PRIVATE KEY-----`
- [ ] `[ -x scripts/bootstrap-gh.sh ]`
- [ ] `bash -n scripts/bootstrap-gh.sh` exits 0
- [ ] `README.md` mentions `vps/default/` layout + `scripts/bootstrap-gh.sh`
- [ ] `git status` clean apart from intended renames + README + new bootstrap
- [ ] git history preserved for moved files: `git log --follow vps/default/id_rsa | head -5` shows commits from old `vps/vultr`

## Risk Assessment

| Risk | Mitigation |
|---|---|
| CRLF in moved files breaks downstream | Phase 2 composite action does `tr -d '\r'`. Verify with `file vps/default/id_rsa` → "ASCII text"; `file vps/default/.env` → "ASCII text". |
| `vps/secrets` not in KEY=val shape today | Inspect first; reformat manually if free-form. Use `KEY=VAL` no quotes (eval-friendly). |
| `vps/ssh` line 2 has extra content | Trim manually. `head -1 host` must equal `user@ip` literally. |
| `id_rsa` ends without trailing newline | Composite action normalizes; but ssh-add prefers trailing newline. Run `[[ $(tail -c1 vps/default/id_rsa | wc -l) -eq 1 ]] || echo "" >> vps/default/id_rsa`. |
| Operator missing admin on consumer repo | bootstrap-gh.sh exits with clear error from `gh secret set`. |
| Pushing before pocketquant CI is ready | Do NOT push pocketquant-config in Phase 1. Phases 1-3 stay local until smoke-test in Phase 4. |

## Next Steps

- Phase 2: build the composite action that reads these files.
- Bootstrap script will be RUN in Phase 4 (after Phase 3 wires the action).
