# Deployment

This doc covers production only. For local development, see the [README](../README.md).

## Branches

- `develop` holds all new work. A push there runs the tests only.
- `master` is production. It receives only releases and hotfixes.
- `master` must stay an ancestor of `develop`. No CI step checks this.
  - Release: `git push origin develop:master`. It is a fast-forward, so it fails if `master` has diverged.
  - Hotfix: commit on `master` and push. Then run `git checkout develop && git merge master && git push` to restore the ancestry.

## Deploy

`git push origin master` is the whole deploy. No script runs by hand. The pipeline is `.github/workflows/cicd.yml`. Its `paths-ignore` lists the pushes that do not deploy.

To redeploy without a code change, run `gh workflow run cicd.yml --ref master`.

A deploy rolls `api`, `worker` and `trader` one at a time, so no role stops before its replacement is healthy. The order, the deploy lock and the health waits live in `deploy/vps/10-deploy.sh`.

## Verify

The `deploy` job runs `deploy/vps/11-verify.sh` and uploads its report as the `verify-report` artifact. A green run needs no extra check.

Watch a run:

```bash
RUN_ID=$(gh run list --branch master --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status   # non-zero = a job failed → gh run view "$RUN_ID" --log-failed
```

The SSH commands in this doc run from the repo root with these two variables:

```bash
KEY=../pocketquant-config/vps/default/id_rsa
HOST="$(head -1 ../pocketquant-config/vps/default/host)"
```

Check the VPS by hand only when a run looks wrong, or after a risky change:

```bash
ssh -i "$KEY" "$HOST" "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep pocketquant"
ssh -i "$KEY" "$HOST" "cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env exec -T api curl -s http://localhost:41921/health"
```

After a good deploy, `api`, `worker`, `trader` and `web` show a short uptime and `(healthy)`. `mongodb` and `redis` keep a long uptime. The deploy must not recreate the stateful containers. Anything else: see [Rollback](#rollback).

## Platform and Edge

The VPS is a Vultr machine on Ubuntu. It runs `deploy/compose.prod.yml` with Docker Compose. Checked over SSH (`/sys/class/dmi/id/sys_vendor`, `/etc/os-release`).

| Surface | Where |
|---|---|
| Public SPA | `https://pocketquant.xyz/` |
| API docs | `https://pocketquant.xyz/api/v1/docs` |
| Portainer | `http://localhost:$PORTAINER_PORT` through `just tunnel`. Cloudflare does not expose it. |
| Docker Hub | The account in `pocketquant-config/vps/default/docker-hub.env`. |

- Cloudflare terminates browser TLS.
- `cloudflared` opens an outbound tunnel to Cloudflare. The tunnel's public routes point at `web`.
- The routes for `pocketquant.xyz` and `www` live in the Cloudflare dashboard (Networking > Tunnels), not in this repo. `TUNNEL_TOKEN` only connects the tunnel.
- No DNS A record points at the VPS. The domain resolves to Cloudflare addresses (checked with `nslookup`).
- A domain change needs only Cloudflare edits. The SPA calls its own origin (`web/src/api/api-client.ts`), and nginx accepts any host name (`web/nginx.conf`).

### Firewall

- Only SSH on port 22 listens on a public address.
- Mongo, Redis and Portainer listen on 127.0.0.1 only. Reach them with `just tunnel`.
- ufw is active. It allows port 22 and the Mongo host port. The Mongo rule exposes nothing, because Mongo binds 127.0.0.1.
- Checked over SSH with `ufw status` and `ss -ltn`.
- Docker-published ports bypass ufw. Never publish a port on 0.0.0.0.

## Credentials

- All prod config lives in the sibling `pocketquant-config` repo. It is the single source of truth.
- CI reads it at run time with one read-only deploy key. The key is the `POCKETQUANT_CONFIG_DEPLOY_KEY` GitHub secret. `.github/actions/get-vps-config` does the read.
- Each deploy copies `vps/default/.env` onto the VPS. A manual edit of the `.env` on the VPS is lost at the next deploy.
- Env vars and defaults: `src/pocketquant/core/config.py::Settings`. The full prod set is `vps/default/.env`.
- Only an approved go-live sets `EXNESS_LIVE_TRADING=true`.

**Change a prod value:** edit the file in `pocketquant-config` and push there. Then run `gh workflow run cicd.yml --ref master`. If an `exness` subscription is live, follow [Restart while live](#restart-while-live).

Files in `pocketquant-config`:

| File | Holds |
|---|---|
| `vps/default/host` | `user@ip` of the VPS, one line |
| `vps/default/id_rsa` (`.pub`) | SSH key for the VPS |
| `vps/default/.env` | Prod `.env` |
| `vps/default/docker-hub.env` | Docker Hub user and token |
| `vps/default/portainer.env` | Portainer admin creds |
| `one-time/bootstrap-gh.sh` | Creates or rotates the CI deploy key |
| `local/*.env` | Local profiles. The README covers them. |

## Prerequisites (one-time)

Create the CI deploy key. Re-run the same command to rotate it.

```bash
cd ../pocketquant-config && bash one-time/bootstrap-gh.sh
```

That secret is the only one this repo needs. For a brand-new VPS, see [VPS Migration](#vps-migration).

---

**Operator Runbook: break-glass. Use it only when a deploy fails, or for ops tasks.**

## Stop real-money entries when the site is down

The tunnel is the only public path to the SPA. Pause entries over SSH. The token stays inside the container.

```bash
ssh -i "$KEY" "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env exec -T api sh -s' <<'EOF'
printf 'X-Admin-Token: %s\n' "$ADMIN_TOKEN" | curl -s -H @- -X POST http://localhost:41921/api/v1/admin/safeguards/pause
EOF
```

Then close any open position in the Exness app. The pause is stored and survives a restart.

## Restart while live

Use this for every planned deploy, rollback or config change while an `exness` subscription exists. A deploy does not stop the subscriptions. The new trader warms up in standby, takes over at a bar boundary, and restores each open direction from the open positions (`StrategyAppService.take_over`). The pause survives a restart.

1. Pause entries (Exness strip, or the SSH command above).
2. Deploy.
3. After the health check, `GET /api/v1/admin/safeguards` shows `"entries_paused":true`.
4. Resume entries only with a fresh approval.

Do not restart the trader container by hand. It has no standby, so no trader runs while it warms up. Re-roll the running tag instead:

```bash
ssh -i "$KEY" "$HOST" "cd /opt/pocketquant && IMAGE_TAG=<running tag> bash deploy/vps/10-deploy.sh"
```

## Rollback

Standard: revert and push. CI redeploys from the reverted HEAD.

```bash
git revert <bad-sha> && git push origin master
```

Emergency: pin a known-good image on the VPS. CI tags every image `:sha-<short>`. The `cleanup-tags` job prunes old tags, so an old SHA may be gone. The pin lasts until the next CI deploy, which pulls `:latest`. The image guard in `10-deploy.sh` refuses an image built before the role leases. To go back that far, revert the code, compose file and scripts together and push.

```bash
ssh -i "$KEY" "$HOST" "cd /opt/pocketquant && \
  IMAGE_TAG=sha-<last-good-short> bash deploy/vps/10-deploy.sh && bash deploy/vps/11-verify.sh"
```

Database: restore a backup only if a migration corrupted data. See [Mongo backup and restore](#mongo-backup-and-restore).

Nuke and redeploy. This **DESTROYS THE DATABASE**:

```bash
ssh -i "$KEY" "$HOST" "cd /opt/pocketquant && docker compose -f deploy/compose.prod.yml --env-file deploy/.env down -v"
gh workflow run cicd.yml --ref master
```

## Mongo backup and restore

Backups live in `/opt/pocketquant/backups` on the VPS. They are plain mongodump archives, not gzip.

Back up before any data change:

```bash
ssh -i "$KEY" "$HOST" "docker exec pocketquant-mongodb sh -c 'mongodump --uri=\"mongodb://\$MONGO_INITDB_ROOT_USERNAME:\$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/pocketquant?authSource=admin\" --archive' > /opt/pocketquant/backups/<name>-$(date -u +%Y%m%d).archive"
```

Restore an archive. `--drop` replaces each collection in the archive:

```bash
ssh -i "$KEY" "$HOST" "docker exec -i pocketquant-mongodb sh -c 'mongorestore --uri=\"mongodb://\$MONGO_INITDB_ROOT_USERNAME:\$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/?authSource=admin\" --archive --drop' < /opt/pocketquant/backups/<archive>"
```

## Local access to prod

- `just tunnel` forwards prod Mongo, Redis and Portainer to localhost. The `justfile` holds the ports. Keep it open while you work.
- Use it for DataGrip, RedisInsight and Portainer. The creds are in `vps/default/.env` and `vps/default/portainer.env`.
- To run local code against the prod DB, see the README section [Against the prod VPS DB](../README.md#against-the-prod-vps-db).

## VPS Migration

The VPS is disposable. To move:

1. Provision Ubuntu. Run `deploy/vps/one-time/00-server-setup.sh` once as root over SSH. Set `SSH_PORT=22`. CI (`cicd.yml`) and `just tunnel` connect on the default SSH port, and the script's default moves SSH elsewhere.
2. Update `pocketquant-config/vps/default/host` with the `deploy@ip` the script prints. The script turns off root login. Update `id_rsa`/`.pub` too if you made a new key. Push there.
3. Run `gh workflow run cicd.yml --ref master`. CI does the first deploy.

The live VPS was not set up by this script as written. SSH listens on 22, CI logs in as `root`, there is no `deploy` user, and ufw has no rules for the script's HTTP ports. Checked over SSH.

The DB on a new VPS starts empty. Backups stay on the old VPS, so copy the ones you need first. Then re-sync with the [data runbooks](#data-runbooks).

## Data Runbooks

The scripts ship in the app image under `/app/scripts`. Run each one in the `api` service with `ssh -i "$KEY" "$HOST" "cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env exec -T api python scripts/<path>"`. Each script's `--help` lists its flags.

### Two-year bar re-sync

Refresh historical bars after a data-source change.

1. [Back up Mongo](#mongo-backup-and-restore).
2. Run `audit_bar_quality.py` over two years for a pre-audit report.
3. Run `backfill/binance_bars.py` as a bulk two-year replace, first as a dry run.
4. Run the same command for real.
5. Run `audit_bar_quality.py` again. Accept the result when the flat and zero-volume shares are at most 1%.

### Exness symbols and deep history

1. Run `seed_exness_symbols.py` before the first sync reaches the Exness symbols. Dry-run first, then apply.
2. Run `backfill/provider_bars.py` for history beyond the request cap. Do it before go-live: the script refuses while `EXNESS_LIVE_TRADING` is true.

Exness keeps limited history. A window older than that fails with an Exness error code, for example `REQUEST_INVALID_TIME_RANGE` (observed against the Exness API).

### Sync gap repair

Check for bar-data gaps when `job_history` shows `missed` events for `sync_backfill`. A deploy that cuts the job leaves no gap, because the next worker resumes it ([System Architecture](system-architecture.md#decisions)). The schedule is in `register_sync_jobs` (`engine/market_data/app_services/sync_jobs.py`). The web `/monitor` page shows the same audit for all symbols.

Audit first. Run the repair only if the audit shows gaps. The repair deletes misaligned bars and re-syncs the gap ranges.

```bash
ssh -i "$KEY" "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env exec -T api sh -s' <<'EOF'
body='{"symbol":"BTCUSDT:BINANCE","interval":"1m","days_back":7}'
printf 'X-Admin-Token: %s\n' "$ADMIN_TOKEN" | curl -s -H @- -X POST -H 'Content-Type: application/json' -d "$body" http://localhost:41921/api/v1/market-data/integrity/check
# only if gaps: same call with /integrity/repair
EOF
```

Re-audit and expect `missing_count == 0`. A gap that stays means the provider lacks that window. It cannot be recovered.
