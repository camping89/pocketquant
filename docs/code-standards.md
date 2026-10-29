# Code Standards

This file holds the coding rules that code cannot state. The hard limits (language, code size, layering, logging) are in `CLAUDE.md` under "Rules that change decisions". This file does not repeat them. Commands live in the [README](../README.md). The other rules here are rules of thumb: break one when following it makes the code worse.

## Helpers, Files and Functions

- One concept has one definition. Two copies are fine. Consolidate at the third.
- Extract a helper only when its name adds meaning the inline code cannot say, or when two places use it.
- Do not extract only to shorten a function. A function that only forwards one call (`return self._x.y(...)`) makes the reader jump a file and learn nothing. The [metric ratchet](#quality-gate) counts these.
- No god-function that owns a whole flow.
- About 400 lines per file is a soft guide, not a split trigger. Split a file when it holds two independent concerns.
- A long function usually does several jobs. Split it by named step, not by line count. `scripts/code_metrics.py --json` lists the long ones.

## Naming

Class and file names encode the layer. Domain concepts (entities, value objects, enums, events) carry no layer suffix: they are the domain language. A file name is `snake_case`, and its suffix matches the main class inside it.

### Class Naming by Layer

| Layer | Class pattern | File |
|---|---|---|
| Entities | `{Name}`, or `{Name}Aggregate` | `entities.py` |
| Events | `{Entity}{PastTense}Event` | `events.py` |
| Enums, value objects | `{Concept}` | any |
| Domain services | `{Name}DomainService` | `*_domain_service.py` |
| Strategy implementations | `{Name}StrategyService` | `*_strategy_service.py` |
| Repositories | `{Entity}Repository` | `*_repository.py` |
| Infra ports | `I{Concept}Port`, one port per file | `*_port.py` |
| Infra adapters | `{Source}[{Type}]Adapter`; a new source and type pair gets its own adapter | `*_adapter.py` |
| Helpers | `{Name}Helper`, only when a helper module is justified | `*_helper.py` |
| App services | `{Name}AppService` | `*_app_service.py` |
| Query and command models | `{Get\|List}{Entity}Query`, `{Action}{Entity}Command` | beside the service that takes it |
| CQRS services | `{Domain}CommandService`, `{Domain}QueryService` | `*_service.py` |
| DTOs | `{Name}Response` | any |
| Routes | functions | `app/routes/{feature}.py` |
| Middleware | `{Name}Middleware` | `*middleware.py` |
| Errors | `{Name}Error` | any |
| DI providers | `{Domain}Provider` | `app/di/{domain}.py` |
| Configs | `{Name}Config` | `config.py` or `value_objects.py` |
| Background jobs | functions | `*_jobs.py` |

### Naming Principles & Exemptions

1. A class or file name states its layer without the folder.
2. Do not stack two doer-suffixes (`-er`, `-or`) in one name. Use a gerund instead: `*TrackingHelper`, not `*TrackerHelper`. A business noun that ends in `-er` (`Broker`) is not a doer-suffix, so `BrokerAdapter` is valid.
3. A role that already has a standard suffix keeps it. Do not force the layer suffix on `*CommandService` and `*QueryService` (request-scoped, not orchestrators), `*Repository`, `*Provider`, `*Middleware`, `*Handler`, `*Factory`, `*Scheduler`, or on data classes (entities, value objects, enums, events, `*Command`, `*Query`, `*Response`).

## Routes & Services

- Route injection and service signatures follow the "Routes" rule in `CLAUDE.md`.
- A route parses the request, calls one service method and returns the result. Business logic lives in the service.
- Mutations are guarded once, on the `api` router in `app/main_extensions.py`. Do not add per-route auth.
- Routes and services do not catch an exception to build a response. Exceptions propagate to the global handlers from `register_exception_handlers` (`core/common/exceptions.py`).
- Catch a specific exception only where the code recovers, such as a job or an adapter retry. Never write a bare `except:`.
- A state change publishes a domain event on the event bus.
- All dependencies come in through the constructor.
- Datetimes sent to the frontend go through `to_utc_iso()` (`pocketquant.core.common.time`) for a correct `Z` suffix. Bare `.isoformat()` is for logs and cache keys only.

## Domain & Repositories

- Entities are Pydantic models that serialize themselves with `to_mongo()` and `from_mongo()`. There is no schemas directory and no `Create` subclass. Factories are classmethods.
- Value objects and events are frozen dataclasses.
- Use an aggregate only when the entity protects invariants, has lifecycle behaviour, owns other entities or emits events. A data record or a CRUD-only model stays a plain entity.
- Strategies return a `Signal` and stay pure: no broker, no database. `StrategyAppService` executes the signal.
- Put uniqueness and idempotency on a secondary unique index, never on `_id`.
- The one exception to the UUIDv7 rule in `CLAUDE.md` is a collection whose `_id` a third-party library writes (APScheduler's `apscheduler_jobs`). Do not patch the library to force UUIDv7.

## Composite Symbol Format

- Every entity carries one immutable composite `symbol` string instead of a `(code, exchange)` pair. The format is `COMPOSITE_SYMBOL_RE` in `core/domain/symbol/entities.py`.
- The suffix names, in full, the data provider that produces the bars. It never names the exchange and is never a short code. The decision is in [system-architecture.md](./system-architecture.md), "Decisions".
- Only `provider_id_for()` reads the suffix. All other code treats `symbol` as opaque.
- A broker maps the full composite symbol to its own instrument name, in its own table (`EXNESS_INSTRUMENTS` in `exness_mappers.py`).
- In URL path segments, `:` is encoded as `%3A`. JSON and the database keep the raw `:`.

**Adding a data provider** touches these places:

1. An adapter package `src/pocketquant/core/infra/<provider>/` that implements `IDataProviderPort` and, optionally, `IRealtimeQuoteProviderPort`.
2. `Settings` fields in `src/pocketquant/core/config.py`, with their prod values in `pocketquant-config` (see [deployment.md](./deployment.md)).
3. One `DATA_PROVIDER_DEFAULTS` entry (`core/domain/market_data/provider_routing_domain_service.py`) and one entry in each router in `app/di/adapters.py` (`get_data_provider`, `get_realtime_quote_provider`). `tests/app_test/unit/test_data_provider_registration.py` checks that the three match.
4. A calendar registered in `TradingCalendarFactory` (`core/infra/calendars/trading_calendar_factory.py`) when no existing one fits, built from recorded sessions.
5. A `ContractSpec` per symbol, written by a seed script modelled on `scripts/seed_exness_symbols.py` (`symbols` and `tracked_symbols`).
6. The provider in the `/health` provider map (`register_health_checks`, `app/main_extensions.py`).
7. Any new symbol-keyed collection or Redis key joins the symbol-removal cascade (`TrackedSymbolService.remove`).
8. A broker is optional and separate: a `BrokerFactory` branch, with the broker's own instrument table keyed by the full composite symbol.
9. Adapter tests under `tests/core_test/infra/<provider>/` against recorded fixtures.

## Strategy IDs

Two ids must never be confused:

- `strategy_code` names a strategy class in `STRATEGY_REGISTRY`.
- `subscription_id` is the UUIDv7 of one `(strategy_code, symbol, interval)` binding. It keys the in-memory strategy instance, orders, positions and trades.

The only duplicate guard for a subscription is the unique index `ix_subscriptions_dedup_triple`. The index is case-sensitive, so `add_symbol` upper-cases `symbol` before it stores it. No test pins that upper-case. Do not remove it.

## Async Suspension Points — "Await Is Preemption"

The rule is in `CLAUDE.md`. These are the places where this code base hides suspension points, and the rules that follow from them:

- `await container.get(X)` can run provider I/O.
- Publish before subscribe. Set module globals and wire handlers before the first call that can start a worker (scheduler, queue consumer, websocket reader, background task). `lifespan()` in `app/main.py` shows the case: `set_sync_container(container)` runs before the worker role starts the scheduler, because persisted jobs can dispatch as soon as it starts.
- A Dishka `AsyncIterator` factory suspends at `yield`. Do all setup before `yield`, and cleanup in `try/finally` after it.
- A check before an `await` may be stale after it. Guard shared in-memory state with the owning service's `asyncio.Lock` across the `await`, or move the invariant into a storage-side condition.
- When two subsystems do similar startup wiring (`init_backtest_tasks`, `register_sync_jobs`), diff their order. An asymmetry is usually a bug.

## Comment Policy — Explain WHY, Not WHAT

Comments are short, plain English. They cost lines and drift from the code. The default is no comment. Add one only when the code cannot speak for itself.

No docstrings. Python `"""` docstrings and TS/JS `/** */` blocks are not used, on modules, classes, functions or tests. A WHY goes in a `#` or `//` comment above the line or definition it explains. Text the program reads (script `--help`, API descriptions) is a plain string value, never `__doc__`. `tests/core_test/unit/test_no_docstrings.py` enforces this.

Never write:

- a comment that restates the line (`# increment counter`);
- a banner, divider or count label (`# ---- setup ----`, `# Market data (16)`);
- filler Arrange/Act/Assert markers;
- a plan, phase or finding reference. Explain the invariant, not the origin.

Write a comment only for:

- WHY: races, ordering and suspension constraints, invariants, trade-offs;
- hacks, workarounds and external-system quirks (Exness, Mongo, Redis, asyncio, APScheduler);
- `# type: ignore[...]`, `// @ts-expect-error` and `// eslint-disable`, always with their reason;
- a non-obvious failure mode (`# benign — already dropped`);
- a contract, edge case or return semantic the signature cannot show;
- a test comment for scenario intent or non-obvious setup.

## Testing

- Before you restructure a flow, pin its current behaviour with a test. A refactor that changes that test's result changed behaviour.
- Do not mock the database when the behaviour under test is a query or an index. Use the real MongoDB or Redis from testcontainers (`tests/app_test/conftest.py`).
- There is no coverage gate.

## Performance

- No blocking I/O on the event loop. Use a native async client. If a sync library is unavoidable, run it with `loop.run_in_executor(...)`.
- Write in bulk, not in a loop of single inserts.
- Invalidate cache by pattern (`Cache.delete_pattern`), not by guessing individual keys.
- Public functions and class attributes carry full type hints.

## Quality Gate

- A change is done when the tests, Ruff, Pyright, import-linter and the metric ratchet pass.
- Ruff and Pyright report 0 errors in `src/` and in every file you touch.
- CI does not run Ruff or Pyright. Run them locally.
- Layer rules are checks, not prose: `[tool.importlinter]` in `pyproject.toml` and `tests/core_test/unit/domain/test_domain_purity.py`.
- The metric definitions are in `scripts/code_metrics.py`. The ceilings are `[tool.code-metrics]` in `pyproject.toml`.
- Lower a ceiling when a change improves its metric.
- Do not pad or contort code to pass the ratchet. KISS wins.
- If clean, needed code pushes a metric over its ceiling, raise the ceiling modestly in its own commit and tell the owner.
- A tiny share of 30% or less and 20 delegations or fewer are the aspiration, not a gate.

## Configuration & Secrets

- Never hardcode configuration. Every setting is a field on `Settings` in `src/pocketquant/core/config.py`.
- Secrets follow the credentials rule in `CLAUDE.md`. A secret value is never logged.
