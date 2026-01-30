---
title: "PocketQuant Deployment Strategy"
description: "Docker + GitHub Actions + SSH Deploy to Any VPS"
status: completed
priority: P1
effort: 4h
branch: feature/stream
tags: [deployment, ci-cd, docker, github-actions, self-hosted]
created: 2026-01-29
updated: 2026-01-29
---

# PocketQuant Deployment Strategy

## Overview

Triển khai CI/CD pipeline tự động cho PocketQuant:
- **Trigger:** Push to `master` branch
- **Build:** Multi-stage Docker image
- **Registry:** GitHub Container Registry (GHCR)
- **Deploy:** SSH to any VPS (Vultr, Azure, DigitalOcean, etc.)
- **Services:** All self-hosted (MongoDB, Redis, Loki, Grafana)
- **Management:** Caddy reverse proxy + Portainer UI

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           VPS (Any Provider)                            │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                      CADDY (:80/:443)                             │  │
│  │   /api/*     → app:8000          /portainer/* → portainer:9000   │  │
│  │   /grafana/* → grafana:3000      /mongo/*     → mongo-express    │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐   │
│  │   App    │ │ MongoDB  │ │  Redis   │ │ Grafana  │ │ Portainer  │   │
│  │  :8000   │ │  :27017  │ │  :6379   │ │  :3000   │ │   :9000    │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────────┘   │
│                                                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────────────────────┐   │
│  │   Loki   │ │ Promtail │ │   Cleanup Cron (docker prune daily) │   │
│  │  :3100   │ │          │ │                                      │   │
│  └──────────┘ └──────────┘ └──────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Implementation Phases

| Phase | Description | Status | Effort |
|-------|-------------|--------|--------|
| [Phase 01](phase-01-dockerfile.md) | Create Dockerfile | ✅ Done | 30m |
| [Phase 02](phase-02-compose-prod.md) | Production Docker Compose (full stack) | ✅ Done | 45m |
| [Phase 03](phase-03-github-actions.md) | GitHub Actions Workflow | ✅ Done | 45m |
| [Phase 04](phase-04-server-setup.md) | Server Setup (any provider) | ✅ Done | 45m |
| [Phase 05](phase-05-caddy-portainer.md) | Caddy + Portainer | ✅ Done | 30m |
| [Phase 06](phase-06-monitoring.md) | Self-hosted Loki + Grafana | ✅ Done (config in Phase 02) | 30m |
| [Phase 07](phase-07-cleanup.md) | Automated Cleanup | ✅ Done | 15m |

## Prerequisites

- [ ] VPS 2GB+ RAM với Ubuntu 22.04 (any provider)
- [ ] GitHub repository với GHCR enabled
- [ ] (Optional) Domain cho HTTPS

## GitHub Secrets Required

```yaml
# Generic naming - works with any VPS provider
DEPLOY_HOST       # VPS IP address
DEPLOY_USER       # SSH user (e.g., deploy)
DEPLOY_SSH_KEY    # Private SSH key (PEM format)

# App config (stored on server, not in secrets)
# MONGODB_URL, REDIS_URL, etc. → managed in server's .env file

# Optional
TRADINGVIEW_USERNAME
TRADINGVIEW_PASSWORD
```

## Files to Create

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage Python build |
| `docker/compose.prod.yml` | Full production stack |
| `docker/Caddyfile` | Reverse proxy config |
| `docker/loki-config.yml` | Loki log aggregation |
| `docker/promtail-config.yml` | Log shipping config |
| `.github/workflows/deploy.yml` | CI/CD pipeline |
| `scripts/server-setup.sh` | Server provisioning |
| `scripts/cleanup.sh` | Docker garbage collection |

## Services Overview

| Service | Port | Purpose | Exposed via Caddy |
|---------|------|---------|-------------------|
| App | 8000 | FastAPI application | `/api/*` |
| MongoDB | 27017 | Database | Internal only |
| Mongo Express | 8081 | DB admin UI | `/mongo/*` (auth) |
| Redis | 6379 | Cache | Internal only |
| Grafana | 3000 | Dashboards | `/grafana/*` |
| Loki | 3100 | Log aggregation | Internal only |
| Promtail | - | Log shipping | Internal only |
| Portainer | 9000 | Container UI | `/portainer/*` |

## Success Criteria

- [ ] Push to master → Deploy < 5 minutes
- [ ] Health check passes after deploy
- [ ] Logs visible in self-hosted Grafana
- [ ] Background jobs running
- [ ] Portainer accessible
- [ ] Auto cleanup prevents disk full
- [ ] Can rollback within 2 minutes

## Reference

- [Brainstorm Report](../reports/brainstorm-260129-1100-deployment-strategy.md)
