---
phase: 4
title: "DI split and two entrypoints"
status: completed
priority: P1
effort: "10h"
dependencies: [1, 2, 3]
---

# Phase 4: DI split and two entrypoints

## Locked decisions (user-confirmed 2026-06-09, supersede earlier plan guesses)

Verification contradicted the plan's "all market_data is bff-safe / move to bff":

| # | Decision | Value |
|---|----------|-------|
| P4-D1 | App is headless → needs 0 HTTP handlers; only `/health` | confirmed |
| P4-D2 | Shared MD logic home (CQRS handlers + app_services) | **`pocketquant-execution`** (FastAPI-free; both app-runtime + bff import it) |
| P4-D3 | FastAPI routes/routers + `symbol_validation` | **`pocketquant-bff`** (bff is the only HTTP server) |
| P4-D4 | Drop live-runtime quote endpoints FE never calls | **DELETE** `quotes/get_all`, `quotes/get_status`(subscribe-count), `quotes/subscribe`, `quotes/unsubscribe`, `status/get_quote_service_status` (`/market-data/status`) |
| P4-D5 | `current-bar` + `stream-bars` rewire | use `BarAppService.get_current_bar` (Cache→DB, no WS RAM) — bff-safe |
| P4-D6 | bff `BarAppService` | Cache + BarRepository only, NO WS provider |
| P4-D7 | Provider sharing | option C — each package declares own Core+Persistence provider (isolation > DRY) |
| P4-D8 | `/system/jobs` | bff reads Mongo (`apscheduler_jobs` + `job_history`) — no running scheduler |

**Verified runtime-only app_services (STAY in app, do NOT move):** `quote_app_service`, `ws_subscription_manager`, `tracked_symbol_seeder`. **Shared (→execution):** `sync_jobs`, `integrity_jobs`, `cascade_aggregator`, `quote_dto`, `bar_app_service`.
**APScheduler text-ref `_MODULE` in sync_jobs changes** `pocketquant.app...sync_jobs` → `pocketquant.execution...sync_jobs`. VERIFIED self-healing: `register_sync_jobs` re-adds all 5 jobs each boot via `add_cron_job` which sets `replace_existing=True` (scheduler.py:205-style), overwriting stored func refs by job_id. No migration needed.

FE actually calls (verified): backtest/run+strategies, market-data/{ohlcv,symbols,sync-status,bars/stream,integrity/check,integrity/repair}, quotes/{latest,stream,current-bar}, strategies/*, subscriptions/*, system/jobs(+runs/stats). Nothing else.

## Overview

Điểm hợp nhất. Sau Phase 2+3, mọi write-path bff-bound đã = Mongo. Giờ chia DI container thành 2 subset + di chuyển HTTP routes/middleware sang `pocketquant-bff`, để lại app headless với lifespan runtime + 1 `/health`.

- **app**: `create_app_container()` — Core + Persistence + Infrastructure (scheduler/WS provider/broker_factory) + Execution (engine + reconcile) + MarketData (WS manager) + backtest worker. Lifespan: migrations, indexes, recovery, rehydrate, scheduler, WS feed, reconcile, backtest worker. HTTP: chỉ `/health` liveness.
- **bff**: `create_bff_container()` — Core + Persistence (repos) + read/write-DB handlers + serve web. KHÔNG scheduler, KHÔNG WS provider, KHÔNG StrategyAppService, KHÔNG reconcile/worker.

## Requirements

- Functional:
  - 2 container factory chia provider subset rõ ràng.
  - app entrypoint (`pocketquant.app.main`): lifespan giữ toàn bộ runtime; `register_routes` rút gọn còn `/health` (bỏ feature routers + StaticFiles + SPA). KHÔNG mount public API.
  - bff entrypoint (`pocketquant.bff.main`): full FastAPI — middleware stack, exception handlers, mọi feature router hiện tại, StaticFiles serve `pocketquant-web/dist`, SPA fallback. Lifespan bff: chỉ connect Mongo/Redis (cho repos) + health checks. KHÔNG migration/scheduler/WS/reconcile.
  - bff container resolve KHÔNG kéo JobScheduler/StrategyAppService/IRealtimeQuoteProvider/WsSubscriptionManager/reconcile/worker.
  - app container resolve đủ runtime; KHÔNG kéo handler HTTP nào cần thiết cho serve (app không serve).
- Non-functional:
  - Provider chung (Core, Persistence) DRY — không copy 2 bản. Đặt provider ở `pocketquant.app.di` rồi bff import lại subset? hay tách provider sang chỗ chung? — xem Architecture.
  - import-linter: bff không import app, app không import bff (Phase 6 enforce).

## Architecture

### Provider sharing — tránh trùng lặp

Provider hiện ở `pocketquant.app.di.*` (CoreProvider, PersistenceProvider, InfrastructureProvider, ExecutionProvider, MarketDataProvider, HandlerProvider). bff cần Core + Persistence + 1 HandlerProvider-subset (chỉ read/write-DB handlers).

Lựa chọn (chốt khi implement, mặc định A):

- **(A) Giữ provider ở `pocketquant.app.di`, bff import cái nó cần**: `pocketquant.bff` import `CoreProvider, PersistenceProvider` từ `pocketquant.app.di`. NHƯNG điều này tạo cạnh `bff → app` (vi phạm "2 top layer độc lập"). ❌ Không được.
- **(B) Hạ provider chung xuống tầng thấp hơn**: provider thuần wiring; CoreProvider/PersistenceProvider có thể đặt ở 1 module dùng chung mà cả app+bff import — nhưng provider import từ infrastructure/core nên hợp lệ ở bất kỳ top package. Đặt shared providers ở **`pocketquant-infrastructure`**? Provider là Dishka-specific wiring, không phải hạ tầng thuần. Đặt ở 1 package neutral.
- **(C) Mỗi package tự khai provider của mình**: app có DI riêng (đã có), bff khai CoreProvider + PersistenceProvider + BffHandlerProvider riêng trong `pocketquant.bff.di`. Trùng ~30 dòng provider Core+Persistence nhưng **ranh giới cứng, 0 cross-import**. Theo DRY-vs-isolation trade-off, isolation thắng ở đây (2 process độc lập là mục tiêu).

**Mặc định (C)** — mỗi package tự khai provider. Core+Persistence provider nhỏ (~50 dòng tổng); copy chấp nhận được để đổi lấy ranh giới cứng + import-linter sạch. Handler subset khác nhau hẳn (app không serve, bff không runtime) nên HandlerProvider vốn đã phải tách.

→ Xác nhận: liệu có thể trích Core+Persistence provider thành package chung nhỏ không tốn? Nếu phát sinh cạnh import xấu thì theo (C). Quyết định cuối khi đọc Dishka provider import graph lúc implement.

### Routes ownership

| Route group | app | bff |
|-------------|-----|-----|
| `/health` (liveness) | ✅ minimal | ✅ (readiness w/ DB+Redis) |
| market_data read (ohlcv, symbols, sync-status, status, stream) | — | ✅ |
| market_data write (sync, sync/bulk, integrity) | — | ✅ (stateless DB write) |
| tracked_symbols (add/remove/update/list/backfill) | — | ✅ |
| quotes (latest/all/status/stream/subscribe) | — | ✅ |
| system/jobs (list) | — | ✅ (đọc job_history + scheduler state?) ⚠ xem risk |
| strategy/subscription (start/stop/add/remove/delete/list/get) | — | ✅ (pure Mongo sau Phase 3) |
| backtest (run/run-all/get/list/optimize) | — | ✅ enqueue + read (sau Phase 2) |
| StaticFiles + SPA serve web/dist | — | ✅ |

### app lifespan vs bff lifespan

- **app lifespan** (giữ nguyên `main.py` hiện tại trừ register_routes): migrations → indexes → recovery → seed → rehydrate → health → background jobs → quote feed → reconcile → backtest worker.
- **bff lifespan** (mới, tối giản): connect Database+Cache (cho repos qua DI) → register handlers (chỉ subset bff cần cho Mediator) → register health checks. KHÔNG migration/indexes (app làm; bff giả định schema sẵn sàng) → KHÔNG scheduler/WS/reconcile/worker.

### system/jobs route ⚠

`/system/jobs` đọc `JobScheduler.get_jobs()` — cần scheduler instance. bff không chạy scheduler. 2 cách: (a) bff đọc trực tiếp `job_history` repo + `apscheduler_jobs` collection (read-only, không cần scheduler running); (b) bỏ route khỏi bff (chỉ debug, FE `monitor-api.ts` có gọi `/system/jobs`). Verify FE dùng → giữ qua đường đọc Mongo trực tiếp (a). Cần `JobScheduler.get_jobs()` refactor để đọc store không cần `_scheduler` running, HOẶC repo method mới.

## Related Code Files

- Create: `packages/pocketquant-bff/src/pocketquant/bff/di/` — container + provider subset (Core, Persistence, BffHandler)
- Create: `packages/pocketquant-bff/src/pocketquant/bff/main.py` — full FastAPI (move từ app main.py + main_extensions.py phần routes/middleware)
- Create: `packages/pocketquant-bff/src/pocketquant/bff/main_extensions.py` — configure_middleware + register_routes + register_health_checks (move từ app)
- Modify: `packages/pocketquant-app/.../main.py` — bỏ `register_routes` feature, `create_app` chỉ mount `/health`; giữ lifespan runtime
- Modify: `packages/pocketquant-app/.../main_extensions.py` — bỏ configure_middleware/register_routes phần feature + StaticFiles; giữ migrations/recovery/lifecycle helpers
- Modify: `packages/pocketquant-app/.../di/handlers.py` — app không cần HTTP handler subset cho serve; nhưng worker/reconcile cần Mediator? verify Mediator usage runtime-side
- Modify: `packages/pocketquant-app/pyproject.toml` — siết deps nếu app không còn cần fastapi-full (vẫn cần fastapi cho /health + lifespan)
- Modify: `packages/pocketquant-bff/pyproject.toml` — deps thật (core+infra+backtest+trading+fastapi+dishka; KHÔNG cần execution nếu không import engine — verify)
- Read context: `app/main.py`, `app/main_extensions.py`, `app/di/*.py`, FE `monitor-api.ts` (system/jobs usage)

## Implementation Steps

1. **TEST FIRST** — `tests/bff_test/test_bff_container_no_runtime.py`:
   - `create_bff_container()` resolve được mọi BffHandler + repos.
   - resolve KHÔNG khởi tạo JobScheduler (mock/spy: scheduler.start không gọi); KHÔNG StrategyAppService; KHÔNG IRealtimeQuoteProvider; KHÔNG reconcile/worker.
2. **TEST FIRST** — `tests/app_test/test_app_headless_no_public_routes.py`:
   - app FastAPI có `/health`; KHÔNG có `/api/v1/market-data/...`, KHÔNG StaticFiles mount.
   - app lifespan start scheduler+WS+reconcile+worker (gated enable_jobs).
3. Chia provider: tạo `pocketquant.bff.di` với CoreProvider + PersistenceProvider (copy/share theo quyết định C) + BffHandlerProvider (subset handlers read/write-DB — start/stop/add/remove/delete/list/get + market_data + quotes + backtest enqueue/read + tracked_symbols).
4. Move routes/middleware: tạo `pocketquant.bff.main` + `main_extensions` từ app's `register_routes`/`configure_middleware`/StaticFiles/SPA. Import routers từ `trading`/`backtest`/`app.market_data`. ⚠ market_data handlers/routers hiện ở `pocketquant.app.market_data` — bff cần import chúng. Cạnh `bff → app.market_data`? Đây vi phạm độc lập 2 top layer. **Quyết định**: market_data handlers move sang đâu? Option: giữ ở app nhưng bff import (tạo cạnh xấu) HOẶC move market_data routes/handlers xuống package thấp hơn / sang bff. Xem risk — có thể cần move `app.market_data` → vùng dùng chung. **Chốt: market_data read/write handlers move sang `pocketquant-bff`** (chúng là HTTP-facing, không phải runtime); chỉ `WsSubscriptionManager` + `sync_jobs` (background) ở lại app.
5. Trim app: `create_app` chỉ `/health`; xóa feature router includes + StaticFiles khỏi app.
6. Refactor `/system/jobs` đọc Mongo trực tiếp (repo method) để bff serve không cần scheduler running.
7. bff lifespan tối giản (connect DB/Cache + register subset handlers + health). app lifespan giữ runtime.
8. Wire entrypoints: `pocketquant.app.main:run` (headless uvicorn /health port), `pocketquant.bff.main:run` (full, web port).
9. `uv sync`; `uv run pocketquant` (app headless) + `uv run pocketquant-bff` (gateway) chạy song song local; smoke: FE→bff OK, app không expose public.
10. `just test` toàn bộ + lint + types.

## Success Criteria

- [ ] bff container resolve KHÔNG có scheduler/WS/engine/reconcile/worker (test).
- [ ] app FastAPI chỉ `/health`, không public routes/StaticFiles (test).
- [ ] app lifespan chạy đủ runtime; bff lifespan chỉ DB/Cache + handlers.
- [ ] market_data HTTP handlers ở bff; WS background ở app.
- [ ] `/system/jobs` serve được từ bff (đọc Mongo, không cần scheduler).
- [ ] 2 process chạy song song; FE→bff hoạt động; app headless auto-trade.
- [ ] Full suite + lint + types xanh.

## Risk Assessment

- **market_data handlers ở `pocketquant.app`**: bff import chúng tạo cạnh `bff → app` (vi phạm độc lập). Mitigation: move HTTP market_data handlers sang `pocketquant-bff` (Step 4); chỉ background WS/sync ở app. Đây là move lớn nhất của Phase 4 — blast radius: imports trong app DI, tests app_test market_data. Verify kỹ.
- **Provider duplication (C)**: copy Core+Persistence provider 2 chỗ → drift sau này. Mitigation: provider mỏng, chỉ wiring; chấp nhận để đổi lấy ranh giới cứng. Ghi comment WHY.
- **Mediator ở app**: reconcile/worker có gọi Mediator không? Nếu không, app không cần HandlerProvider/Mediator → nhẹ. Verify: `integrity_repair` dùng Mediator nhưng đó là bff route. Worker gọi engine trực tiếp (không Mediator). → app có thể bỏ Mediator. Confirm khi implement.
- **bff không cần execution package**: nếu bff không import StrategyAppService/engine, gỡ `pocketquant-execution` khỏi bff deps (trading kéo theo transitive vẫn OK cho import nhưng runtime không khởi tạo). Verify import graph.
- **2 process cùng connect Mongo, chỉ app migrate**: bff giả định schema/index sẵn. Nếu bff start trước app (chưa migrate) → bff đọc shape cũ. Mitigation: deploy order app trước bff (Phase 6 compose depends_on); bff chỉ đọc, migration idempotent.
- **app /health vs bff /health khác mức**: app=liveness (process sống), bff=readiness (DB+Redis). Tách rõ ở docker healthcheck Phase 6.
