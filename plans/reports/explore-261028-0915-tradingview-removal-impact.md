---
title: "TradingView removal impact (read-only scout)"
date: 2026-10-28
author: Explore agent (read-only); saved by the controller
context: owner deprecates TradingView; quotes and bars must come from the broker that executes orders
---

# TradingView removal impact

## 1. TradingView dependencies (verified by grep and reads)

**Becomes dead if TradingView is removed:**
- `src/pocketquant/core/infra/tradingview/` (all 6 modules: `tvdatafeed_client.py`, `tradingview_adapter.py`, `tradingview_quote_adapter.py`, `tradingview_mappers.py`, `tradingview_client_interface.py`, `__init__.py`).
- `src/pocketquant/app/di/adapters.py:43-45, 77-80, 100-104, 114-124`: the client provider and the `"tradingview"` entries in both routers.
- `src/pocketquant/core/domain/market_data/provider_routing_domain_service.py:46`: the `"tradingview"` entry in `DATA_PROVIDER_DEFAULTS`.
- `src/pocketquant/core/config.py:66-107` (`tradingview_*` fields, capabilities, poll floor) and `core/domain/shared/enums.py:62-107` (`TradingViewPlan`, capabilities).
- `src/pocketquant/app/main_extensions.py:66, 275-298` (credential check, health registration).
- `src/pocketquant/engine/market_data/app_services/quote_app_service.py:32-34` (TTL derived from the TradingView poll interval).
- `src/pocketquant/core/infra/market_data/provider_health_check.py:14, 60`.
- `src/pocketquant/core/infra/calendars/cme_globex_calendar_adapter.py` (the CME calendar), if no other symbol uses `CALENDAR_CME_GLOBEX_EQUITY`; none found, its only consumer is the TradingView default.
- `scripts/seed_index_futures.py:45-55`, `scripts/README.md:12`.
- Web: `web/src/lib/symbol-format.ts`, `components/chart/trading-chart.tsx`, `components/backtest/backtest-form.tsx`, `components/ticker-widget/ticker-widget.tsx`, `components/data-lag-badge.tsx`, `components/controls/symbol-selector.tsx`, `types/quote.ts`, `types/market-data.ts`, `lib/datetime.test.ts`.
- Tests: `tests/core_test/infra/tradingview/*`, `tests/app_test/unit/test_tradingview_credentialed.py`, `tests/core_test/infra/calendars/test_cme_globex_calendar.py`, plus routing and integration tests that name it.
- Docs: `docs/system-architecture.md`, `docs/deployment.md`, `docs/codebase-summary.md`, `docs/project-overview-pdr.md`, `docs/code-standards.md`, `README.md`.
- `pyproject.toml` and `uv.lock` (not read for the exact pinned package).

**Not TradingView-specific (verified):** `engine/market_data/app_services/sync_jobs.py` has no "tradingview" string; it uses `calendar_factory.for_symbol` and routing ports, so it survives removal.

## 2. Symbols that depend only on TradingView
- `ES1!:TRADINGVIEW`, `NQ1!:TRADINGVIEW`, `YM1!:TRADINGVIEW` (`scripts/seed_index_futures.py:45-55`; exchange map `tradingview_mappers.py:37-41`).
- No broker alternative in code: `EXNESS_INSTRUMENTS` (`core/infra/exness/exness_mappers.py:28-32`) maps only `XAUUSD`, `EURUSD`, `BTCUSD`; Binance is spot/crypto only (`binance_adapter.py:46`).
- Inference: whether the Exness account offers US index CFDs is not answerable from code; `ExnessClient.instruments()` (`exness_client.py:369`) would answer it at runtime.

## 3. Broker data paths

| Path | History | Live | Bar construction | Calendar |
|---|---|---|---|---|
| Exness REST (`exness/exness_adapter.py:37-76`) | `getCandleHistory` paged backward, `count=-n`, `price_type=bid`; page size from broker limits, default 1000 (`exness_client.py:130-134`); depth beyond that unverified | none | broker candles; in-progress candle dropped via `exness_bar_start` | `EXNESS` session calendar |
| Exness WS (`exness/exness_stream.py`, `exness_quote_adapter.py`) | n/a | one signed reconnecting stream on the account access point; backoff 1→30 s, breaker after 10 failures with 300 s pause (`exness_stream.py:29-32`) | ticks; `bar_app_service.py:102` builds bars via `calendar.bar_start` | `EXNESS` |
| Binance REST (`binance/binance_adapter.py`) | klines 1000/call, `_INTER_CALL_SLEEP_S=0.1` (`:30-31`, `:125`); budget 2 weight/call, 1200/min (`:3`) | none | broker klines | `CRYPTO_24_7` |
| Binance WS (`binance/binance_websocket_adapter.py`) | n/a | `@aggTrade`, reconnect backoff 1→60 s, 5 s watchdog | ticks | `CRYPTO_24_7` |

## 4. CPU-heavy calendar paths
- Removed with CME (verified): `cme_globex_calendar_adapter.py:158` `trading_minutes` (iterrows), `:204` `_periods_per_year` (iterrows, `lru_cache(16)`), `:233` `_window_rows` (iterrows per instant lookup), `:166` `bar_start`.
- Callers that stay (verified): `integrity_jobs.py:49-50` (per-minute `trading_minutes` + `bar_start` loop) and `:103`; `cascade_aggregator.py:142-145` (per-bucket `bar_start`) and `:197` (`trading_minutes` per bucket). Their cost falls only if the calendar is cheap (inference).
- Exness calendar (verified): `exness_session_calendar_adapter.py` has no pandas import; `bar_start` is arithmetic off `session_open`. Cost not measured (inference: cheap).
- Not read: CME `session_date` (`:108-125`), crypto calendar.

## 5. Concurrency facts (verified)
- TradingView: one `asyncio.Lock` in `TvDatafeedClient` (`tvdatafeed_client.py:102, 117`); scraper calls run in `asyncio.to_thread` under `wait_for` (`:120-124`); history and quotes share one client and lock (`adapters.py:77-80`).
- Exness: one shared `ExnessClient` (`adapters.py:83-87`) with `_access_point_lock` (`exness_client.py:210`) and `_RequestPacer` at strictest rate × 1.2 (`:116-120`, `:147-168`, `:348-355`); 429 retry with `asyncio.sleep` (`:306-312`); transport retry `2**attempt` (`:329`).
- Binance WS: per-trade logging is DEBUG on purpose because INFO saturates the loop (`binance_websocket_adapter.py:198-199`).
- `CLAUDE.md`: single uvicorn worker; scheduler, WS feeds and broker are in-process singletons.

## Risks
- ES/NQ/YM have no broker-sourced path; removing TradingView without a new source removes them.
- Exness history depth depends on runtime `max_candles` and retention (unconfirmed).
- A single shared `ExnessClient` pacer: any second consumer (e.g. a separate data process) shares or splits the rate budget.

## Unresolved questions
- Does the Exness account offer ES/NQ/YM-equivalent CFDs (`ExnessClient.instruments()`)?
- Exact TradingView package pinned in `pyproject.toml` / `uv.lock`.
- Cost of CME `session_date` and the crypto calendar (not read).
