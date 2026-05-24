---
phase: 7
title: "Write VPS migration runbook"
status: pending
priority: P1
effort: "30m"
dependencies: [6]
---

# Phase 7: Write VPS migration runbook

## Overview

Existing VPS at `/opt/pocketquant` has the OLD layout (`docker/`, root `deploy.sh`, etc.). After this refactor lands, the next deploy will fail without a one-time on-VPS file relocation. Runbook lives inside `docs/deployment-guide.md` and gives operators a copy-pasteable migration + rollback path.

## Requirements

- Functional: operator can copy-paste blocks in order and end up with new layout on the VPS, with running services and a successful `verify.sh` post-check.
- Non-functional: every command is idempotent OR includes a clear "already migrated → skip" gate. Rollback path published.

## Architecture

```
BEFORE (VPS)                           AFTER (VPS)
/opt/pocketquant/                      /opt/pocketquant/
├── deploy.sh                          └── deploy/
├── verify.sh                              ├── deploy.sh
└── docker/                                ├── verify.sh
    ├── compose.prod.yml                   ├── compose.prod.yml
    ├── .env                               ├── .env
    └── scripts/                           └── scripts/
        └── ...                                └── ...
```

Migration = `mkdir -p deploy && mv` flow, run ONCE, after which standard deploys resume via `bash deploy/deploy.sh`.

## Related Code Files

- Modify: `docs/deployment-guide.md` — insert new top-level section `## VPS Migration Runbook` immediately after the "Breaking change" note added in Phase 6.

## Implementation Steps

Insert the following section into `docs/deployment-guide.md` (after Phase 6's "Breaking change" note, before regular deploy instructions):

```markdown
## VPS Migration Runbook

**One-time migration required.** Run on `/opt/pocketquant` BEFORE the first deploy of the new layout. Idempotent — safe to re-run.

### Step 1: SSH to VPS, take snapshot

```bash
ssh -p 49722 deploy@VPS
cd /opt/pocketquant
# Snapshot (provider-side disk snapshot OR mongodump — pick one):
docker exec pocketquant-mongodb mongodump --archive=/tmp/pre-deploy-layout.archive --gzip
docker cp pocketquant-mongodb:/tmp/pre-deploy-layout.archive ./backups/
```

### Step 2: Relocate files

```bash
cd /opt/pocketquant
mkdir -p deploy/scripts/patches

# Move files if old layout still present (idempotent guards)
[ -f deploy.sh ] && mv deploy.sh deploy/deploy.sh
[ -f verify.sh ] && mv verify.sh deploy/verify.sh
[ -d docker ] && {
  mv docker/compose.prod.yml deploy/compose.prod.yml 2>/dev/null || true
  mv docker/compose.yml deploy/compose.yml 2>/dev/null || true
  mv docker/mongo-init.js deploy/mongo-init.js 2>/dev/null || true
  mv docker/.env deploy/.env 2>/dev/null || true
  mv docker/scripts/cleanup.sh deploy/scripts/cleanup.sh 2>/dev/null || true
  mv docker/scripts/server-setup.sh deploy/scripts/server-setup.sh 2>/dev/null || true
  # Remove empty docker/ folder
  rmdir docker/scripts 2>/dev/null || true
  rmdir docker 2>/dev/null || true
}
```

### Step 3: Sync new files from local

From your laptop (replace `$KEY` and `$VPS`):

```bash
scp -i $KEY deploy/deploy.sh deploy/verify.sh deploy/compose.prod.yml deploy/mongo-init.js \
    deploy/.env.example $VPS:/opt/pocketquant/deploy/
scp -i $KEY deploy/scripts/cleanup.sh deploy/scripts/server-setup.sh \
    $VPS:/opt/pocketquant/deploy/scripts/

# .env is git-ignored — ensure local deploy/.env has prod values, then:
scp -i $KEY deploy/.env $VPS:/opt/pocketquant/deploy/.env
```

### Step 4: Fix CRLF if scp'd from Windows

```bash
ssh -p 49722 deploy@VPS "
  sed -i 's/\r$//' /opt/pocketquant/deploy/deploy.sh
  sed -i 's/\r$//' /opt/pocketquant/deploy/verify.sh
  sed -i 's/\r$//' /opt/pocketquant/deploy/scripts/*.sh
"
```

### Step 5: Deploy

```bash
ssh -p 49722 deploy@VPS "cd /opt/pocketquant && bash deploy/deploy.sh"
```

### Step 6: Verify

```bash
ssh -p 49722 deploy@VPS "cd /opt/pocketquant && bash deploy/verify.sh"
# Inspect report:
ssh -p 49722 deploy@VPS "ls -lt /opt/pocketquant/deploy/reports/ | head"
```

All checks should be PASS. If any FAIL, jump to **Rollback**.

---

## Rollback Runbook

If new-layout deploy fails AND the old `docker/` files are still on the VPS (or in a snapshot):

```bash
ssh -p 49722 deploy@VPS
cd /opt/pocketquant

# Stop new-layout containers
docker compose -f deploy/compose.prod.yml --env-file deploy/.env down || true

# Restore old layout
mkdir -p docker/scripts
mv deploy/deploy.sh deploy.sh
mv deploy/verify.sh verify.sh
mv deploy/compose.prod.yml docker/compose.prod.yml
mv deploy/compose.yml docker/compose.yml 2>/dev/null || true
mv deploy/mongo-init.js docker/mongo-init.js
mv deploy/.env docker/.env
mv deploy/scripts/cleanup.sh docker/scripts/cleanup.sh
mv deploy/scripts/server-setup.sh docker/scripts/server-setup.sh
rmdir deploy/scripts/patches deploy/scripts deploy 2>/dev/null || true

# Pull OLD images (use last-known-good SHA, NOT :latest)
docker pull <DOCKERHUB_USERNAME>/pocketquant:sha-<LAST_GOOD_SHA>
docker pull <DOCKERHUB_USERNAME>/pocketquant-web:sha-<LAST_GOOD_SHA>
# Override IMAGE_TAG and re-deploy old layout:
IMAGE_TAG=sha-<LAST_GOOD_SHA> bash deploy.sh
```

If DB schema also broke (unlikely — this refactor is layout-only), restore from `./backups/pre-deploy-layout.archive`:

```bash
docker exec -i pocketquant-mongodb mongorestore --archive --gzip --drop < ./backups/pre-deploy-layout.archive
```
```

## Success Criteria

- [ ] `docs/deployment-guide.md` contains `## VPS Migration Runbook` and `## Rollback Runbook` sections
- [ ] Every shell command in the runbook is copy-pasteable (no `<placeholders>` left except the documented `$KEY`, `$VPS`, `<DOCKERHUB_USERNAME>`, `<LAST_GOOD_SHA>`)
- [ ] Idempotent guards (`[ -f X ] && ...`, `2>/dev/null || true`) on every move
- [ ] Rollback explicitly references "last-known-good SHA, NOT :latest" (because :latest will have been overwritten by CI)
- [ ] Runbook cross-linked from `docs/project-changelog.md` Phase 6 entry

## Risk Assessment

- **Risk:** Operator runs migration twice → file vanishes (second `mv` finds no source). **Mitigation:** every `mv` wrapped in `[ -f X ] &&` or `2>/dev/null || true`; re-run is a no-op.
- **Risk:** CRLF causes `bash: invalid option`. **Mitigation:** Step 4 is mandatory for Windows-sourced edits.
- **Risk:** :latest tag already overwritten by post-merge CI before operator can roll back. **Mitigation:** rollback explicitly uses `sha-<LAST_GOOD_SHA>` (CI retains last 7 SHA-tagged builds per ci.yml).
- **Risk:** Operator forgets DB snapshot. **Mitigation:** Step 1 is first; documented as required.
- **Risk:** `.env` not yet on VPS at new path → deploy.sh `[ ! -f .env ]` fails. **Mitigation:** Step 3 includes explicit `scp` of `.env`.
