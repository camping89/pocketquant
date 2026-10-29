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

# One deploy at a time: CI and a manual re-roll must never scale the same service together.
exec 9>/opt/pocketquant/deploy.lock
flock -n 9 || { echo "ERROR: another deploy holds /opt/pocketquant/deploy.lock"; exit 1; }

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

IMG="${DOCKERHUB_USERNAME}/pocketquant:${IMAGE_TAG:-latest}"
LOG_DIR=/opt/pocketquant/logs
mkdir -p "$LOG_DIR"
dc() { docker compose -f compose.prod.yml --env-file .env "$@"; }

echo "=== Pulling images ==="
docker pull "$IMG"
docker pull "${DOCKERHUB_USERNAME}/pocketquant-web:${IMAGE_TAG:-latest}"

# An image without leases under this compose would run three unleased full
# runtimes. To go back that far, revert compose.prod.yml and deploy/vps together.
if ! docker run --rm "$IMG" python -c "import pocketquant.core.infra.persistence.repositories.lease_repository"; then
  echo "ERROR: $IMG has no lease module; refusing to run it as api/worker/trader"
  exit 1
fi

fail_tail() {  # fail_tail <service> <container>: the CI log is public, so it gets only the path
  local f="$LOG_DIR/failed-$1-$(date -u +%Y%m%dT%H%M%SZ).log"
  docker logs --tail 50 "$2" > "$f" 2>&1 || true
  echo "ERROR: $1 log tail saved on the VPS: $f"
}

wait_healthy() {  # wait_healthy <service> <container> <timeout-s>
  local svc=$1 c=$2 t=$3 i
  for i in $(seq "$t"); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$c" 2>/dev/null)" = healthy ] && return 0
    sleep 1
  done
  echo "ERROR: $svc not healthy after ${t}s"; fail_tail "$svc" "$c"
  return 1
}

wait_lease() {  # wait_lease <service> <timeout-s>: the running copy holds its lease
  local svc=$1 t=$2 c h i
  c=$(dc ps -q "$svc" | head -1)
  for i in $(seq "$t"); do
    h=$(docker exec "$c" curl -fsS --max-time 2 http://localhost:41921/health 2>/dev/null || true)
    case "$h" in *'"lease":"held"'*) echo "$svc holds its lease."; return 0 ;; esac
    sleep 1
  done
  echo "ERROR: $svc does not hold its lease after ${t}s"; fail_tail "$svc" "$c"
  return 1
}

save_logs() {  # save_logs <label> <container>: run after docker stop, before docker rm
  docker logs "$2" 2>&1 | gzip > "$LOG_DIR/$1-$(docker inspect -f '{{.Id}}' "$2" | cut -c1-12)-$(date -u +%Y%m%dT%H%M%SZ).log.gz"
}

roll() {  # roll <service> <health-timeout-s>: start a second copy, wait healthy, stop the old one
  local svc=$1 t=$2 old new n
  docker ps -aq --filter label=com.docker.compose.project=pocketquant-prod \
    --filter label=com.docker.compose.service="$svc" \
    --filter status=exited --filter status=created | xargs -r docker rm
  n=$(dc ps -q "$svc" | wc -l)
  if [ "$n" -gt 1 ]; then
    echo "ERROR: $n running copies of $svc; a roll needs exactly one. Stop the extra copy by hand first."
    exit 1
  fi
  if [ "$n" -eq 0 ]; then   # nothing to hand over from
    dc up -d --no-deps "$svc"
    wait_healthy "$svc" "$(dc ps -q "$svc")" "$t"
    return
  fi
  old=$(dc ps -q "$svc")
  dc up -d --no-deps --no-recreate --scale "$svc=2" "$svc"
  new=$(dc ps -q "$svc" | grep -vxF "$old")
  if ! wait_healthy "$svc" "$new" "$t"; then docker stop "$new"; docker rm "$new"; return 1; fi
  if [ "$svc" = api ]; then
    # Docker DNS stops naming the old api at once; nginx re-resolves within 5 s.
    docker network disconnect pocketquant-prod_backend "$old"
    sleep 6
  fi
  docker stop "$old"        # honours stop_grace_period; the trader drains here
  save_logs "$svc" "$old"   # after stop, so the drain and release lines are kept
  docker rm "$old"
}

oom_ok() {  # the only machine stop: a new OOM since the recorded baseline
  local r
  r=$(bash /opt/pocketquant/bin/oom-check.sh $(cat /opt/pocketquant/bin/oom-baseline 2>/dev/null) 2>&1 || true)
  [ "$r" = OOM_OK ] && return 0
  echo "ERROR: ${r:-no answer from oom-check.sh}"
  return 1
}

if docker ps -a --format '{{.Names}}' | grep -qx pocketquant-app; then
  # One-time cutover from the single-backend compose: the new services wait in
  # standby while the old container holds both leases, then take them over.
  echo "=== One-time cutover: app -> api, worker, trader ==="
  dc up -d --no-deps api worker trader
  wait_healthy api "$(dc ps -q api)" 120
  wait_healthy worker "$(dc ps -q worker)" 120
  wait_healthy trader "$(dc ps -q trader)" 240
  if ! oom_ok; then         # four runtimes overlap now; the old app still holds both leases
    echo "ERROR: OOM stop before the cutover; removing the new services, the old app keeps trading"
    dc rm -sf api worker trader
    exit 1
  fi
  dc up -d --no-deps web      # new nginx proxies api
  docker stop pocketquant-app # 180 s grace: drains the trader at a boundary, releases both leases
  save_logs app pocketquant-app
  docker rm pocketquant-app
  wait_lease worker 60
  wait_lease trader 60
else
  echo "=== Rolling api, worker, trader ==="
  roll api 120
  roll worker 120
  wait_lease worker 60
  roll trader 240
  wait_lease trader 60
fi

dc up -d --no-deps web cloudflared
dc up -d --remove-orphans

echo "=== Cleaning old images and logs ==="
docker image prune -f
find "$LOG_DIR" -maxdepth 1 \( -name '*.log.gz' -o -name 'failed-*.log' \) -mtime +30 -delete

echo "=== Done ==="
docker ps --format "table {{.Names}}\t{{.Status}}" | grep pocketquant || true
