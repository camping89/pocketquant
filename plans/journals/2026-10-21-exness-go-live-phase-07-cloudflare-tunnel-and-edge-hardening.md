---
title: "Exness go-live phase 07: Cloudflare Tunnel service and edge hardening"
date: 2026-10-21
summary: "Phase 07 shipped (c13fab5): cloudflared on its own network, loopback data ports, per-client rate limiting and an SSE cap; one Verify line corrected"
---

# Exness go-live phase 07: Cloudflare Tunnel service and edge hardening

## What happened
- Phase 07 of `plans/261019-1957-exness-go-live` shipped to `develop` as `c13fab5`. Nothing is deployed yet; Phase 08 deploys and checks it.
- `cloudflared` runs digest-pinned (`2026.10.0`) on an `edge` network with only its token. `web` sits on `edge` and `backend`; `app`, Mongo and Redis sit on `backend` only.
- Mongo, Redis and Portainer bind 127.0.0.1, and Mongo is pinned to `7.0.45`. `just tunnel` forwards them over ssh to local 27017, 6379 and `$PORTAINER_PORT`.
- The rate limiter now sees the real client: nginx realip reads `CF-Connecting-IP` from Docker peers and uvicorn trusts `X-Forwarded-For` from Docker ranges. `/api/v1/admin/safeguards*` is never limited, and nginx caps open SSE streams at 10 per client IP.
- `just be` binds 127.0.0.1, and `11-verify.sh` checks the new container.

## What went wrong
- The Task 7.4 Verify command (`docker compose ... config --quiet`) exits 1 on any workstation because `app.env_file: .env` exists only on the VPS. The HEAD file fails the same way. After counsel, the Verify line now uses `--no-env-resolution`.
- A Python heredoc run through `uv run python -` halved the backslashes in the `tunnel` recipe, which left real CR bytes in the justfile and dropped the line continuations. `just --dry-run` showed it, and the recipe was rewritten from a script file.

## Next steps
- Phase 08: after one request through `tunnel-test`, `docker logs pocketquant-web` must show the public client IP, not `172.x`.
- Until the Phase 09 cutover, the old A-record path reaches nginx from Cloudflare edge IPs, so buckets there are per edge IP.
- Task 8.7: confirm `just tunnel` runs Git's bash, not WSL's.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
