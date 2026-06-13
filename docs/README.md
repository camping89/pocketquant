# PocketQuant Docs

Tài liệu canonical cho code layout và workflow hiện tại. Docs là **AS-IS only** — không changelog, không version banner, không change narrative (git giữ lịch sử). Xem Documentation Policy trong `CLAUDE.md` của project.

## Reading Order (orient → run → understand → operate)

| # | Doc | Description |
|---|-----|-------------|
| 0 | [Root README](../README.md) | Entry point + local workflow: cài deps, chạy Mongo/Redis, chạy API, sync data, chạy UI, smoke-test. **Đọc trước tiên.** |
| 1 | [Project Overview / PDR](./project-overview-pdr.md) | Product vision, scope, functional requirements (F1…F10), non-functional (NF1…NF6). Phần "why" và "what". |
| 2 | [System Architecture](./system-architecture.md) | Design reference duy nhất: layers (Clean Architecture + DDD + CQRS), request flows, "Where Does X Live?", MongoDB ERD, real-time streaming (WS/SSE), strategy lifecycle, DI graph, ops context (CI/CD, config flow), bounded contexts, ubiquitous language, limitations. |
| 3 | [Code Standards](./code-standards.md) | Naming, file-size rules, dependency direction, route/service/repository conventions, exception handling, async-suspension patterns, testing, worked example end-to-end. |
| 4 | [Deployment](./deployment.md) | Production deploy: GitHub Actions → Docker Hub → SSH tới Vultr VPS. Env vars, rollback, operator runbook, port map. |

## Current Repo Shape

One Python package (`pocketquant`) tại repo-root `src/`; subpackage boundaries enforced bởi import-linter contracts trong `pyproject.toml` (layout chuẩn xem [Root README](../README.md)).

```text
src/pocketquant/
├── core/       # 0 deps — domain, common, config, ports/DTOs, persisted entities + infra adapters
├── engine/     # → core — shared strategy/order/position/risk engine
├── backtest/   # → core + engine — backtest engine, optimization, run orchestration
└── app/        # → core + engine + backtest — FastAPI routes, scheduler, WS feed, strategy lifecycle, reconcile, backtest worker, SPA serve
web/        # React 19 + Vite SPA (separate npm app)
```

Dependency direction: `core ◁ engine ◁ backtest ◁ app`, `web → app` (HTTP only). `fastapi` chỉ được import bởi `app`.

Single process: app (FastAPI port 41921, serve toàn bộ `/api/*` routes + SPA fallback). Scheduler, WS feed, broker, strategy engine chạy chung process; ràng buộc single-worker (`--workers 1`).

## Maintenance Note

Khi documentation mâu thuẫn với code:

- tin `README.md`
- verify routes qua FastAPI OpenAPI tại `http://localhost:41921/api/v1/docs`
- fold nội dung trùng vào doc canonical, xóa bản trùng, sửa inbound links
