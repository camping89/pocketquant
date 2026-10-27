# Code Standards

The hard limits (language, code size, layering, logging) are in the project `CLAUDE.md` under "Rules that change decisions"; they always apply. This file explains how to meet them, and its other guidance is rules of thumb: break one when it makes the code worse. Run and test commands live in the [README](../README.md); the design lives in [system-architecture.md](./system-architecture.md).

## Principles

- **KISS:** the countable limits are the code rule in `CLAUDE.md`. This file does not restate them.
- **DRY:** one concept has one definition. Repeating something twice is fine; the third time, consolidate.
- **Balance:** no god-function that owns a whole flow, and no micro-helper that only wraps one call. A function does one job that has a clear name.
- **Dependency direction is fixed:** `core ◁ engine ◁ app`. `core.domain` never imports `core.infra` and does no I/O (no pymongo, redis or aiohttp; Pydantic is allowed). Only `app` imports `fastapi`. import-linter enforces these (see [Quality Gate](#quality-gate)); `tests/core_test/unit/domain/test_domain_purity.py` also checks domain purity.
- **Backtest and live are two drivers on one engine:** `engine.backtest` and `engine.live` never import each other, and the shared machinery (`engine.strategy`, `engine.execution`, `engine.market_data`) imports neither.

## When to Extract a Helper

- Extract when the helper's name adds meaning the inline code cannot say, or when the code is reused in at least two places.
- Do not extract only to make a function shorter. A 2-line function that only does `return self._x.y(...)` is a pure delegation: the reader jumps a file and learns nothing. The [metric ratchet](#quality-gate) counts these.
- A flow should read in one file where possible, and in 3 at most (plus leaf calls such as repositories and clients).

## File and Function Size

- About 400 LOC per file is soft guidance, not a split trigger. Split when a file holds two independent concerns, not because it is long.
- Keep functions ≲ 60 lines. A longer function is usually doing several jobs; split by named step, not by line count. `scripts/code_metrics.py --json` lists every function over 60 lines.

## Naming

Class and file names encode the layer. Domain concepts (entities, value objects, enums) have no suffix — they are the domain language.

### File Naming

`snake_case`, named for the module's purpose; the suffix encodes the layer and matches the main class inside:

```
app/routes/market_data.py            # market-data route functions
quote_app_service.py                 # QuoteAppService (application orchestrator)
bar_builder_domain_service.py        # BarBuilderDomainService (domain logic)
engulfing_strategy_service.py        # EngulfingStrategyService (strategy impl)
strategy_service_interface.py        # IStrategyService (strategy interface)
bar_repository.py                    # BarRepository (data access)
data_provider_port.py                # IDataProviderPort (infra boundary)
binance_adapter.py                   # BinanceAdapter (infra impl)
exness_broker_adapter.py             # ExnessBrokerAdapter (source + type → separate adapter)
```

### Class Naming by Layer

| Layer | Pattern | Class Suffix | File | Example |
|-------|---------|--------|--------|--------|
| Entities | `{Name}` or `{Name}Aggregate` | None / `Aggregate` | `entities.py` | `Bar`, `Symbol`, `OrderAggregate` |
| Events | `{Entity}{PastTense}Event` | `Event` | `events.py` | `OrderFilledEvent`, `BarCompletedEvent` |
| Enums / Value Objects | `{Concept}` | None | `.py` | `Interval`, `OrderSide`, `PnL`, `OHLCV` |
| **Domain Services** | `{Name}DomainService` | `DomainService` | `*_domain_service.py` | `PositionCalculatorDomainService`, `BarBuilderDomainService` |
| **Domain Strategy (Impl)** | `{Name}StrategyService` | `StrategyService` | `*_strategy_service.py` | `EngulfingStrategyService`, `HitNRun2StrategyService` |
| **Domain Strategy (Interface)** | `IStrategyService` | `IStrategyService` | `strategy_service_interface.py` | `IStrategyService` |
| Repositories | `{Entity}Repository` | `Repository` | `*_repository.py` | `BarRepository`, `OrderRepository` |
| **Infra Port (Interface)** | `I{Concept}Port` | `Port` | `*_port.py` (1 port/file) | `IBrokerPort`, `IDataProviderPort`, `IRealtimeQuoteProviderPort` |
| **Infra Adapter (Impl)** | `{Source}[{Type}]Adapter` | `Adapter` | `*_adapter.py` | `ExnessBrokerAdapter`, `BinanceAdapter`, `PaperBrokerAdapter` |
| **Helper** | `{Name}Helper` | `Helper` | `*_helper.py` | (only when a helper module is justified) |
| **App Services** | `{Name}AppService` | `AppService` | `*_app_service.py` | `StrategyReconcileAppService`, `BacktestReportAppService` |
| Query / Command Models | `{Get\|List}{Entity}Query`, `{Action}{Entity}Command` | `Query` / `Command` | beside the service that takes it | `GetOHLCVQuery`, `SyncSymbolCommand`, `RunBacktestCommand` |
| CQRS Services | `{Domain}{Command\|Query}Service` | `Service` | `*_service.py` | `StrategyCommandService`, `BacktestQueryService` |
| DTOs | `{Name}Response` | `Response` | `.py` | `SyncResponse`, `QuoteResponse` |
| Routes | (functions) | — | `app/routes/{feature}.py` | `async def sync_symbol(...)` |
| Middleware | `{Name}Middleware` | `Middleware` | `*middleware.py` | `RateLimitMiddleware` |
| Errors | `{Name}Error` | `Error` | `.py` | `AppError`, `NotFoundError`, `DomainError` |
| DI Providers | `{Domain}Provider` | `Provider` | `app/di/{domain}.py` | `InfrastructureProvider`, `ServicesProvider` |
| Configs | `{Name}Config` | `Config` | `config.py` / `value_objects.py` | `BacktestConfig`, `RiskConfig` |
| Background Jobs | (functions) | — | `*_jobs.py` | `sync_1m()`, `sync_integrity()` |

### Naming Principles & Exemptions

1. **The class + file name self-encodes layer/role.** `PositionCalculatorDomainService` or `binance_adapter.py` tells you the layer without looking at the folder.
2. **Do not stack two generic doer-suffixes (`-er`/`-or`) in one name.** Use a gerund instead (`*TrackingHelper`, not `*TrackerHelper`). A business noun ending in `-er` (`Broker`) is not a doer-suffix, so `BrokerAdapter` is valid.
3. **A data class or role that already has a standard suffix keeps it.** Exempt list (do not force the convention):

| Group | Example |
|---|---|
| CQRS | `*CommandService`, `*QueryService` (request-scoped, not orchestrators) |
| Persistence | `*Repository` |
| DI / cross-cutting | `*Provider`, `*Middleware` |
| App handler | `RiskCheckHandler` |
| Infra factory/scheduler | `BrokerFactory`, `JobScheduler` |
| Data class | Entity, VO, enum, event, `*Command`/`*Query`/`*Response` |

## Routes & Services

- Routes live in `src/pocketquant/app/routes/`, use `route_class=DishkaRoute` and inject services with `FromDishka[...]`. Never `Depends()` for a service.
- A route is thin: parse the request, call one service method, return the result. Business logic lives in the service.
- Mutations are guarded once, on the `api` router; do not add per-route auth.
- Service methods take scalars. A Pydantic model is passed only when it is a real request body (`SyncSymbolCommand`, `AddTrackedSymbolCommand`, `RunBacktestCommand`) or a multi-field parameter object that carries its own validation (`GetOHLCVQuery`, `BackfillTrackedSymbolCommand`). Do not wrap path or query scalars in a model.
- No try/except in routes or services to turn an exception into a response. Exceptions propagate to the global handlers registered by `register_exception_handlers` (`core/common/exceptions.py`, wired in `app/main_extensions.py`): `NotFoundError` → 404, `DomainError` → 400, `AppError` → 500, body `{error: {code, message}}`. Catch a specific exception only where the code genuinely recovers (a job, an adapter retry); never a bare `except:`.
- State changes publish domain events. A service subscribes its handlers with `event_bus.subscribe(EventType, handler)`, usually in its `start()`.
- Datetimes returned to the frontend go through `to_utc_iso()` (`pocketquant.core.common.time`) for a correct `Z` suffix. Bare `.isoformat()` is for internal use only (logs, cache keys).

```python
@router.post("/{strategy_code}/subscriptions", status_code=201)
async def create_subscription(
    strategy_code: str,
    body: CreateSubscriptionBody,
    cmd_svc: FromDishka[StrategyCommandService],
) -> dict:
    return await cmd_svc.add_symbol(strategy_code, body.symbol, body.interval)
```

## Dependency Injection

- `src/pocketquant/app/di/` holds exactly three providers: `InfrastructureProvider` (Settings, EventBus, Database, Cache, repositories, calendars, scheduler, health), `AdaptersProvider` (the routing data and quote adapters, `BrokerFactory`) and `ServicesProvider` (app services, the execution engine, the services routes inject).
- `create_container(settings)` passes `Settings` in through `from_context` and builds with `STRICT_VALIDATION`: a type registered twice fails at startup instead of the last registration silently winning. Each type has exactly one provider.
- All dependencies come in through the constructor. A service that needs cleanup uses a generator factory: all setup before `yield`, cleanup in `try/finally` (see [Async](#async-suspension-points--await-is-preemption), pattern 5).

## Domain & Repositories

- Entities are Pydantic `BaseModel`s that serialize themselves with `to_mongo()` / `@classmethod from_mongo()`. There is no schemas directory and no `Create` subclass; factories are classmethods (`Symbol.create()`, `OrderAggregate.create()`, `PositionAggregate.open()`). Value objects and events are frozen dataclasses.
- An aggregate earns its complexity: use one only when the entity protects invariants, has lifecycle behaviour, owns other entities or emits events. A data record (`Bar`) or a CRUD-only model stays a plain entity.
- Strategies implement `IStrategyService` (`on_bar_completed` is required; `on_order_filled` and `on_order_rejected` are optional) and return `Signal | None`. They stay pure — no broker, no database; `StrategyAppService` executes signals.
- All repositories live in `core.infra.persistence.repositories`; `engine` and `app` have none. A repository is an instance class that extends `BaseRepository`, gets `Database` through its constructor and uses `_collection(name)`.

**Primary key: UUIDv7 only.** Every document our code writes has a UUIDv7 `_id` from `generate_id()` (`core/common/uuid.py`); persisted entities declare `id: UUID`. No hash key, no natural key, no Mongo ObjectId, no composite-string key. Uniqueness and idempotency go on a secondary unique index, never on `_id`. The one exception is a collection whose `_id` a third-party library writes (APScheduler's `apscheduler_jobs`); do not patch the library to force uuid7.

```python
# ❌ hash / natural / objectid as primary key
_id = hashlib.sha256(f"{a}|{b}|{c}".encode()).hexdigest()[:16]
_id = symbol                       # composite string as id
id: str                            # persisted entity declaring str id
# (and: letting Mongo assign a default ObjectId)

# ✅ correct — every persisted entity
from pocketquant.core.common.uuid import UUID, generate_id
id: UUID = Field(default_factory=generate_id)
def to_mongo(self) -> dict: return {"_id": str(self.id), ...}
# uniqueness/idempotency → separate unique index, e.g.
await collection.create_index([("strategy_code", 1), ("symbol", 1), ("interval", 1)], unique=True)
```

## Composite Symbol Format

**Format:** `{CODE}:{PROVIDER}` (e.g., `BTCUSDT:BINANCE`, `ES1!:TRADINGVIEW`, `XAUUSD:EXNESS`)

- One immutable `symbol: str` field replaces `(code, exchange)` pairs on every entity: Bar, Order, Position, Symbol, SyncStatus, Subscription, TrackedSymbol.
- The suffix is the id of the data provider that produces the symbol's bars, written as `provider_id.upper()` in full — `BINANCE`, `TRADINGVIEW`, never a short code and never the exchange. Routing reads it in one place, `provider_id_for()` in `core/domain/market_data/provider_routing_domain_service.py`; everything else treats `symbol` as opaque.
- A suffix that names no registered provider fails loudly (`UnknownDataProviderError`, a `ValueError`) — it is never guessed or routed by asset class.
- An unseeded symbol takes its provider's defaults (`DATA_PROVIDER_DEFAULTS`: `asset_class` + `calendar_id`).
- The execution broker (paper, Exness) is a strategy setting (`StrategyConfig.broker`), not part of the symbol. A broker's own instrument name is the broker adapter's concern: it maps from the full composite symbol in its own table (`TRADINGVIEW_EXCHANGE_BY_CODE` in `tradingview_mappers.py`; `EXNESS_INSTRUMENTS` in `exness_mappers.py`).
- Validation: `COMPOSITE_SYMBOL_RE` for internal data, `COMPOSITE_SYMBOL_PATTERN` for HTTP input (`core/domain/symbol/entities.py`).
- URL: `:` is encoded as `%3A` in path segments (`/api/v1/market-data/sync-status/BTCUSDT%3ABINANCE`). JSON and the database keep the raw `:`. Cache keys use the whole symbol: `quote:latest:{symbol}`, `bar:current:{symbol}:{interval}`.

**Adding a data provider** touches exactly these places:

1. An adapter package `src/pocketquant/core/infra/<provider>/` implementing `IDataProviderPort` and, optionally, `IRealtimeQuoteProviderPort`.
2. `Settings` fields in `src/pocketquant/core/config.py`.
3. One `DATA_PROVIDER_DEFAULTS` entry (`core/domain/market_data/provider_routing_domain_service.py`) and one entry in each router in `app/di/adapters.py` (`get_data_provider`, `get_realtime_quote_provider`); `tests/app_test/unit/test_data_provider_registration.py` enforces that the three match.
4. A calendar registered in `TradingCalendarFactory` (`core/infra/calendars/trading_calendar_factory.py`) when no existing one fits, built from recorded sessions.
5. A `ContractSpec` per symbol, written by a seed script modelled on `scripts/seed_index_futures.py` (`symbols` and `tracked_symbols`).
6. The provider in the `/health` provider map (`register_health_checks`, `app/main_extensions.py`).
7. Any new symbol-keyed collection or Redis key joins the symbol-removal cascade (`TrackedSymbolService.remove`).
8. A broker is optional and separate: a `BrokerFactory` branch, with the broker's own instrument table keyed by the full composite symbol.
9. Env rows in `docs/deployment.md`, and adapter tests under `tests/core_test/infra/<provider>/` against recorded fixtures.

## Strategy IDs

Three ids that must never be confused:

| ID | Meaning | Example |
|---|---|---|
| `strategy_code` | Template name registered in `STRATEGY_REGISTRY`; picks the strategy class | `"hitnrun2"` |
| `subscription_id` | uuid7 of one `(strategy_code, symbol, interval)` binding; keys the in-memory instance, orders, positions and backtest docs | `"019ebe98-…"` |
| `template_id` | **Deprecated** old name for `strategy_code`; treat any reference as `strategy_code` | — |

The only duplicate guard for a subscription is the unique compound index `ix_subscriptions_dedup_triple` on `(strategy_code, symbol, interval)`. The index is case-sensitive, so `add_symbol` upper-cases `symbol` before storing it — that normalization is load-bearing (`tests/core_test/infra/persistence/test_subscription_repository.py::test_concurrent_add_same_triple_one_doc_one_error`).

## Async Suspension Points — "Await Is Preemption"

**One-line rule:** every `await` is a preemption point. The event loop may resume any other ready coroutine there, so state another coroutine reads must be valid **before** the suspension point that lets it run.

| Construct | Suspension? | Notes |
|---|---|---|
| `await coro()` | Yes | The obvious one. |
| `await asyncio.sleep(0)` | Yes | Explicit yield even with 0. |
| `yield x` inside `async def` | **Yes** | Easy to miss. Async generators + `@asynccontextmanager` use this. |
| `async for x in iterable` | Yes | Calls `await iterable.__anext__()` each loop. |
| `async with cm:` | Yes (entry & exit) | Calls `await cm.__aenter__()` and `__aexit__()`. |
| `await asyncio.gather(...)` | Yes | Children interleave between each other's awaits. |
| `await container.get(X)` | Yes if provider does I/O | Dishka `AsyncIterator` factories hide awaits. |
| Plain assignment, `if`, arithmetic | No | Synchronous between awaits — use this for atomic regions. |

**1. Publish-before-subscribe** — wire dependencies BEFORE the call that starts a worker (scheduler, queue consumer, websocket reader, background task). Once that call returns, the worker may dispatch at the next `await`. `app/main.py` calls `set_sync_container(container)` before its first `await` for this reason: APScheduler persists `next_run_time` across restarts, so a job due within its `misfire_grace_time` can dispatch during an early `container.get(...)` and would hit an unset module global.

```python
# Anti-pattern (racy)
await register_sync_jobs(
    container=container,
    job_scheduler=await container.get(JobScheduler),  # scheduler may start here
)
# the container global is set inside register_sync_jobs — too late

# Fix
set_sync_container(container)   # synchronous, wired FIRST
await register_sync_jobs(
    container=container,
    job_scheduler=await container.get(JobScheduler),
)
```

**2. Initialize-before-first-await** — never expose a half-built object to other tasks. Do all I/O, construct atomically, then publish.

**3. TOCTOU across `await`** — a check before an `await` may be stale after it. Push the invariant into storage (`await db.try_debit(...)` with a `WHERE balance >= amount`), hold a per-key `asyncio.Lock` across the `await`, or re-read after it.

**4. Atomic blocks have no `await`** — between a paired read and write of shared state there is no suspension. `counters[key] += 1` is atomic between awaits in CPython, never across one.

**5. `yield` in `@asynccontextmanager` / an `AsyncIterator` factory IS a suspension point.** All setup before `yield`, cleanup in `try/finally` after it.

```python
@provide(scope=Scope.APP)
async def my_service(self) -> AsyncIterator[Service]:
    svc = Service()
    await svc.connect()          # all setup BEFORE yield
    try:
        yield svc
    finally:
        await svc.aclose()       # cleanup in finally — survives cancellation
```

**6. Cancellation lands at any `await`.** `asyncio.CancelledError` may be raised at the next `await` after `task.cancel()`. Paired writes belong in a transaction, or in `try/finally` with a compensating action.

**Symmetry check:** when two adjacent subsystems do similar wiring (e.g. `init_backtest_tasks` and `register_sync_jobs`), diff their startup sequences. Asymmetric ordering is almost always a bug.

**Pre-`await` checklist:**
- Does this publish a handle, register a callback or start a worker? If yes, is the object fully initialized?
- What invariants am I leaving in an intermediate state?
- Did I just read a value another coroutine could modify before my next line uses it?
- If `CancelledError` lands here, will cleanup run? Should this be in `try/finally` or `asyncio.shield`?
- Does this `async for` / `async with` / `gather` hide more suspension points than I think?

## Comment Policy — Explain WHY, Not WHAT

Comments are short, plain English only. They cost LOC and rot out of sync with code. Default: no comment. Add one only when the code cannot speak for itself. Applies to Python (`#`, `"""`) and TS/JS (`//`, `/** */`) alike.

### REMOVE / never write

- Comments restating the line (`# increment counter`, `# validate creds` over obvious validation)
- Banner / divider / count labels (`# Trading (4)`, `# ---- setup ----`, `# Market data (16)`)
- Docstrings echoing the symbol name (`"""Get bar."""` on `get_bar`)
- Filler Arrange/Act/Assert markers that add nothing
- Plan/phase/finding refs — explain the invariant, not the origin

### KEEP / write only for

- **WHY:** races, ordering/suspension constraints, publish-before-subscribe, await-preemption notes, invariants, trade-offs
- **Hacks / workarounds** + external-system quirks (Exness, TradingView, Mongo, Redis, asyncio, APScheduler)
- `# type: ignore[...]` / `// @ts-expect-error` / `// eslint-disable` — always with their reason
- Warnings about non-obvious failure modes (`# benign — already dropped`)
- Docstrings documenting params / contracts / edge cases / non-obvious return semantics
- Test comments explaining scenario intent or non-obvious setup

### Examples

```python
# KEEP — load-bearing ordering note (see "Await Is Preemption")
# Wire the event bus before any handler can publish: container.get() awaits,
# so a subscriber resolved first would miss publish-before-subscribe events.

# REMOVE — restates the call
# Get the bar from the repository
bar = await repo.get(bar_id)
```

**Route docstrings:** name-echo docstrings on FastAPI routes are removed even though OpenAPI summaries may blank — only docstrings carrying param/contract/edge-case content survive.

**Docstrings:** Minimal. Let type hints carry the heavy lifting. Module-level: brief purpose statement only when non-obvious.

## Testing

- Tests mirror the package: `tests/core_test/`, `tests/engine_test/`, `tests/backtest_test/`, `tests/app_test/`, and `tests/scripts/` for `scripts/`.
- Before restructuring a flow, pin its current behaviour with a test; a refactor that changes that test's result changed behaviour.
- Integration tests that need real MongoDB or Redis use `testcontainers` (`tests/app_test/conftest.py`), so Docker must be running. Do not mock the database when the behaviour under test is a query or an index.
- Nothing may depend on the host timezone: CI runs the suite under `UTC`, `Asia/Ho_Chi_Minh` and `America/Chicago`, and `just test-tz` does the same locally.
- Use pytest fixtures and `monkeypatch` for mocking. Cover service methods, repository methods and error paths; there is no coverage gate (`pytest --cov=src` is available).

## Performance

- No blocking I/O on the event loop. Use a native async client; if a sync library is unavoidable, isolate it with `await loop.run_in_executor(...)`.
- Write in bulk (`BarRepository.insert_many`), not in a loop of single inserts.
- Invalidate cache by pattern (`Cache.delete_pattern("bar:...:*")`), not by guessing individual keys.
- Guard shared in-memory state (for example the bar builders) with an `asyncio.Lock`.
- Full type hints on public functions and class attributes; Pyright checks them.

## Quality Gate

A change is done when all of these pass. Ruff and Pyright must report 0 errors in `src/` and in every file you touch; older test files still carry lint debt, so a repo-wide `ruff check .` is not yet clean.

| Check | Command |
|---|---|
| Tests | `just test` |
| Lint | `uv run ruff check src <touched files>`; format touched files with `uv run ruff format` |
| Type check | `uv run pyright src <touched files>` (settings from `pyrightconfig.json`) |
| Import contracts | `uv run lint-imports` → `Contracts: 8 kept, 0 broken.` |
| Metric ratchet | `uv run python scripts/code_metrics.py --ratchet` |

- The CI `tests` job in `.github/workflows/cicd.yml` runs `lint-imports`, the metric ratchet and `pytest` in each timezone leg. Ruff and Pyright are not CI steps; run them locally.
- **Import contracts** (`[tool.importlinter]` in `pyproject.toml`): the `app → engine → core` layers, domain free of infra, the backtest/live driver independence, shared engine machinery free of drivers, `fastapi` only in `app`, no `bson`, `pandas_market_calendars` only in `core.infra.calendars`, and `tvDatafeed` only in `core.infra.tradingview`.
- **Metric ratchet:** `scripts/code_metrics.py` measures `tiny_share` (share of functions whose body is ≤ 2 statements) and `delegations` (functions whose body is a single `return` or expression calling an attribute) over `src/pocketquant`; the exact definitions are in the script's docstring. `--ratchet` compares them with `max_tiny_share` and `max_delegations` in `[tool.code-metrics]` of `pyproject.toml` and exits 1 when either is above its ceiling.
- The ceiling only moves down. Lower it when a change improves a metric; raising it is a user decision, never a way to make CI green. When the ratchet blocks a change, restructure (for example inline a thin wrapper) — do not inline code only to move the number.
- A tiny share ≤ 30% and ≤ 20 delegations are the aspiration, not a gate.

## Configuration & Secrets

Never hardcode. Use `.env` (local) and environment variables (prod). Never commit `.env` or secrets. Define in `src/pocketquant/core/config.py::Settings` with Pydantic.

- `EXNESS_*` keys live only in `pocketquant-config`. `EXNESS_SECRET_KEY` is a single-line 128-hex secret key; every `.env` value is a single-line `KEY=VALUE`. Secrets are never logged, and `EXNESS_LIVE_TRADING` stays false outside a go-live plan.
