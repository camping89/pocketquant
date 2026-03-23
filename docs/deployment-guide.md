# Production Deployment Guide

**Last Updated:** 2026-03-23 | **CI:** GitHub Actions → Docker Hub | **CD:** Manual via deploy.sh

## Architecture

4 Docker containers on a disposable VPS. CI builds image, you pull manually.

```
GitHub push → CI builds Docker image → Docker Hub
VPS: deploy.sh pulls image → docker compose up (app + mongodb + redis + portainer)
```

## Prerequisites

**One-time GitHub setup:**

1. Create Docker Hub access token: hub.docker.com → Account Settings → Security → New Access Token
2. Add GitHub repo secrets (Settings → Secrets and variables → Actions):
   - `DOCKERHUB_USERNAME` — your Docker Hub username
   - `DOCKERHUB_TOKEN` — the access token from step 1

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
ssh vps "mkdir -p /opt/pocketquant/docker"
scp deploy.sh vps:/opt/pocketquant/
scp docker/compose.prod.yml docker/mongo-init.js vps:/opt/pocketquant/docker/
scp .env.prod vps:/opt/pocketquant/docker/.env
```

### Step 3: Run deploy

```bash
ssh vps "cd /opt/pocketquant && bash deploy.sh"
```

`deploy.sh` will:
- Install Docker if missing (then exit — re-run after logging back in)
- Validate all required env vars
- Pull image from Docker Hub
- Start all 4 services
- Prune old images

### Step 4: Verify

```bash
ssh vps "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep pocketquant"
```

Expected: 4 containers running (app, mongodb, redis, portainer).

```bash
# Health check
ssh vps "curl -s http://localhost:\$APP_PORT/health"

# Portainer UI
open http://vps-ip:$PORTAINER_PORT
```

---

## Updating (2nd+ Deploy)

After pushing code to master:

```bash
# 1. CI builds + pushes image automatically (check GitHub Actions tab)
# 2. Pull and restart on VPS:
ssh vps "cd /opt/pocketquant && bash deploy.sh"
```

If compose file or mongo-init.js changed, re-scp them first:

```bash
scp docker/compose.prod.yml docker/mongo-init.js vps:/opt/pocketquant/docker/
ssh vps "cd /opt/pocketquant && bash deploy.sh"
```

If .env changed:

```bash
scp .env.prod vps:/opt/pocketquant/docker/.env
ssh vps "cd /opt/pocketquant && bash deploy.sh"
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
ssh -L 52017:localhost:52017 -L 53679:localhost:53679 vps
# Then connect DataGrip to localhost:52017
```

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
ssh vps "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep pocketquant"

# App logs (last 50 lines)
ssh vps "docker logs pocketquant-app --tail 50"

# Health check
ssh vps "docker exec pocketquant-app curl -s http://localhost:41920/health"

# Restart all services
ssh vps "cd /opt/pocketquant && docker compose -f docker/compose.prod.yml --env-file docker/.env restart"

# Wipe everything and redeploy (destroys database)
ssh vps "cd /opt/pocketquant && docker compose -f docker/compose.prod.yml --env-file docker/.env down -v && bash deploy.sh"
```

---

## VPS Migration

VPS is disposable. To move to a new VPS, repeat "First Deploy" steps. Database will be fresh — everything can be re-synced.

## Post-Migration Cleanup (GitHub)

After migrating from the old GHCR-based setup, delete unused GitHub repo settings:

**Delete secrets:** DEPLOY_SSH_KEY, GHCR_TOKEN, MONGO_PASSWORD, MONGO_EXPRESS_PASSWORD, GRAFANA_PASSWORD, TRADINGVIEW_USERNAME, TRADINGVIEW_PASSWORD, OKX_API_KEY, OKX_API_SECRET, OKX_PASSPHRASE

**Delete vars:** DEPLOY_HOST, DEPLOY_SSH_PORT, DEPLOY_USER

**Keep secrets:** DOCKERHUB_USERNAME, DOCKERHUB_TOKEN
