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
| [Strategy Lifecycle](./strategy-lifecycle.md) | Template-based strategy model: load → subscribe → backtest → start/stop. `strategy_code` vs `subscription_id`. |
| [Handler Pipelines](./handler-pipelines.md) | Per-handler request/processing/side-effect detail for all CQRS handlers. The API-level reference. |
| [WebSocket Architecture](./websocket-architecture.md) | Outbound WS ingest (Binance `@aggTrade` quotes, OKX orders) + SSE egress (bars, quotes). No server-side WS. |
| [Feature: Add Symbol](./features/feature-add-symbol.md) | Worked example of one feature end-to-end (strategy subscription modal). Template for understanding other slices. |

### 4. Operations

| Doc | Description |
|-----|-------------|
| [Deployment](./deployment.md) | Production deploy via GitHub Actions → Docker Hub → SSH to Vultr VPS. Skill-friendly summary + operator runbook. |

## Current Repo Shape

```text
packages/
├── pocketquant-core/           # 0 deps — domain, concepts, common, config, ports + DTOs, persisted entities
├── pocketquant-infrastructure/ # → core — Database, Cache, repositories, PaperBroker, binance, scheduler, http
├── pocketquant-execution/      # → core + infra — shared strategy/order/position/risk engine
├── pocketquant-backtest/       # → core + infra + execution — backtest engine, optimization, run orchestration
├── pocketquant-trading/        # → core + infra + execution — live trading, OKX broker, strategy/subscription
├── pocketquant-app/            # → all above — FastAPI, DI container, route composition
└── pocketquant-web/            # React 19 + Vite SPA (separate npm app, excluded from uv workspace)
```

Dependency direction: `core ◁ infrastructure ◁ execution ◁ {backtest, trading} ◁ app`, `web → app` (HTTP only). `backtest` and `trading` are independent siblings.

Notes:

- The 5 Python packages share the `pocketquant.*` namespace and form the `uv` workspace.
- `pocketquant-web` is a separate npm/Vite app, **excluded** from the uv workspace.
- The built web app is served by FastAPI when `packages/pocketquant-web/dist` exists.

## Maintenance Note

When documentation conflicts with the code:

- trust `README.md`
- verify routes against FastAPI OpenAPI at `http://localhost:41920/api/v1/docs`
- fold duplicate content into the canonical doc, delete the duplicate, fix inbound links
