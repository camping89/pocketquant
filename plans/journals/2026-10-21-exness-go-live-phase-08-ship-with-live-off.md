---
title: "Exness go-live phase 08: ship with live off (deploy A)"
date: 2026-10-21
summary: "Deploy A is live (f0179f2, run 39611273334, 0 failures): admin token and Exness caps set, live trading off, data ports loopback, tunnel-test serving"
---

# Exness go-live phase 08: ship with live off (deploy A)

## What happened
- `pocketquant-config` got `ADMIN_TOKEN`, `EXNESS_DAILY_LOSS_CAP=25`, `EXNESS_MAX_LOTS=0.01`, `EXNESS_LEVERAGE=1000` and `EXNESS_RISK_PER_TRADE=0.10`; `EXNESS_LIVE_TRADING` stays absent. Both local remote-DB env files now point at `just tunnel` (localhost).
- `develop:master` was pushed at 2026-10-21T13:48:45Z (32 commits). The deploy verdict was `21/22 passed, 1 warnings, 0 failures`.
- Prod settings, `/admin/safeguards`, the 401 guard, the four paper subscriptions and `unexpected_count` all checked out. `tunnel-test` and the old path both return 200. Mongo, Redis and Portainer no longer answer on the VPS IP, and Mongo runs `7.0.45`. Mongo and Redis answer through `just tunnel`.
- The coordinator ran the read-only SPA check for the user and replied `spa ok`.

## What went wrong
- The config `.env` diff was not empty as the plan expected. It held the uncommitted `TUNNEL_TOKEN` line from Phase 07, and the Task 8.3 commit carried it. This was disclosed in the gate question.
- The deploy verdict's one warning was `cloudflared` "still starting". Two minutes later it was `(healthy)`.
- Stopping the `just tunnel` background task left its `ssh.exe` listening on 27017 and 6379. That process was stopped by PID.
- The engulfing EURUSD paper subscription lost one open paper position on restart. This was accepted in the plan.

## Next steps
- Phase 09: deploy B recreates `web` while the tunnel is the only public path. A `cloudflared` "still starting" WARN in the verdict can hide a real outage window, so treat the Task 9.10 curls as the real proof, not the verdict.
- Before reusing `just tunnel`, expect to stop its `ssh.exe` by hand.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
