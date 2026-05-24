#!/usr/bin/env bash
set -euo pipefail

# PocketQuant VPS Deploy Script
# Handles first-time setup + subsequent deploys in one script.
#
# First time:
#   scp deploy/deploy.sh deploy/compose.prod.yml deploy/.env to VPS:/opt/pocketquant/deploy/
#   ssh vps "cd /opt/pocketquant && bash deploy/deploy.sh"
#
# Update:
#   ssh vps "cd /opt/pocketquant && bash deploy/deploy.sh"

cd "$(dirname "$0")"

# ─── Setup (runs only if needed) ──────────────────────────────

if ! command -v docker &>/dev/null; then
  echo "=== Installing Docker ==="
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"
  echo "Docker installed. Log out and back in, then re-run this script."
  exit 0
fi

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Copy .env.example, fill prod values, place at deploy/.env"
  exit 1
fi

# ─── Validate required env vars ───────────────────────────────

set -a && source .env && set +a

REQUIRED_VARS="DOCKERHUB_USERNAME MONGO_PASSWORD APP_PORT MONGO_PORT REDIS_PORT PORTAINER_PORT"
for var in $REQUIRED_VARS; do
  if [ -z "${!var:-}" ]; then
    echo "ERROR: $var not set in deploy/.env"
    exit 1
  fi
done

# ─── Deploy ───────────────────────────────────────────────────

echo "=== Pulling latest images ==="
docker pull "${DOCKERHUB_USERNAME}/pocketquant:${IMAGE_TAG:-latest}"
docker pull "${DOCKERHUB_USERNAME}/pocketquant-web:${IMAGE_TAG:-latest}"

echo "=== Starting services ==="
docker compose -f compose.prod.yml --env-file .env up -d --remove-orphans

echo "=== Cleaning old images ==="
docker image prune -f

echo "=== Done ==="
docker ps --format "table {{.Names}}\t{{.Status}}" | grep pocketquant || true
