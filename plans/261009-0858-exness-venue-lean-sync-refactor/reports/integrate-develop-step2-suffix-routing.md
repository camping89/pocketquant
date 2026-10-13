# Integrate develop, step 2: route market data by symbol suffix

`develop` now routes each composite symbol to the data provider its suffix names (`BTCUSDT:BINANCE` → `binance`, `ES1!:TRADINGVIEW` → `tradingview`). CI run 38365651685 passed every job, and the deploy verify step printed `=== Verdict: HEALTHY (20/20 passed, 0 warnings, 0 failures) ===`. After the deploy I seeded the three index futures in prod. They now sync from TradingView every minute, and `/health` reports `healthy`.

## Commits on develop (pushed as b134b91..58e8a1d)

| Commit | Subject |
|---|---|
| 5084c60 | test(market-data): pin how a crypto symbol is routed, synced and described |
| 9d64caa | feat(market-data): route each symbol to the data provider its suffix names |
| 58e8a1d | docs: describe suffix-based market-data routing |

I committed the characterization tests first and ran them green against the old asset-class routing. Their assertions are unchanged in 9d64caa. Only the two constructor helpers changed, because the adapters no longer take `settings` and `symbol_lookup`.

## Design

**The rule lives in one domain module.** `core/domain/market_data/provider_routing_domain_service.py` now holds:
- `provider_id_for(symbol)`, which returns the lower-cased suffix. A symbol with no suffix raises `UnknownDataProviderError`.
- `DATA_PROVIDER_DEFAULTS`, which maps each registered provider id to a default `asset_class` and `calendar_id`. `binance` maps to crypto spot on `CRYPTO_24_7`, and `tradingview` maps to index future on `CME_GLOBEX_EQUITY`.
- `provider_defaults_for(symbol)` and `unseeded_symbol(symbol)`. Both raise `UnknownDataProviderError` when the suffix is not a registered provider.

`UnknownDataProviderError` subclasses `ValueError`, so callers that already caught `ValueError` from the realtime router still catch it.

**Routing adapters.** `RoutingDataProviderAdapter` and `RoutingRealtimeQuoteAdapter` keep their class names, ports and DI positions. Each now takes only `providers`. Both send a symbol to exactly the provider its suffix names and raise `UnknownDataProviderError` for an unregistered suffix. The REST adapter no longer falls back to another provider, because another provider's bars for the same code would be a different instrument. A provider failure still propagates rather than being reported as an empty market. Symbol search goes to `DEFAULT_SEARCH_PROVIDER_ID = "binance"`.

**Removed:** `Settings.market_data_providers`, `Settings.symbol_provider_overrides`, `resolve_provider_ids`, and `core/infra/market_data/symbol_provider_resolver.py`, together with its symbol-document lookup and its CRYPTO_SPOT assumption for unseeded symbols. The env-var docs are gone from `README.md` and `docs/system-architecture.md`. `AssetClass` stays on `Symbol` for calendar and spec defaults. The prod `.env` set neither variable (checked in `pocketquant-config`), and `Settings` ignores extra keys.

**Unseeded defaults now come from the provider.** `SymbolRepository.touch` inserts `unseeded_symbol(symbol)`, and `TradingCalendarFactory.for_symbol` uses `provider_defaults_for(symbol).calendar_id` when no document exists. An unseeded `ES1!:TRADINGVIEW` therefore becomes an index future on the CME calendar. An unseeded `XAUUSD:EXNESS` raises instead of silently becoming 24/7 crypto. When Exness is registered, it needs one entry in `DATA_PROVIDER_DEFAULTS` and one in each router in `app/di/`. A test fails if those three sets differ.

**Health check.** `check_market_data_providers` no longer takes a resolver. It reads the provider from the suffix and checks it against the registered provider ids. A tracked symbol with an unregistered suffix is reported on its own row as `provider: null` plus an `error`. The check itself does not fail, so one bad row cannot hide the state of the other symbols.

**TradingView exchange.** `TRADINGVIEW_EXCHANGE_BY_CODE = {"ES1!": "CME_MINI", "NQ1!": "CME_MINI", "YM1!": "CBOT_MINI"}` in `tradingview_mappers.py`. `split_futures_symbol` takes the exchange from this table, and a missing code raises `ValueError` with the table's name in the message.

**Seeder.** `scripts/seed_index_futures.py` seeds `ES1!:TRADINGVIEW`, `NQ1!:TRADINGVIEW` and `YM1!:TRADINGVIEW`. Contract specs are unchanged.

## Files

- Domain and infra: `provider_routing_domain_service.py`, `routing_data_provider_adapter.py`, `routing_realtime_quote_adapter.py`, `provider_health_check.py`, `trading_calendar_factory.py`, `symbol_repository.py`, `tradingview_mappers.py`, and docstring examples in `tradingview_adapter.py` and `tradingview_quote_adapter.py`. `symbol_provider_resolver.py` is deleted.
- Wiring and config: `app/di/infrastructure.py`, `app/di/market_data.py`, `app/main_extensions.py`, `core/config.py`.
- Scripts: `scripts/seed_index_futures.py`, `scripts/README.md`.
- Web: example strings only (`ES1!:CME_MINI` → `ES1!:TRADINGVIEW`) in 9 files under `web/src`. No logic changed.
- Docs: `README.md`, `docs/code-standards.md` (Composite Symbol Format), `docs/system-architecture.md` (TradingView row, a new "Market-data routing" paragraph, health check, env vars). The prose is English, matching develop's docs, as the coordinator confirmed.

## Tests

New tests:
- `tests/app_test/integration/test_market_data_routing_characterization.py` (6 tests, real Mongo and Redis). An unseeded `BTCUSDT:BINANCE` syncs through the binance child only, its bars and document are stamped crypto/24-7, an outage is raised, a quiet answer is `[]`, search goes to binance, streaming uses the binance child only, and health reports binance/24-7.
- `tests/core_test/unit/domain/market_data/test_provider_routing.py` (rewritten): the suffix becomes the provider id, a missing suffix fails, defaults exist per provider, an unregistered provider has no defaults, and `unseeded_symbol` works.
- `tests/core_test/infra/market_data/test_routing_data_provider_adapter.py` (rewritten): BINANCE and TRADINGVIEW route to their own provider only, the suffix match is case-insensitive, an unknown or missing suffix fails loudly, there is no fallback after a failure, and search goes to the named default.
- `tests/core_test/infra/calendars/test_trading_calendar_factory_unseeded_default.py`: an unseeded BINANCE symbol is 24/7, an unseeded TRADINGVIEW symbol gets CME, an unseeded EXNESS symbol raises, and a seeded record wins.
- `tests/core_test/infra/persistence/test_symbol_repository_touch.py`: two new cases. `touch` stamps TRADINGVIEW defaults and refuses EXNESS without writing anything.
- `tests/core_test/infra/tradingview/test_tradingview_mappers.py`: the exchange table for ES, NQ and YM, the exact table contents, and a missing code (`RTY1!`) raising.
- `tests/app_test/unit/test_data_provider_registration.py`: the providers registered in both DI routers equal the keys of `DATA_PROVIDER_DEFAULTS`.

Updated tests: the realtime router and health-check tests use suffix routing. The closed-market test now pins one call per attempt to the suffix's provider, where it previously pinned attempts × providers. Test fixtures that used `…:CME_MINI` composite names now use `…:TRADINGVIEW`. I removed the fallback, override and "unseeded assumed crypto" tests because the behaviour they pinned is gone by design.

## Gate (local, Windows)

- `uv run lint-imports`: 10 contracts kept, 0 broken.
- `ruff check src/ tests/`: all checks passed. `ruff format --check` passes on the touched files.
- `pyright src/`: 0 errors. On touched test files, pyright reports 8 errors, all of them pre-existing `EventDict` or `_FakeClient` typing debt. Running pyright on the HEAD copies of the same files gives the same counts.
- `pytest`: 945 passed, 1 skipped, and 4 failed plus 4 errors. These are the 4 known `time.tzset` tests on Windows. The baseline before this change was 920 passed with the same 4 failures.
- `web/` vitest was not run locally, because this worktree has no web dependencies installed. CI `build-web` passed.

## CI and deploy

Run 38365651685 passed `tests` under UTC, Asia/Ho_Chi_Minh and America/Chicago, `build-app`, `build-web`, `deploy` and `cleanup-tags`. Verify on VPS printed `=== Verdict: HEALTHY (20/20 passed, 0 warnings, 0 failures) ===`.

## Prod seeding

- Before the change, prod held only `BTCUSDT`, `ETHUSDT` and `SOLUSDT` on `:BINANCE` across `symbols`, `tracked_symbols` and `subscriptions`. No symbol needed renaming.
- The seeder is built to run in prod. It ships in the image at `/app/scripts`, defaults to a dry run, and is idempotent. Before writing, I backed up both collections to `/opt/pocketquant/backups/pre-futures-seed-symbols-20261013.archive` and `pre-futures-seed-tracked-20261013.archive`, 3 documents each.
- `docker exec pocketquant-app python scripts/seed_index_futures.py` ran as a dry run first, then with `--apply`, which printed "Seeded 3 symbol(s) into symbols + tracked_symbols."
- `GET /api/v1/market-data/symbols` returned HTTP 200 and lists `ES1!:TRADINGVIEW`, `NQ1!:TRADINGVIEW` and `YM1!:TRADINGVIEW` as `index_future` / `CME_GLOBEX_EQUITY`, alongside the three Binance symbols.
- In the next `sync_1m` cycles (08:01 to 08:02 UTC) the logs show `tradingview.fetch_completed bars_fetched=99` and `market_data.sync.completed` for all three futures. `/health` reports `healthy`, with each future on `provider: tradingview`, `calendar_id: CME_GLOBEX_EQUITY` and `is_market_open: true`. By 08:03 UTC, prod held 390 `…:TRADINGVIEW` bar documents.

## Verdict

Done. The suffix decides the data provider, an unknown suffix fails loudly, unseeded symbols take provider-keyed defaults, and the futures are live on develop's prod under their `:TRADINGVIEW` names.

## Notes for later phases

- `SymbolLookupHelper.contract_spec` still returns `LINEAR_SPEC` for an unseeded symbol. Only `asset_class` and `calendar_id` are provider-keyed, as the brief asked. Seeding remains the way a futures contract spec is recorded.
- Registering Exness means adding `"exness"` to `DATA_PROVIDER_DEFAULTS` with its asset class and calendar, and adding it to both routers in `app/di/`. `test_data_provider_registration.py` enforces that the three sets stay equal.
