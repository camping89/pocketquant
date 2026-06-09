#!/usr/bin/env bash
set -euo pipefail

# PocketQuant VPS-side deploy script (runs ON the VPS).
# Invoked over SSH by the CI/CD deploy job in .github/workflows/cicd.yml.
#
# Manual invocation (debug / emergency rollback):
#   ssh vps "cd /opt/pocketquant && bash deploy/vps/10-deploy.sh"
#   ssh vps "cd /opt/pocketquant && IMAGE_TAG=sha-<short> bash deploy/vps/10-deploy.sh"

# Resolve script dir BEFORE cd (other helpers live alongside this script).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# cd to deploy/ (one level up from vps/) so .env + compose.prod.yml resolve relatively
cd "$SCRIPT_DIR/.."

# ─── Setup (runs only if needed) ──────────────────────────────

if ! command -v docker &>/dev/null; then
  echo "=== Installing Docker ==="
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"
  echo "Docker installed. Log out and back in, then re-run this script."
  exit 0
fi

if [ ! -f .env ]; then
  echo "ERROR: .env not found. CI/CD writes it from pocketquant-config/vps/default/.env; for manual deploys, place that file's contents at deploy/.env"
  exit 1
fi

# ─── Load env ─────────────────────────────────────────────────

set -a && source .env && set +a

# An empty REDIS_PASSWORD makes `redis-server --requirepass` a no-op (auth
# silently disabled) while the healthcheck `-a ""` still returns PONG — the
# exposure would reopen with nothing flagging it. Fail closed instead.
if [ -z "${REDIS_PASSWORD:-}" ]; then
  echo "ERROR: REDIS_PASSWORD is empty/unset in .env — refusing to deploy (would disable Redis auth)"
  exit 1
fi

# ─── Deploy ───────────────────────────────────────────────────

echo "=== Pulling latest images ==="
docker pull "${DOCKERHUB_USERNAME}/pocketquant:${IMAGE_TAG:-latest}"
docker pull "${DOCKERHUB_USERNAME}/pocketquant-web:${IMAGE_TAG:-latest}"

echo "=== Starting services ==="
docker compose -f compose.prod.yml --env-file .env up -d --remove-orphans

# Wait for both processes. app (headless runtime) migrates the schema in its
# lifespan before becoming healthy; bff depends_on app healthy, so it only
# starts accepting traffic after migration. Probe both — a healthy app with a
# dead bff means the FE has no API upstream.
wait_health() {
  local container="$1" port="$2" timeout="$3"
  echo "=== Waiting for $container health (timeout ${timeout}s) ==="
  local deadline=$(( $(date +%s) + timeout ))
  until docker exec "$container" curl -fsS --max-time 2 "http://localhost:${port}/health" >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
      echo "ERROR: $container did not become healthy within ${timeout}s"
      echo "--- last 30 log lines ---"
      docker logs "$container" --tail 30 2>&1 || true
      echo "--- container status ---"
      docker ps --format "table {{.Names}}\t{{.Status}}" | grep pocketquant || true
      exit 1
    fi
    sleep 2
  done
  echo "$container is healthy."
}

wait_health pocketquant-app 41920 60
wait_health pocketquant-bff 41921 30

echo "=== Cleaning old images ==="
docker image prune -f

echo "=== Done ==="
docker ps --format "table {{.Names}}\t{{.Status}}" | grep pocketquant || true
