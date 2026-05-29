---
title: "Secure prod Redis with requirepass auth"
description: "Add a password to the publicly-exposed production Redis (requirepass), update dependent healthcheck/verify/URL, deploy, and rotate."
status: in-progress
priority: P1
branch: "develop"
tags: [security, infra, redis, deployment]
blockedBy: []
blocks: []
created: "2026-05-29T10:37:23.289Z"
createdBy: "ck:plan"
source: skill
---

# Secure prod Redis with requirepass auth

## Overview

Production Redis is published on a public IP (`207.148.79.60:53679`) with **no
password**. Anyone reaching that port can read all cached data, `FLUSHALL`, or
abuse `CONFIG SET dir`/`SAVE` for RCE-style attacks. This plan adds a strong
`requirepass` password as the **sole** access control (public port retained by
user decision — no static IP for allowlisting, no SSH tunnel), then deploys and
rotates.

**Decided constraints (from brainstorm):**
- Scope: **Redis only**. Mongo/Portainer/app exposure, Mongo-password rotation,
  and committed `id_rsa` are explicitly OUT of scope.
- Mechanism: **`requirepass`** (password-only `default` user), NOT ACL.
- Storage: password **plaintext** in `pocketquant-config/vps/default/.env`,
  mirroring the existing `MONGO_PASSWORD` pattern.
- Environment: **prod only**. `compose.local.yml` stays no-auth on localhost.
- Network: public `0.0.0.0` publish **retained**. Strong random password is the
  only mitigation — documented residual risk (online brute force / future Redis
  auth-bypass CVE).

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Apply Redis auth](./phase-01-apply-redis-auth.md) | Complete |
| 2 | [Deploy and verify](./phase-02-deploy-and-verify.md) | Pending |

## Key Files (two repos)

- `pocketquant/deploy/compose.prod.yml` — redis `command` + `healthcheck`
- `pocketquant/deploy/vps/11-verify.sh` — redis-cli PING check
- `pocketquant/docs/security-redis-exposure.md` — status → Resolved
- `pocketquant-config/vps/default/.env` — `REDIS_PASSWORD`, `REDIS_URL` (separate git repo)

## Critical Gotchas (must not miss)

1. **Healthcheck breaks under auth.** Once `--requirepass` is set, the existing
   `redis-cli ping` healthcheck returns `NOAUTH` → container marked unhealthy →
   `app` (`depends_on: redis: service_healthy`) never starts. Healthcheck MUST be
   updated in the same commit.
2. **Verify script breaks under auth.** `11-verify.sh` runs `redis-cli PING`
   inside the container — same `NOAUTH` failure. Must pass `-a "$REDIS_PASSWORD"`.

## Dependencies

No cross-plan dependencies. Independent of `260529-bug-backlog-*` (no file overlap).
