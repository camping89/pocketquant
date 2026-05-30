# Docs Table of Contents

Reading order for the PocketQuant docs. Top to bottom = onboarding path: orient → run → understand → deep-dive → operate.

> Already know the repo? Jump straight to the **Domain Deep-Dives** tier.

## 0. Start Here

| # | Doc | Short Description |
|---|-----|-------------------|
| 1 | [Root README](../README.md) | Project entry point and hands-on local workflow: what PocketQuant is, install deps, start Mongo/Redis, run API, sync data, run the UI, smoke-test both, shutdown. **Read first.** |

## 1. Big Picture (orient before code)

| # | Doc | Short Description |
|---|-----|-------------------|
| 2 | [Project Overview / PDR](./project-overview-pdr.md) | Product vision, scope, functional requirements (F1…), roadmap. The "why" and "what". |
| 3 | [System Architecture](./system-architecture.md) | Deep design reference: Clean Architecture + DDD + CQRS layers, request flows, "Where Does X Live?", config, limitations. |
| 4 | [Architecture Visual Map](./architecture-visual-map.md) | ASCII + Mermaid diagrams, bounded contexts, context map, ubiquitous-language glossary. Visual companion to #3. |

## 2. Conventions (before you write code)

| # | Doc | Short Description |
|---|-----|-------------------|
| 5 | [Code Standards](./code-standards.md) | Naming, file-size rules, layer dependency direction, DDD aggregate-classification guide, Pyright conventions. |

## 3. Domain Deep-Dives (how features actually work)

| # | Doc | Short Description |
|---|-----|-------------------|
| 6 | [Strategy Lifecycle](./strategy-lifecycle.md) | Template-based strategy model: load → subscribe → backtest → start/stop. `strategy_code` vs `subscription_id`. |
| 7 | [Handler Pipelines](./handler-pipelines.md) | Per-handler request/processing/side-effect detail for all 37 CQRS handlers. The API-level reference. |
| 8 | [WebSocket Architecture](./websocket-architecture.md) | Outbound WS clients only: Binance `@aggTrade` market-data stream + OKX private order/position stream. No server-side WS. |
| 9 | [Feature: Add Symbol](./feature-add-symbol.md) | Worked example of one feature end-to-end (strategy subscription modal). Template for understanding other slices. |

## 4. Operations

| # | Doc | Short Description |
|---|-----|-------------------|
| 10 | [Deployment](./deployment.md) | Production deploy via GitHub Actions → Docker Hub → SSH to Vultr VPS. Skill-friendly summary + operator runbook. |

## Index

- [docs/README.md](./README.md) — canonical alphabetical index of all docs (no reading order).
