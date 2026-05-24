---
phase: 3
title: "Update shell scripts"
status: pending
priority: P1
effort: "20m"
dependencies: [2]
---

# Phase 3: Update shell scripts

## Overview

Fix path references inside `deploy/deploy.sh` and `deploy/verify.sh` now that they live in `deploy/` and compose+env files are siblings instead of children.

## Requirements

- Functional: scripts run end-to-end against new layout on a VPS with `cd /opt/pocketquant && bash deploy/deploy.sh`.
- Non-functional: `cd "$(dirname "$0")"` idiom still anchors CWD to the script's dir (now `deploy/`), so sibling paths use no prefix.

## Architecture

After Phase 2, layout on VPS will be:
```
/opt/pocketquant/
└── deploy/
    ├── deploy.sh    (CWD after `cd "$(dirname "$0")"` = /opt/pocketquant/deploy/)
    ├── verify.sh    (same)
    ├── compose.prod.yml
    ├── .env
    └── ...
```

So `docker/compose.prod.yml` → `compose.prod.yml` (sibling) and `docker/.env` → `.env` (sibling).

## Related Code Files

- Modify: `deploy/deploy.sh`
- Modify: `deploy/verify.sh`
- Modify: `deploy/scripts/server-setup.sh` (line ~101: `mkdir -p /opt/pocketquant/docker`)

## Implementation Steps

### `deploy/deploy.sh`

1. Replace `if [ ! -f docker/.env ]; then` → `if [ ! -f .env ]; then`
2. Replace error message `Copy .env.example, fill prod values, place at docker/.env` → `Copy .env.example, fill prod values, place at deploy/.env`
3. Replace `set -a && source docker/.env && set +a` → `set -a && source .env && set +a`
4. Replace `docker compose -f docker/compose.prod.yml --env-file docker/.env up -d --remove-orphans` → `docker compose -f compose.prod.yml --env-file .env up -d --remove-orphans`
5. Sanity-check: ensure Phase 1 already removed the `one_time_purge_legacy_strategies` block; if not, remove now.

### `deploy/verify.sh`

1. Replace `source docker/.env 2>/dev/null || true` → `source .env 2>/dev/null || true`
2. Report path `REPORT_DIR="./reports"` — keep as-is (relative to CWD = `deploy/`, so reports land in `deploy/reports/`). Document this in changelog.
   - **Alternative considered:** `REPORT_DIR="../reports"` to land at project root. Rejected — keep reports next to script for VPS portability.

### `deploy/scripts/server-setup.sh`

1. Line ~101: `mkdir -p /opt/pocketquant/docker` → `mkdir -p /opt/pocketquant/deploy/scripts/patches`
2. Line ~110 (echo): `Copy docker/ folder to /opt/pocketquant/docker/` → `Copy deploy/ folder to /opt/pocketquant/deploy/`
3. Line ~111: `Create /opt/pocketquant/docker/.env.prod` → `Create /opt/pocketquant/deploy/.env`

## Success Criteria

- [ ] `grep -n "docker/" deploy/deploy.sh deploy/verify.sh deploy/scripts/server-setup.sh` returns zero matches
- [ ] `grep -n "one_time_purge_legacy_strategies" deploy/deploy.sh` returns zero matches
- [ ] Shellcheck (if available) reports no new warnings: `shellcheck deploy/deploy.sh deploy/verify.sh deploy/scripts/*.sh`
- [ ] Manual dry-trace: read each script top-to-bottom, confirm no broken path

## Risk Assessment

- **Risk:** Missed a path ref. **Mitigation:** Phase 1 audit + grep success criterion above.
- **Risk:** CRLF line endings introduced by Windows edits cause `bash: invalid option` on VPS. **Mitigation:** verify with `file deploy/*.sh` (should report `ASCII text` not `CRLF line terminators`); convert via `dos2unix` or `sed -i 's/\r$//'` if needed. Already documented in deployment-guide.
- **Risk:** Compose file lookup fails because `--env-file` path is now relative. **Mitigation:** `cd "$(dirname "$0")"` at script top ensures CWD = `deploy/`; sibling `.env` resolves correctly. Validated in Phase 8.
