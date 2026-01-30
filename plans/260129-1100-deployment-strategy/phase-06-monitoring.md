# Phase 06: Self-hosted Monitoring (Loki + Grafana)

## Context

- **Parent:** [plan.md](plan.md)
- **Dependencies:** [Phase 02](phase-02-compose-prod.md), [Phase 05](phase-05-caddy-portainer.md)
- **Docs:** Grafana Loki documentation

## Overview

| Field | Value |
|-------|-------|
| Priority | P2 |
| Status | ⏳ Pending |
| Effort | 30m |

Setup self-hosted Loki + Grafana để log aggregation và visualization.

## Key Insights

- Loki lightweight hơn ELK stack
- Promtail auto-discover Docker containers
- Grafana có pre-built Loki datasource
- 7-day log retention (configurable)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                          VPS                                │
│                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐  │
│  │   App    │    │  Other   │    │     Docker Logs      │  │
│  │ (JSON)   │    │ Services │    │  /var/lib/docker/... │  │
│  └────┬─────┘    └────┬─────┘    └──────────┬───────────┘  │
│       │               │                      │              │
│       └───────────────┴──────────────────────┘              │
│                          │                                   │
│                          ▼                                   │
│                   ┌──────────────┐                          │
│                   │   Promtail   │ (scrape logs)            │
│                   └──────┬───────┘                          │
│                          │                                   │
│                          ▼                                   │
│                   ┌──────────────┐                          │
│                   │     Loki     │ (store + index)          │
│                   │   (256MB)    │                          │
│                   └──────┬───────┘                          │
│                          │                                   │
│                          ▼                                   │
│                   ┌──────────────┐                          │
│                   │   Grafana    │ (visualize)              │
│                   │   (256MB)    │                          │
│                   └──────────────┘                          │
│                          │                                   │
│                          ▼                                   │
│                   http://IP/grafana                         │
└─────────────────────────────────────────────────────────────┘
```

## Config Files (created in Phase 02)

Files đã được define trong Phase 02:
- `docker/loki-config.yml` - Loki configuration
- `docker/promtail-config.yml` - Promtail log scraping
- `docker/grafana-datasources.yml` - Auto-provision Loki datasource

## Implementation Steps

### Step 1: Verify Config Files

```bash
# On server
cd /opt/pocketquant/docker

# Check files exist
ls -la loki-config.yml promtail-config.yml grafana-datasources.yml
```

### Step 2: Start Monitoring Stack

```bash
cd /opt/pocketquant

# Start with monitoring profile
docker compose -f docker/compose.prod.yml \
  --env-file docker/.env.prod \
  --profile monitoring \
  up -d loki promtail grafana

# Check status
docker ps | grep -E "loki|promtail|grafana"
```

### Step 3: Access Grafana

```bash
# Via Caddy
http://YOUR_IP/grafana

# Login
Username: admin (or $GRAFANA_USER from .env.prod)
Password: from $GRAFANA_PASSWORD in .env.prod
```

### Step 4: Verify Loki Datasource

1. Go to Grafana → Connections → Data sources
2. Should see "Loki" already configured (auto-provisioned)
3. Click "Test" to verify connection

### Step 5: Create Log Dashboard

1. Go to Explore (compass icon)
2. Select Loki datasource
3. Try these queries:

```logql
# All logs from app
{container="pocketquant-app"}

# Error logs only
{container="pocketquant-app"} |= "error"

# JSON parsing
{container="pocketquant-app"} | json | level="ERROR"

# Count errors over time
count_over_time({container="pocketquant-app"} |= "error" [5m])

# Specific event
{container="pocketquant-app"} | json | event="sync_completed"
```

### Step 6: Save Dashboard

1. Create new dashboard
2. Add panels:
   - **Logs Panel**: `{container="pocketquant-app"}`
   - **Error Count**: `count_over_time({container=~"pocketquant.*"} |= "error" [1h])`
   - **Request Rate**: Based on your app's log format

### Step 7: Optional - Setup Alerts

1. Go to Alerting → Alert rules
2. Create rule:
   - Name: "High Error Rate"
   - Query: `count_over_time({container="pocketquant-app"} |= "error" [5m]) > 10`
   - Contact point: (configure email/webhook)

## Resource Usage

| Component | Memory | Disk |
|-----------|--------|------|
| Loki | 256MB | ~50MB/day logs |
| Promtail | 64MB | minimal |
| Grafana | 256MB | ~100MB |

With 7-day retention, expect ~350MB disk for logs.

## Log Retention

Configured in `loki-config.yml`:

```yaml
limits_config:
  retention_period: 168h  # 7 days
```

Adjust based on disk space:
- `24h` = 1 day
- `168h` = 7 days
- `720h` = 30 days

## Todo List

- [ ] Verify config files on server
- [ ] Start monitoring stack
- [ ] Access Grafana
- [ ] Verify Loki datasource
- [ ] Test log queries
- [ ] Create basic dashboard

## Success Criteria

- [ ] Grafana accessible at `/grafana`
- [ ] Loki datasource connected
- [ ] App logs visible in Explore
- [ ] Can filter by container/level
- [ ] Dashboard saved

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Disk full from logs | High | Retention policy + cleanup |
| Loki OOM | Medium | Memory limit 256MB |
| No logs appearing | Medium | Check Promtail config |

## Troubleshooting

### No logs in Grafana

```bash
# Check Promtail
docker logs pocketquant-promtail

# Check Loki
docker logs pocketquant-loki

# Verify Promtail can reach Loki
docker exec pocketquant-promtail wget -qO- http://loki:3100/ready
```

### Loki not starting

```bash
# Check config syntax
docker run --rm -v $(pwd)/docker/loki-config.yml:/etc/loki/config.yaml \
  grafana/loki:2.9.0 -config.file=/etc/loki/config.yaml -verify-config
```

## Next Steps

After completion → [Phase 07: Cleanup](phase-07-cleanup.md)
