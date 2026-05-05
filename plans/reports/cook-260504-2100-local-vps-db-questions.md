# Cook session: local → VPS DB — open questions

**Date:** 2026-05-04 21:00 +0700
**Status:** Local stack verified end-to-end; awaiting decisions before VPS deploy.

---

## What's done

| Phase | Result |
|---|---|
| P1 — `.env` trỏ VPS Mongo + Redis | `just check` pass: Mongo v7.0.31 @ `207.148.79.60:52017`, Redis v7.2.13 @ `207.148.79.60:53679` |
| P2 — Distributed scheduling | `MemoryJobStore` → `MongoDBJobStore`. `sync_jobs.py` refactored: 8 jobs picklable (module-level coroutines, container resolved at exec time). Verified persistence by registering + cleanup against VPS Mongo. |
| P4 — Cleanup deadvars | Removed `JOB_WORKER_COUNT` everywhere (dead code, no Settings field). Removed `MONGOEXPRESS_PORT` + entire `mongo-express` service from `docker/compose.yml`. Removed `WEB_PORT` from envs (defaults to 80 in `compose.prod.yml`). Set `LOG_FORMAT=console` on both local + VPS env. |
| P3 — E2E verify | BE up @ 41920 → `/health` healthy, `/api/v1/system/jobs` shows 8 jobs in VPS Mongo, `/api/v1/market-data/ohlcv/BINANCE/BTCUSDT?interval=1d` returned 5 bars (3183 total bar_count). FE up @ 5173, `/api/*` proxy → BE → VPS DB roundtrip OK. |

Files touched:

- `D:\w\_me\pocketquant\.env` (rewrote, points VPS)
- `D:\w\_me\pocketquant\.env.example` (drop MONGOEXPRESS_PORT)
- `D:\w\_me\pocketquant\.env.test` (drop JOB_WORKER_COUNT)
- `D:\w\_me\pocketquant\docker\compose.yml` (remove mongo-express service)
- `D:\w\_me\pocketquant\packages\pocketquant-core\src\pocketquant\core\infrastructure\scheduling\scheduler.py` (MongoDBJobStore, drop history wrapping)
- `D:\w\_me\pocketquant\packages\pocketquant-api\src\pocketquant\api\market_data\app_services\sync_jobs.py` (refactor to picklable module-level fns)
- `D:\w\_me\pocketquant\packages\pocketquant-api\src\pocketquant\api\main_extensions.py` (new register_sync_jobs signature)
- `D:\w\_me\pocketquant-config\.env.prod` (drop JOB_WORKER_COUNT/WEB_PORT, LOG_FORMAT=console)
- `D:\w\_me\pocketquant-config\.env` (drop deadvars)
- `D:\w\_me\pocketquant-config\.env.test` (drop deadvars)

Backup of original local env: `D:\w\_me\pocketquant\.env.local-only.bak`

---

## Open questions — please answer inline (just edit this file)

### Q1. VPS deploy timing for distributed scheduling
**Why it matters:** P2 created collection `apscheduler_jobs` in VPS Mongo. Local now reads/writes it. **VPS still runs OLD code with `MemoryJobStore`** — it ignores the collection and runs jobs from its own in-process memory. So right now you have **DOUBLE FIRE again** (local + VPS) until you deploy the new code to VPS.

**Options:**
- (a) Deploy ASAP — both sides converge on `MongoDBJobStore`, single instance fires.
- (b) Stop local jobs (`ENABLE_JOBS=false` in local `.env`) until VPS is deployed.
- (c) Stop VPS jobs first, then enable local-only as primary, then deploy VPS.

**Your answer:** jus deploy, no worries
> 

---

### Q2. Test env DB endpoints
`packages/pocketquant-core/tests/conftest.py:13` reads `.env.test` which points at `mongodb://localhost:47017` / `redis://localhost:46379/1`. These ports are NOT in `docker/compose.yml` (which uses 52017/53679). Tests likely don't run against any real instance, or they spin up testcontainers somewhere I didn't see.

**Question:** Should I leave `.env.test` alone? Or do you want it pointing somewhere reachable (e.g. ephemeral testcontainers / a separate test DB on VPS)?

**Your answer:** remove 100% env test, we dont need this, both in this repo and pocketquant-config repo. New test = local, prod = vps
> 

---

### Q3. Local docker stack — keep or kill?
`docker compose ps` shows `pocketquant-redis` still running locally (started by previous `just up`). Now unused since `.env` points at VPS Redis. Two options:

- (a) Run `just down` — frees ~50MB RAM, simpler mental model.
- (b) Keep it — low overhead, can switch back to local-only via `cp .env.local-only.bak .env` instantly without restarting docker.

**Your answer:** A - just down, but we need redis for future developmennt on local. So just down everything is enough, I can run FE + BE in debugging mode later
> 

---

### Q4. Commit pocketquant-config changes?
That's a separate git repo. Cleanup edits in:
- `.env.prod` (LOG_FORMAT=console, drop dead vars)
- `.env` (drop dead vars)
- `.env.test` (drop dead var)

**Question:** Want me to commit + push there too? Suggested message: `chore: drop dead vars (JOB_WORKER_COUNT, WEB_PORT, MONGOEXPRESS_PORT), use LOG_FORMAT=console`.

**Your answer:** ok let me commit manually
> 

---

### Q5. Build FE for FastAPI serving?
Currently FE runs via `npm run dev` on `:5173` → proxy to `:41920`. FastAPI also serves `pocketquant-web/dist/` if it exists (`main_extensions.py:161`). `dist/` may be stale from previous build.

**Question:** Want me to `npm run build` so FastAPI can serve a fresh SPA at `http://localhost:41920/`?

**Your answer:** yea do that, but FE  is just run, wyh do we need to build?
> 

---

### Q6. Safety rails for prod-DB writes from local
Now that local has direct write access to prod DB, common foot-guns:
- `mediator.send(SyncSymbolCommand(...))` from a manual script will write to prod
- Any pytest accidentally pointing at prod env

**Question:** Want me to add a startup guard that prints a big red banner when `MONGODB_URL` contains the prod IP, AND/OR refuse to start if `ENVIRONMENT=production` but launched from non-prod hostname?

**Your answer:** pytest need to run test (e2e or integration in a test db, so write everything needed to do this, do not touch PROD db for test and unit test)
> 

---

## Notes for resuming work

- BE was stopped after verification. To restart: `just be`.
- FE was stopped. To restart: `just fe`.
- All 8 jobs persist in VPS Mongo `apscheduler_jobs` collection. Next firings:
  - sync_5m: every 5 min
  - sync_15m: every 15 min
  - sync_hourly: every 1h
  - sync_swing: every 4h
  - sync_daily: cron 00:30
  - sync_backfill: cron 03:00
  - sync_integrity: cron 04:00
  - sync_repair: every 12h

  These WILL fire from local once a job tick comes around (and from VPS too — see Q1).

- To revert local to fully-isolated dev mode: `cp .env.local-only.bak .env && just up`.

---

## Unresolved technical risks

- **Race on first deploy:** When VPS is restarted with new code, both local + VPS will register jobs with `replace_existing=True` — last writer wins. Since intervals are deterministic from code, end state is identical; only `next_run_time` may shift by a few seconds. Not a real risk.
- **Pickling of arguments:** Job functions take no arguments — closures over Interval enum + n_bars are baked into module-level wrappers. No future contributor should add APScheduler `kwargs=` with non-picklable values.
