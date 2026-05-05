# PocketQuant Docs

This directory mixes two kinds of documentation:

- canonical docs for the current local workflow and code layout
- deeper design notes that are still useful, but may contain older naming or historical detail

Start with the canonical set.

## Canonical Docs

- [Root README](../README.md)
  Current setup, backend/frontend startup, sync smoke test, and UI smoke test.
- [Run And Test Guide](./run-and-test-guide.md)
  Step-by-step local workflow for running the API, syncing data, running the UI, and testing both.
- [Codebase Summary](./codebase-summary.md)
  Current package map, route groups, runtime flows, and testing assets.
- [System Architecture](./system-architecture.md)
  Deeper backend/frontend architecture reference.
- [Deployment Guide](./deployment-guide.md)
  Production deployment notes.

## Specialized Deep Dives

- [Project Overview / PDR](./project-overview-pdr.md)
- [Handler Pipelines](./handler-pipelines.md)
- [DDD Strategic Map](./ddd-strategic-map.md)
- [Architecture Visual Map](./architecture-visual-map.md)
- [Code Standards](./code-standards.md)
- [Debug Audit: Order Execution](./debug-audit-order-execution.md)
- [Migration Doubts And Notes](./migration-doubts-and-notes.md)
- [Project Changelog](./project-changelog.md)

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
2. [Run And Test Guide](./run-and-test-guide.md)

For implementation work:

1. [Codebase Summary](./codebase-summary.md)
2. [System Architecture](./system-architecture.md)
3. [Code Standards](./code-standards.md)

For deployment:

1. [Deployment Guide](./deployment-guide.md)

## Maintenance Note

When documentation conflicts with the code:

- trust `README.md`
- trust `docs/run-and-test-guide.md`
- verify routes against FastAPI OpenAPI at `http://localhost:41920/api/v1/docs`
