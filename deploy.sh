#!/usr/bin/env bash
set -euo pipefail

# PocketQuant VPS Deploy Script
# Handles first-time setup + subsequent deploys in one script.
#
# First time:
#   scp deploy.sh docker/compose.prod.yml .env to VPS
#   ssh vps "cd /opt/pocketquant && bash deploy.sh"
#
# Update:
#   ssh vps "cd /opt/pocketquant && bash deploy.sh"

cd "$(dirname "$0")"

# ─── Setup (runs only if needed) ──────────────────────────────

if ! command -v docker &>/dev/null; then
  echo "=== Installing Docker ==="
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"
  echo "Docker installed. Log out and back in, then re-run this script."
  exit 0
fi

if [ ! -f docker/.env ]; then
  echo "ERROR: docker/.env not found. Copy .env.example, fill prod values, place at docker/.env"
  exit 1
fi

# ─── Validate required env vars ───────────────────────────────

set -a && source docker/.env && set +a

REQUIRED_VARS="DOCKERHUB_USERNAME MONGO_PASSWORD APP_PORT MONGO_PORT REDIS_PORT PORTAINER_PORT"
for var in $REQUIRED_VARS; do
  if [ -z "${!var:-}" ]; then
    echo "ERROR: $var not set in docker/.env"
    exit 1
  fi
done

# ─── Deploy ───────────────────────────────────────────────────

echo "=== Pulling latest images ==="
docker pull "${DOCKERHUB_USERNAME}/pocketquant:${IMAGE_TAG:-latest}"
docker pull "${DOCKERHUB_USERNAME}/pocketquant-web:${IMAGE_TAG:-latest}"

echo "=== Starting services ==="
docker compose -f docker/compose.prod.yml --env-file docker/.env up -d --remove-orphans

# ─── One-time migrations (idempotent — safe to re-run every deploy) ───
echo "=== Running one-time migrations ==="
# Wait for app container to be healthy (depends on mongodb being healthy already).
for i in {1..30}; do
  if docker inspect --format='{{.State.Health.Status}}' pocketquant-app 2>/dev/null | grep -q healthy; then
    break
  fi
  sleep 2
done

# Purge MongoDB data for legacy strategies (ma_crossover, hit_and_run) deleted
# in the hitnrun2 migration. Idempotent: no-op once collections are clean.
docker compose -f docker/compose.prod.yml --env-file docker/.env exec -T app \
  python -m scripts.one_time_purge_legacy_strategies || true

echo "=== Cleaning old images ==="
docker image prune -f

echo "=== Done ==="
docker ps --format "table {{.Names}}\t{{.Status}}" | grep pocketquant || true
