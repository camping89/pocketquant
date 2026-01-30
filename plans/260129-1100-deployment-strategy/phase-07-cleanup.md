# Phase 07: Automated Cleanup

## Context

- **Parent:** [plan.md](plan.md)
- **Dependencies:** [Phase 04](phase-04-server-setup.md)
- **Docs:** Docker documentation

## Overview

| Field | Value |
|-------|-------|
| Priority | P2 |
| Status | ⏳ Pending |
| Effort | 15m |

Setup automated cleanup để prevent disk full từ Docker images, logs, và build cache.

## Key Insights

- Docker images accumulate với mỗi deploy
- Container logs có thể grow indefinitely
- Build cache tốn disk
- Cron job chạy daily cleanup

## What Gets Cleaned

| Item | Command | Schedule |
|------|---------|----------|
| Dangling images | `docker image prune -f` | Daily |
| Old images (>7 days) | `docker image prune -af --filter "until=168h"` | Daily |
| Stopped containers | `docker container prune -f` | Daily |
| Unused networks | `docker network prune -f` | Weekly |
| Build cache | `docker builder prune -f --filter "until=168h"` | Weekly |
| Unused volumes | Manual only | Never (data!) |

## Implementation Steps

### Step 1: Create Cleanup Script

```bash
# scripts/cleanup.sh
#!/bin/bash
# Docker cleanup script - run daily via cron
# Prevents disk full from accumulated Docker resources

set -e

LOG_FILE="/var/log/docker-cleanup.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

log() {
    echo "[$DATE] $1" | tee -a "$LOG_FILE"
}

log "=== Starting Docker cleanup ==="

# Get disk usage before
DISK_BEFORE=$(df -h / | awk 'NR==2 {print $5}')
log "Disk usage before: $DISK_BEFORE"

# Remove dangling images (not tagged, not used)
log "Removing dangling images..."
docker image prune -f >> "$LOG_FILE" 2>&1

# Remove images older than 7 days (except those in use)
log "Removing old images (>7 days)..."
docker image prune -af --filter "until=168h" >> "$LOG_FILE" 2>&1

# Remove stopped containers (should be none with restart: unless-stopped)
log "Removing stopped containers..."
docker container prune -f >> "$LOG_FILE" 2>&1

# Day of week check (0 = Sunday)
DOW=$(date +%u)

if [ "$DOW" -eq 7 ]; then
    log "Weekly cleanup (Sunday)..."

    # Remove unused networks
    log "Removing unused networks..."
    docker network prune -f >> "$LOG_FILE" 2>&1

    # Remove build cache older than 7 days
    log "Removing old build cache..."
    docker builder prune -f --filter "until=168h" >> "$LOG_FILE" 2>&1
fi

# Get disk usage after
DISK_AFTER=$(df -h / | awk 'NR==2 {print $5}')
log "Disk usage after: $DISK_AFTER"

log "=== Cleanup completed ==="
echo "" >> "$LOG_FILE"
```

### Step 2: Deploy Script to Server

```bash
# On server
mkdir -p /opt/pocketquant/scripts
# Copy cleanup.sh to /opt/pocketquant/scripts/cleanup.sh
chmod +x /opt/pocketquant/scripts/cleanup.sh
```

### Step 3: Setup Cron Job

```bash
# Edit crontab
crontab -e

# Add daily cleanup at 3 AM
0 3 * * * /opt/pocketquant/scripts/cleanup.sh

# Verify
crontab -l
```

### Step 4: Setup Log Rotation for Cleanup Logs

```bash
# Create logrotate config
sudo tee /etc/logrotate.d/docker-cleanup << 'EOF'
/var/log/docker-cleanup.log {
    weekly
    rotate 4
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
}
EOF
```

### Step 5: Docker Log Limits (Already in compose.prod.yml)

Đã config trong Phase 02:

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

Mỗi container max 30MB logs (10MB × 3 files).

### Step 6: Disk Alert Script (Optional)

```bash
# scripts/disk-alert.sh
#!/bin/bash
# Alert when disk usage exceeds threshold

THRESHOLD=85
USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')

if [ "$USAGE" -gt "$THRESHOLD" ]; then
    echo "WARNING: Disk usage is ${USAGE}% (threshold: ${THRESHOLD}%)"
    # Add notification here (webhook, email, etc.)
fi
```

```bash
# Add to cron - check every hour
0 * * * * /opt/pocketquant/scripts/disk-alert.sh
```

## Manual Cleanup Commands

```bash
# Emergency cleanup - free space immediately
docker system prune -af

# Check what's using space
docker system df

# List largest images
docker images --format "{{.Size}}\t{{.Repository}}:{{.Tag}}" | sort -hr | head -20

# List container log sizes
du -sh /var/lib/docker/containers/*/

# WARNING: This removes ALL unused volumes (data loss!)
# docker volume prune -f
```

## Disk Space Budget (2GB VPS)

| Component | Size |
|-----------|------|
| Ubuntu OS | ~2GB |
| Docker Engine | ~500MB |
| App Image | ~300MB |
| MongoDB Data | Variable |
| Redis Data | ~100MB max |
| Loki Logs (7 days) | ~350MB |
| Grafana | ~100MB |
| **Buffer needed** | ~500MB |

With cleanup, disk should stay healthy.

## Todo List

- [ ] Create `scripts/cleanup.sh`
- [ ] Deploy to server
- [ ] Setup cron job (daily 3 AM)
- [ ] Setup logrotate
- [ ] Test cleanup script manually
- [ ] Verify disk usage after cleanup

## Success Criteria

- [ ] Cleanup script runs without errors
- [ ] Cron job scheduled
- [ ] Disk usage stays under 80%
- [ ] Old images removed automatically
- [ ] Logs visible in `/var/log/docker-cleanup.log`

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Delete wrong images | High | Only delete old/dangling |
| Volume data loss | Critical | Never auto-prune volumes |
| Script fails silently | Medium | Log all output |

## Security Considerations

- Script runs as deploy user (has docker access)
- No secrets in script
- Log file readable by root only

## Monitoring Disk Usage

```bash
# Add to Grafana/Prometheus if available
# Or simple cron check:

# Check disk every hour, log if > 70%
0 * * * * df -h / | awk 'NR==2 && int($5) > 70 {print strftime("%Y-%m-%d %H:%M") " Disk: " $5}' >> /var/log/disk-monitor.log
```

## Next Steps

After completion → Deployment pipeline complete! 🎉

**Final checklist:**
- [ ] All phases completed
- [ ] Push to master triggers deploy
- [ ] Health check passes
- [ ] Logs visible in Grafana
- [ ] Portainer shows all containers
- [ ] Cleanup cron scheduled
- [ ] Can rollback within 2 minutes
