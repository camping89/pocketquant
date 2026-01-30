# Brainstorm Report: PocketQuant Deployment Strategy

**Date:** 2026-01-29
**Status:** Agreed
**Author:** Brainstorm Agent

---

## Problem Statement

Deploy PocketQuant (FastAPI + MongoDB + Redis + APScheduler) một cách tự động khi push code, với:
- Vultr VPS 2GB RAM (primary)
- MongoDB Atlas (managed)
- Redis self-hosted
- Budget: Personal/Hobby
- Automation level: Git push → Auto deploy

---

## Evaluated Approaches

### Approach 1: Docker + GitHub Actions + SSH Deploy ✅ SELECTED
| Aspect | Rating |
|--------|--------|
| Complexity | ⭐⭐ Low |
| Setup time | 2-3 hours |
| Learning curve | Minimal (đã quen Docker + GH Actions) |
| Cost | Free |
| Control | High |

**Pros:** Simple, debuggable, leverage existing skills
**Cons:** SSH key management, manual failover

### Approach 2: Docker + Watchtower
**Rejected:** Polling delay không lý tưởng, ít control

### Approach 3: Coolify/CapRover
**Rejected:** Overkill cho 1 app, chiếm ~1GB RAM overhead

---

## Final Solution Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    GITHUB (master branch)                   │
└────────────────────────┬────────────────────────────────────┘
                         │ push / merge
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   GITHUB ACTIONS WORKFLOW                   │
│  Build → Push GHCR → SSH Deploy → Health Check → Notify    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    VULTR VPS (2GB RAM)                      │
│  ┌────────────────────────────────────────────────────┐    │
│  │              DOCKER COMPOSE                         │    │
│  │  ┌──────────────┐  ┌───────────┐  ┌────────────┐  │    │
│  │  │ FastAPI App  │  │   Redis   │  │  Promtail  │  │    │
│  │  │ (Port 8000)  │  │  (6379)   │  │  (logs)    │  │    │
│  │  └──────────────┘  └───────────┘  └────────────┘  │    │
│  └────────────────────────────────────────────────────┘    │
│                           │                                 │
│  UFW Firewall: 22, 8000   │                                 │
└───────────────────────────┼─────────────────────────────────┘
                            │
           ┌────────────────┴────────────────┐
           ▼                                 ▼
┌─────────────────────┐           ┌─────────────────────┐
│   MONGODB ATLAS     │           │   GRAFANA CLOUD     │
│   (Free M0 Tier)    │           │   (Free Tier)       │
│   - Auto backups    │           │   - Loki logs       │
│   - Cloud managed   │           │   - Dashboards      │
└─────────────────────┘           └─────────────────────┘
```

---

## Implementation Components

### 1. Files to Create

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build for Python app |
| `docker/compose.prod.yml` | Production services (app + redis + promtail) |
| `.github/workflows/deploy.yml` | CI/CD pipeline |
| `scripts/server-setup.sh` | One-time server provisioning |

### 2. GitHub Secrets Required

```yaml
VULTR_HOST: <Vultr VPS IP>
VULTR_USER: deploy  # hoặc root
VULTR_SSH_KEY: <Private SSH key content>
MONGODB_URL: <Connection string>
TRADINGVIEW_USERNAME: <optional>
TRADINGVIEW_PASSWORD: <optional>
# For monitoring (optional)
GRAFANA_LOKI_URL: <Grafana Cloud Loki push URL>
GRAFANA_LOKI_USER: <numeric user ID>
GRAFANA_LOKI_TOKEN: <API token>
```

### 3. Deployment Flow

```
1. git push origin master
2. GitHub Actions triggers on push to master
3. Checkout code
4. Build Docker image (multi-stage, ~200MB final)
5. Push to ghcr.io/<username>/pocketquant:latest
6. SSH to Vultr:
   - docker pull ghcr.io/<username>/pocketquant:latest
   - docker compose -f docker/compose.prod.yml down
   - docker compose -f docker/compose.prod.yml up -d
7. Health check: curl http://localhost:8000/health
8. (Optional) Send notification to Telegram/Discord
```

---

## Monitoring & Logging Strategy

### Option A: Grafana Cloud (Recommended for Hobby)
- **Free tier:** 50GB logs/month, 10k series metrics
- **Components:**
  - Promtail sidecar → ships logs to Loki
  - Pre-built dashboards
- **Why:** Zero infra management, generous free tier

### Option B: Self-hosted (More control, more work)
- Loki + Grafana on same VPS
- Consumes ~300-500MB extra RAM
- Full control but more maintenance

### Recommended Monitoring Stack
```yaml
# docker/compose.prod.yml addition
services:
  promtail:
    image: grafana/promtail:latest
    volumes:
      - /var/log:/var/log:ro
      - ./promtail-config.yml:/etc/promtail/config.yml
    command: -config.file=/etc/promtail/config.yml
```

### Log Levels Strategy
```
Production: LOG_LEVEL=INFO, LOG_FORMAT=json
- All requests logged
- Business events logged
- Errors with stack traces
```

### Key Metrics to Watch
| Metric | Alert Threshold |
|--------|-----------------|
| Response time P95 | > 500ms |
| Error rate | > 1% |
| Memory usage | > 80% |
| Disk usage | > 85% |
| Background job failures | > 0 |

---

## Resource Estimation

| Component | RAM | CPU |
|-----------|-----|-----|
| Ubuntu 22.04 | 200MB | - |
| Docker Engine | 100MB | - |
| FastAPI App | 200-300MB | 0.5 core |
| Redis | 50-100MB | 0.1 core |
| Promtail | 50MB | 0.1 core |
| **Total** | **600-750MB** | **0.7 core** |
| **Available (2GB)** | **~1.3GB** ✅ | ✅ |

---

## Security Checklist

- [ ] SSH key-only auth (disable password)
- [ ] UFW firewall (allow: 22, 8000 only)
- [ ] Non-root deploy user
- [ ] GitHub secrets encrypted
- [ ] MongoDB Atlas IP whitelist
- [ ] Redis bound to localhost only
- [ ] HTTPS via reverse proxy (optional: Caddy/Nginx)

---

## Rollback Strategy

### Quick Rollback (< 1 min)
```bash
# On server
docker compose -f docker/compose.prod.yml down
docker tag ghcr.io/<user>/pocketquant:latest ghcr.io/<user>/pocketquant:broken
docker pull ghcr.io/<user>/pocketquant:previous
docker tag ghcr.io/<user>/pocketquant:previous ghcr.io/<user>/pocketquant:latest
docker compose -f docker/compose.prod.yml up -d
```

### Git Rollback
```bash
# Local
git revert HEAD
git push origin master
# → Triggers new deploy with reverted code
```

### Image Tagging Strategy
```
ghcr.io/<user>/pocketquant:latest      # Current production
ghcr.io/<user>/pocketquant:sha-abc123  # Git commit SHA
ghcr.io/<user>/pocketquant:v1.0.0      # Tagged releases
```

---

## Server Setup Checklist

### One-time Setup (Fresh Ubuntu)
```bash
# 1. Update system
apt update && apt upgrade -y

# 2. Create deploy user
adduser deploy
usermod -aG sudo deploy
usermod -aG docker deploy

# 3. Install Docker
curl -fsSL https://get.docker.com | sh

# 4. Setup SSH key for deploy user
mkdir -p /home/deploy/.ssh
# Add your public key to authorized_keys

# 5. Configure firewall
ufw allow 22
ufw allow 8000
ufw enable

# 6. Create app directory
mkdir -p /opt/pocketquant
chown deploy:deploy /opt/pocketquant
```

---

## Cost Analysis

| Service | Monthly Cost |
|---------|--------------|
| Vultr VPS 2GB | $12-15 |
| MongoDB Atlas M0 | Free |
| Grafana Cloud | Free |
| GitHub Actions | Free (2000 min) |
| Domain (optional) | $10-15/year |
| **Total** | **~$12-15/month** |

---

## Success Criteria

- [ ] Push to master → Deploy completes < 5 minutes
- [ ] Zero-downtime deploys (docker compose recreate)
- [ ] Logs accessible via Grafana Cloud
- [ ] Health endpoint responds 200
- [ ] Background jobs running (check /api/v1/system/jobs)
- [ ] Can rollback within 2 minutes

---

## Next Steps

1. **Server Setup:** Run provisioning script on Vultr
2. **MongoDB Atlas:** Create free cluster, get connection string
3. **GitHub Secrets:** Configure all required secrets
4. **Create Files:** Dockerfile, compose.prod.yml, deploy workflow
5. **First Deploy:** Push to master, verify everything works
6. **Monitoring:** Setup Grafana Cloud + Promtail

---

## Unresolved Questions

- Domain cần không? Nếu có thì dùng Cloudflare DNS + Caddy reverse proxy
- TradingView credentials có setup trên production không?
- Cần notification (Telegram/Discord) khi deploy xong không?
