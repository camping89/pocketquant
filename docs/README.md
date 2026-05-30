# PocketQuant Docs

This directory holds the canonical documentation for the current code layout and workflow. Docs are **AS-IS only** — no changelogs, version banners, or change narratives (git is the history). See the Documentation Policy in the project `CLAUDE.md`.

**New here?** Start with [Table of Contents](./table-of-contents.md) for a guided reading order.

Start with the canonical set.

## Canonical Docs

- [Root README](../README.md)
  Current setup, backend/frontend startup, sync smoke test, UI smoke test, and shutdown.
- [System Architecture](./system-architecture.md)
  Deeper backend/frontend architecture reference — layers, request flows, "Where Does X Live?", config, dependencies, limitations.
- [Architecture Visual Map](./architecture-visual-map.md)
  ASCII + Mermaid diagrams, bounded contexts, context map, ubiquitous language glossary.
- [System Relationship Map](./system-relationship-map.md)
  Whole-system view: two repos, CI/CD, Docker Hub, VPS runtime, external services, clients — how they relate.
- [Handler Pipelines](./handler-pipelines.md)
  Per-handler request/processing/side-effect detail for all CQRS handlers.
- [Code Standards](./code-standards.md)
  Naming, file-size rules, layer patterns, DDD aggregate-classification guide.
- [Deployment](./deployment.md)
  Production deployment — single source of truth (skill-friendly summary + full operator runbook).
- [Project Overview / PDR](./project-overview-pdr.md)
  Product requirements, scope, roadmap.
- [Strategy Lifecycle](./strategy-lifecycle.md)
  Strategy load → subscribe → backtest → start/stop lifecycle.
- [WebSocket Architecture](./websocket-architecture.md)
  Real-time quote/bar streaming design.

## Features

- [Add Symbol (Strategy Subscription)](./feature-add-symbol.md)

## Current Repo Shape

```text
packages/
├── pocketquant-core/
├── pocketquant-backtest/
├── pocketquant-trading/
├── pocketquant-api/
└── pocketquant-web/
```

Notes:

- `pocketquant-core`, `pocketquant-backtest`, `pocketquant-trading`, and `pocketquant-api` are managed by the root `uv` workspace.
- `pocketquant-web` is a separate npm/Vite app.
- The built web app is served by FastAPI when `packages/pocketquant-web/dist` exists.

## Recommended Reading Order

For setup:

1. [Root README](../README.md)

For implementation work:

1. [System Architecture](./system-architecture.md)
2. [Architecture Visual Map](./architecture-visual-map.md)
3. [Code Standards](./code-standards.md)

For deployment:

1. [Deployment](./deployment.md)

## Maintenance Note

When documentation conflicts with the code:

- trust `README.md`
- verify routes against FastAPI OpenAPI at `http://localhost:41920/api/v1/docs`
