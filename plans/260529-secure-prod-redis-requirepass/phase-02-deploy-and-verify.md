---
phase: 2
title: "Deploy and verify"
status: in-progress
priority: P1
effort: "30m"
dependencies: [1]
---

# Phase 2: Deploy and verify

## Overview

Commit both repos, deploy to the VPS so Redis comes up with auth, then verify from
inside (app healthy) and from an untrusted network (unauth rejected). Finally
rotate: `FLUSHALL` once under new auth to drop any keys planted during the prior
unauth window.

## Requirements

- Functional: prod stack healthy post-deploy; Redis rejects unauth, accepts auth.
- Non-functional: zero app downtime beyond the redis container recreate window.

## Architecture

Deploy path (from `deploy/vps/10-deploy.sh`, invoked by CI/CD or manually):
```
push pocketquant-config  ──► CI materializes /opt/pocketquant/deploy/.env (new REDIS_*)
push pocketquant         ──► CI ► ssh VPS ► 10-deploy.sh
                                  └─ docker compose -f compose.prod.yml --env-file .env up -d
                                       └─ redis recreated WITH --requirepass
                                       └─ app waits on redis healthcheck (now auth-aware) ► healthy
```

## Related Code Files

- Read: `pocketquant/deploy/vps/10-deploy.sh` (deploy mechanics — no edit)
- Run: `pocketquant/deploy/vps/11-verify.sh` (post-deploy)

## Implementation Steps

1. **Commit + push config repo first** (so CI has the new `.env` to materialize):
   ```bash
   cd pocketquant-config && git add vps/default/.env && \
     git commit -m "chore: add Redis requirepass for prod" && git push
   ```
   > `.env` is intentionally committed in this repo (same as existing
   > `MONGO_PASSWORD`) — that is the established pattern, not a new leak.

2. **Commit + push app repo** (compose + verify + doc):
   ```bash
   cd pocketquant && git add deploy/compose.prod.yml deploy/vps/11-verify.sh docs/security-redis-exposure.md && \
     git commit -m "fix(security): require password on prod Redis" && git push
   ```
   This triggers CI/CD (`.github/workflows/cicd.yml`).

3. **Wait for deploy** (CI) or run manually:
   ```bash
   ssh vps "cd /opt/pocketquant && bash deploy/vps/10-deploy.sh"
   ```
   `10-deploy.sh` waits up to 60s for app `/health`; if redis healthcheck is
   wrong the app stage fails loudly here — that is the early-warning signal.

4. **Run verification:**
   ```bash
   ssh vps "cd /opt/pocketquant && bash deploy/vps/11-verify.sh"
   ```
   Expect `Redis ping: PASS (PONG)` and `API /health: PASS (... redis=Nms)`.

5. **Rotate / clean the unauth window** — drop any attacker-planted keys:
   ```bash
   ssh vps 'cd /opt/pocketquant && set -a && source deploy/.env && set +a && \
     docker exec pocketquant-redis redis-cli -a "$REDIS_PASSWORD" --no-auth-warning FLUSHALL'
   ```
   > Cache-only data (TTL'd market data / computed state) — safe to flush; app
   > repopulates. No persistent business state lives only in Redis.

6. **Confirm external unauth is rejected** (from your laptop, untrusted network):
   ```bash
   redis-cli -h 207.148.79.60 -p 53679 ping            # expect: NOAUTH / error
   redis-cli -h 207.148.79.60 -p 53679 -a "$REDIS_PASSWORD" --no-auth-warning ping  # expect: PONG
   ```

## Success Criteria

- [ ] Both repos pushed; CI/CD deploy green (or manual `10-deploy.sh` reports "App is healthy")
- [ ] `11-verify.sh` verdict HEALTHY; Redis ping PASS; API /health PASS with redis latency
- [ ] External `redis-cli ... ping` (no `-a`) returns NOAUTH error
- [ ] External `redis-cli ... -a $PASS ping` returns PONG
- [ ] `FLUSHALL` executed once under auth
- [ ] App logs show no redis connection errors post-deploy

## Risk Assessment

- **App can't reach Redis after deploy** (URL/password mismatch between repos) →
  `10-deploy.sh` health gate fails → fix `REDIS_URL` in config `.env`, redeploy.
  Mitigation: copy the *same* generated string into both `REDIS_PASSWORD` and the
  URL in Phase 1.
- **Redis recreate drops cache mid-trade** → acceptable; cache is non-authoritative
  and `--appendonly` AOF restores prior keys anyway (then FLUSHALL clears them by
  design). No order/position state lives in Redis (those are Mongo-backed).
- **Rollback:** revert both commits + redeploy → returns to prior (unauth) state.
  Only do this if auth blocks the app and can't be fixed forward.
