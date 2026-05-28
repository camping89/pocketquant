---
phase: 2
title: "Remove operator-side wrapper artifacts"
status: completed
priority: P2
effort: "30m"
dependencies: [1]
---

# Phase 2: Remove operator-side wrapper artifacts

## Overview

After CI/CD owns deploy, the laptop-side wrapper is dead code. Remove `deploy/deploy.sh`, `deploy/deploy.conf.example`, and the `.gitignore` line for `deploy/deploy.conf`. Operator's local `deploy/deploy.conf` (if it exists) becomes orphan — operator can delete manually.

## Requirements

- Functional:
  - `deploy/` folder no longer contains operator wrapper files
  - `.gitignore` no longer references `deploy/deploy.conf`
  - VPS-side scripts in `deploy/vps/*.sh` unchanged
  - `deploy/compose.prod.yml`, `compose.yml`, `Dockerfile` unchanged
- Non-functional:
  - No orphan references in any other tracked file (handled in Phase 3)

## Architecture

```
Before (deploy/):                After (deploy/):
├── Dockerfile                   ├── Dockerfile
├── compose.prod.yml             ├── compose.prod.yml
├── compose.yml                  ├── compose.yml
├── deploy.sh                    └── vps/
├── deploy.conf.example              ├── deploy.sh
└── vps/                              ├── verify.sh
    ├── deploy.sh                     ├── cleanup.sh
    ├── verify.sh                     ├── server-setup.sh
    ├── cleanup.sh                    └── patches/
    ├── server-setup.sh
    └── patches/
```

## Related Code Files

- Delete: `deploy/deploy.sh`
- Delete: `deploy/deploy.conf.example`
- Modify: `.gitignore` — remove `deploy/deploy.conf` line

## Implementation Steps

1. Confirm Phase 1 merged + at least one successful CI/CD run on develop. Do NOT run this phase before Phase 1 is live — wrapper is the only deploy path until then.
2. `git rm deploy/deploy.sh deploy/deploy.conf.example`
3. Edit `.gitignore`:
   - Find the block `# Operator-side deploy config (VPS_HOST, SSH key path). Local only.` + `deploy/deploy.conf`
   - Delete both lines
4. Verify no remaining references in tracked source files (defer doc/README sweeps to Phase 3):
   ```bash
   grep -rn "deploy/deploy.sh\|deploy/deploy.conf" \
     --include="*.sh" --include="*.py" --include="*.yml" --include="*.toml" \
     --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=htmlcov
   ```
   Expected: zero matches.
5. Run `bash -n` syntax check on all remaining shell scripts in `deploy/` to confirm nothing in `deploy/vps/*` had a stale `source ../deploy.conf` or similar.

## Success Criteria

- [ ] `ls deploy/` shows: `Dockerfile  compose.prod.yml  compose.yml  vps/` only
- [ ] `git status` shows the two deletions + .gitignore modification
- [ ] No grep matches for `deploy/deploy.sh` or `deploy/deploy.conf` in any `.sh`/`.py`/`.yml`/`.toml`
- [ ] `bash -n deploy/vps/*.sh` exits 0 for every file

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Phase 2 merged before Phase 1 live → no deploy path | Strict phase ordering. Explicit gate in Step 1: confirm a green CI/CD run on develop first. |
| Operator's local `deploy/deploy.conf` lingers | Not tracked, no harm. Document in commit message that operators can delete locally. |
| Stale ref in script not caught by grep | `bash -n` parse check on all remaining shell scripts catches sourcing errors |

