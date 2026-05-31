# Brainstorm — Extract Infrastructure + Execution Packages

**Status:** Design agreed, ready for `/ck:plan`. Implementation (`cook`) runs separately.

## Problem Statement

`pocketquant-core` is not a pure domain core: it carries `persistence/` (Database, Cache, BaseRepository, 4 repos) and `infrastructure/` (broker ports + PaperBroker, Binance REST/WS, scheduler, http_client). Core's deps include pymongo/redis/apscheduler/websockets/httpx/cachetools — heavy adapters masquerading as "core".

Scouting also surfaced incorrect/misplaced logic the move must fix:

1. **backtest ↔ trading circular tangle** (both already violate existing import-linter contracts — which, separately, *do not run today*: config error, missing `include_external_packages=True`).
   - `backtest/handlers/run/handler.py:14` imports `trading.StrategyAppService`, then reaches into its **private** members (`_lock`, `_strategies`, `_brokers`, `_configs`) at `handler.py:101-104` with `# pyright: ignore[reportPrivateUsage]`.
   - `trading` → `backtest`: `run_all_backtests` handler, `jobs/backtest_jobs.py`, `jobs/backtest_strategy_loader.py`, and 4 strategy handlers (`delete`, `list_symbols`, `remove_symbol`, `get_subscription_backtest`) import `backtest.BacktestRepository` / `BacktestAppService`.
2. `infrastructure/scheduling/job_history_repository.py:24` — a *repository* living in infrastructure, inheriting persistence `BaseRepository`.
3. `persistence/repositories/sync_status_repository.py:58-84` — `bump/reset_empty_fetch` counter business rule embedded in the repo.
4. Private-member hack (item 1) is the concrete "incorrect logic".

## Requirements

**Functional (end state):**
- New `pocketquant-infrastructure` package: ALL persistence (Database, Cache, BaseRepository, every repository) + ALL concrete adapters (PaperBroker, Binance REST/WS, JobScheduler, JobHistoryRepository, ResilientHttpClient).
- New `pocketquant-execution` package: shared strategy-execution engine (StrategyAppService, OrderAppService, PositionAppService, RiskCheckHandler) — acts identically for backtest vs forward-test.
- `pocketquant-core`: pure domain/concepts/common/config + **ports** (IBroker, IBrokerFactory, IDataProvider, IRealtimeQuoteProvider) + shared DTOs (OrderResult, AccountBalance, OrderEvent) + **all persisted domain entities** (incl. promoted BacktestResult/Subscription).
- `backtest` and `trading` become true siblings — neither imports the other.
- Library-like packages (no standalone runnable app); api remains the only composition root / HTTP surface.

**Non-functional:**
- import-linter repaired and enforcing the new layered graph in CI.
- All existing tests pass; no behavior change (pure structural refactor + the 4 targeted logic fixes).

## Target Dependency Graph

```
core ──▶ infrastructure ──▶ execution ──▶ { backtest, trading } ──▶ api
                    └──────────────────────────▶ (backtest, trading also import infra directly)
```

- **core** — zero adapter deps. Domain (incl. promoted entities), concepts, common, config, ports, DTOs.
- **infrastructure** → core only. Persistence + adapters. Can serialize any domain entity because all persisted entities now live in core.
- **execution** → core + infrastructure. Shared app-services.
- **backtest** → core + infrastructure + execution. Backtest ENGINE only (run/optimize/performance_calculator/result collection).
- **trading** → core + infrastructure + execution. Live/forward-test only.
- **api** → all. Thin HTTP wrapper + DI composition root + cross-package orchestration if any remains.

No sibling→sibling edges. No cycles (`performance_calculator` verified numpy-only; backtest engine has no residual trading coupling once entities promoted).

## Agreed Decisions (locked)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Ports vs adapters | **Ports + DTOs → core**; concrete adapters → infrastructure |
| 2 | Shared strategy engine home | **New `pocketquant-execution` package** |
| 3 | Core domain repos (Bar/Symbol/SyncStatus/TrackedSymbol) | **→ infrastructure** |
| 4 | Backtest-result coupling (trading reads/deletes results) | **BacktestRepository → infrastructure**; backtest pkg keeps engine only |
| 5 | New package count | **2 new** (infrastructure + execution) → final 6 Python pkgs: core, infrastructure, execution, backtest, trading, api |
| 6 | Entity promotion | **Promote ALL persisted entities to core** (BacktestResult + VOs, Subscription as-is, + existing) so EVERY repo can live in infrastructure uniformly; zero repos remain in backtest/trading |
| 6a | Subscription split (Forward vs Backtest) | **Deferred — sequenced AFTER this extraction**, own brainstorm→plan. This effort promotes the single `Subscription` unchanged. |
| 7 | trading→backtest orchestration edges | Removed — trading reads backtest *results* via infrastructure repos (results' entities now in core); no import of `backtest` package |
| 8 | Bundled cleanups | Relocate JobHistoryRepository (→ infra repositories tree); extract sync-status counter logic to domain service; fix+enforce import-linter; kill private-member hack (add public `inject_prepared_strategy()` on execution service) |
| 9 | Execution path | Brainstorm → `/ck:plan`; `cook` runs separately |

## Key Consequence — "repo follows entity"

A repository may live in `infrastructure` only if the domain entity it (de)serializes lives in `core` (infrastructure sits below backtest/trading; cannot import their domain). Decision #6 promotes **all** persisted entities to core, so all repos move uniformly. Entities to promote into core domain:
- `backtest.domain.BacktestResult`, `OptimizationResult` + VOs (`BacktestMetrics`, `EquityPoint`, `Fill`, `OpenLot`, `OptimizationResultEntry`, `Order`, `Trade`) — ~340 LOC. `OrderEvent` already targeted for core (DTO).
- `trading.domain.Subscription` (+ `SubscriptionAlreadyExistsError`) — 76 LOC.
- Backtest **services** (`performance_calculator.py`) stay in backtest engine (not persisted, numpy-only).

## Logic Fixes (bundled)

1. **Private-member hack** — add public method on execution `StrategyAppService` (e.g. `inject_prepared_strategy(sid, strategy, broker, config)`) acquiring `_lock` internally; backtest run handler calls it instead of touching `_lock/_strategies/_brokers/_configs`. Removes 4 `reportPrivateUsage` ignores.
2. **JobHistoryRepository** — move from `infrastructure/scheduling/` into infra `repositories/` tree; scheduler keeps a typed reference, no behavior change.
3. **sync-status counter** — extract `bump/reset_empty_fetch` business rule into a domain service (e.g. `SyncStatusProgressTracker`); repo keeps only `find_one/find_all/upsert`.
4. **import-linter** — add `include_external_packages = True` (fixes bson contract crash); add layered contract enforcing core ◁ infrastructure ◁ execution ◁ {backtest,trading} ◁ api.

## Migration Edges That Must Be Re-pointed

- Core back-reference shims (would cycle): `common/database/__init__.py`, `common/cache/__init__.py`, `common/jobs/__init__.py` re-export from persistence/infra; `common/health/checks.py:5-6` imports Database/Cache. → move shim targets to infrastructure or drop shims, update all consumers to import from `pocketquant.infrastructure.*`.
- Every consumer of `core.persistence.*` / `core.infrastructure.*` (api DI providers, market-data app services + handlers, backtest engine, trading app services/brokers/jobs) re-points to `pocketquant.infrastructure.*`.
- `core.infrastructure.brokers.interface` (IBroker/IBrokerFactory) + `models`/`events` (DTOs) re-home into core (ports/DTOs), NOT infrastructure — consumers update accordingly.
- api DI: new `ExecutionProvider` (or fold into TradingProvider) wiring execution app-services; `PersistenceProvider`/`InfrastructureProvider` import from new package.
- New package scaffolding: `pyproject.toml` (hatchling, `pocketquant-*` workspace sources), uv workspace already globs `packages/*`.

## Approaches Considered

- **Ports placement:** ports→core vs everything→infra → chose ports→core (DIP, matches CLAUDE.md "IBrokerFactory protocol in core").
- **Engine home:** new execution pkg vs fold-into-infra vs keep-in-trading → chose execution pkg (app services mislabeled as "infrastructure" is a smell; linearizing trading-below-backtest is inverted).
- **Backtest-result coupling:** repo→infra vs handlers→api vs accept-edge → chose repo→infra (hexagonal: repo is adapter, engine is domain; trading reads results via infra, never imports backtest).
- **Entity promotion breadth:** cross-read-only vs all-persisted vs repos-stay-home → chose **all-persisted** (uniform: zero repos left in backtest/trading; accepts Subscription-in-core despite trading-only reader).

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Large import surface re-point — easy to miss a site | import-linter (repaired) + full grep sweep per package; run tests between phases |
| Promoting Subscription to core where only trading reads it (YAGNI tension) | Accepted per decision #6 for uniformity; documented |
| Circular import via core back-reference shims | Explicit phase to relocate/drop shims first |
| Hidden runtime DI breakage (Dishka providers) | Phase boundary = api boots + integration tests green |
| Behavior drift during sync-status counter extraction | Characterization: keep exact `$inc` semantics; unit-test bump/reset before+after |

## Success Criteria

- 6 packages; `core` has zero pymongo/redis/apscheduler/websockets/httpx/cachetools deps.
- `backtest` and `trading` import neither each other; no `reportPrivateUsage` ignores remain on the strategy-injection path.
- `uv run lint-imports` runs and passes with the new layered contracts.
- Full test suite green; api boots.

## Deferred Follow-up — Subscription Split (separate effort)

After this extraction lands, a dedicated brainstorm→plan splits the single `Subscription` into **ForwardSubscription** and **BacktestSubscription** (distinct natures). Captured intent:
- **Lifecycle/running-state:** forward has live running-state + broker binding + boot rehydration; backtest is a one-shot historical run spec with no live state.
- **Independent existence:** a backtest subscription can exist with NO live counterpart (pure research run), and a forward subscription can run without a stored backtest. Neither requires the other.

Why deferred, not folded: it's a domain redesign touching the **load-bearing deterministic-ID recipe** (`subscription.py:52-54` — "existing subscription IDs in production depend on this exact recipe"), the boot migration (`migrate_strategy_id_fields`), and cascade-delete paths. Riding PK/migration changes inside the package move would make verification harder. Sequencing yields two verifiable changes: clean layering first, then a focused domain split with its own characterization tests around the ID/migration risk. Orthogonal to package boundaries — the split changes how many entities sit in core, not the graph shape.

## Open Questions

None — all forks resolved. Subscription split explicitly deferred (see above).

## Next Step

`/ck:plan` with this doc as input → phased plan (suggest: scaffold pkgs → promote entities to core → move ports/DTOs to core → move persistence+adapters to infra → extract execution engine + kill private hack → re-point backtest/trading/api consumers → relocate JobHistoryRepository + extract sync-status service → repair+enforce import-linter → full test pass).
