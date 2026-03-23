#!/usr/bin/env bash
set -euo pipefail

# PocketQuant VPS Deploy Script
# Usage: scp to VPS, then: bash deploy.sh
# Requires: docker/.env with GITHUB_USER, GHCR_TOKEN, MONGO_PASSWORD set

cd "$(dirname "$0")"

set -a && source docker/.env && set +a

echo "=== Logging in to GHCR ==="
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GITHUB_USER" --password-stdin

echo "=== Pulling latest image ==="
docker pull "ghcr.io/${GITHUB_USER}/pocketquant:${IMAGE_TAG:-latest}"

echo "=== Starting services ==="
docker compose -f docker/compose.prod.yml --env-file docker/.env up -d --remove-orphans

echo "=== Cleaning old images ==="
docker image prune -f

echo "=== Done ==="
docker ps --format "table {{.Names}}\t{{.Status}}" | grep pocketquant || true
