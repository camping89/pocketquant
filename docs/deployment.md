# Deployment

CI/CD: GitHub Actions push → Docker Hub → SSH to VPS.

> **Deploy is via GitHub Actions push.** Push to `master` or `develop` triggers the full build → deploy → verify pipeline.

> **Single source of truth.** Top section is the `/deploy` skill–compatible summary; the operator runbook follows below.

## Platform

**Vultr VPS** (Ubuntu) with self-managed Docker Compose stack. 5 containers: app (FastAPI + routes + SPA), web (reverse proxy), MongoDB, Redis, Portainer. Images built by GitHub Actions, pushed to Docker Hub, pulled on the VPS.

Dashboards:
- Portainer: `http://<vps-ip>:$PORTAINER_PORT`
- Docker Hub: `https://hub.docker.com/r/<DOCKERHUB_USERNAME>/pocketquant`

## Production URL

`http://<vps-ip>:$WEB_PORT/` — public SPA entry point. The web container (nginx) reverse-proxies `/api/*` to the app container (FastAPI, internal :41921). Set `$WEB_PORT=443` if terminating TLS directly.

API: `http://<vps-ip>:$WEB_PORT/api/v1/docs` (Swagger, via web → app).
App health: container-internal only — `docker exec pocketquant-app curl http://localhost:41921/health`.

## Deploy Command

Push to `master` or `develop`:

```bash
git push origin develop
```

GitHub Actions handles everything: builds images, syncs files, ssh-deploys, verifies. Watch the run on the **Actions** tab.

Manual trigger:

```bash
gh workflow run cicd.yml --ref develop
# or: GitHub repo → Actions → CI/CD → Run workflow
```

**What runs:** 5 jobs in `.github/workflows/cicd.yml`

1. `tests` — pre-build gate: `uv sync --frozen` → `pytest tests/api_test/`. `build-api` + `build-web` both `needs: [tests]`, nên build chỉ chạy khi tests xanh.
2. `build-api` + `build-web` (parallel, ~3-5 min) — build + push Docker images, tagged `:latest` và `:sha-<short>`.
3. `cleanup-tags` — prune old Docker Hub SHA tags.
4. `deploy` (needs both builds green): `get-vps-config` composite action fetches config from `pocketquant-config` → setup SSH → write `deploy/.env` → rsync `compose.prod.yml` + `.env` + `deploy/vps/` → ssh `bash deploy/vps/10-deploy.sh` (pull, up, ≤60s health gate, prune) → ssh `bash deploy/vps/11-verify.sh` (19 checks) → upload verify report as artifact.

**Concurrency:** `concurrency: deploy / cancel-in-progress: true`. A new push cancels an in-flight deploy — newest wins.

**Verify report:** download from the run's `verify-report` artifact (retained 3 days).

## Environment Variables

Production config (host, SSH key, prod `.env`, Docker Hub creds, Portainer creds) lives in the sibling `pocketquant-config/` repo. CI/CD fetches it at run time via a single read-only deploy key — see [Prerequisites](#prerequisites) and [Credentials & Config Layout](#credentials--config-layout).

### Production config source-of-truth

`pocketquant-config/vps/default/.env` is the **single source of truth** for prod runtime env. The CI/CD `deploy` job materializes it as `deploy/.env` on the VPS each run via `rsync`. Any manual `.env` on the VPS is overwritten — edit the file in `pocketquant-config/`, `git push`, then push a commit to `pocketquant` (or `gh workflow run cicd.yml`).

The `app` service consumes it directly via `env_file: .env` in `compose.prod.yml` — there is **no** hardcoded `environment:` block to keep in sync. `MONGODB_URL`/`REDIS_URL` in this file use the **internal docker-network service names** (`mongodb:27017`, `redis:6379`) because the file IS the container env; `MONGO_PORT`/`REDIS_PORT` are the host-published ports for external tools. Host-side scripts that need DB access run inside the container (`docker exec pocketquant-app …`), where those names resolve — see the resync/backup procedures below.

### `<repo>/.env` — app + Docker/compose vars (local dev only)

Pydantic Settings reads it for `just be` / `just fe`. On the VPS, the same shape lives at `/opt/pocketquant/deploy/.env`, regenerated each deploy from `pocketquant-config/vps/default/.env`.

| Variable | Required | Purpose |
|---|---|---|
| `DOCKERHUB_USERNAME` | Yes | Docker Hub user that owns the images |
| `IMAGE_TAG` | No | Image tag to pull; defaults to `latest` |
| `MONGO_USER` | Yes | Mongo root user |
| `MONGO_PASSWORD` | Yes | Strong random Mongo password |
| `WEB_PORT` | Yes | Public SPA entry (default `80`, use `443` for TLS) |
| `MONGO_PORT` | Yes | Mongo external port (obscure value) |
| `REDIS_PORT` | Yes | Redis external port (obscure value) |
| `PORTAINER_PORT` | Yes | Portainer UI port (obscure value) |
| `REDIS_PASSWORD` | Yes | Redis auth password |
| `OKX_API_KEY` / `OKX_API_SECRET` / `OKX_PASSPHRASE` | No | Only for OKX live trading |
| `OKX_DEMO_MODE` | Yes | `false` in prod, `true` in dev |

The full key set lives in `pocketquant-config/vps/default/.env` (prod) and `pocketquant-config/local/` (local templates: `all-local.env`, `remote-db.env`). App reads them via Pydantic with `extra="ignore"`, so unused keys are harmless. There is no separate required-key gate — a genuinely missing prod value (e.g. `MONGO_PASSWORD`) surfaces as a container that fails to boot, caught by `11-verify.sh`.

Adding a new env var:
1. Set its value in `pocketquant-config/vps/default/.env`, `git push` from `pocketquant-config`.
2. Push any commit to `pocketquant` to redeploy.

**Where credentials live:** SSH key + prod `.env` + Docker Hub token + Portainer admin all live in the sibling `pocketquant-config/` directory — see [Credentials & Config Layout](#credentials--config-layout). CI/CD reads them at run time via the `POCKETQUANT_CONFIG_DEPLOY_KEY` secret (the only secret this repo needs).

## Custom Domain

Not configured by default — the VPS is reached by IP. To add a domain:

1. Point an A record at `<vps-ip>`.
2. Edit `pocketquant-config/vps/default/.env`: set `WEB_PORT=443`. `git push` from `pocketquant-config`.
3. Add Caddy or nginx + certbot in front of the `web` container, OR enable Cloudflare proxy (orange cloud) and let it terminate TLS.
4. Push any commit to `pocketquant` (or `gh workflow run cicd.yml`) — CI/CD re-deploys with the new env.

## Rollback

### Standard: revert commit + push

```bash
git revert <bad-sha>
git push origin develop  # or master
```

CI/CD runs from the reverted HEAD. ~5-8 min from push to VPS healthy on old code.

### Emergency: manual SSH (CI/CD unavailable, or need a specific SHA fast)

```bash
ssh -i pocketquant-config/vps/default/id_rsa "$(cat pocketquant-config/vps/default/host)" "cd /opt/pocketquant && \
  IMAGE_TAG=sha-<last-good-short> bash deploy/vps/10-deploy.sh && \
  bash deploy/vps/11-verify.sh"
```

CI tags every push as both `:latest` and `:sha-<commit>`. Pick the SHA of a known-good commit.

### Database rollback (only if a migration corrupted data)

```bash
ssh <VPS> "docker exec -i pocketquant-mongodb mongorestore --archive --gzip --drop < /opt/pocketquant/backups/<archive>"
```

## Troubleshooting

```bash
# Container status
ssh <VPS> "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep pocketquant"

# App logs
ssh <VPS> "docker logs pocketquant-app --tail 50"

# Health (app)
ssh <VPS> "docker exec pocketquant-app curl -s http://localhost:41921/health"

# Restart app (restarts scheduler + WS)
ssh <VPS> "docker restart pocketquant-app"

# Restart everything (no rebuild)
ssh <VPS> "cd /opt/pocketquant && docker compose -f deploy/compose.prod.yml --env-file deploy/.env restart"

# Nuke and redeploy (DESTROYS DATABASE)
ssh <VPS> "cd /opt/pocketquant && docker compose -f deploy/compose.prod.yml --env-file deploy/.env down -v"
git commit --allow-empty -m "chore: redeploy" && git push origin develop
```

The `11-verify.sh` **Boot integrity** check is a hard FAIL gate — it greps the last 200 log lines for fatal startup signatures (`CRITICAL`, `Startup Failed`, `Application startup failed`, `lifespan ... failed/error`, `RuntimeError ... lifespan`, `migration.failed`). Pattern is endpoint-agnostic so it keeps working as features change.

---

## Operator Runbook

### Services & Health

| Service | Check | Restart |
|---------|-------|---------|
| **app** (routes + scheduler, :41921) | `ssh <VPS> "docker exec pocketquant-app curl -s http://localhost:41921/health"` | `docker restart pocketquant-app` (stops scheduler/WS/strategy; data persists in MongoDB) |
| **web** (nginx, public) | `ssh <VPS> "docker exec pocketquant-web curl -s http://localhost:80"` | `docker restart pocketquant-web` (safe; API continues) |
| **Logs** | `ssh <VPS> "docker logs pocketquant-app --tail 50"` | — |

## Architecture

```
git push origin develop (or master)
  │
  └── .github/workflows/cicd.yml (GH-hosted ubuntu-latest)
        ├─ build-api      (Docker build + push :latest + :sha-<short>)
        ├─ build-web      (Docker build + push :latest + :sha-<short>)
        ├─ cleanup-tags   (prune old Docker Hub SHA tags)
        └─ deploy         (needs: build-api + build-web; concurrency: deploy)
              ├─ get-vps-config composite action (clones pocketquant-config via deploy key)
              ├─ setup SSH (key from cfg.outputs.ssh_key)
              ├─ write deploy/.env from cfg.outputs.env_content
              ├─ rsync deploy/{compose.prod.yml,.env,vps/} → VPS:/opt/pocketquant/
              ├─ ssh → bash deploy/vps/10-deploy.sh    (pull, up, ≤60s health gate, prune)
              ├─ ssh → bash deploy/vps/11-verify.sh    (19 checks → report)
              └─ upload verify-report artifact (30-day retention)

VPS containers: app (FastAPI routes + scheduler) + web (nginx) + mongodb + redis + portainer
```

### Distributed Scheduling

Background sync jobs are scheduled via APScheduler with a **MongoDBJobStore** backed by collection `apscheduler_jobs`. Multiple processes (e.g. the VPS app + a local dev BE pointing at VPS Mongo) coordinate through this shared collection — first to update `next_run_time` wins each tick. No extra lock layer needed. See [Local Dev Pointing at VPS DB](#local-dev-pointing-at-vps-db).

## Prerequisites

**One-time setup** — bootstrap the deploy key via the script in `pocketquant-config`:

```bash
cd ../pocketquant-config
bash one-time/bootstrap-gh.sh
```

The script generates an ed25519 deploy key, attaches it to `camping89/pocketquant-config` (read-only), and pushes the private half as `POCKETQUANT_CONFIG_DEPLOY_KEY` in `camping89/pocketquant`. Idempotent — re-run anytime to rotate.

Required GH Actions secrets in `camping89/pocketquant`:

| Secret | Source |
|---|---|
| `POCKETQUANT_CONFIG_DEPLOY_KEY` | Set by `pocketquant-config/one-time/bootstrap-gh.sh` |

That's it for the operator. No laptop-side setup is required for deploys.

**Optional laptop setup (for emergency rollback or debug ssh):**

- SSH key at `pocketquant-config/vps/default/id_rsa`.
- Standard tools: `ssh`, `scp` (macOS/Linux ships them).

## Credentials & Config Layout

All operator-side credentials live OUTSIDE this repo, in a sibling `pocketquant-config/` directory. Each VPS gets its own folder under `vps/`:

| File (under `pocketquant-config/`) | Purpose |
|------|---------|
| `vps/default/id_rsa` | OpenSSH private key — fetched by CI/CD as `cfg.outputs.ssh_key` |
| `vps/default/id_rsa.pub` | Matching public key (installed on VPS authorized_keys) |
| `vps/default/host` | Single line: `user@ip` — fetched as `cfg.outputs.vps_host` |
| `vps/default/.env` | Prod `.env` — fetched as `cfg.outputs.env_content` |
| `vps/default/docker-hub.env` | `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` |
| `vps/default/portainer.env` | Portainer admin credentials |
| `one-time/bootstrap-gh.sh` | Idempotent deploy-key setup + rotation |
| `local/all-local.env` | Ready-to-run local `.env` (code + Mongo + Redis all local) — `cp local/all-local.env ../pocketquant/.env` |
| `local/remote-db.env` | Local code against VPS Mongo/Redis — `cp local/remote-db.env ../pocketquant/.env` |

CI/CD reads all of the above at run time via the `POCKETQUANT_CONFIG_DEPLOY_KEY` GH secret + the `get-vps-config` composite action (`.github/actions/get-vps-config/`). Updates flow one-way: edit the file → `git push` from `pocketquant-config` → next CI/CD run picks it up.

## Port Map

| Service | Env Var | Default Container Port |
|---------|---------|----------------|
| App (routes + scheduler) | — | 41921 (internal) |
| Web (SPA + reverse proxy to app) | `WEB_PORT` | 80 |
| MongoDB | `MONGO_PORT` | 27017 |
| Redis | `REDIS_PORT` | 6379 |
| Portainer | `PORTAINER_PORT` | 9000 |

No default values in `.env` — you MUST set them. **`WEB_PORT` is the public entry point** (`80`, or `443` for TLS). MongoDB, Redis, and Portainer ports should use obscure values to cut bot-scanner noise — they aren't meant for direct public access.

---

## First Deploy

1. One-time: `bash pocketquant-config/one-time/bootstrap-gh.sh` (creates `POCKETQUANT_CONFIG_DEPLOY_KEY`).
2. Push (or `gh workflow run cicd.yml --ref develop`).

The `deploy` job will:

- Fetch VPS config from `pocketquant-config` via the `get-vps-config` composite action.
- Setup SSH (write key + `ssh-keyscan` the VPS IP).
- Write `deploy/.env` from `cfg.outputs.env_content`.
- `rsync` `compose.prod.yml` + `.env` + `deploy/vps/` to `/opt/pocketquant/`.
- ssh `bash deploy/vps/10-deploy.sh`:
  - Installs Docker if missing (then exits — re-run after logging back in).
  - Validates required env vars.
  - Pulls images from Docker Hub.
  - Starts all 4 services (app, web, mongodb, redis) + portainer.
  - Waits up to 60s for `pocketquant-app` `/health` to return 200; fails with last 30 log lines + container status if not.
  - Prunes old images.
- ssh `bash deploy/vps/11-verify.sh` — writes report to `deploy/reports/verify-<utc>.md` on the VPS, uploaded as `verify-report` artifact.

If `11-verify.sh` reports FAIL on any check, jump to [Rollback](#rollback).

---

## Updating (2nd+ Deploy)

```bash
git push origin develop      # or master
```

That's it. CI/CD is the only deploy path. Watch the run on the GitHub Actions tab.

---

## 2-Year Bar Re-Sync Procedure

Refresh historical market data after major data source changes (e.g. Binance migration, bug fixes). Scripts ship in app image (`/app/scripts`) and run via `docker exec pocketquant-app`.

**Backup → Audit (pre) → Dry-run resync → Execute → Post-audit:**

```bash
# Backup
ssh <VPS> "docker exec pocketquant-mongodb sh -c 'mongodump --uri=\"mongodb://\$MONGO_INITDB_ROOT_USERNAME:\$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/pocketquant?authSource=admin\" --archive' > /opt/pocketquant/backup-$(date -u +%Y%m%d).archive"

# Pre-audit (baseline)
ssh <VPS> "docker exec pocketquant-app python scripts/audit_bar_quality.py --days 730 --output /app/audit-pre.md"

# Dry-run resync
ssh <VPS> "docker exec pocketquant-app python scripts/resync_2y_from_binance.py --dry-run --days 730"

# Execute resync (all symbols, ~2-3h)
ssh <VPS> "docker exec pocketquant-app python scripts/resync_2y_from_binance.py --days 730"

# Post-audit (verify; flat_pct/zerovol_pct should be ≤1%)
ssh <VPS> "docker exec pocketquant-app python scripts/audit_bar_quality.py --days 730 --output /app/audit-post.md"

# Monitor for rate-limit errors
ssh <VPS> "docker logs pocketquant-app --tail 100 -f"
```

---

## Connecting from Local Machine

| Tool | Connection |
|------|------------|
| Swagger | `http://<vps-ip>:$APP_PORT/api/v1/docs` |
| DataGrip | `mongodb://pocketquant:PASSWORD@<vps-ip>:$MONGO_PORT/pocketquant?authSource=admin` |
| RedisInsight | `<vps-ip>:$REDIS_PORT` |
| Portainer | `http://<vps-ip>:$PORTAINER_PORT` |

### SSH Tunnel (if firewall blocks DB ports)

```bash
ssh -i pocketquant-config/vps/default/id_rsa -L 52017:localhost:52017 -L 53679:localhost:53679 "$(cat pocketquant-config/vps/default/host)"
# Then connect DataGrip to localhost:52017
```

---

## Local Dev Pointing at VPS DB

Run FE + BE on your machine but point them at the production VPS Mongo + Redis for one source of truth. Useful for live debugging, feature work, ad-hoc queries against real data.

### Setup

1. Copy the ready-made remote-DB config — its `MONGODB_URL`/`REDIS_URL` already point at the VPS IP + published ports with the correct creds (the prod `vps/default/.env` URLs use **internal** docker hostnames `mongodb`/`redis` that only resolve on the VPS network, so they can't be used from a laptop):

   ```bash
   cp ../pocketquant-config/local/remote-db.env .env
   ```

   The Redis URL carries the `--requirepass` password — without it every Redis command is rejected (NOAUTH).

2. Verify connectivity to `<vps-ip>:<MONGO_PORT>` and `<vps-ip>:<REDIS_PORT>` (mongo shell, redis-cli, or your IDE).

3. Start servers (two terminals):

   ```bash
   just be      # app (FastAPI + scheduler) on :41921
   just fe      # Vite dev server on :5173 (proxies /api -> :41921)
   ```

### Safety notes

- Local writes go to the **production** database. Treat destructive scripts (drop, reset, bulk delete) with the same care as on the VPS.
- Tests must NEVER touch prod. `tests/core_test/conftest.py` raises if `MONGODB_URL` or `REDIS_URL` contains the prod IP, and uses ephemeral testcontainers for the `settings` fixture.
- Before pointing at prod, back up local config: `cp .env .env.local-only.bak`. To revert: `cp .env.local-only.bak .env && just up`.
- Keep `ENABLE_JOBS=false` on local (the default in `remote-db.env`). The scheduler runs on PROD only; a local instance with jobs enabled would run them against the shared production state. Never set it to `true` locally.

---

## Firewall (Recommended)

```bash
sudo ufw allow 22                 # SSH
sudo ufw allow <APP_PORT>         # App API
sudo ufw allow <PORTAINER_PORT>   # Portainer
sudo ufw deny <MONGO_PORT>        # Block external MongoDB
sudo ufw deny <REDIS_PORT>        # Block external Redis
sudo ufw enable
```

---

## VPS Migration (new VPS)

VPS is disposable. To move to a new VPS:

1. Provision the new VPS, run `deploy/vps/one-time/00-server-setup.sh` once (it bootstraps Docker, firewall, fail2ban, deploy user). Run manually over SSH from your laptop on first install.
2. Update `pocketquant-config/vps/default/host` with the new `user@ip` (and `id_rsa` / `id_rsa.pub` if regenerated). `git push` from `pocketquant-config`.
3. Push (or `gh workflow run cicd.yml`) — CI/CD performs the first deploy on the new VPS.

Database will be fresh — everything can be re-synced via the [2-Year Bar Re-Sync Procedure](#2-year-bar-re-sync-procedure).

---

## Sync Gap Repair

When `job_history` shows `missed` events for `sync_backfill` (or after manual deploy windows that overlapped 03:00-04:00 UTC), verify whether bar-data gaps persist and repair them.

The cascade in `sync_1m` already self-heals 100 min of missed 1m data per tick, so most missed-daily windows leave no residual gap — but always verify before assuming.

### Step 1: Audit

```bash
ssh <VPS> "curl -s -X POST http://localhost:\$APP_PORT/api/v1/market-data/integrity/check \
  -H 'Content-Type: application/json' \
  -d '{\"symbol\":\"BTCUSDT:BINANCE\",\"interval\":\"1m\",\"days_back\":7}' | jq ."
```

Response includes `missing_count`, `gap_ranges`, `misaligned_ids`. The web Monitor view (`/monitor`) renders the same data across all tracked symbols.

### Step 2: Repair (only if audit shows gaps)

```bash
# Repair endpoint (deletes misaligned + auto-resyncs gap ranges):
ssh <VPS> "curl -s -X POST http://localhost:\$APP_PORT/api/v1/market-data/integrity/repair \
  -H 'Content-Type: application/json' \
  -d '{\"symbol\":\"BTCUSDT:BINANCE\",\"interval\":\"1m\",\"days_back\":7}' | jq ."

# Or per-symbol sync with deep n_bars window:
ssh <VPS> "curl -X POST http://localhost:\$APP_PORT/api/v1/market-data/sync \
  -H 'Content-Type: application/json' \
  -d '{\"symbol\":\"BTCUSDT:BINANCE\",\"interval\":\"1m\",\"n_bars\":5000}'"
```

`n_bars=5000` covers >3 days of 1m bars — enough to repair any realistic missed-backfill window.

### Step 3: Verify

Re-run Step 1 — expect `missing_count == 0` and empty `gap_ranges`. Any residual gap means the source provider is missing data for that window (not a sync issue) and the gap is unrecoverable.

### Catch-up at boot (automatic)

`start_background_jobs` runs `enqueue_missed_catchups` after cron registration. If the last successful `sync_backfill` / `sync_integrity` was >25h ago (or `sync_repair` >12.5h ago), a `<job_id>_catchup` one-off run is enqueued automatically. Manual audit is still recommended after any restart spanning a daily window, until 30 days of clean `job_history` confirm the catch-up is reliable.

---

For local development and UI testing, see [README](../README.md). This document is production-only.
