---
phase: 6
title: "Move adapters to infrastructure"
status: pending
priority: P1
effort: "1d"
dependencies: [5]
---

# Phase 6: Move adapters to infrastructure

## Overview

Move the concrete infrastructure adapters out of `core/infrastructure/` into the `pocketquant-infrastructure` package: PaperBroker, Binance REST/WS clients + mappers, JobScheduler, ResilientHttpClient. After this, `core/infrastructure/` is empty and deleted — core no longer carries any adapter or heavy lib. (JobHistoryRepository already moved in Phase 5 with persistence; only `scheduler.py` remains here.)

## Requirements
- Functional: PaperBroker, BinanceClient, BinanceWebSocketClient, binance_mappers, JobScheduler, ResilientHttpClient live under `pocketquant.infrastructure.*`. `core/infrastructure/` deleted. Core `pyproject.toml` drops apscheduler/websockets/httpx/cachetools/pymongo/redis. Full suite + api boot green.
- Non-functional: adapter logic moves verbatim (PaperBroker state machine, binance bar-cutoff, scheduler MongoDBJobStore coordination, http retry). PaperBroker fills characterization test stays green.

## Architecture

Target infra layout:
- `infrastructure/brokers/paper/paper_broker.py` — imports ports from `core.domain.brokers` (Phase 4), events/position/order from core domain, EventBus/time/uuid from `core.common`.
- `infrastructure/market_data/binance/` — `binance_client.py`, `binance_websocket_client.py`, `binance_mappers.py` (implement `core.domain.market_data` ports).
- `infrastructure/scheduling/scheduler.py` — `JobScheduler` (APScheduler). Its `TYPE_CHECKING` ref to `JobHistoryRepository` now points at `infrastructure.persistence.repositories` (moved Phase 5).
- `infrastructure/http_client/client.py` — `ResilientHttpClient`.

Core back-reference shim:
- `core/common/jobs/__init__.py:3` re-exports `JobScheduler` from `core.infrastructure.scheduling` → DELETE; consumers import `infrastructure.scheduling.JobScheduler`.

PaperBroker is shared by backtest engine + paper trading; both already import it via DI/factory — re-point those imports to infra.

## Related Code Files
- Create: `infrastructure/brokers/paper/paper_broker.py` (+ `brokers/__init__.py`), `infrastructure/market_data/binance/*`, `infrastructure/scheduling/scheduler.py`, `infrastructure/http_client/client.py`
- Delete: `core/infrastructure/` (whole tree, after moves), `core/common/jobs/`
- Modify (re-point): api `di/broker_factory.py:4-5` (PaperBroker), `di/infrastructure.py:12-15` (BinanceClient, JobScheduler, JobHistoryRepository), `di/market_data.py:9-10` (BinanceWebSocketClient), `main_extensions.py:33-35`; backtest `engine/backtest_app_service.py:19`, `optimization/grid_optimization_app_service.py:19`, `handlers/run/handler.py:12`; trading `webhooks/dispatcher.py:11` (ResilientHttpClient), `handlers/strategy/{delete,remove_symbol,run_all_backtests}/handler.py` (JobScheduler); core `common/jobs` consumers.
- Modify: `core/pyproject.toml` — remove apscheduler, websockets, httpx, cachetools, pymongo, redis (verify zero core usage via grep first). Keep pandas/numpy/pydantic/structlog/rich/pyyaml if still used by core domain/concepts.
- Move tests: `tests/core_test/unit/infrastructure/binance/`, `.../brokers/`, `.../scheduling/` → `tests/infrastructure_test/{market_data/binance,brokers,scheduling}/`.

## Implementation Steps
1. Move PaperBroker → infra; fix imports (ports from `core.domain.brokers`, events `core.domain.brokers.events`, `BarCompletedEvent` from `core.domain.bar.events`). Run PaperBroker fills characterization test.
2. Move binance client/ws/mappers → infra; they implement `core.domain.market_data` ports.
3. Move `scheduler.py` → infra; fix `JobHistoryRepository` TYPE_CHECKING import to infra persistence.
4. Move `ResilientHttpClient` → infra.
5. Delete `core/common/jobs/` shim; re-point consumers to `infrastructure.scheduling`.
6. Grep-sweep all `core.infrastructure.*` import sites to zero; re-point to `infrastructure.*`.
7. Delete the emptied `core/infrastructure/` tree.
8. Grep core/src for apscheduler/websockets/httpx/cachetools/pymongo/redis usage → expect zero; remove pins from `core/pyproject.toml`. `uv sync`.
9. Full suite + api boot smoke + `lint-imports` (core should now import NO adapter libs).
10. Commit: `refactor: move concrete adapters (PaperBroker, binance, scheduler, http) to pocketquant-infrastructure; core drops adapter deps`.

## Success Criteria
- [ ] `core/infrastructure/` and `core/common/jobs/` deleted.
- [ ] `core/pyproject.toml` has no pymongo/redis/apscheduler/websockets/httpx/cachetools.
- [ ] PaperBroker fills characterization test green; full suite + api boot green.
- [ ] `lint-imports`: core imports only stdlib + pydantic/pandas/numpy/structlog (domain libs).

## Risk Assessment
- Risk: core still imports a dropped lib somewhere subtle (e.g. cachetools in a domain util). Mitigation: grep before removing each pin; remove one at a time if uncertain, re-run `uv sync` + import smoke.
- Risk: APScheduler text-path job references (`module:function` strings) break when modules move. Mitigation: scheduler job strings point at JOB modules (`trading.jobs...`/`backtest...`), not adapter modules — those move in Phase 7, not here. Verify no job string references `core.infrastructure`.
- Risk: PaperBroker subscribes to `BarCompletedEvent` via EventBus at runtime — import move shouldn't change event wiring, but verify the event-handler registration still fires (characterization test covers SL/TP path).
