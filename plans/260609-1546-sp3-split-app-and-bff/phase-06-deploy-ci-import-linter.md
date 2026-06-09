---
phase: 6
title: "Deploy CI import-linter"
status: pending
priority: P1
effort: "6h"
dependencies: [4]
---

# Phase 6: Deploy CI import-linter

## Overview

Đóng gói + chạy 2 process: import-linter contract cho `pocketquant.bff` (top layer độc lập), 2 Docker image (hoặc 1 image 2 CMD), compose 2 service, CI build cả 2, deploy script. App không expose port public; bff expose. Cập nhật `pocketquant-config` nếu cần env/port mới.

## Requirements

- Functional:
  - import-linter: `pocketquant.bff` thêm vào layers contract cùng tầng `pocketquant.app` (cả 2 top, trên `{backtest,trading}`); forbidden contract: bff không import app, app không import bff.
  - Docker: build image cho app + bff. Quyết định 1 image 2 CMD vs 2 image — xem Architecture.
  - compose.prod.yml: service `app` (no public port hoặc chỉ internal /health) + `bff` (expose, serve web) + mongo + redis. `web` service trỏ bff. app `restart: always`/`unless-stopped`; depends_on mongo+redis healthy. bff depends_on app? (xem risk migration order).
  - CI cicd.yml: build app image + bff image; test path; deploy 2 service.
  - app healthcheck: liveness `/health`; bff healthcheck: readiness `/health`.
- Non-functional:
  - Kill bff không restart app (separate containers).
  - app migration chạy 1 lần (chỉ app), bff giả định schema ready.

## Architecture

### 1 image 2 CMD vs 2 image

- **1 image, 2 CMD** (Recommended cho KISS): cùng wheel chứa cả `pocketquant-app` + `pocketquant-bff` (workspace build), compose chạy 2 service từ cùng image, khác `command:` (`uvicorn pocketquant.app.main:app` vs `pocketquant.bff.main:app`). 1 build, 1 push, 2 container. Ít CI churn nhất.
- **2 image riêng**: tách Dockerfile, image nhỏ hơn mỗi cái nhưng 2 build + 2 push + 2 cleanup. Phức tạp hơn.

**Mặc định 1 image 2 CMD** — build 1 wheel chứa cả 2 entrypoint (deps overlap lớn). compose phân biệt qua `command`. Giảm CI/registry phức tạp. (Nếu sau cần image bff mỏng không kéo backtest engine, tách sau — YAGNI giờ.)

### Compose topology

```
web (nginx serve static? hoặc bff serve dist) → bff → mongo/redis
                                                  app → mongo/redis (headless, no public port)
```
Hiện `web` là service riêng (nginx, compose.prod.yml) VÀ app cũng serve dist qua StaticFiles. Sau split: **bff serve dist** (Phase 4 StaticFiles ở bff). Vậy `web` nginx service: giữ (proxy→bff) hay bỏ (bff serve trực tiếp)? Verify compose.prod hiện `web` nginx proxy gì. Mặc định: bff serve dist trực tiếp, `web` nginx chỉ reverse-proxy/TLS nếu cần — chốt khi đọc nginx config.

### Migration order (app trước bff)

App chạy migration/ensure_indexes lúc boot; bff giả định ready. compose: bff `depends_on: app: condition: service_healthy` để app migrate xong (healthy) rồi bff mới nhận traffic. ⚠ app healthy = liveness, không đảm bảo migration xong. Cần app `/health` chỉ trả healthy SAU khi lifespan startup hoàn tất (migration + indexes done) — lifespan chạy migration trước `yield`, nên app chỉ accept request sau yield ⇒ healthy ⇒ migration đã xong. OK tự nhiên.

## Related Code Files

- Modify: root `pyproject.toml` `[tool.importlinter]` — thêm `pocketquant.bff` vào layers contract top tier; thêm forbidden contract bff↔app
- Modify: `deploy/Dockerfile` — copy bff package pyproject; build wheel chứa cả 2 (workspace sync đã gồm)
- Modify: `deploy/compose.prod.yml` — thêm service `app` headless (no public port) tách khỏi service serve; service `bff` expose; `web` nginx trỏ bff
- Modify: `deploy/compose.local.yml` — (chỉ mongo+redis hiện tại; có thể thêm note 2 process local qua just)
- Modify: `.github/workflows/cicd.yml` — build app+bff (1 image 2 CMD → 1 build job giữ nguyên; chỉ đổi nếu 2 image); test path gồm bff_test
- Modify: `justfile` — recipe `be` (app headless) + `bff` (gateway) chạy 2 process local; hoặc `be` chạy cả 2
- Modify: `deploy/vps/10-deploy.sh` — healthcheck cả app+bff container
- Modify: `pocketquant-config/vps/default/.env` + `local/all-local.env` — thêm `BFF_PORT`/`APP_PORT` nếu tách; xác nhận với user (config repo riêng)
- Read context: `deploy/Dockerfile`, `compose.prod.yml`, `cicd.yml`, nginx config trong web image, `pocketquant-config/`

## Implementation Steps

1. import-linter: thêm `pocketquant.bff` vào `layers` contract (cùng dòng tier với `pocketquant.app` — dùng `pocketquant.app | pocketquant.bff` hoặc 2 entry top). Thêm forbidden: source `pocketquant.bff` forbidden `pocketquant.app`; source `pocketquant.app` forbidden `pocketquant.bff`. `lint-imports` xanh.
2. Dockerfile: copy `packages/pocketquant-bff/pyproject.toml`; `uv sync` đã gồm (workspace). Verify wheel chứa cả 2 entrypoint scripts.
3. compose.prod: tách service. `app`: cùng image, `command: uvicorn pocketquant.app.main:app ...`, no `ports` public (hoặc chỉ internal), healthcheck app `/health`, `restart: unless-stopped`, depends_on mongo+redis. `bff`: `command: uvicorn pocketquant.bff.main:app`, expose `${BFF_PORT}:41920` (hoặc serve web), healthcheck bff `/health`, depends_on app healthy + mongo+redis. `web` nginx → trỏ bff.
4. Xác nhận env: port mới (`APP_PORT` internal, `BFF_PORT` public). Nếu cần sửa `pocketquant-config` → hỏi user (repo riêng, không tự commit).
5. CI: thêm `tests/bff_test/` vào pytest; build job giữ 1 image (2 CMD). Verify deploy job pull + up 2 service.
6. deploy.sh: wait health cả `pocketquant-app` + `pocketquant-bff` container.
7. justfile: `just be` (app headless) + `just bff` (gateway) — 2 recipe; cập nhật README run order.
8. `lint-imports` + `just test` + Docker build local + `docker compose -f compose.prod.yml up` smoke (2 service healthy).

## Success Criteria

- [ ] import-linter: bff top layer độc lập; bff↔app không import lẫn nhau; contract xanh.
- [ ] Docker build (1 image 2 CMD) thành công; cả 2 entrypoint chạy.
- [ ] compose: app headless (no public) + bff expose + web→bff; 2 container healthy.
- [ ] CI build + test (gồm bff_test) + deploy 2 service xanh.
- [ ] app restart policy độc lập bff.
- [ ] `pocketquant-config` env xác nhận với user (nếu đổi).

## Risk Assessment

- **pocketquant-config là repo riêng** (CAO — không tự sửa): port/env mới cần user cập nhật `pocketquant-config/vps/default/.env`. Mitigation: liệt kê env cần thêm, hỏi user, KHÔNG commit repo đó.
- **web nginx topology đổi**: nếu nginx hiện proxy→app, đổi→bff; verify nginx conf trong web image trước. Nếu bff serve dist trực tiếp, nginx có thể thừa.
- **1 image kéo cả engine vào bff container**: bff container có code backtest engine dù không chạy. Image lớn hơn nhưng không chạy runtime — chấp nhận (YAGNI tách image). Verify bff process KHÔNG khởi tạo engine (Phase 4 test).
- **Deploy order race**: bff start trước app migrate. Mitigation: `depends_on: app: service_healthy` + app healthy chỉ sau lifespan startup (migration trước yield). Verify app health chỉ 200 sau startup hoàn tất.
- **CI concurrency `cancel-in-progress`**: deploy group cancel — 2 service deploy phải atomic trong 1 job. Giữ 1 deploy job up cả compose.
