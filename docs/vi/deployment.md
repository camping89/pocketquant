# Deployment

CI/CD: `git push` → GitHub Actions build images → Docker Hub → SSH vào VPS. Một workflow duy nhất (`.github/workflows/cicd.yml`), hoàn toàn tự động. Chỉ dành cho production; muốn dev cục bộ xem [README](../../README.md).

## Deploy

**`git push origin develop` (hoặc `master`) chính là toàn bộ quy trình deploy.** Không có `.sh` nào phải chạy bằng tay — runner tự SSH vào VPS và chạy các script deploy hộ bạn.

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

- `tests` là cửa chặn cho phần build: `uv sync --frozen` → `lint-imports` (import-linter contracts) → `pytest tests/ -q`. `build-app`/`build-web` cần nó xanh mới chạy.
- Images gắn tag `:latest` + `:sha-<short>`. `deploy` chạy trên `develop`/`master`/`workflow_dispatch`.
- **Concurrency `deploy`, `cancel-in-progress`** — một push mới hủy deploy đang chạy dở; bản mới nhất thắng.

Trigger thủ công (không đổi code): `gh workflow run cicd.yml --ref develop`.

## Verify

`deploy` chạy `11-verify.sh` (19 checks) ngay trong pipeline và upload artifact `verify-report` (giữ 3 ngày). Đó là health gate của chính lần deploy — một lần chạy xanh bình thường không cần thêm gì.

Theo dõi một lần chạy:

```bash
RUN_ID=$(gh run list --branch develop --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status   # non-zero = a job failed → gh run view "$RUN_ID" --log-failed
```

Kiểm tra SSH ngoài luồng — chỉ khi một lần chạy có vẻ sai, hoặc để xác nhận image live sau một thay đổi rủi ro:

```bash
HOST="$(cat ../pocketquant-config/vps/default/host)"; KEY="../pocketquant-config/vps/default/id_rsa"
ssh -i "$KEY" "$HOST" "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep pocketquant"
ssh -i "$KEY" "$HOST" "docker exec pocketquant-app curl -s -o /dev/null -w 'HTTP %{http_code}' http://localhost:41921/health"
```

`app`/`web` uptime ngắn + `(healthy)` = lần deploy đã restart chúng lên image mới (`:latest`, build từ commit vừa push). `mongodb`/`redis` giữ uptime dài là điều bình thường — lần deploy không được tạo lại các container có state. Bất kỳ điều gì khác → [Rollback](#rollback).

## Platform & URLs

**Vultr VPS** (Ubuntu), tự quản lý bằng Docker Compose. 5 containers: app (FastAPI + routes + SPA, internal :41921), web (nginx reverse proxy), MongoDB, Redis, Portainer. Images do Actions build, push lên Docker Hub, pull về trên VPS.

| Surface | URL |
|---|---|
| Public SPA | `https://pocketquant.xyz/` |
| API (Swagger) | `https://pocketquant.xyz/api/v1/docs` |
| App health | container-internal: `docker exec pocketquant-app curl http://localhost:41921/health` |
| Portainer | `http://<vps-ip>:$PORTAINER_PORT` (direct, not via Cloudflare) |
| Docker Hub | `https://hub.docker.com/r/<DOCKERHUB_USERNAME>/pocketquant` |

Traffic đi vào qua **Cloudflare** (orange-cloud proxy) → container `web` (nginx, `$WEB_PORT`) → app (internal :41921). Cloudflare terminate TLS phía trình duyệt. DNS: `A @ → <vps-ip>` + `CNAME www → pocketquant.xyz`, cả hai đều proxied. SPA không phụ thuộc domain (gọi `window.location.origin + /api/...`), nên không cần rebuild khi đổi domain. SSH (22) và các port DB (`$MONGO_PORT`/`$REDIS_PORT`) truy cập VPS trực tiếp qua IP, không qua Cloudflare.

## Environment & Credentials

Config prod (host, SSH key, `.env`, Docker Hub + Portainer creds) nằm trong repo anh em **`pocketquant-config/`** — **single source of truth**. CI/CD fetch nó lúc run time qua một deploy key read-only duy nhất: GH secret `POCKETQUANT_CONFIG_DEPLOY_KEY` + composite action `get-vps-config`. `deploy` materialize `vps/default/.env` lên VPS mỗi lần chạy bằng `rsync`; bất kỳ `.env` sửa tay nào trên VPS đều bị ghi đè.

**Đổi một giá trị prod:** sửa file trong `pocketquant-config/` → `git push` ở đó → push bất kỳ commit nào vào `pocketquant` (hoặc `gh workflow run cicd.yml`) để redeploy.

`app` đọc `.env` qua `env_file:` trong `compose.prod.yml` — không có block `environment:` nào phải giữ đồng bộ. `MONGODB_URL`/`REDIS_URL` dùng service name nội bộ của docker (`mongodb:27017`, `redis:6379`); `MONGO_PORT`/`REDIS_PORT` là các port host-published cho tool bên ngoài. App đọc key qua Pydantic (`extra="ignore"`), nên key không dùng vô hại; một giá trị thực sự thiếu sẽ hiện ra dưới dạng container fail boot, bị `11-verify.sh` bắt.

Các file config trong `pocketquant-config/`:

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

Các env var prod chính (đầy đủ trong `vps/default/.env`):

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

Bootstrap deploy key — sinh một ed25519 key read-only trên `pocketquant-config` và push nửa private làm `POCKETQUANT_CONFIG_DEPLOY_KEY` trong `pocketquant`. Idempotent (chạy lại để rotate):

```bash
cd ../pocketquant-config && bash one-time/bootstrap-gh.sh
```

Đó là secret duy nhất repo này cần. Deploy lần đầu = push (hoặc `gh workflow run cicd.yml`); job `deploy` cài Docker nếu thiếu, pull images, khởi động cả 5 container, và health-gate app. Với VPS hoàn toàn mới, xem [VPS Migration](#vps-migration).

---

**Operator Runbook — break-glass. Chỉ cần khi một lần deploy fail hoặc cho các tác vụ ops.**

## Rollback

Chuẩn — revert + push (CI/CD redeploy từ HEAD đã revert, ~5-8 phút):

```bash
git revert <bad-sha> && git push origin develop   # or master
```

Khẩn cấp — pin một SHA đã biết là tốt trực tiếp trên VPS (CI tag mỗi push `:sha-<commit>`):

```bash
ssh -i pocketquant-config/vps/default/id_rsa "$(cat pocketquant-config/vps/default/host)" "cd /opt/pocketquant && \
  IMAGE_TAG=sha-<last-good-short> bash deploy/vps/10-deploy.sh && bash deploy/vps/11-verify.sh"
```

Database (chỉ khi một migration làm hỏng dữ liệu):

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

`11-verify.sh` **Boot integrity** là một cửa hard-FAIL — grep 200 dòng log cuối tìm các chữ ký lỗi khởi động fatal (`CRITICAL`, `Startup Failed`, `Application startup failed`, `lifespan … failed/error`, `RuntimeError … lifespan`, `migration.failed`). Không phụ thuộc endpoint, nên sống sót qua các thay đổi feature.

Nuke + redeploy (**HỦY TOÀN BỘ DATABASE**):

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

SSH tunnel nếu các port DB bị firewall:

```bash
ssh -i pocketquant-config/vps/default/id_rsa -L 52017:localhost:52017 -L 53679:localhost:53679 "$(cat pocketquant-config/vps/default/host)"
```

**Chạy FE + BE cục bộ chống lại DB của prod VPS** (một source of truth cho live debugging):

```bash
cp .env .env.local-only.bak                          # back up local config first
cp ../pocketquant-config/local/remote-db.env .env    # MONGODB_URL/REDIS_URL already point at VPS IP + creds
just be   # app on :41921
just fe   # Vite on :5173
```

- Ghi cục bộ đập thẳng vào DB **production** — đối xử với các script phá hủy cẩn trọng ở mức VPS.
- Giữ `ENABLE_JOBS=false` (default trong `remote-db.env`). Scheduler chỉ chạy trên PROD; bật nó cục bộ sẽ double-run jobs lên state prod dùng chung. Nhiều process phối hợp qua collection `apscheduler_jobs` dùng chung — xem `system-architecture.md`.
- `ENABLE_JOBS=false` **không** dừng WS quote feed — `start_quote_feed` không bị gate, nên realtime chart vẫn stream cục bộ. Feed chỉ ghi các key phù du `quote:latest` / `bar:current` vào Redis; cron `sync_1m` + cascade bị gate mới là bên ghi Mongo `bars` duy nhất, nên local **không persist bar nào** lên prod Mongo.
- Để giữ bar/quote đang dở của feed cục bộ khỏi Redis dùng chung của prod, dùng `remote-db-local-redis.env` (`REDIS_URL` → local, `MONGODB_URL` → prod cho history + closed bars). Khởi động cache cục bộ bằng `just redis` (chỉ service redis, không phải `just up`) **trước** `just be` — Redis là hard startup dependency, nên app crash lúc boot nếu nó down.
- Để test chính bên ghi bar-building, chạy hoàn toàn cục bộ (`all-local.env` + `just up`) với `ENABLE_JOBS=true` để `sync_1m` + cascade ghi bar vào Mongo của chính bạn.
- Redis URL trong `remote-db.env` mang password `--requirepass`; thiếu nó mọi lệnh Redis bị từ chối (NOAUTH).
- Tests không bao giờ chạm prod: `tests/core_test/conftest.py` raise nếu `MONGODB_URL`/`REDIS_URL` chứa IP prod, và dùng testcontainers phù du.

## Firewall

```bash
sudo ufw allow 22 && sudo ufw allow <PORTAINER_PORT>
sudo ufw deny <MONGO_PORT> && sudo ufw deny <REDIS_PORT>
sudo ufw enable
```

## VPS Migration

VPS là disposable. Để chuyển:

1. Provision, chạy `deploy/vps/one-time/00-server-setup.sh` một lần (Docker, firewall, fail2ban, deploy user) — thủ công qua SSH ở lần cài đầu.
2. Cập nhật `pocketquant-config/vps/default/host` (+ `id_rsa`/`.pub` nếu regenerate), `git push` ở đó.
3. Push (hoặc `gh workflow run cicd.yml`) — CI/CD làm deploy lần đầu.

DB khởi động mới tinh — re-sync qua quy trình dưới đây.

## 2-Year Bar Re-Sync

Refresh bar lịch sử sau khi đổi data-source. Scripts đóng trong app image (`/app/scripts`), chạy qua `docker exec`.

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

Khi `job_history` hiện các event `missed` cho `sync_backfill` (hoặc sau các cửa sổ deploy chồng lên 03:00-04:00 UTC), kiểm tra + sửa gap dữ liệu bar. Cascade `sync_1m` tự chữa 100 phút dữ liệu 1m bị miss mỗi tick, nên hầu hết cửa sổ không để lại gap dư — nhưng verify trước đã.

```bash
# Audit (web /monitor renders the same across all symbols)
ssh <VPS> "curl -s -X POST http://localhost:\$APP_PORT/api/v1/market-data/integrity/check -H 'Content-Type: application/json' -d '{\"symbol\":\"BTCUSDT:BINANCE\",\"interval\":\"1m\",\"days_back\":7}' | jq ."
# Repair (only if gaps): deletes misaligned + auto-resyncs gap ranges
ssh <VPS> "curl -s -X POST http://localhost:\$APP_PORT/api/v1/market-data/integrity/repair -H 'Content-Type: application/json' -d '{\"symbol\":\"BTCUSDT:BINANCE\",\"interval\":\"1m\",\"days_back\":7}' | jq ."
```

Re-audit → kỳ vọng `missing_count == 0`. Một gap dư nghĩa là provider nguồn thiếu cửa sổ đó (không cứu được). Lúc boot, `start_background_jobs` chạy `enqueue_missed_catchups`: nếu `sync_backfill`/`sync_integrity` gần nhất >25h trước (hoặc `sync_repair` >12.5h), một run một lần `<job_id>_catchup` được enqueue tự động.

---

Cho local development và UI testing, xem [README](../../README.md). Tài liệu này chỉ dành cho production.
