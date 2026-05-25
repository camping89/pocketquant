# Report: codebase-summary trim

**Date:** 2026-05-25
**Task:** Trim `codebase-summary.md` from 796 → ≤400 lines; migrate deep content to `system-architecture.md`.

---

## Line Counts

| File | Before | After | Delta |
|------|--------|-------|-------|
| `codebase-summary.md` | 796 | 278 | −518 |
| `system-architecture.md` | 721 | 814 | +93 |

---

## Sections Removed from codebase-summary

All content below was either already covered in system-architecture.md or relocated there:

- `pocketquant.core.common` — full API doc (Mediator, HandlerRegistry, EventBus, decorators, middleware, UUID, Database/Cache singletons, logging, constants) — ~50 lines
- `pocketquant.core.domain` — full entity/VO/event/enum/service listing with LOC counts — ~65 lines
- `pocketquant.backtest + pocketquant.trading` submodule app service enumeration — ~13 lines
- `pocketquant.core.infrastructure` — broker interface/impl specs, OKX WS detail, BinanceClient contract, scheduling detail — ~62 lines
- `pocketquant.core.persistence` — 8 repository method signatures, BaseRepository, persistence consolidation notes — ~62 lines
- `pocketquant.api.features` — vertical slice architecture explainer, full backtesting folder tree, sync_one refactor detail — ~48 lines
- CQRS Flow diagram (`HTTP Request → Route → Mediator → Handler → Response`) — already in sys-arch request flows
- Key Patterns section (CQRS, Event Bus, Value Objects, Mediator, Broker Abstraction, Domain Purity) — already in sys-arch
- Testing Strategy section (unit/domain-purity/integration test descriptions) — already in sys-arch
- Recent Changes changelog (2026-02-12 through 2026-05-24 — 6 change entries, ~60 lines) — relocated to sys-arch
- `HandlerProvider` detailed DI provider descriptions with handler lists — relocated to sys-arch
- Container Factory code snippet (`PROVIDERS`, `create_container()`, `register_handlers()`) — already in sys-arch DI section
- Route Integration code example (`FromDishka`, `@router.post`) — already in sys-arch
- Data Pipelines inline listing (8 background jobs with schedules) — relocated to sys-arch
- `vite.config.ts` proxy note (duplicated mid-doc) — removed duplicate

---

## Sections Added to system-architecture.md

1. **Layer 6 Web UI — Routes and Custom Hooks table** (+20 lines)
   - Three routes (`/`, `/strategies`, `/monitor`) with component lists
   - 10-row hooks table (useOHLCV, useBacktest, useSymbols, useAvailableIntervals, useRealTimeBar, useIndicators, useSyncStatus, useIntegrityCheck/Repair, useBackgroundJobs, useSubscriptions)
   - API layer note (api-client.ts wrappers, 3 API modules)

2. **Dependency Injection § — PersistenceProvider repository list** (+3 lines)
   - Expanded from "7 repositories" to explicit 8-repo list

3. **Dependency Injection § — InfrastructureProvider full item list** (+3 lines)
   - Explicit list: PaperBroker, OKXBroker, BrokerFactory, BinanceClient, BinanceWebSocketClient, OkxWebSocketClient, OkxReconnectionHandler, HTTP client, WebhookDispatcher, JobScheduler

4. **27 CQRS Handlers by Category table** (+10 lines)
   - Market data (13), Backtesting (5), Strategy (5), Trading (4)

5. **8 Background Jobs detail table** (+15 lines)
   - Job ID, schedule, purpose, misfire grace time for all 8 jobs
   - Note on cron offset (+2s), bounded retry, startup catch-up

6. **Recent Significant Changes section** (+55 lines)
   - Scheduler Resilience (2026-05-24)
   - Strategy Subscriptions (2026-05-23)
   - Integrity Repair Verification (2026-04-13)
   - Bar Integrity System (2026-04-11)
   - sync_one Handler Refactor (2026-05-05)
   - 4-Package Monorepo (2026-03-21)
   - DDD + Persistence Cleanup (2026-03-15)
   - Dishka DI Migration (2026-03-13)

---

## Cross-Link Suggestions

- `codebase-summary.md` now links to `system-architecture.md`, `handler-pipelines.md`, `run-and-test-guide.md`, `project-changelog.md`, `code-standards.md` in the "Deep Dives" table at the bottom.
- `system-architecture.md` already links to `handler-pipelines.md` and `README.md`; the existing link at the top should be updated to also reference `codebase-summary.md` as the quick map entry point.
- Suggest adding to the top of `system-architecture.md`: `For a quick package map, see [codebase-summary.md](./codebase-summary.md).`

---

## Notes

- No information was deleted; all factual claims relocated to system-architecture.md or were already present there.
- The `project-changelog.md` doc (not in scope) is the more appropriate home for the 8-entry Recent Changes log that was in codebase-summary. The trimmed version in system-architecture is condensed (~55 lines vs ~60 original).
- `HandlerProvider` handler count note: system-architecture says "27 handlers" and "7 repositories" in two places; the latter is now corrected to 8 (JobHistoryRepository was added in 2026-04-13 but the count was not updated).
