---
phase: 8
title: "Topology and cutover to api/worker/trader (Deploy B)"
status: pending
priority: P1
effort: "1d code + Docker Desktop rehearsal + 1 deploy (D-5)"
dependencies: [7]
---

# Phase 08: Topology and cutover to `api`/`worker`/`trader` (Deploy B)

## Goal

Replace the single `app` service with `api`, `worker` and `trader` from one image, make nginx re-resolve `api`, and give `10-deploy.sh` a locked rolling deploy (image guard, log capture, lease wait) plus a one-time cutover branch. The cutover starts the three services in standby beside the Deploy A `app`, re-checks the OOM stop, recreates `web`, then stops `app`, which drains the trader at a 1m boundary and releases both leases to the new containers. Install the one VPS helper set that Phases 08-11 reuse. Rehearse it on Docker Desktop first (including a drain retry and the OOM abort), then run it in prod as D-5 and record row 0 of the handover log with the D25 measurements (record only, D31).

## Context (verified on `develop` @ 453e8e90)

- `deploy/compose.prod.yml`: `name: pocketquant-prod` `:1` (so the backend network is `pocketquant-prod_backend`, declared `:167`); `web` `:4-25` (`container_name: pocketquant-web` `:6`, `depends_on: app` `:12-14`, healthcheck uses `curl` `:16`); `app` `:53-91` (`container_name: pocketquant-app` `:60`); Vietnamese comments `:113-114` (this phase removes them); networks comment `:164`. Phase 07 set `app` `APP_ROLES: "api,worker,trader"`, `stop_grace_period: 180s`, `start_period: 180s` and `--timeout-graceful-shutdown 10`; the `app_roles` default is `api`, so every service names its roles.
- `web/nginx.conf:24-26` has a static `proxy_pass http://app:41921;`; a static `proxy_pass` resolves once and keeps the old IP after a swap (researcher report Q4). The web image is `nginx:1.27-alpine` (`web/Dockerfile:17`).
- `deploy/vps/10-deploy.sh`: `cd` into `deploy/` `:12-14`, pulls `:46-47`, `up -d --remove-orphans` `:50`, `wait_health` `:54-70` (Phase 07 writes its tail to a file), `wait_health pocketquant-app 41921 240` `:72`, prune `:75`; the "Deploy" section starts at `:43`. CI rsyncs `compose.prod.yml`, `.env` and `deploy/vps/` into `/opt/pocketquant/deploy/` and runs `cd /opt/pocketquant && bash deploy/vps/10-deploy.sh`, then `11-verify.sh` (`.github/workflows/cicd.yml:225-245`); the Actions log is public. So on the VPS the compose project lives in `/opt/pocketquant/deploy` and a committed `deploy/vps/leases.sh` lands at `/opt/pocketquant/deploy/vps/leases.sh`.
<!-- Red team 2026-10-28: #7 -->
- CI concurrency is `cancel-in-progress: true` for every ref (`.github/workflows/cicd.yml:13-15`): a newer master push cancels a deploy mid-roll. Manual re-rolls run outside CI. The local Git Bash has no `flock` and no `setsid` (checked 2026-10-28), so the rehearsal disables the lock line and Task 8.3 tests the lock in an `ubuntu:24.04` container.
<!-- Red team 2026-10-28: #9 -->
- `deploy/vps/11-verify.sh` names `pocketquant-app` at lines `67,79,93,110,120,172,177,188,228,240`; it `cd`s to `deploy/` at `:12` and sources `.env` at `:13`; its error patterns at `:177,187,228` match JSON logs only (`"levelname":"ERROR"`), while prod logs are console lines whose level token reads `[error` after ANSI stripping; its memory check FAILs at 90 % (`:157-168`), which D31 makes a recorded value, not a stop.
- Rolling facts (researcher report): `--scale svc=2 --no-recreate` adds one container from the new config; remove exited containers first; never scale down with `--no-recreate` (it keeps the old one); `docker stop <id>` honours the compose `stop_grace_period`; uvicorn binds the port only after lifespan startup, so a healthy trader is a warm standby (Phase 07).
<!-- Red team 2026-10-28: #1 #4 #5 -->
- Prod logs are console-rendered with ANSI colours (`../pocketquant-config/vps/default/.env:27`, `src/pocketquant/core/common/logging/setup.py:71`); every log grep strips them with `sed 's/\x1b\[[0-9;]*m//g'`. Phase 07 log events: `trader.standby warmup_s=`, `lease.waiting`, `lease.acquired`, `lease.takeover_failed`, `trader.takeover handover_gap_ms=` (right after the acquire), `trader.takeover_complete takeover_ms=`, `trader.drain_retry boundary= inflight=`, `trader.drain_timeout`, `trader.lease_released inflight= boundary= offset_s=`, `worker.lease_released`, `lease.lost`, `strategy.signal_discarded reason=lease|drain`; `/health` adds `"role"`, `"lease"` (`held` only after the takeover finished, else `standby`/`none`) and `"lease_renewed_age_s"`. Lease owners are `hostname:pid`, and a container's hostname is its short id.
<!-- Red team 2026-10-28: #11 -->
- Phases 09-11 append rows to `reports/handover-log.md` under the header `| # | UTC start | kind | stamp | inflight | offset_s | drain_timeout | handover_gap_ms | takeover_ms | gap_skips | discarded | probe | leases | verify | verdict |`, reuse the helper set this phase installs in `/opt/pocketquant/bin/`, and create no other copies. Phase 09 deletes the cutover branch and checks `grep -oE "roll (api|worker|trader) [0-9]+" deploy/vps/10-deploy.sh` gives 3 lines.
<!-- Red team 2026-10-28: #2 -->
- OOM rule (D31, plan.md Conventions): `reports/machine-baseline.md` holds one line `oom_baseline=<boot_id> <oom_kill>`. A reading stops the plan when the boot id differs, the `oom_kill` counter in `/proc/vmstat` is higher, or `State.OOMKilled` is `true` for a container of the compose project; `oom-check.sh` (Task 8.4) is that check. Memory, swap, PSI, load and lag are recorded. `web` is recreated on this image deploy with a few seconds of SPA gap (D27); its probe is recorded only.

## Entry gate

Run from `D:/w/_me/algotrading/pocketquant`:

1. `git status --porcelain -- src web deploy tests scripts docs` prints nothing.
2. `grep -c "^Result: PASS$" plans/261028-0652-exness-only-parallel-runtime/reports/deploy-a-roles-and-leases.md` prints `1`.
3. `git fetch origin -q && git cat-file -e origin/master:src/pocketquant/core/infra/persistence/repositories/lease_repository.py && echo deploy-a-on-master` prints `deploy-a-on-master`.
<!-- Red team 2026-10-28: #2 -->
4. `grep -c "^oom_baseline=" plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md` prints `1`.
5. `docker ps >/dev/null 2>&1 && echo docker-ok` prints `docker-ok` (else start `"/c/Program Files/Docker/Docker/Docker Desktop.exe"` in the background, retry once after 10 s).
<!-- Red team 2026-10-28: #6 #7 -->
6. `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key; HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'docker compose version --short; docker version -f "{{.Server.Version}}"; docker ps --format "{{.Names}}" | grep -cx pocketquant-app; docker ps -aq --filter label=pq-probe=1 | wc -l' | tee .cache/vps-versions.txt` prints a Compose version whose major number is `>= 2`, an Engine version, `1`, then `0` (no probe container from Phase 07 can win a lease at the cutover). The versions stay in the gitignored `.cache/`; the public repo gets none.

On any miss: edit nothing, spawn no `kongming`, leave the phase pending, run `rm -f .cache/ssh/vps_key`, and end with exactly:
```
Status: BLOCKED
NOT_YET: <which gate line missed>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261028-0652-exness-only-parallel-runtime --from 08 after <UTC time>
```
**Resume rule.** On a resumed run, run each task's Verify first; a task whose Verify already passes is done and is skipped. Task 8.5 is done when `plans/261028-0652-exness-only-parallel-runtime/reports/cutover-rehearsal.md` holds `Rehearsal: PASS` (its own Verify reads rehearsal containers that its step 10 removes). Every `NOT_YET` exit of this phase (Task 8.7 steps 1-3) happens before the `develop:master` push, so `pocketquant-app` still runs and gate line 6 holds on a resume.

## Files to create/modify

<!-- Red team 2026-10-28: #7 #11 -->
Modify: `deploy/compose.prod.yml`, `web/nginx.conf`, `deploy/vps/10-deploy.sh`, `deploy/vps/11-verify.sh`, `.github/workflows/cicd.yml`.
Create: `deploy/vps/leases.sh`, `plans/261028-0652-exness-only-parallel-runtime/reports/cutover-rehearsal.md`, `plans/261028-0652-exness-only-parallel-runtime/reports/handover-log.md`.
Local scratch (gitignored, `.gitignore:42`): `.cache/vps-bin/` (the helper sources), `.cache/rehearsal/`, `.cache/vps-versions.txt`. VPS only: `/opt/pocketquant/bin/` (the helper set), `/opt/pocketquant/deploy.lock`, `/opt/pocketquant/logs/` (saved container logs, failed tails), `/opt/pocketquant/logs/cutover/`.

## Tasks

### Task 8.1 — Three services from one image

**Goal:** compose runs `api`, `worker` and `trader` with their roles, rate fractions and grace periods; only the trader may trade live; `web` waits for `api`.
**Target files and symbols:** `deploy/compose.prod.yml` (`app` service, `web.depends_on`, comments `:10-11`, `:53-57`, `:113-114`, `:164`).
**Steps:**
1. Under `name: pocketquant-prod` add the anchor (keys and values copied from today's `app`):
   ```yaml
   # Shared by api, worker and trader: one image, settings from .env (materialized
   # from pocketquant-config/vps/default/.env each deploy), backend network only.
   x-backend: &backend
     image: ${DOCKERHUB_USERNAME}/pocketquant:${IMAGE_TAG:-latest}
     restart: unless-stopped
     env_file:
       - .env
     networks: [backend]
     depends_on:
       mongodb:
         condition: service_healthy
       redis:
         condition: service_healthy
     logging:
       driver: json-file
       options:
         max-size: "10m"
         max-file: "3"
   ```
2. Replace the whole `app` service (`:53-91`) with three services, each `<<: *backend`, no `container_name`, no `ports`, comment above them: "api, worker and trader run one image with different APP_ROLES. No container_name: a deploy starts a second copy beside the old one (deploy/vps/10-deploy.sh roll). TZ is set after env_file so it wins; the app refuses a non-UTC zone. Only the trader may trade live: api and worker pin EXNESS_LIVE_TRADING off."
<!-- Red team 2026-10-28: #5 -->
   - `api`: `command: ["uvicorn", "pocketquant.app.main:app", "--host", "0.0.0.0", "--port", "41921", "--forwarded-allow-ips", "172.16.0.0/12,192.168.0.0/16", "--timeout-graceful-shutdown", "10"]`; `environment: {TZ: "UTC", APP_ROLES: "api", EXNESS_RATE_FRACTION: "0.05", EXNESS_LIVE_TRADING: "false"}` (block style); `stop_grace_period: 30s`.
   - `worker`: `command: ["uvicorn", "pocketquant.app.main:app", "--host", "0.0.0.0", "--port", "41921"]`; `APP_ROLES: "worker"`, `EXNESS_RATE_FRACTION: "0.3"`, `EXNESS_LIVE_TRADING: "false"`; `stop_grace_period: 120s` with comment "scheduler pause, running jobs finish (up to 90 s), worker lease release".
   - `trader`: same command as `worker`; `APP_ROLES: "trader"`, `EXNESS_RATE_FRACTION: "0.6"` (live trading follows `.env`); `stop_grace_period: 180s` with comment "drain at the next 1m boundary and bounded stop (up to 160 s), then release the trader lease".
   - Each healthcheck: `test: ["CMD", "curl", "-f", "http://localhost:41921/health"]`, `interval: 10s`, `timeout: 10s`, `retries: 3`; `start_period: 30s` for `api` and `worker`, `start_period: 180s` for `trader` with comment "healthy = warm standby".
3. `web.depends_on`: `api: {condition: service_healthy}` (block style); comment `:10-11` → "nginx proxies /api to api. Wait for api readiness so the SPA never hits a dead upstream on first paint."
4. `:113-114` → "# Chatty on stdout (a connection line per healthcheck every 10 s). Capped because a stateful service is not recreated on deploy, so its json.log would grow without bound."
5. `:164` → "# edge: cloudflared and web only; backend: web, api, worker, trader and the data stores."
**Success criteria:** the parsed file matches every value above; no Vietnamese left.
**Verify:** `uv run python -c "import yaml; s=yaml.safe_load(open('deploy/compose.prod.yml', encoding='utf-8'))['services']; r=[s[k] for k in ('api','worker','trader')]; assert sorted(s)==['api','cloudflared','mongodb','portainer','redis','trader','web','worker']; assert all('container_name' not in v and 'ports' not in v for v in r); assert [v['environment']['APP_ROLES'] for v in r]==['api','worker','trader']; assert [v['environment']['EXNESS_RATE_FRACTION'] for v in r]==['0.05','0.3','0.6']; assert [v['environment'].get('EXNESS_LIVE_TRADING') for v in r]==['false','false',None]; assert [v['stop_grace_period'] for v in r]==['30s','120s','180s']; assert [v['healthcheck']['interval'] for v in r]==['10s']*3; assert [v['healthcheck']['start_period'] for v in r]==['30s','30s','180s']; assert r[0]['command'][-2:]==['--timeout-graceful-shutdown','10']; assert all(v['image'].endswith('/pocketquant:\${IMAGE_TAG:-latest}') and v['restart']=='unless-stopped' for v in r); assert list(s['web']['depends_on'])==['api']; print('ok')"; grep -c "từ\|Không" deploy/compose.prod.yml` → `ok` then `0`.

### Task 8.2 — nginx re-resolves `api`

**Goal:** after a roll, nginx reaches the new `api` within seconds and retries a refused or slow connect.
**Target files and symbols:** `web/nginx.conf:24-26`.
**Steps:**
1. Inside `server`, after `index index.html;`, add:
   ```nginx
       # Docker DNS. A rolled api gets a new IP; re-resolve every 5 s.
       resolver 127.0.0.11 valid=5s ipv6=off;
   ```
<!-- Red team 2026-10-28: #7 -->
2. Replace `:24-26` with:
   ```nginx
       # API reverse proxy -> api. A variable proxy_pass re-resolves through the
       # resolver; any static proxy_pass to api would pin one IP. A 1 s connect
       # timeout lets a request to a just-removed api move to the other copy.
       location /api/ {
           set $api_upstream http://api:41921;
           proxy_pass $api_upstream;
           proxy_connect_timeout 1s;
           proxy_next_upstream error timeout;
   ```
   Keep every other line of the block unchanged; add no URI part to the variable.
**Success criteria:** config tests clean in the web base image; no static `proxy_pass`.
**Verify:** `MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W)/web/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.27-alpine nginx -t 2>&1 | grep -c "test is successful"; grep -c "proxy_pass http://" web/nginx.conf; grep -c "resolver 127.0.0.11 valid=5s ipv6=off;" web/nginx.conf; grep -c "proxy_connect_timeout 1s;" web/nginx.conf` → `1`, `0`, `1`, `1`.

### Task 8.3 — Locked rolling deploy, image guard, log capture, one-time cutover

**Goal:** `10-deploy.sh` runs one deploy at a time, rolls each role with no gap, keeps log tails off the public CI log, and runs the one-time cutover while the old `app` container exists, aborting it on an OOM stop; a master deploy is never cancelled mid-roll.
**Target files and symbols:** `deploy/vps/10-deploy.sh:14` and `:43-78` (the "Deploy" section); `.github/workflows/cicd.yml:13-15`.
**Steps:**
<!-- Red team 2026-10-28: #7 -->
1. After `cd "$SCRIPT_DIR/.."` (`:14`) insert (before the Docker install check, so a second run touches nothing):
   ```bash

   # One deploy at a time: CI and a manual re-roll must never scale the same service together.
   exec 9>/opt/pocketquant/deploy.lock
   flock -n 9 || { echo "ERROR: another deploy holds /opt/pocketquant/deploy.lock"; exit 1; }
   ```
2. Replace everything from `# ─── Deploy` to the end with:
   ```bash
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
   ```
   A roll with no running copy starts one (there is nothing to hand over and no second copy to collide with); more than one copy stops the deploy.
3. `.github/workflows/cicd.yml:13-15`: `cancel-in-progress: ${{ github.ref != 'refs/heads/master' }}` with the comment "A master run deploys: cancelling it mid-roll can leave two copies of a service. Other refs still cancel."
**Success criteria:** the script parses; four cutover lines name the old container; three role rolls; one guard; one lock that refuses a second run; no log tail printed to the CI log; master runs are not cancelled.
**Verify:** `bash -n deploy/vps/10-deploy.sh && echo syntax-ok; grep -c "pocketquant-app" deploy/vps/10-deploy.sh; grep -oE "roll (api|worker|trader) [0-9]+" deploy/vps/10-deploy.sh | wc -l; grep -c "lease_repository" deploy/vps/10-deploy.sh; grep -c "^flock -n 9 " deploy/vps/10-deploy.sh; grep -c "docker network disconnect pocketquant-prod_backend" deploy/vps/10-deploy.sh; grep -c "docker logs --tail" deploy/vps/10-deploy.sh; grep -cF "cancel-in-progress: \${{ github.ref != 'refs/heads/master' }}" .github/workflows/cicd.yml; MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W)/deploy/vps:/s:ro" ubuntu:24.04 bash -c 'mkdir -p /opt/pocketquant; exec 8>/opt/pocketquant/deploy.lock; flock 8; bash /s/10-deploy.sh; echo "exit=$?"'` → `syntax-ok`, `4`, `3`, `1`, `1`, `1`, `1` (the one in `fail_tail`, which writes to a file), `1`, then `ERROR: another deploy holds /opt/pocketquant/deploy.lock` and `exit=1`.

### Task 8.4 — `11-verify.sh` follows the roles; the VPS helper set

**Goal:** the post-deploy verify finds the rolled containers by service, counts console-format errors, and checks one copy per role, held leases and lease owners that are the role containers; the one helper set that Phases 08-11 use exists in `.cache/vps-bin/` (installed on the VPS in Task 8.7).
**Target files and symbols:** `deploy/vps/11-verify.sh` lines `13`, `67`, `79`, `93`, `110`, `120`, `126`, `172`, `177`, `187`, `188`, `228`, `240`; new `deploy/vps/leases.sh`; `.cache/vps-bin/{snapshot,sample,probe,oom-check}.sh`.
**Steps:**
<!-- Red team 2026-10-28: #5 #11 -->
1. Create `deploy/vps/leases.sh` (committed so CI ships it and `11-verify.sh` uses the same check the plan uses):
   ```bash
   #!/usr/bin/env bash
   # Lease owners and whether each owner is a running container of its compose service.
   # usage: leases.sh -> worker=<owner> trader=<owner> unexpired=<n> owners_match=<yes|no>
   cd "$(dirname "$(readlink -f "$0")")/.." || exit 1
   dc() { docker compose -f compose.prod.yml --env-file .env "$@"; }
   hosts() { for c in $(dc ps -q "$1"); do docker inspect -f '{{.Config.Hostname}}' "$c"; done; }
   t=$(dc ps -q trader | head -1)
   read -r w tr n < <(docker exec -i "$t" python -c 'from datetime import UTC, datetime
   from pymongo import MongoClient
   from pocketquant.core.config import get_settings
   s = get_settings(); db = MongoClient(str(s.mongodb_url), tz_aware=True)[s.mongodb_database]
   d = {x["name"]: x for x in db.leases.find()}; now = datetime.now(UTC)
   print(d.get("worker", {}).get("owner", "none"), d.get("trader", {}).get("owner", "none"), sum(x["expires_at"] > now for x in d.values()))' 2>/dev/null || echo "none none ?")
   m=yes
   hosts worker | grep -qx "${w%%:*}" || m=no
   hosts trader | grep -qx "${tr%%:*}" || m=no
   echo "worker=$w trader=$tr unexpired=$n owners_match=$m"
   ```
<!-- Red team 2026-10-28: #9 -->
2. After `11-verify.sh:13` insert:
   ```bash
   dc() { docker compose -f compose.prod.yml --env-file .env "$@"; }
   # Role containers have no fixed names: every deploy rolls them.
   role_name() { dc ps --format '{{.Name}}' "$1" 2>/dev/null | head -1; }
   API=$(role_name api); WORKER=$(role_name worker); TRADER=$(role_name trader)
   API=${API:-api-missing}; WORKER=${WORKER:-worker-missing}; TRADER=${TRADER:-trader-missing}
   # Console logs: strip ANSI colours so the level token reads "[error".
   role_logs() { for c in "$API" "$WORKER" "$TRADER"; do docker logs "$c" --tail "$1" 2>&1; done | sed 's/\x1b\[[0-9;]*m//g'; }
   ERROR_PATTERN='\[error\|\[critical\|Traceback'
   ```
3. `:67` → `CONTAINERS="$API $WORKER $TRADER pocketquant-mongodb pocketquant-redis pocketquant-portainer pocketquant-cloudflared"`; `:79` → `HEALTH_CONTAINERS="$API $WORKER $TRADER pocketquant-mongodb pocketquant-redis pocketquant-cloudflared"`; `:93`, `:110`, `:120` → `docker exec "$API" ...`; `:172` → `docker inspect --format='{{.Config.Image}}' "$API"`; `:177` → `error_count=$(role_logs 100 | grep -ci "$ERROR_PATTERN" || true)`; `:187` → append `|\[critical` to `BOOT_PATTERNS`; `:188` → `boot_failures=$(role_logs 200 | grep -cE "$BOOT_PATTERNS" || true)`; `:228` → `$(role_logs 100 | grep -i "$ERROR_PATTERN" | tail -10)`; `:240` → `$(role_logs 200 | grep -E "$BOOT_PATTERNS" | tail -20)`.
4. After the SPA-route loop (`:126`) add section `# ─── 3c. Roles and leases`:
   ```bash
   for svc in api worker trader; do
     n=$(dc ps -q "$svc" 2>/dev/null | wc -l)
     if [ "$n" -eq 1 ]; then check "$svc containers" "$PASS" "1 running"; else check "$svc containers" "$FAIL" "$n running"; fi
   done
   for c in "$WORKER" "$TRADER"; do
     lease=$(docker exec "$c" curl -sf http://localhost:41921/health 2>/dev/null | grep -o '"lease":"[^"]*"' | cut -d'"' -f4)
     if [ "$lease" = "held" ]; then check "$c lease" "$PASS" "held"; else check "$c lease" "$FAIL" "${lease:-no answer}"; fi
   done
   leases=$(bash vps/leases.sh 2>/dev/null)
   case "$leases" in
     *"unexpired=2 owners_match=yes") check "Leases" "$PASS" "$leases" ;;
     *) check "Leases" "$FAIL" "${leases:-no answer}" ;;
   esac
   ```
<!-- Red team 2026-10-28: #2 #7 #11 -->
5. Write the helper sources (gitignored; Task 8.5 rehearses `probe.sh` and Task 8.7 installs all four in `/opt/pocketquant/bin/` beside a `leases.sh` symlink to `/opt/pocketquant/deploy/vps/leases.sh`). Each `start` detaches and returns at once, the background loop ends itself after 1 h, and `stop` ends it:
   ```bash
   mkdir -p .cache/vps-bin
   cat > .cache/vps-bin/snapshot.sh <<'SH'
   #!/usr/bin/env bash
   # usage: snapshot.sh <label> - one line: host memory, load, PSI, OOM counter, boot id (record only)
   read -r used avail < <(free -m | awk '/^Mem:/{print $3, $7}')
   swap=$(free -m | awk '/^Swap:/{print $3}')
   psi=$(awk '/^some/{for(i=2;i<=NF;i++) if($i ~ /^avg10=/){split($i,a,"="); print a[2]}}' /proc/pressure/memory 2>/dev/null)
   echo "label=$1 ts=$(date -u +%FT%TZ) mem_used_mb=$used mem_available_mb=$avail swap_used_mb=$swap load1=$(cut -d' ' -f1 /proc/loadavg) psi_some_avg10=${psi:-na} oom=$(awk '/^oom_kill /{print $2}' /proc/vmstat) boot_id=$(cat /proc/sys/kernel/random/boot_id)"
   SH
   cat > .cache/vps-bin/sample.sh <<'SH'
   #!/usr/bin/env bash
   # usage: sample.sh start|stop <file> - every 2 s while a roll runs: one host line, then one
   # docker stats row per container (record only). start detaches; stop ends the sampler.
   case "$1" in
     start) nohup timeout 3600 bash "$0" run "$2" >/dev/null 2>&1 </dev/null & echo $! > "$2.pid" ;;
     stop) kill "$(cat "$2.pid" 2>/dev/null)" 2>/dev/null; rm -f "$2.pid" ;;
     run) while :; do
            free -m | awk -v ts="$(date -u +%FT%TZ)" '/^Mem:/{u=$3; a=$7} /^Swap:/{s=$3} END{print "host ts=" ts " mem_used_mb=" u " mem_available_mb=" a " swap_used_mb=" s}'
            docker stats --no-stream --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}'
            sleep 2
          done >> "$2" ;;
     *) echo "usage: sample.sh start|stop <file>" >&2; exit 2 ;;
   esac
   SH
   cat > .cache/vps-bin/probe.sh <<'SH'
   #!/usr/bin/env bash
   # usage: probe.sh start|stop <file> - one API request through web every 0.5 s, one line
   # "HH:MM:SS <http_code>" each (000 = no answer). start detaches; stop ends the probe.
   case "$1" in
     start) nohup timeout 3600 bash "$0" run "$2" >/dev/null 2>&1 </dev/null & echo $! > "$2.pid" ;;
     stop) kill "$(cat "$2.pid" 2>/dev/null)" 2>/dev/null; rm -f "$2.pid" ;;
     run) while :; do
            c=$(docker exec pocketquant-web curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost/api/v1/market-data/symbols 2>/dev/null)
            echo "$(date -u +%T) ${c:-000}"
            sleep 0.5
          done >> "$2" ;;
     *) echo "usage: probe.sh start|stop <file>" >&2; exit 2 ;;
   esac
   SH
   cat > .cache/vps-bin/oom-check.sh <<'SH'
   #!/usr/bin/env bash
   # usage: oom-check.sh <boot_id> <oom_kill> - OOM_OK, or OOM_STOP <reason> (the only machine stop)
   b=$(cat /proc/sys/kernel/random/boot_id); k=$(awk '/^oom_kill /{print $2}' /proc/vmstat)
   if [ "$b" != "${1:-}" ]; then echo "OOM_STOP boot_id ${1:-none} -> $b"; exit 1; fi
   if [ "$k" -gt "${2:-0}" ]; then echo "OOM_STOP oom_kill $2 -> $k"; exit 1; fi
   for c in $(docker ps -aq --filter label=com.docker.compose.project=pocketquant-prod); do
     if [ "$(docker inspect -f '{{.State.OOMKilled}}' "$c")" = true ]; then
       echo "OOM_STOP OOMKilled $(docker inspect -f '{{.Name}}' "$c")"; exit 1
     fi
   done
   echo OOM_OK
   SH
   ```
**Success criteria:** both scripts parse; no fixed backend name is left in `11-verify.sh`; no JSON-only error pattern is left; the four helpers parse.
**Verify:** `bash -n deploy/vps/11-verify.sh && bash -n deploy/vps/leases.sh && echo syntax-ok; grep -c "pocketquant-app" deploy/vps/11-verify.sh; grep -c 'check "Leases"' deploy/vps/11-verify.sh; grep -c '"levelname":"ERROR"' deploy/vps/11-verify.sh; for f in snapshot sample probe oom-check; do bash -n .cache/vps-bin/$f.sh || echo "syntax_error $f"; done; ls .cache/vps-bin/*.sh | wc -l` → `syntax-ok`, `0`, `2`, `0`, no `syntax_error` line, `4`.

### Task 8.5 — Rehearsal on Docker Desktop

**Goal:** the OOM abort, the cutover and a same-tag roll all work end to end before prod; each drain meets a delayed ACK at its boundary, retries once and still releases with `inflight=0`; one takeover per new trader; held leases owned by the role containers; a clean probe on the roll.
**Target files and symbols:** `.cache/rehearsal/` (copies only); `reports/cutover-rehearsal.md`.
<!-- Red team 2026-10-28: #3 -->
**Test-only seam (why it is the smallest):** a delayed venue ACK cannot reach the image without a code path, and a new config key or flag would be product code with one caller. Instead the rehearsal builds its own image layer on top of the real image: `sitecustomize.py` on `PYTHONPATH`, which Python imports at interpreter start. It makes every `PaperBrokerAdapter` report one order in flight for 45 s after the first `inflight_count` read (only the drain reads it), so the first drain window (boundary + 30 s) ends busy, `trader.drain_retry` is logged, and the retry at the next boundary releases. No file under `src`, `deploy` or `.env` changes, and the prod image never contains it. The real open path is covered in CI by Phase 07's lifespan test; the rehearsal covers what CI cannot (docker stop grace, uvicorn graceful, compose scaling, the lease handover across containers).
**Steps** (long steps run in the shell tool's background mode; wait for each completion notice):
1. Fake layer and images:
   ```bash
   mkdir -p .cache/rehearsal/fake
   cat > .cache/rehearsal/fake/sitecustomize.py <<'PY'
   """Rehearsal only: paper brokers report one order in flight for 45 s after the
   first inflight_count read, as a venue whose ACK lands after the drain window."""
   import time


   def _patch() -> None:
       from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter

       first: list[float] = []

       def inflight_count(self) -> int:
           if not first:
               first.append(time.monotonic())
           return 1 if time.monotonic() - first[0] < 45.0 else 0

       PaperBrokerAdapter.inflight_count = property(inflight_count)


   try:
       _patch()
   except Exception as exc:  # the rehearsal Verify fails without drain_retry lines
       print(f"rehearsal sitecustomize failed: {exc}", flush=True)
   PY
   printf 'FROM pqlocal/pocketquant:base\nENV PYTHONPATH=/rehearsal\nCOPY sitecustomize.py /rehearsal/sitecustomize.py\n' > .cache/rehearsal/fake/Dockerfile
   ```
   Then (background): `docker build -f deploy/Dockerfile -t pqlocal/pocketquant:base . && docker build -t pqlocal/pocketquant:new .cache/rehearsal/fake && docker tag pqlocal/pocketquant:new pqlocal/pocketquant:old && docker build -t pqlocal/pocketquant-web:new web && git worktree add .cache/rehearsal/src-old origin/master && docker build -t pqlocal/pocketquant-web:old .cache/rehearsal/src-old/web && echo images-ok`. The backend code is the same for both runs (this phase changes no Python); the old web image proxies `app`.
2. Copies with renamed containers, project, paths and no lock (Git Bash has no `flock`; Task 8.3 tested it):
   ```bash
   R=.cache/rehearsal; mkdir -p $R/old $R/new/vps $R/new/logs $R/new/bin
   SED='s#\([^/]\)pocketquant-\(app\|web\|mongodb\|redis\|cloudflared\|portainer\)#\1pqr-\2#g; s#pocketquant-prod#pqrehearsal#g; s#/opt/pocketquant/logs#./logs#g; s#/opt/pocketquant/bin#./bin#g; s#/opt/pocketquant/deploy.lock#./deploy.lock#g; s#flock -n 9#true#; /^docker pull/d'
   git show origin/master:deploy/compose.prod.yml | sed "$SED" > $R/old/compose.prod.yml
   sed "$SED" deploy/compose.prod.yml > $R/new/compose.prod.yml
   for f in 10-deploy.sh 11-verify.sh leases.sh; do sed "$SED" deploy/vps/$f > $R/new/vps/$f; done
   sed "$SED" .cache/vps-bin/probe.sh > $R/new/bin/probe.sh
   echo "rehearsal 0" > $R/new/bin/oom-baseline
   ```
3. Env files (dummy values, gitignored):
   ```bash
   cat > .cache/rehearsal/old/.env <<'EOF'
   APP_NAME=pocketquant-rehearsal
   APP_VERSION=0.0.0
   ENVIRONMENT=development
   LOG_LEVEL=INFO
   LOG_FORMAT=console
   MONGO_PORT=57017
   MONGO_USER=pocketquant
   MONGO_PASSWORD=rehearsal-pw
   MONGODB_URL=mongodb://pocketquant:rehearsal-pw@mongodb:27017/pocketquant?authSource=admin
   MONGODB_DATABASE=pocketquant
   MONGODB_MIN_POOL_SIZE=1
   MONGODB_MAX_POOL_SIZE=20
   REDIS_PORT=57379
   REDIS_PASSWORD=rehearsal-pw
   REDIS_URL=redis://:rehearsal-pw@redis:6379/0
   REDIS_CACHE_TTL=3600
   PORTAINER_PORT=59000
   TUNNEL_TOKEN=rehearsal-none
   DOCKERHUB_USERNAME=pqlocal
   IMAGE_TAG=old
   EOF
   sed 's/^IMAGE_TAG=old$/IMAGE_TAG=new/' .cache/rehearsal/old/.env > .cache/rehearsal/new/.env
   docker compose -f .cache/rehearsal/new/compose.prod.yml --env-file .cache/rehearsal/new/.env config -q && echo config-ok
   ```
   `config-ok` must print. `cloudflared` restarts in a loop without a real token; that is expected and ignored.
4. Old topology and one paper subscription (background): `docker compose -f .cache/rehearsal/old/compose.prod.yml --env-file .cache/rehearsal/old/.env up -d && for i in $(seq 150); do [ "$(docker inspect -f '{{.State.Health.Status}}' pqr-app 2>/dev/null)" = healthy ] && break; sleep 2; done; docker exec pqr-app curl -s http://localhost:41921/health | grep -o '"lease":"[^"]*"'` → `"lease":"held"`. Then seed (the fake needs a running paper broker in each trader):
   ```bash
   cat > .cache/rehearsal/seed.py <<'PY'
   import asyncio
   from datetime import UTC, datetime

   from pocketquant.core.common.uuid import generate_id
   from pocketquant.core.config import get_settings
   from pocketquant.core.domain.shared.enums import Interval
   from pocketquant.core.domain.subscription import Subscription
   from pocketquant.core.infra.persistence.mongodb import Database
   from pocketquant.core.infra.persistence.repositories.subscription_repository import SubscriptionRepository


   async def main() -> None:
       db = Database()
       await db.connect(get_settings())
       sub = Subscription(id=generate_id(), strategy_code="hitnrun2", symbol="BTCUSDT:BINANCE",
                          interval=Interval.MINUTE_1, created_at=datetime.now(UTC),
                          desired_state="running", actual_state="stopped")
       await SubscriptionRepository(db).add(sub)
       print("seeded")


   asyncio.run(main())
   PY
   docker exec -i pqr-app python - < .cache/rehearsal/seed.py; sleep 30; docker exec -i pqr-app python -c "from pymongo import MongoClient; from pocketquant.core.config import get_settings; s=get_settings(); print(MongoClient(str(s.mongodb_url))[s.mongodb_database].subscriptions.find_one()['actual_state'])"
   ```
   → `seeded` then `running`.
<!-- Red team 2026-10-28: #2 -->
5. OOM abort (background): `printf '#!/usr/bin/env bash\necho "OOM_STOP rehearsal"\n' > .cache/rehearsal/new/bin/oom-check.sh; L=.cache/rehearsal/new/logs; bash .cache/rehearsal/new/vps/10-deploy.sh > $L/deploy-abort.txt 2>&1; echo "deploy-exit=$?" >> $L/deploy-abort.txt; docker ps --filter label=com.docker.compose.project=pqrehearsal --format '{{.Label "com.docker.compose.service"}}' | grep -cE '^(api|worker|trader)$'; docker exec pqr-app curl -s http://localhost:41921/health | grep -o '"lease":"[^"]*"'` → `deploy-abort.txt` contains `OOM stop before the cutover` and ends with `deploy-exit=1`; then `0` and `"lease":"held"` (the old app kept trading).
6. Cutover with a probe: `printf '#!/usr/bin/env bash\necho OOM_OK\n' > .cache/rehearsal/new/bin/oom-check.sh; bash .cache/rehearsal/new/bin/probe.sh start .cache/rehearsal/new/logs/probe-cutover.txt`; then (background) `L=.cache/rehearsal/new/logs; bash .cache/rehearsal/new/vps/10-deploy.sh > $L/deploy-cutover.txt 2>&1; echo "deploy-exit=$?" >> $L/deploy-cutover.txt` → contains `One-time cutover` and ends with `deploy-exit=0`; then `bash .cache/rehearsal/new/bin/probe.sh stop .cache/rehearsal/new/logs/probe-cutover.txt`.
7. `bash .cache/rehearsal/new/vps/11-verify.sh 2>/dev/null | grep -cE "containers: PASS|lease: PASS|Leases: PASS"` → `6` (host checks that differ on Windows are ignored).
8. Same-tag roll with a probe: `bash .cache/rehearsal/new/bin/probe.sh start .cache/rehearsal/new/logs/probe-roll.txt`; then (background) `L=.cache/rehearsal/new/logs; bash .cache/rehearsal/new/vps/10-deploy.sh > $L/deploy-roll.txt 2>&1; echo "deploy-exit=$?" >> $L/deploy-roll.txt` → contains `Rolling api, worker, trader`, ends `deploy-exit=0`; then `bash .cache/rehearsal/new/bin/probe.sh stop .cache/rehearsal/new/logs/probe-roll.txt`.
9. Record in `reports/cutover-rehearsal.md`: the last 15 lines of each deploy output, both probe counts (`grep -vc ' 200$'` and `wc -l`), the abort-run result, and the Verify output below; add `Rehearsal: PASS` only when every Verify condition holds.
10. Clean up what this task started: `docker compose -p pqrehearsal down -v; git worktree remove --force .cache/rehearsal/src-old; docker image rm pqlocal/pocketquant:old pqlocal/pocketquant:new pqlocal/pocketquant:base pqlocal/pocketquant-web:old pqlocal/pocketquant-web:new`.
**Success criteria:** the abort run removes the new services and leaves the old app holding its leases; cutover and roll exit 0; the old app and the rolled-out trader each logged one `trader.drain_retry` and released with `inflight=0`; no drain timeout; the new trader logged both takeover events; 0 non-200 on the same-tag roll (the cutover probe is recorded only).
**Verify** (run before step 10): `L=.cache/rehearsal/new/logs; S='s/\x1b\[[0-9;]*m//g'; zcat $L/app-*.log.gz | sed "$S" | grep -c "trader\.drain_retry"; zcat $L/app-*.log.gz | sed "$S" | grep "trader\.lease_released" | grep -c "inflight=0"; zcat $L/trader-*.log.gz | sed "$S" | grep -c "trader\.drain_retry"; zcat $L/trader-*.log.gz | sed "$S" | grep "trader\.lease_released" | grep -c "inflight=0"; zcat $L/*.log.gz | sed "$S" | grep -c "trader\.drain_timeout"; docker logs "$(docker ps -q --filter label=com.docker.compose.project=pqrehearsal --filter label=com.docker.compose.service=trader)" 2>&1 | sed "$S" | grep -cE "trader\.takeover( |$)|trader\.takeover_complete"; grep -vc ' 200$' $L/probe-roll.txt; grep -c "OOM stop before the cutover" $L/deploy-abort.txt` → `1`, `1`, `1`, `1`, `0`, `2`, `0`, `1`.

### Task 8.6 — Gates, commit, push `develop`

**Goal:** the topology change is on `develop` with CI green.
**Target files and symbols:** the six changed files.
**Steps:**
1. Full suite (no Python changed; this proves nothing else moved): `uv run python -m pytest tests/ -q > .cache/pytest-full.txt 2>&1`; `uv run lint-imports`.
2. `git add deploy/compose.prod.yml web/nginx.conf deploy/vps/10-deploy.sh deploy/vps/11-verify.sh deploy/vps/leases.sh .github/workflows/cicd.yml && git commit -m "feat(deploy): run api, worker and trader with locked rolling deploys"`.
3. `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`; then in background mode `sleep 15 && GH_TOKEN=$(gh auth token --user camping89) gh run watch "$(GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --workflow cicd.yml --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status`.
**Success criteria:** known local red only; CI run succeeds.
**Verify:** `grep -E "^(FAILED|ERROR) " .cache/pytest-full.txt | grep -vcE "test_utc_runtime_guard|test_cron_trigger_timezone"; tail -1 .cache/pytest-full.txt; uv run lint-imports | tail -1; grep -c "^Rehearsal: PASS$" plans/261028-0652-exness-only-parallel-runtime/reports/cutover-rehearsal.md; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` → `0`, a line starting `4 failed` and containing `4 errors`, `Contracts: 6 kept, 0 broken.`, `1`, `pushed`; the background `gh run watch` exited 0.

### Task 8.7 — Install the helpers, cutover deploy D-5 with measurement

**Goal:** the helper set is on the VPS, the OOM stop is checked before and during the cutover, and prod moves from `app` to `api`/`worker`/`trader` with no trading gap, measured while it happens.
**Target files and symbols:** prod VPS; `/opt/pocketquant/bin/`; `/opt/pocketquant/logs/cutover/`.
**Steps:**
<!-- Red team 2026-10-28: #11 -->
1. Window: `D=$(date -u +%u); M=$((10#$(date -u +%H)*60+10#$(date -u +%M))); if [ $D -le 5 ] && { { [ $M -ge 360 ] && [ $M -lt 680 ]; } || { [ $M -ge 770 ] && [ $M -lt 1170 ]; }; }; then echo OK; else echo OUTSIDE; fi` (the **Deploy window** rule in plan.md Conventions: Mon-Fri 06:00-11:20 or 12:50-19:30 UTC). On `OUTSIDE`: `rm -f .cache/ssh/vps_key` and exit with the NOT_YET block (Resume at the next window start).
2. [ASK] (only an explicit yes counts):
   > Recommended: đồng ý — đã diễn tập cutover, roll và nhánh hủy do OOM trên Docker Desktop (reports/cutover-rehearsal.md: Rehearsal: PASS), có trình tự rollback; live trading vẫn tắt. Câu hỏi: Cho phép đẩy `develop:master` để chuyển prod từ `app` sang `api`/`worker`/`trader` ngay bây giờ (<UTC time>)? Trader mới chờ ở standby, `app` cũ xả lệnh tại mốc phút rồi nhường lease; `web` được tạo lại nên SPA gián đoạn vài giây (D27, chỉ ghi nhận).
<!-- Red team 2026-10-28: #2 #11 -->
3. Install the helper set and check the OOM stop (prints the six entries, `OOM_OK`, then an `OOM_STOP oom_kill -1 -> <n>` line that proves the stop path):
   ```bash
   B=$(sed -n 's/^oom_baseline=//p' plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md); HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'mkdir -p /opt/pocketquant/bin /opt/pocketquant/logs/cutover' && scp -i .cache/ssh/vps_key .cache/vps-bin/*.sh "$HOST:/opt/pocketquant/bin/" && ssh -i .cache/ssh/vps_key "$HOST" "bash -s $B" <<'SH'
   D=/opt/pocketquant/bin
   echo "$1 $2" > $D/oom-baseline
   ln -sf /opt/pocketquant/deploy/vps/leases.sh $D/leases.sh   # CI ships the target on this deploy
   chmod +x $D/snapshot.sh $D/sample.sh $D/probe.sh $D/oom-check.sh
   for f in snapshot sample probe oom-check; do bash -n $D/$f.sh || echo "syntax_error $f"; done
   ls $D | sort | tr '\n' ' '; echo
   bash $D/oom-check.sh $1 $2
   bash $D/oom-check.sh $1 -1
   SH
   ```
   → `leases.sh oom-baseline oom-check.sh probe.sh sample.sh snapshot.sh `, `OOM_OK`, `OOM_STOP oom_kill -1 -> <n>`. If the second line is `OOM_STOP ...`, the plan stops (D31): record it, `rm -f .cache/ssh/vps_key`, and exit with the NOT_YET block (`NOT_YET: OOM_STOP <reason>; owner decides`).
4. Before (record in `reports/handover-log.md` notes): `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'free -m; bash /opt/pocketquant/bin/snapshot.sh cutover-before'`.
5. Start the sampler and the probe (each returns at once and ends itself after 1 h): `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'D=/opt/pocketquant/logs/cutover; bash /opt/pocketquant/bin/sample.sh start $D/stats.txt; bash /opt/pocketquant/bin/probe.sh start $D/probe.txt; ls $D/*.pid | wc -l'` → `2`. Note the UTC start time.
6. Release: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop develop:master && git fetch origin`; then in background mode the Task 8.6 `gh run watch` command with `--branch master` (the deploy step can take up to about 8 minutes: standby warm-up plus the old trader's drain). The deploy script re-runs `oom-check.sh` after the new services are healthy and, on `OOM_STOP`, removes them and exits 1 while `app` keeps trading (Rollback: "D-5 stopped before `docker stop pocketquant-app`").
7. After: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'free -m; bash /opt/pocketquant/bin/snapshot.sh cutover-after; D=/opt/pocketquant/logs/cutover; bash /opt/pocketquant/bin/sample.sh stop $D/stats.txt; bash /opt/pocketquant/bin/probe.sh stop $D/probe.txt'`, recorded as "after".
**Success criteria:** the helper set is installed and the stop path works; the deploy run succeeded; samples and probe files exist and both loops stopped.
**Verify:** `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'D=/opt/pocketquant/logs/cutover; test -s $D/stats.txt && test -s $D/probe.txt && echo files-ok; ls $D/*.pid 2>/dev/null | wc -l; ls /opt/pocketquant/logs/app-*.log.gz | wc -l; bash /opt/pocketquant/bin/leases.sh | grep -c "owners_match=yes"'; GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --workflow cicd.yml --limit 1 --json conclusion -q '.[0].conclusion'` → `files-ok`, `0`, `1`, `1`, `success`.

### Task 8.8 — Verify the cutover and write row 0

**Goal:** the three roles run, each lease has one holder that is its role container, the old trader released cleanly, and row 0 carries the handover and D25 values.
**Target files and symbols:** `reports/handover-log.md`.
**Steps:**
1. Run the Verify command and keep its output.
<!-- Red team 2026-10-28: #1 #4 -->
2. Values for the row:
   ```bash
   HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'bash -s' <<'SH'
   cd /opt/pocketquant/deploy; S='s/\x1b\[[0-9;]*m//g'
   T=$(docker compose -f compose.prod.yml --env-file .env ps -q trader)
   A=$(zcat /opt/pocketquant/logs/app-*.log.gz | sed "$S"); N=$(docker logs "$T" 2>&1 | sed "$S")
   printf '%s\n' "$A" | grep -E "trader\.(lease_released|drain_retry|drain_timeout)"
   printf '%s\n' "$N" | grep -E "trader\.(standby|takeover)"
   echo "gap_skips=$(printf '%s\n' "$N" | grep 'strategy\.entry_skipped' | grep -c 'reason=gap')"
   D=$(printf '%s\n%s\n' "$A" "$N" | grep 'strategy\.signal_discarded')
   echo "discarded=lease:$(printf '%s\n' "$D" | grep -c 'reason=lease') drain:$(printf '%s\n' "$D" | grep -c 'reason=drain')"
   P=/opt/pocketquant/logs/cutover/probe.txt
   echo "probe_non200=$(grep -vc ' 200$' $P) probe_total=$(wc -l < $P)"
   awk '$1=="host"{for(i=2;i<=NF;i++){split($i,a,"="); v[a[1]]=a[2]+0} if(min==""||v["mem_available_mb"]<min)min=v["mem_available_mb"]; if(v["mem_used_mb"]>mu)mu=v["mem_used_mb"]; if(v["swap_used_mb"]>sw)sw=v["swap_used_mb"]; next}
        NF>=3{c=$2+0; u=$3; gsub(/[0-9.]/,"",u); x=$3+0; if(u=="GiB")x*=1024; else if(u=="KiB")x/=1024; else if(u=="B")x/=1048576; if(x>r[$1])r[$1]=x; if(c>p[$1])p[$1]=c}
        END{for(k in r) printf "peak %s rss_mib=%.0f cpu_pct=%.1f\n", k, r[k], p[k]; printf "host_used_max_mb=%s min_available_mb=%s max_swap_used_mb=%s\n", mu, min, sw}' /opt/pocketquant/logs/cutover/stats.txt
   cd /opt/pocketquant && bash deploy/vps/11-verify.sh | grep "^\[x\]"
   SH
   ```
<!-- Red team 2026-10-28: #4 #11 -->
3. Write `reports/handover-log.md`: a title `# Handover log`; a section `## Row 0 machine measurements (cutover D-5; D25, record only per D31)` holding `free -m` and the `snapshot.sh` lines before and after, the peak lines, the baseline `oom_baseline` and both `oom=` readings, `warmup_s` of the new trader, the `drain_retry` lines if any, the `11-verify.sh` FAIL rows (a `Memory` FAIL is recorded, D31); then the table header `| # | UTC start | kind | stamp | inflight | offset_s | drain_timeout | handover_gap_ms | takeover_ms | gap_skips | discarded | probe | leases | verify | verdict |`, the separator `|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|`, and row `| 0 | <UTC start> | cutover D-5 (image deploy, web recreated) | <yyyymmddTHHMMSSZ of the start> | <inflight> | <offset_s> | <drain_timeout count> | <handover_gap_ms from trader.takeover> | <takeover_ms from trader.takeover_complete> | <gap_skips> | lease:<n> drain:<n> | <non200>/<total> recorded (D27) | 2/2 owners_match=yes | <FAIL rows other than Memory> FAIL | PASS |`. The table is the last thing in the file (Phases 09-11 append rows). No VPS versions go into this file.
4. `git add plans/261028-0652-exness-only-parallel-runtime/reports/handover-log.md plans/261028-0652-exness-only-parallel-runtime/reports/cutover-rehearsal.md && git commit -m "docs(plans): record the api, worker and trader cutover" && git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin` (`**/*.md` does not trigger CI).
5. `rm -f .cache/ssh/vps_key`.
**Success criteria:** every Verify value holds; row 0 says PASS.
<!-- Red team 2026-10-28: #1 #2 #5 #11 -->
**Verify:** `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy; S="s/\x1b\[[0-9;]*m//g"; dc() { docker compose -f compose.prod.yml --env-file .env "$@"; }; docker ps --format "{{.Names}}" | grep -cE "^pocketquant-prod-(api|worker|trader)-[0-9]+$"; docker ps -a --format "{{.Names}}" | grep -cx pocketquant-app; T=$(dc ps -q trader); docker logs "$T" 2>&1 | sed "$S" | grep -cE "trader\.takeover( |$)"; docker logs "$T" 2>&1 | sed "$S" | grep -c "trader\.takeover_complete"; zcat /opt/pocketquant/logs/app-*.log.gz | sed "$S" | grep "trader\.lease_released" | grep -c "inflight=0"; zcat /opt/pocketquant/logs/app-*.log.gz | sed "$S" | grep -c "trader\.drain_timeout"; for s in worker trader; do docker exec "$(dc ps -q $s)" curl -s http://localhost:41921/health | grep -o "\"lease\":\"[^\"]*\""; done; docker exec pocketquant-web curl -s -o /dev/null -w "%{http_code}\n" http://localhost/api/v1/market-data/symbols; bash /opt/pocketquant/bin/leases.sh; bash /opt/pocketquant/bin/oom-check.sh $(cat /opt/pocketquant/bin/oom-baseline)'` → `3`, `0`, `1`, `1`, `1`, `0`, `"lease":"held"`, `"lease":"held"`, `200`, a line ending `unexpired=2 owners_match=yes`, and `OOM_OK`.

## Rollback

- **Before D-5:** `git revert --no-edit HEAD` (the Task 8.6 commit) on `develop` and push `develop`; nothing ran in prod. The helper files in `/opt/pocketquant/bin/` are inert and may stay.
<!-- Red team 2026-10-28: #2 -->
- **D-5 stopped before `docker stop pocketquant-app`** (an OOM stop, which already removed the new services, or a `wait_healthy` timeout): prod still trades on `app`, which holds both leases; after a timeout the new containers wait in standby. Remove them: `ssh ... 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env rm -sf api worker trader'`, then roll back the files as below. The failed tail is in `/opt/pocketquant/logs/failed-<svc>-<ts>.log`.
- **Cutover rollback sequence (after `app` was stopped):**
  1. Record `free -m` on the VPS.
  2. `git revert --no-edit <Task 8.6 commit>` on `develop`; push `develop`; CI green.
  3. [ASK] (Vietnamese, starts with `Recommended: ...`), then push `develop:master` inside the **Deploy window** of plan.md Conventions. CI rsyncs the reverted compose and scripts; the reverted `10-deploy.sh` runs `up -d --remove-orphans`, which stops `api`, `worker` and `trader` with their grace periods (the trader drains and releases) and creates `pocketquant-app` from the Deploy A image line, which takes both leases (at most the 30 s TTL if a release was missed). Expect a gap of about one `app` warm-up for paper; live is off.
  4. Check: `docker ps --format '{{.Names}}' | grep -cx pocketquant-app` prints `1` and the Task 7.8 lease one-liner prints `2 trader,worker 2 <h>` with `<h>` the `app` hostname. Record `free -m` after.
  5. Without CI (emergency, still after the step 3 [ASK] and inside the same deploy window): after the local revert, `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); scp -i .cache/ssh/vps_key deploy/compose.prod.yml "$HOST:/opt/pocketquant/deploy/" && scp -i .cache/ssh/vps_key deploy/vps/10-deploy.sh deploy/vps/11-verify.sh "$HOST:/opt/pocketquant/deploy/vps/"`, then `ssh ... 'cd /opt/pocketquant && bash deploy/vps/10-deploy.sh && bash deploy/vps/11-verify.sh'`.
- **A stuck lock:** the lock is held only while a `10-deploy.sh` process runs (`flock` on fd 9 ends with it); `ssh ... 'fuser /opt/pocketquant/deploy.lock'` names the holder.
- **Image guard rule:** never pin `IMAGE_TAG=sha-<x>` under the split compose when `<x>` predates Deploy A; the guard exits 1 before touching any container. To go back that far, first revert `compose.prod.yml` and `deploy/vps/` together (sequence above), then pin inside the single-`app` topology.
- `/opt/pocketquant/logs/cutover/` can be deleted after Phase 10; `/opt/pocketquant/logs/*.log.gz` stay for Phase 10 counts (the deploy prunes them after 30 days); `/opt/pocketquant/bin/` stays for Phases 09-11.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same failure evidence to the user. Never continue by self-reasoning.
