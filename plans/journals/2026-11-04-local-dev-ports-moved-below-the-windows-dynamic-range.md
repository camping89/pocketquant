---
title: Local dev ports moved below the Windows dynamic range
date: 2026-11-04
summary: "Local Mongo 47017 and Redis 46379 in all pocketquant-config local profiles; just be is broken on Windows, so the backend was verified with direct uvicorn"
---

# Local dev ports moved below the Windows dynamic range

## What happened
Windows reserves moving blocks inside its dynamic port range (49152-65535) through Hyper-V/WinNAT. Local Redis on 53679 was reserved on 2026-11-01, which broke `just up`. Every local profile in `../pocketquant-config/local/` now uses MONGO_PORT=47017 and REDIS_PORT=46379, and the URLs that point at local Docker use the same ports. Config commit `7191764` is pushed to pocketquant-config master.

## Verification
After `just up`, `docker ps` showed 46379->6379 and 47017->27017. `just be` failed before the app ran: the justfile runs recipes in PowerShell (`windows-shell`), and PowerShell rejects the `TZ=UTC cmd` prefix. Per the Failure Protocol, kongming advised running the recipe's command directly from Git Bash with TZ=UTC. The backend then logged mongodb.connected, redis.connected and "Application startup complete." with no connection errors.

## Decision
The justfile was not changed, because Phase 01 is scoped to pocketquant-config. `just be` and the TZ lines of the test recipe stay broken on Windows. This is recorded as a carried finding in `plans/261103-1741-1d-cascade-fold-and-small-fixes/reports/phase-01-local-dev-ports.md`.

## Next steps
Phase 02 should run FULLSUITE once before any code change, because `.env` now exists in the repo and `Settings` reads it. Commit the Phase 01 plan-file edits with the Phase 02 CLOSE commit.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
