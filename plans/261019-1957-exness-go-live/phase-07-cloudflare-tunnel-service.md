---
phase: 7
title: "Cloudflare Tunnel service and edge hardening (B10, B12, B13)"
status: pending
priority: P1
effort: 3h + ~5 min user
dependencies: []
---

# Phase 07: Cloudflare Tunnel service and edge hardening (B10, B12, B13)

## Context
- Three-round tunnel rollout with no downtime: round 1 (this phase, user) creates the tunnel and a test hostname; round 2 (this phase, code) adds `cloudflared` while `web` keeps its host port, deployed and checked in Phase 08; round 3 (Phase 09) cuts DNS over and drops the port.
- Today the SPA is reached through the Cloudflare proxy to `web` on `${WEB_PORT:-80}` (`deploy/compose.prod.yml:8-9`; `docs/deployment.md:68`). Cloudflare→origin is plain HTTP.
- No Cloudflare API token exists for an agent, so the user creates the tunnel. Prod `.env` has no `TUNNEL_TOKEN` (counted 2026-10-20, value not read).
- The deploy runs `docker compose -f compose.prod.yml --env-file .env up -d --remove-orphans` (`deploy/vps/10-deploy.sh:50`); it pulls only the app and web images (`:46-47`), and compose pulls any other missing image on `up`. `11-verify.sh` checks running containers (`:66`) and health (`:78`).
- Red team (user decision 2026-10-20 20:20, ship in deploy A before arming):
  - Mongo, Redis and Portainer publish public host ports: `"${MONGO_PORT}:27017"` (`compose.prod.yml:70-71`), `"${REDIS_PORT}:6379"` (`:95-96`), `"${PORTAINER_PORT}:9000"` with `docker.sock` (`:115-118`). Docker-published ports bypass ufw. `mongo:7.0` is a floating tag (`:67`); MongoBleed (CVE-2025-14847, pre-auth) is fixed from 7.0.28. The newest 7.0 patch on Docker Hub on 2026-10-20 is `7.0.45`.
  - User decision 2026-10-20 21:32 (replaces "keep Mongo/Redis open" of 20:50): all three bind 127.0.0.1; local debugging against the remote DB goes through a new `just tunnel` recipe. Prod `.env` has `MONGO_PORT=52017`, `REDIS_PORT=53679`, `PORTAINER_PORT=54900` (read 2026-10-20). Local compose publishes the same 52017/53679 (`deploy/compose.local.yml:9,27`; `all-local.env`), so the tunnel uses local 27017 and 6379 to avoid a clash with `just up`/`just redis`. `pocketquant-config/local/remote-db.env` and `remote-db-local-redis.env` point `MONGODB_URL` (and `remote-db.env` also `REDIS_URL`) at the VPS IP; Phase 08 Task 8.3 moves them to localhost.
  - The file has no `networks:` key, so every service shares the default network.
  - The rate limiter keys on `request.client.host` (`src/pocketquant/core/common/rate_limit/middleware.py:37-38`), registered at `app/main_extensions.py:376` (capacity 200, refill 20/s). uvicorn runs without `--forwarded-allow-ips` (`compose.prod.yml:38`), and uvicorn 0.40 trusts forwarded headers only from 127.0.0.1 by default. So every public request shares the nginx container's bucket, and a flood of GETs also blocks Pause.
  - nginx sends `X-Forwarded-For $proxy_add_x_forwarded_for` (`web/nginx.conf:18`); the image is `nginx:1.27-alpine` (`web/Dockerfile:17`), which has the realip module. Cloudflare sets `CF-Connecting-IP` on every proxied request.
- `web` (nginx) listens on 80 and has a healthcheck (`compose.prod.yml:15-20`). The SSE routes are `/api/v1/market-data/bars/stream/{symbol}` (`app/routes/market_data.py:215`) and `/api/v1/quotes/stream/{symbol}` (`app/routes/market_data_quotes.py:72`). One SPA tab opens at most two streams (`web/src/hooks/use-realtime-bar.ts:48`, `web/src/hooks/use-realtime-quote.ts:80`).
- `just be` binds `0.0.0.0:41921` (`justfile:39`). With `remote-db.env` (`ENVIRONMENT=development`, no `ADMIN_TOKEN`) its mutation routes need no token and write prod Mongo, so anyone on the developer's LAN can reach them. Vite proxies to `http://localhost:41921` (`web/vite.config.ts:11`). `--host 0.0.0.0` listens on IPv4 only, so a local client that reaches it today also reaches `127.0.0.1` [I]. The justfile sets `windows-shell` to PowerShell (`justfile:4`); a `#!/usr/bin/env bash` recipe ignores that shell. Checked 2026-10-20 with just 1.58.0 in a scratch justfile with the same `windows-shell`: a bash shebang recipe ran, and `just --dry-run <recipe>` printed its body.
- Research (`plans/261019-1957-exness-go-live/reports/researcher-261020-1906-cloudflare-tunnel-facts.md`), verified: image `cloudflare/cloudflared` is distroless; `cloudflared tunnel --metrics 127.0.0.1:<port> ready` exists and fails without a metrics address; the 2026 dashboard path is Networking > Tunnels; a route save creates a proxied CNAME; the Free plan has asked for a payment card.

## Gates in this phase
- [USER] Task 7.1 only when `TUNNEL_TOKEN` is absent: the user creates the tunnel and replies `tunnel created`. The user may do this before cooking so the worker never waits.
- The `develop` push (Task 7.9) is authorized by the plan.

## Entry gate
Run first. On a miss: edit nothing, spawn no `kongming`, leave the phase pending, and end with:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pq-develop/plans/261019-1957-exness-go-live --from 07 after <UTC time>
```
- `docker ps` exits 0 (start Docker Desktop and retry once after 10 s).
- `git status --porcelain -- src web deploy tests scripts docs` prints nothing.

## Tasks

### Task 7.1 — [USER] Create the tunnel and the test route (round 1)
- Goal: `TUNNEL_TOKEN` exists in `pocketquant-config` and `tunnel-test.pocketquant.xyz` routes to `http://web:80`.
- Target files and symbols: `../pocketquant-config/vps/default/.env` key `TUNNEL_TOKEN` (user writes it); Cloudflare dashboard.
- Steps:
  1. Run `grep -c "^TUNNEL_TOKEN=." ../pocketquant-config/vps/default/.env`. If it prints `1`, skip to Task 7.2.
  2. Otherwise ask the user exactly: "In the Cloudflare dashboard: Networking > Tunnels > Create a tunnel > Cloudflared, name `pocketquant-prod` (the Free plan may ask for a payment card). Copy the token after `--token` in the install command; do not run that command. Then open the tunnel > Routes > Add route > Published application: subdomain `tunnel-test`, domain `pocketquant.xyz`, service URL `http://web:80`, Save. Leave `@` and `www` unchanged. Add the line `TUNNEL_TOKEN=<token>` to `pocketquant-config/vps/default/.env`. Never paste the token in chat. Reply `tunnel created`."
  3. Wait for the reply.
- Success criteria: the key exists; its value is never read or printed.
- Verify: `grep -c "^TUNNEL_TOKEN=." ../pocketquant-config/vps/default/.env` prints `1`.

### Task 7.2 — Pin the `cloudflared` image by digest
- Goal: an exact release at least 7 days old, pinned as `tag@sha256:digest`, whose `tunnel ready` command exists.
- Target files and symbols: none yet (the reference goes into Task 7.3).
- Steps:
  1. Print the newest `YYYY.M.P` tag last updated at least 7 days ago, with its digest: `curl -s "https://hub.docker.com/v2/repositories/cloudflare/cloudflared/tags?page_size=50&ordering=last_updated" | uv run python -c "import json,re,sys;from datetime import UTC,datetime,timedelta;c=datetime.now(UTC)-timedelta(days=7);t=next(t for t in json.load(sys.stdin)['results'] if re.fullmatch(r'\d{4}\.\d+\.\d+',t['name']) and datetime.fromisoformat(t['last_updated'].replace('Z','+00:00'))<=c);print(t['name']+'@'+t['digest'])"`. On 2026-10-20 this printed `2026.10.0@sha256:9b49eed8f62806d5d45ddf59ecefb5710429598ea6d3fcccd2af938f621b2b07`.
  2. `docker run --rm cloudflare/cloudflared:<tag>@<digest> tunnel ready --help`.
- Success criteria: one `tag@digest` chosen.
- Verify: step 2 exits 0 (`echo $?` prints `0`).

### Task 7.3 — Add the `cloudflared` service
- Goal: an outbound-only tunnel container on the `edge` network, with its own token only.
- Target files and symbols: `deploy/compose.prod.yml` (insert after the `web` service block, before `app:`).
- Steps: add, keeping `web`'s `ports:`:
  ```yaml
  # Outbound-only tunnel to Cloudflare; its published routes point at web:80.
  # Gets only its own token, not the app's .env. Pinned by digest.
  cloudflared:
    image: cloudflare/cloudflared:<tag>@<digest>
    container_name: pocketquant-cloudflared
    restart: unless-stopped
    command: ["tunnel", "--no-autoupdate", "run"]
    environment:
      TUNNEL_TOKEN: ${TUNNEL_TOKEN}
      TUNNEL_METRICS: 127.0.0.1:60123
    networks: [edge]
    depends_on:
      web:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "cloudflared", "tunnel", "--metrics", "127.0.0.1:60123", "ready"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    logging:
      driver: json-file
      options:
        max-size: "5m"
        max-file: "3"
  ```
  Do not add `env_file: .env` (it would hand every prod secret to this container).
- Success criteria: only `app` has `env_file`.
- Verify: `grep -c "^    env_file:" deploy/compose.prod.yml` prints `1` and `grep -c "cloudflared:.*@sha256:" deploy/compose.prod.yml` prints `1`.

### Task 7.4 — Networks, loopback data ports, pinned Mongo
- Goal: `cloudflared` reaches only `web`; Mongo, Redis and Portainer are reachable only from the VPS itself (and through `just tunnel`); Mongo runs a fixed patch ≥ 7.0.28.
- Target files and symbols: `deploy/compose.prod.yml` (top-level `networks:`; `networks:` on `web`, `app`, `mongodb`, `redis`; the three `ports:` lines; `mongodb.image`).
- Steps:
  1. `for k in MONGO_PORT REDIS_PORT PORTAINER_PORT; do grep -cE "^$k=[0-9]+\s*$" ../pocketquant-config/vps/default/.env; done` prints `1` three times (bare port numbers, so the prefix below is valid).
  2. Add at the end of the file: `networks:` with `edge: {}` and `backend: {}`, and one comment line: "edge: cloudflared and web only; backend: web, app and the data stores."
  3. `web`: `networks: [edge, backend]`. `app`, `mongodb`, `redis`: `networks: [backend]`. Portainer keeps the default network (it talks to the Docker socket only).
  4. Ports become `"127.0.0.1:${MONGO_PORT}:27017"`, `"127.0.0.1:${REDIS_PORT}:6379"`, `"127.0.0.1:${PORTAINER_PORT}:9000"`, with one comment line: "Loopback only: reach them with `just tunnel` (ssh -L)."
  5. Print the newest `7.0.N` Mongo tag: `curl -s "https://hub.docker.com/v2/repositories/library/mongo/tags?page_size=100&name=7.0." | uv run python -c "import json,re,sys;print(max((t['name'] for t in json.load(sys.stdin)['results'] if re.fullmatch(r'7\.0\.\d+',t['name'])),key=lambda n:int(n.split('.')[2])))"` (`7.0.45` on 2026-10-20). Set `image: mongo:<that tag>`; one comment line: "Pinned patch of the 7.0 line (same data files); 7.0.28+ fixes CVE-2025-14847."
- Success criteria: three loopback ports, two networks, a fixed Mongo patch.
- Verify: `docker compose -f deploy/compose.prod.yml config --quiet` exits 0 (unset variables only warn); `grep -c '"127.0.0.1:[$]{' deploy/compose.prod.yml` prints `3`; `grep -cE "image: mongo:7\.0\.[0-9]+$" deploy/compose.prod.yml` prints `1`.

### Task 7.5 — Real client IP for the rate limiter; Pause never limited; capped SSE streams
- Goal: each public client gets its own bucket, `/api/v1/admin/safeguards*` is never rate limited, and one client IP holds at most 10 open SSE streams.
- Target files and symbols: `web/nginx.conf` (server block); `deploy/compose.prod.yml:38` (`app.command`); `src/pocketquant/core/common/rate_limit/middleware.py` → `RateLimitMiddleware.dispatch`; create `tests/core_test/unit/common/test_rate_limit_middleware.py`.
- Steps:
  1. nginx, before `location /api/`: `set_real_ip_from 172.16.0.0/12;`, `set_real_ip_from 192.168.0.0/16;`, `real_ip_header CF-Connecting-IP;`, with one comment line: "Real client IP from Cloudflare, trusted only from Docker peers (cloudflared)." `$remote_addr`, and so the existing `X-Real-IP`/`X-Forwarded-For` lines, then carry the client IP.
  2. compose `app.command`: append `"--forwarded-allow-ips", "172.16.0.0/12,192.168.0.0/16"` (uvicorn then reads the client from nginx's `X-Forwarded-For`; the SSH break-glass call from 127.0.0.1 keeps its own bucket).
  3. Middleware: module constant `_UNLIMITED_PREFIX = "/api/v1/admin/safeguards"`; first line of `dispatch`: `if request.url.path.startswith(_UNLIMITED_PREFIX): return await call_next(request)`, with one comment line: "Pause must work while the API is flooded."
  4. Test (Starlette app with `RateLimitMiddleware(capacity=1)` and a dict-backed stub on `app.state.cache` with async `get`/`set`): two GETs to `/api/v1/x` → second is 429; three POSTs to `/api/v1/admin/safeguards/pause` → all 200.
  5. nginx SSE cap. At the top of the file, before `server {` (the file is included in the `http` context), add with one comment line "Open SSE streams per client IP; an empty key is not counted.":
     ```nginx
     map $uri $sse_client {
         ~/stream/  $binary_remote_addr;
         default    "";
     }
     limit_conn_zone $sse_client zone=sse:1m;
     ```
     In `location /api/` add `limit_conn sse 10;` and `limit_conn_status 429;`. `$binary_remote_addr` is the real client after step 1; 10 leaves room for several tabs at two streams each.
- Success criteria: four edits and one test file.
- Verify: `uv run python -m pytest tests/core_test/unit/common/test_rate_limit_middleware.py -q` exits 0; `MSYS_NO_PATHCONV=1 docker run --rm --add-host app:127.0.0.1 -v "$(pwd -W)/web/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.27-alpine nginx -t` exits 0; `grep -c "forwarded-allow-ips" deploy/compose.prod.yml` prints `1`; `grep -cE "limit_conn sse 10;|limit_conn_zone [$]sse_client" web/nginx.conf` prints `2`.

### Task 7.6 — justfile: `be` on loopback, new `tunnel` recipe
- Goal: a local backend (for example with `remote-db.env`, which skips the token check) is not reachable from the LAN; `just tunnel` forwards the loopback-only prod Mongo, Redis and Portainer to this machine.
- Target files and symbols: `justfile` → recipe `be` (`:39`); new recipe `tunnel` after `be`.
- Steps:
  1. In `be`, change `--host 0.0.0.0` to `--host 127.0.0.1`. Nothing else changes (Vite already proxies to `localhost:41921`).
  2. Add (no secret and no host in the repo; everything is read from `pocketquant-config` at run time; a key copy of its own, so an ops phase's `.cache/ssh/vps_key` is never touched):
     ```just
     # Forward prod Mongo -> localhost:27017, Redis -> localhost:6379, Portainer -> localhost:$PORTAINER_PORT.
     # Prod binds them to 127.0.0.1. Keep this running while debugging; Ctrl+C closes it.
     tunnel:
         #!/usr/bin/env bash
         set -euo pipefail
         cfg=../pocketquant-config/vps/default
         port() { grep "^$1=" "$cfg/.env" | cut -d= -f2 | tr -d '\r '; }
         mkdir -p .cache/ssh
         tr -d '\r' < "$cfg/id_rsa" > .cache/ssh/tunnel_key
         chmod 600 .cache/ssh/tunnel_key
         trap 'rm -f .cache/ssh/tunnel_key' EXIT
         ssh -i .cache/ssh/tunnel_key -N -o ExitOnForwardFailure=yes \
           -L "27017:localhost:$(port MONGO_PORT)" \
           -L "6379:localhost:$(port REDIS_PORT)" \
           -L "$(port PORTAINER_PORT):localhost:$(port PORTAINER_PORT)" \
           "$(head -1 "$cfg/host" | tr -d '\r')"
     ```
- Success criteria: one changed flag and one recipe. The tunnel itself is proven in Phase 08 Task 8.7, after the ports close.
- Verify: `grep -c -- "--host 127.0.0.1 --port 41921" justfile` prints `1`; `grep -c "0\.0\.0\.0" justfile` prints `0`; `just --dry-run tunnel 2>&1 | grep -c -- "-L \"27017:localhost:"` prints `1`.

### Task 7.7 — Verify script checks the new container
- Goal: the deploy verdict fails when `cloudflared` is down or unhealthy.
- Target files and symbols: `deploy/vps/11-verify.sh` → `CONTAINERS` (`:66`), `HEALTH_CONTAINERS` (`:78`).
- Steps: append `pocketquant-cloudflared` to both lists.
- Success criteria: both lists name it.
- Verify: `bash -n deploy/vps/11-verify.sh` exits 0 and `grep -c "pocketquant-cloudflared" deploy/vps/11-verify.sh` prints `2`.

### Task 7.8 — Docs
- Goal: `docs/deployment.md` lists the container, the key, the networks, loopback-only data ports reached through `just tunnel`, and the capped SSE streams.
- Target files and symbols: `docs/deployment.md`: container list (`:58`), Portainer row (`:65`), the last sentence of the traffic line (`:68`), env table (`TUNNEL_TOKEN` row; `MONGO_PORT / REDIS_PORT / PORTAINER_PORT` row `:100`), port map (`:117`), "Local access" (`:173-203`), "Firewall" (`:205-210`).
- Steps:
  1. `:58` → "6 containers" and add "cloudflared (Cloudflare Tunnel, outbound only)". Add one sentence: "Networks: `edge` (cloudflared, web) and `backend` (web, app, MongoDB, Redis)."
  2. Env row: `TUNNEL_TOKEN` | Yes | "Token of the Cloudflare Tunnel run by `cloudflared`. Routes are set in the Cloudflare dashboard (Networking > Tunnels), not here."
  3. `:68` last sentence → "SSH (22) reaches the VPS by IP; Mongo, Redis and Portainer bind 127.0.0.1 (use `just tunnel`)." `:100` row → "Host ports, bound to 127.0.0.1 (use obscure values)". Port map: Mongo `127.0.0.1:$MONGO_PORT`→27017 · Redis `127.0.0.1:$REDIS_PORT`→6379 · Portainer `127.0.0.1:$PORTAINER_PORT`→9000. One sentence after the traffic line: "nginx allows at most 10 open SSE streams per client IP (429 beyond)."
  4. "Local access": first line "Run `just tunnel` first and keep it open (Ctrl+C closes it). It forwards prod Mongo to `localhost:27017`, Redis to `localhost:6379` and Portainer to `localhost:$PORTAINER_PORT`; local 52017/53679 stay free for `just up`/`just redis`." Rows: DataGrip `mongodb://pocketquant:PASSWORD@localhost:27017/pocketquant?authSource=admin`; RedisInsight `localhost:6379` (password from `.env`); Portainer `http://localhost:$PORTAINER_PORT` (the `:65` row says the same). Delete the "SSH tunnel if DB ports are firewalled:" line and its code block. In the remote-db block: add `just tunnel   # in another terminal, first` before `just be`, and change the `cp` comment to "MONGODB_URL/REDIS_URL point at localhost through `just tunnel`". Append two sentences to the existing `ENABLE_JOBS=false` bullet (`:198`): "With it off no reconcile loop or live collector starts, so no live broker connects. Its mutation routes need no token and write prod Mongo, which prod's reconcile then acts on."
  5. Firewall block: `sudo ufw allow 22 && sudo ufw enable` only; one sentence: "Mongo, Redis and Portainer bind 127.0.0.1, so they need no ufw rule (Docker-published ports bypass ufw anyway)." The traffic line's first part changes in Phase 09.
- Success criteria: no doc line reaches a data port by the VPS IP; every remote-DB path starts with `just tunnel`.
- Verify: `grep -c "TUNNEL_TOKEN" docs/deployment.md` prints ≥ 1; `grep -c "6 containers" docs/deployment.md` prints `1`; `grep -cE "<vps-ip>:[$](MONGO|REDIS|PORTAINER)_PORT" docs/deployment.md` prints `0`; `grep -c "just tunnel" docs/deployment.md` prints ≥ 3; `grep -c "ufw deny" docs/deployment.md` prints `0`; `wc -l < docs/deployment.md` prints a number < 800.

### Task 7.9 — Gates and push
- Goal: on `origin/develop` (tests only; the deploy and round 2 checks run in Phase 08).
- Target files and symbols: the files above.
- Steps: ruff and pyright on `src/pocketquant/core/common/rate_limit` and the new test; `uv run lint-imports`; `uv run python scripts/code_metrics.py --ratchet`; commit; `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin` (never print the token).
- Success criteria: gates pass, push succeeds.
- Verify: ruff `All checks passed!`; pyright `0 errors`; lint-imports `Contracts: 8 kept, 0 broken.`; ratchet exits 0; `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.

## Risk
- `TUNNEL_TOKEN` wrong at deploy A (L/M): `cloudflared` restarts in a loop and the verdict fails; the site keeps the old path. Task 7.1 checks the key exists.
- `web` not resolvable from `cloudflared` (L/M): both are on `edge`; Phase 08's `tunnel-test` check proves it before anything is removed.
- The new networks recreate every container at deploy A, Mongo included (M/L): same volume, same 7.0 line; `app` waits for a healthy Mongo. No `exness` subscription exists at deploy A.
- Local tools and `remote-db.env` that reach Mongo, Redis or Portainer by the VPS IP stop working at deploy A (H/L): `just tunnel` (Task 7.6), the docs (Task 7.8), and the `pocketquant-config/local` URL edit in Phase 08 Task 8.3.
- Local port 27017 or 6379 already in use on the workstation (L/L): `ExitOnForwardFailure=yes` makes `just tunnel` exit with the bind error; stop the local service holding it.
- A browser with many tabs hits the SSE cap (L/L): the 11th stream gets 429 and the chart or ticker stays static; close tabs.
- `just be` no longer answers on the LAN (L/L): a phone or another machine cannot open the local backend; that is the intent.
- Private ranges are trusted for forwarded headers (L/L): only containers on `backend` can reach `app`, and only `cloudflared` reaches `web` once the port is gone (Phase 09). Before Phase 09 a direct client of `:80` can spoof `CF-Connecting-IP` to get a fresh bucket; that weakens only the limiter.
- The token is a new prod secret (M/M): it lives only in `pocketquant-config`; rotate it in the dashboard if it leaks.

## Rollback
Revert the commit; the next deploy with `--remove-orphans` removes the container and returns the default network and the public data ports (then revert the `pocketquant-config/local` URLs too). The user deletes the tunnel, the `tunnel-test` route and its DNS CNAME by hand (removing a route leaves its CNAME). After Phase 10, deploy only through the "Restart while live" runbook (`docs/deployment.md`).

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.
