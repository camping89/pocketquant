#!/bin/bash
# Docker cleanup script - run daily via cron
# Prevents disk full from accumulated Docker resources

set -e

LOG_FILE="/var/log/docker-cleanup.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Ensure log file exists and is writable
if [ ! -f "$LOG_FILE" ]; then
    touch "$LOG_FILE" 2>/dev/null || LOG_FILE="/tmp/docker-cleanup.log"
fi
if [ ! -w "$LOG_FILE" ]; then
    LOG_FILE="/tmp/docker-cleanup.log"
fi

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

# Day of week check (7 = Sunday)
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
