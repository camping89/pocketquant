---
phase: 2
title: "Add get-vps-config composite action"
status: completed
priority: P2
effort: "1h"
dependencies: [1]
---

# Phase 2: Add get-vps-config composite action

## Overview

Create `pocketquant/.github/actions/get-vps-config/action.yml` — a composite action that, given a deploy key + VPS folder name, clones `pocketquant-config`, reads the 6 files under `vps/<name>/`, masks every value, emits as outputs, then cleans up the checkout.

## Requirements

- Functional:
  - Inputs: `vps` (folder name, default `default`), `deploy-key` (SSH private key string)
  - Outputs: `vps_host`, `env_content`, `ssh_key`, `dockerhub_username`, `dockerhub_token`, `portainer_url`, `portainer_password`
  - Action checks out only `camping89/pocketquant-config@master` via `actions/checkout@v4` with `ssh-key:` input
  - Action errors clearly if `vps/<name>/` directory missing
  - Action normalizes CRLF on all files before parsing
  - Action `::add-mask::`s every non-empty value
  - Action cleans up `.pq-config/` even on failure (`if: always()`)
- Non-functional:
  - No values leak to logs (verify by inspecting a smoke-test run's logs in Phase 4)
  - Composite (not Docker action) — runs in same shell context as caller
  - No external dependencies beyond `actions/checkout@v4` and standard ubuntu-latest tools (bash, tr, head, sed)

## Architecture

```
pocketquant/.github/actions/get-vps-config/
└── action.yml

Action runs:
  1. actions/checkout@v4
       repository: camping89/pocketquant-config
       ref: master
       ssh-key: ${{ inputs.deploy-key }}
       path: .pq-config
       persist-credentials: false
  2. Validate vps/<name>/ exists
  3. Read + normalize + mask + output:
       host           → vps_host (single-line)
       .env           → env_content (multi-line, each KEY=val value masked)
       id_rsa         → ssh_key (multi-line, each line masked best-effort)
       docker-hub.env → dockerhub_username + dockerhub_token (sourced via eval after normalize)
       portainer.env  → portainer_url + portainer_password (sourced via eval after normalize)
  4. rm -rf .pq-config (always)
```

## Related Code Files

- Create: `.github/actions/get-vps-config/action.yml`

## Implementation Steps

1. Create directory: `mkdir -p .github/actions/get-vps-config`
2. Write `action.yml` with the full composite action (content below).
3. Validate YAML syntax: `yq eval '.' .github/actions/get-vps-config/action.yml > /dev/null` (or Python yaml.safe_load).
4. Shellcheck the embedded scripts: copy each `run:` block into a `.sh` temp file and run `shellcheck` to catch obvious issues.
5. Local dry-run of the script logic (without checkout) — point at a local clone of pocketquant-config and step through:
   ```bash
   VPS_DIR="/Users/admin/workspace/_me/algo-trading/pocketquant-config/vps/default"
   # paste the action's bash block, substituting $VPS_DIR for ".pq-config/vps/${{ inputs.vps }}"
   ```
   Confirm all 7 expected outputs would be set + no plaintext value leaked to stdout.
6. Do NOT yet wire it into cicd.yml — Phase 3 does that.

### action.yml content

```yaml
name: 'Get VPS Config from pocketquant-config'
description: 'Clone pocketquant-config (private), read VPS env+key+host+creds, mask + emit as outputs'

inputs:
  vps:
    description: 'VPS folder name under vps/'
    required: true
    default: default
  deploy-key:
    description: 'SSH deploy key (read-only) for pocketquant-config'
    required: true

outputs:
  vps_host:
    description: 'user@ip (single line)'
    value: ${{ steps.read.outputs.vps_host }}
  env_content:
    description: 'Prod .env content (multi-line)'
    value: ${{ steps.read.outputs.env_content }}
  ssh_key:
    description: 'OpenSSH private key (multi-line)'
    value: ${{ steps.read.outputs.ssh_key }}
  dockerhub_username:
    value: ${{ steps.read.outputs.dockerhub_username }}
  dockerhub_token:
    value: ${{ steps.read.outputs.dockerhub_token }}
  portainer_url:
    value: ${{ steps.read.outputs.portainer_url }}
  portainer_password:
    value: ${{ steps.read.outputs.portainer_password }}

runs:
  using: composite
  steps:
    - name: Checkout pocketquant-config (read-only)
      uses: actions/checkout@v4
      with:
        repository: camping89/pocketquant-config
        ref: master
        ssh-key: ${{ inputs.deploy-key }}
        path: .pq-config
        persist-credentials: false

    - name: Read + mask + emit outputs
      id: read
      shell: bash
      env:
        VPS_NAME: ${{ inputs.vps }}
      run: |
        set -euo pipefail
        VPS_DIR=".pq-config/vps/$VPS_NAME"
        if [[ ! -d "$VPS_DIR" ]]; then
          echo "::error::VPS folder not found: $VPS_DIR"
          exit 1
        fi

        # Normalize: strip CR, ensure trailing newline
        normalize() { tr -d '\r' < "$1" | sed -e '$a\'; }

        # 1) host (single line)
        VPS_HOST=$(head -1 "$VPS_DIR/host" | tr -d '\r')
        if [[ -z "$VPS_HOST" ]]; then
          echo "::error::Empty host in $VPS_DIR/host"
          exit 1
        fi
        echo "::add-mask::$VPS_HOST"
        echo "vps_host=$VPS_HOST" >> "$GITHUB_OUTPUT"

        # 2) .env (multi-line). Mask each non-empty value.
        ENV_CONTENT=$(normalize "$VPS_DIR/.env")
        while IFS='=' read -r k v; do
          [[ -z "$k" || "$k" =~ ^[[:space:]]*# ]] && continue
          v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
          [[ -n "$v" ]] && echo "::add-mask::$v"
        done <<< "$ENV_CONTENT"
        {
          echo 'env_content<<DOTENV_EOF'
          printf '%s' "$ENV_CONTENT"
          echo 'DOTENV_EOF'
        } >> "$GITHUB_OUTPUT"

        # 3) ssh_key (multi-line PEM). Best-effort line-level mask.
        SSH_KEY=$(normalize "$VPS_DIR/id_rsa")
        while IFS= read -r line; do
          [[ -n "$line" ]] && echo "::add-mask::$line"
        done <<< "$SSH_KEY"
        {
          echo 'ssh_key<<SSHKEY_EOF'
          printf '%s' "$SSH_KEY"
          echo 'SSHKEY_EOF'
        } >> "$GITHUB_OUTPUT"

        # 4) docker-hub.env (KEY=val pairs). Source-eval after normalize.
        DH_NORM=$(normalize "$VPS_DIR/docker-hub.env")
        eval "$DH_NORM"
        : "${DOCKERHUB_USERNAME:?missing DOCKERHUB_USERNAME in docker-hub.env}"
        : "${DOCKERHUB_TOKEN:?missing DOCKERHUB_TOKEN in docker-hub.env}"
        echo "::add-mask::$DOCKERHUB_USERNAME"
        echo "::add-mask::$DOCKERHUB_TOKEN"
        echo "dockerhub_username=$DOCKERHUB_USERNAME" >> "$GITHUB_OUTPUT"
        echo "dockerhub_token=$DOCKERHUB_TOKEN" >> "$GITHUB_OUTPUT"

        # 5) portainer.env (KEY=val pairs).
        PT_NORM=$(normalize "$VPS_DIR/portainer.env")
        eval "$PT_NORM"
        : "${PORTAINER_URL:?missing PORTAINER_URL in portainer.env}"
        : "${PORTAINER_PASSWORD:?missing PORTAINER_PASSWORD in portainer.env}"
        echo "::add-mask::$PORTAINER_URL"
        echo "::add-mask::$PORTAINER_PASSWORD"
        echo "portainer_url=$PORTAINER_URL" >> "$GITHUB_OUTPUT"
        echo "portainer_password=$PORTAINER_PASSWORD" >> "$GITHUB_OUTPUT"

        echo "Loaded config for VPS '$VPS_NAME' from pocketquant-config (no values logged)"

    - name: Cleanup pocketquant-config checkout
      if: always()
      shell: bash
      run: rm -rf .pq-config
```

## Success Criteria

- [ ] `.github/actions/get-vps-config/action.yml` exists, parses as valid YAML
- [ ] `action.yml` has 7 outputs declared (vps_host, env_content, ssh_key, dockerhub_username, dockerhub_token, portainer_url, portainer_password)
- [ ] `inputs.vps` has default `default`
- [ ] `inputs.deploy-key` is required + has no default
- [ ] Cleanup step has `if: always()`
- [ ] Shellcheck passes on each `run:` block (or warnings are explicitly understood)
- [ ] Local dry-run with `VPS_DIR` pointing at the real `pocketquant-config/vps/default/` (after Phase 1) successfully reads all 7 values without printing them to stdout
- [ ] Action does NOT log raw values — only `Loaded config for VPS '...'` summary

## Risk Assessment

| Risk | Mitigation |
|---|---|
| `eval` on `docker-hub.env` / `portainer.env` runs arbitrary shell | Files are in private repo + only operator commits. Threat = self-sabotage. Acceptable. |
| `::add-mask::` line-by-line for SSH key may miss very-short common substrings (BEGIN/END markers) | These are public PEM markers, not key material — leak is harmless. |
| GH may print masked value preamble for `with:` inputs in caller's step (`uses: ./.github/actions/get-vps-config with: deploy-key: ***`) | GH auto-masks secrets in `${{ secrets.X }}` references in `with:` blocks. Verify in smoke-test logs. |
| `actions/checkout@v4` writes credentials to disk → leak via subsequent steps | `persist-credentials: false` prevents that. |
| Missing required key in `docker-hub.env` / `portainer.env` | Bash `:?` syntax exits with clear `parameter null or not set` error. |
| YAML indentation bug in heredoc within composite action | Validated via yaml.safe_load + tested in dry-run. |
| Multiple jobs cloning concurrently hit GH rate limit | Per-repo rate limit is high (5000/hr); 4 clones × N runs/day << limit. |

## Next Steps

- Phase 3 wires this action into all 4 jobs of `cicd.yml`.
- Phase 4 smoke-tests on throwaway branch.
