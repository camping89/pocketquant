# Re-validation against develop (4b3a77a): Phases 01, 06, 07

Evidence is from develop; paths are under `src/pocketquant/` unless prefixed. **(inference)** marks unchecked claims.

## 1. Phase 01 artefacts on develop

| Artefact | On develop? | Evidence |
|---|---|---|
| `scripts/exness_spike.py`, `tests/scripts/test_exness_spike.py` | No | `git merge-base --is-ancestor e96b2db HEAD` → 1 |
| `cryptography` direct dependency | No | transitive only in `uv.lock` |
| `.env` single-line guard in `.github/actions/get-vps-config/action.yml` | No | — |
| Fixtures `tests/core_test/infra/exness/fixtures/` | Not in any ref | `git log --all -- 'tests/core_test/infra/exness/*'` empty |
| Spike journal `docs/journals/*-exness-api-spike.md` | Not in any ref | same |
| `reports/user-preconditions.md` | Yes | U1, U2 confirmed; host `api.exness.com`; OKX nothing to migrate |

- e96b2db covers T1.2–T1.5 only. Nothing T1.6–T1.12 produces (VPS run outputs, fixtures, journal) exists in git, so Phase 06/07 inputs (`instrument_names`, `ws_subprotocol`, `ticks_subscribe_mode`, `access_point`, `conditions_<I>.json`, `limits.json`, `deals.json`, `snapshot.json`, `summary.json`) are missing.
- Cherry-pick of e96b2db: one conflict in `pyproject.toml` dependencies (develop's `tvdatafeed` line at :28-31 vs `cryptography>=46`; keep both, then `uv lock`).
- It does not run on develop: the spike imports `core.domain.bar.services.bar_builder` (renamed `bar_builder_domain_service.py`), and `is_bar_aligned` now needs a `calendar: ITradingCalendarPort` argument (`core/domain/bar/services/bar_builder_domain_service.py:37-38`). `RiskConfig().max_exposure_percent` still exists.

## 2. Phase 06

Develop facts:
- Routing is by **asset class**: `Settings.market_data_providers: dict[AssetClass, list[str]]` (`core/config.py:77-81`) plus `symbol_provider_overrides` (:84), resolved by `resolve_provider_ids` (`core/domain/market_data/provider_routing_domain_service.py:198-217`). A symbol with no `symbols` doc is assumed `CRYPTO_SPOT` and routes to `binance` (`core/infra/market_data/symbol_provider_resolver.py:187,204-212`).
- `sync_policy.py`, `sync_runner.py`, `app/di/adapters.py`, `split_composite`, `tests/baseline/`, `scripts/code_metrics.py` do not exist on develop.
- `sync_1m` fetches 1m by REST gated by the symbol calendar (`engine/market_data/app_services/sync_jobs.py:189-194`) then cascades; non-24/7 calendars do not cascade 1d (`cascade_aggregator.py:49-60`); 1d/1w come from REST in `sync_backfill` (`sync_jobs.py:757-758`).

| Task | Class | Notes |
|---|---|---|
| T6.1 | STALE | `master` → `develop` |
| T6.2 | VALID, lines stale | `Settings` at `core/config.py:38`; `okx_demo_mode` at :133 |
| T6.3 | VALID, blocked | needs Phase 01 port + import fix |
| T6.4/T6.5 | RESHAPE | no `split_composite` (develop uses `symbol.split(":")[0]`, `binance_adapter.py:63`); fixtures missing; lot math overlaps `ContractSpec` + `PositionCalculatorDomainService` (`core/domain/risk/services/position_calculator_domain_service.py:46-53`) |
| T6.6/T6.7 | VALID | allowlist host `api.exness.com` |
| T6.8/T6.9 | VALID | `BinanceWebSocketAdapter.run_forever` at `core/infra/binance/binance_websocket_adapter.py:97`; `_SUBPROTOCOL`/`_WS_ON_ACCESS_POINT` need the missing journal |
| T6.10/T6.11 | RESHAPE | `IDataProviderPort` (`core/domain/market_data/data_provider_port.py:15`); `BinanceAdapter` (`binance_adapter.py:51`); drop in-progress bar via `calendar.bar_start` (`tradingview_adapter.py:74-75`); `fetch_with_retry` at `sync_internals/provider_fetch.py:32`; router re-raises only if no provider answers (`routing_data_provider_adapter.py:57-103`) |
| T6.12/T6.13 | VALID, names stale | `IRealtimeQuoteProviderPort` Protocol with read-only `last_tick_at` (`realtime_quote_provider_port.py:15-67`); callback at `engine/market_data/app_services/quote_app_service.py:40`; `aggtrade_to_quote_dict` at `binance_mappers.py:72` |
| T6.14 | RESHAPE | no `SyncPolicy`/`MarketCalendar`; sessions belong in an `ITradingCalendarPort` (`trading_calendar_port.py:123`, 11 members) registered in `TradingCalendarFactory` (`core/infra/calendars/trading_calendar_factory.py:24-26`); no per-provider `poll_time_cap_s` (symbols loop serially), so a slow Exness can delay Binance `sync_1m` |
| T6.15 | RESHAPE | register `"exness"` in `app/di/infrastructure.py:53-63` (bars) and `app/di/market_data.py:59-66` (quotes); `ExnessClient` APP-scoped generator; routing via `core/config.py:77-81` or overrides |
| T6.16 | RESHAPE | no `build_sync_policies`; use the routed `IDataProviderPort`; `BarRepository.insert_many(..., source=)` (:42), `count` (:199), `SOURCE_REST_BACKFILL` (`core/domain/bar/entities.py:16`) valid |
| T6.17 | STALE | no ratchet, no `tests/baseline`; 10 import-linter contracts (`pyproject.toml:88-180`) |
| T6.18 | VALID + add | routes: `app/routes/market_data_sync.py:17` (`source` required, `n_bars ≤ 5000`), `market_data_ohlcv.py:74,95`, `market_data_quotes.py:68,77`, `POST /tracked-symbols` admin-token (`tracked_symbols.py:35`). Add a step to seed `symbols` docs (asset class, calendar, contract spec) before tracking, or symbols route to Binance |

## 3. Phase 07

| Task | Class | Notes |
|---|---|---|
| T7.1 | VALID | `default_broker: Literal["paper","okx"]` (`core/config.py:140`) |
| T7.2 | VALID, names stale | `IBrokerPort` (`core/domain/brokers/broker_port.py:13`, abstract :21-106 incl. `subscribe_trades`/`unsubscribe_trades` :92/:104); `IStrategyService` (`strategy_service_interface.py:21`); `HitNRun2StrategyService` (`core/domain/strategy/services/hitnrun2_strategy_service.py:44`); `normalize_quantity` may reduce to min/max-lot clamp via `ContractSpec` |
| T7.3 | VALID, paths stale | `engine/strategy/strategy_app_service.py`, `engine/execution/order_app_service.py`, `engine/execution/position_app_service.py` |
| T7.4/T7.5 | RESHAPE | must implement trade subscription emitting `TradeClosedEvent` (`engine/live/live_trade_collector.py:20-29`); `OrderResult.commission` (`value_objects.py:23`); fixtures missing |
| T7.6 | VALID, blocked | fixtures |
| T7.7 | VALID | `PositionAppService(event_bus, repo, symbol_lookup=None)` (`engine/execution/position_app_service.py:17-21`) |
| T7.8 | STALE | `BrokerFactory` at `core/infra/brokers/broker_factory.py:9`, ctor `(event_bus)`; `default_broker_config` at `app/di/execution.py:72-80` (reads `contract_spec`); T7.3 Verify "no diff under `core/infra/brokers`" conflicts with the factory location |
| T7.9 | STALE | `create_container()` takes no args; Settings via `get_settings()` in `CoreProvider` (`app/di/core.py:14-16`); `tests/baseline/test_app_boot_smoke.py` absent |
| T7.10/T7.11 | STALE | ratchet artefacts absent |
| T7.12 | VALID | branch flow update |

## 4. Plan-level

- G1 holds; develop has the seams (routing adapters, calendar port, `ContractSpec`, `StrategyConfig.broker: str = "paper"` at `core/domain/strategy/value_objects.py:84`).
- Decision 2 stale (ratchet must be rebuilt). Decision 4 superseded by develop's asset-class routing with fallback. Decision 5 covered (nothing to migrate). Decisions 1 and 3 valid.
- PaperBroker has slippage only (`core/infra/brokers/paper/paper_broker_adapter.py:483-486`); spread is Phase 08 work.

## 5. How a venue plugs into develop

- **Bars:** `core/infra/exness/` adapter implementing `IDataProviderPort`; add to `app/di/infrastructure.py:53-63`; route via new `AssetClass` members (`core/domain/shared/enums.py:49-58`) + `DEFAULT_CALENDAR_BY_ASSET_CLASS`/`DEFAULT_SPEC_BY_ASSET_CLASS` (`core/domain/symbol/value_objects.py:69-83`) + `market_data_providers`, or via `SYMBOL_PROVIDER_OVERRIDES`; seed `symbols`/`tracked_symbols` (model on `scripts/seed_index_futures.py`); add to the health-probe map (`app/main_extensions.py:323`). No sync-job change.
- **Quotes:** adapter satisfying `IRealtimeQuoteProviderPort`; add to `app/di/market_data.py:59-66`; router subscribes only via the primary provider (`routing_realtime_quote_adapter.py:64-84`); `run_forever` is gathered across children (:93-95), so it must never raise.
- **Calendar:** implement `ITradingCalendarPort`; add a `calendar_id` constant (`core/domain/symbol/value_objects.py:20-21`); register in `TradingCalendarFactory`. Sync gating, cascade, integrity, data lag and health pick it up. `pandas_market_calendars` usage must stay in `core.infra.calendars` (FX calendar availability unverified).
- **Broker:** `IBrokerPort` adapter with trade subscription; branch in `core/infra/brokers/broker_factory.py:33-71`; config in `default_broker_config`; strategies pick via `config.broker` (`engine/strategy/strategy_app_service.py:120`), brokers pooled per `(broker_type, contract_spec)` at :426-443 with `subscribe_trades` at :441.

## Unresolved questions

- Did the T1.9 VPS spike run, and do fixtures/journal exist outside git?
- Exness routing: new asset classes or per-symbol overrides (`BTCUSD:EXNESS` collides with crypto → Binance)?
- Is the Phase 05 ratchet re-landed on develop?
