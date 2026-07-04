# Deployment

CI/CD: `git push` → GitHub Actions builds images → Docker Hub → SSH to VPS. One workflow (`.github/workflows/cicd.yml`), fully automatic. Production-only; for local dev see [README](../README.md).

## Deploy

**`git push origin develop` (or `master`) is the entire deploy.** There is no `.sh` to run by hand — the runner SSHes into the VPS and runs the deploy scripts for you.

```
git push origin develop
  │
  └─ .github/workflows/cicd.yml   (5 jobs, GH-hosted ubuntu-latest)
       tests ──► build-app ─┐
                 build-web ─┴─► cleanup-tags
                                deploy ──► get-vps-config  (clone pocketquant-config via deploy key)
                                           rsync compose.prod.yml + .env + deploy/vps/ → VPS
                                           ssh → 10-deploy.sh   (pull, up, ≤60s health gate, prune)
                                           ssh → 11-verify.sh   (19 checks → report artifact)
```

- `tests` gates the build: `uv sync --frozen` → `lint-imports` (import-linter contracts) → `pytest tests/ -q`. `build-app`/`build-web` need it green.
- Images tagged `:latest` + `:sha-<short>`. `deploy` runs on `develop`/`master`/`workflow_dispatch`.
- **Concurrency `deploy`, `cancel-in-progress`** — a new push cancels an in-flight deploy; newest wins.

Manual trigger (no code change): `gh workflow run cicd.yml --ref develop`.

## Verify

`deploy` runs `11-verify.sh` (19 checks) in-pipeline and uploads the `verify-report` artifact (3-day retention). That is the deploy's own health gate — a normal green run needs nothing extra.

Watch a run:

```bash
RUN_ID=$(gh run list --branch develop --limit 1 --json databaseId -q '.[0].databaseId')
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

**Vultr VPS** (Ubuntu), self-managed Docker Compose. 5 containers: app (FastAPI + routes + SPA, internal :41921), web (nginx reverse proxy), MongoDB, Redis, Portainer. Images built by Actions, pushed to Docker Hub, pulled on the VPS.

| Surface | URL |
|---|---|
| Public SPA | `https://pocketquant.xyz/` |
| API (Swagger) | `https://pocketquant.xyz/api/v1/docs` |
| App health | container-internal: `docker exec pocketquant-app curl http://localhost:41921/health` |
| Portainer | `http://<vps-ip>:$PORTAINER_PORT` (direct, not via Cloudflare) |
| Docker Hub | `https://hub.docker.com/r/<DOCKERHUB_USERNAME>/pocketquant` |

Traffic enters via **Cloudflare** (orange-cloud proxy) → `web` container (nginx, `$WEB_PORT`) → app (internal :41921). Cloudflare terminates browser TLS. DNS: `A @ → <vps-ip>` + `CNAME www → pocketquant.xyz`, both proxied. The SPA is domain-agnostic (calls `window.location.origin + /api/...`), so no rebuild on domain change. SSH (22) and DB ports (`$MONGO_PORT`/`$REDIS_PORT`) reach the VPS by IP directly, not through Cloudflare.

## Environment & Credentials

Prod config (host, SSH key, `.env`, Docker Hub + Portainer creds) lives in the sibling **`pocketquant-config/`** repo — the **single source of truth**. CI/CD fetches it at run time via one read-only deploy key: the `POCKETQUANT_CONFIG_DEPLOY_KEY` GH secret + the `get-vps-config` composite action. `deploy` materializes `vps/default/.env` onto the VPS each run via `rsync`; any manual `.env` on the VPS is overwritten.

**Change a prod value:** edit the file in `pocketquant-config/` → `git push` there → push any commit to `pocketquant` (or `gh workflow run cicd.yml`) to redeploy.

`app` consumes `.env` via `env_file:` in `compose.prod.yml` — no `environment:` block to keep in sync. `MONGODB_URL`/`REDIS_URL` use internal docker service names (`mongodb:27017`, `redis:6379`); `MONGO_PORT`/`REDIS_PORT` are host-published ports for external tools. App reads keys via Pydantic (`extra="ignore"`), so unused keys are harmless; a genuinely missing value surfaces as a container that fails to boot, caught by `11-verify.sh`.

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
| `WEB_PORT` | Yes | Public SPA entry (`80`, or `443` for TLS) |
| `MONGO_PORT` / `REDIS_PORT` / `PORTAINER_PORT` | Yes | Host-published ports (use obscure values) |
| `OKX_API_KEY` / `_SECRET` / `_PASSPHRASE` | No | OKX live trading only |
| `OKX_DEMO_MODE` | Yes | `false` in prod, `true` in dev |

Port map: app `41921` (internal, no host port) · web `$WEB_PORT` (public) · Mongo `$MONGO_PORT`→27017 · Redis `$REDIS_PORT`→6379 · Portainer `$PORTAINER_PORT`→9000.

## Prerequisites (one-time)

Bootstrap the deploy key — generates an ed25519 read-only key on `pocketquant-config` and pushes the private half as `POCKETQUANT_CONFIG_DEPLOY_KEY` in `pocketquant`. Idempotent (re-run to rotate):

```bash
cd ../pocketquant-config && bash one-time/bootstrap-gh.sh
```

That is the only secret this repo needs. First deploy = push (or `gh workflow run cicd.yml`); the `deploy` job installs Docker if missing, pulls images, starts all 5 containers, and health-gates the app. For a brand-new VPS, see [VPS Migration](#vps-migration).

---

**Operator Runbook — break-glass. Needed only when a deploy fails or for ops tasks.**

## Rollback

Standard — revert + push (CI/CD redeploys from reverted HEAD, ~5-8 min):

```bash
git revert <bad-sha> && git push origin develop   # or master
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
git commit --allow-empty -m "redeploy" && git push origin develop
```

## Local access (from your machine)

| Tool | Connection |
|---|---|
| Swagger | `https://pocketquant.xyz/api/v1/docs` (via Cloudflare) |
| DataGrip | `mongodb://pocketquant:PASSWORD@<vps-ip>:$MONGO_PORT/pocketquant?authSource=admin` (direct) |
| RedisInsight | `<vps-ip>:$REDIS_PORT` (direct) |
| Portainer | `http://<vps-ip>:$PORTAINER_PORT` (direct) |

SSH tunnel if DB ports are firewalled:

```bash
ssh -i pocketquant-config/vps/default/id_rsa -L 52017:localhost:52017 -L 53679:localhost:53679 "$(cat pocketquant-config/vps/default/host)"
```

**Run FE + BE locally against the prod VPS DB** (one source of truth for live debugging):

```bash
cp .env .env.local-only.bak                          # back up local config first
cp ../pocketquant-config/local/remote-db.env .env    # MONGODB_URL/REDIS_URL already point at VPS IP + creds
just be   # app on :41921
just fe   # Vite on :5173
```

- Local writes hit the **production** DB — treat destructive scripts with VPS-level care.
- Keep `ENABLE_JOBS=false` (default in `remote-db.env`). The scheduler runs on PROD only; enabling it locally double-runs jobs against shared prod state. Multiple processes coordinate via the shared `apscheduler_jobs` collection — see `system-architecture.md`.
- The `remote-db.env` Redis URL carries the `--requirepass` password; without it every Redis command is rejected (NOAUTH).
- Tests never touch prod: `tests/core_test/conftest.py` raises if `MONGODB_URL`/`REDIS_URL` contains the prod IP, and uses ephemeral testcontainers.

## Firewall

```bash
sudo ufw allow 22 && sudo ufw allow <PORTAINER_PORT>
sudo ufw deny <MONGO_PORT> && sudo ufw deny <REDIS_PORT>
sudo ufw enable
```

## VPS Migration

VPS is disposable. To move:

1. Provision, run `deploy/vps/one-time/00-server-setup.sh` once (Docker, firewall, fail2ban, deploy user) — manually over SSH on first install.
2. Update `pocketquant-config/vps/default/host` (+ `id_rsa`/`.pub` if regenerated), `git push` there.
3. Push (or `gh workflow run cicd.yml`) — CI/CD does the first deploy.

DB starts fresh — re-sync via the procedure below.

## 2-Year Bar Re-Sync

Refresh historical bars after data-source changes. Scripts ship in the app image (`/app/scripts`), run via `docker exec`.

```bash
# Backup
ssh <VPS> "docker exec pocketquant-mongodb sh -c 'mongodump --uri=\"mongodb://\$MONGO_INITDB_ROOT_USERNAME:\$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/pocketquant?authSource=admin\" --archive' > /opt/pocketquant/backup-$(date -u +%Y%m%d).archive"
# Pre-audit → dry-run → execute (~2-3h) → post-audit (flat_pct/zerovol_pct should be ≤1%)
ssh <VPS> "docker exec pocketquant-app python scripts/audit_bar_quality.py --days 730 --output /app/audit-pre.md"
ssh <VPS> "docker exec pocketquant-app python scripts/backfill/binance_bars.py --dry-run --days 730 --replace"
ssh <VPS> "docker exec pocketquant-app python scripts/backfill/binance_bars.py --days 730 --replace"
ssh <VPS> "docker exec pocketquant-app python scripts/audit_bar_quality.py --days 730 --output /app/audit-post.md"
```

## Sync Gap Repair

When `job_history` shows `missed` events for `sync_backfill` (or after deploy windows overlapping 03:00-04:00 UTC), check + repair bar-data gaps. The `sync_1m` cascade self-heals 100 min of missed 1m data per tick, so most windows leave no residual gap — but verify first.

```bash
# Audit (web /monitor renders the same across all symbols)
ssh <VPS> "curl -s -X POST http://localhost:\$APP_PORT/api/v1/market-data/integrity/check -H 'Content-Type: application/json' -d '{\"symbol\":\"BTCUSDT:BINANCE\",\"interval\":\"1m\",\"days_back\":7}' | jq ."
# Repair (only if gaps): deletes misaligned + auto-resyncs gap ranges
ssh <VPS> "curl -s -X POST http://localhost:\$APP_PORT/api/v1/market-data/integrity/repair -H 'Content-Type: application/json' -d '{\"symbol\":\"BTCUSDT:BINANCE\",\"interval\":\"1m\",\"days_back\":7}' | jq ."
```

Re-audit → expect `missing_count == 0`. A residual gap means the source provider is missing that window (unrecoverable). At boot, `start_background_jobs` runs `enqueue_missed_catchups`: if the last `sync_backfill`/`sync_integrity` was >25h ago (or `sync_repair` >12.5h), a `<job_id>_catchup` one-off run is enqueued automatically.

---

For local development and UI testing, see [README](../README.md). This document is production-only.
