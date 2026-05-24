# Production Deployment Guide

**Last Updated:** 2026-05-24 | **CI:** GitHub Actions → Docker Hub | **CD:** Manual via deploy/deploy.sh

> **Breaking change (2026-05-24):** Deployment layout reorganized — all deploy assets now live under `deploy/`. See [VPS Migration Runbook](#vps-migration-runbook) before deploying to existing VPS.

## VPS Migration Runbook

**One-time migration required.** Run on `/opt/pocketquant` BEFORE the first deploy of the new layout. Idempotent — safe to re-run.

### Step 1: SSH to VPS, take snapshot

```bash
ssh -i $KEY $VPS
cd /opt/pocketquant
# Snapshot (provider-side disk snapshot OR mongodump — pick one):
docker exec pocketquant-mongodb mongodump --archive=/tmp/pre-deploy-layout.archive --gzip
mkdir -p ./backups
docker cp pocketquant-mongodb:/tmp/pre-deploy-layout.archive ./backups/
```

### Step 2: Relocate files (idempotent)

```bash
cd /opt/pocketquant
mkdir -p deploy/scripts/patches

# Move files if old layout still present (idempotent guards)
[ -f deploy.sh ] && mv deploy.sh deploy/deploy.sh
[ -f verify.sh ] && mv verify.sh deploy/verify.sh
[ -d docker ] && {
  mv docker/compose.prod.yml deploy/compose.prod.yml 2>/dev/null || true
  mv docker/compose.yml      deploy/compose.yml      2>/dev/null || true
  mv docker/.env             deploy/.env             2>/dev/null || true
  mv docker/scripts/cleanup.sh      deploy/scripts/cleanup.sh      2>/dev/null || true
  mv docker/scripts/server-setup.sh deploy/scripts/server-setup.sh 2>/dev/null || true
  # Remove now-empty docker/ folder
  rmdir docker/scripts 2>/dev/null || true
  rmdir docker         2>/dev/null || true
}
```

### Step 3: Sync new files from local

From your laptop (replace `$KEY` and `$VPS`):

```bash
scp -i $KEY deploy/deploy.sh deploy/verify.sh deploy/compose.prod.yml \
    deploy/.env.example $VPS:/opt/pocketquant/deploy/
scp -i $KEY deploy/scripts/cleanup.sh deploy/scripts/server-setup.sh \
    $VPS:/opt/pocketquant/deploy/scripts/

# .env is git-ignored — ensure local deploy/.env has prod values, then:
scp -i $KEY deploy/.env $VPS:/opt/pocketquant/deploy/.env
```

### Step 4: Fix CRLF if scp'd from Windows

```bash
ssh -i $KEY $VPS "
  sed -i 's/\r$//' /opt/pocketquant/deploy/deploy.sh
  sed -i 's/\r$//' /opt/pocketquant/deploy/verify.sh
  sed -i 's/\r$//' /opt/pocketquant/deploy/scripts/*.sh
"
```

### Step 5: Deploy

```bash
ssh -i $KEY $VPS "cd /opt/pocketquant && bash deploy/deploy.sh"
```

### Step 6: Verify

```bash
ssh -i $KEY $VPS "cd /opt/pocketquant && bash deploy/verify.sh"
# Inspect report (lives next to script in new layout):
ssh -i $KEY $VPS "ls -lt /opt/pocketquant/deploy/reports/ | head"
```

All checks should be PASS. If any FAIL, jump to [Rollback Runbook](#rollback-runbook).

---

## Rollback Runbook

If new-layout deploy fails AND old `docker/` files are still on the VPS (or in a snapshot):

```bash
ssh -i $KEY $VPS
cd /opt/pocketquant

# Stop new-layout containers
docker compose -f deploy/compose.prod.yml --env-file deploy/.env down || true

# Restore old layout
mkdir -p docker/scripts
mv deploy/deploy.sh                  deploy.sh
mv deploy/verify.sh                  verify.sh
mv deploy/compose.prod.yml           docker/compose.prod.yml
mv deploy/compose.yml                docker/compose.yml         2>/dev/null || true
mv deploy/.env                       docker/.env
mv deploy/scripts/cleanup.sh         docker/scripts/cleanup.sh
mv deploy/scripts/server-setup.sh    docker/scripts/server-setup.sh
rmdir deploy/scripts/patches deploy/scripts deploy 2>/dev/null || true

# Pull OLD images (use last-known-good SHA, NOT :latest — :latest will already be overwritten by CI)
docker pull <DOCKERHUB_USERNAME>/pocketquant:sha-<LAST_GOOD_SHA>
docker pull <DOCKERHUB_USERNAME>/pocketquant-web:sha-<LAST_GOOD_SHA>

# Override IMAGE_TAG and re-deploy old layout:
IMAGE_TAG=sha-<LAST_GOOD_SHA> bash deploy.sh
```

If DB schema also broke (unlikely — this refactor is layout-only), restore from `./backups/pre-deploy-layout.archive`:

```bash
docker exec -i pocketquant-mongodb mongorestore --archive --gzip --drop < ./backups/pre-deploy-layout.archive
```

---

Current note: for local development and UI testing, use [README](../README.md) and [run-and-test-guide](./run-and-test-guide.md). This document is production-only.

## Architecture

5 Docker containers on a disposable VPS (app, web, mongodb, redis, portainer). CI builds image, you pull manually.

```
GitHub push → CI builds Docker image → Docker Hub
VPS: deploy/deploy.sh pulls image → docker compose up (app + web + mongodb + redis + portainer)
```

### Distributed Scheduling

Background sync jobs are scheduled via APScheduler with a **MongoDBJobStore** backed by collection `apscheduler_jobs`. Multiple processes (e.g. the VPS app + a local dev BE pointing at VPS Mongo) coordinate through this shared collection — the first instance to update `next_run_time` wins each tick, the others skip. No extra lock layer needed. See [Local Dev Pointing at VPS DB](#local-dev-pointing-at-vps-db).

## Prerequisites

**One-time GitHub setup:**

1. Create Docker Hub access token: hub.docker.com → Account Settings → Security → New Access Token
2. Add GitHub repo secrets (Settings → Secrets and variables → Actions):
   - `DOCKERHUB_USERNAME` — your Docker Hub username
   - `DOCKERHUB_TOKEN` — the access token from step 1

## SSH Session Variables

Set these in each terminal session before running deploy commands:

```powershell
$KEY = "path\to\your\vps-private-key"
$VPS = "root@<vps-ip>"

# Example:
# $KEY = "C:\w\_me\pocketquant-config\sandbox\vultr"
# $VPS = "root@207.148.79.60"
```

All commands below use `ssh -i $KEY $VPS` pattern.

## Port Map

| Service | Env Var | Container Port |
|---------|---------|----------------|
| App API | `APP_PORT` | 41920 |
| MongoDB | `MONGO_PORT` | 27017 |
| Redis | `REDIS_PORT` | 6379 |
| Portainer | `PORTAINER_PORT` | 9000 |

No default ports — you MUST set them in `.env`. Pick obscure values to avoid scanning.

---

## First Deploy

### Step 1: Prepare .env

```bash
cp deploy/.env.example deploy/.env
```

Edit `deploy/.env` — uncomment and fill the production infrastructure section:

```env
# Change these from dev defaults:
ENVIRONMENT=production
LOG_FORMAT=json

# Uncomment and fill these:
DOCKERHUB_USERNAME=your-dockerhub-username
IMAGE_TAG=latest
MONGO_USER=pocketquant
MONGO_PASSWORD=your_strong_random_password
APP_PORT=58921
MONGO_PORT=52017
REDIS_PORT=53679
PORTAINER_PORT=54900

# Optional — fill if using OKX live trading:
OKX_API_KEY=your_key
OKX_API_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase
OKX_DEMO_MODE=false

# Crypto market data: Binance public REST/WS (no auth required)
# Remove stale TRADINGVIEW_* vars from production .env if present (ignored by Pydantic via extra="ignore")
```

### Step 2: Copy files to VPS

```bash
ssh -i $KEY $VPS "mkdir -p /opt/pocketquant/deploy/scripts/patches"
scp -i $KEY deploy/deploy.sh deploy/verify.sh deploy/compose.prod.yml ${VPS}:/opt/pocketquant/deploy/
scp -i $KEY deploy/scripts/cleanup.sh deploy/scripts/server-setup.sh ${VPS}:/opt/pocketquant/deploy/scripts/
scp -i $KEY deploy/.env ${VPS}:/opt/pocketquant/deploy/.env
```

### Step 3: Run deploy

```bash
ssh -i $KEY $VPS "cd /opt/pocketquant && bash deploy/deploy.sh"
```

`deploy/deploy.sh` will:
- Install Docker if missing (then exit — re-run after logging back in)
- Validate all required env vars
- Pull image from Docker Hub
- Start all 4 services
- Prune old images

**Windows users:** If deploy/deploy.sh fails with `invalid option`, fix CRLF line endings first:

```bash
ssh -i $KEY $VPS "sed -i 's/\r$//' /opt/pocketquant/deploy/deploy.sh /opt/pocketquant/deploy/verify.sh /opt/pocketquant/deploy/scripts/*.sh"
```

### Step 4: Verify

```bash
ssh -i $KEY $VPS "cd /opt/pocketquant && bash deploy/verify.sh"
```

Runs 15 checks (containers, health, HTTP, MongoDB, Redis, disk, memory, ports, image, logs) and outputs a markdown report to `reports/verify-<UTC-timestamp>.md` on the VPS.

Quick check without full report:

```bash
ssh -i $KEY $VPS "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep pocketquant"
ssh -i $KEY $VPS "curl -s http://localhost:\$APP_PORT/health"
```

Portainer UI: `http://vps-ip:$PORTAINER_PORT`

---

## Updating (2nd+ Deploy)

After pushing code (CI triggers on `master` and `develop`):

```bash
# 1. CI builds + pushes image automatically (check GitHub Actions tab)
# 2. Pull and restart on VPS:
ssh -i $KEY $VPS "cd /opt/pocketquant && bash deploy/deploy.sh"
```

If compose file changed, re-scp it first:

```bash
scp -i $KEY deploy/compose.prod.yml ${VPS}:/opt/pocketquant/deploy/
ssh -i $KEY $VPS "cd /opt/pocketquant && bash deploy/deploy.sh"
```

If .env changed:

```bash
scp -i $KEY deploy/.env ${VPS}:/opt/pocketquant/deploy/.env
ssh -i $KEY $VPS "cd /opt/pocketquant && bash deploy/deploy.sh"
```

---

## 2-Year Bar Re-Sync Procedure

**Purpose:** Refresh historical market data after major data source changes (e.g., Binance migration, bug fixes).

**Prerequisites:** VPS deployment running, MongoDB accessible, ~30 GB free disk space for mongodump backup.

**Runbook:**

### Step 1: Backup Current Data
```bash
ssh -i $KEY $VPS "mongodump --uri='$MONGODB_URL' --archive=/opt/pocketquant/backup-$(date -u +%Y%m%d-%H%M%S).archive"
```

### Step 2: Pre-Audit (Baseline Quality Check)
```bash
ssh -i $KEY $VPS "cd /opt/pocketquant && python scripts/audit_bar_quality.py --days 730 --output /opt/pocketquant/audit-pre.md"
# Inspect output — note flat_pct and zerovol_pct per interval
```

### Step 3: Plan Resync (Dry Run)
```bash
ssh -i $KEY $VPS "cd /opt/pocketquant && python scripts/resync_2y_from_binance.py --dry-run --days 730"
# Output shows symbols, intervals, and bar counts to resync (no writes)
```

### Step 4: Execute Resync (Live)
```bash
# For all symbols (default, ~2-3 hours):
ssh -i $KEY $VPS "cd /opt/pocketquant && python scripts/resync_2y_from_binance.py --days 730"

# For specific symbols only (faster, ~30 min):
ssh -i $KEY $VPS "cd /opt/pocketquant && python scripts/resync_2y_from_binance.py --days 730 --symbols BTCUSDT,ETHUSDT"
```

### Step 5: Higher-Timeframe Direct Fetch
```bash
# Binance cascade (1m→5m→15m→...→1M) is slow over WAN.
# Fetch higher TFs directly for speed:
ssh -i $KEY $VPS "curl -X POST http://localhost:\$APP_PORT/api/v1/market-data/sync \
  -H 'Content-Type: application/json' \
  -d '{\"symbol\":\"BTCUSDT\",\"exchange\":\"BINANCE\",\"interval\":\"1h\",\"n_bars\":17520}'"
# Repeat for 4h (4380 bars) and 1d (730 bars)
```

### Step 6: Post-Audit (Verify Quality)
```bash
ssh -i $KEY $VPS "cd /opt/pocketquant && python scripts/audit_bar_quality.py --days 730 --output /opt/pocketquant/audit-post.md"
# Compare to pre-audit: flat_pct and zerovol_pct should be ≤ 1% (or 0.0% if bug fixed)
```

**Monitoring:** Check VPS logs during resync via `docker logs pocketquant-app --tail 100 -f` for rate-limit errors or data quality warnings.

---

## Connecting from Local Machine

| Tool | Connection |
|------|------------|
| Swagger | `http://vps-ip:$APP_PORT/api/v1/docs` |
| DataGrip | `mongodb://pocketquant:PASSWORD@vps-ip:$MONGO_PORT/pocketquant?authSource=admin` |
| RedisInsight | `vps-ip:$REDIS_PORT` |
| Portainer | `http://vps-ip:$PORTAINER_PORT` |

Replace `$VAR` with your actual port values from `.env`.

### SSH Tunnel (if firewall blocks DB ports)

```bash
ssh -i $KEY -L 52017:localhost:52017 -L 53679:localhost:53679 $VPS
# Then connect DataGrip to localhost:52017
```

---

## Local Dev Pointing at VPS DB

Run FE + BE on your machine but point them at the production VPS Mongo + Redis so there is one source of truth for data. Useful for live debugging, feature work, and ad-hoc queries against real data.

### Setup

1. Copy VPS connection settings from `pocketquant-config/.env.prod` into your local `D:\w\_me\pocketquant\.env`. Override these for local-friendly behaviour:

   ```env
   ENVIRONMENT=development
   LOG_FORMAT=console
   ```

2. Verify connectivity to `<vps-ip>:<MONGO_PORT>` and `<vps-ip>:<REDIS_PORT>` (mongo shell, redis-cli, or your IDE).

3. Start servers (two terminals):

   ```bash
   just be      # FastAPI on :41920
   just fe      # Vite dev server on :5173 (proxies /api -> :41920)
   ```

   Or build the SPA once (`cd packages/pocketquant-web && npm run build`) and let FastAPI serve it at `http://localhost:41920/`.

### Safety notes

- Local writes go to the **production** database. Treat destructive scripts (drop, reset, bulk delete) with the same care as on the VPS.
- Tests must NEVER touch prod. `packages/pocketquant-core/tests/conftest.py` raises if `MONGODB_URL` or `REDIS_URL` contains the prod IP, and uses ephemeral testcontainers (Mongo + Redis) for the `settings` fixture.
- Before pointing at prod, back up your previous local config: `cp .env .env.local-only.bak`. To revert: `cp .env.local-only.bak .env && just up`.
- `ENABLE_JOBS=true` on local is safe because the MongoDBJobStore coordinates with the VPS scheduler — the same job will not fire twice per tick.

---

## Firewall (Recommended)

```bash
sudo ufw allow 22                 # SSH
sudo ufw allow <APP_PORT>         # App API
sudo ufw allow <PORTAINER_PORT>   # Portainer
sudo ufw deny <MONGO_PORT>        # Block external MongoDB
sudo ufw deny <REDIS_PORT>        # Block external Redis
sudo ufw enable
```

---

## Troubleshooting

```bash
# Container status
ssh -i $KEY $VPS "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep pocketquant"

# App logs (last 50 lines)
ssh -i $KEY $VPS "docker logs pocketquant-app --tail 50"

# Health check
ssh -i $KEY $VPS "docker exec pocketquant-app curl -s http://localhost:41920/health"

# Restart all services
ssh -i $KEY $VPS "cd /opt/pocketquant && docker compose -f deploy/compose.prod.yml --env-file deploy/.env restart"

# Wipe everything and redeploy (destroys database)
ssh -i $KEY $VPS "cd /opt/pocketquant && docker compose -f deploy/compose.prod.yml --env-file deploy/.env down -v && bash deploy/deploy.sh"
```

---

## VPS Migration

VPS is disposable. To move to a new VPS, repeat "First Deploy" steps. Database will be fresh — everything can be re-synced.

## Post-Migration Cleanup (GitHub)

After migrating from the old GHCR-based setup, delete unused GitHub repo settings:

**Delete secrets:** DEPLOY_SSH_KEY, GHCR_TOKEN, MONGO_PASSWORD, MONGO_EXPRESS_PASSWORD, GRAFANA_PASSWORD (TRADINGVIEW_USERNAME and TRADINGVIEW_PASSWORD already removed in v2.0.0), OKX_API_KEY, OKX_API_SECRET, OKX_PASSPHRASE

**Delete vars:** DEPLOY_HOST, DEPLOY_SSH_PORT, DEPLOY_USER

**Keep secrets:** DOCKERHUB_USERNAME, DOCKERHUB_TOKEN

---

## Sync Gap Repair

When `job_history` shows `missed` events for `sync_backfill` (or after manual deploy windows that overlapped 03:00-04:00 UTC), verify whether bar-data gaps persist and repair them.

The cascade in `sync_1m` already self-heals 100 min of missed 1m data per tick, so most missed-daily windows leave no residual gap — but always verify before assuming.

### Step 1: Audit

Use the integrity endpoint per `(symbol, interval)`:

```bash
ssh -i $KEY $VPS "curl -s -X POST http://localhost:\$APP_PORT/api/v1/market-data/integrity/check \
  -H 'Content-Type: application/json' \
  -d '{\"symbol\":\"BTCUSDT:BINANCE\",\"interval\":\"1m\",\"days_back\":7}' | jq ."
```

Response includes `missing_count`, `gap_ranges` (start/end timestamps), and `misaligned_ids`. The web Monitor view (`/monitor`) renders the same data across all tracked symbols.

### Step 2: Repair (only if audit shows gaps)

Either call the repair endpoint (deletes misaligned + auto-resyncs gap ranges):

```bash
ssh -i $KEY $VPS "curl -s -X POST http://localhost:\$APP_PORT/api/v1/market-data/integrity/repair \
  -H 'Content-Type: application/json' \
  -d '{\"symbol\":\"BTCUSDT:BINANCE\",\"interval\":\"1m\",\"days_back\":7}' | jq ."
```

Or hit the per-symbol sync endpoint directly with a deep `n_bars` window:

```bash
ssh -i $KEY $VPS "curl -X POST http://localhost:\$APP_PORT/api/v1/market-data/sync \
  -H 'Content-Type: application/json' \
  -d '{\"symbol\":\"BTCUSDT:BINANCE\",\"interval\":\"1m\",\"n_bars\":5000}'"
```

`n_bars=5000` covers >3 days of 1m bars — enough to repair any realistic missed-backfill window.

### Step 3: Verify

Re-run Step 1 — expect `missing_count == 0` and empty `gap_ranges`. Any residual gap means the source provider is missing data for that window (not a sync issue) and the gap is unrecoverable.

### Catch-up at boot (automatic)

As of the scheduler-resilience changes, `start_background_jobs` runs `enqueue_missed_catchups` after cron registration. If the last successful `sync_backfill` / `sync_integrity` was >25h ago (or `sync_repair` >12.5h ago), a `<job_id>_catchup` one-off run is enqueued automatically. Manual audit is still recommended after any restart spanning a daily window, until 30 days of clean `job_history` confirm the catch-up is reliable.
