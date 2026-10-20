# Red team: Security Adversary review of the Exness go-live plan

Date: 2026-10-20. Scope: `plan.md`, `phase-01` to `phase-12`. The binding user decisions in `debate-evidence-packet.md` and `plan.md` "User decisions (binding)" are treated as constraints. Labels: [V] means verified by grep, read, or a local command (no secret values printed). [I] means inference.

## Finding 1: Mongo, Redis and Portainer stay on the public internet, and each one bypasses every control the plan adds
- **Severity:** Critical
- **Location:** plan.md, section "Out of scope (flagged)"; Phase 09, Task 9.6 step 2 and Task 9.9 (AC10); Phase 10, section "Risk"
- **Flaw:** The plan treats the admin token as the last barrier in front of real money. Phase 10's Risk section says there is "no barrier left against an accidental `exness` subscription except the token". The plan leaves three published host ports out of scope. It calls their binding "unchecked", but checking it needs no secret values: [V] none of `MONGO_PORT`, `REDIS_PORT` or `PORTAINER_PORT` in the prod `.env` starts with `127.0.0.1:` (count 0). Docker publishes these ports past ufw (the plan's own research says so). Phase 09 then writes the exposure into the docs as intended ("DB ports ... reach the VPS by IP directly"). AC10 probes only port 80.
- **Failure scenario:** All three paths below assume an attacker can reach these ports.
  1. **Mongo write leads to code execution in the app.** APScheduler's `MongoDBJobStore` runs `pickle.loads(job_state)` on documents in `apscheduler_jobs`. A crafted job document runs code inside `pocketquant-app`, which holds the Exness API key and secret plus `ADMIN_TOKEN`.
  2. **Mongo write leads to a live subscription with no token.** An attacker inserts a subscription document with `broker: "exness"` and `desired_state: "running"`. The reconcile loop (every 5 s) loads it through `from_mongo`, which after Phase 02 reads `doc.get("broker","paper")` and checks nothing. This skips both the token and the `BROKER_DISABLED` check, which lives only in `add_symbol`. After Phase 11 Resume or the Phase 12 go-live, its signals send real orders.
  3. **Portainer leads to root on the host.** Portainer has `/var/run/docker.sock` mounted. The `:ro` flag does not limit Docker API calls. With Portainer, an attacker can `docker exec` into the app, read `.env`, and trade directly.
  4. **Mongo may also leak memory to unauthenticated callers.** [I] `mongo:7.0` is a floating tag, and `10-deploy.sh` pulls only the app and web images, so the running Mongo may be older than 7.0.28. In that case it is exposed to MongoBleed (CVE-2025-14847), an unauthenticated memory disclosure that is exploited in the wild.
- **Evidence:**
  - Published ports: `deploy/compose.prod.yml:70-71` (`${MONGO_PORT}:27017`), `:95-96` (`${REDIS_PORT}:6379`), `:115-118` (Portainer `:9000` with `docker.sock:ro`), `:112` (`portainer-ce:latest`), `:67` (`mongo:7.0`).
  - Images pulled on deploy: `deploy/vps/10-deploy.sh:46-47` pulls only the app and web images.
  - Mongo reached over the internet today: `docs/deployment.md:192` ("MONGODB_URL/REDIS_URL already point at VPS IP + creds"). The shape of `local/remote-db.env` is `mongodb://***@<ip>:52017/...` with no TLS parameter.
  - Pickle path: `core/infra/scheduling/scheduler.py:61` uses `MongoDBJobStore`, and installed apscheduler 3.11.2 contains `job_state = pickle.loads(job_state)`.
  - Reconcile trusts the document: `engine/live/strategy_reconcile_app_service.py:166-174` builds `StrategyConfig` from it, and Phase 02 Task 2.3 adds `broker=sub.broker`.
  - The plan's "unchecked" wording: `plan.md` "Out of scope", and Phase 09 Task 9.6 step 2 text.
- **Suggested fix:** Add a task before the Phase 10 [ASK]:
  - In compose, hard-code `127.0.0.1:` on all three port mappings; do not rely on a `.env` value.
  - Remove Portainer, or bind it to localhost and reach it through `ssh -L`.
  - Pin Mongo to `7.0.28` or later, by digest.
  - Move the `remote-db.env` workflow to an SSH tunnel.
  - Extend AC10 and Task 9.9 so the workstation probes each of the three ports and expects curl or nc exit 7 or 28.
  - Have `Subscription.from_mongo` reject any `broker` value other than `paper` or `exness`.

## Finding 2: One anonymous client can switch off the SPA's Pause, because the rate limiter puts all internet traffic in one bucket
- **Severity:** High
- **Location:** plan.md "Rollback", step 1 ("Pause (SPA...)"); Phase 09 Context ("the tunnel is the only public path to Pause") and Task 9.11; Phase 05 Task 5.7
- **Flaw:**
  - `RateLimitMiddleware` keys its bucket on `request.client.host`.
  - uvicorn runs without `--forwarded-allow-ips`. [V] Installed uvicorn trusts forwarded headers only from `127.0.0.1` by default, and the prod `.env` has no `FORWARDED_ALLOW_IPS` (count 0).
  - So every public request reaches the app with the nginx container's IP, and the whole internet shares one bucket: 200 capacity, refilling at 20 per second.
  - The middleware runs before the token guard and applies to every method.
  - SSE streams count once against the bucket, then stay open for up to 86 400 s through nginx. Each stream polls Redis every 0.5 s on the single uvicorn worker that also runs the live engine.
- **Failure scenario:** An attacker sends about 25 GET requests per second (no token needed) through `https://pocketquant.xyz`. Every SPA request now gets 429, including `POST /admin/safeguards/pause` and the strip's GET poll, which shows `—`. If the attacker also opens a few thousand SSE streams, the event loop that runs reconcile, the WS feed and the Exness adapter slows down. [I] Strategy signals and Exness WS heartbeats then lag. The SSH break-glass still works, because its requests come from `127.0.0.1` and get their own bucket. But the plan calls the SPA the softest rollback path and never tests it under load.
- **Evidence:** `src/pocketquant/core/common/rate_limit/middleware.py:37-48`; `src/pocketquant/app/main_extensions.py:376` (`capacity=200, refill_rate=20.0`); `deploy/compose.prod.yml:38` (uvicorn command with no proxy flags); `web/nginx.conf:26` (`proxy_read_timeout 86400s`); `src/pocketquant/app/routes/market_data.py:215-283` and `market_data_quotes.py:72` (SSE poll loops, 0.5 s).
- **Suggested fix:**
  - Trust only the proxy hop and key the bucket on the real client: in nginx, `real_ip_header CF-Connecting-IP` and `set_real_ip_from` the cloudflared subnet; in uvicorn, `--forwarded-allow-ips` set to the web container's subnet.
  - Exempt `/api/v1/admin/safeguards*`, or give requests with a valid token a separate bucket.
  - Cap concurrent streams with nginx `limit_conn` on `*/stream*`.
  - Add one Cloudflare rate-limiting rule (the free plan includes one).
  - Add a Phase 09 check: send 300 GETs in a burst, then SPA Pause must return 200.

## Finding 3: cloudflared shares a network with every backend service, its ingress is edited in the dashboard, and its image tag is mutable
- **Severity:** High
- **Location:** Phase 07, Tasks 7.1, 7.2 and 7.3; Phase 09, Task 9.2
- **Flaw:**
  - **Shared network.** `compose.prod.yml` declares no `networks:`, so the new `cloudflared` container sits on the default network next to `mongodb:27017`, `redis:6379`, `portainer:9000` and `app:41921`.
  - **Dashboard-controlled ingress.** The tunnel is token-run and remotely managed: ingress routes come from the Cloudflare dashboard (Task 7.1 and Task 9.2). Anyone with access to the Cloudflare account can publish `http://portainer:9000` or `http://app:41921` at a new hostname. Publishing the app directly bypasses nginx. No code change and no deploy are needed.
  - **Mutable image tag.** Task 7.2 picks the newest tag on Docker Hub by `last_updated` and pins the tag, not a digest. A re-pushed or compromised tag lands on the next `docker compose up`. `cloudflared` sees every `X-Admin-Token` in clear, because tunnel→`web:80` is plain HTTP.
- **Failure scenario:** A phished Cloudflare login, or a stray "Add route", exposes Portainer, which is root on the host. Or a bad `cloudflared` build captures the admin token, then calls create `exness` subscription and Resume.
- **Evidence:** `deploy/compose.prod.yml:1-129` (whole file, no `networks:` key); Phase 07 Task 7.2 step 1 (newest tag by `ordering=last_updated`) and Task 7.3 (`image: cloudflare/cloudflared:<tag>`); `web/nginx.conf:13-14` (nginx is the only intended path to `app`).
- **Suggested fix:**
  - Add two networks: `edge` holds `cloudflared` and `web`; `backend` holds `web`, `app`, `mongodb` and `redis`.
  - Pin `cloudflare/cloudflared:<tag>@sha256:<digest>`, and choose a release at least 7 days old.
  - Require 2FA on the Cloudflare account, and add a Phase 09 check that the tunnel has exactly two routes, both pointing at `http://web:80`.

## Finding 4: The admin token can cross plaintext HTTP before the cutover and again after a rollback, and the plan never rotates it
- **Severity:** Medium
- **Location:** plan.md "User decisions", bullet "Decided in the synthesis, not asked: no `ADMIN_TOKEN` rotation"; Phase 01 Task 1.4; Phase 08 Task 8.9; Phase 09 "Rollback"
- **Flaw:** The no-rotation decision assumes the token is first typed after the cutover. Nothing enforces that.
  - Deploy A (Phase 08) ships the SPA that prompts on any 401 and stores the answer in `localStorage`. Any ordinary mutation triggers the prompt, for example `POST /backtest/run` or `PATCH /backtest/{id}/name`, which Phase 01 now guards.
  - Today, Cloudflare→origin is plain HTTP on port 80. The gap between Phase 08 and Phase 09 has no time limit, since Phase 09 waits on the user's DNS work. Task 8.9 forbids typing the token only during that one check.
  - Phase 09 Rollback restores the `A @` record and port 80 while the token is still in `localStorage`, so it goes back out in clear with every mutation. There is no rotation step.
  - `window.prompt` shows the token unmasked.
  - nginx sends no Content-Security-Policy.
  - The bundle includes third-party npm code (echarts, lightweight-charts, @tanstack/*), but Phase 01 Risk says "loads no third-party scripts".
- **Failure scenario:** The user runs a backtest between deploy A and deploy B and pastes the token at the prompt. It crosses the Cloudflare-to-Vultr leg in clear, and the token stays valid for the rest of the plan. That token can create an `exness` subscription and Resume entries.
- **Evidence:** `docs/deployment.md:68` (Cloudflare proxy → `web` on `$WEB_PORT`, which is plain HTTP); `src/pocketquant/app/routes/backtest.py:52,83,94` (mutations guarded after Phase 01); `web/nginx.conf:1-43` (no CSP header); `web/package.json` dependencies (echarts, lightweight-charts, @tanstack/*).
- **Suggested fix:**
  - Rotate `ADMIN_TOKEN` in Phase 09 Task 9.7. It goes in the same config commit and rides deploy B, so it costs no extra deploy and also invalidates any copy already in `localStorage`.
  - Add "rotate after rollback" to Phase 09 Rollback.
  - Add a CSP header in nginx (`default-src 'self'`, plus a hash for the inline theme script in `web/index.html:8-18`).
  - Use a password-type input instead of `window.prompt`, and add a "forget token" action.

## Finding 5: The break-glass key is a root key with no passphrase, left on disk in the worktree with world-readable permissions
- **Severity:** Medium
- **Location:** plan.md "Ops recipe" SSH line; Tasks 8.1, 9.1, 10.1, 11.1 and 12.1
- **Flaw:**
  - Every ops phase writes `../pocketquant-config/vps/default/id_rsa` to `.cache/ssh/vps_key` and never deletes it.
  - [V] The key has no passphrase (`ssh-keygen -y -P ""` succeeds), and the host user is `root` (`grep -c "^root@" host` prints 1).
  - [V] `chmod 600` does nothing under Git Bash on NTFS: the existing copy shows `-rw-r--r--`.
  - Root on the VPS gives every prod secret, and orders can be sent straight through `ExnessClient`, outside `Safeguards`.
  - The break-glass needs only a pause, yet it uses a key that can do everything.
- **Failure scenario:** Any process or user on the workstation, a backup tool, or a sync tool copies the plaintext root key. The attacker owns the VPS and the Exness credentials.
- **Evidence:** `ls -la .cache/ssh/` shows `-rw-r--r-- vps_key` (dated 2026-10-20 10:20); `.gitignore:42` (`.cache`, so the key is ignored by git but stays on disk); the plan.md Ops recipe line.
- **Suggested fix:**
  - Load the key with `tr -d '\r' < .../id_rsa | ssh-add -` so it never sits on disk, or delete `.cache/ssh/vps_key` at the end of each phase.
  - For break-glass, add a separate key in `authorized_keys` with `command="docker exec pocketquant-app sh -c 'curl ... /pause'",no-pty,no-port-forwarding`, so a stolen break-glass key can only pause.

## Finding 6: The guard lets everything through outside production, and the documented local backend is an open path into prod
- **Severity:** Medium
- **Location:** Phase 01 Task 1.1 step 4 ("Token unset in any other environment → keep the current warning and allow"); plan.md "Conventions" (no rule on local backends while armed)
- **Flaw:**
  - The guard fails open whenever `ENVIRONMENT` is not `production`, including `staging`.
  - The documented "local code against prod DB" workflow is a problem:
    - It copies `remote-db.env` ([V] `ENVIRONMENT=development` count 1, no `ADMIN_TOKEN`).
    - It starts `just be`, which binds `0.0.0.0:41921` and allows CORS `*` in development.
  - That local process writes `desired_state` and deletes subscription documents in the prod Mongo, and the prod reconcile acts on those documents. Mutations through it need no token. Anyone on the developer's LAN can reach it.
- **Failure scenario:** After go-live, with the local backend running on café Wi-Fi, a LAN peer sends `POST http://<laptop>:41921/api/v1/subscriptions/<exness_id>/start` or `/stop`. Subscription ids come from prod's public `GET /api/v1/subscriptions/`. Prod reconcile then starts or stops the live strategy. [I] A start while entries are resumed means real orders.
- **Evidence:** `justfile:39` (`--host 0.0.0.0`); `docs/deployment.md:190-198` (remote-db workflow; writes hit production); `src/pocketquant/app/main_extensions.py:370` (CORS `*` in development); `src/pocketquant/app/middleware/admin_auth_middleware.py:28-31` (skips the check when the token is unset).
- **Suggested fix:**
  - Fail closed unless `environment == "development"` and the Mongo host is local; otherwise require the token.
  - Change `just be` to `--host 127.0.0.1`.
  - Add to the plan's Conventions: no local backend pointed at prod Mongo from Phase 10 on.

## Finding 7: Phase 09's verify-script edit breaks the Redis check and fails deploy B after the port is already gone
- **Severity:** Medium
- **Location:** Phase 09, Task 9.5 step 1; Task 9.8 Verify
- **Flaw:**
  - Task 9.5 says to delete "the `WEB_PORT_VAL` line (and its `source .env` line if nothing else in 3b uses it)".
  - Nothing else in section 3b uses it, so a literal worker deletes line 118.
  - But section 5 (`:140`) reads `${REDIS_PASSWORD:-}`, which only that `source` sets.
  - Section 8's `source` (`:176`) is deleted in the same task.
  - The script runs in a fresh ssh shell (`cicd.yml` "Verify on VPS"), so nothing else exports the variable.
  - Separately, `redis-cli -a "$REDIS_PASSWORD"` puts the Redis password in the process arguments, visible to `ps` on the host.
- **Failure scenario:** Deploy B finishes with port 80 already removed, and the verdict shows `Redis ping FAIL`. Task 9.8 Verify fails, so the Failure Protocol starts in the middle of the cutover.
- **Evidence:** `deploy/vps/11-verify.sh:118` (`source .env`), `:140` (`redis-cli -a "${REDIS_PASSWORD:-}"`), `:176`; `.github/workflows/cicd.yml:245` (`ssh "$VPS_HOST" "... bash deploy/vps/11-verify.sh"`).
- **Suggested fix:** Move `source .env` to the top of the script and say "keep it" in Task 9.5. Switch the Redis check to `docker exec -e REDISCLI_AUTH ...` so the password is not in the arguments.

## Finding 8: After go-live, anyone can read the live account's trading activity without a token
- **Severity:** Medium
- **Location:** AC1 ("every GET ... works without it"); Phase 01 Task 1.1 step 2
- **Flaw:**
  - The binding decision makes only `GET /admin/safeguards` public. AC1 widens that to every GET, so the guard skips all safe methods.
  - After Phase 11, anyone on the internet can read:
    - which subscriptions are `exness`, with their ids (`GET /subscriptions/`);
    - live positions, trades and metrics (`/subscriptions/{id}/positions|trades|metrics`);
    - engine orders and positions (`/trading/orders`, `/trading/positions`);
    - whether entries are paused (`/admin/safeguards`).
  - Those ids feed the attack in Finding 6.
  - The reason given, that EventSource cannot send headers, applies only to the two `/stream/` routes.
- **Failure scenario:** An outsider watches real-money positions and P&L, and harvests subscription ids for targeted mutations.
- **Evidence:** `src/pocketquant/app/routes/strategy.py:85,111,119,128`; `src/pocketquant/app/routes/trading_orders_positions.py:16-31`; `web/src/hooks/use-realtime-bar.ts:48` and `use-realtime-quote.ts:80` (the only EventSource callers).
- **Suggested fix:**
  - Skip the guard only for `GET /admin/safeguards` and the two `*/stream/*` paths, and require the token on the other GETs. The SPA's `apiFetch` would then send the header too.
  - Or put Cloudflare Access in front of `/api/v1/subscriptions*` and `/api/v1/trading*`.
  - Either change touches a public contract (AC1), so ask the user first.

## Fact-check summary (citations against the codebase)
Verified as cited:
- `core/config.py:121,127-128,132,135`
- `exness_client.py:238-246,265-266`
- `broker_factory.py:28,87-88,92-98,103-105`
- `position_calculator_domain_service.py:43-45`
- `strategy/value_objects.py:84`
- `strategy_reconcile_app_service.py:138-181`
- `strategy_app_service.py:64,402,406-408,462-480`
- `exness_broker_adapter.py:59,95-107,175-177,187,197,214,243,255,266,645-658`
- `subscription_repository.py:102-106`
- `strategy_command_service.py:99-107`
- `main_extensions.py:439-461`
- the 17 mutation routes (5 in market_data, 4 in tracked, 5 in strategy, 3 in backtest)
- the 4 per-route guards at `market_data.py:370,383,401,429`
- `api-client.ts:35-53`
- `strategy-api.ts:8-21,35-46`
- `use-realtime-bar.ts:48`, `use-realtime-quote.ts:80`
- `11-verify.sh:66,78,118-127,171-185`
- `10-deploy.sh:50`
- `provider_bars.py:76-78`
- `docs/deployment.md:10,58,68,99,115,117`
- `docs/system-architecture.md:164,179,187`
- `cicd.yml:48-54`
- prod `ENVIRONMENT=production` and the absence of `ADMIN_TOKEN` (key counts only)

Mismatches or gaps:
1. plan.md says the Mongo, Redis and Portainer bindings are "unchecked". They can be checked without reading values, and all three are not loopback-bound (Finding 1).
2. Phase 09 Task 9.5's "if nothing else in 3b uses it" is the wrong scope test (Finding 7).
3. Phase 01 Risk says "The SPA loads no third-party scripts". The bundle ships npm third-party code, and nginx has no CSP (Finding 4).
