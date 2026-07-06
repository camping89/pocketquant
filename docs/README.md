# PocketQuant Docs

Canonical documentation for the current code layout and workflow. Docs are **AS-IS only** — no changelog, no version banner, no change narrative (git keeps the history). See the Documentation Policy in the project's `CLAUDE.md`.

## Reading Order (orient → run → understand → operate)

| # | Doc                                                 | Description                                                                                                                                                                                                                                                              |
|---|-----------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 0 | [Root README](../README.md)                         | Entry point + local workflow: install deps, run Mongo/Redis, run the API, sync data, run the UI, smoke-test. **Read this first.**                                                                                                                                        |
| 1 | [Project Overview / PDR](./project-overview-pdr.md) | Product vision, scope, functional requirements (F1…F10), non-functional (NF1…NF6). The "why" and "what".                                                                                                                                                                 |
| 2 | [System Architecture](./system-architecture.md)     | The single design reference: layers (Clean Architecture + DDD + CQRS), request flows, "Where Does X Live?", MongoDB ERD, real-time streaming (WS/SSE), strategy lifecycle, DI graph, ops context (CI/CD, config flow), bounded contexts, ubiquitous language, limitations. |
| 3 | [Code Standards](./code-standards.md)               | Naming, file-size rules, dependency direction, route/service/repository conventions, exception handling, async-suspension patterns, testing, worked example end-to-end.                                                                                                  |
| 4 | [Deployment](./deployment.md)                       | Production deploy: GitHub Actions → Docker Hub → SSH to Vultr VPS. Env vars, rollback, operator runbook, port map.                                                                                                                                                       |

### Topic docs

| Doc                                                             | Description                                                                                                                                         |
|-----------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|
| [Engine scale-out limitation](./engine-scale-out-limitation.md) | Why the engine settles one entry → one TP → closes the whole position; four limitation layers that block scale-out / multi-TP / partial close.     |
| [Swing pivot & key-level](./swing-pivot-key-level.md)           | Key-level for take-profit: max/min proxy over an N-bar window, TP = max(RR 1:1, key-level), and why the chart's "show all patterns" differs from the strategy's signal set. |

## Current Repo Shape

One Python package (`pocketquant`) at repo-root `src/`; subpackage boundaries enforced by import-linter contracts in `pyproject.toml` (for the canonical layout see [Root README](../README.md)).

```text
src/pocketquant/
├── core/       # 0 deps — domain, common, config, ports/DTOs, persisted entities + infra adapters
├── engine/     # → core — shared engine with 5 feature areas (strategy, execution, market_data, backtest, live)
└── app/        # → core + engine — FastAPI routes, scheduler, WS feed, strategy lifecycle, reconcile, backtest tasks, SPA serve
web/        # React 19 + Vite SPA (separate npm app)
```

Dependency direction: `core ◁ engine ◁ app`, `web → app` (HTTP only). Backtest and live are two drivers on one shared engine. `fastapi` is imported only by `app`.

Single process: app (FastAPI port 41921, serves all `/api/*` routes + SPA fallback). Scheduler, WS feed, broker, strategy engine run in the same process; single-worker constraint (`--workers 1`).

## Maintenance Note

When documentation conflicts with the code:

- trust `README.md`
- verify routes via FastAPI OpenAPI at `http://localhost:41921/api/v1/docs`
- fold duplicate content into the canonical doc, delete the duplicate, fix inbound links
