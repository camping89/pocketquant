# Integrate develop, step 3: collapse DI, merge market-data routes, drop scalar wrappers

`develop` now wires the app through 3 DI providers under dishka `STRICT_VALIDATION`, serves every `/market-data` endpoint from one route module, and passes scalars to services where 25 single-use wrapper classes used to sit. The OpenAPI document is byte-identical to the one before the change. CI run 38368787036 passed every job, and the deploy verify step printed `=== Verdict: HEALTHY (20/20 passed, 0 warnings, 0 failures) ===`.

## Commits on develop (pushed as aeb2017..277a09c)

| Commit | Subject |
|---|---|
| 3b998c0 | refactor(app): collapse dependency injection into three strictly validated providers |
| fe72d53 | refactor(app): merge the market-data route modules into one file |
| 8914a46 | refactor(engine): pass scalars to services instead of single-use wrapper models |
| 9ff439a | build: drop the import-linter contracts the layers contract already enforces |
| 277a09c | docs: describe the three DI providers, merged market-data routes and scalar service methods |

I ported the intent of 26451e9 and did not cherry-pick it. Develop's layout differs: `BrokerFactory` already lives in `core/infra/brokers/`, and there is no `SyncPolicies` registry, so the two routing adapters from step 2 move into the adapters provider unchanged.

## DI: 8 providers to 3

Before: `CoreProvider`, `PersistenceProvider`, `InfrastructureProvider`, `ExecutionProvider`, `MarketDataProvider`, `AppTradingServiceProvider`, `BacktestWorkerProvider` and `ServicesProvider`, in 10 files (including `container.py` and `__init__.py`).

After, in 4 files:
- `infrastructure.py`, `InfrastructureProvider`: `Settings` via `from_context(provides=Settings, scope=Scope.APP)`, `EventBus`, `Database`, `Cache`, the 12 repositories, `SymbolLookupHelper`, `TradingCalendarFactory`, `JobScheduler` and `HealthCoordinator`.
- `adapters.py`, `AdaptersProvider`: `TvDatafeedClient`, `IDataProviderPort` as `RoutingDataProviderAdapter` and `IRealtimeQuoteProviderPort` as `RoutingRealtimeQuoteAdapter` (both over `{binance, tradingview}`, unchanged from step 2), and `BrokerFactory`.
- `services.py`, `ServicesProvider`: the market-data app services, the execution engine and live services, backtest execution, and the 13 feature services that routes inject. Factory bodies were moved without changes.
- `__init__.py`: `create_container(settings=None)` builds the three providers with `context={Settings: settings or get_settings()}` and `validation_settings=STRICT_VALIDATION`. `main.py` passes the `Settings` it already holds. `get_settings` is `lru_cache`d, so the instance is the same one the old `CoreProvider` returned.

The "last duplicate wins" risk from the old `services.py:6-9` comment is closed. I checked it directly: adding a second `EventBus` factory to the three providers makes `make_async_container` raise `ImplicitOverrideDetectedError`. The production graph builds cleanly under strict validation.

Tests: `app_factory.py` drops `TestCoreProvider` and uses `create_container(settings)`. `test_app_standalone_runtime.py` uses the same production container. `test_data_provider_registration.py` builds `AdaptersProvider` with its stubs, and its assertion that both routers register exactly the `DATA_PROVIDER_DEFAULTS` keys is unchanged, so the step-2 provider routing stays pinned.

## Routes: 7 market-data modules to 1

`market_data.py` (the aggregator), `market_data_ohlcv.py`, `market_data_status.py`, `market_data_sync.py`, `integrity.py`, `list_symbols.py` and `tracked_symbols.py` are now one `routes/market_data.py`. It defines `router` (prefix `/market-data`, tag `Market Data`) and `tracked_symbols_router` (tag `Tracked Symbols`). `main_extensions.register_routes` still mounts the second router under `/market-data`, so the tag split is preserved. `market_data_quotes.py` stays separate because it owns a different prefix (`/quotes`) and tag.

The route functions moved verbatim, in the old registration order. Two small changes were made: `sync_symbol_background` passes `sync_service.sync_one` straight to `background_tasks.add_task` instead of wrapping it in a closure, and the stale "tracked_symbols router is mounted directly…" comment is gone.

## Wrappers: 25 classes removed

`git grep` counts `^class …(Query|Command)` in `src`: 33 before and 8 after.

Removed, so that the service takes the scalars:
- `GetBacktestQuery`, `SetVerdictCommand` and `SetNameCommand`
- `GetLatestQuoteQuery`, `ListSymbolsQuery` (market data), `GetSyncStatusQuery`, `GetSymbolSyncStatusQuery` and `GetDataLagQuery`
- `UpdateTrackedSymbolCommand`, `RemoveTrackedSymbolCommand` and `ListTrackedSymbolsQuery`
- `GetOrderQuery`, `ListOrdersQuery`, `GetPositionQuery` and `ListPositionsQuery`
- `StartStrategyCommand`, `StopStrategyCommand`, `AddSymbolCommand`, `RemoveSymbolCommand` and `DeleteStrategyCommand`
- `GetStrategiesQuery`, `GetStrategyQuery`, `ListSymbolsQuery` (strategy), `GetStrategyPositionsQuery` and `GetStrategyTradesQuery`

Kept, 8 classes:
- **Request bodies:** `SyncSymbolCommand`, `BulkSyncCommand`, `AddTrackedSymbolCommand` and `RunBacktestCommand`. The route-local bodies `SetVerdictBody`, `SetNameBody`, `CreateSubscriptionBody` and `IntegrityRequest` are not named `…Query`/`…Command`, so they are outside the count. They stay too.
- **Multi-field parameter objects that carry their own behaviour:**
  - `GetOHLCVQuery` coerces naive datetimes to UTC.
  - `BackfillTrackedSymbolCommand` has symbol and mode validators and `resolved_mode()`.
  - `ListTradesQuery` (6 fields) and `ListBacktestsQuery` (5 fields) are both query-parameter bundles.

  Phase 04 T4.4 step 2 kept all four too. Splitting them would move validation into each caller with no gain.

`AddSymbolCommand` went because it was never the HTTP body: `CreateSubscriptionBody` is, and the route copied its fields into the command. The 2000- and 200-character limits from `SetVerdictCommand`/`SetNameCommand` still apply at the HTTP edge through `SetVerdictBody`/`SetNameBody`.

**A regression that pyright caught.** In `SyncStatusQueryService.get_symbol_sync_status`, renaming the parameter left `interval` (now the `str`) feeding the bar repository and the `interval is Interval.MINUTE_1` check. The check would have been silently `False` for 1m. I fixed it by converting once (`tf = Interval(interval)`) and using `tf` throughout. Pyright then reported 0 errors.

## OpenAPI proof

Method: the throwaway script `%TEMP%/pq-step3/dump_openapi.py` imports `pocketquant.app.main`, dumps `app.openapi()` raw (key order preserved) and sorted, and lists `app.routes` in registration order. I took the baseline from a `git archive HEAD src` export of aeb2017 on `PYTHONPATH`, and confirmed it loaded from the export. No snapshot is committed.

| Comparison | Result |
|---|---|
| aeb2017 vs after the route merge (fe72d53 state) | raw OpenAPI identical, route order identical |
| aeb2017 vs final tree (277a09c) | raw OpenAPI identical (0 diff lines), 49 operations, 53 routes in the same order |

There is no schema-name diff to explain: none of the removed wrappers was ever exposed in OpenAPI, and every request-body model kept its class name.

## import-linter: 10 contracts to 8

Dropped:
- "Core imports no inner package"
- "Engine imports no upper package"

Both restate the layers contract (`app` > `engine` > `core`). I proved it by injecting each forbidden edge with the two contracts gone. The edges were core→engine (`core/common/uuid.py` importing `pocketquant.engine.strategy`), core→app and engine→app. Each broke "Layered architecture — app top tier", and each file was restored afterwards.

Kept, though the plan's 3-contract target would have dropped them:
- **The bson ban.** CI runs `lint-imports` but has no ruff step, so ruff `banned-api` alone would leave CI without the check.
- **The four develop-added guards:** driver independence, shared-machinery isolation, pandas_market_calendars confinement and tvDatafeed confinement. They are not implied by layers.

The stale comment that pointed at the deleted `tests/baseline/test_package_layout_contract.py` is removed. `uv run lint-imports`: `Contracts: 8 kept, 0 broken.`

## Docs

All edits are in English, with the `docs/vi/` mirror updated to match.
- `README.md`: the contract count goes from 10 to 8. The brief cited `:87`; the count is on line 112.
- `CLAUDE.md`: the service-method rule now says scalars, and the contract count is 8.
- `docs/code-standards.md` and `docs/vi/code-standards.md`: the DI section, the route and service templates, the worked example, and the naming-table examples.
- `docs/system-architecture.md` and `docs/vi/system-architecture.md`: the DI section (3 providers, `from_context`, `STRICT_VALIDATION`), the routes layer and file list, the `start`/`stop`/`add_symbol`/`list_symbols` signatures, and "Where does X live". `EventBus max_history` was wrong before this change (it said 50; the code says 100) and now reads 100.
- `docs/codebase-summary.md` and `docs/vi/codebase-summary.md`: the `di/` tree, the routes tree and the provider list.
- `docs/project-overview-pdr.md` and `docs/vi/project-overview-pdr.md`: the route module names and "3 Provider classes". Its "8 contracts" line was wrong before this step and is now true.

Journals under `docs/journals/` are historical records and were not changed. Every remaining contract-count claim outside the journals says 8.

## Gate (local, Windows)

- `uv run lint-imports`: 8 kept, 0 broken.
- `uv run ruff check src tests`: all checks passed. `ruff format --check` passes on every touched file. There are 13 pre-existing unformatted files elsewhere in `src`, which I did not touch.
- `uv run pyright src`: 0 errors. Over the touched test files, pyright reports 3 errors, all on lines this change did not touch (accepted test debt).
- Full suite (`uv run python -m pytest -q`, the same interpreter as `just test`): 945 passed, 1 skipped, 4 failed, 4 errors. The failure set is identical to the baseline taken before any edit: the 4 `time.tzset` tests in `test_utc_runtime_guard.py` and `test_cron_trigger_timezone.py`, each also reporting a teardown error. No new failures.
- The intermediate state after the route-merge commit passed `tests/app_test` (157 passed) with identical OpenAPI.

## CI and deploy

Run 38368787036 (head 277a09c) succeeded on every job: `tests` under UTC, Asia/Ho_Chi_Minh and America/Chicago (each runs `lint-imports` and then the full pytest suite on Linux, where the tzset tests run), `build-web`, `build-app`, `cleanup-tags` and `deploy`. The deploy job's "Verify on VPS" step printed `=== Verdict: HEALTHY (20/20 passed, 0 warnings, 0 failures) ===`. I did not run a separate SSH smoke test.

## Verdict

Done. Phase 04's goals now hold on develop in develop's own shape. DI has 3 providers with strict validation and Settings from context, and no silent duplicate can win. The market-data routes are one module, plus the separate `/quotes` module. Single-use wrapper models are gone. The HTTP surface is unchanged, as the identical OpenAPI document shows. The contract count is 8, not the plan's 3, because only the 2 duplicated contracts were redundant; dropping the others would weaken a rule that CI enforces.

## Unresolved questions

- Should `ListBacktestsQuery`, `ListTradesQuery`, `GetOHLCVQuery` and `BackfillTrackedSymbolCommand` also become plain parameters? I kept them because they carry validation or many fields, which matches Phase 04 T4.4. Flattening them is a separate, behaviour-sensitive change.
