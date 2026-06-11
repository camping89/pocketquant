---
phase: 3
title: "Merge bff into app single process"
status: pending
priority: P1
effort: "6h"
dependencies: [2]
---

# Phase 3: Merge bff into app single process

## Overview

Gộp `pocketquant.bff` vào `pocketquant.app`: 1 FastAPI app, 1 DI container, 1 lifespan (full runtime: migrations, indexes, scheduler, WS feed, reconcile, backtest worker) + toàn bộ feature routes + SPA serving, listen `:41921`. Xóa toàn bộ bản DI copy của bff. Bug 500 `/trading/orders|positions` tự hết. Gỡ xfail (`test_dissolved_subpackages_are_gone`) từ Phase 1.

## Context Links

- Brainstorm: [report](../reports/brainstorm-260611-1651-collapse-six-subpackages-to-four-single-process-report.md)
- Đảo ngược một phần SP3 ([plan cũ](../260609-1546-sp3-split-app-and-bff/plan.md)) — user xác nhận 2026-06-11: "we only need one entry point from backend side".

## Key Insights

- `bff/di/` là isolated copy của `app/di/` (tự nhận trong docstring). Phần bff có mà app thiếu: `BffServiceProvider` (`bff/di/services.py` — query/command services cho routes) và admin auth dependency. Phần app có mà bff thiếu: execution, market_data WS, backtest worker, scheduler.
- **DI dedupe bắt buộc** <!-- red-team: dishka 1.9.1 duplicate provide = silent last-wins, không error -->: union container có 3 type đăng ký TRÙNG: `StrategyCommandService` + `StrategyQueryService` (`app/di/trading_services.py:17-18` vs `bff/di/services.py:30-31`), `SyncService` (`app/di/market_data.py:24` vs `bff/di/services.py:25`). Dishka không báo lỗi — provider sau thắng thầm lặng. Khi merge: STRIP 3 provides này khỏi services provider ex-bff, giữ bản của app. Mỗi type đúng 1 registration.
- `OrderPositionQueryService` đã đăng ký trong `app/di/trading_services.py:20` → routes mount cùng process resolve được → 500 thành 200. KHÔNG cần code mới cho fix này (đã verify chain: ExecutionProvider cấp OrderAppService/PositionAppService).
- `bff/main_extensions.py` (162 LOC): `register_routes` (mount 9 routers + SPA fallback + `/health`), `configure_middleware` (byte-tương-đương bản app), `register_health_checks`. `app/main_extensions.py` (530 LOC): lifecycle jobs + `/health`. Merge: **REPLACE** body `register_routes` của app bằng bản bff (KHÔNG đắp thêm — cả 2 đều đăng ký `/health`, cộng dồn sẽ duplicate route và lệch snapshot).
- OpenAPI snapshot: routes y hệt bff hiện tại → chỉ `info.title` + `info.description` đổi. LƯU Ý: bff hardcode `title="PocketQuant BFF"` (`bff/main.py:68`) còn app dùng `title=settings.app_name` — main mới PHẢI hardcode literal `"PocketQuant"`, nếu lấy từ settings thì snapshot phụ thuộc env (`APP_NAME=pocketquant-test` trong tests/conftest.py).
- `bff/system_jobs/route.py`, `bff/middleware/admin_auth_middleware.py`, `bff/common/symbol_validation.py`, `bff/routes/**` → move nguyên vẹn sang `app/`.
- **`tests/bff_test/` KHÔNG move mechanical được** <!-- red-team: suite này assert điều ngược lại end-state -->: `tests/bff_test/integration/test_bff_stateless_serve.py:44-69` (`test_bff_container_cannot_resolve_runtime`) assert `NoFactoryError` cho `JobScheduler`/`StrategyAppService`/`StrategyReconcileService`/`BacktestRequestWorker` — trong container hợp nhất tất cả resolve OK (chính là bug fix của plan). Xử lý: XÓA test đó (guarantee đảo có chủ đích); `test_bff_start_writes_desired_state_only` (`:96-101`) viết lại trên factory không start reconcile loop (invariant declarative write vẫn đáng giữ); `test_bff_serves_seeded_read` giữ làm route test thường. Factory files thực tế: `tests/app_test/integration/app_factory.py` + `bff_factory.py` (không có `bff_app_factory.py`) — hợp nhất thành 1.
- Port 41920 consumers ngoài justfile/bruno: `deploy/Dockerfile:54,56,58` (HEALTHCHECK/EXPOSE/CMD default) và `src/pocketquant/app/main.py:132` (`run()` hardcode 41920 — entrypoint console script `pocketquant`, `pyproject.toml:30`). Cả hai phải sang 41921 trong phase này (Dockerfile default đúng giúp `docker run` trần không chết cổng).
- `pyproject.toml:31` có console script `pocketquant-bff = "pocketquant.bff.main:run"` — phải xóa, grep sweep `src tests` không nhìn thấy pyproject.

## Requirements

- Functional: toàn bộ routes của bff serve y hệt từ app process; lifecycle jobs (scheduler, WS, reconcile, worker) chạy như app cũ; SPA serving + fallback giữ nguyên.
- Non-functional: `pocketquant.bff` không importable; không còn DI duplication; 1 entrypoint duy nhất.

## Architecture

```text
src/pocketquant/app/            # SAU PHASE 3
├── di/
│   ├── container.py            # 1 factory duy nhất: app providers + ServicesProvider (ex-bff)
│   ├── services.py             # NEW HOME: ex-bff/di/services.py (query/command services)
│   ├── core.py / persistence.py / market_data.py / ...  # giữ bản app, xóa bản bff
├── routes/                     # ex-bff/routes/** + ex-bff/system_jobs/route.py
├── middleware/                 # ex-bff/middleware/admin_auth_middleware.py
├── common/                     # ex-bff/common/symbol_validation.py
├── market_data/                # giữ nguyên
├── main.py                     # lifespan = app cũ (full runtime) + routes = bff cũ; port 41921
└── main_extensions.py          # merge: lifecycle (app) + register_routes/SPA (bff)
```

Layers cuối: `core ◁ engine ◁ backtest ◁ app`.

## Related Code Files

- Move: `bff/routes/**` → `app/routes/`; `bff/system_jobs/route.py` → `app/routes/system_jobs.py`; `bff/middleware/**` → `app/middleware/`; `bff/common/**` → `app/common/`; `bff/di/services.py` → `app/di/services.py` (strip 3 duplicate provides — xem Key Insights)
- Modify: `app/di/container.py` (thêm ServicesProvider), `app/di/__init__.py`, `app/main.py` (title hardcode "PocketQuant", description, docs_url; `run()` port 41920→41921), `app/main_extensions.py` (REPLACE register_routes bằng bản bff + SPA, sửa docstring "headless")
- Delete: `src/pocketquant/bff/` toàn bộ (main, main_extensions, di/ copies)
- Modify (config): `pyproject.toml` — import-linter (layer `"pocketquant.app | pocketquant.bff"` → `"pocketquant.app"`, xóa contract bff-isolation; gỡ `pocketquant.bff` khỏi `source_modules` contract fastapi-containment — source thiếu module = hard-error) + XÓA console script `pocketquant-bff` (`pyproject.toml:31`); `justfile` (`just be` port 41921, xóa `just bff`); `deploy/Dockerfile:54,56,58` (HEALTHCHECK/EXPOSE/CMD → 41921)
- Modify (tests): `tests/baseline/test_openapi_snapshot.py:25` + `test_route_inventory.py:21` (cả hai import `pocketquant.bff.main` — repoint sang `pocketquant.app.main` TRƯỚC, diff với snapshot đã commit, RỒI mới regenerate; đổi tên snapshot files `*_bff_*` → app), `test_app_boot_smoke.py` (1 entrypoint), `test_package_layout_contract.py` (gỡ xfail), `tests/bff_test/**` → `tests/app_test/` theo enumeration ở Key Insights, `tests/http/environments/local.bru` (base_url 41920 → 41921)
- Modify (docstrings): `engine/orders_positions_service.py` + `app/routes/trading_orders_positions.py` — xóa đoạn "bff will return 500" (không còn đúng)

## Implementation Steps

1. **TDD-lock:** viết test mới `test_single_entrypoint_serves_all_routes` (import `pocketquant.app.main`, assert route inventory == bff inventory cũ NGUYÊN VĂN — `/health` đã nằm trong snapshot bff, KHÔNG cộng thêm). Test này ĐỎ bây giờ — đúng TDD.
2. Move files theo bảng Related Code Files (`git mv`). Khi move `bff/di/services.py`: strip 3 provides trùng (`StrategyCommandService`, `StrategyQueryService`, `SyncService`) — giữ bản app.
3. `app/di/container.py`: thêm `ServicesProvider` (ex-bff, đã dedupe) vào danh sách providers. Xóa toàn bộ `bff/di/` copies. Verify: mỗi type đúng 1 provider (dishka silent last-wins, không tự báo).
4. `app/main_extensions.py`: REPLACE body `register_routes` bằng bản bff (routes + SPA fallback + /health — không giữ /health bản app, tránh duplicate); giữ nguyên toàn bộ lifecycle functions. Sửa module docstring (app không còn headless).
5. `app/main.py`: FastAPI `title="PocketQuant"` (hardcode literal — không dùng settings.app_name kẻo snapshot lệch theo env), description merge, docs_url giữ `/api/v1/docs`; `run()` đổi port 41921; gọi register_routes mới.
6. Xóa `src/pocketquant/bff/`.
7. Import sweep: `grep -rn "pocketquant.bff" src tests pyproject.toml justfile` → sửa hết → rỗng (pyproject có console script `pocketquant-bff` phải xóa).
8. `pyproject.toml`: layer top tier thành `"pocketquant.app"`; xóa contracts riêng của bff; gỡ `pocketquant.bff` khỏi `source_modules` fastapi-containment. Chạy `just lint-imports`.
9. Tests — thứ tự bắt buộc: (a) repoint imports `pocketquant.bff.main` → `pocketquant.app.main` trong `test_openapi_snapshot.py` + `test_route_inventory.py`; (b) chạy diff với snapshot ĐÃ COMMIT — diff PHẢI chỉ ở `info.title`/`info.description`, mọi diff path khác = bug, dừng điều tra; (c) RỒI mới regenerate + rename snapshot files. Merge `bff_test` vào `app_test` theo enumeration Key Insights (xóa `test_bff_container_cannot_resolve_runtime`, viết lại desired-state test, giữ seeded-read test; hợp nhất `app_factory.py`/`bff_factory.py`). Sửa baseline boot smoke; gỡ xfail Phase 1 (strict=True tự nhắc nếu quên).
10. justfile: `just be` chạy `uvicorn pocketquant.app.main:app --port 41921`; xóa recipe `bff`; sửa comment test-sub (core, engine, backtest, app). Ghi chú recipe: dev route-iteration nên chạy `ENABLE_JOBS=false just be` — `enable_jobs` đã gate scheduler/reconcile/worker sẵn, tránh `--reload` reboot full trading runtime mỗi lần save. `deploy/Dockerfile`: HEALTHCHECK/EXPOSE/CMD → 41921. `tests/http/environments/local.bru` → `http://localhost:41921`.
11. Smoke thủ công: `just be` → mở `/api/v1/docs`, gọi `GET /api/v1/trading/orders` → **200** (bug fix verify), `GET /health` → 200.
12. Full gates xanh. Commit nhưng **KHÔNG push lên develop** — CI auto-deploy mỗi push develop; image thiếu `pocketquant.bff` sẽ crash-loop container bff cũ trên VPS (compose cũ vẫn gọi `uvicorn pocketquant.bff.main:app`) → outage. Push chung với Phase 4 thành 1 đợt (xem plan.md "Deployment atomicity"). Commit message: `refactor(structure): merge bff into app — one process, one container, one entrypoint`.

## Todo List

- [ ] TDD-lock: single-entrypoint route test viết trước (đỏ; inventory == bff cũ nguyên văn)
- [ ] Move routes/middleware/common/di-services sang app (di-services strip 3 duplicate provides)
- [ ] Container hợp nhất — mỗi type đúng 1 provider; bff DI copies xóa
- [ ] main (title hardcode, run() 41921) + main_extensions (REPLACE register_routes) merge
- [ ] bff/ dir xóa; sweep `src tests pyproject.toml justfile` rỗng; console script pocketquant-bff xóa
- [ ] import-linter contracts cập nhật (cả source_modules)
- [ ] Tests: repoint imports → diff snapshot commit → regenerate + rename; bff_test merge theo enumeration
- [ ] Gỡ xfail Phase 1
- [ ] justfile (+ ENABLE_JOBS=false note) + Dockerfile 41921 + bruno env cập nhật
- [ ] Smoke: /trading/orders 200
- [ ] Full gates xanh, commit — KHÔNG push (đợi Phase 4, atomic deploy)

## Success Criteria

- [ ] `find src/pocketquant -maxdepth 1 -type d` → core, engine, backtest, app
- [ ] `grep -rn "pocketquant.bff" src tests` → rỗng
- [ ] 1 process `:41921` serve: tất cả API routes + /health + SPA; scheduler/WS/reconcile/worker chạy in-process
- [ ] `GET /api/v1/trading/orders` → 200
- [ ] OpenAPI snapshot diff chỉ ở `info.title`/`info.description`
- [ ] Full gates xanh, 0 xfail còn lại

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Lifespan nặng (migrations, rehydrate, WS connect) giờ chặn API readiness — happy path không tăng thời gian, nhưng **blast radius khi boot FAIL đổi hẳn**: trước đây app crash-loop thì bff vẫn serve toàn bộ API; sau merge, crash loop (vd `_rename_collection_if_needed` raise khi cả 2 collection tồn tại — `main_extensions.py:150-154`, hoặc rehydrate raise trên subscription doc hỏng) = API chết hoàn toàn + OKX connect/disconnect churn mỗi vòng restart | Document trade-off (user đã chấp nhận single process); cân nhắc trong phase: wrap các boot step không thiết yếu (rehydrate, recover_*) thành catch-log-degrade thay vì fail-fast — quyết khi implement, default giữ fail-fast cho migrations/indexes (schema phải đúng trước khi serve) |
| Duplicate DI provides silent last-wins (dishka không error) | Bước 2-3: strip 3 provides trùng; review checklist "mỗi type 1 provider" |
| Route nào đó của bff phụ thuộc state mà app lifespan thay đổi (DB/Cache trên app.state) | Cả 2 main đều set `app.state.database/cache` — giữ nguyên pattern |
| Backtest/optimization CPU-bound làm chậm API (mất SP3 isolation) | User đã chấp nhận; grid optimizer bounded bởi semaphore `max_workers`; ghi nhận theo dõi, ngoài scope. CẤM chữa bằng `--workers N` — xem ghi chú single-worker Phase 4 |
| `--reload` dev giờ reboot full trading runtime mỗi save | `ENABLE_JOBS=false just be` cho route iteration (enable_jobs đã gate scheduler/reconcile/worker — `main_extensions.py:361,417,447`) |
| Snapshot regenerate che giấu diff thật | Thứ tự bắt buộc bước 9: repoint import → diff với snapshot commit → mới regenerate; jq path-level chỉ cho phép `info.title`, `info.description` |

## Security Considerations

- Admin auth là **route-level dependency** (`Depends(verify_admin_token)`), không phải middleware — `configure_middleware` hai bên byte-tương-đương nên không có thứ tự middleware để verify. Check thật sự: sau move, mọi route đang gắn `Depends(verify_admin_token)` (hiện chỉ `tracked_symbols.py:36,48,67,93`) giữ nguyên dependency.
- **Ghi nhận (pre-existing, ngoài scope):** phần lớn mutation routes (strategy start/stop/delete, backtest run/optimize, sync, integrity repair) KHÔNG có admin token — và `/trading/orders|positions` sau fix 500→200 sẽ trả live positions không auth. Toàn bộ chỉ reachable qua nginx nội bộ + `admin_token` unset = dev mode skip. Không đổi trong plan này; cân nhắc plan riêng về auth coverage.
- App process giờ expose public API VÀ giữ OKX credentials in-RAM — chấp nhận (trước đây bff cũng cùng image, cùng .env). Giữ nguyên: không publish port app ra host trong prod compose.

## Next Steps

- Phase 4: compose/nginx/deploy scripts + docs sync.
