# Deployment

CI/CD: `git push` → GitHub Actions builds images → Docker Hub → SSH to VPS. One workflow (`.github/workflows/cicd.yml`), fully automatic. Production-only; for local dev see [README](../README.md).

## Branches

- `develop` holds all new development. A push there runs `tests` only.
- `master` is production: it receives only releases and hotfixes, and every push to it deploys.
- `master` must always be an ancestor of `develop`: same history, `develop` further ahead.
  - Release: `git push origin develop:master` (fast-forward; fails if `master` has diverged).
  - Hotfix: commit on `master`, push (deploys), then `git checkout develop && git merge master && git push` to restore the ancestry.

## Deploy

**`git push origin master` is the entire deploy.** A push to `develop` runs `tests` only and never touches Docker Hub or the VPS. There is no `.sh` to run by hand — the runner SSHes into the VPS and runs the deploy scripts for you.

```
git push origin master
  │
  └─ .github/workflows/cicd.yml   (5 jobs, GH-hosted ubuntu-latest)
       tests ──► build-app ─┐
                 build-web ─┴─► cleanup-tags
                                deploy ──► get-vps-config  (clone pocketquant-config via deploy key)
                                           rsync compose.prod.yml + .env + deploy/vps/ → VPS
                                           ssh → 10-deploy.sh   (pull, up, ≤60s health gate, prune)
                                           ssh → 11-verify.sh   (health checks → report artifact)
```

- `tests` gates the build. It runs once per host timezone (`UTC`, `Asia/Ho_Chi_Minh`, `America/Chicago`): `uv sync --frozen` → host-zone check → `lint-imports` (import-linter contracts) → `scripts/code_metrics.py --ratchet` (code metric ratchet, see [code-standards.md](./code-standards.md#quality-gate)) → `pytest tests/ -q`. `build-app`/`build-web` need every leg green.
- Images tagged `:latest` + `:sha-<short>`. `build-app`, `build-web`, `cleanup-tags` and `deploy` run only on `master` (push or `workflow_dispatch`); on any other ref they are skipped.
- **Concurrency per workflow and ref, `cancel-in-progress`** — a new `master` push cancels an in-flight `master` deploy; newest wins. A `develop` push never cancels a `master` run.

Manual trigger (no code change): `gh workflow run cicd.yml --ref master`.

## Verify

`deploy` runs `11-verify.sh` in-pipeline and uploads the `verify-report` artifact (3-day retention). That is the deploy's own health gate — a normal green run needs nothing extra.

Watch a run:

```bash
RUN_ID=$(gh run list --branch master --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status   # non-zero = a job failed → gh run view "$RUN_ID" --log-failed
```

Out-of-band SSH check — only when a run looks wrong, or to confirm the live image after a risky change:

```bash
HOST="$(cat ../pocketquant-config/vps/default/host)"; KEY="../pocketquant-config/vps/default/id_rsa"
ssh -i "$KEY" "$HOST" "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep pocketquant"
ssh -i "$KEY" "$HOST" "docker exec pocketquant-app curl -s -o /dev/null -w 'HTTP %{http_code}' http://localhost:41921/health"
```

`app`/`web` on short uptime + `(healthy)` = the deploy restarted them onto the fresh image (`:latest`, built from the pushed commit). `mongodb`/`redis` keeping long uptime is expected — the deploy must not recreate stateful containers. Anything else → [Rollback](#rollback).

## Platform & URLs

**Vultr VPS** (Ubuntu), self-managed Docker Compose. 6 containers: app (FastAPI + routes, internal :41921), web (nginx: serves the SPA and reverse-proxies `/api`, internal), cloudflared (Cloudflare Tunnel, outbound only), MongoDB, Redis, Portainer. Networks: `edge` (cloudflared, web) and `backend` (web, app, MongoDB, Redis). Images built by Actions, pushed to Docker Hub, pulled on the VPS.

| Surface | URL |
|---|---|
| Public SPA | `https://pocketquant.xyz/` |
| API (Swagger) | `https://pocketquant.xyz/api/v1/docs` |
| App health | container-internal: `docker exec pocketquant-app curl http://localhost:41921/health` |
| Portainer | `http://localhost:$PORTAINER_PORT` (through `just tunnel`, not via Cloudflare) |
| Docker Hub | `https://hub.docker.com/r/<DOCKERHUB_USERNAME>/pocketquant` |

Traffic enters via Cloudflare → Cloudflare Tunnel (`cloudflared`, outbound only) → `web` (nginx :80, no host port) → app (internal :41921). Cloudflare terminates browser TLS. DNS: the tunnel's routes `pocketquant.xyz` and `www`; no A record points at the VPS. The SPA is domain-agnostic (calls `window.location.origin + /api/...`), so no rebuild on domain change. SSH (22) is the only public port on the VPS; Mongo, Redis and Portainer bind 127.0.0.1 (use `just tunnel`).

nginx allows at most 10 open SSE streams per client IP (429 beyond).

## Environment & Credentials

Prod config (host, SSH key, `.env`, Docker Hub + Portainer creds) lives in the sibling **`pocketquant-config/`** repo — the **single source of truth**. CI/CD fetches it at run time via one read-only deploy key: the `POCKETQUANT_CONFIG_DEPLOY_KEY` GH secret + the `get-vps-config` composite action. `deploy` materializes `vps/default/.env` onto the VPS each run via `rsync`; any manual `.env` on the VPS is overwritten.

**Change a prod value:** edit the file in `pocketquant-config/` → `git push` there → push any commit to `pocketquant` (or `gh workflow run cicd.yml`) to redeploy.

`app` consumes `.env` via `env_file:` in `compose.prod.yml` — no `environment:` block to keep in sync. `MONGODB_URL`/`REDIS_URL` use internal docker service names (`mongodb:27017`, `redis:6379`); `MONGO_PORT`/`REDIS_PORT` are loopback host ports that external tools reach through `just tunnel`. App reads keys via Pydantic (`extra="ignore"`), so unused keys are harmless; a genuinely missing value surfaces as a container that fails to boot, caught by `11-verify.sh`.

Config files under `pocketquant-config/`:

| File | Purpose |
|---|---|
| `vps/default/host` | `user@ip` (single line) → `cfg.outputs.vps_host` |
| `vps/default/id_rsa` (`.pub`) | OpenSSH key → `cfg.outputs.ssh_key` |
| `vps/default/.env` | Prod `.env` → `cfg.outputs.env_content` |
| `vps/default/docker-hub.env` | `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` |
| `vps/default/portainer.env` | Portainer admin creds |
| `one-time/bootstrap-gh.sh` | Idempotent deploy-key setup + rotation |
| `local/all-local.env` | Local `.env` (code + Mongo + Redis all local) |
| `local/remote-db.env` | Local code against VPS Mongo/Redis |

Key prod env vars (full set in `vps/default/.env`):

| Variable | Req | Purpose |
|---|---|---|
| `DOCKERHUB_USERNAME` | Yes | Docker Hub user owning the images |
| `IMAGE_TAG` | No | Tag to pull; default `latest` |
| `MONGO_USER` / `MONGO_PASSWORD` | Yes | Mongo root creds |
| `REDIS_PASSWORD` | Yes | Redis auth (empty → deploy refuses; would silently disable auth) |
| `ADMIN_TOKEN` | Yes | Required in production; mutations return 503 while unset. Sent as `X-Admin-Token`. |
| `TUNNEL_TOKEN` | Yes | Token of the Cloudflare Tunnel run by `cloudflared`. Routes are set in the Cloudflare dashboard (Networking > Tunnels), not here. |
| `MONGO_PORT` / `REDIS_PORT` / `PORTAINER_PORT` | Yes | Host ports, bound to 127.0.0.1 (use obscure values) |
| `EXNESS_API_BASE_URL` | No | `https://api.exness.com` exactly (any other host or scheme leaves Exness unconfigured). Serves `getAccessPoint` only. |
| `EXNESS_ACCOUNT_ID` | No | Exness account id. |
| `EXNESS_API_KEY` | No | Exness API key id. |
| `EXNESS_SECRET_KEY` | No | The 128-hex secret exactly as Key Management shows it: 32-byte seed, then 32-byte public key. PEM is rejected, and the CI `.env` guard fails on multi-line values. |
| `EXNESS_LIVE_TRADING` | No | Default `false`; only a go-live plan changes it. While false, the `exness` broker and every order call are refused. |
| `EXNESS_RATE_FRACTION` | No | Share of the published Exness request rate the process uses; default `1.0`. |
| `EXNESS_DAILY_LOSS_CAP` | No | Daily realized-loss limit in account currency, per UTC day; unset rejects every Exness order. |
| `EXNESS_MAX_LOTS` | No | Upper bound on an Exness order's lots; unset means the minimum lot. |
| `EXNESS_LEVERAGE` | No | Account leverage ratio, used only to size Exness entries; default 1. |
| `EXNESS_RISK_PER_TRADE` | No | Share of balance risked per Exness entry, 0-0.10; default 0.02. |
| `PAPER_FUTURES_INITIAL_BALANCE` | No | Starting balance of paper accounts for futures (a contract spec with a multiplier); unset uses `PAPER_INITIAL_BALANCE`. |
| `PAPER_FUTURES_LEVERAGE` | No | Leverage that sizes paper futures entries; default 1. |

The per-account Exness access point is not an env var: `ExnessClient` resolves it from `getAccessPoint` once per process, holds it in memory and uses it as a full https URL. A transport failure or a 421 clears it; the next call resolves it again. All Exness values live in `pocketquant-config`; without the first four the app boots with Exness unconfigured.

Port map: app `41921` (internal, no host port) · web `80` (internal, no host port) · Mongo `127.0.0.1:$MONGO_PORT`→27017 · Redis `127.0.0.1:$REDIS_PORT`→6379 · Portainer `127.0.0.1:$PORTAINER_PORT`→9000.

## Prerequisites (one-time)

Bootstrap the deploy key — generates an ed25519 read-only key on `pocketquant-config` and pushes the private half as `POCKETQUANT_CONFIG_DEPLOY_KEY` in `pocketquant`. Idempotent (re-run to rotate):

```bash
cd ../pocketquant-config && bash one-time/bootstrap-gh.sh
```

That is the only secret this repo needs. First deploy = push (or `gh workflow run cicd.yml`); the `deploy` job installs Docker if missing, pulls images, starts every container, and health-gates the app. For a brand-new VPS, see [VPS Migration](#vps-migration).

---

**Operator Runbook — break-glass. Needed only when a deploy fails or for ops tasks.**

## Stop real-money entries when the site is down
The tunnel is the only public path to the SPA. Pause entries over SSH; the token stays inside the container:

```bash
ssh -i <key> <host> 'docker exec -i pocketquant-app sh -s' <<'EOF'
curl -s -X POST -H "X-Admin-Token: $ADMIN_TOKEN" http://localhost:41921/api/v1/admin/safeguards/pause
EOF
```

Then close any open position in the Exness app. The pause is stored and survives a restart.

## Restart while live
Use this for every planned restart (deploy, rollback, config dispatch) while an `exness` subscription exists. The pause survives a restart; strategy state (warmup, open direction) does not.
1. Pause entries (Exness strip, or the SSH command above).
2. Stop each `exness` subscription: `POST /api/v1/subscriptions/{id}/stop` with the token.
3. Confirm the account is flat (`GET /api/v1/subscriptions/{id}/positions` is empty for each), or accept that the venue SL/TP protects the open position.
4. Deploy.
5. After the health check, `GET /api/v1/admin/safeguards` shows `"entries_paused":true`.
6. Start each `exness` subscription again.
7. Resume entries only with a fresh approval.

## Rollback

Standard — revert + push (CI/CD redeploys from reverted HEAD, ~5-8 min):

```bash
git revert <bad-sha> && git push origin master
```

Emergency — pin a known-good SHA directly on the VPS (CI tags every push `:sha-<commit>`):

```bash
ssh -i pocketquant-config/vps/default/id_rsa "$(cat pocketquant-config/vps/default/host)" "cd /opt/pocketquant && \
  IMAGE_TAG=sha-<last-good-short> bash deploy/vps/10-deploy.sh && bash deploy/vps/11-verify.sh"
```

Database (only if a migration corrupted data):

```bash
ssh <VPS> "docker exec -i pocketquant-mongodb mongorestore --archive --gzip --drop < /opt/pocketquant/backups/<archive>"
```

## Troubleshooting

```bash
ssh <VPS> "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep pocketquant"   # status
ssh <VPS> "docker logs pocketquant-app --tail 50"                                    # logs
ssh <VPS> "docker exec pocketquant-app curl -s http://localhost:41921/health"        # health
ssh <VPS> "docker restart pocketquant-app"                                           # restart app (restarts scheduler + WS)
ssh <VPS> "cd /opt/pocketquant && docker compose -f deploy/compose.prod.yml --env-file deploy/.env restart"   # restart all, no rebuild
```

`11-verify.sh` **Boot integrity** is a hard-FAIL gate — greps the last 200 log lines for fatal startup signatures (`CRITICAL`, `Startup Failed`, `Application startup failed`, `lifespan … failed/error`, `RuntimeError … lifespan`, `migration.failed`). Endpoint-agnostic, so it survives feature churn.

Nuke + redeploy (**DESTROYS DATABASE**):

```bash
ssh <VPS> "cd /opt/pocketquant && docker compose -f deploy/compose.prod.yml --env-file deploy/.env down -v"
git commit --allow-empty -m "redeploy" && git push origin master
```

## Local access (from your machine)

Run `just tunnel` first and keep it open (Ctrl+C closes it). It forwards prod Mongo to `localhost:27017`, Redis to `localhost:6379` and Portainer to `localhost:$PORTAINER_PORT`; local 52017/53679 stay free for `just up`/`just redis`.

| Tool | Connection |
|---|---|
| Swagger | `https://pocketquant.xyz/api/v1/docs` (via Cloudflare) |
| DataGrip | `mongodb://pocketquant:PASSWORD@localhost:27017/pocketquant?authSource=admin` |
| RedisInsight | `localhost:6379` (password from `.env`) |
| Portainer | `http://localhost:$PORTAINER_PORT` |

**Run FE + BE locally against the prod VPS DB** (one source of truth for live debugging):

```bash
cp .env .env.local-only.bak                          # back up local config first
cp ../pocketquant-config/local/remote-db.env .env    # MONGODB_URL/REDIS_URL point at localhost through `just tunnel`
just tunnel   # in another terminal, first
just be   # app on :41921
just fe   # Vite on :5173
```

- Local writes hit the **production** DB — treat destructive scripts with VPS-level care.
- Keep `ENABLE_JOBS=false` (default in `remote-db.env`). The scheduler runs on PROD only; enabling it locally double-runs jobs against shared prod state. APScheduler 3 does not support two schedulers on one job store. With it off no reconcile loop or live collector starts, so no live broker connects. Its mutation routes need no token and write prod Mongo, which prod's reconcile then acts on.
- `ENABLE_JOBS=false` does **not** stop the WS quote feed — `start_quote_feed` is ungated, so the realtime chart still streams locally. The feed writes only ephemeral `quote:latest` / `bar:current` keys to Redis; the gated `sync_1m` + cascade cron is the sole Mongo `bars` writer, so local persists **no bars** to prod Mongo.
- To keep the local feed's in-progress bar/quote off prod's shared Redis, use `remote-db-local-redis.env` (`REDIS_URL` → local, `MONGODB_URL` → prod for history + closed bars). Start the local cache with `just redis` (only the redis service, not `just up`) **before** `just be` — Redis is a hard startup dependency, so the app crashes on boot if it is down.
- To exercise the bar-building writer itself, go fully local (`all-local.env` + `just up`) with `ENABLE_JOBS=true` so `sync_1m` + cascade write bars to your own Mongo.
- The `remote-db.env` Redis URL carries the `--requirepass` password; without it every Redis command is rejected (NOAUTH).
- Tests never touch prod: `tests/core_test/conftest.py` raises if `MONGODB_URL`/`REDIS_URL` contains the prod IP, and uses ephemeral testcontainers.

## Firewall

```bash
sudo ufw allow 22 && sudo ufw enable
```

Mongo, Redis and Portainer bind 127.0.0.1, so they need no ufw rule (Docker-published ports bypass ufw anyway).

## VPS Migration

VPS is disposable. To move:

1. Provision, run `deploy/vps/one-time/00-server-setup.sh` once (Docker, firewall, fail2ban, deploy user) — manually over SSH on first install.
2. Update `pocketquant-config/vps/default/host` (+ `id_rsa`/`.pub` if regenerated), `git push` there.
3. Push (or `gh workflow run cicd.yml`) — CI/CD does the first deploy.

DB starts fresh. Re-sync with the [data runbooks](#data-runbooks).

## Data Runbooks

### Two-year bar re-sync

Refresh historical bars after a data-source change. Scripts ship in the app image (`/app/scripts`), run via `docker exec`.

```bash
# Backup
ssh <VPS> "docker exec pocketquant-mongodb sh -c 'mongodump --uri=\"mongodb://\$MONGO_INITDB_ROOT_USERNAME:\$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/pocketquant?authSource=admin\" --archive' > /opt/pocketquant/backup-$(date -u +%Y%m%d).archive"
# Pre-audit → dry-run → execute (~2-3h) → post-audit (flat_pct/zerovol_pct should be ≤1%)
ssh <VPS> "docker exec pocketquant-app python scripts/audit_bar_quality.py --days 730 --output /app/audit-pre.md"
ssh <VPS> "docker exec pocketquant-app python scripts/backfill/binance_bars.py --dry-run --days 730 --replace"
ssh <VPS> "docker exec pocketquant-app python scripts/backfill/binance_bars.py --days 730 --replace"
ssh <VPS> "docker exec pocketquant-app python scripts/audit_bar_quality.py --days 730 --output /app/audit-post.md"
```

### Exness symbols and deep history

Seed the Exness CFDs (`XAUUSD:EXNESS`, `EURUSD:EXNESS`, `BTCUSD:EXNESS`) before the first `sync_1m` reaches them, then backfill history beyond the 5000-bar request cap. The backfill uses half the Exness request rate by default because the running app shares it, and it refuses to run (exit 3) while `EXNESS_LIVE_TRADING` is true.

```bash
ssh <VPS> "docker exec pocketquant-app python scripts/seed_exness_symbols.py"            # dry-run
ssh <VPS> "docker exec pocketquant-app python scripts/seed_exness_symbols.py --apply"
ssh <VPS> "docker exec pocketquant-app python scripts/backfill/provider_bars.py --symbol <CODE>:<PROVIDER> --interval <tf> --days <n> --rate-fraction 0.5"
```

A window older than the history Exness keeps fails with the Exness error code (for example `REQUEST_INVALID_TIME_RANGE`) and exit 1. `DELETE /api/v1/market-data/tracked-symbols/{symbol}` removes an Exness symbol together with all its data.

### Sync gap repair

When `job_history` shows `missed` events for `sync_backfill` (or after deploy windows overlapping 03:00-04:00 UTC), check + repair bar-data gaps. The `sync_1m` cascade self-heals 100 min of missed 1m data per tick, so most windows leave no residual gap — but verify first.

```bash
# Audit (web /monitor renders the same across all symbols)
ssh <VPS> "curl -s -X POST http://localhost:\$APP_PORT/api/v1/market-data/integrity/check -H 'Content-Type: application/json' -d '{\"symbol\":\"BTCUSDT:BINANCE\",\"interval\":\"1m\",\"days_back\":7}' | jq ."
# Repair (only if gaps): deletes misaligned + auto-resyncs gap ranges
ssh <VPS> "curl -s -X POST http://localhost:\$APP_PORT/api/v1/market-data/integrity/repair -H 'Content-Type: application/json' -d '{\"symbol\":\"BTCUSDT:BINANCE\",\"interval\":\"1m\",\"days_back\":7}' | jq ."
```

Re-audit → expect `missing_count == 0`. A residual gap means the source provider is missing that window (unrecoverable). At boot, `start_jobs` runs `enqueue_missed_catchups`: if the last `sync_backfill`/`sync_integrity` was >25h ago (or `sync_repair` >12.5h), a `<job_id>_catchup` one-off run is enqueued automatically.

---

For local development and UI testing, see [README](../README.md). This document is production-only.
