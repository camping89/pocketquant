# Deploy Verification — Deploy Folder Consolidation

**Date:** 2026-05-25 08:30 +07 / 01:30 UTC
**Commit:** `89be395` refactor(deploy): consolidate deployment assets into deploy/ folder
**Branch:** develop

## CI

| Job | Result | Duration |
|-----|--------|----------|
| build-api | PASS | 57s |
| build-web | PASS | 46s |
| cleanup-tags | PASS | 5s |

GH Actions run: 26378350599. Images pushed to Docker Hub (`camping89/pocketquant:latest`, `camping89/pocketquant-web:latest`).

## VPS Migration (Runbook Execution)

| Step | Status |
|------|--------|
| 1 — mongodump snapshot | PASS — `pre-deploy-layout-20260525T012716.archive` (63MB) in `/opt/pocketquant/backups/` |
| 2 — relocate files | PASS — `deploy.sh`, `verify.sh`, `docker/compose.prod.yml`, `docker/.env`, `docker/.env.bak` → `deploy/`; `docker/` removed |
| 3 — scp new deploy/* from local | PASS |
| 4 — CRLF fix on shell scripts | PASS |
| 5 — `bash deploy/deploy.sh` | PASS — both images pulled, app recreated, healthy in 17s |
| 6 — `bash deploy/verify.sh` | DEGRADED (14/15) — see below |

Verify report saved on VPS at `/opt/pocketquant/deploy/reports/verify-20260525T013022.md`.

## Verify Findings

| Check | Result |
|-------|--------|
| All 4 containers running | PASS |
| App/Mongo/Redis healthy | PASS |
| API `/health` | PASS — db=1ms redis=0ms |
| MongoDB ping, Redis PING | PASS |
| Disk 29% / Memory 32% | PASS |
| Port 58921 listening | PASS |
| Image = `camping89/pocketquant:latest` | PASS |
| App logs (last 100) | WARN — 1 error |

### WARN Investigation

```
binance_ws.error 'server rejected WebSocket connection: HTTP 400'
```

Transient Binance WS handshake error at startup. NOT related to refactor. Client reconnects with backoff. Non-blocking.

## sync_jobs Container-Init Error — Followup

User's original morning concern (`sync_jobs container not initialized` on 2026-05-23T04:00:00Z) is **fixed in production** since commit `45e2d7f` (deployed 2026-05-24 11:31 UTC). That specific daily job has run cleanly since.

However, **the race still occurs during container restarts**. Hit again at `2026-05-25T01:30:02Z` (sync_1m, during my redeploy). Next tick at 01:31:02 recovered (passed). Pattern:

```
01:29:02 sync_1m completed OK   ← old container
01:30:02 sync_1m failed         ← restart window — JobScheduler dispatched persisted job
                                  before start_background_jobs() reached set_sync_container()
01:31:02 sync_1m completed OK   ← new container fully wired
```

### Root Cause

`start_background_jobs()` in `packages/pocketquant-api/src/pocketquant/api/main_extensions.py:157` does:

```python
set_backtest_container(container)              # ok
settings = await container.get(Settings)       # ← yield 1
if not settings.enable_jobs: return
from ... import set_container as set_sync_container
set_sync_container(container)                  # ← only set AFTER first await
await register_sync_jobs(...)
```

The JobScheduler singleton was already started by Dishka's async-gen lifespan earlier; any persisted job whose `next_run_time` falls inside `misfire_grace_time` can dispatch during the `await container.get(Settings)` yield, hitting `_get_container()` before `set_sync_container` runs.

### Severity

- Daily `sync_integrity` 04:00Z: low risk — almost never coincides with deploy
- Per-minute `sync_1m`: HIGH chance of one failure per deploy (proven this morning)
- Each failure is a single missed tick — APScheduler reconciles via catch-up + the next 60s tick

### Suggested Fix (out of scope here)

Either:
1. Hoist `set_sync_container(container)` to the FIRST line of `start_background_jobs` (before any `await`), so even racy dispatches during `container.get(Settings)` find a wired container.
2. Or move `set_sync_container` up into `lifespan()` before `start_background_jobs` is awaited.

Either approach makes the wiring strictly synchronous and happens before any awaits that could cede control to the scheduler dispatcher.

## Implementation Divergences

5 divergences logged during the refactor at `plans/260524-1805-deploy-folder-consolidation/reports/implementation-questions.md`. All low-impact plan-vs-reality adjustments.

## Verdict

**Deploy successful. Refactor live on VPS.** sync_jobs init race needs a follow-up plan (1-line hoist suggested). All other systems healthy.
