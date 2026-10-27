# Re-validation of Phases 02–05 against `develop` (4b3a77a)

Date: 2026-10-12. Scope: phase-02..05, plan.md G2/G3, D4/D5/D6. Read-only; nothing in `src/`, `tests/`, `scripts/` or config was changed.
Convention: **Fact** = verified by grep/read/run in this session. **Inference** = my reading, not verified.

## 0. Blocking repo facts (apply to every phase)

- **History is disjoint.** `git merge-base HEAD backup/master-20261012` prints nothing; the root commits differ (`eaf8d20` vs `15f9dbb`). `29f2f67` (the T2.3 baseline commit) is a local object but **not an ancestor of develop**.
- **Branches:** `origin/master` = `origin/develop` = `develop-sync` = `4b3a77a`; local `master` = `6a0d01c` = backup tag. Every `git switch master && git pull --ff-only` step (T2.1, T3.1, T4.1, T5.1) fails or lands on the old snapshot.
- **CI deploys from both branches:** `.github/workflows/cicd.yml:5` `branches: [master, develop]`, `:187` deploy `if` develop or master. The plan says only "a push to master deploys".
- **The safety net the plan relies on was removed on purpose.** `tests/baseline/` does not exist on develop. Commit `78b7982` (2026-07-04, an ancestor of develop): "Remove scaffolding/characterization tests, brittle baseline snapshots (OpenAPI + route-inventory), DI/boot smokes". T3.13 step 6, T4.2-T4.4 Verify and T4 Risks all run `tests/baseline`.

## 1. Develop design map

**Sync jobs:** `engine/market_data/app_services/sync_jobs.py` (897 LOC). `SYNC_INTERVALS` :72, `_MODULE` :88, `CATCHUP_TARGETS` :90, `_sync_by_intervals` :148 (it gates on the calendar and skips a closed market, recording `status="skipped", error="closed"`), `_run_sync` :296, `_run_integrity` :349, `_run_repair` :395, `sync_1m` :451, `_verify_one_symbol` :526, `sync_verify_cascade` :583, `_run_data_lag` :681, `data_lag_check` :753, `sync_backfill` :757, `register_sync_jobs` :811. **6 cron jobs** (`data_lag_check` is new: `*/1`, `second=30`, grace 60, :846) and the log uses `job_count=6` (:897). A UTC-trigger assertion is at :880-889.
**Integrity:** `app_services/integrity_jobs.py` (188 LOC). `check_integrity` :54 and `repair_integrity` :112 already take `calendar: ITradingCalendarPort`, and `_expected_instants` :37 builds the grid from the calendar.
**Cascade:** `cascade_aggregator.py`, `cascade_for_symbol` :162 takes `calendar`, and `cascade_tfs(calendar)` :49 drops 1d for session calendars.
**SyncService:** `sync_service.py` (203 LOC). `__init__` :39 takes `provider: IDataProviderPort` and `calendar_factory`. `sync_one` :55, `sync_bulk` :144, `_fail` :195.
**`sync_internals/`:** 7 files (the plan says 6). `calendar_stamp.py` is new.

**Provider routing:**
- `core/domain/market_data/provider_routing_domain_service.py:13` `resolve_provider_ids(symbol, asset_class, provider_map, overrides)`. A per-symbol override wins; otherwise the providers come from `provider_map[asset_class]`.
- `core/infra/market_data/symbol_provider_resolver.py:53`: the asset class comes from the persisted `symbols` doc. An unseeded symbol is assumed to be `CRYPTO_SPOT` (:41, warns once).
- `RoutingDataProviderAdapter.fetch_ohlcv` (`routing_data_provider_adapter.py:34-103`): **ordered fallback**. It moves to the next provider on an exception or an empty answer, and re-raises the first failure only when no provider returned bars.
- `RoutingRealtimeQuoteAdapter.subscribe` (`routing_realtime_quote_adapter.py:64-84`): **primary only, no fallback**. It raises `ValueError` when no provider is found.
- Map: `core/config.py:77-84` `market_data_providers = {CRYPTO_SPOT:["binance"], CRYPTO_PERP:["binance"], INDEX_FUTURE:["tradingview"]}` and `symbol_provider_overrides = {}`. Both are env-overridable (`MARKET_DATA_PROVIDERS`, `SYMBOL_PROVIDER_OVERRIDES`; documented in `docs/system-architecture.md:789` and `README.md:40`).
- `AssetClass` has 3 values (`core/domain/shared/enums.py:49-58`).
- Answer: **routing is by asset class, through a map, with per-symbol overrides. It is not by exchange suffix.** Futures use two suffixes, `ES1!:CME_MINI` and `YM1!:CBOT_MINI` (`scripts/seed_index_futures.py:47-57`).

**Calendars:** the `ITradingCalendarPort` port (`trading_calendar_port.py:23`), `Continuous24x7Calendar` and `CmeGlobexCalendarAdapter`. `TradingCalendarFactory.for_symbol` (`core/infra/calendars/trading_calendar_factory.py:44`) resolves by `Symbol.calendar_id` and defaults to 24/7. `calendar_id` is derived from the asset class (`symbol/value_objects.py:69` `DEFAULT_CALENDAR_BY_ASSET_CLASS`).

**DI** (`app/di/`):
- 10 files: `__init__`, `backtest_worker`, `container`, `core`, `execution`, `infrastructure`, `market_data`, `persistence`, `services`, `trading_services`. There is no `broker_factory.py`; `BrokerFactory` now lives in `core/infra/brokers/broker_factory.py`.
- 8 `Provider` classes, built in `container.py:16-29` with a plain `make_async_container(*PROVIDERS)`.
- **No `STRICT_VALIDATION`, no `from_context`**: grep finds 0 hits. dishka 1.9.1 exports both (checked by import).
- `services.py:6-9` still carries the warning that the last duplicate registration silently wins.
- Providers are built in `infrastructure.py:42-64` (`get_data_provider` -> `RoutingDataProviderAdapter{binance, tradingview}`) and `market_data.py:50-69` (`get_realtime_quote_provider` -> `RoutingRealtimeQuoteAdapter{binance, tradingview}`).

**Routes:**
- `app/routes/`: `market_data.py` (aggregator, with the stale comment at :16-18), `market_data_ohlcv.py`, `market_data_status.py` (now also `/data-lag/{symbol}` :71), `market_data_sync.py`, `integrity.py`, `list_symbols.py`, `tracked_symbols.py` and `market_data_quotes.py`.
- `ls app/routes/market_data*.py` = 5.
- Routes are mounted in `main_extensions.py:417-457` (`register_routes`, 65 lines).

**Scalar wrappers:** all 22 class definitions that T4.4 names still exist (21 names; `ListSymbolsQuery` appears twice). Two new candidates: `SetNameCommand` (`engine/backtest/backtest_command_service.py:57`) and `GetDataLagQuery` (`engine/market_data/data_lag_service.py:178`).

**import-linter:** **10 contracts**. `uv run lint-imports --no-cache` prints `Contracts: 10 kept, 0 broken.`. The names (`pyproject.toml:88-177`) are:
- Layered architecture — app top tier (app/engine/core)
- Core domain stays free of infra adapters
- Core imports no inner package
- Engine imports no upper package
- Engine backtest and live drivers stay independent
- Shared engine machinery must not import drivers
- fastapi only in app
- No bson/ObjectId usage — UUID7 only
- pandas_market_calendars confined to core.infra.calendars
- tvDatafeed confined to core.infra.tradingview

ruff `banned-api` bans bson at `:69-71`. The comment at `pyproject.toml:146-148` points to the deleted `tests/baseline/test_package_layout_contract.py`, so it is stale.

**`scripts/code_metrics.py`:** absent on develop. It exists only on the backup tag, together with `tests/scripts/test_code_metrics.py`. Develop's `pyproject.toml:75` sets `pythonpath = ["."]`.

**Docs:**
- `CLAUDE.md`: 24 lines. Line 13 holds the rule "Service methods take Pydantic command/query models"; line 14 says "10 contracts".
- `docs/code-standards.md`: 826 lines, 17 H2 headings.
  - `## Comment Policy — Explain WHY, Not WHAT` is at :455; the async H3 is at :610; `## Configuration & Secrets` is at :760.
  - Stale strings: `### 9. Service Extract-Method Pattern` :177 and "under 200 LOC" :411-413.
  - The naming table (`### Class Naming by Layer` :358) is develop's Adapter/Port/AppService/DomainService suffix convention, and `CLAUDE.md:21` links it.
- Commit `fda359a`: "docs/ = English; docs/vi/ = Vietnamese mirror". `docs/vi/code-standards.md` exists.

**CI:** job `tests` is a 3-TZ matrix (`UTC`, `Asia/Ho_Chi_Minh`, `America/Chicago`). Steps: `uv sync --frozen` :38, TZ check :43, `Check import contracts (layered architecture)` :47-48, `uv run pytest tests/ -q` :50-51. There is **no ruff and no pyright step**. Deploy runs `11-verify.sh` (:239).

## 2. Metric baseline on develop (Fact)

Command: `uv run python <TEMP>/cm/code_metrics.py --json --path src/pocketquant` (the script is copied verbatim from the backup tag to `C:/Users/evele/AppData/Local/Temp/cm/`; `--path` defaults to `src/pocketquant`).

| | functions_total | measured | tiny | tiny_share | delegations | >60 lines |
|---|---|---|---|---|---|---|
| develop 4b3a77a | **950** | **775** | **370** | **0.4774** | **77** | **28** |
| plan baseline 29f2f67 | 794 | 661 | 315 | 0.4766 | 63 | - |
| backup frozen ceiling | - | - | - | 0.4754 | 63 | - |

The functions over 60 lines include `sync_jobs._sync_by_intervals` 146, `sync_verify_cascade` 96, `cascade_for_symbol` 94, `sync_one` 88, `register_sync_jobs` 87, `routing_data_provider_adapter.fetch_ohlcv` 70 and `tradingview_adapter.fetch_ohlcv` 85.
Develop already exceeds the backup ceiling, so the backup `[tool.code-metrics]` values cannot be carried over.

Venue command (T2.6 paths, all still present on develop): **101 passed**. The backup baseline was 79.

## 3. Task classification

Legend: **SNW** = still needed as written. **STALE** = needed, but the citations are stale. **COVERED** = develop already does it. **CONFLICT** = clashes with the develop design.

### Phase 02
| Task | Class | Evidence / develop truth |
|---|---|---|
| T2.1 | STALE | `git switch master` = old snapshot (section 0). The Verify step expects `Contracts: 7 kept`; develop prints **10**. CI has no ruff/pyright, but the local gate is still valid. |
| T2.2 | STALE (reuse) | The script and its tests already exist on `backup/master-20261012`. Copy the files; a cherry-pick of history is impossible because the histories are disjoint. Imports work through `pythonpath=["."]`. |
| T2.3 | STALE | `29f2f67` is not in develop history, and `794/661/315/63` is not develop's baseline. Use **950/775/370 (0.4774)/77** at `4b3a77a`. |
| T2.4 | STALE + CONFLICT | **Stale:** `sync_jobs.py` symbols moved (:72/:90/:148/:451/:583/:757/:811). There are **6** registrations, not 5 (`data_lag_check`), and `job_count=6`. `FakeProvider(IDataProvider)` becomes `IDataProviderPort`. `SyncService(...)` also needs `calendar_factory`; `FakeContainer` must map `TradingCalendarFactory`, plus `SyncStatusRepository` and `Cache` for `data_lag_check`. An unseeded symbol logs `routing.unseeded_symbol`. **Conflict:** commit `78b7982` deleted characterization tests on purpose. Re-adding them reverses a recorded develop decision, so the user decides. Partial overlap already exists: `test_futures_sync_end_to_end.py`, `test_sync_source_labels.py`, `test_sync_jobs_calendar_gate.py`, `test_closed_market_skip_precedes_provider_loops.py`. |
| T2.5 | STALE + CONFLICT | `IDataProvider -> BinanceClient` becomes `IDataProviderPort -> RoutingDataProviderAdapter`. `IRealtimeQuoteProvider -> BinanceWebSocketClient` becomes `IRealtimeQuoteProviderPort -> RoutingRealtimeQuoteAdapter`. `PaperBroker` becomes `PaperBrokerAdapter`, `OKXBroker` becomes `OKXBrokerAdapter`, `WsSubscriptionManager` becomes `WsSubscriptionAppService`, and `StrategyReconcileService` becomes `StrategyReconcileAppService` (`engine/live/`). The `build_test_container` list needs `CoreProvider` handling, because `TestCoreProvider` is at `app_factory.py:46` and `make_test_app` at :66 (unchanged). The same `78b7982` conflict as T2.4 (DI smokes were removed). |
| T2.6 | SNW (rebaseline) | The paths exist. The pass count is now **101**, not 79. |
| T2.7 | STALE | Branch/merge to `master` (section 0). `Contracts: 7` becomes 10. Pushing to develop also deploys. |

### Phase 03
| Task | Class | Evidence |
|---|---|---|
| T3.1 | STALE | Branch base (section 0). |
| T3.2 | STALE, still useful | The split copies are `binance_adapter.py:63` and `binance_websocket_adapter.py:83` (not `binance_client.py:62` / `binance_websocket_client.py:83`). A third split is `tradingview_mappers.py:50` (`partition`). `COMPOSITE_SYMBOL_RE` is at `entities.py:26` and `COMPOSITE_SYMBOL_PATTERN` at :31 (not :19/:24). |
| T3.3 | CONFLICT | `SyncPolicy.data_provider/quote_provider` duplicates the provider map plus the DI dicts. `MarketCalendar`/`ALWAYS_OPEN` duplicate `ITradingCalendarPort`/`Continuous24x7Calendar`/`TradingCalendarFactory`. `cascade` duplicates `cascade_tfs(calendar)`. Suffix lookup contradicts asset-class routing. Imports of `core.domain.market_data.interfaces` and `IDataProvider` no longer exist. |
| T3.4 | CONFLICT | Tests T3.3. |
| T3.5 | STALE (the fold part) / CONFLICT (the policy part) | `sync_internals` now has 7 files (`calendar_stamp.py`). `sync_service` cites `__init__` :39, `sync_one` :55, `sync_bulk` :144, `_fail` :195 and 203 LOC. Folding is still possible; injecting `policies` conflicts. The test lines `test_no_progress_tracking.py:81` and `test_sync_service.py:92` are not :78/:84. Patch-target users include `test_closed_market_skip_precedes_provider_loops.py` and `test_sync_status_calendar.py` (not listed). |
| T3.6 | COVERED (calendar) / STALE (move) | Calendar-aware integrity exists: `integrity_jobs.py:37,54,112`, and `routes/integrity.py:8` already injects `TradingCalendarFactory`. Only the cosmetic move into `bar_integrity.py` is left. |
| T3.7 | CONFLICT (policy) / optional lean split | Runner-by-policy duplicates routing and calendar. `register_sync_jobs` now has 6 jobs plus the UTC assertion. `poll_time_cap_s` has no develop equivalent; this is the one real new capability. |
| T3.8 | COVERED | Consumers already see one composite port: `quote_app_service.py:28`, `ws_subscription_app_service.py:37`, `tracked_symbols_backfill.py:91`. The routing adapters fan out (`routing_realtime_quote_adapter.py:93-114`). The plan path `app/market_data/app_services/...` is stale; it is now `engine/market_data/app_services/`. `stop_quote_feed` is at `main_extensions.py:215/225`. |
| T3.9 | CONFLICT | `get_data_provider` is at `infrastructure.py:42`, not :30. Removing it removes develop's routing seam. |
| T3.10 | STALE/CONFLICT | `main.py:34,53` and `main_extensions.py:189`. The docstrings `cascade_aggregator.py:127`, `job_history_repository.py:5` and `scheduler.py:9` still say `sync_jobs`. 13 test files import `sync_jobs`/`integrity_jobs`/`sync_internals` (several not listed). Three listed tests are gone: `test_di_data_provider.py`, `test_integrity_jobs_repair_source.py`, `test_sync_jobs_source_labels.py` (now `test_sync_source_labels.py`). |
| T3.11-T3.17 | STALE (premise) | Under develop routing, `:OKX` is not suffix-routed. An unseeded `X:OKX` becomes `CRYPTO_SPOT` and then Binance, which drops the suffix (`binance_adapter.py:63`). So the migration is not *required* by develop (Inference). Index citations: `symbol_repository.py:63` (not :44); `subscription_repository.py:98-100`; `deployment.md:211/133` (not :205/:130). The 2026-10-11 prod inventory found 0 docs. |
| T3.12 | STALE | Target files do not exist. Develop has 28 functions over 60 lines (section 2). |
| T3.13 | STALE | `Contracts: 7` becomes 10; venue count 79 becomes 101; `tests/baseline` is absent. |
| T3.18 | STALE | The `master` flow; the `apscheduler_jobs` check needs 6 ids including `data_lag_check`. |

### Phase 04
| Task | Class | Evidence |
|---|---|---|
| T4.1 | STALE | Branch base. |
| T4.2 | STALE + partly CONFLICT | 10 files and 8 providers, not 11 and 493 LOC (develop is 541 LOC). `broker_factory.py` is gone from `app/di`. `STRICT_VALIDATION`/`from_context` are still absent, so that part is still needed. `get_sync_policies` does not exist; moving the routing factories instead works. The test files `test_reconcile_di_resolution.py`, `test_di_data_provider.py` and `tests/baseline/test_app_boot_smoke.py` are gone. |
| T4.3 | STALE | The 8 files are still there (now including `/data-lag`). `register_routes` is at :417-457. Without `tests/baseline` there is no snapshot proof of a byte-identical OpenAPI, so a new guard would be needed (CONFLICT with `78b7982` if a snapshot is re-added). |
| T4.4 | STALE | Paths moved: `engine/backtest/`, `engine/execution/orders_positions_service.py`, `engine/strategy/`. `set_verdict` is at :93 (not :74); `sync_status_service` is at :144/:221 (not :96/:135). Add `SetNameCommand` and `GetDataLagQuery` if consistent. Missing test files: `test_quotes_service.py`, `test_strategy_handlers_declarative.py`, `test_strategy_position_and_trade_handlers.py`, `handlers/status/test_get_sync_status.py`, `test_get_symbol_sync_status.py`. The Verify step runs `tests/baseline` (absent). |
| T4.5 | CONFLICT | 10 contracts, not 7. "Backtest imports no upper package" no longer exists, and "Engine imports no sibling/upper package" is now "Engine imports no upper package". Cutting to 3 would delete 4 develop-added guards: drivers independence, shared machinery, pandas_market_calendars and tvDatafeed. The 2 implied by layers plus the bson contract can go, which gives **7** (Inference: layers semantics already forbid core->engine/app and engine->app). |
| T4.6-T4.7 | STALE | Contract count, venue count, `master` flow. |

### Phase 05
| Task | Class | Evidence |
|---|---|---|
| T5.1 | STALE | Branch base. |
| T5.2 | STALE + CONFLICT | The file is 826 lines (not 799). Comment Policy is at :455 (not :428), async H3 at :610 (not :583), Config & Secrets at :760 (not :733). The 17-H2 count still matches. Forbidden strings present today: `Extract-Method` :177 and `200 LOC` :411-413. **Conflicts:** "Vietnamese prose" contradicts `fda359a` (docs/ English-only, plus a `docs/vi/` mirror to keep in sync). Trimming the suffix table contradicts develop's naming convention, which `CLAUDE.md:21` points to. Section 6 (3 DI modules), section 8 (SyncPolicy) and section 13 (3 contracts) describe a design develop does not have. |
| T5.3 | STALE | `CLAUDE.md` lines are **13 and 14** (not 3 and 12), and the text is "10 contracts", not "(7 contracts)". `README.md:113` also says 10. |
| T5.4 | SNW (rebaseline) | Insert after `cicd.yml:47-48`. Note that the tests job runs 3 times (one per TZ), so the ratchet would run 3 times. Freeze on develop numbers, not 0.4754/63. |
| T5.5 | STALE | `master` flow, contract count. |

### plan.md
- **G2** ("one adapter package, one policy factory, one registry entry; routing strictly by suffix; no router layer"): **CONFLICT**. The develop touchpoints for a new venue are an adapter pair, the 2 DI dicts (`infrastructure.py:54`, `market_data.py:59`), a `Settings.market_data_providers` entry, an `AssetClass` value, a calendar adapter plus a `TradingCalendarFactory` entry and `DEFAULT_CALENDAR/SPEC_BY_ASSET_CLASS`, and a seed script.
- **G3** ("3 import-linter contracts"): **CONFLICT** (10 today; 7 is the defensible floor).
- **D4:** `sync_internals` present, 10 DI files, 8 route files. **D5:** `3 kept` would conflict. **D6:** the venue count must be rebaselined to 101; CI has no ruff/pyright step.

## 4. Decision 4 vs develop routing, and the SyncPolicy question

**Does develop satisfy decision 4? No.** Develop does the opposite on three of the four points:
- it has a router layer (`RoutingDataProviderAdapter`, `RoutingRealtimeQuoteAdapter` plus `SymbolProviderResolver`);
- REST has ordered fallback (`routing_data_provider_adapter.py:60-103`);
- the key is the asset class plus overrides, not the suffix.

The fourth point, "each venue owns its providers", is met in substance by the DI dicts plus the map.

**Minimal delta that keeps the intent of decision 4 inside develop's design** (Inference, not built):
1. Add an Exness asset class (or classes) to `AssetClass`, with defaults in `DEFAULT_CALENDAR_BY_ASSET_CLASS`, `DEFAULT_SPEC_BY_ASSET_CLASS` and `Settings.market_data_providers` = `["exness"]`. A single-entry list means no fallback.
2. Add `"exness"` to the two DI provider dicts.
3. Add an Exness session calendar implementing `ITradingCalendarPort`, registered in `TradingCalendarFactory`. This replaces `MarketCalendar`.
4. Seed `:EXNESS` symbols before tracking them, following `scripts/seed_index_futures.py`.
5. Optional guard: in `SymbolProviderResolver`, an *unseeded* symbol whose suffix is a non-crypto venue returns `[]` instead of assuming `CRYPTO_SPOT`. This prevents `XAUUSD:EXNESS` from silently reaching Binance (the documented trap at `symbol_provider_resolver.py:13-19`).

**Is "SyncPolicy registry plus one shared runner" still meaningful? Mostly no.** Provider ownership, calendar gating, calendar-aware integrity and cascade, and consumer fan-out already exist (T3.6, T3.8 COVERED). A registry would create a second source of truth that fights the provider map and the calendar port. The remaining gaps:
- a per-venue `poll_time_cap_s` (a slow venue delaying `sync_1m`), which can live in the Exness adapter or as a per-provider timeout in the routing adapter;
- the lean goals: folding `sync_internals` and splitting the 897-LOC `sync_jobs.py`, which are independent of Exness.

**Options for the user** (decision 4 and G3 are recorded user decisions; this report does not reverse them):
- **A. Adopt develop routing.** Drop T3.3/T3.4/T3.8/T3.9/T3.11-T3.17; reduce Phase 03 to the T3.2 helper, the optional fold/split and the unseeded guard; rewrite G2/D4. *Pro:* smallest diff, no duplication, keeps TradingView/CME working. *Con:* fallback and asset-class routing remain; the "strict by suffix" property is approximated by config plus the guard.
- **B. Add a strict suffix gate on top.** The resolver rejects provider ids whose venue does not match the suffix. *Pro:* closer to decision 4. *Con:* futures use 2 suffixes for 1 provider, so a suffix-to-provider table is needed anyway, and this partly duplicates the map.
- **C. Keep the SyncPolicy registry as planned.** *Con:* replaces the develop routing and calendar port, breaks the `MARKET_DATA_PROVIDERS`/`SYMBOL_PROVIDER_OVERRIDES` env contract, and conflicts with develop's design. Not recommended.

Phase 02/04/05 also need decisions:
- whether to re-add characterization/snapshot tests that `78b7982` deleted;
- whether G3 is 7 contracts instead of 3;
- whether to drop the Vietnamese-prose and suffix-trim parts of T5.2.

## Unresolved questions
- Prod currently runs develop (`origin/master` = develop). Whether prod `tracked_symbols` holds any `:OKX` or unseeded non-crypto symbols today is not verified.
- I did not run the full `just test`, ruff or pyright on develop, so the T2.1 gate state is unknown.
