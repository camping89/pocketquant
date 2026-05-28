#!/usr/bin/env bash
set -euo pipefail

# PocketQuant VPS-side deploy script (runs ON the VPS).
# Invoked over SSH by the CI/CD deploy job in .github/workflows/cicd.yml.
#
# Manual invocation (debug / emergency rollback):
#   ssh vps "cd /opt/pocketquant && bash deploy/vps/deploy.sh"
#   ssh vps "cd /opt/pocketquant && IMAGE_TAG=sha-<short> bash deploy/vps/deploy.sh"

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
  echo "ERROR: .env not found. Copy .env.example, fill prod values, place at deploy/.env"
  exit 1
fi

# ─── Validate required env vars ───────────────────────────────

set -a && source .env && set +a

REQUIRED_VARS_FILE="$SCRIPT_DIR/required-env-vars.txt"
if [ ! -f "$REQUIRED_VARS_FILE" ]; then
  echo "ERROR: $REQUIRED_VARS_FILE not found"
  exit 1
fi

missing=()
while IFS= read -r var; do
  [[ -z "$var" || "$var" =~ ^[[:space:]]*# ]] && continue
  if [ -z "${!var:-}" ]; then
    missing+=("$var")
  fi
done < "$REQUIRED_VARS_FILE"

if [ ${#missing[@]} -gt 0 ]; then
  echo "ERROR: missing required vars in deploy/.env:"
  printf '  - %s\n' "${missing[@]}"
  echo "Source of truth: deploy/vps/required-env-vars.txt"
  exit 1
fi

# ─── Deploy ───────────────────────────────────────────────────

echo "=== Pulling latest images ==="
docker pull "${DOCKERHUB_USERNAME}/pocketquant:${IMAGE_TAG:-latest}"
docker pull "${DOCKERHUB_USERNAME}/pocketquant-web:${IMAGE_TAG:-latest}"

echo "=== Starting services ==="
docker compose -f compose.prod.yml --env-file .env up -d --remove-orphans

echo "=== Waiting for app health (timeout 60s) ==="
deadline=$(( $(date +%s) + 60 ))
until docker exec pocketquant-app curl -fsS --max-time 2 http://localhost:41920/health >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "ERROR: app did not become healthy within 60s"
    echo "--- last 30 log lines ---"
    docker logs pocketquant-app --tail 30 2>&1 || true
    echo "--- container status ---"
    docker ps --format "table {{.Names}}\t{{.Status}}" | grep pocketquant || true
    exit 1
  fi
  sleep 2
done
echo "App is healthy."

echo "=== Cleaning old images ==="
docker image prune -f

echo "=== Done ==="
docker ps --format "table {{.Names}}\t{{.Status}}" | grep pocketquant || true
