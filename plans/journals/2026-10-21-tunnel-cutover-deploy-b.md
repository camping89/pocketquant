---
title: "Tunnel cutover: deploy B"
date: 2026-10-21
summary: pocketquant.xyz and www now reach prod only through Cloudflare Tunnel; web host port removed; admin token rotated
---

# Tunnel cutover: deploy B

## What happened
- The user moved `www` and `@` from proxied DNS records to tunnel routes on `pocketquant-prod` and removed `tunnel-test`. Both names returned 200 through the tunnel before the port was dropped.
- Cloudflare 2FA is on. The coordinator created the `api-flood` rate rule through the Rulesets API (wildcard expression accepted on the Free plan) with a zone-scoped token in the gitignored `.cache/cf_api_token`. That replaces the earlier no-token decision at the user's request.
- Commit b30ea30 removed the `web` host port (`deploy/compose.prod.yml`). It also changed `deploy/vps/11-verify.sh` to probe the SPA from inside `pocketquant-app`, pass the Redis password via `REDISCLI_AUTH`, and drop the port-listening section. `docs/deployment.md` gained the new traffic path, an SSH pause runbook and a "Restart while live" runbook.
- pocketquant-config dropped `WEB_PORT` and rotated `ADMIN_TOKEN`. Deploy B (master run 39639409829) passed with a 0-failure verdict.
- Post-deploy: the web, Mongo, Redis and Portainer ports refuse or drop connections by IP, SSE delivered 137 data lines, SSH break-glass pause and resume worked, Pause answered 200 after a 300-request burst, and the user's SPA pause with the new token worked.

## Surprises
- The plan's compose Verify (`docker compose config --quiet`) fails locally because `deploy/.env` does not exist on the workstation, even on the unchanged file. kongming approved `--no-env-resolution` as the equivalent check.
- The flood burst produced no 429s: 299×200 and 1×000, over about 4 minutes. Neither limiter was exercised, and the Verify only required that Pause answers.

## Next steps
- Phase 10 (arm live, all paper). After this point, deploy only through the "Restart while live" runbook in `docs/deployment.md`.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
