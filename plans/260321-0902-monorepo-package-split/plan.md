---
title: "Monorepo Package Split"
description: "Refactor single src/ into 4-package uv workspace: core, backtest, trading, api"
status: pending
priority: P1
effort: 24h
branch: feat/monorepo-split
tags: [refactoring, monorepo, uv-workspace, architecture]
created: 2026-03-21
blockedBy: []
blocks: [260108-1144-trading-features, 260131-2006-okx-websocket-backtest-integration]
---

# Monorepo Package Split

Refactor PocketQuant from single `src/` package into 4-package uv workspace monorepo.

## Dependency Graph

```
pocketquant-core        (0 deps)
     ↑           ↑
     │           │
 backtest      trading
 (core)        (core)
     ↑           ↑
     │           │
     pocketquant-api
     (core + backtest + trading)
     [composition root]
```

## Revised Package Ownership (Post-Analysis)

**Critical finding**: `IStrategy` imports `OrderAggregate`, `IBroker` imports both `OrderAggregate` and `PositionAggregate`. Therefore order/position domain + broker ports + PaperBroker → core.

| Package | Owns | Files |
|---------|------|-------|
| **core** | domain/{bar,symbol,sync_status,shared,order,position}, concepts/{strategy,risk,quote}, common/, persistence/, infra/{tradingview,scheduling,http_client,brokers/interface+models+paper}, config.py | ~110 |
| **backtest** | domain/backtest/, application/backtesting/, features/backtesting/ | ~30 |
| **trading** | application/{trading,strategy}/, infra/{brokers/okx,webhooks}/, features/{trading,strategy,risk}/ | ~55 |
| **api** | application/market_data/, features/market_data/, di/, main.py, infra/brokers/factory.py | ~85 |

## Phases

| Phase | File | Status | Risk |
|-------|------|--------|------|
| 0 | [phase-00-pre-migration-prep.md](phase-00-pre-migration-prep.md) | pending | None |
| 1 | [phase-01-workspace-and-core.md](phase-01-workspace-and-core.md) | pending | Medium |
| 2 | [phase-02-backtest-extraction.md](phase-02-backtest-extraction.md) | pending | Low |
| 3 | [phase-03-trading-extraction.md](phase-03-trading-extraction.md) | pending | Medium |
| 4 | [phase-04-api-composition-root.md](phase-04-api-composition-root.md) | pending | Low |
| 5 | [phase-05-validation-and-ci.md](phase-05-validation-and-ci.md) | pending | Low |

## Key Design Decisions

1. **Order/Position → core**: Both IStrategy and IBroker reference these types. Must be shared.
2. **PaperBroker → core**: Used by both backtest (fresh per run) and trading (paper mode). Shared concern.
3. **IBrokerFactory protocol → core**: StrategyAppService depends on protocol. API provides concrete BrokerFactory.
4. **BrokerFactory → api**: Only composition root knows about all implementations (PaperBroker + OKXBroker).
5. **Config.py → core**: Settings used by all packages.
6. **All repositories → core**: User chose "core owns everything" for persistence.

## Success Criteria

- [ ] `uv sync --package pocketquant-core` works standalone
- [ ] `uv sync --package pocketquant-backtest` works without trading
- [ ] `uv run --package pocketquant-api` starts the server
- [ ] All existing tests pass
- [ ] import-linter contracts pass (backtest ⊥ trading)
- [ ] No circular dependencies between packages

## Context

- Brainstorm: `plans/reports/brainstorm-260321-0902-monorepo-package-split.md`
- Research: `plans/reports/researcher-260321-0847-python-monorepo-research.md`
