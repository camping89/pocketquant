# PocketQuant Docs

Canonical documentation for the current code layout and workflow. Docs are **AS-IS only** — no changelogs, version banners, or change narratives (git is the history). See the Documentation Policy in the project `CLAUDE.md`.

## Reading Order (onboarding path: orient → run → understand → deep-dive → operate)

> Already know the repo? Jump straight to the **Domain Deep-Dives** tier.

### 0. Start Here

| Doc | Description |
|-----|-------------|
| [Root README](../README.md) | Project entry point + hands-on local workflow: what PocketQuant is, install deps, start Mongo/Redis, run API, sync data, run UI, smoke-test, shutdown. **Read first.** |

### 1. Big Picture (orient before code)

| Doc | Description |
|-----|-------------|
| [Project Overview / PDR](./project-overview-pdr.md) | Product vision, scope, functional requirements (F1…). The "why" and "what". |
| [System Architecture](./system-architecture.md) | Deep design reference + **all prose**: Clean Architecture + DDD + CQRS layers, request flows, "Where Does X Live?", collections/ERD reference, whole-system view, bounded contexts, ubiquitous language, config, limitations. |
| [Architecture Visual Map](./architecture-visual-map.md) | **Diagrams only** — ASCII + Mermaid: layer maps, request/data/event flows, DI graph, C4, context map. Visual companion to System Architecture. |
| [System Relationship Map](./system-relationship-map.md) | **Diagrams only** — whole-system forest view: repo secret boundary, build→ship→run, config flow, collection ERD. Prose lives in System Architecture. |

### 2. Conventions (before you write code)

| Doc | Description |
|-----|-------------|
| [Code Standards](./code-standards.md) | Naming, file-size rules, layer dependency direction, DDD aggregate-classification guide, Pyright conventions. |

### 3. Domain Deep-Dives (how features actually work)

| Doc | Description |
|-----|-------------|
| [Strategy Lifecycle](./features/strategy-lifecycle.md) | Template-based strategy model: load → subscribe → backtest → start/stop. `strategy_code` vs `subscription_id`. |
| [Service & Route Conventions](./service-and-route-conventions.md) | Route → service → repository recipe: where routes/services live, DI wiring, command/query models, error handling. API inventory lives in FastAPI OpenAPI (`/api/v1/docs`). |
| [WebSocket Architecture](./websocket-architecture.md) | Outbound WS ingest (Binance `@aggTrade` quotes, OKX orders) + SSE egress (bars, quotes). No server-side WS. |
| [Feature: Add Symbol](./features/feature-add-symbol.md) | Worked example of one feature end-to-end (strategy subscription modal). Template for understanding other slices. |

### 4. Operations

| Doc | Description |
|-----|-------------|
| [Deployment](./deployment.md) | Production deploy via GitHub Actions → Docker Hub → SSH to Vultr VPS. Skill-friendly summary + operator runbook. |

## Current Repo Shape

One Python package (`pocketquant`) at repo-root `src/`; subpackage boundaries are enforced by import-linter contracts in `pyproject.toml` (see [Root README](../README.md) for the authoritative layout).

```text
src/pocketquant/
├── core/       # 0 deps — domain, common, config, ports/DTOs, persisted entities + infra adapters
├── engine/     # → core — shared strategy/order/position/risk engine
├── backtest/   # → core + engine — backtest engine, optimization, run orchestration
├── trading/    # → core + engine — live trading, OKX broker, strategy/subscription
├── app/        # → all — headless runtime: scheduler, WS feed, strategy lifecycle, reconcile, backtest worker
└── bff/        # → all except app — stateless gateway: read/write routes, backtest enqueue
web/        # React 19 + Vite SPA (separate npm app)
```

Dependency direction: `core ◁ engine ◁ {backtest, trading} ◁ {app, bff}`, `web → bff` (HTTP only). `app` and `bff` are independent siblings (no cross-imports). `backtest` and `trading` are independent siblings. `fastapi` may only be imported by `app`/`bff`.

Notes:

- Two processes run from one image (1-image-2-CMD): app (headless, port 41920 internal, `/health` only) and bff (stateless gateway, port 41921 internal, serves all `/api/*` routes).

## Maintenance Note

When documentation conflicts with the code:

- trust `README.md`
- verify routes against FastAPI OpenAPI at `http://localhost:41921/api/v1/docs` (bff, not app)
- fold duplicate content into the canonical doc, delete the duplicate, fix inbound links
