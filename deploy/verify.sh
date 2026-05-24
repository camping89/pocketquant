#!/usr/bin/env bash
set -uo pipefail

# PocketQuant VPS Deployment Verification
# Runs post-deploy checks and outputs a markdown report.
#
# Usage:
#   ssh vps "cd /opt/pocketquant && bash deploy/verify.sh"
#   # Report saved to ./reports/verify-<ISO-datetime>.md

cd "$(dirname "$0")"

REPORT_DIR="./reports"
mkdir -p "$REPORT_DIR"
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%S")
REPORT="$REPORT_DIR/verify-$TIMESTAMP.md"

PASS="PASS"
FAIL="FAIL"
WARN="WARN"
total=0
passed=0
failed=0
warned=0

# ─── Helpers ────────────────────────────────────────────────

check() {
  local name="$1" status="$2" detail="$3"
  total=$((total + 1))
  case "$status" in
    "$PASS") passed=$((passed + 1)); icon="+" ;;
    "$FAIL") failed=$((failed + 1)); icon="x" ;;
    "$WARN") warned=$((warned + 1)); icon="!" ;;
  esac
  echo "| $name | $status | $detail |" >> "$REPORT"
  echo "[$icon] $name: $status - $detail"
}

container_health() {
  docker inspect --format='{{.State.Health.Status}}' "$1" 2>/dev/null || echo "not_found"
}

container_running() {
  docker inspect --format='{{.State.Running}}' "$1" 2>/dev/null || echo "false"
}

# ─── Report header ──────────────────────────────────────────

cat > "$REPORT" <<EOF
# PocketQuant Verification Report

- **Date:** $(date -u +"%Y-%m-%dT%H:%M:%SZ")
- **Host:** $(hostname)
- **Kernel:** $(uname -r)

## Results

| Check | Status | Detail |
|-------|--------|--------|
EOF

# ─── 1. Container running checks ───────────────────────────

CONTAINERS="pocketquant-app pocketquant-mongodb pocketquant-redis pocketquant-portainer"
for c in $CONTAINERS; do
  running=$(container_running "$c")
  if [ "$running" = "true" ]; then
    check "$c running" "$PASS" "container is up"
  else
    check "$c running" "$FAIL" "container not running"
  fi
done

# ─── 2. Docker health status ───────────────────────────────

HEALTH_CONTAINERS="pocketquant-app pocketquant-mongodb pocketquant-redis"
for c in $HEALTH_CONTAINERS; do
  health=$(container_health "$c")
  if [ "$health" = "healthy" ]; then
    check "$c health" "$PASS" "healthy"
  elif [ "$health" = "starting" ]; then
    check "$c health" "$WARN" "still starting"
  else
    check "$c health" "$FAIL" "$health"
  fi
done

# ─── 3. App HTTP healthcheck ───────────────────────────────

health_response=$(docker exec pocketquant-app curl -sf http://localhost:41920/health 2>/dev/null || echo "")
if [ -n "$health_response" ]; then
  app_status=$(echo "$health_response" | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)
  if [ "$app_status" = "healthy" ]; then
    db_latency=$(echo "$health_response" | grep -o '"database":{[^}]*}' | grep -o '"latency_ms":[0-9.]*' | cut -d: -f2)
    redis_latency=$(echo "$health_response" | grep -o '"redis":{[^}]*}' | grep -o '"latency_ms":[0-9.]*' | cut -d: -f2)
    check "API /health" "$PASS" "db=${db_latency:-?}ms redis=${redis_latency:-?}ms"
  else
    check "API /health" "$FAIL" "status=$app_status"
  fi
else
  check "API /health" "$FAIL" "no response from app"
fi

# ─── 4. MongoDB direct check ───────────────────────────────

mongo_ok=$(docker exec pocketquant-mongodb mongosh --quiet --eval "db.adminCommand('ping').ok" 2>/dev/null || echo "0")
if [ "$mongo_ok" = "1" ]; then
  check "MongoDB ping" "$PASS" "responds to ping"
else
  check "MongoDB ping" "$FAIL" "ping failed"
fi

# ─── 5. Redis direct check ─────────────────────────────────

redis_ok=$(docker exec pocketquant-redis redis-cli PING 2>/dev/null || echo "")
if [ "$redis_ok" = "PONG" ]; then
  check "Redis ping" "$PASS" "PONG"
else
  check "Redis ping" "$FAIL" "no PONG"
fi

# ─── 6. Disk space ─────────────────────────────────────────

disk_pct=$(df / --output=pcent | tail -1 | tr -d ' %')
if [ "$disk_pct" -lt 80 ]; then
  check "Disk usage" "$PASS" "${disk_pct}% used"
elif [ "$disk_pct" -lt 90 ]; then
  check "Disk usage" "$WARN" "${disk_pct}% used"
else
  check "Disk usage" "$FAIL" "${disk_pct}% used — critical"
fi

# ─── 7. Memory ─────────────────────────────────────────────

mem_total=$(free -m | awk '/Mem:/{print $2}')
mem_used=$(free -m | awk '/Mem:/{print $3}')
mem_pct=$((mem_used * 100 / mem_total))
if [ "$mem_pct" -lt 80 ]; then
  check "Memory" "$PASS" "${mem_used}MB/${mem_total}MB (${mem_pct}%)"
elif [ "$mem_pct" -lt 90 ]; then
  check "Memory" "$WARN" "${mem_used}MB/${mem_total}MB (${mem_pct}%)"
else
  check "Memory" "$FAIL" "${mem_used}MB/${mem_total}MB (${mem_pct}%) — critical"
fi

# ─── 8. Port listening ─────────────────────────────────────

if command -v ss &>/dev/null; then
  source .env 2>/dev/null || true
  app_port="${APP_PORT:-41920}"
  if ss -tlnp | grep -q ":${app_port} "; then
    check "Port $app_port" "$PASS" "listening"
  else
    check "Port $app_port" "$FAIL" "not listening"
  fi
else
  check "Port check" "$WARN" "ss not available"
fi

# ─── 9. Image tag ──────────────────────────────────────────

current_image=$(docker inspect --format='{{.Config.Image}}' pocketquant-app 2>/dev/null || echo "unknown")
check "Image" "$PASS" "$current_image"

# ─── 10. Recent errors in app logs ─────────────────────────

error_count=$(docker logs pocketquant-app --tail 100 2>&1 | grep -ci '"levelname":"ERROR"\|"level":"error"\|Traceback' || true)
if [ "$error_count" -eq 0 ]; then
  check "App logs (last 100)" "$PASS" "no errors"
else
  check "App logs (last 100)" "$WARN" "${error_count} error(s) found"
fi

# ─── Summary ────────────────────────────────────────────────

if [ "$failed" -gt 0 ]; then
  verdict="UNHEALTHY"
elif [ "$warned" -gt 0 ]; then
  verdict="DEGRADED"
else
  verdict="HEALTHY"
fi

cat >> "$REPORT" <<EOF

## Summary

- **Verdict:** $verdict
- **Passed:** $passed / $total
- **Warnings:** $warned
- **Failures:** $failed

## Container Details

\`\`\`
$(docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "pocketquant|NAMES")
\`\`\`
EOF

# Append recent errors if any
if [ "$error_count" -gt 0 ]; then
  cat >> "$REPORT" <<EOF

## Recent Errors (last 100 log lines)

\`\`\`
$(docker logs pocketquant-app --tail 100 2>&1 | grep -i '"levelname":"ERROR"\|"level":"error"\|Traceback' | tail -10)
\`\`\`
EOF
fi

echo ""
echo "=== Verdict: $verdict ($passed/$total passed, $warned warnings, $failed failures) ==="
echo "Report: $REPORT"
