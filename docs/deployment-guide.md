# Production Deployment Guide

**Last Updated:** 2026-05-04 | **CI:** GitHub Actions → Docker Hub | **CD:** Manual via deploy.sh

Current note: for local development and UI testing, use [README](../README.md) and [run-and-test-guide](./run-and-test-guide.md). This document is production-only.

## Architecture

5 Docker containers on a disposable VPS (app, web, mongodb, redis, portainer). CI builds image, you pull manually.

```
GitHub push → CI builds Docker image → Docker Hub
VPS: deploy.sh pulls image → docker compose up (app + web + mongodb + redis + portainer)
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
cp .env.example .env.prod
```

Edit `.env.prod` — uncomment and fill the production infrastructure section:

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

# Optional — fill if using:
TRADINGVIEW_USERNAME=your_username
TRADINGVIEW_PASSWORD=your_password
OKX_API_KEY=your_key
OKX_API_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase
OKX_DEMO_MODE=false
```

### Step 2: Copy files to VPS

```bash
ssh -i $KEY $VPS "mkdir -p /opt/pocketquant/docker"
scp -i $KEY deploy.sh verify.sh ${VPS}:/opt/pocketquant/
scp -i $KEY docker/compose.prod.yml ${VPS}:/opt/pocketquant/docker/
scp -i $KEY .env ${VPS}:/opt/pocketquant/docker/.env
```

### Step 3: Run deploy

```bash
ssh -i $KEY $VPS "cd /opt/pocketquant && bash deploy.sh"
```

`deploy.sh` will:
- Install Docker if missing (then exit — re-run after logging back in)
- Validate all required env vars
- Pull image from Docker Hub
- Start all 4 services
- Prune old images

**Windows users:** If deploy.sh fails with `invalid option`, fix CRLF line endings first:

```bash
ssh -i $KEY $VPS "sed -i 's/\r$//' /opt/pocketquant/deploy.sh"
```

### Step 4: Verify

```bash
ssh -i $KEY $VPS "cd /opt/pocketquant && bash verify.sh"
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
ssh -i $KEY $VPS "cd /opt/pocketquant && bash deploy.sh"
```

If compose file changed, re-scp it first:

```bash
scp -i $KEY docker/compose.prod.yml ${VPS}:/opt/pocketquant/docker/
ssh -i $KEY $VPS "cd /opt/pocketquant && bash deploy.sh"
```

If .env changed:

```bash
scp -i $KEY .env ${VPS}:/opt/pocketquant/docker/.env
ssh -i $KEY $VPS "cd /opt/pocketquant && bash deploy.sh"
```

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

2. Verify connectivity:

   ```bash
   just check
   ```

   Expect Mongo + Redis healthy against `<vps-ip>:<MONGO_PORT>` and `<vps-ip>:<REDIS_PORT>`.

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
ssh -i $KEY $VPS "cd /opt/pocketquant && docker compose -f docker/compose.prod.yml --env-file docker/.env restart"

# Wipe everything and redeploy (destroys database)
ssh -i $KEY $VPS "cd /opt/pocketquant && docker compose -f docker/compose.prod.yml --env-file docker/.env down -v && bash deploy.sh"
```

---

## VPS Migration

VPS is disposable. To move to a new VPS, repeat "First Deploy" steps. Database will be fresh — everything can be re-synced.

## Post-Migration Cleanup (GitHub)

After migrating from the old GHCR-based setup, delete unused GitHub repo settings:

**Delete secrets:** DEPLOY_SSH_KEY, GHCR_TOKEN, MONGO_PASSWORD, MONGO_EXPRESS_PASSWORD, GRAFANA_PASSWORD, TRADINGVIEW_USERNAME, TRADINGVIEW_PASSWORD, OKX_API_KEY, OKX_API_SECRET, OKX_PASSPHRASE

**Delete vars:** DEPLOY_HOST, DEPLOY_SSH_PORT, DEPLOY_USER

**Keep secrets:** DOCKERHUB_USERNAME, DOCKERHUB_TOKEN
