---
phase: 1
title: "Apply Redis auth"
status: complete
priority: P1
effort: "30m"
dependencies: []
---

# Phase 1: Apply Redis auth

## Overview

Add `--requirepass` to the prod Redis container, set a strong random password in
the config repo, and update every consumer that talks to Redis (the URL, the
container healthcheck, the verify script). All edits are config/compose only — no
application code changes (the app reads `REDIS_URL` from `Settings` unchanged).

## Requirements

- Functional: prod Redis rejects unauthenticated connections; app + healthcheck +
  verify script authenticate successfully.
- Non-functional: password ≥ 32 bytes of entropy (only barrier vs public
  internet; Redis does no AUTH rate-limiting).

## Architecture

```
compose up --env-file .env
  └─ ${REDIS_PASSWORD} interpolated into:
       redis.command     → redis-server ... --requirepass <pw>
       redis.healthcheck → redis-cli -a <pw> --no-auth-warning ping
app container reads REDIS_URL=redis://:<pw>@redis:6379/0  (internal docker DNS)
```

`${REDIS_PASSWORD}` is interpolated by Compose at `up` time from `--env-file .env`
(see `10-deploy.sh`: `docker compose -f compose.prod.yml --env-file .env up -d`).
The redis service does **not** need an `env_file:` block for this — variable
substitution in `command`/`healthcheck` happens at the Compose layer, not inside
the container.

## Related Code Files

- Modify: `pocketquant/deploy/compose.prod.yml` — redis `command` + `healthcheck`
- Modify: `pocketquant-config/vps/default/.env` — add `REDIS_PASSWORD`, edit `REDIS_URL` (separate repo)
- Modify: `pocketquant/deploy/vps/11-verify.sh` — redis-cli PING → add `-a`
- Modify: `pocketquant/docs/security-redis-exposure.md` — status → Resolved + residual-risk note
- Out of scope (do NOT touch): `compose.local.yml`, `pocketquant-config/local/.env`, `pocketquant/.env`

## Implementation Steps

1. **Generate password:**
   ```bash
   openssl rand -base64 32
   ```
   Use the exact output (≈44 chars). It contains `/`, `+`, `=` — safe inside the
   `.env` value and inside the URL userinfo since there is no shell/URL parsing
   that splits on them here (Compose reads the raw `.env` line; the app passes the
   URL string to redis-py which accepts these). Avoid wrapping in quotes in `.env`.

2. **`pocketquant-config/vps/default/.env`** — add under the Redis section:
   ```
   REDIS_PASSWORD=<generated>
   REDIS_URL=redis://:<generated>@redis:6379/0
   ```
   Keep `REDIS_PORT=53679` unchanged. Note the leading `:` (empty username — the
   `default` user). Host stays `redis` (internal docker network).

3. **`pocketquant/deploy/compose.prod.yml`** — redis service. Change `command` and
   add a `healthcheck` that authenticates:
   ```yaml
   redis:
     image: redis:7.2-alpine
     container_name: pocketquant-redis
     restart: unless-stopped
     ports:
       - "${REDIS_PORT}:6379"
     command: redis-server --appendonly yes --maxmemory 100mb --maxmemory-policy allkeys-lru --requirepass ${REDIS_PASSWORD}
     volumes:
       - redis_data:/data
     healthcheck:
       test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "--no-auth-warning", "ping"]
       interval: 10s
       timeout: 5s
       retries: 5
   ```
   (`--no-auth-warning` suppresses the stderr warning so the healthcheck exit code
   stays clean.)

4. **`pocketquant/deploy/vps/11-verify.sh`** — the Redis direct check (section 5).
   `$REDIS_PASSWORD` is already in scope (script does `source .env`). Change:
   ```bash
   redis_ok=$(docker exec pocketquant-redis redis-cli -a "$REDIS_PASSWORD" --no-auth-warning PING 2>/dev/null || echo "")
   ```

5. **`pocketquant/docs/security-redis-exposure.md`** — update header + close:
   - `**Status:** Open — action required` → `**Status:** Resolved 2026-05-29 (requirepass; public port retained by decision)`
   - Append a short "Resolution" note: requirepass applied; loopback/tunnel
     rejected (no static IP); residual risk = online brute force / future Redis
     auth-bypass CVE, mitigated by 32-byte random password; revisit removing
     `ports:` if the external-tool need ends.

6. **Validate compose syntax locally** (does not start anything; needs the var
   present so substitution resolves):
   ```bash
   cd pocketquant/deploy && REDIS_PASSWORD=dummy REDIS_PORT=53679 \
     DOCKERHUB_USERNAME=x APP_PORT=1 MONGO_PORT=1 MONGO_PASSWORD=x PORTAINER_PORT=1 \
     docker compose -f compose.prod.yml config >/dev/null && echo OK
   ```

## Success Criteria

- [ ] `REDIS_PASSWORD` (32-byte base64) present in `pocketquant-config/vps/default/.env`
- [ ] `REDIS_URL` in that file = `redis://:<pw>@redis:6379/0`
- [ ] `compose.prod.yml` redis `command` ends with `--requirepass ${REDIS_PASSWORD}`
- [ ] `compose.prod.yml` redis `healthcheck` uses `-a ${REDIS_PASSWORD} --no-auth-warning`
- [ ] `11-verify.sh` redis check passes `-a "$REDIS_PASSWORD"`
- [ ] `security-redis-exposure.md` status = Resolved + residual-risk note
- [ ] `docker compose -f compose.prod.yml config` validates with no error
- [ ] No edits to `compose.local.yml` / local `.env` files (prod-only scope held)

## Risk Assessment

- **Forgot healthcheck/verify update** → app won't start / verify false-FAIL.
  Mitigation: both are explicit checklist items + plan.md Gotchas.
- **Password special chars break parsing** → low; `.env` is read literally by
  Compose, redis-py accepts base64 chars in userinfo. If paranoid, regenerate
  until output has no `/` or `+` (cosmetic only).
- **Two-repo edit drift** (config repo separate) → ensure both repos committed
  before deploy; CI materializes `.env` from config repo.
