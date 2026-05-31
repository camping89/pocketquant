---
phase: 4
title: "Move ports + DTOs to core"
status: done
priority: P1
effort: "0.5d"
dependencies: [3]
---

# Phase 4: Move ports + DTOs to core

## Overview

Relocate the broker/data ports and shared DTOs from `core/infrastructure/` into a proper core home (domain-level ports), so that after Phase 5/6 the `infrastructure` PACKAGE holds only concrete adapters. Ports stay in core because trading/backtest/execution depend on the abstractions, not the adapters (DIP — matches CLAUDE.md "IBrokerFactory protocol in core").

## Requirements
- Functional: `IBroker`, `IBrokerFactory`, `OrderCallback`, `IDataProvider`, `IRealtimeQuoteProvider`, and DTOs `OrderResult`, `AccountBalance`, `OrderEvent` live under core (NOT under the infrastructure package). All consumers import from the new core path. Full suite green.
- Non-functional: no concrete adapter (PaperBroker, BinanceClient, etc.) moves in this phase — only interfaces + DTOs.

## Architecture

These are still physically inside `pocketquant-core` today (`core/infrastructure/brokers/`, `core/infrastructure/data_provider.py`, `core/infrastructure/realtime_quote_provider.py`). "Move to core" here means relocate to a non-`infrastructure` subtree of core so the soon-to-be-extracted `core/infrastructure/` adapter code can leave cleanly without dragging the ports.

Target placement (ports are domain contracts):
- `core/domain/brokers/interfaces.py` — `IBroker`, `IBrokerFactory`, `OrderCallback`
- `core/domain/brokers/value_objects.py` — `OrderResult`, `AccountBalance` (DTOs; depend on `core.domain.order` enums — already core)
- `core/domain/brokers/events.py` — `OrderEvent` (depends on `core.domain.order.enums.OrderStatus` — already core)
- `core/domain/market_data/interfaces.py` — `IDataProvider`, `IRealtimeQuoteProvider` (depend on `core.domain.bar`, `shared.enums.Interval` — already core)

(Folder names follow the codebase's domain layout; final names confirmed during implementation against existing `core/domain/` siblings.)

## Related Code Files
- Create: `core/domain/brokers/{__init__.py,interfaces.py,value_objects.py,events.py}`
- Create: `core/domain/market_data/{__init__.py,interfaces.py}`
- Delete (after move): `core/infrastructure/brokers/interface.py`, `brokers/models.py`, `brokers/events.py`, `core/infrastructure/data_provider.py`, `core/infrastructure/realtime_quote_provider.py`
- Modify (re-point): everything importing `core.infrastructure.brokers.{interface,models,events}`, `core.infrastructure.data_provider`, `core.infrastructure.realtime_quote_provider`. Scout consumer list: core PaperBroker (`paper_broker.py:47-48`), `brokers/__init__.py`; backtest `engine/backtest_app_service.py:19`, `domain/value_objects/order.py:17` (now in core from Phase 3), `handlers/run/handler.py`; trading `app_services/{strategy,order}_app_service.py`, `handlers/risk/check_risk/handler.py`, `brokers/okx/okx_broker.py:10-11`, `okx/websocket/okx_order_mapper.py`; api `di/{infrastructure,market_data,broker_factory}.py`; binance client/ws (`binance_client.py:23`).
- Modify: `core/domain/backtest/value_objects` OrderEvent import (from Phase 3 temp) → re-point to `core.domain.brokers.events`.

## Implementation Steps
1. Create the new core domain port/DTO modules; port source verbatim, fixing only internal import paths (they already reference `core.domain.order|position|bar|shared` — valid).
2. Grep all import sites of the 5 old module paths; re-point to the new `core.domain.brokers.*` / `core.domain.market_data.*` paths. Include the Phase-3 temporary `OrderEvent` import.
3. Update `core/infrastructure/brokers/__init__.py`: it currently re-exports interface+models+PaperBroker. PaperBroker stays (moves in Phase 6). BINDING: do NOT keep a thin compat re-export of interface/models/events — remove those names from this `__init__` and re-point ALL consumers to the new `core.domain.brokers.*` paths in THIS phase. A compat re-export would let consumers keep importing via `core.infrastructure.brokers`, which Phase 6 deletes — a deferred landmine that surfaces only at the Phase 6 boundary. Known consumers still on the old path: `order_app_service.py:8-9`, `strategy_app_service.py:14`, `check_risk/handler.py:7`, `backtest/domain/value_objects/order.py:17` (now in core from Phase 3).
4. Delete the old port/DTO modules under `core/infrastructure/`.
5. Run characterization tests (PaperBroker fills still resolve IBroker from new path). Full `uv run pytest`. `uv run lint-imports`.
6. Commit: `refactor: relocate broker/data ports + DTOs into core domain`.

## Success Criteria
- [ ] No module under `core/infrastructure/` defines an interface/DTO — only adapters remain there (PaperBroker, binance, scheduling, http_client).
- [ ] All consumers import ports from `core.domain.brokers` / `core.domain.market_data`.
- [ ] `grep -r "core.infrastructure.brokers.\(interface\|models\|events\)" packages/` → 0 hits (no compat re-export left riding into Phase 6).
- [ ] Characterization + full suite green.

## Risk Assessment
- Risk: wide import churn → missed site. Mitigation: exhaustive grep of the 5 old paths before deleting; full suite + api boot.
- Risk: OrderEvent has dual identity (core DTO vs backtest VO re-export at `backtest/domain/value_objects/order.py`). Mitigation: single source = `core.domain.brokers.events.OrderEvent`; backtest VO module imports it, never redefines.
- Risk: temptation to also move PaperBroker now. Mitigation: explicitly out of scope here — keeps this phase a pure interface relocation, smaller blast radius.
