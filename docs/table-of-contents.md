# Docs Table of Contents

Reading order for the PocketQuant docs. Top to bottom = onboarding path: orient → run → understand → deep-dive → operate.

> Already know the repo? Jump straight to the **Domain Deep-Dives** tier.

## 0. Start Here

| # | Doc | Short Description |
|---|-----|-------------------|
| 1 | [Root README](../README.md) | Project entry point. What PocketQuant is, setup, backend/frontend startup, sync + UI smoke tests. **Read first.** |
| 2 | [Run And Test Guide](./run-and-test-guide.md) | Step-by-step local workflow: install deps, start Mongo/Redis, run API, sync data, run the UI, test both. Hands-on. |

## 1. Big Picture (orient before code)

| # | Doc | Short Description |
|---|-----|-------------------|
| 3 | [Project Overview / PDR](./project-overview-pdr.md) | Product vision, scope, functional requirements (F1…), roadmap. The "why" and "what". |
| 4 | [System Architecture](./system-architecture.md) | Deep design reference: Clean Architecture + DDD + CQRS layers, request flows, "Where Does X Live?", config, limitations. |
| 5 | [Architecture Visual Map](./architecture-visual-map.md) | ASCII + Mermaid diagrams, bounded contexts, context map, ubiquitous-language glossary. Visual companion to #4. |

## 2. Conventions (before you write code)

| # | Doc | Short Description |
|---|-----|-------------------|
| 6 | [Code Standards](./code-standards.md) | Naming, file-size rules, layer dependency direction, DDD aggregate-classification guide, Pyright conventions. |

## 3. Domain Deep-Dives (how features actually work)

| # | Doc | Short Description |
|---|-----|-------------------|
| 7 | [Strategy Lifecycle](./strategy-lifecycle.md) | Template-based strategy model: load → subscribe → backtest → start/stop. `strategy_code` vs `subscription_id`. |
| 8 | [Handler Pipelines](./handler-pipelines.md) | Per-handler request/processing/side-effect detail for all 37 CQRS handlers. The API-level reference. |
| 9 | [WebSocket Architecture](./websocket-architecture.md) | Outbound WS clients only: Binance `@aggTrade` market-data stream + OKX private order/position stream. No server-side WS. |
| 10 | [Feature: Add Symbol](./feature-add-symbol.md) | Worked example of one feature end-to-end (strategy subscription modal). Template for understanding other slices. |

## 4. Operations

| # | Doc | Short Description |
|---|-----|-------------------|
| 11 | [Deployment](./deployment.md) | Production deploy via GitHub Actions → Docker Hub → SSH to Vultr VPS. Skill-friendly summary + operator runbook. |
| 12 | [Project Changelog](./project-changelog.md) | Version history and notable changes (Semantic Versioning). Check here for recent breaking changes. |

## Index

- [docs/README.md](./README.md) — canonical alphabetical index of all docs (no reading order).
